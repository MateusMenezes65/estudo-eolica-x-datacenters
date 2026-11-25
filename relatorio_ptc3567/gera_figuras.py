"""Figuras do relatório, redesenhadas no tamanho da página a partir das saídas do pipeline.

Uso (na raiz do projeto): python relatorio_ptc3567/gera_figuras.py
Lê reports/, data/interim e data/processed. Não é necessário para compilar o LaTeX.
"""
import sys
from pathlib import Path

import matplotlib
import matplotlib.dates
import matplotlib.patches
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
FIG = AQUI / "figures"
REP = RAIZ / "reports"
PREVIA = Path(sys.argv[1]) if len(sys.argv) > 1 else None      # pasta para prévias em PNG

SEQ = {"sem_dc": "#8a8984", "conservador": "#8fbcef", "central": "#2a78d6", "alto": "#0d3f80"}
NOME = {"sem_dc": "sem data centers", "conservador": "conservador", "central": "central", "alto": "alto"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 8, "pdf.fonttype": 42, "axes.titlesize": 8.5, "legend.fontsize": 7.5})


def virgula(x, n=1):
    return f"{x:+.{n}f}".replace(".", ",").replace("-", "−")


def estilo(ax, titulo="", ylabel="", xlabel=""):
    ax.set_title(titulo, loc="left")
    ax.set_ylabel(ylabel, color=INK2)
    ax.set_xlabel(xlabel, color=INK2)
    ax.grid(axis="y", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    ax.tick_params(colors=INK2)


def salvar(fig, nome):
    """Salva em PDF com vírgula decimal nos eixos."""
    for ax in fig.axes:
        for eixo in [ax.xaxis, ax.yaxis]:
            if isinstance(eixo.get_major_formatter(), matplotlib.ticker.ScalarFormatter):
                eixo.set_major_formatter(matplotlib.ticker.FuncFormatter(
                    lambda v, _, eixo=eixo: f"{v:.{casas(eixo)}f}".replace(".", ",").replace("-", "−")))
    fig.tight_layout()
    fig.savefig(FIG / f"{nome}.pdf", dpi=200, bbox_inches="tight", pad_inches=0.02, metadata={"CreationDate": None})
    if PREVIA:
        fig.savefig(PREVIA / f"{nome}.png", dpi=150, bbox_inches="tight", pad_inches=0.02, facecolor="white")
    plt.close(fig)


def casas(eixo):
    """Casas decimais necessárias para as marcas do eixo."""
    v = eixo.get_majorticklocs()
    return next((n for n in range(4) if np.allclose(v, np.round(v, n), atol=1e-9)), 4)


def distribuicao_e_hora():
    S = pd.read_parquet(RAIZ / "data/processed/mc_sorteios.parquet")
    S = S[S.cenario_eolico == "base"]
    H = pd.read_csv(REP / "tables/didatico_importacao_por_hora_2030.csv")
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.3, 2.5))
    for c, cor in SEQ.items():
        x = np.sort(S[S.cenario_dc == c].importacao_TWh.to_numpy())
        a.plot(x, np.arange(1, len(x) + 1) / len(x), color=cor, lw=1.8, label=NOME[c])
        h = H[H.cenario_dc == c]
        b.plot(h.hora, h.pct_horas_importacao, color=cor, lw=1.8)
    estilo(a, "(a) Distribuição acumulada", "fração dos sorteios", "importação em 2030 (TWh)")
    a.set_xlim(0, 14)
    a.legend(frameon=False, loc="lower right")
    estilo(b, "(b) Dias com importação em cada hora", "% dos dias", "hora do dia")
    b.set_xticks(range(0, 24, 4))
    b.set_ylim(0, None)
    salvar(fig, "fig_distribuicao")


