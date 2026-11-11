"""Reanálise horária ERA5 via Open-Meteo Historical (sem chave).

Uso: python -m src.collect.openmeteo [--start 2022-01-01] [--end AAAA-MM-DD]
     python -m src.collect.openmeteo --start 1995-01-01 --end 2021-12-31 --chunk-years 9
     (anos climáticos para o Monte Carlo; retomável: blocos já baixados são pulados)

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


def chunks(start: str, end: str, years: int):
    """Divide [start, end] em blocos de `years` anos civis (0 = bloco único)."""
    if years <= 0:
        return [(start, end)]
    y0, y1 = int(start[:4]), int(end[:4])
    out = []
    for y in range(y0, y1 + 1, years):
        a = max(start, f"{y}-01-01")
        b = min(end, f"{min(y + years - 1, y1)}-12-31")
        out.append((a, b))
    return out


def get_with_limits(params: dict, max_wait_h: float = 30.0) -> requests.Response:
    """GET respeitando os limites da API gratuita (por minuto, hora e dia).

    Em HTTP 429 lê o motivo: limite por minuto/hora -> espera 2/15 min; diário ->
    espera 30 min em ciclos (o contador diário reinicia). Desiste após max_wait_h.
    """
    waited = 0.0
    while True:
        try:
            resp = requests.get(API, params=params, timeout=600)
        except requests.RequestException as e:
            print(f"  erro de rede: {e}; nova tentativa em 60 s", flush=True)
            time.sleep(60); waited += 60; continue
        if resp.status_code != 429:
            resp.raise_for_status()
            return resp
        reason = ""
        try:
            reason = resp.json().get("reason", "")
        except ValueError:
            pass
        low = reason.lower()
        wait = 120 if "minut" in low else 900 if "hour" in low else 1800
        if waited + wait > max_wait_h * 3600:
            raise RuntimeError(f"limite da API persistente: {reason}")
        print(f"  429 ({reason or 'sem motivo'}); aguardando {wait // 60} min", flush=True)
        time.sleep(wait); waited += wait


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2022-01-01")
    p.add_argument("--end", default=(date.today() - timedelta(days=8)).isoformat())
    p.add_argument("--chunk-years", type=int, default=0,
                   help="0: um arquivo <ponto>.json.gz (período de calibração); "
                        ">0: blocos em data/raw/openmeteo/hist/<ponto>_<ini>_<fim>.json.gz")
    p.add_argument("--only", nargs="*")
    a = p.parse_args(argv)
    pts = pd.read_csv(CONFIG / "weather_points.csv")
    OUT.mkdir(parents=True, exist_ok=True)
    for ini, fim in chunks(a.start, a.end, a.chunk_years):
        for _, r in pts.iterrows():
            if a.only and r.point_id not in a.only:
                continue
            if a.chunk_years > 0:
                dest = OUT / "hist" / f"{r.point_id}_{ini[:4]}_{fim[:4]}.json.gz"
            else:
                dest = OUT / f"{r.point_id}.json.gz"
            if dest.exists():
                print(f"skip {dest.name}"); continue
            params = dict(latitude=r.lat, longitude=r.lon, start_date=ini, end_date=fim,
                          hourly=VARS[r.kind], models="era5", timezone="GMT",
                          wind_speed_unit="ms")
            resp = get_with_limits(params)
            j = resp.json()
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                json.dump(j, f)
            tmp.replace(dest)
            n = len(j["hourly"]["time"])
            record(dest, source="Open-Meteo Historical API (ERA5)", dataset="archive-api era5",
                   resource=r.point_id, url=resp.url, ref_period=f"{ini}..{fim}",
                   time_zone="UTC", units=json.dumps(j.get("hourly_units"), ensure_ascii=False),
                   notes=f"{r.kind}; lat={r.lat}; lon={r.lon}; grid=({j.get('latitude')},{j.get('longitude')}); "
                         f"elev={j.get('elevation')}; {n} horas")
            print(f"OK {dest.name}: {n} horas", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()
