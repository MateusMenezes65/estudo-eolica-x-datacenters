"""Diagnóstico da subestimação da importação (backtest de 2026 e validação retrospectiva 2022–2025).

Uso: python -m src.sim.diagnostico_importacao [--n 2000]
Pré-requisitos: src.sim.sinteticos, src.sim.backcast, src.sim.anos, src.sim.backtest_2026.
Saídas (reports/sim/): diag_beta_hidro.csv, diag_backcast_beta.csv, diag_substituicao.csv,
diag_2030_beta.csv, diag_perfil_hidro.csv; figuras r15b_perfil_horario_hidraulica.png e
r27_diagnostico_importacao.png.

Pergunta: a importação simulada fica abaixo da observada em 2024, 2025 e 2026. Isso é o erro esperado
de um ano específico ou vem da metodologia? Três testes:
1. Consistência do coeficiente da regra hidráulica. O beta anterior era estimado sobre a carga líquida
   REALIZADA (eólica e solar já cortadas, decisão 39), mas a regra é aplicada à carga líquida
   POTENCIAL simulada. Com corte crescente as duas divergem. Desde a decisão 52 (2026-11-17) o caso
   central usa o beta sobre a carga líquida potencial; aqui os dois são comparados.
2. Substituição de formas (2022–2026). Com os NÍVEIS observados de cada ano, troca-se a forma horária
   simulada de cada parcela (funções de transferência re-treinadas sem o próprio ano, sem resíduos)
   pela observada, e a regra hidráulica pelo despacho observado. Mostra qual parcela explica o erro e
   se o sinal se repete entre anos (sistemático) ou não (ano específico).
3. Efeito em 2030: Monte Carlo do estudo (mesmos 2.000 sorteios) com o beta anterior e o adotado.
"""
from __future__ import annotations

import argparse
import types

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.features.build import calendar_features
from src.paths import FIGURES, PROCESSED, REPORTS
from src.sim import backcast as bc
from src.sim import montecarlo as mc
from src.sim import sinteticos as sint
from src.sim.anos import InsumosAno, simular_ano
from src.sim.deterministico import l_dc_2030, load_cfg

OUT = REPORTS / "sim"
ANOS = [2022, 2023, 2024, 2025, 2026]
FIM_2026 = "2026-10-31 23:00"
COR = {"obs": "#52514e", "real": "#2a78d6", "pot": "#eb6834"}
INK2, GRID = "#52514e", "#e1e0d9"


# ------------------------------------------------------------------ 1. beta
def observado_ano(X: pd.DataFrame, ano: int) -> pd.DataFrame:
    """Parcelas observadas do ano (MWmed por hora). Carga bruta coerente com o balanço do ONS, de modo
    que hid + ter + eólica + solar + MMGD − carga = intercâmbio + cortes (M potencial observado)."""
    g = X[(X.ano == ano) & (X.t <= FIM_2026)].set_index("t").copy()
    req = ["interc", "hid", "ter", "eol_bal", "sol_central", "ger_eol_fc", "pot_eol_fc", "ger_sol_fc", "pot_sol_fc",
           "L_net", "MMGD"]
    g["valida"] = g[req].notna().all(axis=1) & (g.anomalia_balanco.fillna(1) == 0)
    v = g[g.valida]
    fr_e = v.eol_bal.mean() / v.ger_eol_fc.mean()
    fr_s = v.sol_central.mean() / v.ger_sol_fc.mean()
    O = pd.DataFrame(index=g.index)
    O["valida"] = g.valida
    O["hid"], O["ter"], O["MMGD"] = g.hid, g.ter, g.MMGD
    O["eol_real"], O["sol_real"] = g.eol_bal, g.sol_central
    O["eol_pot"], O["sol_pot"] = g.pot_eol_fc * fr_e, g.pot_sol_fc * fr_s
    O["L_bal"] = g.hid + g.ter + g.eol_bal + g.sol_central + g.MMGD - g.interc       # carga bruta implícita no balanço
    O["L_api_liq"] = g.L_net
    O["M"] = O.hid + O.ter + O.eol_pot + O.sol_pot + O.MMGD - O.L_bal
    O["interc"] = g.interc
    O.attrs.update(fr_e=fr_e, fr_s=fr_s)
    return O


