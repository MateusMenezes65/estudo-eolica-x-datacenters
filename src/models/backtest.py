"""Modelos A (carga líquida), B (CF eólico potencial) e C (CF solar) com backtesting temporal.

Uso: python -m src.models.backtest
Saídas: reports/models/metricas_*.csv, reports/models/backtest.md, reports/figures/m*.png

Dois papéis (AGENTS.md, "Papel dos modelos"):
1. Curto prazo (validação acadêmica): horizontes h = 1 h e 24 h. Origem da previsão
   em t−h; lags e médias móveis do alvo usam só valores até t−h. O clima ERA5 no
   instante-alvo é tratado como previsão perfeita → resultados são LIMITE SUPERIOR
   de desempenho frente a uma previsão meteorológica operacional.
2. Função de transferência clima → sistema (sem lags do alvo): usada para gerar
   perfis horários de anos meteorológicos. Avaliada por validação deixando um ano fora
   (carga) e por validação temporal recente (eólica/solar, por mudança de frota).

Backtesting: origem móvel, 12 dobras mensais em 2025; treino = todo o histórico
anterior ao início do mês testado (janela expansível). Transformações ajustadas só no
treino (árvores não exigem escala). Modelo principal: HistGradientBoostingRegressor
(sklearn), hiperparâmetros fixos (sem busca), semente fixa.
"""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from src.paths import FIGURES, PROCESSED, REPORTS, rel

SEED = 20261111
OUT = REPORTS / "models"
HGB = dict(max_iter=400, learning_rate=0.05, max_leaf_nodes=31, min_samples_leaf=40,
           l2_regularization=1.0, random_state=SEED)

CAL = ["hora", "dia_semana", "mes", "dia_ano", "feriado_nacional", "n_uf_feriado_estadual",
       "ponto_facultativo", "carnaval", "sao_joao", "ponte", "vespera_feriado", "pos_feriado"]
TARGETS = {
    "A_carga_liquida": dict(y="L_net", exog=CAL + ["temperature_2m", "apparent_temperature",
                                                     "relative_humidity_2m", "cdh24", "shortwave_radiation"],
                            unidade="MW"),
    "B_cf_eolico_pot": dict(y="cf_eol_pot", exog=["hora", "mes", "dia_ano", "wind_speed_100m",
                                                   "wind_speed3_100m"], unidade="CF"),
    "C_cf_solar": dict(y="cf_sol_obs", exog=["hora", "mes", "dia_ano", "shortwave_radiation",
                                             "temperature_2m"], unidade="CF"),
}


def lag_features(y: pd.Series, h: int) -> pd.DataFrame:
    """Lags e janelas móveis do alvo conhecidos na origem t−h (sem vazamento)."""
    base = y.shift(h)  # último valor observado na origem
    f = pd.DataFrame(index=y.index)
    for k in sorted({h, h + 1, h + 2, 24 if h <= 24 else h, 48, 168}):
        if k >= h:
            f[f"lag_{k}"] = y.shift(k)
    f["mm24_orig"] = base.rolling(24, min_periods=20).mean()
    f["mm168_orig"] = base.rolling(168, min_periods=150).mean()
    f["dp24_orig"] = base.rolling(24, min_periods=20).std()
    return f


def baselines(y: pd.Series, h: int) -> dict[str, pd.Series]:
    b = {"sazonal_semanal": y.shift(168)}       # baseline sazonal obrigatório
    b[f"persistencia_{h}h"] = y.shift(h)
    if h < 24:
        b["sazonal_diario"] = y.shift(24)
    return b


def metrics(y, p) -> dict:
    m = y.notna() & p.notna()
    e = (p[m] - y[m])
    return {"n": int(m.sum()), "MAE": float(e.abs().mean()), "RMSE": float(np.sqrt((e ** 2).mean()))}


