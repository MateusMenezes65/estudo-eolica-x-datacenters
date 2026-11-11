"""Modelo D — viabilidade de um classificador horário de cortes eólicos no NE.

Uso: python -m src.models.cortes
Saídas: reports/models/cortes_metricas.csv, cortes_calibracao.csv

Rótulo (hora t): GNRa eólica apurada no NE, por motivo (ENE, CNF, REL) e total,
acima de 1% da capacidade eólica vigente (≈ 200–320 MW).
Features só ex-ante (regra 13): potencial eólico e solar "previstos" (CF potencial ×
capacidade — clima perfeito, logo limite superior), carga bruta e MMGD, excedente bruto
previsto = eólica + solar + MMGD − carga, capacidades instaladas e calendário.
Nunca entram intercâmbio, despacho hidrotérmico ou corte observados no mesmo instante.
Validação temporal com dois cortes (há mudança de regime 2024–2025, regra 15).
Interpretação NÃO causal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score, roc_auc_score

from src.models.backtest import SEED
from src.paths import INTERIM, PROCESSED, REPORTS

OUT = REPORTS / "models"
CORTES = [("2023-01-01", "2024-12-31 23:00", "2025-01-01", "2025-12-31 23:00"),
          ("2024-07-01", "2025-12-31 23:00", "2026-01-01", "2026-10-31 23:00")]


def dataset() -> pd.DataFrame:
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet").set_index("t")
    H = pd.read_parquet(INTERIM / "ne_hourly.parquet").set_index("t")
    D = pd.DataFrame(index=X.index)
    D["pot_eol"] = X.cf_eol_pot * X.cap_eol
    D["pot_sol"] = X.cf_sol_pot.fillna(X.cf_sol_obs) * X.cap_sol
    D["L_gross"] = X.L_gross
    D["MMGD"] = X.MMGD
    D["exc_bruto_prev"] = D.pot_eol + D.pot_sol + D.MMGD - D.L_gross
    D["cap_eol"] = X.cap_eol
    D["cap_sol"] = X.cap_sol
    for c in ["hora", "dia_semana", "mes", "feriado_nacional", "ponte"]:
        D[c] = X[c]
    lim = 0.01 * X.cap_eol
    for r in ["ene", "cnf", "rel"]:
        D[f"y_{r}"] = (H[f"coff_eol_gnr_{r}"].fillna(0) > lim).astype(int)
    D["y_total"] = (H.coff_eol_geracaonaorealizadaapurada.fillna(0) > lim).astype(int)
    return D[D.index < "2026-11-01"].dropna(subset=["pot_eol", "L_gross"])


def main() -> None:
    D = dataset()
    feats = [c for c in D.columns if not c.startswith("y_")]
    rows, cal = [], []
    taxa = D.filter(like="y_").groupby(D.index.year).mean().round(3)
    for alvo in ["y_ene", "y_cnf", "y_rel", "y_total"]:
        for tr0, tr1, te0, te1 in CORTES:
            tr, te = D.loc[tr0:tr1], D.loc[te0:te1]
            if tr[alvo].sum() < 50 or te[alvo].sum() < 20:
                rows.append({"alvo": alvo, "treino": f"{tr0[:7]}..{tr1[:7]}", "teste": f"{te0[:7]}..{te1[:7]}",
                             "nota": "eventos insuficientes"})
                continue
            m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                               min_samples_leaf=40, random_state=SEED).fit(tr[feats], tr[alvo])
            p = m.predict_proba(te[feats])[:, 1]
            y = te[alvo].values
            base = np.full_like(p, tr[alvo].mean(), dtype=float)
            rows.append({"alvo": alvo, "treino": f"{tr0[:7]}..{tr1[:7]}", "teste": f"{te0[:7]}..{te1[:7]}",
                         "taxa_treino": tr[alvo].mean(), "taxa_teste": y.mean(),
                         "PR_AUC": average_precision_score(y, p), "PR_AUC_aleatorio": y.mean(),
                         "ROC_AUC": roc_auc_score(y, p), "Brier": brier_score_loss(y, p),
                         "Brier_climatologia_treino": brier_score_loss(y, base),
                         "precisao@0.5": precision_score(y, p > 0.5, zero_division=0),
                         "revocacao@0.5": recall_score(y, p > 0.5, zero_division=0),
                         "prob_media_prevista": p.mean()})
            b = pd.cut(p, [0, .1, .2, .4, .6, .8, 1], include_lowest=True)
            cal.append(pd.DataFrame({"alvo": alvo, "teste": f"{te0[:7]}..{te1[:7]}", "faixa": b, "y": y, "p": p})
                       .groupby(["alvo", "teste", "faixa"], observed=True).agg(n=("y", "size"), freq_obs=("y", "mean"), p_med=("p", "mean")).reset_index())
    R = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    R.to_csv(OUT / "cortes_metricas.csv", index=False)
    pd.concat(cal).to_csv(OUT / "cortes_calibracao.csv", index=False)
    taxa.to_csv(OUT / "cortes_taxa_eventos_ano.csv")
    print("taxa de horas com corte > 1% da capacidade, por ano:"); print(taxa.to_string())
    print(R.round(3).to_string())


if __name__ == "__main__":
    main()
