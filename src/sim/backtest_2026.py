"""Backtest de 2026: o simulador com os níveis de cenário de 2026 contra o balanço observado (jan–out).

Uso: python -m src.sim.backtest_2026
Pré-requisitos: src.sim.anos (perfis e Monte Carlo por ano) e src.sim.trajetorias.
Saídas: reports/sim/backtest_2026*.csv, data/processed/backtest_2026_horario.parquet,
reports/figures/b26_backtest_2026.png.

Período: 2026-01-01 a 2026-10-31 (meses completos; novembro é preliminar, decisão 11), só nas
horas em que o balanço do ONS fecha (as 878 horas anômalas de jan–mai/2026 ficam fora, decisão 16).
Cenário: níveis de 2026 de config/cenarios_anuais.yaml com DC central (a carga global do PLAN de
2026 inclui os DC da 2ª RQ) e eólica base (em 2026 os três cenários eólicos coincidem).

Observado (ONS):
- M realizado = intercâmbio (> 0 exportação); importação realizada = max(0, −intercâmbio);
- M potencial = intercâmbio + corte eólico e solar (GNRa das usinas com FC levada à frota
  inteira, como em src/sim/backcast.py). É o conceito do simulador, que usa geração potencial.

Simulado:
- (A) ex-ante: os 2.000 sorteios do Monte Carlo de 2026 (clima 1995–2025, hidrologia 2022–2025);
  pergunta: o ano observado cai dentro da faixa simulada?
- (B) clima e hidrologia de 2026 conhecidos: funções de transferência re-treinadas só com dados
  até 2025-12-31 (fora da amostra) aplicadas ao ERA5 de 2026; térmica observada; hidráulica pela
  regra emulada com a energia diária observada de 2026 e o coeficiente sobre a carga líquida
  potencial (decisão 52); como comparação, o coeficiente anterior e o despacho observado.
  Os níveis continuam sendo os do cenário (PLAN, SIGA): o erro de B mistura o erro de nível do
  cenário com o das formas horárias. O ERA5 é reanálise (clima perfeito): limite superior.
"""
from __future__ import annotations

import types

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.features.build import calendar_features
from src.paths import FIGURES, PROCESSED, REPORTS
from src.sim import montecarlo as mc
from src.sim import sinteticos as sint
from src.sim.anos import InsumosAno, calendario, niveis_dc, simular_ano
from src.sim.deterministico import load_cfg
from src.sim.trajetorias import calcular, config_ano, load_cfg_anual

OUT = REPORTS / "sim"
ANO = 2026
FIM_TREINO = "2025-12-31 23:00"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def observado(cfa: dict) -> pd.DataFrame:
    """Série horária observada de 2026 (jan–out) no calendário completo do período, com máscara de validade."""
    p0, p1 = cfa["backtest_2026"]["periodo"]
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    g = X[X.t.between(p0, p1)].set_index("t")
    t = pd.date_range(p0, p1, freq="h")
    g = g.reindex(t)
    req = ["interc", "hid", "ter", "eol_bal", "sol_central", "ger_eol_fc", "pot_eol_fc", "ger_sol_fc", "pot_sol_fc",
           "L_gross", "MMGD"]
    ok = g[req].notna().all(axis=1)
    if cfa["backtest_2026"]["excluir_horas_anomalas"]:
        ok &= g.anomalia_balanco.fillna(1) == 0
    v = g[ok]
    fr_e = v.eol_bal.mean() / v.ger_eol_fc.mean()        # frota inteira / usinas com FC
    fr_s = v.sol_central.mean() / v.ger_sol_fc.mean()
    O = pd.DataFrame(index=t)
    O["valida"] = ok
    O["corte"] = (g.pot_eol_fc - g.ger_eol_fc) * fr_e + (g.pot_sol_fc - g.ger_sol_fc) * fr_s
    O["M_real"] = g.interc
    O["M_pot"] = g.interc + O.corte
    O["L_gross"], O["MMGD"], O["hid"], O["ter"] = g.L_gross, g.MMGD, g.hid, g.ter
    O["eol_pot"], O["sol_pot"] = g.pot_eol_fc * fr_e, g.pot_sol_fc * fr_s
    O["eol_real"], O["sol_real"] = g.eol_bal, g.sol_central
    O.attrs.update(fr_e=fr_e, fr_s=fr_s)
    return O


