"""Figuras didáticas do relatório técnico (caracterização, modelos, simulador e Monte Carlo).

Uso: python -m src.report.figuras_didaticas
Pré-requisitos: pipeline até src.sim.montecarlo. Saídas: reports/figures/r*.png e as tabelas
reports/tables/didatico_*.csv com os números citados no relatório técnico.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.inspection import permutation_importance

from src.paths import CONFIG, FIGURES, INTERIM, PROCESSED, REPORTS, TABLES

# paleta de referência (skill dataviz), cor fixa por entidade
COR = {"hid": "#2a78d6", "ter": "#eb6834", "eol": "#1baf7a", "sol": "#eda100", "mmgd": "#e87ba4",
       "carga": "#0b0b0b", "dc": "#6250d6", "imp": "#e34948", "cinza": "#8a8984"}
SEQ = {"sem_dc": "#8a8984", "conservador": "#8fbcef", "central": "#2a78d6", "alto": "#0d3f80"}
INK2, GRID = "#52514e", "#e4e3df"
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def estilo(ax, titulo, ylabel="", xlabel=""):
    ax.set_title(titulo, loc="left", fontsize=10)
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.set_xlabel(xlabel, color=INK2, fontsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8)


def salvar(fig, nome):
    fig.tight_layout()
    fig.savefig(FIGURES / nome, dpi=130, facecolor="white")
    plt.close(fig)


def feats():
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    return X[X.t < "2026-11-01"].copy()


# ------------------------------------------------------------------ etapa 1: dados
def r01_cobertura():
    cov = pd.read_csv(TABLES / "cobertura.csv", parse_dates=["inicio", "fim"])
    linhas = [(r.bloco, r.inicio, r.fim, "ONS") for r in cov.itertuples() if "clima" not in r.bloco]
    linhas.append(("clima ERA5, 34 pontos (série desde 1995)", pd.Timestamp("1995-01-01"), pd.Timestamp("2026-11-03"), "ERA5"))
    fig, ax = plt.subplots(figsize=(11, 4.4))
    x0 = pd.Timestamp("2021-07-01")
    ax.axvspan(pd.Timestamp("2022-01-01"), pd.Timestamp("2026-01-01"), color=GRID, alpha=0.6, lw=0, zorder=0)
    ax.text(pd.Timestamp("2022-01-20"), len(linhas) - 0.35, "período de calibração 2022–2025", fontsize=8, color=INK2)
    for i, (nome, ini, fim, fonte) in enumerate(linhas):
        ax.barh(i, (fim - max(ini, x0)).days, left=max(ini, x0), height=0.5, zorder=2,
                color=COR["hid"] if fonte == "ONS" else COR["eol"])
        ax.text(fim + pd.Timedelta(days=20), i, nome, fontsize=8, va="center", color="#0b0b0b")
    ax.set_yticks([]); ax.set_xlim(x0, pd.Timestamp("2029-06-01"))
    ax.set_xticks([pd.Timestamp(f"{a}-01-01") for a in range(2022, 2028)], [str(a) for a in range(2022, 2028)])
    estilo(ax, "Cobertura das séries horárias usadas (azul: ONS; verde: reanálise ERA5)")
    ax.grid(axis="x", color=GRID)
    salvar(fig, "r01_cobertura_dados.png")


def r02_mapa():
    fc = pd.read_parquet(INTERIM / "ne_fc_usina_h.parquet")
    fc = fc[(fc.t >= "2026-10-01") & (fc.t < "2026-11-01")]
    u = fc.groupby(["id_ons", "fonte"]).agg(lat=("val_latitudesecoletora", "first"), lon=("val_longitudesecoletora", "first"),
                                            cap=("val_capacidadeinstalada", "mean")).reset_index().dropna()
    pts = pd.read_csv(CONFIG / "weather_points.csv")
    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    for fonte, cor, nome in [("EOL", COR["eol"], "eólica (usina/conjunto)"), ("SOL", COR["sol"], "solar (usina/conjunto)")]:
        g = u[u.fonte == fonte]
        ax.scatter(g.lon, g.lat, s=g.cap / 6, color=cor, alpha=0.55, edgecolor="white", lw=0.5, label=f"{nome}, área ∝ MW")
    for kind, mk, cor, nome in [("wind", "^", "#0b0b0b", "ponto ERA5 eólico"), ("solar", "s", "#7a5b00", "ponto ERA5 solar"),
                                ("capital", "o", COR["hid"], "capital (temperatura)")]:
        g = pts[pts.kind == kind]
        ax.scatter(g.lon, g.lat, marker=mk, s=40, facecolor="none" if kind != "capital" else cor, edgecolor=cor, lw=1.2, label=nome)
    for r in pts[pts.kind == "capital"].itertuples():
        ax.text(r.lon + 0.15, r.lat + 0.12, f"{r.name} ({r.uf})", fontsize=7.5, color=INK2)
    ax.set_aspect("equal"); ax.set_xlabel("longitude", fontsize=9, color=INK2); ax.set_ylabel("latitude", fontsize=9, color=INK2)
    estilo(ax, "Usinas eólicas e solares despachadas pelo ONS no subsistema NE (out/2026) e pontos ERA5", "latitude", "longitude")
    ax.grid(color=GRID); ax.legend(frameon=False, fontsize=7.5, loc="lower left", markerscale=0.6)
    salvar(fig, "r02_mapa_usinas_pontos.png")
    return u.groupby("fonte").cap.agg(["size", "sum"])


def r03_capacidade(X, c):
    m = X.set_index("t")[["cap_eol", "cap_sol"]].resample("ME").mean() / 1000
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(m.index, m.cap_eol, color=COR["eol"], lw=2, label="eólica (FC ONS)")
    ax.plot(m.index, m.cap_sol, color=COR["sol"], lw=2, label="solar centralizada (FC ONS)")
    x30 = pd.Timestamp("2030-07-01")
    for nome, v in c["eolica"]["capacidade_2030_MW"].items():
        ax.scatter(x30, v["valor"] / 1000, color=COR["eol"], s=40, zorder=3)
        ax.text(x30 + pd.Timedelta(days=60), v["valor"] / 1000, f"eólica {nome}: {v['valor']/1000:.1f} GW".replace(".", ","), fontsize=8, va="center")
    ax.scatter(x30, c["solar"]["capacidade_2030_MW"]["valor"] / 1000, color=COR["sol"], s=40, zorder=3)
    ax.text(x30 + pd.Timedelta(days=60), c["solar"]["capacidade_2030_MW"]["valor"] / 1000, "solar 2030: 13,5 GW", fontsize=8, va="center")
    ax.axvline(pd.Timestamp("2026-11-01"), color=INK2, lw=0.8, ls="--")
    ax.set_xlim(pd.Timestamp("2022-01-01"), pd.Timestamp("2032-06-01"))
    estilo(ax, "Capacidade instalada no NE: histórico (média mensal) e cenários de 2030", "GW")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    salvar(fig, "r03_capacidade_historico_cenarios.png")


def r04_mapas_calor(X):
    x = X[X.ano == 2025]
    series = [("L_net", "Carga líquida de MMGD (MWmed)", "Greys"), ("cf_eol_pot", "CF eólico potencial", "Greens"),
              ("cf_sol_pot", "CF solar potencial", "Oranges"), ("MMGD", "MMGD estimada (MWmed)", "RdPu")]
    fig, axes = plt.subplots(1, 4, figsize=(15, 4.2))
    for ax, (col, tit, cm) in zip(axes, series):
        piv = x.pivot_table(index="hora", columns="mes", values=col, aggfunc="mean")
        im = ax.imshow(piv.values, aspect="auto", cmap=cm, origin="lower")
        ax.set_xticks(range(12), [m[0].upper() for m in MESES], fontsize=7)
        ax.set_yticks(range(0, 24, 3), range(0, 24, 3), fontsize=7)
        ax.set_title(tit, loc="left", fontsize=9.5); ax.set_xlabel("mês", fontsize=8, color=INK2)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03).ax.tick_params(labelsize=7)
    axes[0].set_ylabel("hora (Brasília)", fontsize=8, color=INK2)
    fig.suptitle("Perfis médios por hora do dia × mês, 2025", x=0.01, ha="left", fontsize=11)
    salvar(fig, "r04_mapas_calor_hora_mes_2025.png")
    piv = x.pivot_table(index="hora", values=["L_net", "cf_eol_pot", "cf_sol_pot"], aggfunc="mean")
    return piv


def r05_temperatura_carga(X):
    x = X[X.ano.between(2022, 2025)].copy()
    x["Lnorm"] = x.L_gross / x.groupby("ano").L_gross.transform("mean")
    d = x.groupby(x.t.dt.date).agg(L=("Lnorm", "mean"), Tm=("temperature_2m", "mean"), dow=("dia_semana", "first"),
                                   fer=("feriado_nacional", "max"))
    util = (d.dow < 5) & (d.fer == 0)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.scatter(d.Tm[util], d.L[util], s=9, alpha=0.5, color=COR["hid"], label="dias úteis")
    ax.scatter(d.Tm[~util], d.L[~util], s=9, alpha=0.6, color=COR["ter"], label="fins de semana e feriados")
    for msk, cor in [(util, COR["hid"]), (~util, COR["ter"])]:
        b = np.polyfit(d.Tm[msk], d.L[msk], 1)
        xs = np.linspace(d.Tm.min(), d.Tm.max(), 10)
        ax.plot(xs, np.polyval(b, xs), color=cor, lw=2)
    estilo(ax, "Carga bruta diária (relativa à média do ano) × temperatura média ponderada, 2022–2025",
           "carga / média anual", "temperatura a 2 m ponderada pela população (°C)")
    ax.legend(frameon=False, fontsize=8)
    salvar(fig, "r05_temperatura_carga.png")
    corr = {"util": np.corrcoef(d.Tm[util], d.L[util])[0, 1], "nao_util": np.corrcoef(d.Tm[~util], d.L[~util])[0, 1],
            "slope_util_pct_por_C": 100 * np.polyfit(d.Tm[util], d.L[util], 1)[0],
            "nivel_fim_semana_pct": 100 * (d.L[~util].mean() / d.L[util].mean() - 1)}
    return corr


def r06_corte_hora_mes():
    H = pd.read_parquet(INTERIM / "ne_hourly.parquet")
    x = H[H.t.dt.year == 2025].copy()
    x["mes"], x["hora"] = x.t.dt.month, x.t.dt.hour
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    for ax, (col, tit) in zip(axes, [("coff_eol_gnr_ene", "ENE — razão energética"), ("coff_eol_gnr_cnf", "CNF — confiabilidade"),
                                     ("coff_eol_gnr_rel", "REL — indisponibilidade externa")]):
        piv = x.assign(v=x[col].fillna(0)).pivot_table(index="hora", columns="mes", values="v", aggfunc="mean")
        im = ax.imshow(piv.values, aspect="auto", cmap="Reds", origin="lower", vmin=0)
        ax.set_xticks(range(12), [m[0].upper() for m in MESES], fontsize=7)
        ax.set_yticks(range(0, 24, 3), range(0, 24, 3), fontsize=7)
        ax.set_title(tit, loc="left", fontsize=9.5); ax.set_xlabel("mês", fontsize=8, color=INK2)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.03, label="MWmed").ax.tick_params(labelsize=7)
    axes[0].set_ylabel("hora (Brasília)", fontsize=8, color=INK2)
    fig.suptitle("Corte eólico apurado (GNRa) médio por hora × mês e por motivo, 2025", x=0.01, ha="left", fontsize=11)
    salvar(fig, "r06_corte_eolico_hora_mes_2025.png")


def r07_importacao_hora(X):
    x = X[X.ano.between(2022, 2025)]
    p = (x.interc < 0).groupby([x.ano, x.hora]).mean().unstack(0) * 100
    fig, ax = plt.subplots(figsize=(9, 4))
    for ano, cor in zip(p.columns, [COR["hid"], COR["ter"], COR["eol"], COR["dc"]]):
        ax.plot(p.index, p[ano], color=cor, lw=2, label=str(ano))
    ax.set_xticks(range(0, 24, 2))
    estilo(ax, "Horas com importação líquida pelo NE, por hora do dia (observado)", "% das horas do ano", "hora (Brasília)")
    ax.legend(frameon=False, fontsize=8, ncol=4)
    salvar(fig, "r07_importacao_por_hora_historico.png")
    return p


def r08_data_centers():
    of = pd.read_csv(CONFIG / "dc_trajetoria_oficial_ne.csv")
    inv = pd.read_csv(CONFIG / "data_centers_ne.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.6), gridspec_kw={"width_ratios": [1, 1.3]})
    for est, cor, lab in [("PLAN 2026-2030", "#8fbcef", "PLAN 2026–30 (acessos de nov/2025)"),
                          ("1a RQ PLAN 2026-2030", "#2a78d6", "1ª RQ (mar/2026)"), ("2a RQ PLAN 2026-2030", "#0d3f80", "2ª RQ (jul/2026)")]:
        g = of[(of.estudo == est) & (of.componente == "total")]
        a1.plot(g.ano, g.mwmed, marker="o", color=cor, lw=2, label=lab)
        a1.text(2030.08, g.mwmed.iat[-1], f"{g.mwmed.iat[-1]:,.0f}".replace(",", "."), fontsize=8, va="center")
    g = of[(of.estudo == "2a RQ PLAN 2026-2030") & (of.componente == "contratos_assinados")]
    a1.plot(g.ano, g.mwmed, color="#0d3f80", lw=1.2, ls="--", label="2ª RQ: só contratos assinados")
    a1.set_xticks(range(2026, 2031)); a1.set_xlim(2025.8, 2030.6)
    estilo(a1, "Projeção oficial de carga de data centers no NE (Rede Básica)", "MWmed")
    a1.legend(frameon=False, fontsize=7.5, loc="upper left")
    v = inv.dropna(subset=["potencia_mw"]).sort_values("potencia_mw")
    from matplotlib.patches import Patch
    cores = {"M0": "#c9c8c2", "M1": "#0d3f80", "M2": "#2a78d6", "M3": "#8fbcef"}
    rot = {"M0": "M0 em operação até 2025", "M1": "M1 obra, contrato ou operação em 2026",
           "M2": "M2 conexão contratada ou viável", "M3": "M3 anúncio ou protocolo"}
    a2.barh(v.projeto.str.slice(0, 42), v.potencia_mw, color=[cores[m] for m in v.maturidade])
    a2.tick_params(axis="y", labelsize=7)
    estilo(a2, "Inventário: potência publicada por projeto", "", "MW, na definição de cada fonte")
    a2.grid(axis="x", color=GRID)
    a2.legend(handles=[Patch(color=cc, label=rot[m]) for m, cc in cores.items()], frameon=False, fontsize=7.5, loc="lower right")
    salvar(fig, "r08_data_centers_trajetoria_inventario.png")


def r09_ciclo_diurno(X):
    x = X[X.ano == 2025]
    g = x.groupby("hora")[["cf_eol_pot", "wind_speed_100m", "wind_speed3_100m"]].mean()
    g = g / g.mean()
    fig, ax = plt.subplots(figsize=(8.5, 4))
    ax.plot(g.index, g.cf_eol_pot, color=COR["eol"], lw=2.4, label="CF eólico potencial (ONS)")
    ax.plot(g.index, g.wind_speed3_100m, color=COR["carga"], lw=1.6, label="vento³ a 100 m (ERA5)")
    ax.plot(g.index, g.wind_speed_100m, color=COR["cinza"], lw=1.6, ls="--", label="vento a 100 m (ERA5)")
    ax.axhline(1, color=GRID, lw=1)
    ax.set_xticks(range(0, 24, 2))
    estilo(ax, "Ciclo diário médio em 2025, relativo à média do dia", "valor / média diária", "hora (Brasília)")
    ax.legend(frameon=False, fontsize=8)
    salvar(fig, "r09_ciclo_diurno_cf_vs_era5.png")
    return g


# ------------------------------------------------------------------ etapa 2: modelos
def r10_backtest_mensal():
    M = pd.read_csv(REPORTS / "models" / "metricas_curto_prazo_mensal.csv")
    B = pd.read_csv(REPORTS / "models" / "comparacao_hgb_baseline.csv")
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8))
    nomes = {"A_carga_liquida": "A — carga líquida (MW)", "B_cf_eolico_pot": "B — CF eólico potencial", "C_cf_solar": "C — CF solar"}
    for ax, alvo in zip(axes, nomes):
        bb = B[(B.alvo == alvo) & (B.h == 24)].metodo_melhor_baseline.iat[0]
        g = M[(M.alvo == alvo) & (M.h == 24)].pivot_table(index="mes", columns="metodo", values="MAE")
        x = np.arange(len(g))
        ax.bar(x - 0.2, g[bb], width=0.38, color=COR["cinza"], label=f"baseline ({bb})")
        ax.bar(x + 0.2, g["HGB"], width=0.38, color=COR["hid"], label="HGB")
        ax.set_xticks(x, [m[5:] for m in g.index], fontsize=7)
        estilo(ax, f"{nomes[alvo]}, h = 24 h", "MAE", "mês de 2025 (dobra)")
        ax.legend(frameon=False, fontsize=7)
    salvar(fig, "r10_backtest_mae_mensal.png")


def r11_transferencia_importancia():
    from src.sim import sinteticos as si
    D = si.dados_treino()
    rows, pred = [], {}
    casos = {"A0": ("2022-01-01", "2024-12-31 23:00", "2025-01-01", "2025-12-31 23:00"),
             "B0": ("2024-07-01", "2025-12-31 23:00", "2026-01-01", "2026-10-31 23:00")}
    for nome, (a, b, c_, d_) in casos.items():
        s = si.MODELOS[nome]
        tr = D.t.between(a, b) & D[s["alvo"]].notna()
        te = D.t.between(c_, d_) & D[s["alvo"]].notna()
        from sklearn.ensemble import HistGradientBoostingRegressor
        from src.models.backtest import HGB
        mdl = HistGradientBoostingRegressor(**HGB).fit(D.loc[tr, s["ex"]], D.loc[tr, s["alvo"]])
        Xte = D.loc[te, s["ex"]]
        yte = D.loc[te, s["alvo"]]
        sub = Xte.sample(min(6000, len(Xte)), random_state=1)
        pi = permutation_importance(mdl, sub, yte.loc[sub.index], n_repeats=5, random_state=1, scoring="neg_mean_absolute_error")
        for f, v, e in zip(s["ex"], pi.importances_mean, pi.importances_std):
            rows.append({"modelo": nome, "feature": f, "aumento_MAE": v, "dp": e})
        pred[nome] = pd.DataFrame({"t": D.loc[te, "t"], "obs": yte, "pred": mdl.predict(Xte)})
    I = pd.DataFrame(rows)
    I.to_csv(TABLES / "didatico_importancia_permutacao.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    for ax, nome, tit in [(axes[0], "A0", "A0 — forma da carga bruta (teste 2025)"), (axes[1], "B0", "B0 — CF eólico potencial (teste 2026)")]:
        g = I[I.modelo == nome].sort_values("aumento_MAE")
        ax.barh(g.feature, g.aumento_MAE, xerr=g.dp, color=COR["hid"] if nome == "A0" else COR["eol"], ecolor=INK2)
        estilo(ax, tit, "", "aumento do MAE ao embaralhar a variável")
        ax.grid(axis="x", color=GRID); ax.tick_params(axis="y", labelsize=8)
    salvar(fig, "r11_importancia_permutacao.png")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    a = pred["A0"]; w = a[(a.t >= "2025-07-07") & (a.t < "2025-07-21")]
    axes[0].plot(w.t, w.obs, color=COR["carga"], lw=1.8, label="observado")
    axes[0].plot(w.t, w.pred, color=COR["hid"], lw=1.8, label="A0 (só clima e calendário)")
    estilo(axes[0], "A0: duas semanas de julho/2025, fora do treino", "carga / média anual")
    axes[0].legend(frameon=False, fontsize=8)
    b = pred["B0"].set_index("t").resample("D").mean()
    axes[1].plot(b.index, b.obs, color=COR["carga"], lw=1.6, label="observado (média diária)")
    axes[1].plot(b.index, b.pred, color=COR["eol"], lw=1.6, label="B0 (vento ERA5 + hora/mês)")
    estilo(axes[1], "B0: CF eólico potencial diário em 2026, fora do treino", "CF")
    axes[1].legend(frameon=False, fontsize=8)
    salvar(fig, "r12_transferencia_obs_vs_pred.png")
    return I


def r13_classificador():
    cal = pd.read_csv(REPORTS / "models" / "cortes_calibracao.csv")
    taxa = pd.read_csv(REPORTS / "models" / "cortes_taxa_eventos_ano.csv", index_col=0)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
    for col, cor, lab in [("y_ene", COR["imp"], "ENE"), ("y_cnf", COR["ter"], "CNF"), ("y_rel", COR["hid"], "REL"), ("y_total", COR["carga"], "total")]:
        a1.plot(taxa.index, taxa[col] * 100, marker="o", color=cor, lw=2, label=lab)
    estilo(a1, "Horas com corte eólico > 1% da capacidade, por motivo", "% das horas do ano")
    a1.set_xticks(taxa.index); a1.legend(frameon=False, fontsize=8)
    a2.plot([0, 1], [0, 1], color=GRID, lw=1.5)
    for (alvo, teste), g in cal[cal.alvo.isin(["y_ene", "y_total"])].groupby(["alvo", "teste"]):
        cor = COR["imp"] if alvo == "y_ene" else COR["carga"]
        ls = "-" if teste.startswith("2025") else "--"
        a2.plot(g.p_med, g.freq_obs, marker="o", color=cor, ls=ls, lw=1.8, label=f"{alvo[2:].upper()} — teste {teste[:4]}")
    estilo(a2, "Calibração: probabilidade prevista × frequência observada", "frequência observada", "probabilidade prevista (média da faixa)")
    a2.legend(frameon=False, fontsize=8)
    salvar(fig, "r13_classificador_cortes.png")


# ------------------------------------------------------------------ etapas 3-4: simulador e Monte Carlo
def mc_contexto():
    from src.sim import montecarlo as mc
    c, d = mc.load_cfg()
    ins = mc.Insumos()
    return mc, c, d, ins


def r14_semana_2030(mc, c, d, ins):
    """Uma semana de 2030 (sorteio de importação mediana) decomposta: geração × carga + DC."""
    D = pd.read_parquet(PROCESSED / "mc_sorteios.parquet")
    g = D[(D.cenario_dc == "central") & (D.cenario_eolico == "base")]
    alvo = g.iloc[(g.importacao_TWh - g.importacao_TWh.median()).abs().argsort().iloc[0]]
    sd = mc.sortear(ins, 2000, 7, 20261112)
    i = int(alvo.sorteio)
    idx = np.array([i])
    h = sd["h"][idx]
    k = mc.componentes(ins, sd, idx, c)                   # mesmos componentes do simulador
    L, M = k["L"][0], k["MMGD"][0]
    eol = k["cfe"][0] * c["eolica"]["capacidade_2030_MW"]["base"]["valor"]
    sol = k["cfs"][0] * c["solar"]["capacidade_2030_MW"]["valor"]
    ter = k["ter"][0]
    base, cfe, _, hh = mc.series(ins, sd, idx, c)
    hid = mc.hidraulica(ins, hh, -(base + cfe * c["eolica"]["capacidade_2030_MW"]["base"]["valor"]), "regra_historica")[0]
    hid_hist = ins.hid[h][0]
    ldc = mc.l_dc_2030("central", d)[0]
    t = pd.date_range("2030-01-01", periods=8760, freq="h")
    S = pd.DataFrame({"hid": hid, "hid_hist": hid_hist, "ter": ter, "eol": eol, "sol": sol, "mmgd": M, "L": L}, index=t)
    S["G"] = S[["hid", "ter", "eol", "sol", "mmgd"]].sum(axis=1)
    S["Mdc"] = S.G - (S.L + ldc)
    # semana com mais importação no mês de menor vento (abril–maio costuma ser o vale eólico)
    sem = S.Mdc.clip(upper=0).resample("W-MON").sum()
    ini = sem.idxmin() - pd.Timedelta(days=7)
    w7 = S.loc[ini: ini + pd.Timedelta(days=7)]
    fig, ax = plt.subplots(figsize=(12, 4.8))
    pilha = [("hid", "hidráulica (regra emulada)", COR["hid"]), ("ter", "térmica", COR["ter"]), ("eol", "eólica", COR["eol"]),
             ("sol", "solar centralizada", COR["sol"]), ("mmgd", "MMGD", COR["mmgd"])]
    ax.stackplot(w7.index, *[w7[k] / 1000 for k, _, _ in pilha], colors=[cc for _, _, cc in pilha],
                 labels=[lab for _, lab, _ in pilha], alpha=0.85, edgecolor="white", lw=0.3)
    ax.plot(w7.index, w7.L / 1000, color=COR["carga"], lw=1.6, label="carga bruta sem DC")
    ax.plot(w7.index, (w7.L + ldc) / 1000, color=COR["dc"], lw=2, label=f"carga + DC central ({ldc/1000:.1f} GWmed)".replace(".", ","))
    ax.fill_between(w7.index, w7.G / 1000, (w7.L + ldc) / 1000, where=w7.Mdc < 0, facecolor="none", edgecolor=COR["imp"],
                    hatch="////", lw=0, label="importação necessária")
    estilo(ax, f"Semana de maior importação de um sorteio mediano de 2030 (clima {int(alvo.ano_clima)}, hidrologia {int(alvo.ano_hidro)}; eólica base, DC central)", "GW médios na hora")
    ax.legend(frameon=False, fontsize=7.5, ncol=4, loc="upper left")
    salvar(fig, "r14_semana_simulada_2030.png")
    fig, ax = plt.subplots(figsize=(12, 4))
    nl = (w7.L - w7.mmgd - w7.eol - w7.sol - w7.ter) / 1000
    ax.plot(w7.index, w7.hid_hist / 1000, color=COR["cinza"], lw=1.6, label=f"hidráulica observada em {int(alvo.ano_hidro)} (mesmas datas)")
    ax.plot(w7.index, w7.hid / 1000, color=COR["hid"], lw=2, label="hidráulica pela regra emulada (2030)")
    ax.plot(w7.index, nl, color=COR["carga"], lw=1, ls=":", label="carga líquida antes da hidráulica (2030)")
    estilo(ax, "Regra hidráulica emulada: mesma energia diária, forma que acompanha a carga líquida simulada", "GW")
    ax.legend(frameon=False, fontsize=7.5, ncol=3, loc="upper left")
    salvar(fig, "r15_regra_hidraulica.png")
    return {"sorteio": i, "ano_clima": int(alvo.ano_clima), "ano_hidro": int(alvo.ano_hidro), "semana_inicio": str(ini.date())}


def r16_diferencas_e_anos(mc, c, d, ins):
    D = pd.read_parquet(PROCESSED / "mc_sorteios.parquet")
    b = D[D.cenario_eolico == "base"].pivot_table(index="sorteio", columns="cenario_dc", values="importacao_TWh")
    g = D[(D.cenario_dc == "central") & (D.cenario_eolico == "base")]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 4.4), gridspec_kw={"width_ratios": [1, 1.8]})
    dlt = b.central - b.sem_dc
    a1.hist(dlt, bins=40, color=COR["hid"], edgecolor="white")
    for q in [5, 50, 95]:
        v = np.percentile(dlt, q)
        a1.axvline(v, color=INK2, lw=1, ls="--")
        a1.text(v, a1.get_ylim()[1] * 0.95, f"P{q}\n{v:.1f}".replace(".", ","), fontsize=7.5, ha="center", va="top")
    estilo(a1, "Efeito dos DC por sorteio: central − sem DC (eólica base)", "nº de sorteios", "Δ importação (TWh/ano)")
    anos = sorted(g.ano_clima.unique())
    a2.boxplot([g[g.ano_clima == a].importacao_TWh for a in anos], positions=range(len(anos)), widths=0.6,
               patch_artist=True, boxprops=dict(facecolor="#cfe1f6", edgecolor=COR["hid"]),
               medianprops=dict(color=COR["hid"], lw=2), whiskerprops=dict(color=INK2), capprops=dict(color=INK2), flierprops=dict(markersize=2))
    a2.set_xticks(range(len(anos)), [str(a)[2:] for a in anos], fontsize=7)
    estilo(a2, "Importação anual por ano meteorológico sorteado (DC central, eólica base)", "TWh/ano", "ano meteorológico (19xx/20xx)")
    salvar(fig, "r16_efeito_pareado_e_anos_meteorologicos.png")


def r17_curva_compensacao(mc, c, d, ins, n=300):
    sd = mc.sortear(ins, n, 7, 20261112)
    idx = np.arange(n)
    base, cfe, _, h = mc.series(ins, sd, idx, c)
    cap0 = c["eolica"]["capacidade_2030_MW"]["base"]["valor"]
    grade = np.arange(0, 16001, 1000)
    rows = []
    for dw in grade:
        G = base + cfe * (cap0 + dw)
        G = G + mc.hidraulica(ins, h, -G, "regra_historica")
        for cen in ["sem_dc", "central"]:
            ldc = mc.l_dc_2030(cen, d)[0]
            imp = np.clip(-(G - ldc), 0, None)
            rows.append({"dW_MW": dw, "cenario_dc": cen, "importacao_TWh": imp.sum(1).mean() / 1e6,
                         "horas": (G - ldc < 0).sum(1).mean()})
    Cv = pd.DataFrame(rows)
    Cv.to_csv(TABLES / "didatico_curva_compensacao.csv", index=False)
    K = pd.read_csv(REPORTS / "mc" / "mc_compensacao_eolica.csv")
    k = K[(K.cenario_dc == "central") & (K.cenario_eolico == "base")].iloc[0]
    ref = Cv[(Cv.cenario_dc == "sem_dc") & (Cv.dW_MW == 0)].importacao_TWh.iat[0]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for cen in ["sem_dc", "central"]:
        g = Cv[Cv.cenario_dc == cen]
        ax.plot(g.dW_MW / 1000, g.importacao_TWh, color=SEQ[cen], lw=2.4, marker="o", ms=3, label=f"{cen} + ΔW eólico")
    ax.axhline(ref, color=SEQ["sem_dc"], lw=1, ls="--")
    ax.text(15.8, ref + 0.08, "nível sem DC (ΔW = 0)", fontsize=8, ha="right", color=INK2)
    for x, lab in [(k.dW_energia_anual_MW / 1000, "compensa a energia anual"), (k.dW_importacao_anual_media_MW / 1000, "compensa a importação anual")]:
        ax.axvline(x, color=INK2, lw=1, ls=":")
        ax.text(x + 0.15, ax.get_ylim()[1] * 0.92, f"{lab}\n{x:.1f} GW".replace(".", ","), fontsize=8, color=INK2)
    estilo(ax, f"Importação média em 2030 × eólica adicional sobre a base ({n} sorteios comuns)", "importação (TWh/ano)", "ΔW eólico adicional (GW)")
    ax.legend(frameon=False, fontsize=8, loc="lower left")
    salvar(fig, "r17_curva_compensacao_eolica.png")
    return Cv


def r18_importacao_por_hora_2030(mc, c, d, ins, n=500):
    sd = mc.sortear(ins, n, 7, 20261112)
    idx = np.arange(n)
    base, cfe, _, h = mc.series(ins, sd, idx, c)
    cap = c["eolica"]["capacidade_2030_MW"]["base"]["valor"]
    G = base + cfe * cap
    G = G + mc.hidraulica(ins, h, -G, "regra_historica")
    hora = np.tile(np.arange(24), 365)
    rows = []
    for cen in ["sem_dc", "conservador", "central", "alto"]:
        ldc = mc.l_dc_2030(cen, d)[0]
        imp = np.clip(-(G - ldc), 0, None)
        prob = (G - ldc < 0)
        for hr in range(24):
            m = hora == hr
            rows.append({"cenario_dc": cen, "hora": hr, "importacao_media_MW": imp[:, m].mean(),
                         "pct_horas_importacao": 100 * prob[:, m].mean()})
    P = pd.DataFrame(rows)
    P.to_csv(TABLES / "didatico_importacao_por_hora_2030.csv", index=False)
    cfh = pd.DataFrame({"hora": hora, "cf": cfe.mean(0)}).groupby("hora").cf.mean()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 4.2))
    for cen in ["sem_dc", "conservador", "central", "alto"]:
        g = P[P.cenario_dc == cen]
        a1.plot(g.hora, g.pct_horas_importacao, color=SEQ[cen], lw=2.2, label=cen)
    a1.set_xticks(range(0, 24, 2))
    estilo(a1, "2030: % das horas com importação, por hora do dia (eólica base)", "% das horas", "hora")
    a1.legend(frameon=False, fontsize=8)
    a2.plot(cfh.index, cfh.values, color=COR["eol"], lw=2.2)
    a2.set_xticks(range(0, 24, 2))
    estilo(a2, "CF eólico médio sorteado por hora do dia", "CF", "hora")
    salvar(fig, "r18_importacao_por_hora_2030.png")
    return P


def numeros_intercambio(X) -> dict:
    """Intercâmbio observado em 2022–2025 (interc > 0 = exportação do NE), para o texto."""
    g = X[X.ano.between(2022, 2025)]
    liq = g.groupby("ano").interc.sum() / 1e6             # exportação líquida (TWh)
    pct = 100 * (g.interc < 0).groupby(g.ano).mean()      # % das horas com importação
    return {"export_liq_2022_TWh": float(liq.loc[2022]), "export_liq_2025_TWh": float(liq.loc[2025]),
            "pct_horas_import_min": float(pct.min()), "pct_horas_import_max": float(pct.max())}


def main() -> None:
    import yaml
    c = yaml.safe_load(open(CONFIG / "cenarios.yaml", encoding="utf-8"))
    X = feats()
    out = {}
    r01_cobertura()
    out["mapa"] = r02_mapa()
    r03_capacidade(X, c)
    out["perfis"] = r04_mapas_calor(X)
    out["temp"] = r05_temperatura_carga(X)
    r06_corte_hora_mes()
    out["imp_hora_hist"] = r07_importacao_hora(X)
    r08_data_centers()
    out["diurno"] = r09_ciclo_diurno(X)
    r10_backtest_mensal()
    r11_transferencia_importancia()
    r13_classificador()
    mc, c2, d, ins = mc_contexto()
    out["semana"] = r14_semana_2030(mc, c2, d, ins)
    r16_diferencas_e_anos(mc, c2, d, ins)
    r17_curva_compensacao(mc, c2, d, ins)
    r18_importacao_por_hora_2030(mc, c2, d, ins)
    # números citados no texto
    t = out["temp"]; dv = out["diurno"]; ih = out["imp_hora_hist"]
    nums = {"temp_corr_util": t["util"], "temp_slope_util_pct_por_C": t["slope_util_pct_por_C"],
            "fim_semana_nivel_pct": t["nivel_fim_semana_pct"],
            "cf_noite_rel": float(dv.cf_eol_pot.loc[[0, 1, 2, 3, 4, 22, 23]].mean()), "cf_meiodia_rel": float(dv.cf_eol_pot.loc[[11, 12, 13]].mean()),
            "v3_noite_rel": float(dv.wind_speed3_100m.loc[[0, 1, 2, 3, 4, 22, 23]].mean()), "v3_meiodia_rel": float(dv.wind_speed3_100m.loc[[11, 12, 13]].mean()),
            "imp_hist_pct_madrugada": float(ih.loc[1:4].mean().mean()), "imp_hist_pct_meiodia": float(ih.loc[9:12].mean().mean()),
            "imp_hist_pct_17h": float(ih.loc[17].mean()),
            **numeros_intercambio(X),
            "n_usinas_eol": int(out["mapa"].loc["EOL", "size"]), "cap_eol_mapa_MW": float(out["mapa"].loc["EOL", "sum"]),
            "n_usinas_sol": int(out["mapa"].loc["SOL", "size"]), "cap_sol_mapa_MW": float(out["mapa"].loc["SOL", "sum"]),
            **{f"semana_{k}": v for k, v in out["semana"].items()}}
    pd.Series(nums).to_csv(TABLES / "didatico_numeros.csv", header=["valor"])
    print(pd.Series(nums).to_string())


if __name__ == "__main__":
    main()
