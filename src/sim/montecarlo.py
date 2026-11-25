"""Monte Carlo do balanço horário do NE em 2030 (regra 14).

Uso: python -m src.sim.montecarlo [--n 2000] [--bloco 7] [--semente 20261112]
Pré-requisitos: src.sim.sinteticos (perfis, resíduos, pool hidrotérmico).
Saídas: reports/mc/*.csv e reports/figures/mc*.png
Validação contra a importação observada de 2022–2025: src.sim.backcast.

Cada sorteio d = (ano meteorológico w ∈ 1995–2025, ano hidrotérmico h ∈ 2022–2025,
sequência de blocos de resíduos). Os resíduos fora da amostra das quatro séries (carga,
MMGD, CF eólico, CF solar) são reamostrados JUNTOS, em blocos de `bloco` dias iniciados à
00h, escolhidos na janela 2024-07..2026-10 entre dias com dia do ano a ±14 dias do dia-alvo
(preserva ciclo diário, sazonalidade, autocorrelação e dependência entre séries).
O coeficiente da regra hidráulica emulada é estimado sobre a carga líquida POTENCIAL (geração +
corte), a mesma grandeza a que a regra é aplicada (decisão 52). Como ele cai quando a carga líquida
oscila mais dentro do dia, o caso central usa o coeficiente de 2026, o ano observado com a oscilação
mais próxima da de 2030 (decisão 57); o do próprio ano hidrológico sorteado e a amplitude constante em
MW ficam como sensibilidades.
Os resíduos são RECENTRADOS por mês (solar e MMGD, por mês e hora): subtrai-se de cada série a média
esperada sob o próprio esquema de sorteio, e as formas de carga e MMGD são renormalizadas para média 1 em cada sorteio. Assim
os resíduos devolvem variabilidade horária sem deslocar o nível, que vem dos cenários (carga, MMGD) e
das funções de transferência (CF). Ver docs/decisoes.md, decisões 38 e 56.
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
from src.sim.observado import potencial_frota

OUT = REPORTS / "mc"
SEMENTE = 20261112
JANELA_DOY = 14


# ------------------------------------------------------------------ insumos
COLS_BETA = ["interc", "hid", "ter", "eol_bal", "sol_central", "ger_eol_fc", "pot_eol_fc", "ger_sol_fc", "pot_sol_fc",
             "L_net", "MMGD"]


def desvios_regra(g: pd.DataFrame, potencial: bool = True) -> tuple[pd.Series, pd.Series]:
    """Desvios intradiários (em relação à média do dia) da carga líquida e da hidráulica, nas horas com ambos.

    Carga líquida = carga líquida de MMGD menos eólica e solar. Caso central (decisão 52): eólica e solar
    POTENCIAIS (balanço + corte apurado, `src.sim.observado`), que é a grandeza a que a regra é aplicada
    no simulador.
    `potencial=False` usa a geração realizada, já cortada (versão anterior; decisões 34 e 39).
    """
    if potencial:
        v = g[g[COLS_BETA].notna().all(axis=1) & (g.anomalia_balanco.fillna(1) == 0)]
        P = potencial_frota(g, v)
        nl = g.L_net - P.eol_pot - P.sol_pot
    else:
        nl = g.L_net - g.eol_bal - g.sol_central
    d = g.index.date
    dh = g.hid - g.hid.groupby(d).transform("mean")
    dn = nl - nl.groupby(d).transform("mean")
    ok = dh.notna() & dn.notna()
    return dn[ok], dh[ok]


def beta_regra(g: pd.DataFrame, potencial: bool = True) -> float:
    """Coeficiente da regra hidráulica emulada para um ano de dados horários observados (índice = t):
    regressão do desvio intradiário da hidráulica sobre o da carga líquida (ver `desvios_regra`)."""
    dn, dh = desvios_regra(g, potencial)
    return float(np.polyfit(dn, dh, 1)[0])


def horas_validas(g: pd.DataFrame) -> pd.Series:
    """Horas com todas as séries da regra e com o balanço do ONS fechando."""
    return g[COLS_BETA].notna().all(axis=1) & (g.anomalia_balanco.fillna(1) == 0)


def beta_e_dp(g: pd.DataFrame) -> tuple[float, float]:
    """Coeficiente da regra e desvio-padrão intradiário da carga líquida potencial (MW)."""
    dn, dh = desvios_regra(g, True)
    return float(np.polyfit(dn, dh, 1)[0]), float(dn.std())


def corr_regra(g: pd.DataFrame, potencial: bool = True) -> float:
    """Correlação entre os desvios intradiários da hidráulica e da carga líquida (aderência da regra)."""
    dn, dh = desvios_regra(g, potencial)
    return float(np.corrcoef(dn, dh)[0, 1])


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
        F = pd.read_parquet(PROCESSED / "ne_features_h.parquet", columns=["t", "ano", "L_gross", "anomalia_balanco"] + COLS_BETA)
        ref = load_cfg()[0]["hidro_termica"]["beta_regra"]
        R26 = F[F.t.between(*ref["periodo"])].set_index("t")
        F = F[F.ano.isin(self.anos_h)].set_index("t")
        # referências históricas citadas nos relatórios (fluxo não é capacidade; decisão 26)
        self.import_max_hist_MW = float((-F.interc).max())
        self.L_gross_api_2025 = float(F.L_gross[F.ano == 2025].mean())
        self.beta_ano, self.dp_ano, self.hmin, self.hmax = [], [], [], []
        mes30 = pd.date_range("2030-01-01", "2030-12-31 23:00", freq="h").month.to_numpy() - 1
        for ano in self.anos_h:
            g = F[F.ano == ano]
            b, dp = beta_e_dp(g)                                   # do próprio ano hidrológico
            self.beta_ano.append(b)
            self.dp_ano.append(dp)
            mm = g.hid.groupby(g.index.month)
            self.hmin.append(mm.min().to_numpy()[mes30])
            self.hmax.append(mm.max().to_numpy()[mes30])
        self.hmin, self.hmax = np.array(self.hmin), np.array(self.hmax)
        self.beta_ano, self.dp_ano = np.array(self.beta_ano), np.array(self.dp_ano)
        # caso central: coeficiente do regime de referência (2026) para todos os anos hidrológicos (decisão 57)
        self.beta_ref, self.dp_ref = beta_e_dp(R26[horas_validas(R26)])
        self.beta = np.full(len(self.anos_h), self.beta_ref)
        R = pd.read_parquet(PROCESSED / "residuos_pool.parquet").set_index("t")
        full = pd.date_range(R.index.min().normalize(), R.index.max().normalize() + pd.Timedelta(hours=23), freq="h")
        R = R.reindex(full)
        dias = R.index.normalize().unique()
        arr = R[["A0", "E0", "B0", "C0"]].to_numpy().reshape(len(dias), 24, 4)
        self.res = arr                                   # (ndias, 24, 4)
        self.dia_ok = ~np.isnan(arr).any(axis=(1, 2))
        self.doy_pool = dias.day_of_year.to_numpy()
        self.ano_pool = dias.year.to_numpy()
        self.janela_res = (dias[0].date(), dias[-1].date())
        self.nd = 365                                    # dias do ano-alvo (2030; 366 em anos bissextos)


def candidatos(ins: Insumos, bloco: int):
    """Para cada bloco do ano-alvo: (dia inicial k, nº de dias L, inícios candidatos no pool)."""
    nd = len(ins.dia_ok)
    ndias = getattr(ins, "nd", 365)
    starts_ok = np.array([ins.dia_ok[j:j + bloco].all() and j + bloco <= nd for j in range(nd)])
    for k in range(0, ndias, bloco):
        doy_alvo = k + 1
        dist = np.abs(((ins.doy_pool - doy_alvo) + 182) % 365 - 182)
        yield k, min(bloco, ndias - k), np.flatnonzero(starts_ok & (dist <= JANELA_DOY))


def dias_fora_do_ano(ins: Insumos, ano: int) -> np.ndarray:
    """Dias utilizáveis do pool de resíduos sem os do ano `ano`: nas validações, o ano testado não pode
    receber os próprios resíduos."""
    return ins.dia_ok & (ins.ano_pool != ano)


def mes_dos_dias(nd: int) -> np.ndarray:
    """Mês (0–11) de cada um dos `nd` primeiros dias do ano-alvo (366 = bissexto)."""
    return pd.date_range("2028-01-01" if nd == 366 else "2030-01-01", periods=nd).month.to_numpy() - 1


def centro_residuos(ins: Insumos, bloco: int) -> np.ndarray:
    """Média esperada de cada série de resíduos no ano-alvo, sob o esquema de sorteio (12 meses × 24 h × 4).

    Carga e CF eólico: média do mês. MMGD e CF solar: média do mês em cada hora, porque um centro único
    deslocaria também as horas sem sol e criaria geração solar à noite.
    Os resíduos fora da amostra não têm média zero, e o viés muda com a época do ano: em CF eólico ele é
    grande no 2º semestre de 2024 e quase nulo de janeiro a junho. Um centro único para o ano inteiro
    (usado até 2026-11-25) deslocava o CF nos meses de importação para compensar o viés de outros meses
    (decisão 56). Subtrair o centro do mês zera o valor esperado do resíduo em cada mês e série.
    Meses fora do período (backtest de jan–out) ficam com NaN.
    """
    nd = getattr(ins, "nd", 365)
    e = np.empty((nd,) + ins.res.shape[1:])               # resíduo esperado em cada dia e hora (nd, 24, 4)
    for k, L, cand in candidatos(ins, bloco):
        for i in range(L):
            e[k + i] = ins.res[cand + i].mean(axis=0)
    mes = mes_dos_dias(nd)
    c = np.array([e[mes == m].mean(axis=0) if (mes == m).any() else np.full(e.shape[1:], np.nan) for m in range(12)])
    for j in (0, 2):                                      # carga (A0) e CF eólico (B0): um valor por mês
        c[:, :, j] = c[:, :, j].mean(axis=1, keepdims=True)
    return c


def expandir_centro(centro: np.ndarray, nd: int) -> np.ndarray:
    """Centro (12 meses × 24 h × 4) → horas do ano-alvo (nd·24 × 4)."""
    return np.asarray(centro)[mes_dos_dias(nd)].reshape(nd * 24, -1)


def sortear(ins: Insumos, n: int, bloco: int, semente: int) -> dict:
    """Sorteios reprodutíveis: ano meteorológico, ano hidrotérmico e dias de resíduo (n × 365)."""
    rng = np.random.default_rng(semente)
    w = rng.integers(0, len(ins.anos), n)
    h = rng.integers(0, len(ins.anos_h), n)
    dias = np.empty((n, getattr(ins, "nd", 365)), dtype=int)
    for k, L, cand in candidatos(ins, bloco):
        j = rng.choice(cand, n)
        dias[:, k:k + L] = j[:, None] + np.arange(L)[None, :]
    cm = centro_residuos(ins, bloco)
    return {"w": w, "h": h, "dias": dias, "bloco": bloco, "semente": semente, "centro_mensal": cm.mean(axis=1),
            "centro": expandir_centro(cm, dias.shape[1])}


def componentes(ins: Insumos, sd: dict, idx: np.ndarray, c: dict, opc: dict | None = None) -> dict:
    """Componentes horários (len(idx) × 8760) de um lote de sorteios: carga bruta e MMGD (MW),
    CF eólico e solar, térmica (MW) e ano hidrotérmico.

    Opções: `sem_residuo` (perfis suavizados), `residuo_bruto` (resíduos sem recentrar nem
    renormalizar; só para medir o efeito da correção), `L_gross` e `MMGD` (níveis em MWmed).
    """
    opc = opc or {}
    r = ins.res[sd["dias"][idx]].reshape(len(idx), -1, 4)
    if opc.get("sem_residuo"):
        r = np.zeros_like(r)
    elif not opc.get("residuo_bruto"):
        r = r - sd["centro"]                              # valor esperado zero em cada série e mês
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


def hidraulica(ins: Insumos, h: np.ndarray, nl: np.ndarray, modo: str, beta: np.ndarray | None = None) -> np.ndarray:
    """Geração hidráulica do NE em 2030 (n × 8760) segundo a convenção `modo`.

    - "regra_historica" (central): energia diária do ano hidrotérmico h; forma intradiária
      = média diária + beta × desvio intradiário da carga líquida simulada `nl` (carga −
      MMGD − eólica − solar − térmica), limitada ao mín./máx. mensal histórico de h e
      reajustada até conservar a energia diária. beta vem de `ins.beta` (caso central: regime de
      2026, decisão 57) ou do argumento `beta` (um valor por ano hidrológico); descontar ou não a
      térmica muda beta em menos de 0,005.
    - "historico_sorteado": série horária observada do ano h (sem resposta ao clima sorteado).
    - "plana": energia anual do ano h distribuída de forma constante (pessimista).
    """
    hid = ins.hid[h]
    if modo == "historico_sorteado":
        return hid
    if modo == "plana":
        return np.repeat(hid.mean(axis=1, keepdims=True), hid.shape[1], axis=1)
    n, nd = len(h), hid.shape[1] // 24
    Ed = hid.reshape(n, nd, 24).mean(axis=2, keepdims=True)
    dev = nl.reshape(n, nd, 24) - nl.reshape(n, nd, 24).mean(axis=2, keepdims=True)
    lo, hi = ins.hmin[h].reshape(n, nd, 24), ins.hmax[h].reshape(n, nd, 24)
    b = ins.beta if beta is None else np.asarray(beta)
    x = np.clip(Ed + b[h][:, None, None] * dev, lo, hi)
    # devolve a energia diária cortada pelos limites às horas que ainda têm folga; a energia
    # diária está sempre dentro dos limites mensais do próprio ano, então a correção converge
    for _ in range(30):
        falta = Ed - x.mean(axis=2, keepdims=True)        # MWmed do dia ainda não alocados
        pend = np.abs(falta[..., 0]) > 0.05               # dias que ainda não fecham (n, nd)
        if not pend.any():
            break
        xp, fp, lop, hip = x[pend], falta[pend], lo[pend], hi[pend]
        livre = np.where(fp > 0, xp < hip - 1e-9, xp > lop + 1e-9)
        x[pend] = np.clip(xp + np.where(livre, fp * 24 / np.maximum(livre.sum(axis=1, keepdims=True), 1), 0.0), lop, hip)
    return x.reshape(n, nd * 24)


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


def ic_amostra_de_anos(D: pd.DataFrame, reamostras: int = 4000, semente: int = SEMENTE) -> dict:
    """IC95 das médias (central, eólica base) por reamostragem dos ANOS, não dos sorteios.

    Os sorteios repetem 31 anos meteorológicos e 4 anos hidrotérmicos; aumentar o número deles reduz o erro
    de simulação, mas não a incerteza de a amostra ter só esses anos. Cada reamostra sorteia, com reposição,
    31 anos meteorológicos e 4 hidrotérmicos e tira a média das células clima × hidrologia (peso igual).
    Com 4 anos hidrotérmicos o intervalo é aproximado.
    """
    q = D[D.cenario_eolico == "base"]
    k = ["sorteio", "ano_clima", "ano_hidro"]
    c = q[q.cenario_dc == "central"].set_index(k).importacao_TWh
    s = q[q.cenario_dc == "sem_dc"].set_index(k).importacao_TWh.reindex(c.index)
    rng = np.random.default_rng(semente)
    out = {"reamostras": reamostras, "n_anos_clima": 0, "n_anos_hidro": 0}
    iw = ih = None
    for nome, x in [("importacao_central", c), ("importacao_sem_dc", s), ("efeito_dc_central", c - s)]:
        A = x.groupby(["ano_clima", "ano_hidro"]).mean().unstack().to_numpy()
        assert not np.isnan(A).any(), "célula clima × hidrologia sem sorteio"
        nw, nh = A.shape
        if iw is None:                                     # mesmas reamostras para as três médias
            iw, ih = rng.integers(0, nw, (reamostras, nw)), rng.integers(0, nh, (reamostras, nh))
        ic = lambda m: [float(v) for v in np.percentile(m, [2.5, 97.5])]
        ambos = np.array([A[np.ix_(a, b)].mean() for a, b in zip(iw, ih)])
        out[nome] = {"media_celulas_TWh": float(A.mean()), "ic95_TWh": ic(ambos),
                     "ic95_so_clima_TWh": ic(A.mean(axis=1)[iw].mean(axis=1)),
                     "ic95_so_hidrologia_TWh": ic(A.mean(axis=0)[ih].mean(axis=1)),
                     "erro_padrao_anos_TWh": float(ambos.std()),
                     "erro_padrao_simulacao_TWh": float(x.std() / np.sqrt(len(x)))}
        out["n_anos_clima"], out["n_anos_hidro"] = nw, nh
    return out


def gravar_incerteza(D: pd.DataFrame, clip: dict) -> dict:
    """Decomposição da variância, dispersões e IC da amostra de anos → reports/mc/mc_incerteza.json."""
    g = D[(D.cenario_dc == "central") & (D.cenario_eolico == "base")]
    # efeitos principais (central/base): ano meteorológico × ano hidrotérmico
    y = g.importacao_TWh
    sst = ((y - y.mean()) ** 2).sum()
    eta = {f: float((g.groupby(f).importacao_TWh.transform("mean") - y.mean()).pow(2).sum() / sst)
           for f in ["ano_clima", "ano_hidro"]}
    eta["residuos_e_interacao"] = 1 - sum(eta.values())
    med = D.groupby(["cenario_dc", "cenario_eolico"]).importacao_TWh.median()
    inc = {"eta2": eta, "iqr_amostral_central_base_TWh": float(np.subtract(*np.percentile(y, [75, 25]))),
           "amplitude_medianas_entre_cenarios_TWh": float(med.max() - med.min()),
           "amplitude_medianas_dc_com_eolica_base_TWh": float(med.xs("base", level=1).max() - med.xs("base", level=1).min()),
           "amplitude_medianas_eolica_com_dc_central_TWh": float(med.xs("central").max() - med.xs("central").min()),
           "ic_amostra_de_anos": ic_amostra_de_anos(D), "limitacao_cf_0_1_energia_%": clip}
    with open(OUT / "mc_incerteza.json", "w", encoding="utf-8") as f:
        json.dump(inc, f, ensure_ascii=False, indent=1)
    return inc


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
    ap.add_argument("--so-incerteza", action="store_true", help="refaz mc_incerteza.json a partir dos sorteios gravados")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if a.so_sensibilidades:
        c, d = load_cfg()
        sensibilidades(Insumos(), c, d, a)
        print(pd.read_csv(OUT / "mc_sensibilidades.csv").round(2).to_string())
        return
    if a.so_incerteza:
        antes = json.load(open(OUT / "mc_incerteza.json", encoding="utf-8"))
        inc = gravar_incerteza(pd.read_parquet(PROCESSED / "mc_sorteios.parquet"), antes["limitacao_cf_0_1_energia_%"])
        print(json.dumps(inc["ic_amostra_de_anos"], indent=1, ensure_ascii=False))
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

    inc = gravar_incerteza(D, clip.to_dict())

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
                   "beta_hidro_central": round(ins.beta_ref, 4),
                   "beta_hidro_definicao": "regime de 2026, carga liquida potencial (decisoes 52 e 57)",
                   "beta_hidro_por_ano": {int(y): round(float(b), 4) for y, b in zip(ins.anos_h, ins.beta_ano)},
                   "dp_intradiario_carga_liquida_MW": {**{str(int(y)): round(float(v), 0) for y, v in zip(ins.anos_h, ins.dp_ano)},
                                                       "2026_jan_out": round(ins.dp_ref, 0),
                                                       "2030_simulado": round(dp_intradiario_2030(ins, sd, c), 0)},
                   "centro_residuos": {k: round(float(x), 6) for k, x in zip(["A0", "E0", "B0", "C0"], sd["centro"].mean(axis=0))},
                   "centro_residuos_mensal": {k: [round(float(x), 6) for x in sd["centro_mensal"][:, j]]
                                              for j, k in enumerate(["A0", "E0", "B0", "C0"])},
                   "janela_residuos": [str(ins.janela_res[0]), str(ins.janela_res[1])],
                   "import_max_hist_MW": round(ins.import_max_hist_MW, 1),
                   "termica_hist_media_MWmed": {int(y): round(float(v), 1) for y, v in zip(ins.anos_h, ins.ter.mean(axis=1))},
                   "termica_hist_max_MW": round(float(ins.ter.max()), 1),
                   "L_gross_api_2025_MWmed": round(ins.L_gross_api_2025, 1)}, f, indent=1)
    print(pd.read_csv(OUT / "mc_resumo.csv").query("metrica=='importacao_TWh'").to_string())
    print(C.round(3).to_string())
    print(json.dumps(inc, indent=1, ensure_ascii=False))


def dp_intradiario_2030(ins: Insumos, sd: dict, c: dict, n: int = 300) -> float:
    """Desvio-padrão intradiário da carga líquida simulada (eólica base, sem DC, MW)."""
    idx = np.arange(min(n, len(sd["w"])))
    base, cfe, _, _ = series(ins, sd, idx, c)
    nl = -(base + cfe * c["eolica"]["capacidade_2030_MW"]["base"]["valor"])
    nl = nl.reshape(len(idx), -1, 24)
    return float((nl - nl.mean(axis=2, keepdims=True)).std())


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
        "hidraulica: beta do proprio ano hidrologico": {"beta": ins.beta_ano},
        "hidraulica: amplitude constante em MW": {"beta": ins.beta_ano * ins.dp_ano / dp_intradiario_2030(ins, sd, c)},
    }
    rows = []
    for nome, k in casos.items():
        beta0 = ins.beta
        ins.beta = k.get("beta", beta0)
        Dk, _ = simular(ins, sd, c, d, [("central", k.get("w", "base"))], opc=k.get("opc"), ldc_override=k.get("ldc"))
        D0, _ = simular(ins, sd, c, d, [("sem_dc", k.get("w", "base"))], opc=k.get("opc"), ldc_override=k.get("ldc_sem", 0.0))
        ins.beta = beta0
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
