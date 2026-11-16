"""Fluxogramas do relatório técnico desenhados como imagens (para a versão HTML).

Uso: python -m src.report.diagramas
Saídas: reports/figures/d1_pipeline.png e d2_sorteio.png
O relatório em Markdown mantém os mesmos fluxogramas como blocos `mermaid`; `src.report.html`
troca cada bloco, na ordem em que aparece, pela imagem correspondente de DIAGRAMAS.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from src.paths import FIGURES

INK, INK2 = "#0b0b0b", "#52514e"
GRUPO = {"dados": ("#e8f1fb", "#2a78d6"), "modelos": ("#e6f6ef", "#1baf7a"),
         "sim": ("#efecfb", "#6250d6"), "res": ("#fdf0e9", "#eb6834"), "sorteio": ("#fdf5e0", "#eda100")}
# ordem dos blocos mermaid no relatório técnico -> (arquivo, legenda)
DIAGRAMAS = [("d1_pipeline.png", "Visão geral do pipeline: das fontes de dados aos resultados."),
             ("d2_sorteio.png", "Como é feito um sorteio do Monte Carlo.")]
W, H = 0.90, 0.56   # largura e altura das caixas, em unidades do eixo


def caixa(ax, x, y, texto, grupo, w=W, h=H):
    face, borda = GRUPO[grupo]
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h, boxstyle="round,pad=0.0,rounding_size=0.06",
                                facecolor=face, edgecolor=borda, lw=1.2))
    ax.text(x, y, texto, ha="center", va="center", fontsize=8, color=INK, linespacing=1.25)


def seta(ax, a, b, w=W, h=H, vertical=False):
    """Seta da caixa centrada em `a` até a caixa centrada em `b`."""
    (xa, ya), (xb, yb) = a, b
    if vertical:
        ini, fim = (xa, ya - h / 2), (xb, yb + h / 2)
    else:
        ini, fim = (xa + w / 2, ya), (xb - w / 2, yb)
    ax.annotate("", xy=fim, xytext=ini, arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1.1, shrinkA=1, shrinkB=1))


def moldura(ax, xlim, ylim):
    ax.set_xlim(*xlim); ax.set_ylim(*ylim)
    ax.axis("off")


def pipeline():
    p = {"ERA": (0, 4, "ERA5 1995–2026\n34 pontos", "dados"),
         "ONS": (0, 3, "ONS: balanço, carga (API),\nusinas, cortes", "dados"),
         "ANEEL": (0, 1.6, "ANEEL: SIGA e MMGD", "dados"),
         "PLAN": (0, 0.8, "PLAN 2026–30\ne PDE 2035", "dados"),
         "INV": (0, 0.0, "Inventário de\ndata centers", "dados"),
         "CLI": (1, 4, "Clima ponderado", "dados"),
         "INT": (1, 3, "Base horária integrada\n2022–2026", "dados"),
         "CEN": (1, 0.8, "Cenários 2030", "dados"),
         "TF": (2, 4, "Funções de transferência\nA0, E0, B0, C0", "modelos"),
         "BT": (2, 3, "Backtesting de curto\nprazo: A, B, C", "modelos"),
         "CL": (2, 0.0, "Classificador\nde cortes D", "modelos"),
         "SIN": (3, 4, "Perfis sintéticos de 2030\npara 31 anos", "sim"),
         "MCS": (3, 2.7, "Monte Carlo\n2.000 sorteios", "sim"),
         "DET": (3, 0.8, "Simulador\ndeterminístico", "sim"),
         "RES": (4, 1.75, "Importação, excedente,\ncompensação eólica,\nsensibilidades", "res")}
    fig, ax = plt.subplots(figsize=(13, 6.4))
    moldura(ax, (-0.6, 4.6), (-0.55, 5.0))
    for titulo, x in [("1. Dados: fontes", 0), ("1. Dados: bases", 1), ("2. Modelos", 2), ("3. Simulador 2030", 3), ("4. Resultados", 4)]:
        ax.text(x, 4.72, titulo, ha="center", va="center", fontsize=10, color=INK2, fontweight="bold")
    for a, b in [("ONS", "INT"), ("ERA", "CLI"), ("ANEEL", "CEN"), ("PLAN", "CEN"), ("INV", "CEN"),
                 ("INT", "BT"), ("INT", "TF"), ("CLI", "TF"), ("INT", "CL"), ("TF", "SIN"),
                 ("CEN", "DET"), ("INT", "DET"), ("CEN", "MCS"), ("MCS", "RES"), ("DET", "RES")]:
        seta(ax, p[a][:2], p[b][:2])
    seta(ax, p["SIN"][:2], p["MCS"][:2], vertical=True)
    for x, y, texto, grupo in p.values():
        caixa(ax, x, y, texto, grupo, h=0.72 if texto.count("\n") == 2 else H)
    fig.savefig(FIGURES / "d1_pipeline.png", dpi=140, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def sorteio():
    w = 1.78
    p = {"W": (0, 4, "Sorteia um ano meteorológico\nentre 1995 e 2025", "sorteio"),
         "R": (1.9, 4, "Sorteia blocos de 7 dias de resíduos,\nos 4 juntos, da mesma época do ano", "sorteio"),
         "H": (3.8, 4, "Sorteia um ano hidrológico\nentre 2022 e 2025", "sorteio"),
         "P": (0.95, 2.9, "Perfis sintéticos de 2030:\ncarga, MMGD, CF eólico, CF solar", "modelos"),
         "HT": (3.8, 2.9, "Energia hidráulica diária\ne térmica", "dados"),
         "B": (0.95, 1.8, "Balanço horário de 2030\npara cada cenário", "sim"),
         "HR": (3.8, 1.8, "Regra hidráulica emulada", "sim"),
         "M": (0.95, 0.7, "Métricas do ano: importação,\nhoras, P95, excedente", "res")}
    fig, ax = plt.subplots(figsize=(11, 5.6))
    moldura(ax, (-1.0, 4.8), (0.3, 4.45))
    for a, b in [("W", "P"), ("R", "P"), ("H", "HT"), ("HT", "HR"), ("P", "B"), ("B", "M")]:
        seta(ax, p[a][:2], p[b][:2], w=w, vertical=True)
    (xa, ya), (xb, yb) = p["HR"][:2], p["B"][:2]          # regra hidráulica -> balanço (da direita para a esquerda)
    ax.annotate("", xy=(xb + w / 2, yb), xytext=(xa - w / 2, ya),
                arrowprops=dict(arrowstyle="-|>", color=INK2, lw=1.1, shrinkA=1, shrinkB=1))
    for x, y, texto, grupo in p.values():
        caixa(ax, x, y, texto, grupo, w=w)
    fig.savefig(FIGURES / "d2_sorteio.png", dpi=140, facecolor="white", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    pipeline()
    sorteio()
    print("reports/figures/d1_pipeline.png, d2_sorteio.png")


if __name__ == "__main__":
    main()
