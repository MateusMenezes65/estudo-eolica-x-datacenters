"""Base analítica horária do NE (data/processed/ne_features_h.parquet).

Uso: python -m src.features.build   (requer python -m src.build.ne_hourly)

Definições (docs/decisoes.md):
- L_net  = carga global líquida de MMGD (API ONS, val_cargaglobalsmmgd)   [decisão 13]
- MMGD   = carga atendida por MMGD (API ONS, val_cargammgd)
- L_gross = L_net + MMGD (= carga global; conceito do PDE)
- CF eólico/solar por usina (FC ONS), somente usinas com capacidade > 0  [decisão 17]
  * cf_*_obs = Σ geração verificada / Σ capacidade
  * cf_*_pot = Σ (geração verificada + GNRa apurada) / Σ capacidade      [decisão 14]
    (solar: GNRa só existe desde 2024-04; antes disso cf_sol_pot = NaN)
- Geração centralizada do balanço: hid, ter, eol, sol_central = bal_sol − MMGD (geração por usina)
- Clima ERA5 ponderado (população para temperatura; capacidade vigente para vento/irradiância)
- Calendário: config/calendario_ne.csv
Sem imputação: horas sem dado ficam NaN; `anomalia_balanco` marca as horas em que o
balanço ONS não fecha (|G−L−I| > 50 MW, jan–mai/2026).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.paths import CONFIG, INTERIM, PROCESSED


def cf_tables() -> pd.DataFrame:
    fc = pd.read_parquet(INTERIM / "ne_fc_usina_h.parquet",
                         columns=["t", "id_ons", "fonte", "val_geracaoverificada", "val_capacidadeinstalada"])
    fc = fc[fc.val_capacidadeinstalada > 0]
    out = []
    for s, f in [("eol", "EOL"), ("sol", "SOL")]:
        a = fc[fc.fonte == f]
        c = pd.read_parquet(INTERIM / f"ne_coff_{s}_usina_h.parquet",
                            columns=["t", "id_ons", "val_geracaonaorealizadaapurada"])
        m = a.merge(c, on=["id_ons", "t"], how="left")
        coff_ini = c.t.min()
        m["pot"] = m.val_geracaoverificada + m.val_geracaonaorealizadaapurada.fillna(0)
        g = m.groupby("t")
        d = pd.DataFrame({
            f"cap_{s}": g.val_capacidadeinstalada.sum(),
            f"ger_{s}_fc": g.val_geracaoverificada.sum(),
            f"pot_{s}_fc": g.pot.sum(),
            f"n_usinas_{s}": g.size(),
        })
        d[f"cf_{s}_obs"] = d[f"ger_{s}_fc"] / d[f"cap_{s}"]
        d[f"cf_{s}_pot"] = (d[f"pot_{s}_fc"] / d[f"cap_{s}"]).where(d.index >= coff_ini)
        out.append(d)
    return pd.concat(out, axis=1)


def calendar_features(t: pd.Series) -> pd.DataFrame:
    cal = pd.read_csv(CONFIG / "calendario_ne.csv", parse_dates=["data"]).set_index("data")
    day = t.dt.normalize()
    f = pd.DataFrame(index=t.index)
    f["hora"] = t.dt.hour
    f["dia_semana"] = t.dt.day_of_week
    f["mes"] = t.dt.month
    f["ano"] = t.dt.year
    f["dia_ano"] = t.dt.day_of_year
    for c in ["feriado_nacional", "n_uf_feriado_estadual", "ponto_facultativo", "carnaval",
              "sao_joao", "ponte", "vespera_feriado", "pos_feriado"]:
        f[c] = day.map(cal[c]).astype("float")
    return f


def main() -> None:
    H = pd.read_parquet(INTERIM / "ne_hourly.parquet").set_index("t")
    X = pd.DataFrame(index=H.index)
    X["L_net"] = H.api_cargaglobalsmmgd
    X["MMGD"] = H.api_cargammgd
    X["L_gross"] = H.api_cargaglobal
    X["hid"] = H.bal_hid
    X["ter"] = H.bal_ter
    X["eol_bal"] = H.bal_eol
    X["mmgd_usina"] = H.gu_sol_mmgd.fillna(0).where(H.bal_sol.notna())
    X["sol_central"] = H.bal_sol - X.mmgd_usina
    X["interc"] = H.bal_interc  # > 0 = exportação do NE
    G = H[["bal_hid", "bal_ter", "bal_eol", "bal_sol"]].sum(axis=1, min_count=4)
    X["anomalia_balanco"] = ((G - H.bal_carga - H.bal_interc).abs() > 50).astype(int)
    X = X.join(cf_tables(), how="left")
    for c in ["w_temperature_2m_pop", "w_apparent_temperature_pop", "w_relative_humidity_2m_pop",
              "w_wind_speed_100m_cap", "w_wind_speed3_100m_cap", "w_shortwave_radiation_cap"]:
        X[c.replace("w_", "").replace("_cap", "").replace("_pop", "")] = H[c]
    X["cdh24"] = (X.temperature_2m - 24).clip(lower=0)  # graus-hora de resfriamento (base 24 °C)
    X = X.reset_index()
    X = pd.concat([X, calendar_features(X.t)], axis=1)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    X.to_parquet(PROCESSED / "ne_features_h.parquet")
    print(X.shape, X.t.min(), X.t.max())
    print(X.groupby("ano")[["L_net", "MMGD", "cf_eol_obs", "cf_eol_pot", "cf_sol_obs", "cf_sol_pot"]].mean().round(3).to_string())


if __name__ == "__main__":
    main()
