"""Monte Carlo do balanço horário do NE em 2030 (regra 14).

Uso: python -m src.sim.montecarlo [--n 2000] [--bloco 7] [--semente 20261112]
Pré-requisitos: src.sim.sinteticos (perfis, resíduos, pool hidrotérmico).
Saídas: reports/mc/*.csv e reports/figures/mc*.png
Validação contra a importação observada de 2022–2025: src.sim.backcast.

Cada sorteio d = (ano meteorológico w ∈ 1995–2025, ano hidrotérmico h ∈ 2022–2025,
sequência de blocos de resíduos). Os resíduos fora da amostra das quatro séries (carga,
MMGD, CF eólico, CF solar) são reamostrados JUNTOS, em blocos de `bloco` dias iniciados à
00h, escolhidos na janela 2024-07..2025-12 entre dias com dia do ano a ±14 dias do dia-alvo
(preserva ciclo diário, sazonalidade, autocorrelação e dependência entre séries).
Os resíduos são RECENTRADOS: subtrai-se de cada série a média esperada sob o próprio esquema
de sorteio, e as formas de carga e MMGD são renormalizadas para média 1 em cada sorteio. Assim
os resíduos devolvem variabilidade horária sem deslocar o nível anual, que vem dos cenários
(carga, MMGD) e das funções de transferência (CF). Ver docs/decisoes.md, decisão 38.
Os MESMOS sorteios são usados em todos os cenários (números aleatórios comuns), de modo que
as diferenças entre cenários são pareadas. A incerteza amostrada é só a climática e
operacional (clima, resíduos, hidrologia/despacho histórico); as escolhas de cenário
(data centers, eólica) ficam como eixos separados. Nenhum resultado é probabilidade de
déficit de suprimento: importação é necessidade de importação do restante do SIN.
"""
from __future__ import annotations

import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.paths import FIGURES, PROCESSED, REPORTS
from src.sim.deterministico import l_dc_2030, load_cfg

OUT = REPORTS / "mc"
SEMENTE = 20261112
JANELA_DOY = 14


# ------------------------------------------------------------------ insumos
class Insumos:
    def __init__(self, anos_clima=None):
        S = pd.read_parquet(PROCESSED / "sinteticos_2030.parquet")
        if anos_clima is not None:
            S = S[S.ano_clima.isin(anos_clima)]
        self.anos = np.array(sorted(S.ano_clima.unique()))
        self.A0 = S.pivot(index="t", columns="ano_clima", values="A0")[self.anos].to_numpy().T   # (nw, 8760)
        self.E0 = S.pivot(index="t", columns="ano_clima", values="E0")[self.anos].to_numpy().T
        self.B0 = S.pivot(index="t", columns="ano_clima", values="B0")[self.anos].to_numpy().T
        self.C0 = S.pivot(index="t", columns="ano_clima", values="C0")[self.anos].to_numpy().T
        H = pd.read_parquet(PROCESSED / "hidrotermica_pool.parquet")
        self.anos_h = np.array(sorted(H.ano_hidro.unique()))
        self.hid = H.pivot(index="t", columns="ano_hidro", values="hid")[self.anos_h].to_numpy().T
        self.ter = H.pivot(index="t", columns="ano_hidro", values="ter")[self.anos_h].to_numpy().T
        # regra de despacho hidráulico emulada: beta intradiário e limites mensais por ano
        F = pd.read_parquet(PROCESSED / "ne_features_h.parquet", columns=["t", "ano", "L_net", "L_gross", "eol_bal", "sol_central", "hid", "interc"])
        F = F[F.ano.isin(self.anos_h)].set_index("t")
        # referências históricas citadas nos relatórios (fluxo não é capacidade; decisão 26)
        self.import_max_hist_MW = float((-F.interc).max())
        self.L_gross_api_2025 = float(F.L_gross[F.ano == 2025].mean())
        F["nl"] = F.L_net - F.eol_bal - F.sol_central
        self.beta, self.hmin, self.hmax = [], [], []
        mes30 = pd.date_range("2030-01-01", "2030-12-31 23:00", freq="h").month.to_numpy() - 1
        for ano in self.anos_h:
            g = F[F.ano == ano]
            dh = g.hid - g.hid.groupby(g.index.date).transform("mean")
            dn = g.nl - g.nl.groupby(g.index.date).transform("mean")
            self.beta.append(np.polyfit(dn, dh, 1)[0])
            mm = g.hid.groupby(g.index.month)
            self.hmin.append(mm.min().to_numpy()[mes30])
            self.hmax.append(mm.max().to_numpy()[mes30])
        self.beta, self.hmin, self.hmax = np.array(self.beta), np.array(self.hmin), np.array(self.hmax)
        R = pd.read_parquet(PROCESSED / "residuos_pool.parquet").set_index("t")
        full = pd.date_range(R.index.min().normalize(), R.index.max().normalize() + pd.Timedelta(hours=23), freq="h")
        R = R.reindex(full)
        dias = R.index.normalize().unique()
        arr = R[["A0", "E0", "B0", "C0"]].to_numpy().reshape(len(dias), 24, 4)
        self.res = arr                                   # (ndias, 24, 4)
        self.dia_ok = ~np.isnan(arr).any(axis=(1, 2))
        self.doy_pool = dias.day_of_year.to_numpy()