def perfis_clima_2026(t: pd.DatetimeIndex) -> pd.DataFrame:
    """Funções de transferência treinadas até 2025-12-31 aplicadas ao ERA5 de 2026 (sem resíduo)."""
    D = sint.dados_treino()
    Cl = pd.read_parquet(PROCESSED / "clima_ne_1995_2026.parquet").set_index("t")
    c = Cl.reindex(t)
    assert c.notna().all().all(), "ERA5 de 2026 incompleto no período do backtest"
    c = c.join(calendar_features(pd.Series(t)).set_index(t))
    P = pd.DataFrame(index=t)
    treino = {}
    for nome, s in sint.MODELOS.items():
        ini = s["treino"][0]
        m = D.t.between(ini, FIM_TREINO) & D[s["alvo"]].notna() & D[s["ex"]].notna().all(axis=1)
        mdl = sint.HistGradientBoostingRegressor(**sint.HGB).fit(D.loc[m, s["ex"]], D.loc[m, s["alvo"]])
        P[nome] = mdl.predict(c[s["ex"]])
        treino[nome] = f"{ini[:10]}..{FIM_TREINO[:10]}"
    P["B0"], P["C0"] = P.B0.clip(0, 1), P.C0.clip(0, 1)
    P["E0"] = P.E0.clip(lower=0)
    P.attrs["treino"] = treino
    return P


def beta_hidro(O: pd.DataFrame, potencial: bool = True) -> float:
    """Coeficiente da regra emulada em 2026, pela mesma função do Monte Carlo (mc.beta_regra), nas
    horas válidas do período. Caso central: carga líquida potencial (decisão 52); `potencial=False`
    dá o coeficiente anterior (carga líquida realizada, já cortada)."""
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    g = X.set_index("t").reindex(O.index)[O.valida.to_numpy()]
    return mc.beta_regra(g, potencial=potencial)


def metricas(M: np.ndarray, sel: np.ndarray) -> dict:
    """Métricas de um conjunto de séries (n × horas) restritas às horas `sel`."""
    M = np.atleast_2d(M)[:, sel]
    imp = np.clip(-M, 0, None)
    return {"importacao_TWh": imp.sum(1) / 1e6, "horas_importacao": (M < 0).sum(1),
            "importacao_p95_MW": np.percentile(imp, 95, axis=1), "importacao_pico_MW": imp.max(1),
            "excedente_TWh": np.clip(M, 0, None).sum(1) / 1e6, "M_medio_MW": M.mean(1)}


