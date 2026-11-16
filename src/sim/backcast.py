"""Validação retrospectiva do simulador do Monte Carlo contra a importação observada.

Uso: python -m src.sim.backcast [--n 300]
Pré-requisitos: src.sim.sinteticos (perfis, resíduos, pool hidrotérmico).
Saídas: reports/mc/mc_backcast.csv e reports/figures/mc4_backcast.png

Pergunta: alimentado com os NÍVEIS observados de um ano passado, o simulador reproduz a
importação que o NE realmente teve? Para cada ano y de 2022–2025:
- clima e ano hidrotérmico fixos em y; só os blocos de resíduos são sorteados;
- carga bruta = carga líquida coerente com o balanço do ONS (geração − intercâmbio) + MMGD;
- energia eólica e solar = energia POTENCIAL observada em y (geração + GNRa), levada à frota
  inteira pela razão balanço / usinas com fator de capacidade; a capacidade efetiva é a que faz
  o CF simulado médio devolver essa energia. Os níveis anuais são, portanto, os observados;
- o que se testa são as FORMAS horárias (funções de transferência + resíduos) e a convenção
  hidráulica: a regra emulada (caso central) e o despacho hidráulico observado no próprio ano.
A térmica é a observada em y nas duas convenções.

O simulador usa a geração potencial. Cortes eólicos que ocorreram em horas de importação
(restrições de rede) aumentam a importação observada e não são representados; a tabela traz
esse corte para leitura do erro. Não é um teste dos cenários de 2030.
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.paths import FIGURES, PROCESSED, REPORTS
from src.sim import montecarlo as mc
from src.sim.deterministico import load_cfg

OUT = REPORTS / "mc"
CONVENCOES = {"regra_historica": "regra emulada (caso central)",
              "historico_sorteado": "despacho hidráulico observado no ano"}


def niveis_observados(g: pd.DataFrame) -> dict:
    """Níveis anuais observados de um ano (MWmed) e métricas da importação observada."""
    fr_e = g.eol_bal.mean() / g.ger_eol_fc.mean()        # frota inteira / usinas com FC
    fr_s = g.sol_central.mean() / g.ger_sol_fc.mean()
    l_net_bal = (g.hid + g.ter + g.eol_bal + g.sol_central - g.interc).mean()
    imp = (-g.interc).clip(lower=0)
    em_imp = g.interc < 0
    corte = (g.pot_eol_fc - g.ger_eol_fc) * fr_e
    return {"L_gross": l_net_bal + g.MMGD.mean(), "MMGD": g.MMGD.mean(),
            "eol_pot": g.pot_eol_fc.mean() * fr_e, "sol_pot": g.pot_sol_fc.mean() * fr_s,
            "obs_TWh": imp.sum() / 1e6, "obs_horas": int(em_imp.sum()),
            "obs_p95_MW": float(np.percentile(imp, 95)), "obs_pico_MW": float(imp.max()),
            "corte_eol_em_horas_de_importacao_TWh": float(corte[em_imp].sum() / 1e6)}


def simular_ano(ins, c, X: pd.DataFrame, ano: int, n: int, semente: int = mc.SEMENTE) -> list[dict]:
    nv = niveis_observados(X[X.ano == ano])
    sd = mc.sortear(ins, n, 7, semente)
    sd["w"] = np.full(n, int(np.flatnonzero(ins.anos == ano)[0]))
    sd["h"] = np.full(n, int(np.flatnonzero(ins.anos_h == ano)[0]))
    k = mc.componentes(ins, sd, np.arange(n), c, {"L_gross": nv["L_gross"], "MMGD": nv["MMGD"]})
    cap_e = nv["eol_pot"] / k["cfe"].mean()
    cap_s = nv["sol_pot"] / k["cfs"].mean()
    base = k["ter"] + k["cfs"] * cap_s + k["cfe"] * cap_e - (k["L"] - k["MMGD"])
    rows = []
    for modo, rotulo in CONVENCOES.items():
        M = base + mc.hidraulica(ins, k["h"], -base, modo)
        imp = np.clip(-M, 0, None)
        twh = imp.sum(1) / 1e6
        rows.append({"ano": ano, "convencao": rotulo, "obs_TWh": nv["obs_TWh"], "sim_TWh": twh.mean(),
                     "sim_TWh_p5": np.percentile(twh, 5), "sim_TWh_p95": np.percentile(twh, 95),
                     "erro_%": 100 * (twh.mean() / nv["obs_TWh"] - 1),
                     "obs_horas": nv["obs_horas"], "sim_horas": (M < 0).sum(1).mean(),
                     "obs_p95_MW": nv["obs_p95_MW"], "sim_p95_MW": np.percentile(imp, 95, axis=1).mean(),
                     "obs_pico_MW": nv["obs_pico_MW"], "sim_pico_MW": imp.max(1).mean(),
                     "corte_eol_em_horas_de_importacao_TWh": nv["corte_eol_em_horas_de_importacao_TWh"],
                     "cap_eol_efetiva_MW": cap_e, "cap_sol_efetiva_MW": cap_s, "n_sorteios": n})
    return rows


def figura(B: pd.DataFrame) -> None:
    anos = sorted(B.ano.unique())
    x = np.arange(len(anos))
    fig, ax = plt.subplots(figsize=(8.5, 4))
    obs = B.drop_duplicates("ano").set_index("ano").obs_TWh.reindex(anos)
    ax.bar(x - 0.27, obs, width=0.25, color="#52514e", label="observado")
    for i, (rotulo, cor) in enumerate(zip(CONVENCOES.values(), ["#2a78d6", "#eb6834"])):
        g = B[B.convencao == rotulo].set_index("ano").reindex(anos)
        ax.bar(x + i * 0.27, g.sim_TWh, width=0.25, color=cor, label=f"simulado: {rotulo}")
        ax.errorbar(x + i * 0.27, g.sim_TWh, yerr=[g.sim_TWh - g.sim_TWh_p5, g.sim_TWh_p95 - g.sim_TWh],
                    fmt="none", ecolor="#0b0b0b", lw=1)
    ax.set_xticks(x, [str(a) for a in anos])
    ax.set_ylabel("importação anual (TWh)", fontsize=9, color="#52514e")
    ax.set_title("Validação retrospectiva: importação observada × simulada com os níveis do próprio ano",
                 loc="left", fontsize=10)
    ax.grid(axis="y", color="#e4e3df"); ax.set_axisbelow(True)
    [ax.spines[k].set_visible(False) for k in ["top", "right"]]
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout(); fig.savefig(FIGURES / "mc4_backcast.png", dpi=130); plt.close(fig)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    c, _ = load_cfg()
    ins = mc.Insumos()
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    rows = []
    for ano in [int(y) for y in ins.anos_h]:
        rows += simular_ano(ins, c, X, ano, a.n)
    B = pd.DataFrame(rows)
    B.round(3).to_csv(OUT / "mc_backcast.csv", index=False)
    figura(B)
    print(B[["ano", "convencao", "obs_TWh", "sim_TWh", "sim_TWh_p5", "sim_TWh_p95", "erro_%", "obs_horas",
             "sim_horas", "obs_pico_MW", "sim_pico_MW", "corte_eol_em_horas_de_importacao_TWh"]].round(2).to_string())
    print(B.groupby("convencao", sort=False)["erro_%"].agg(["mean", "min", "max"]).round(1).to_string())


if __name__ == "__main__":
    main()