def candidatos(ins: Insumos, bloco: int):
    """Para cada bloco do ano-alvo: (dia inicial k, nº de dias L, inícios candidatos no pool)."""
    nd = len(ins.dia_ok)
    starts_ok = np.array([ins.dia_ok[j:j + bloco].all() and j + bloco <= nd for j in range(nd)])
    for k in range(0, 365, bloco):
        doy_alvo = k + 1
        dist = np.abs(((ins.doy_pool - doy_alvo) + 182) % 365 - 182)
        yield k, min(bloco, 365 - k), np.flatnonzero(starts_ok & (dist <= JANELA_DOY))


def centro_residuos(ins: Insumos, bloco: int) -> np.ndarray:
    """Média esperada de cada série de resíduos sob o esquema de sorteio (vetor de 4).

    Os resíduos fora da amostra não têm média zero, e o sorteio por época do ano pesa os meses
    de forma desigual (jan–jun só existe em 2025 no pool). Subtrair este vetor faz com que o
    valor esperado do resíduo sorteado seja exatamente zero em cada série.
    """
    dm = ins.res.mean(axis=1)                             # média diária (ndias, 4)
    tot = np.zeros(dm.shape[1])
    for _, L, cand in candidatos(ins, bloco):
        tot += sum(dm[cand + i] for i in range(L)).mean(axis=0)
    return tot / 365


def sortear(ins: Insumos, n: int, bloco: int, semente: int) -> dict:
    """Sorteios reprodutíveis: ano meteorológico, ano hidrotérmico e dias de resíduo (n × 365)."""
    rng = np.random.default_rng(semente)
    w = rng.integers(0, len(ins.anos), n)
    h = rng.integers(0, len(ins.anos_h), n)
    dias = np.empty((n, 365), dtype=int)
    for k, L, cand in candidatos(ins, bloco):
        j = rng.choice(cand, n)
        dias[:, k:k + L] = j[:, None] + np.arange(L)[None, :]
    return {"w": w, "h": h, "dias": dias, "bloco": bloco, "semente": semente,
            "centro": centro_residuos(ins, bloco)}