def tabela_beta(obs: dict, X: pd.DataFrame) -> pd.DataFrame:
    """Beta anterior (carga líquida realizada) e adotado (potencial) por ano, pela função do Monte Carlo."""
    rows = []
    Xt = X.set_index("t")
    for ano, O in obs.items():
        g = O if ano != 2026 else O[O.valida]
        bruto = Xt.reindex(g.index)
        nl_r = g.L_api_liq - g.eol_real - g.sol_real
        nl_p = g.L_api_liq - g.eol_pot - g.sol_pot
        d = g.index.date
        sd = lambda s: float((s - s.groupby(d).transform("mean")).std())
        rows.append({"ano": ano, "beta_realizada": mc.beta_regra(bruto, False), "beta_potencial": mc.beta_regra(bruto, True),
                     "dp_intradiario_carga_liq_realizada_MW": sd(nl_r), "dp_intradiario_carga_liq_potencial_MW": sd(nl_p),
                     "corte_eolico_%": float(100 * (g.eol_pot - g.eol_real).sum() / g.eol_pot.sum()),
                     "corte_solar_%": float(100 * (g.sol_pot - g.sol_real).sum() / g.sol_pot.sum())})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 2. validação retrospectiva com os dois beta
def backcast_beta(c: dict, Tb: pd.DataFrame, n: int) -> pd.DataFrame:
    ins = mc.Insumos()
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    tb = Tb.set_index("ano").loc[[int(a) for a in ins.anos_h]]
    rows = []
    for nome, b in [("beta anterior (carga líquida realizada)", tb.beta_realizada.to_numpy()),
                    ("beta adotado (carga líquida potencial)", tb.beta_potencial.to_numpy())]:
        ins.beta = b
        for ano in [int(a) for a in ins.anos_h]:
            r = [x for x in bc.simular_ano(ins, c, X, ano, n) if x["convencao"].startswith("regra")][0]
            rows.append({"beta": nome, "ano": ano, "obs_TWh": r["obs_TWh"], "sim_TWh": r["sim_TWh"], "erro_%": r["erro_%"],
                         "obs_horas": r["obs_horas"], "sim_horas": r["sim_horas"]})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ 3. substituição de formas
def formas_fora_do_ano(D: pd.DataFrame, Cl: pd.DataFrame, ano: int, t: pd.DatetimeIndex) -> pd.DataFrame:
    """Previsões das funções de transferência re-treinadas sem o ano `ano` (janelas do estudo; 2026 até out)."""
    c = Cl.reindex(t).join(calendar_features(pd.Series(t)).set_index(t))
    P = pd.DataFrame(index=t)
    for nome, s in sint.MODELOS.items():
        m = D.t.between(*s["treino"]) & (D.t.dt.year != ano) & D[s["alvo"]].notna() & D[s["ex"]].notna().all(axis=1)
        mdl = sint.HistGradientBoostingRegressor(**sint.HGB).fit(D.loc[m, s["ex"]], D.loc[m, s["alvo"]])
        ok = c[s["ex"]].notna().all(axis=1)
        p = np.full(len(t), np.nan)
        p[ok.to_numpy()] = mdl.predict(c.loc[ok, s["ex"]])
        P[nome] = p
    P["B0"], P["C0"], P["E0"] = P.B0.clip(0, 1), P.C0.clip(0, 1), P.E0.clip(lower=0)
    return P