def compensacao():
    C = pd.read_csv(REP / "tables/didatico_curva_compensacao.csv")
    K = pd.read_csv(REP / "mc/mc_compensacao_eolica.csv")
    k = K[(K.cenario_dc == "central") & (K.cenario_eolico == "base")].iloc[0]
    ref = C[(C.cenario_dc == "sem_dc") & (C.dW_MW == 0)].importacao_TWh.iat[0]
    g = C[C.cenario_dc == "central"]
    fig, ax = plt.subplots(figsize=(4.9, 2.3))
    ax.plot(g.dW_MW / 1000, g.importacao_TWh, color=SEQ["central"], lw=1.8, marker="o", ms=3)
    ax.axhline(ref, color=SEQ["sem_dc"], lw=1.2, ls="--")
    ax.text(16, ref + 0.05, "nível sem data centers", color=INK2, va="bottom", ha="right")
    for x, t in [(k.dW_energia_anual_MW / 1000, "compensa a\nenergia anual"),
                 (k.dW_importacao_anual_media_MW / 1000, "compensa a\nimportação anual")]:
        ax.axvline(x, color=INK2, lw=0.9, ls=":")
        ax.text(x + 0.2, 5.8, t + f"\n({x:.1f} GW)".replace(".", ","), color=INK2, va="top")
    ax.set_ylim(2, 5.9)
    estilo(ax, "", "importação média (TWh)", "capacidade eólica adicional (GW)")
    salvar(fig, "fig_compensacao")


def sensibilidades():
    S = pd.read_csv(REP / "mc/mc_sensibilidades.csv").set_index("caso").delta_media_TWh
    nomes = {"hidraulica plana": "hidráulica plana", "carga +5%": "carga +5%", "eolica baixa": "eólica baixa",
             "hidraulica historica sorteada (sem resposta)": "hidráulica histórica, sem resposta",
             "hidraulica: amplitude constante em MW": "hidráulica, amplitude constante",
             "nivel de carga pela API do ONS": "nível da carga verificada do ONS", "MMGD baixa": "MMGD baixa",
             "MMGD alta": "MMGD alta", "base PDE 2035": "carga do PDE 2035",
             "hidraulica: beta do proprio ano hidrologico": "coeficiente do ano hidrológico",
             "anos meteorológicos 2010-2025": "anos de clima 2010–2025",
             "sem residuos (perfis suavizados)": "sem resíduos", "carga -5%": "carga −5%",
             "eolica alta": "eólica alta", "DC com atraso de 12 meses": "data centers com 12 meses de atraso"}
    s = S[list(nomes)].rename(nomes).sort_values()
    fig, ax = plt.subplots(figsize=(5.6, 2.9))
    ax.barh(range(len(s)), s.values, height=0.62, color=["#eb6834" if v > 0 else "#2a78d6" for v in s.values])
    for i, v in enumerate(s.values):
        ax.text(v + (0.04 if v > 0 else -0.04), i, virgula(v, 2), va="center", ha="left" if v > 0 else "right", fontsize=6.5, color=INK2)
    ax.axvline(0, color=INK2, lw=0.9)
    estilo(ax, "", "", "variação da importação média (TWh)")
    ax.set_yticks(range(len(s)), s.index)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, lw=0.7)
    ax.set_xlim(-2.1, 2.6)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    salvar(fig, "fig_sensibilidades")