def componentes(ins: Insumos, sd: dict, idx: np.ndarray, c: dict, opc: dict | None = None) -> dict:
    """Componentes horários (len(idx) × 8760) de um lote de sorteios: carga bruta e MMGD (MW),
    CF eólico e solar, térmica (MW) e ano hidrotérmico.

    Opções: `sem_residuo` (perfis suavizados), `residuo_bruto` (resíduos sem recentrar nem
    renormalizar; só para medir o efeito da correção), `L_gross` e `MMGD` (níveis em MWmed).
    """
    opc = opc or {}
    r = ins.res[sd["dias"][idx]].reshape(len(idx), 8760, 4)
    if opc.get("sem_residuo"):
        r = np.zeros_like(r)
    elif not opc.get("residuo_bruto"):
        r = r - sd["centro"]                              # valor esperado zero em cada série
    w, h = sd["w"][idx], sd["h"][idx]
    Lbar = opc.get("L_gross", c["carga"]["L_gross_sem_dc_MWmed"]["valor"])
    Mbar = opc.get("MMGD", c["mmgd"]["media_2030_MWmed"]["valor"])
    L = ins.A0[w] + r[..., 0]
    M = np.clip(ins.E0[w] + r[..., 1], 0, None)
    if not opc.get("residuo_bruto"):                      # o nível anual vem do cenário
        L = L / L.mean(axis=1, keepdims=True)
        M = M / M.mean(axis=1, keepdims=True)
    cfe_raw = ins.B0[w] + r[..., 2]
    cfs_raw = ins.C0[w] + r[..., 3]
    clip = {"cfe_energia_ajustada_%": float(100 * (np.abs(cfe_raw - np.clip(cfe_raw, 0, 1)).sum() / np.clip(cfe_raw, 0, 1).sum())),
            "cfs_energia_ajustada_%": float(100 * (np.abs(cfs_raw - np.clip(cfs_raw, 0, 1)).sum() / np.clip(cfs_raw, 0, 1).sum()))}
    return {"L": L * Lbar, "MMGD": M * Mbar, "cfe": np.clip(cfe_raw, 0, 1), "cfs": np.clip(cfs_raw, 0, 1),
            "ter": ins.ter[h], "h": h, "clip": clip}


def series(ins: Insumos, sd: dict, idx: np.ndarray, c: dict, opc: dict | None = None):
    """Margem sem hidráulica, eólica e DC (`base`), CF eólico, ajuste do limite [0, 1] e ano hidrotérmico."""
    k = componentes(ins, sd, idx, c, opc)
    cap_sol = (opc or {}).get("cap_sol", c["solar"]["capacidade_2030_MW"]["valor"])
    base = k["ter"] + k["cfs"] * cap_sol - (k["L"] - k["MMGD"])
    return base, k["cfe"], k["clip"], k["h"]


def hidraulica(ins: Insumos, h: np.ndarray, nl: np.ndarray, modo: str) -> np.ndarray:
    """Geração hidráulica do NE em 2030 (n × 8760) segundo a convenção `modo`.

    - "regra_historica" (central): energia diária do ano hidrotérmico h; forma intradiária
      = média diária + beta_h × desvio intradiário da carga líquida simulada `nl` (carga −
      MMGD − eólica − solar − térmica), limitada ao mín./máx. mensal histórico de h e
      reajustada até conservar a energia diária. beta_h é estimado no próprio ano (0,27–0,43)
      sobre a carga líquida observada, isto é, com a geração já cortada; descontar ou não a
      térmica muda beta em menos de 0,005.
    - "historico_sorteado": série horária observada do ano h (sem resposta ao clima sorteado).
    - "plana": energia anual do ano h distribuída de forma constante (pessimista).
    """
    hid = ins.hid[h]
    if modo == "historico_sorteado":
        return hid
    if modo == "plana":
        return np.repeat(hid.mean(axis=1, keepdims=True), 8760, axis=1)
    n = len(h)
    Ed = hid.reshape(n, 365, 24).mean(axis=2, keepdims=True)
    dev = nl.reshape(n, 365, 24) - nl.reshape(n, 365, 24).mean(axis=2, keepdims=True)
    lo, hi = ins.hmin[h].reshape(n, 365, 24), ins.hmax[h].reshape(n, 365, 24)
    x = np.clip(Ed + ins.beta[h][:, None, None] * dev, lo, hi)
    # devolve a energia diária cortada pelos limites às horas que ainda têm folga; a energia
    # diária está sempre dentro dos limites mensais do próprio ano, então a correção converge
    for _ in range(30):
        falta = Ed - x.mean(axis=2, keepdims=True)        # MWmed do dia ainda não alocados
        pend = np.abs(falta[..., 0]) > 0.05               # dias que ainda não fecham (n, 365)
        if not pend.any():
            break
        xp, fp, lop, hip = x[pend], falta[pend], lo[pend], hi[pend]
        livre = np.where(fp > 0, xp < hip - 1e-9, xp > lop + 1e-9)
        x[pend] = np.clip(xp + np.where(livre, fp * 24 / np.maximum(livre.sum(axis=1, keepdims=True), 1), 0.0), lop, hip)
    return x.reshape(n, 8760)