def regra(O: pd.DataFrame, base: np.ndarray, b: float) -> np.ndarray:
    """Regra emulada com a energia diária e os limites mensais observados do próprio ano."""
    t = O.index
    lim = O.hid.groupby(t.month)
    o = types.SimpleNamespace(hid=O.hid.to_numpy()[None], hmin=lim.transform("min").to_numpy()[None],
                              hmax=lim.transform("max").to_numpy()[None], beta=np.array([b]))
    return mc.hidraulica(o, np.array([0]), -base[None], "regra_historica")[0]


def com_residuos(P: pd.DataFrame, O: pd.DataFrame, sel: np.ndarray, r: np.ndarray) -> dict:
    """Formas simuladas + resíduos sorteados (como no Monte Carlo), com os níveis observados do ano."""
    lv = lambda k: float(O[k][sel].mean())
    a = P.A0.to_numpy() / np.nanmean(P.A0.to_numpy()[sel]) + r[..., 0]
    e = np.clip(P.E0.to_numpy() / np.nanmean(P.E0.to_numpy()[sel]) + r[..., 1], 0, None)
    ce = np.clip(P.B0.to_numpy() + r[..., 2], 0, 1)
    cs = np.clip(P.C0.to_numpy() + r[..., 3], 0, 1)
    nv = lambda x, k: x / x[:, sel].mean(1, keepdims=True) * lv(k)
    return {"L": nv(a, "L_bal"), "MMGD": nv(e, "MMGD"), "eol": nv(ce, "eol_pot"), "sol": nv(cs, "sol_pot")}