def main() -> None:
    cfa = load_cfg_anual()
    bt = cfa["backtest_2026"]
    c, _ = load_cfg()
    T = calcular()
    cy = config_ano(c, T, ANO)
    ldc = niveis_dc(T, ANO)[bt["cenario_dc"]]
    cap_e = cy["eolica"]["capacidade_2030_MW"][bt["cenario_eolico"]]["valor"]
    cap_s = cy["solar"]["capacidade_2030_MW"]["valor"]
    Lbar = cy["carga"]["L_gross_sem_dc_MWmed"]["valor"]
    Mbar = cy["mmgd"]["media_2030_MWmed"]["valor"]

    O = observado(cfa)
    t = O.index
    nh = len(t)
    sel = O.valida.to_numpy()
    mes = t.month.to_numpy()

    # ---------------- (A) ex-ante: Monte Carlo de 2026 restrito às horas válidas de jan–out
    ins = InsumosAno(ANO)
    n = cfa["simulador"]["n_sorteios_mc"]
    sd = mc.sortear(ins, n, 7, mc.SEMENTE)
    cal = calendario(ANO)
    mascara = np.isin(cal, t[sel])
    DA, MA = simular_ano(ins, cy, {bt["cenario_dc"]: ldc}, sd, ws=[bt["cenario_eolico"]], mascara=mascara, mensal=True)

    # ---------------- (B) clima e hidrologia observados de 2026
    P = perfis_clima_2026(t)
    S = pd.read_parquet(PROCESSED / "sinteticos_anos.parquet")
    S = S[S.ano_alvo == ANO]
    jan_out = S.t.isin(t)
    kA = float(S[jan_out].A0.mean())                       # média jan–out da forma anual (média 1), 31 anos
    E = pd.read_parquet(PROCESSED / "sinteticos_2030.parquet")
    kE = float(E[E.t.dt.month <= t[-1].month].E0.mean())
    beta = beta_hidro(O, potencial=True)            # caso central (decisão 52)
    beta_ant = beta_hidro(O, potencial=False)       # coeficiente anterior (carga já cortada)
    hid_obs = O.hid.to_numpy()
    lim = O.hid.groupby(t.month)
    hmin = lim.transform("min").to_numpy()
    hmax = lim.transform("max").to_numpy()
    obj = types.SimpleNamespace(hid=hid_obs[None, :], hmin=hmin[None, :], hmax=hmax[None, :], beta=np.array([beta]))

    # resíduos fora da amostra sorteados em blocos, como no Monte Carlo (só jan–out)
    base_ins = mc.Insumos()
    rins = types.SimpleNamespace(res=base_ins.res, dia_ok=base_ins.dia_ok, doy_pool=base_ins.doy_pool,
                                 nd=nh // 24, anos=np.array([ANO]), anos_h=np.array([ANO]))
    nr = bt["n_sorteios_residuos"]
    sdr = mc.sortear(rins, nr, 7, mc.SEMENTE)
    rs = base_ins.res[sdr["dias"]].reshape(nr, nh, 4) - sdr["centro"]

    def simular_B(r: np.ndarray | None, modo: str, b: float = beta) -> tuple[np.ndarray, dict]:
        k = 1 if r is None else len(r)
        r = np.zeros((k, nh, 4)) if r is None else r
        A0 = P.A0.to_numpy() / P.A0.mean() * kA + r[..., 0]
        A0 = A0 / A0.mean(1, keepdims=True) * kA
        E0 = np.clip(P.E0.to_numpy() / P.E0.mean() * kE + r[..., 1], 0, None)
        E0 = E0 / E0.mean(1, keepdims=True) * kE
        cfe = np.clip(P.B0.to_numpy() + r[..., 2], 0, 1)
        cfs = np.clip(P.C0.to_numpy() + r[..., 3], 0, 1)
        L, MM = A0 * Lbar, E0 * Mbar
        base = O.ter.to_numpy() + cfs * cap_s + cfe * cap_e - (L - MM)
        h = np.zeros(k, dtype=int)
        o = types.SimpleNamespace(hid=np.repeat(obj.hid, k, 0), hmin=np.repeat(obj.hmin, k, 0),
                                  hmax=np.repeat(obj.hmax, k, 0), beta=np.full(k, b))
        hid = mc.hidraulica(o, np.arange(k), -base, modo)
        M = base + hid - ldc
        comp = {"L_gross": L + ldc, "MMGD": MM, "eol_pot": cfe * cap_e, "sol_pot": cfs * cap_s, "hid": hid,
                "ter": np.repeat(O.ter.to_numpy()[None, :], k, 0)}
        return M, comp

    MB0, compB = simular_B(None, "regra_historica")              # série pontual (sem resíduo)
    MBh0, _ = simular_B(None, "historico_sorteado")
    MBr, _ = simular_B(rs, "regra_historica")                    # com resíduos (distribuição)
    MBhr, _ = simular_B(rs, "historico_sorteado")
    MBa0, compBa = simular_B(None, "regra_historica", beta_ant)   # coeficiente anterior
    MBar, _ = simular_B(rs, "regra_historica", beta_ant)

    # ---------------- tabela principal
    mo_r = metricas(O.M_real.to_numpy(), sel)
    mo_p = metricas(O.M_pot.to_numpy(), sel)
    mb = metricas(MBr, sel)
    mbh = metricas(MBhr, sel)
    mb0 = metricas(MB0, sel)
    mba = metricas(MBar, sel)
    rows = []
    for m in ["importacao_TWh", "horas_importacao", "importacao_p95_MW", "importacao_pico_MW", "excedente_TWh", "M_medio_MW"]:
        a = DA[m].to_numpy() if m in DA else None
        r = {"metrica": m, "observado_realizado": float(mo_r[m][0]), "observado_potencial": float(mo_p[m][0]),
             "B_regra_sem_residuo": float(mb0[m][0]),
             "B_regra_media": float(mb[m].mean()), "B_regra_p5": float(np.percentile(mb[m], 5)),
             "B_regra_p95": float(np.percentile(mb[m], 95)),
             "B_despacho_obs_media": float(mbh[m].mean()),
             "B_regra_beta_anterior_media": float(mba[m].mean()), "B_regra_beta_anterior_p5": float(np.percentile(mba[m], 5)),
             "B_regra_beta_anterior_p95": float(np.percentile(mba[m], 95))}
        if a is not None:
            r.update({"A_p5": float(np.percentile(a, 5)), "A_p50": float(np.percentile(a, 50)),
                      "A_p95": float(np.percentile(a, 95)), "A_media": float(a.mean()),
                      "A_percentil_do_observado_potencial": float(100 * (a < mo_p[m][0]).mean()),
                      "A_percentil_do_observado_realizado": float(100 * (a < mo_r[m][0]).mean())})
        elif m == "M_medio_MW":
            pass
        rows.append(r)
    TB = pd.DataFrame(rows)

    # erro horário de B (sem resíduo) contra o M potencial observado
    e = (MB0[0] - O.M_pot.to_numpy())[sel]
    erro = {"bias_MW": float(e.mean()), "MAE_MW": float(np.abs(e).mean()), "RMSE_MW": float(np.sqrt((e ** 2).mean())),
            "corr": float(np.corrcoef(MB0[0][sel], O.M_pot.to_numpy()[sel])[0, 1]),
            "acerto_sinal_%": float(100 * ((MB0[0][sel] < 0) == (O.M_pot.to_numpy()[sel] < 0)).mean())}

    # níveis médios das parcelas (horas válidas): de onde vem o erro de nível
    comp_rows = []
    for k_, nome in [("L_gross", "carga bruta (com DC)"), ("MMGD", "MMGD"), ("eol_pot", "eólica potencial"),
                     ("sol_pot", "solar potencial"), ("hid", "hidráulica"), ("ter", "térmica")]:
        comp_rows.append({"parcela": nome, "observado_MWmed": float(O[k_][sel].mean()),
                          "simulado_B_MWmed": float(compB[k_][0][sel].mean())})
    TC = pd.DataFrame(comp_rows)
    TC["diferenca_MWmed"] = TC.simulado_B_MWmed - TC.observado_MWmed
    sinal = {"carga bruta (com DC)": -1, "MMGD": 1, "eólica potencial": 1, "solar potencial": 1, "hidráulica": 1, "térmica": 1}
    TC["efeito_em_M_MWmed"] = TC.diferenca_MWmed * TC.parcela.map(sinal)
    # o M observado vem do intercâmbio (balanço do ONS); as parcelas de carga vêm da API de carga.
    # A diferença entre os dois conceitos de carga (decisão 41) fecha a decomposição do viés.
    o = {k_: float(O[k_][sel].mean()) for k_ in ["hid", "ter", "eol_pot", "sol_pot", "MMGD", "L_gross"]}
    gap = float(O.M_pot[sel].mean()) - (o["hid"] + o["ter"] + o["eol_pot"] + o["sol_pot"] + o["MMGD"] - o["L_gross"])
    TC.loc[len(TC)] = {"parcela": "carga: balanço do ONS × API (decisão 41)", "efeito_em_M_MWmed": -gap}
    TC.loc[len(TC)] = {"parcela": "total = viés médio de M (B − observado)",
                       "efeito_em_M_MWmed": float(MB0[0][sel].mean() - O.M_pot[sel].mean())}
    assert abs(TC.efeito_em_M_MWmed.iloc[:-1].sum() - TC.efeito_em_M_MWmed.iloc[-1]) < 1e-6

    # mensal
    mrows = []
    for m in sorted(set(mes)):
        s = sel & (mes == m)
        if not s.any():
            continue
        a = MA[MA.mes == m]
        mrows.append({"mes": m, "horas_validas": int(s.sum()),
                      "obs_real_importacao_TWh": float(np.clip(-O.M_real.to_numpy()[s], 0, None).sum() / 1e6),
                      "obs_pot_importacao_TWh": float(np.clip(-O.M_pot.to_numpy()[s], 0, None).sum() / 1e6),
                      "B_importacao_TWh": float((np.clip(-MBr[:, s], 0, None).sum(1) / 1e6).mean()),
                      "A_importacao_p5_TWh": float(np.percentile(a.importacao_TWh, 5)),
                      "A_importacao_p50_TWh": float(np.percentile(a.importacao_TWh, 50)),
                      "A_importacao_p95_TWh": float(np.percentile(a.importacao_TWh, 95)),
                      "obs_pot_excedente_TWh": float(np.clip(O.M_pot.to_numpy()[s], 0, None).sum() / 1e6),
                      "obs_real_exportacao_TWh": float(np.clip(O.M_real.to_numpy()[s], 0, None).sum() / 1e6),
                      "B_excedente_TWh": float((np.clip(MBr[:, s], 0, None).sum(1) / 1e6).mean()),
                      "A_excedente_p5_TWh": float(np.percentile(a.excedente_TWh, 5)),
                      "A_excedente_p50_TWh": float(np.percentile(a.excedente_TWh, 50)),
                      "A_excedente_p95_TWh": float(np.percentile(a.excedente_TWh, 95))})
    TM = pd.DataFrame(mrows)

    OUT.mkdir(parents=True, exist_ok=True)
    TB.round(4).to_csv(OUT / "backtest_2026.csv", index=False)
    TM.round(4).to_csv(OUT / "backtest_2026_mensal.csv", index=False)
    TC.round(1).to_csv(OUT / "backtest_2026_componentes.csv", index=False)
    info = {"periodo": bt["periodo"], "horas_periodo": int(nh), "horas_validas": int(sel.sum()),
            "cenario_dc": bt["cenario_dc"], "L_DC_MWmed": ldc, "cenario_eolico": bt["cenario_eolico"],
            "cap_eol_MW": cap_e, "cap_sol_MW": cap_s, "L_gross_sem_dc_MWmed": Lbar, "MMGD_MWmed": Mbar,
            "beta_hidro_2026": beta, "beta_hidro_2026_anterior_realizada": beta_ant, "fr_eol": O.attrs["fr_e"], "fr_sol": O.attrs["fr_s"],
            "kA_jan_out": kA, "kE_jan_out": kE, "treino_B": P.attrs["treino"], "n_sorteios_A": n,
            "n_residuos_B": nr, "erro_horario_B": erro}
    pd.Series(info, dtype=object).to_json(OUT / "backtest_2026_config.json", force_ascii=False, indent=1)
    H = pd.DataFrame({"t": t, "valida": sel, "M_obs_real": O.M_real, "M_obs_pot": O.M_pot, "corte": O.corte,
                      "M_B": MB0[0], "M_B_despacho_obs": MBh0[0], "M_B_beta_anterior": MBa0[0], "B_hid_beta_anterior": compBa["hid"][0],
                      **{f"obs_{k_}": O[k_].to_numpy() for k_ in ["L_gross", "MMGD", "eol_pot", "sol_pot", "hid", "ter"]},
                      **{f"B_{k_}": v[0] for k_, v in compB.items()}})
    H.to_parquet(PROCESSED / "backtest_2026_horario.parquet")
    figura(TM)
    print(TB.round(2).to_string())
    print(TC.round(0).to_string())
    print(TM.round(3).to_string())
    print(erro, {k_: round(v, 3) for k_, v in info.items() if isinstance(v, float)})


def figura(TM: pd.DataFrame) -> None:
    x = np.arange(len(TM))
    lab = [MESES[m - 1] for m in TM.mes]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    for ax, (pre, tit) in zip(axes, [("importacao", "Importação por mês (TWh, horas válidas)"),
                                     ("excedente", "Excedente potencial por mês (TWh, horas válidas)")]):
        ax.fill_between(x, TM[f"A_{pre}_p5_TWh"], TM[f"A_{pre}_p95_TWh"], color="#8fbcef", alpha=0.5,
                        label="A: cenário 2026, clima sorteado (P5–P95)", lw=0)
        ax.plot(x, TM[f"A_{pre}_p50_TWh"], color="#2a78d6", lw=1, ls="--", label="A: mediana")
        ax.plot(x, TM[f"B_{pre}_TWh"], color="#eb6834", lw=2, marker="o", ms=4, label="B: clima e hidrologia de 2026")
        ax.plot(x, TM[f"obs_pot_{pre}_TWh"], color="#0b0b0b", lw=2, marker="s", ms=4, label="observado (potencial)")
        if pre == "importacao":
            ax.plot(x, TM.obs_real_importacao_TWh, color="#52514e", lw=1, ls=":", marker=".", label="observado (intercâmbio)")
        ax.set_xticks(x, lab)
        ax.set_title(tit, loc="left", fontsize=10)
        ax.grid(axis="y", color="#e4e3df"); ax.set_axisbelow(True)
        [ax.spines[k].set_visible(False) for k in ["top", "right"]]
    axes[0].legend(frameon=False, fontsize=7.5)
    fig.suptitle("Backtest de 2026 (jan–out): simulador com os níveis de cenário de 2026 × balanço observado do ONS",
                 x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); fig.savefig(FIGURES / "b26_backtest_2026.png", dpi=130); plt.close(fig)


if __name__ == "__main__":
    main()