def pipeline():
    fig, ax = plt.subplots(figsize=(6.3, 2.7))
    ax.set_xlim(-0.005, 1.005)
    ax.set_ylim(0, 1.03)
    ax.axis("off")
    W, A = 0.172, 0.15
    X = [0.0, 0.207, 0.414, 0.621, 0.828]
    azul, verde, roxo, lar = ("#e8f0fb", "#2a78d6"), ("#e4f5ee", "#1baf7a"), ("#efedfb", "#6250d6"), ("#fdefe8", "#eb6834")
    cx = {"ons": (0, .70, "ONS: carga, usinas\ne cortes", azul), "era": (0, .36, "ERA5:\n34 pontos", azul),
          "doc": (0, .02, "ANEEL, EPE, PLAN\ne inventário", azul),
          "base": (1, .70, "Base horária\n2022–2026", azul), "cli": (1, .36, "Clima ponderado\n1995–2026", azul),
          "cen": (1, .02, "Cenários\nde 2030", azul),
          "cp": (2, .76, "Previsão de\ncurto prazo", verde), "cls": (2, .56, "Classificação\ndos cortes", verde),
          "ft": (2, .36, "Funções de\ntransferência", verde),
          "perf": (3, .36, "Perfis de 2030\npara 31 anos", roxo), "mc": (3, .02, "Monte Carlo:\n2.000 sorteios", roxo),
          "res": (4, .02, "Importação,\nexcedente e\ncompensação", lar)}
    for c, y, txt, (fill, borda) in cx.values():
        ax.add_patch(matplotlib.patches.FancyBboxPatch((X[c], y), W, A, boxstyle="round,pad=0,rounding_size=0.012",
                                                       fc=fill, ec=borda, lw=1.0))
        ax.text(X[c] + W / 2, y + A / 2, txt, ha="center", va="center", fontsize=7, color=INK)

    def seta(a, b, vert=False, dy=0.0):
        (ca, ya, *_), (cb, yb, *_) = cx[a], cx[b]
        if vert:
            p, q = (X[ca] + W / 2, ya + (A if yb > ya else 0)), (X[cb] + W / 2, yb + (0 if yb > ya else A))
        else:
            p, q = (X[ca] + W, ya + A / 2), (X[cb], yb + A / 2 + dy)
        ax.annotate("", q, p, arrowprops=dict(arrowstyle="-|>", color=INK2, lw=0.9, shrinkA=1, shrinkB=1, mutation_scale=8))

    for a, b in [("ons", "base"), ("era", "cli"), ("doc", "cen"), ("base", "cp"), ("base", "cls"), ("cli", "ft"), ("ft", "perf"),
                 ("cen", "mc"), ("mc", "res")]:
        seta(a, b)
    seta("base", "ft", dy=0.04)
    seta("cli", "base", vert=True)
    seta("perf", "mc", vert=True)
    for c, n in enumerate(["Fontes", "Bases", "Modelos", "Simulação", "Resultados"]):
        ax.text(X[c] + W / 2, 1.03, n, ha="center", va="top", fontsize=7.5, color=INK2, fontweight="bold")
    salvar(fig, "fig_pipeline")


def mapa():
    fc = pd.read_parquet(RAIZ / "data/interim/ne_fc_usina_h.parquet")
    fc = fc[(fc.t >= "2026-10-01") & (fc.t < "2026-11-01")]
    u = fc.groupby(["id_ons", "fonte"]).agg(lat=("val_latitudesecoletora", "first"), lon=("val_longitudesecoletora", "first"),
                                            cap=("val_capacidadeinstalada", "mean")).reset_index().dropna()
    pts = pd.read_csv(RAIZ / "config/weather_points.csv")
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    for fonte, cor, nome in [("EOL", "#1baf7a", "usina eólica"), ("SOL", "#eda100", "usina solar")]:
        g = u[u.fonte == fonte]
        ax.scatter(g.lon, g.lat, s=g.cap / 16, color=cor, alpha=0.6, edgecolor="white", lw=0.4, label=nome)
    for kind, mk, cor, nome in [("wind", "^", INK, "ponto ERA5, eólico"), ("solar", "s", "#7a5b00", "ponto ERA5, solar"),
                                ("capital", "o", "#2a78d6", "capital")]:
        g = pts[pts.kind == kind]
        ax.scatter(g.lon, g.lat, marker=mk, s=18, facecolor="none" if kind != "capital" else cor, edgecolor=cor, lw=0.9, label=nome)
    for r in pts[pts.kind == "capital"].itertuples():
        ax.text(r.lon + 0.2, r.lat + 0.1, r.uf, fontsize=7, color=INK2)
    ax.set_aspect("equal")
    estilo(ax, "", "latitude (°)", "longitude (°)")
    ax.grid(color=GRID, lw=0.6)
    ax.legend(frameon=False, fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5), markerscale=0.8, handletextpad=0.3)
    salvar(fig, "fig_mapa")