def substituicao(obs: dict, Tb: pd.DataFrame, n_res: int = 100) -> tuple[pd.DataFrame, dict]:
    D = sint.dados_treino()
    pool = mc.Insumos()
    Cl = pd.read_parquet(PROCESSED / "clima_ne_1995_2026.parquet").set_index("t")
    rows, perfis = [], {}
    tb = Tb.set_index("ano")
    for ano, O in obs.items():
        t = O.index
        sel = O.valida.to_numpy()
        P = formas_fora_do_ano(D, Cl, ano, t)
        nivel = lambda forma, alvo: forma / np.nanmean(forma[sel]) * float(O[alvo][sel].mean())
        sim = {"L": nivel(P.A0.to_numpy(), "L_bal"), "MMGD": nivel(P.E0.to_numpy(), "MMGD"),
               "eol": nivel(P.B0.to_numpy(), "eol_pot"), "sol": nivel(P.C0.to_numpy(), "sol_pot")}
        ob = {"L": O.L_bal.to_numpy(), "MMGD": O.MMGD.to_numpy(), "eol": O.eol_pot.to_numpy(), "sol": O.sol_pot.to_numpy()}
        # horas inválidas (balanço que não fecha) ficam fora das métricas; nelas a parcela "observada"
        # recebe a simulada, para não contaminar a redistribuição diária da regra hidráulica
        ob = {k: np.where(sel, v, sim[k]) for k, v in ob.items()}
        ter = O.ter.to_numpy()
        imp = lambda M: float(np.clip(-M[sel], 0, None).sum() / 1e6)

        def M_de(comp: dict, hidro: str):
            base = ter + comp["eol"] + comp["sol"] + comp["MMGD"] - comp["L"]
            if hidro == "obs":
                h = O.hid.to_numpy()
            else:
                h = regra(O, base, float(tb.loc[ano, "beta_realizada" if hidro == "real" else "beta_potencial"]))
            return base + h, h

        casos = {
            "simulado, regra com beta anterior": (sim, "real"),
            "simulado, regra com beta adotado": (sim, "pot"),
            "simulado, despacho hidráulico observado": (sim, "obs"),
            "forma eólica observada (beta adotado)": ({**sim, "eol": ob["eol"]}, "pot"),
            "forma da carga observada (beta adotado)": ({**sim, "L": ob["L"]}, "pot"),
            "formas solar e MMGD observadas (beta adotado)": ({**sim, "sol": ob["sol"], "MMGD": ob["MMGD"]}, "pot"),
            "todas as formas observadas, regra com beta anterior": (ob, "real"),
            "todas as formas observadas, regra com beta adotado": (ob, "pot"),
            "todas as formas observadas, despacho observado": (ob, "obs"),
        }
        # resíduos fora da amostra sorteados em blocos de 7 dias a partir de 1º/jan (mesmo esquema do Monte Carlo)
        rins = types.SimpleNamespace(res=pool.res, dia_ok=pool.dia_ok, doy_pool=pool.doy_pool, nd=len(t) // 24,
                                     anos=np.array([ano]), anos_h=np.array([ano]))
        sdr = mc.sortear(rins, n_res, 7, mc.SEMENTE)
        rr = pool.res[sdr["dias"]].reshape(n_res, len(t), 4) - sdr["centro"]
        cr = com_residuos(P, O, sel, rr)
        casos_res = {}
        for hidro, rot in [("real", "simulado com resíduos, regra com beta anterior"),
                           ("pot", "simulado com resíduos, regra com beta adotado")]:
            b = float(tb.loc[ano, "beta_realizada" if hidro == "real" else "beta_potencial"])
            vals = []
            for j in range(n_res):
                base = ter + cr["eol"][j] + cr["sol"][j] + cr["MMGD"][j] - cr["L"][j]
                vals.append(imp(base + regra(O, base, b)))
            casos_res[rot] = float(np.mean(vals))
        obs_imp = imp(O.M.to_numpy())
        r = {"ano": ano, "horas_validas": int(sel.sum()), "observado_TWh": obs_imp,
             "importacao_intercambio_TWh": float(np.clip(-O.interc.to_numpy()[sel], 0, None).sum() / 1e6)}
        hs = {}
        for nome, (comp, hidro) in casos.items():
            M, h = M_de(comp, hidro)
            r[nome] = imp(M)
            hs[nome] = h
        r.update(casos_res)
        # cauda de pouco vento: P5 horário da eólica (mesmo nível médio)
        r["eolica_p5_observada_MW"] = float(np.percentile(ob["eol"][sel], 5))
        r["eolica_p5_simulada_MW"] = float(np.percentile(sim["eol"][sel], 5))
        r["eolica_p5_simulada_com_residuos_MW"] = float(np.mean([np.percentile(cr["eol"][j][sel], 5) for j in range(n_res)]))
        # quanto a eólica simulada erra nas horas de pouco vento observado (quintil inferior)
        q = O.eol_pot[sel] <= O.eol_pot[sel].quantile(0.2)
        r["erro_eolica_quintil_inferior_MW"] = float((sim["eol"][sel] - ob["eol"][sel])[q.to_numpy()].mean())
        r["dp_eolica_simulada_MW"] = float(np.std(sim["eol"][sel]))
        r["dp_eolica_observada_MW"] = float(np.std(ob["eol"][sel]))
        rows.append(r)
        perfis[ano] = pd.DataFrame({"hora": t.hour, "mes": t.month, "valida": sel, "obs": O.hid.to_numpy(),
                                    "real": hs["todas as formas observadas, regra com beta anterior"],
                                    "pot": hs["todas as formas observadas, regra com beta adotado"]}, index=t)
    return pd.DataFrame(rows), perfis


