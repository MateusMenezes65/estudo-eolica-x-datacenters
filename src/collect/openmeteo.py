"""Reanálise horária ERA5 via Open-Meteo Historical (sem chave).

Uso: python -m src.collect.openmeteo [--start 2022-01-01] [--end AAAA-MM-DD]

Lê config/weather_points.csv e baixa, por ponto, as variáveis do seu tipo:
- capital: temperatura 2 m, umidade relativa 2 m, temperatura aparente,
  irradiância global horizontal (shortwave_radiation), nebulosidade
- wind:    vento a 100 m (velocidade, direção), temperatura 2 m
- solar:   irradiância global horizontal, nebulosidade, temperatura 2 m
Modelo fixado em ERA5 (models=era5, ~0,25°) para homogeneidade temporal e
para permitir estender a anos anteriores. Horário em UTC (timezone=GMT).
Vento em m/s; irradiância em W/m² (média da hora anterior); temperatura em °C.
Resposta JSON bruta salva em data/raw/openmeteo/<point_id>.json.gz.
"""
from __future__ import annotations

import argparse
import gzip
import json
import time
from datetime import date, timedelta

import pandas as pd
import requests

from src.collect.manifest import record
from src.paths import CONFIG, RAW

API = "https://archive-api.open-meteo.com/v1/archive"
OUT = RAW / "openmeteo"
VARS = {
    "capital": "temperature_2m,relative_humidity_2m,apparent_temperature,shortwave_radiation,cloud_cover",
    "wind": "wind_speed_100m,wind_direction_100m,temperature_2m",
    "solar": "shortwave_radiation,cloud_cover,temperature_2m",
}


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2022-01-01")
    p.add_argument("--end", default=(date.today() - timedelta(days=8)).isoformat())
    p.add_argument("--only", nargs="*")
    a = p.parse_args(argv)
    pts = pd.read_csv(CONFIG / "weather_points.csv")
    OUT.mkdir(parents=True, exist_ok=True)
    for _, r in pts.iterrows():
        if a.only and r.point_id not in a.only:
            continue
        dest = OUT / f"{r.point_id}.json.gz"
        if dest.exists():
            print(f"skip {dest.name}"); continue
        params = dict(latitude=r.lat, longitude=r.lon, start_date=a.start, end_date=a.end,
                      hourly=VARS[r.kind], models="era5", timezone="GMT",
                      wind_speed_unit="ms")
        for attempt in range(6):
            resp = requests.get(API, params=params, timeout=300)
            if resp.status_code == 429:
                wait = 60 * (attempt + 1)
                print(f"  429 limite de taxa; aguardando {wait}s"); time.sleep(wait); continue
            resp.raise_for_status(); break
        else:
            raise RuntimeError(f"falha {r.point_id}")
        j = resp.json()
        with gzip.open(dest, "wt", encoding="utf-8") as f:
            json.dump(j, f)
        n = len(j["hourly"]["time"])
        record(dest, source="Open-Meteo Historical API (ERA5)", dataset="archive-api era5",
               resource=r.point_id, url=resp.url, ref_period=f"{a.start}..{a.end}",
               time_zone="UTC", units=json.dumps(j.get("hourly_units"), ensure_ascii=False),
               notes=f"{r.kind}; lat={r.lat}; lon={r.lon}; grid=({j.get('latitude')},{j.get('longitude')}); "
                     f"elev={j.get('elevation')}; {n} horas")
        print(f"OK {r.point_id}: {n} horas; grade ({j.get('latitude')},{j.get('longitude')})")
        time.sleep(3)


if __name__ == "__main__":
    main()