def max_run(b: np.ndarray) -> np.ndarray:
    """Maior sequência de True por linha (vetorizado)."""
    c = np.cumsum(b, axis=1)
    reset = np.where(~b, c, 0)
    return (c - np.maximum.accumulate(reset, axis=1)).max(axis=1)


def metricas(M: np.ndarray, c: dict) -> dict:
    imp = np.clip(-M, 0, None)
    exc = np.clip(M, 0, None)
    lim = c["intercambio"]["limite_exportacao_MW"]["valor"]
    out = {"importacao_TWh": imp.sum(1) / 1e6, "horas_importacao": (M < 0).sum(1),
           "importacao_p95_MW": np.percentile(imp, 95, axis=1), "importacao_pico_MW": imp.max(1),
           "maior_sequencia_importacao_h": max_run(M < 0), "excedente_TWh": exc.sum(1) / 1e6,
           "excedente_acima_limite_exp_TWh": np.clip(M - lim, 0, None).sum(1) / 1e6,
           "horas_acima_limite_exp": (M > lim).sum(1)}
    for L in c["intercambio"]["limites_importacao_sensibilidade_MW"]["valores"]:
        out[f"horas_import_acima_{L // 1000}GW"] = (imp > L).sum(1)
    return out


def simular(ins, sd, c, d, combos, lote=250, opc=None, ldc_override=None):
    rows, clips = [], []
    n = len(sd["w"])
    for i0 in range(0, n, lote):
        idx = np.arange(i0, min(n, i0 + lote))
        base, cfe, clip, h = series(ins, sd, idx, c, opc)
        clips.append(clip)
        modo = (opc or {}).get("hidro", "regra_historica")
        cache = {}
        for cen_dc, cen_w in combos:
            ldc = ldc_override if ldc_override is not None else l_dc_2030(cen_dc, d)[0]
            cap = c["eolica"]["capacidade_2030_MW"][cen_w]["valor"]
            if cen_w not in cache:
                cache[cen_w] = base + cfe * cap + hidraulica(ins, h, -(base + cfe * cap), modo)
            M = cache[cen_w] - ldc
            m = metricas(M, c)
            rows.append(pd.DataFrame({"sorteio": idx, "ano_clima": ins.anos[sd["w"][idx]],
                                      "ano_hidro": ins.anos_h[sd["h"][idx]], "cenario_dc": cen_dc,
                                      "cenario_eolico": cen_w, "L_DC_MWmed": ldc, **m}))
    return pd.concat(rows, ignore_index=True), pd.DataFrame(clips).mean()


def compensacao(ins, sd, c, d, cen_dc, cen_w, ref: pd.DataFrame, idx):
    """ΔW eólico por critério sobre a MÉDIA dos sorteios (bisseção) e por sorteio (vetorizada)."""
    base, cfe, _, h = series(ins, sd, idx, c)
    cap = c["eolica"]["capacidade_2030_MW"][cen_w]["valor"]
    Gw = lambda capw: base + cfe * capw + hidraulica(ins, h, -(base + cfe * capw), "regra_historica")
    ldc = l_dc_2030(cen_dc, d)[0]
    r = ref.set_index("sorteio").loc[idx]
    out = {"cenario_dc": cen_dc, "cenario_eolico": cen_w, "L_DC_MWmed": ldc,
           "dW_energia_anual_MW": ldc / cfe.mean()}
    crit = {"importacao_anual": (lambda M: np.clip(-M, 0, None).sum(1) / 1e6, "importacao_TWh"),
            "horas_importacao": (lambda M: (M < 0).sum(1), "horas_importacao"),
            "p95_importacao": (lambda M: np.percentile(np.clip(-M, 0, None), 95, axis=1), "importacao_p95_MW")}
    for nome, (f, col) in crit.items():
        alvo_med = r[col].mean()
        lo, hi = 0.0, 40000.0
        while hi - lo > 25:
            mid = (lo + hi) / 2
            if f(Gw(cap + mid) - ldc).mean() > alvo_med:
                lo = mid
            else:
                hi = mid
        out[f"dW_{nome}_media_MW"] = hi
        # por sorteio (bisseção vetorizada)
        lo_v, hi_v = np.zeros(len(idx)), np.full(len(idx), 40000.0)
        alvo = r[col].to_numpy()
        for _ in range(12):
            mid = (lo_v + hi_v) / 2
            acima = f(Gw(cap + mid[:, None]) - ldc) > alvo
            lo_v = np.where(acima, mid, lo_v)
            hi_v = np.where(acima, hi_v, mid)
        out[f"dW_{nome}_p5_MW"], out[f"dW_{nome}_p50_MW"], out[f"dW_{nome}_p95_MW"] = np.percentile(hi_v, [5, 50, 95])
    exc0 = np.clip(Gw(cap), 0, None)
    out["absorcao_excedente_%"] = 100 * np.minimum(exc0, ldc).sum() / (ldc * exc0.size)
    return out


