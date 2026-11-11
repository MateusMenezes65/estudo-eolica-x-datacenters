"""Leitura das respostas Open-Meteo (ERA5) e alinhamento à hora do ONS.

ERA5/Open-Meteo, em UTC:
- variáveis instantâneas (temperatura, umidade, vento, nebulosidade) valem no
  instante rotulado;
- shortwave_radiation é a média da hora ANTERIOR ao rótulo.
Hora do ONS: intervalo [t, t+1h) em horário de Brasília (UTC-3).
Alinhamento: instantâneas -> média dos instantes t e t+1h; radiação -> valor
rotulado t+1h. Ambos convertidos de UTC para Brasília.
"""
from __future__ import annotations

import gzip
import json

import pandas as pd

from src.paths import CONFIG, RAW

INSTANT = ["temperature_2m", "relative_humidity_2m", "apparent_temperature",
           "wind_speed_100m", "cloud_cover", "wind_direction_100m"]
PERIOD_PRECEDING = ["shortwave_radiation"]


def read_point(point_id: str) -> pd.DataFrame:
    with gzip.open(RAW / "openmeteo" / f"{point_id}.json.gz", "rt", encoding="utf-8") as f:
        j = json.load(f)
    d = pd.DataFrame(j["hourly"])
    d["t_utc"] = pd.to_datetime(d.pop("time"))
    return d.set_index("t_utc")


def to_ons_hour(d: pd.DataFrame) -> pd.DataFrame:
    """Converte uma série ERA5 (índice UTC) para horas ONS (início, Brasília)."""
    out = pd.DataFrame(index=d.index)
    for c in d.columns:
        if c == "wind_direction_100m":  # direção: não se faz média aritmética de ângulos
            out[c] = d[c]
        elif c in INSTANT:
            out[c] = (d[c] + d[c].shift(-1)) / 2
        elif c in PERIOD_PRECEDING:
            out[c] = d[c].shift(-1)
        else:
            out[c] = d[c]
    out.index = out.index - pd.Timedelta(hours=3)
    out.index.name = "t"
    return out


def points() -> pd.DataFrame:
    return pd.read_csv(CONFIG / "weather_points.csv")
