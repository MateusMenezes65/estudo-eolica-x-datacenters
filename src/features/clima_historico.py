"""Clima ERA5 ponderado do NE, 1995–2026, com pesos FIXOS da frota atual.

Uso: python -m src.features.clima_historico
Saída: data/processed/clima_ne_1995_2026.parquet (t = início da hora, Brasília)

Diferente de ne_features_h (pesos pela capacidade vigente em cada hora), aqui os pesos
são fixos para que todos os anos meteorológicos representem a MESMA população de usinas
(a frota de out/2026) — requisito das funções de transferência (AGENTS.md, papel 2):
- vento a 100 m e irradiância nos polos: capacidade média de out/2026 de cada usina/conjunto
  do FC ONS, atribuída ao ponto ERA5 mais próximo (mesma regra de src.build.ne_hourly);
- temperatura, umidade e irradiância nas capitais: população das UFs (Censo 2022).

Colunas usadas pelas funções de transferência (decisão 55): `ws_<polo>` = vento a 100 m de cada um dos
16 polos eólicos, sem média espacial; `temp_mm24` = média da temperatura ponderada nas 24 h até a hora t.
"""
from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd

from src.build.ne_hourly import nearest_point
from src.ingest import weather
from src.paths import CONFIG, INTERIM, PROCESSED, RAW

VARS_OUT = ["temperature_2m", "apparent_temperature", "relative_humidity_2m", "shortwave_radiation_pop",
            "wind_speed_100m", "wind_speed3_100m", "shortwave_radiation"]


def read_point_full(pid: str) -> pd.DataFrame:
    parts = []
    for f in sorted((RAW / "openmeteo" / "hist").glob(f"{pid}_*.json.gz")) + [RAW / "openmeteo" / f"{pid}.json.gz"]:
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            j = json.load(fh)
        d = pd.DataFrame(j["hourly"])
        d["t_utc"] = pd.to_datetime(d.pop("time"))
        parts.append(d.set_index("t_utc"))
    d = pd.concat(parts).sort_index()
    d = d[~d.index.duplicated()]
    full = pd.date_range(d.index.min(), d.index.max(), freq="h")
    assert len(full) == len(d), f"{pid}: série com lacunas"
    return d


def fixed_weights() -> dict[str, pd.Series]:
    pts = weather.points()
    fc = pd.read_parquet(INTERIM / "ne_fc_usina_h.parquet")
    fc = fc[(fc.t >= "2026-10-01") & (fc.t < "2026-11-01") & (fc.val_capacidadeinstalada > 0)]
    w = {}
    for fonte, kind in [("EOL", "wind"), ("SOL", "solar")]:
        u = fc[fc.fonte == fonte].groupby("id_ons").agg(lat=("val_latitudesecoletora", "first"),
                                                         lon=("val_longitudesecoletora", "first"),
                                                         cap=("val_capacidadeinstalada", "mean")).dropna()
        P = pts[pts.kind == kind]
        u["point_id"] = nearest_point(u.lat.values, u.lon.values, P)
        w[kind] = u.groupby("point_id").cap.sum()
    pop = pd.read_csv(CONFIG / "pop_uf_ne.csv").set_index("uf").peso
    caps = pts[pts.kind == "capital"]
    w["capital"] = pd.Series(pop[caps.uf].values, index=caps.point_id.values)
    return w


def main() -> None:
    w = fixed_weights()
    series = {}
    for kind, wk in w.items():
        for pid in wk.index:
            series[pid] = weather.to_ons_hour(read_point_full(pid))
    idx = series[next(iter(series))].index

    def wavg(kind, var, transform=None):
        acc = 0.0
        for pid, wt in w[kind].items():
            v = series[pid][var]
            acc = acc + (transform(v) if transform else v) * wt
        return acc / w[kind].sum()

    C = pd.DataFrame(index=idx)
    for v in ["temperature_2m", "apparent_temperature", "relative_humidity_2m"]:
        C[v] = wavg("capital", v)
    C["shortwave_radiation_pop"] = wavg("capital", "shortwave_radiation")
    C["wind_speed_100m"] = wavg("wind", "wind_speed_100m")
    C["wind_speed3_100m"] = wavg("wind", "wind_speed_100m", lambda v: v ** 3)
    C["shortwave_radiation"] = wavg("solar", "shortwave_radiation")
    C["cdh24"] = (C.temperature_2m - 24).clip(lower=0)
    for pid in sorted(w["wind"].index):                       # vento de cada polo eólico (modelo B0)
        C[f"ws_{pid}"] = series[pid]["wind_speed_100m"].astype("float32")
    # inércia térmica da carga (modelo A0); nas primeiras 23 h da série a janela é menor
    C["temp_mm24"] = C.temperature_2m.rolling(24, min_periods=1).mean()
    C = C.dropna().reset_index()
    PROCESSED.mkdir(parents=True, exist_ok=True)
    C.to_parquet(PROCESSED / "clima_ne_1995_2026.parquet")
    pd.concat({k: v.rename("peso") for k, v in w.items()}).to_csv(PROCESSED / "clima_pesos_fixos.csv")
    print(C.shape, C.t.min(), C.t.max())
    print(C.groupby(C.t.dt.year)[["wind_speed_100m", "wind_speed3_100m", "temperature_2m", "shortwave_radiation"]]
          .mean().round(2).to_string())


if __name__ == "__main__":
    main()
