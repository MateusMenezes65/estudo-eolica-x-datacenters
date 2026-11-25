"""Escolha das features das funções de transferência por ablação fora da amostra (decisão 55).

Uso: python -m src.models.ablacao
Saída: reports/models/ablacao_features.csv

Cada variante é RETREINADA sem (ou com) uma feature e avaliada em anos ou blocos longos que não
entraram no treino. É diferente da importância por permutação, que embaralha a feature num modelo já
treinado: uma feature em que o modelo se apoiou por sobreajuste parece importante na permutação e,
mesmo assim, o modelo melhora quando é treinado sem ela (caso do dia do ano em B0 e C0).

Dobras: A0 e E0, um ano fora por vez; B0 e C0, dois blocos (2024-07..2025-06 e 2025-07..2026-10).
B0 e C0 também são avaliados no corte temporal (treino até 2025-12, teste em 2026).
Métrica de A0: erro da forma com média 1 no ano, que é como o simulador a usa (o nível vem do cenário).
Comparação com a especificação anterior: bootstrap pareado da diferença de MSE em blocos de 7 dias
(2.000 reamostras, semente fixa); IC95 que não contém zero = diferença significativa.

Limite: as features foram escolhidas nas mesmas dobras em que o erro é medido, então os ganhos são
ligeiramente otimistas. Uma feature de ruído puro serve de controle.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from src.models.backtest import CAL, HGB, OUT, SEED
from src.sim import sinteticos as sint

W_ANTIGO = ["temperature_2m", "apparent_temperature", "relative_humidity_2m", "cdh24", "shortwave_radiation"]
# especificações usadas até 2026-11-25 (referência da comparação)
ANTERIOR = {"A0": CAL + W_ANTIGO,
            "E0": ["hora", "mes", "dia_ano", "shortwave_radiation_pop", "shortwave_radiation", "temperature_2m"],
            "B0": ["hora", "mes", "dia_ano", "wind_speed_100m", "wind_speed3_100m"],
            "C0": ["hora", "mes", "dia_ano", "shortwave_radiation", "temperature_2m"]}
BLOCOS = [("2024-07-01", "2025-06-30 23:00"), ("2025-07-01", "2026-10-31 23:00")]
DOBRAS = {"A0": [(f"{a}-01-01", f"{a}-12-31 23:00") for a in (2022, 2023, 2024, 2025)],
          "E0": [(f"{a}-01-01", f"{a}-12-31 23:00") for a in (2022, 2023, 2024, 2025, 2026)],
          "B0": BLOCOS, "C0": BLOCOS}
TEMPORAL = ("2026-01-01", "2026-10-31 23:00")


def sem(ex: list[str], *fora: str) -> list[str]:
    return [c for c in ex if c not in fora]


def variantes() -> dict[str, dict[str, list[str]]]:
    P = sint.POLOS_EOL
    v = {n: {"anterior": ex, "adotada": sint.MODELOS[n]["ex"], "anterior + ruído (controle)": ex + ["ruido"]}
         for n, ex in ANTERIOR.items()}
    for f in ["cdh24", "apparent_temperature", "relative_humidity_2m", "shortwave_radiation", "mes", "dia_ano"]:
        v["A0"][f"anterior sem {f}"] = sem(ANTERIOR["A0"], f)
    v["A0"]["anterior sem dia_ano e mes"] = sem(ANTERIOR["A0"], "dia_ano", "mes")
    v["A0"]["anterior sem clima"] = CAL
    v["A0"]["anterior sem feriados menores"] = sem(ANTERIOR["A0"], "n_uf_feriado_estadual", "carnaval", "sao_joao", "ponte",
                                                    "vespera_feriado", "pos_feriado")
    v["A0"]["adotada sem temp_mm24"] = sem(sint.MODELOS["A0"]["ex"], "temp_mm24")
    v["A0"]["adotada + dia_ano"] = sint.MODELOS["A0"]["ex"] + ["dia_ano"]
    v["A0"]["adotada sem temperature_2m"] = sem(sint.MODELOS["A0"]["ex"], "temperature_2m")
    v["A0"]["adotada sem ponto_facultativo"] = sem(sint.MODELOS["A0"]["ex"], "ponto_facultativo")
    for f in ["dia_ano", "mes", "temperature_2m", "shortwave_radiation", "shortwave_radiation_pop"]:
        v["E0"][f"anterior sem {f}"] = sem(ANTERIOR["E0"], f)
    v["E0"]["adotada sem mes"] = sem(sint.MODELOS["E0"]["ex"], "mes")
    v["E0"]["adotada + temperature_2m"] = sint.MODELOS["E0"]["ex"] + ["temperature_2m"]
    for f in ["dia_ano", "mes", "hora", "wind_speed_100m", "wind_speed3_100m"]:
        v["B0"][f"anterior sem {f}"] = sem(ANTERIOR["B0"], f)
    v["B0"]["hora, mês, vento médio"] = ["hora", "mes", "wind_speed_100m"]
    v["B0"]["anterior + 16 polos"] = ANTERIOR["B0"] + P
    v["B0"]["adotada sem mes"] = sem(sint.MODELOS["B0"]["ex"], "mes")
    for f in ["dia_ano", "mes", "hora", "temperature_2m"]:
        v["C0"][f"anterior sem {f}"] = sem(ANTERIOR["C0"], f)
    v["C0"]["adotada sem temperature_2m"] = sem(sint.MODELOS["C0"]["ex"], "temperature_2m")
    return v


def prever(D: pd.DataFrame, nome: str, ex: list[str], dobras) -> np.ndarray:
    y = D[sint.MODELOS[nome]["alvo"]].to_numpy()
    p = np.full(len(D), np.nan)
    for a, b in dobras:
        te = D.t.between(a, b).to_numpy()
        p[te] = HistGradientBoostingRegressor(**HGB).fit(D.loc[~te, ex], y[~te]).predict(D.loc[te, ex])
    if nome == "A0":                                     # o simulador usa a forma com média 1 no ano
        p = p / pd.Series(p).groupby(D.ano.to_numpy()).transform("mean").to_numpy()
    return p


def ic_blocos(dif: np.ndarray, t: pd.Series, n: int = 2000) -> tuple[float, float]:
    """IC95 da média de `dif` por bootstrap em blocos de 7 dias."""
    bl = ((t - t.min()).dt.days // 7).to_numpy()
    g = pd.Series(dif).groupby(bl).agg(["sum", "size"]).to_numpy()
    rng = np.random.default_rng(SEED)
    i = rng.integers(0, len(g), (n, len(g)))
    m = g[i, 0].sum(axis=1) / g[i, 1].sum(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


def main() -> None:
    D0 = sint.dados_treino()
    D0["ruido"] = np.random.default_rng(SEED).normal(size=len(D0))
    rows = []
    for nome, V in variantes().items():
        m = sint.MODELOS[nome]
        D = D0[D0.t.between(*m["treino"]) & D0[m["alvo"]].notna()].reset_index(drop=True)
        y = D[m["alvo"]].to_numpy()
        esquemas = [("anos ou blocos fora", DOBRAS[nome])]
        if nome in ("B0", "C0"):
            esquemas.append(("temporal (teste 2026)", [TEMPORAL]))
        for esq, dobras in esquemas:
            e0 = None
            for rotulo, ex in V.items():
                p = prever(D, nome, ex, dobras)
                ok = ~np.isnan(p)
                e = (p - y)[ok] ** 2
                if e0 is None:
                    e0 = e
                lo, hi = ic_blocos(e - e0, D.t[ok].reset_index(drop=True)) if rotulo != "anterior" else (np.nan, np.nan)
                rows.append({"modelo": nome, "validacao": esq, "variante": rotulo, "n_features": len(ex), "n": int(ok.sum()),
                             "MAE": float(np.abs((p - y)[ok]).mean()), "RMSE": float(np.sqrt(e.mean())),
                             "vies": float((p - y)[ok].mean()),
                             "dif_RMSE_%": float(100 * (np.sqrt(e.mean()) / np.sqrt(e0.mean()) - 1)),
                             "dif_MSE_ic95_inf": lo, "dif_MSE_ic95_sup": hi,
                             "significativa": "" if np.isnan(lo) else ("melhor" if hi < 0 else "pior" if lo > 0 else "não")})
        print(f"{nome}: {len(V)} variantes", flush=True)
    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / "ablacao_features.csv", index=False, float_format="%.8g")
    print(R.drop(columns=["dif_MSE_ic95_inf", "dif_MSE_ic95_sup"]).round(4).to_string())


if __name__ == "__main__":
    main()