def resumo(D: pd.DataFrame) -> pd.DataFrame:
    mets = ["importacao_TWh", "horas_importacao", "importacao_p95_MW", "importacao_pico_MW",
            "maior_sequencia_importacao_h", "excedente_TWh", "excedente_acima_limite_exp_TWh",
            "horas_import_acima_8GW"]
    q = lambda p: (lambda s: np.percentile(s, p))
    rows = []
    for (a, b), g in D.groupby(["cenario_dc", "cenario_eolico"], sort=False):
        for m in mets:
            s = g[m]
            rows.append({"cenario_dc": a, "cenario_eolico": b, "metrica": m, "media": s.mean(),
                         "p5": q(5)(s), "p50": q(50)(s), "p95": q(95)(s)})
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--n-sens", type=int, default=500)
    ap.add_argument("--bloco", type=int, default=7)
    ap.add_argument("--semente", type=int, default=SEMENTE)
    ap.add_argument("--so-figuras", action="store_true")
    ap.add_argument("--so-sensibilidades", action="store_true")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.so_sensibilidades:
        c, d = load_cfg()
        sensibilidades(Insumos(), c, d, a)
        print(pd.read_csv(OUT / "mc_sensibilidades.csv").round(2).to_string())
        return
    if a.so_figuras:
        figuras(pd.read_parquet(PROCESSED / "mc_sorteios.parquet"), pd.read_csv(OUT / "mc_convergencia.csv"))
        return
    c, d = load_cfg()
    ins = Insumos()
    sd = sortear(ins, a.n, a.bloco, a.semente)
    combos = [(x, y) for x in d["cenarios"] for y in c["eolica"]["capacidade_2030_MW"]]
    D, clip = simular(ins, sd, c, d, combos)
    D.to_parquet(PROCESSED / "mc_sorteios.parquet")
    resumo(D).round(3).to_csv(OUT / "mc_resumo.csv", index=False)

    # convergência (central, base)
    g = D[(D.cenario_dc == "central") & (D.cenario_eolico == "base")].sort_values("sorteio")
    conv = []
    for n in [100, 250, 500, 1000, 1500, 2000]:
        if n > len(g):
            break
        s = g.importacao_TWh.iloc[:n]
        conv.append({"n": n, "media_TWh": s.mean(), "p95_TWh": np.percentile(s, 95),
                     "p95_horario_medio_MW": g.importacao_p95_MW.iloc[:n].mean()})
    C = pd.DataFrame(conv)
    C["var_media_%"] = 100 * C.media_TWh.pct_change()
    C["var_p95_%"] = 100 * C.p95_TWh.pct_change()
    C.round(4).to_csv(OUT / "mc_convergencia.csv", index=False)

    # por ano meteorológico: CF médio dos perfis (frota atual) e importação média (central, base)
    pd.DataFrame({"ano_clima": ins.anos, "cf_eol": ins.B0.mean(axis=1), "cf_sol": ins.C0.mean(axis=1),
                  "importacao_central_base_TWh": g.groupby("ano_clima").importacao_TWh.mean().reindex(ins.anos).to_numpy(),
                  "n_sorteios": g.groupby("ano_clima").size().reindex(ins.anos).to_numpy()}
                 ).round(4).to_csv(OUT / "mc_ano_clima.csv", index=False)

    # diferenças pareadas contra sem_dc
    base = D[D.cenario_dc == "sem_dc"].set_index(["sorteio", "cenario_eolico"])
    P = []
    for (cd, cw), gg in D[D.cenario_dc != "sem_dc"].groupby(["cenario_dc", "cenario_eolico"], sort=False):
        b = base.loc[list(zip(gg.sorteio, [cw] * len(gg)))]
        for m in ["importacao_TWh", "horas_importacao", "importacao_p95_MW", "excedente_TWh"]:
            delta = gg[m].to_numpy() - b[m].to_numpy()
            P.append({"cenario_dc": cd, "cenario_eolico": cw, "metrica": m, "delta_media": delta.mean(),
                      "delta_p5": np.percentile(delta, 5), "delta_p50": np.percentile(delta, 50),
                      "delta_p95": np.percentile(delta, 95), "frac_sorteios_delta_pos": (delta > 0).mean()})
    pd.DataFrame(P).round(3).to_csv(OUT / "mc_diferencas_pareadas.csv", index=False)

    # decomposição da variância (efeitos principais, central/base): ano meteorológico × ano hidrotérmico
    y = g.importacao_TWh
    sst = ((y - y.mean()) ** 2).sum()
    eta = {f: float((g.groupby(f).importacao_TWh.transform("mean") - y.mean()).pow(2).sum() / sst)
           for f in ["ano_clima", "ano_hidro"]}
    eta["residuos_e_interacao"] = 1 - sum(eta.values())
    # comparação com a dispersão entre escolhas de cenário (medianas por cenário)
    med = D.groupby(["cenario_dc", "cenario_eolico"]).importacao_TWh.median()
    inc = {"eta2": eta, "iqr_amostral_central_base_TWh": float(np.subtract(*np.percentile(y, [75, 25]))),
           "amplitude_medianas_entre_cenarios_TWh": float(med.max() - med.min()),
           "amplitude_medianas_dc_com_eolica_base_TWh": float(med.xs("base", level=1).max() - med.xs("base", level=1).min()),
           "amplitude_medianas_eolica_com_dc_central_TWh": float(med.xs("central").max() - med.xs("central").min()),
           "limitacao_cf_0_1_energia_%": clip.to_dict()}
    with open(OUT / "mc_incerteza.json", "w", encoding="utf-8") as f:
        json.dump(inc, f, ensure_ascii=False, indent=1)

    # probabilidade condicional anual de ao menos 1 h com importação acima de L (não é risco de déficit)
    pr = []
    for (cd, cw), gg in D.groupby(["cenario_dc", "cenario_eolico"], sort=False):
        row = {"cenario_dc": cd, "cenario_eolico": cw}
        for L in c["intercambio"]["limites_importacao_sensibilidade_MW"]["valores"]:
            col = f"horas_import_acima_{L // 1000}GW"
            row[f"P_ano_com_hora_acima_{L // 1000}GW"] = (gg[col] > 0).mean()
            row[f"horas_acima_{L // 1000}GW_media"] = gg[col].mean()
        pr.append(row)
    pd.DataFrame(pr).round(3).to_csv(OUT / "mc_limites_importacao.csv", index=False)

    # compensação eólica (subconjunto de sorteios)
    idx = np.arange(min(500, a.n))
    comp = [compensacao(ins, sd, c, d, cd, cw, D[(D.cenario_dc == "sem_dc") & (D.cenario_eolico == cw)], idx)
            for cd in ["conservador", "central", "alto"] for cw in c["eolica"]["capacidade_2030_MW"]]
    pd.DataFrame(comp).round(1).to_csv(OUT / "mc_compensacao_eolica.csv", index=False)

    sensibilidades(ins, c, d, a)
    figuras(D, C)
    with open(OUT / "mc_config.json", "w", encoding="utf-8") as f:
        json.dump({"n": a.n, "n_sens": a.n_sens, "bloco_dias": a.bloco, "semente": a.semente,
                   "janela_doy_dias": JANELA_DOY, "anos_clima": [int(x) for x in ins.anos],
                   "anos_hidro": [int(x) for x in ins.anos_h],
                   "beta_hidro": {int(y): round(float(b), 4) for y, b in zip(ins.anos_h, ins.beta)},
                   "centro_residuos": dict(zip(["A0", "E0", "B0", "C0"], [round(float(x), 6) for x in sd["centro"]])),
                   "import_max_hist_MW": round(ins.import_max_hist_MW, 1),
                   "termica_hist_media_MWmed": {int(y): round(float(v), 1) for y, v in zip(ins.anos_h, ins.ter.mean(axis=1))},
                   "termica_hist_max_MW": round(float(ins.ter.max()), 1),
                   "L_gross_api_2025_MWmed": round(ins.L_gross_api_2025, 1)}, f, indent=1)
    print(pd.read_csv(OUT / "mc_resumo.csv").query("metrica=='importacao_TWh'").to_string())
    print(C.round(3).to_string())
    print(json.dumps(inc, indent=1, ensure_ascii=False))