# ------------------------------------------------------------------ 4. efeito em 2030
def efeito_2030(c: dict, d: dict, Tb: pd.DataFrame, n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    ins = InsumosAno(2030)
    sd = mc.sortear(ins, n, 7, mc.SEMENTE)
    ldc = {k: l_dc_2030(k, d)[0] for k in ["sem_dc", "central"]}
    tb = Tb.set_index("ano").loc[[int(a) for a in ins.anos_h]]
    rows, perf = [], []
    for nome, b in [("beta anterior (carga líquida realizada)", tb.beta_realizada.to_numpy()),
                    ("beta adotado (carga líquida potencial)", tb.beta_potencial.to_numpy())]:
        ins.beta = b
        for w in ["baixa", "base", "alta"]:
            Dk = simular_ano(ins, c, ldc, sd, ws=[w])
            a1 = Dk[Dk.cenario_dc == "central"].importacao_TWh.to_numpy()
            a0 = Dk[Dk.cenario_dc == "sem_dc"].importacao_TWh.to_numpy()
            rows.append({"beta": nome, "cenario_eolico": w, "central_media_TWh": a1.mean(), "central_p5_TWh": np.percentile(a1, 5),
                         "central_p95_TWh": np.percentile(a1, 95), "sem_dc_media_TWh": a0.mean(),
                         "efeito_DC_TWh": (a1 - a0).mean(), "efeito_DC_p5": np.percentile(a1 - a0, 5),
                         "efeito_DC_p95": np.percentile(a1 - a0, 95),
                         "horas_central": Dk[Dk.cenario_dc == "central"].horas_importacao.mean()})
        # perfil horário médio da hidráulica emulada (300 sorteios, eólica base)
        idx = np.arange(min(300, n))
        base, cfe, _, h = mc.series(ins, sd, idx, c)
        cap = c["eolica"]["capacidade_2030_MW"]["base"]["valor"]
        hid = mc.hidraulica(ins, h, -(base + cfe * cap), "regra_historica")
        hora = np.tile(np.arange(24), 365)
        mes = pd.date_range("2030-01-01", "2030-12-31 23:00", freq="h").month.to_numpy()
        for grupo, mm in [("jan–abr", mes <= 4), ("mai–dez", mes >= 5)]:
            perf.append(pd.DataFrame({"conjunto": "2030", "serie": "real" if nome.startswith("beta anterior") else "pot",
                                      "meses": grupo, "hora": range(24),
                                      "MW": [hid[:, mm & (hora == k)].mean() for k in range(24)]}))
            if nome.startswith("beta anterior"):
                perf.append(pd.DataFrame({"conjunto": "2030", "serie": "obs", "meses": grupo, "hora": range(24),
                                          "MW": [ins.hid[h][:, mm & (hora == k)].mean() for k in range(24)]}))
    return pd.DataFrame(rows), pd.concat(perf, ignore_index=True)


# ------------------------------------------------------------------ figuras
def estilo(ax, titulo, ylab=None):
    ax.set_title(titulo, loc="left", fontsize=9.5)
    if ylab:
        ax.set_ylabel(ylab, fontsize=8.5, color=INK2)
    ax.grid(color=GRID, lw=0.8); ax.set_axisbelow(True)
    [ax.spines[k].set_visible(False) for k in ["top", "right"]]
    ax.tick_params(labelsize=8, colors=INK2)


def figura_perfil(PF: pd.DataFrame) -> None:
    rot = {"obs": "despacho observado", "real": "regra emulada, beta anterior (carga já cortada)",
           "pot": "regra emulada, beta adotado (carga potencial)"}
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 6.4), sharex=True)
    for j, conj in enumerate(["2030", "2026"]):
        for i, meses in enumerate(["jan–abr", "mai–dez" if conj == "2030" else "mai–out"]):
            ax = axes[i, j]
            g = PF[(PF.conjunto == conj) & (PF.meses == meses)]
            for s in ["obs", "real", "pot"]:
                gg = g[g.serie == s].sort_values("hora")
                ax.plot(gg.hora, gg.MW / 1000, color=COR[s], lw=2, label=rot[s])
            tit = (f"2030, Monte Carlo (300 sorteios, eólica base): {meses}" if conj == "2030"
                   else f"2026 observado (backtest, parcelas observadas): {meses}")
            estilo(ax, tit, "hidráulica (GW, média por hora)" if j == 0 else None)
            ax.set_xticks(range(0, 24, 3))
    for ax in axes[1]:
        ax.set_xlabel("hora do dia", fontsize=8.5, color=INK2)
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.suptitle("Perfil horário da hidráulica emulada: mesma energia diária, redistribuída conforme a carga líquida",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); fig.savefig(FIGURES / "r15b_perfil_horario_hidraulica.png", dpi=130); plt.close(fig)