def backtest_short(X: pd.DataFrame, name: str, spec: dict, h: int, months) -> tuple[pd.DataFrame, pd.DataFrame]:
    y = X[spec["y"]]
    F = pd.concat([X[spec["exog"]], lag_features(y, h)], axis=1)
    B = baselines(y, h)
    rows, preds = [], []
    for m0 in months:
        m1 = m0 + pd.offsets.MonthBegin(1)
        tr = (X.t < m0) & y.notna()
        te = (X.t >= m0) & (X.t < m1) & y.notna()
        if te.sum() == 0:
            continue
        mdl = HistGradientBoostingRegressor(**HGB).fit(F[tr], y[tr])
        p = pd.Series(mdl.predict(F[te]), index=y[te].index)
        rows.append({"alvo": name, "h": h, "mes": m0.strftime("%Y-%m"), "metodo": "HGB", **metrics(y[te], p)})
        for bn, bs in B.items():
            rows.append({"alvo": name, "h": h, "mes": m0.strftime("%Y-%m"), "metodo": bn, **metrics(y[te], bs[te])})
        preds.append(pd.DataFrame({"t": X.t[te], "y": y[te], "hgb": p, **{bn: bs[te] for bn, bs in B.items()}}))
    return pd.DataFrame(rows), pd.concat(preds)