def sensibilidades(ins, c, d, a):
    """Sensibilidades univariadas com números aleatórios comuns (central, eólica base)."""
    n = a.n_sens
    sd = sortear(ins, n, a.bloco, a.semente)
    pde = c["carga"]["sensibilidade_pde"]
    Lb = c["carga"]["L_gross_sem_dc_MWmed"]["valor"]
    of = pd.read_csv("config/dc_trajetoria_oficial_ne.csv")
    dc2029 = float(of[(of.estudo == "2a RQ PLAN 2026-2030") & (of.ano == 2029) & (of.componente == "total")].mwmed.iat[0])
    ldc_c = l_dc_2030("central", d)[0]
    # a carga global de 2025 na API do ONS (fonte da forma horária) é maior que a do PLAN (fonte do nível)
    pl = pd.read_csv("config/plan_2rq_ne.csv")
    plan25 = float(pl[(pl.variavel == "carga_global") & (pl.ano == 2025)].mwmed.iat[0])
    casos = {
        "referencia": {}, "sem_dc": {"ldc": 0.0},
        "carga -5%": {"opc": {"L_gross": Lb * 0.95}}, "carga +5%": {"opc": {"L_gross": Lb * 1.05}},
        "MMGD baixa": {"opc": {"MMGD": c["mmgd"]["faixa_sensibilidade_MWmed"]["valores"][0]}},
        "MMGD alta": {"opc": {"MMGD": c["mmgd"]["faixa_sensibilidade_MWmed"]["valores"][1]}},
        "hidraulica plana": {"opc": {"hidro": "plana"}},
        "hidraulica historica sorteada (sem resposta)": {"opc": {"hidro": "historico_sorteado"}},
        "DC com atraso de 12 meses": {"ldc": dc2029},
        "base PDE 2035": {"opc": {"L_gross": pde["L_gross_MWmed"]}, "ldc": ldc_c - pde["desconto_dc_embutido_MWmed"],
                          "ldc_sem": -pde["desconto_dc_embutido_MWmed"]},
        "eolica baixa": {"w": "baixa"}, "eolica alta": {"w": "alta"},
        "sem residuos (perfis suavizados)": {"opc": {"sem_residuo": True}},
        "residuos sem recentrar": {"opc": {"residuo_bruto": True}},
        "nivel de carga pela API do ONS": {"opc": {"L_gross": Lb * ins.L_gross_api_2025 / plan25}},
    }
    rows = []
    for nome, k in casos.items():
        Dk, _ = simular(ins, sd, c, d, [("central", k.get("w", "base"))], opc=k.get("opc"), ldc_override=k.get("ldc"))
        D0, _ = simular(ins, sd, c, d, [("sem_dc", k.get("w", "base"))], opc=k.get("opc"), ldc_override=k.get("ldc_sem", 0.0))
        dlt = Dk.importacao_TWh.to_numpy() - D0.importacao_TWh.to_numpy()   # mesmo sorteio (pareado)
        rows.append({"caso": nome, "media_TWh": Dk.importacao_TWh.mean(), "p95_TWh": np.percentile(Dk.importacao_TWh, 95),
                     "horas_media": Dk.horas_importacao.mean(), "p95_horario_MW": Dk.importacao_p95_MW.mean(),
                     "efeito_DC_TWh": dlt.mean(), "efeito_DC_p5": np.percentile(dlt, 5), "efeito_DC_p95": np.percentile(dlt, 95)})
    for bloco in [3, 14]:
        sdb = sortear(ins, n, bloco, a.semente)
        Dk, _ = simular(ins, sdb, c, d, [("central", "base"), ("sem_dc", "base")])
        a1, a0 = (Dk[Dk.cenario_dc == x].importacao_TWh.to_numpy() for x in ["central", "sem_dc"])
        rows.append({"caso": f"blocos de {bloco} dias", "media_TWh": a1.mean(),
                     "p95_TWh": np.percentile(a1, 95), "horas_media": Dk[Dk.cenario_dc == "central"].horas_importacao.mean(),
                     "p95_horario_MW": Dk[Dk.cenario_dc == "central"].importacao_p95_MW.mean(),
                     "efeito_DC_TWh": (a1 - a0).mean(), "efeito_DC_p5": np.percentile(a1 - a0, 5), "efeito_DC_p95": np.percentile(a1 - a0, 95)})
    ins_r = Insumos(anos_clima=list(range(2010, 2026)))
    sdr = sortear(ins_r, n, a.bloco, a.semente)
    Dk, _ = simular(ins_r, sdr, c, d, [("central", "base"), ("sem_dc", "base")])
    a1, a0 = (Dk[Dk.cenario_dc == x].importacao_TWh.to_numpy() for x in ["central", "sem_dc"])
    rows.append({"caso": "anos meteorológicos 2010-2025", "media_TWh": a1.mean(),
                 "p95_TWh": np.percentile(a1, 95), "horas_media": Dk[Dk.cenario_dc == "central"].horas_importacao.mean(),
                 "p95_horario_MW": Dk[Dk.cenario_dc == "central"].importacao_p95_MW.mean(),
                 "efeito_DC_TWh": (a1 - a0).mean(), "efeito_DC_p5": np.percentile(a1 - a0, 5), "efeito_DC_p95": np.percentile(a1 - a0, 95)})
    S = pd.DataFrame(rows)
    ref = S.set_index("caso").loc["referencia"]
    S["delta_media_TWh"] = S.media_TWh - ref.media_TWh
    S.round(3).to_csv(OUT / "mc_sensibilidades.csv", index=False)