def carga():
    H = pd.read_parquet(RAIZ / "data/interim/ne_hourly.parquet").set_index("t")
    M = H[H.index < "2026-11-01"].resample("ME").mean(numeric_only=True)
    fig, ax = plt.subplots(figsize=(5.4, 2.2))
    ax.plot(M.index, M.api_cargaglobal / 1e3, color="#6250d6", lw=1.5, label="carga global")
    ax.plot(M.index, M.bal_carga / 1e3, color=INK, lw=1.5, label="carga do balanço")
    ax.plot(M.index, M.api_cargaglobalsmmgd / 1e3, color="#e34948", lw=1.5, label="carga líquida de MMGD")
    q = pd.Timestamp("2023-04-29")
    ax.axvline(q, color=INK2, lw=0.9, ls="--")
    ax.text(q + pd.Timedelta(days=15), 10.9, "29/04/2023", fontsize=7, color=INK2, va="top")
    estilo(ax, "", "GW médios")
    ax.set_ylim(None, 16.9)
    ax.legend(frameon=False, loc="upper left", ncol=3, fontsize=7)
    salvar(fig, "fig_carga")


def perfis():
    X = pd.read_parquet(RAIZ / "data/processed/ne_features_h.parquet")
    x = X[X.ano == 2025]
    fig, axes = plt.subplots(1, 4, figsize=(6.3, 1.95), sharey=True)
    for ax, (col, k, tit, cm) in zip(axes, [("L_net", 1e3, "Carga líquida (GW)", "Greys"), ("cf_eol_pot", 1, "CF eólico potencial", "Greens"),
                                            ("cf_sol_pot", 1, "CF solar potencial", "Oranges"), ("MMGD", 1e3, "MMGD (GW)", "RdPu")]):
        piv = x.pivot_table(index="hora", columns="mes", values=col, aggfunc="mean") / k
        im = ax.imshow(piv.values, aspect="auto", cmap=cm, origin="lower")
        ax.set_xticks([0, 3, 6, 9], ["jan", "abr", "jul", "out"], fontsize=6.5)
        ax.set_yticks(range(0, 24, 6), range(0, 24, 6), fontsize=6.5)
        ax.set_title(tit, loc="left", fontsize=7)
        ax.tick_params(colors=INK2, length=2)
        fig.colorbar(im, ax=ax, fraction=0.06, pad=0.04).ax.tick_params(labelsize=6, length=2, colors=INK2)
    axes[0].set_ylabel("hora", color=INK2, fontsize=7)
    salvar(fig, "fig_perfis")


def cf_vento():
    H = pd.read_parquet(RAIZ / "data/interim/ne_hourly.parquet").set_index("t")
    fig, axes = plt.subplots(1, 2, figsize=(5.8, 2.3), sharey=True)
    for ax, y in zip(axes, [2022, 2025]):
        d = H[H.index.year == y]
        pot = (d.coff_eol_geracao + d.coff_eol_geracaonaorealizadaapurada.fillna(0)) / d.fc_eol_cap
        for s, cor, n in [(pot, "#1baf7a", "potencial"), (d.fc_eol_ger / d.fc_eol_cap, "#eb6834", "observado")]:
            ax.scatter(d.w_wind_speed_100m_cap, s, s=1.2, color=cor, alpha=0.25, lw=0, label=n, rasterized=True)
        estilo(ax, str(y), "CF eólico" if y == 2022 else "", "vento a 100 m (m/s)")
    leg = axes[0].legend(frameon=False, markerscale=5, loc="upper left", handletextpad=0.2)
    for h in leg.legend_handles:
        h.set_alpha(0.9)
    salvar(fig, "fig_cf_vento")