def transfer_eval(X: pd.DataFrame) -> pd.DataFrame:
    """Avalia as funções de transferência clima → sistema (sem lags do alvo)."""
    rows = []
    # A0: carga normalizada pelo nível médio do ano (o nível vem dos cenários).
    # Avaliada para a carga BRUTA (forma estável; MMGD tratada à parte) e para a líquida.
    exA = TARGETS["A_carga_liquida"]["exog"]
    for alvo in ["L_gross", "L_net"]:
      yA = X[alvo] / X.groupby("ano")[alvo].transform("mean")
      for ano in [2022, 2023, 2024, 2025]:
        tr = (X.ano != ano) & (X.ano <= 2025) & yA.notna()
        te = (X.ano == ano) & yA.notna()
        mdl = HistGradientBoostingRegressor(**HGB).fit(X.loc[tr, exA], yA[tr])
        p = pd.Series(mdl.predict(X.loc[te, exA]), index=yA[te].index)
        clim = yA[tr].groupby([X.mes[tr], X.dia_semana[tr], X.hora[tr]]).mean()
        pc = pd.Series(clim.reindex(pd.MultiIndex.from_arrays([X.mes[te], X.dia_semana[te], X.hora[te]])).values,
                       index=yA[te].index)
        nm = f"A0 {alvo}/nível anual"
        rows.append({"modelo": nm, "validacao": f"ano fora={ano}", "metodo": "HGB", "vies": float((p - yA[te]).mean()), **metrics(yA[te], p)})
        rows.append({"modelo": nm, "validacao": f"ano fora={ano}", "metodo": "perfil mes×dia×hora", "vies": float((pc - yA[te]).mean()), **metrics(yA[te], pc)})
    # B0/C0: frota muda no tempo → validação temporal em dois cortes
    cortes = {"B0 CF eólico pot": [("2022-01-01", "2024-12-31 23:00", "2025-01-01", "2025-12-31 23:00"),
                                   ("2024-07-01", "2025-12-31 23:00", "2026-01-01", "2026-10-31 23:00")],
              "C0 CF solar pot": [("2024-04-01", "2025-06-30 23:00", "2025-07-01", "2025-12-31 23:00"),
                                  ("2024-07-01", "2025-12-31 23:00", "2026-01-01", "2026-10-31 23:00")]}
    exC = TARGETS["C_cf_solar"]["exog"] + ["cloud_cover"] if "cloud_cover" in X else TARGETS["C_cf_solar"]["exog"]
    for nome, ycol, ex in [("B0 CF eólico pot", "cf_eol_pot", TARGETS["B_cf_eolico_pot"]["exog"]),
                           ("C0 CF solar pot", "cf_sol_pot", exC)]:
        y = X[ycol]
        for tr_ini, tr_fim, te_ini, te_fim in cortes[nome]:
            tr = X.t.between(tr_ini, tr_fim) & y.notna()
            te = X.t.between(te_ini, te_fim) & y.notna()
            mdl = HistGradientBoostingRegressor(**HGB).fit(X.loc[tr, ex], y[tr])
            p = pd.Series(mdl.predict(X.loc[te, ex]), index=y[te].index)
            clim = y[tr].groupby([X.mes[tr], X.hora[tr]]).mean()
            pc = pd.Series(clim.reindex(pd.MultiIndex.from_arrays([X.mes[te], X.hora[te]])).values, index=y[te].index)
            v = f"treino {tr_ini[:7]}..{tr_fim[:7]} / teste {te_ini[:7]}..{te_fim[:7]}"
            rows.append({"modelo": nome, "validacao": v, "metodo": "HGB", "vies": float((p - y[te]).mean()), **metrics(y[te], p)})
            rows.append({"modelo": nome, "validacao": v, "metodo": "perfil mes×hora", "vies": float((pc - y[te]).mean()), **metrics(y[te], pc)})
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--so-transferencia", action="store_true")
    a = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    X = X[X.t < "2026-11-01"].reset_index(drop=True)  # mês corrente é preliminar
    if a.so_transferencia:
        T = transfer_eval(X)
        T.to_csv(OUT / "metricas_funcao_transferencia.csv", index=False)
        print(T.round(4).to_string())
        return
    months = pd.date_range("2025-01-01", "2025-12-01", freq="MS")
    allm, keep = [], {}
    for name, spec in TARGETS.items():
        for h in (1, 24):
            m, p = backtest_short(X, name, spec, h, months)
            allm.append(m)
            keep[(name, h)] = p
            print(f"{name} h={h}: ok")
    M = pd.concat(allm)
    M.to_csv(OUT / "metricas_curto_prazo_mensal.csv", index=False)
    agg = (M.assign(SE=M.RMSE ** 2 * M.n, AE=M.MAE * M.n)
           .groupby(["alvo", "h", "metodo"]).agg(n=("n", "sum"), AE=("AE", "sum"), SE=("SE", "sum")))
    agg["MAE"] = agg.AE / agg.n
    agg["RMSE"] = np.sqrt(agg.SE / agg.n)
    agg = agg[["n", "MAE", "RMSE"]].reset_index()
    best_base = agg[agg.metodo != "HGB"].sort_values("MAE").groupby(["alvo", "h"]).first()
    hgb = agg[agg.metodo == "HGB"].set_index(["alvo", "h"])
    agg_cmp = hgb.drop(columns="metodo").join(best_base[["metodo", "MAE", "RMSE"]].add_suffix("_melhor_baseline"))
    agg_cmp["ganho_MAE_%"] = 100 * (1 - agg_cmp.MAE / agg_cmp.MAE_melhor_baseline)
    # consistência: em quantos meses o HGB vence o melhor baseline (MAE)?
    wins = []
    for (a, h), g in M.groupby(["alvo", "h"]):
        bb = best_base.loc[(a, h), "metodo"]
        piv = g.pivot_table(index="mes", columns="metodo", values="MAE")
        wins.append({"alvo": a, "h": h, "meses_HGB_melhor": int((piv["HGB"] < piv[bb]).sum()), "meses": len(piv)})
    agg_cmp = agg_cmp.reset_index().merge(pd.DataFrame(wins), on=["alvo", "h"])
    agg.to_csv(OUT / "metricas_curto_prazo_2025.csv", index=False)
    agg_cmp.to_csv(OUT / "comparacao_hgb_baseline.csv", index=False)
    T = transfer_eval(X)
    T.to_csv(OUT / "metricas_funcao_transferencia.csv", index=False)

    # figura: uma semana de 2025 para cada alvo, h=24
    fig, axes = plt.subplots(3, 1, figsize=(10, 9))
    for ax, (name, spec) in zip(axes, TARGETS.items()):
        p = keep[(name, 24)]
        w = p[(p.t >= "2025-09-08") & (p.t < "2025-09-15")]
        ax.plot(w.t, w.y, color="#0b0b0b", lw=2, label="observado")
        ax.plot(w.t, w.hgb, color="#2a78d6", lw=2, label="HGB (h=24)")
        ax.plot(w.t, w.sazonal_semanal, color="#eb6834", lw=1.5, ls="--", label="sazonal semanal")
        ax.set_title(f"{name} — semana de 08/09/2025", loc="left", fontsize=10)
        ax.grid(axis="y", color="#e4e3df"); [ax.spines[s].set_visible(False) for s in ["top", "right"]]
    axes[0].legend(frameon=False, fontsize=8, ncol=3)
    fig.tight_layout(); fig.savefig(FIGURES / "m1_backtest_semana.png", dpi=130); plt.close(fig)

    with open(OUT / "backtest_config.json", "w", encoding="utf-8") as f:
        json.dump({"seed": SEED, "hgb": HGB, "dobras": [m.strftime("%Y-%m") for m in months],
                   "targets": TARGETS}, f, ensure_ascii=False, indent=1)
    print(agg_cmp.round(4).to_string())
    print(T.round(4).to_string())


if __name__ == "__main__":
    main()