def figuras(D: pd.DataFrame, C: pd.DataFrame):
    ordem = ["sem_dc", "conservador", "central", "alto"]
    # cenários ordenados: escala sequencial de um só tom (cinza = sem DC)
    cores = {"sem_dc": "#8a8984", "conservador": "#8fbcef", "central": "#2a78d6", "alto": "#0d3f80"}
    fig, axes = plt.subplots(1, 3, figsize=(13, 4), sharey=True, sharex=True)
    for ax, w in zip(axes, ["baixa", "base", "alta"]):
        for cd in ordem:
            s = np.sort(D[(D.cenario_dc == cd) & (D.cenario_eolico == w)].importacao_TWh)
            ax.plot(s, np.linspace(0, 1, len(s)), color=cores[cd], lw=2, label=cd)
        ax.set_title(f"eólica {w}", loc="left", fontsize=10)
        ax.set_xlabel("importação necessária em 2030 (TWh/ano)", fontsize=9, color="#52514e")
        ax.grid(color="#e4e3df"); [ax.spines[k].set_visible(False) for k in ["top", "right"]]
    axes[0].set_ylabel("probabilidade acumulada (condicional ao cenário)", fontsize=9, color="#52514e")
    axes[0].legend(frameon=False, fontsize=8, loc="lower right")
    fig.tight_layout(); fig.savefig(FIGURES / "mc1_distribuicao_importacao.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.plot(C.n, C.media_TWh, color="#2a78d6", lw=2, marker="o", label="média")
    ax.plot(C.n, C.p95_TWh, color="#eb6834", lw=2, marker="o", label="P95")
    ax.set_xlabel("número de sorteios", fontsize=9); ax.set_ylabel("TWh/ano", fontsize=9)
    ax.set_title("Convergência — importação anual, DC central, eólica base", loc="left", fontsize=10)
    ax.legend(frameon=False, fontsize=8); ax.grid(color="#e4e3df")
    [ax.spines[k].set_visible(False) for k in ["top", "right"]]
    fig.tight_layout(); fig.savefig(FIGURES / "mc2_convergencia.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