def figura_diagnostico(Tb: pd.DataFrame, SB: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2))
    ax = axes[0]
    x = np.arange(len(Tb))
    ax.bar(x - 0.18, Tb.beta_realizada, width=0.34, color=COR["real"], label="anterior: sobre carga líquida realizada")
    ax.bar(x + 0.18, Tb.beta_potencial, width=0.34, color=COR["pot"], label="adotado: sobre carga líquida potencial")
    for k, r in enumerate(Tb.itertuples()):
        ax.text(k, max(r.beta_realizada, r.beta_potencial) + 0.015, f"corte {r._6:.0f}%".replace(".", ","),
                ha="center", fontsize=7.5, color=INK2)
    ax.set_xticks(x, [str(a) for a in Tb.ano])
    estilo(ax, "Coeficiente beta da regra hidráulica por ano (e corte eólico)")
    ax.legend(frameon=False, fontsize=7.5, loc="lower left")
    ax = axes[1]
    casos = [("simulado com resíduos, regra com beta anterior", COR["real"], "método anterior (com resíduos, beta anterior)"),
             ("simulado com resíduos, regra com beta adotado", COR["pot"], "método atual (com resíduos, beta adotado)"),
             ("forma eólica observada (beta adotado)", "#1baf7a", "forma eólica observada, beta adotado*"),
             ("todas as formas observadas, regra com beta adotado", "#6250d6", "todas as formas observadas, beta adotado*")]
    x = np.arange(len(SB))
    for k, (col, cor, rot) in enumerate(casos):
        err = 100 * (SB[col] / SB.observado_TWh - 1)
        ax.plot(x, err, color=cor, lw=2, marker="o", ms=5, label=rot)
    ax.axhline(0, color="#c3c2b7", lw=1)
    ax.set_xticks(x, [str(a) for a in SB.ano])
    estilo(ax, "Erro da importação com os níveis observados de cada ano (%; * sem resíduos)", "%")
    ax.legend(frameon=False, fontsize=7.5)
    fig.tight_layout(); fig.savefig(FIGURES / "r27_diagnostico_importacao.png", dpi=130); plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--n-backcast", type=int, default=300)
    a = ap.parse_args(argv)
    c, d = load_cfg()
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    obs = {ano: observado_ano(X, ano) for ano in ANOS}

    Tb = tabela_beta(obs, X)
    Tb.round(4).to_csv(OUT / "diag_beta_hidro.csv", index=False)
    print(Tb.round(3).to_string())

    BK = backcast_beta(c, Tb, a.n_backcast)
    BK.round(3).to_csv(OUT / "diag_backcast_beta.csv", index=False)
    print(BK.round(2).to_string())

    SB, perfis = substituicao(obs, Tb)
    SB.round(4).to_csv(OUT / "diag_substituicao.csv", index=False)
    print(SB.round(2).T.to_string())

    E30, PF30 = efeito_2030(c, d, Tb, a.n)
    E30.round(4).to_csv(OUT / "diag_2030_beta.csv", index=False)
    print(E30.round(2).to_string())

    p26 = perfis[2026]
    p26 = p26[p26.valida]
    PF = [PF30]
    for meses, mm in [("jan–abr", p26.mes <= 4), ("mai–out", p26.mes >= 5)]:
        for s in ["obs", "real", "pot"]:
            PF.append(pd.DataFrame({"conjunto": "2026", "serie": s, "meses": meses, "hora": range(24),
                                    "MW": p26[mm].groupby("hora")[s].mean().reindex(range(24)).to_numpy()}))
    PF = pd.concat(PF, ignore_index=True)
    PF.round(1).to_csv(OUT / "diag_perfil_hidro.csv", index=False)
    figura_perfil(PF)
    figura_diagnostico(Tb, SB)


if __name__ == "__main__":
    main()