def transferencia():
    sys.path.insert(0, str(RAIZ))
    from sklearn.ensemble import HistGradientBoostingRegressor
    from src.models.backtest import HGB
    from src.sim import sinteticos as si
    D = si.dados_treino()
    casos = {"A0": ("2022-01-01", "2024-12-31 23:00", "2025-01-01", "2025-12-31 23:00"),
             "B0": ("2024-07-01", "2025-12-31 23:00", "2026-01-01", "2026-10-31 23:00")}
    p = {}
    for nome, (a, b, c, d) in casos.items():
        s = si.MODELOS[nome]
        tr = D.t.between(a, b) & D[s["alvo"]].notna()
        te = D.t.between(c, d) & D[s["alvo"]].notna()
        m = HistGradientBoostingRegressor(**HGB).fit(D.loc[tr, s["ex"]], D.loc[tr, s["alvo"]])
        p[nome] = pd.DataFrame({"obs": D.loc[te, s["alvo"]].to_numpy(), "pred": m.predict(D.loc[te, s["ex"]])}, index=pd.DatetimeIndex(D.loc[te, "t"]))
    fig, (a, b) = plt.subplots(1, 2, figsize=(6.3, 2.3))
    w = p["A0"]["2025-07-07":"2025-07-20"]
    a.plot(w.index, w.obs, color=INK, lw=1.2, label="observado")
    a.plot(w.index, w.pred, color="#2a78d6", lw=1.2, label="função A0")
    estilo(a, "(a) Carga ÷ média anual, julho de 2025")
    a.set_xticks(pd.date_range("2025-07-07", "2025-07-21", freq="4D"))
    a.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%d/%m"))
    a.set_ylim(0.66, None)
    a.legend(frameon=False, loc="lower left", ncol=2, fontsize=7)
    v = p["B0"].resample("D").mean()
    b.plot(v.index, v.obs, color=INK, lw=1.0, label="observado")
    b.plot(v.index, v.pred, color="#1baf7a", lw=1.0, label="função B0")
    estilo(b, "(b) CF eólico potencial diário, 2026")
    b.set_xticks(pd.date_range("2026-01-01", "2026-11-01", freq="2MS"), ["jan", "mar", "mai", "jul", "set", "nov"])
    b.set_ylim(0, 0.95)
    b.legend(frameon=False, loc="upper left", ncol=2, fontsize=7)
    salvar(fig, "fig_transferencia")


def backtest():
    B = pd.read_csv(REP / "sim/backtest_2026_mensal.csv")
    fig, axes = plt.subplots(1, 2, figsize=(6.3, 2.4))
    mes = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out"]
    for ax, v, tit in [(axes[0], "importacao", "(a) Importação (TWh)"), (axes[1], "excedente", "(b) Excedente (TWh)")]:
        ax.fill_between(B.mes, B[f"A_{v}_p5_TWh"], B[f"A_{v}_p95_TWh"], color="#c7ddf6", lw=0, label="A: P5–P95")
        ax.plot(B.mes, B[f"A_{v}_p50_TWh"], color="#2a78d6", lw=1.1, ls="--", label="A: mediana")
        ax.plot(B.mes, B[f"B_{v}_TWh"], color="#eb6834", lw=1.4, marker="o", ms=3, label="B")
        ax.plot(B.mes, B[f"obs_pot_{v}_TWh"], color=INK, lw=1.4, marker="s", ms=3, label="observado")
        estilo(ax, tit)
        ax.set_xticks([1, 4, 7, 10], [mes[i - 1] for i in [1, 4, 7, 10]])
    axes[0].legend(frameon=False, fontsize=7, loc="upper right")
    salvar(fig, "fig_backtest")


if __name__ == "__main__":
    FIG.mkdir(exist_ok=True)
    for f in [pipeline, mapa, carga, perfis, cf_vento, transferencia, backtest, distribuicao_e_hora, compensacao, sensibilidades]:
        f()
