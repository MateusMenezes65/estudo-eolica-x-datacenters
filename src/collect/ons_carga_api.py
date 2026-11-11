"""Carga verificada semi-horária do ONS via API (separa MMGD da carga global).

Uso: python -m src.collect.ons_carga_api --area NE --start 2022-01 --end 2026-11

API: https://apicarga.ons.org.br/prd/cargaverificada (sem chave).
Cada mês é salvo como resposta JSON bruta comprimida em
data/raw/ons/carga_verificada/<AREA>_<AAAA>_<MM>.json.gz.
Campos: din_referenciautc = FIM do intervalo de 30 min, em UTC;
dat_referencia = data local (Brasília). Valores em MWmed no intervalo.
Meses já baixados são pulados, exceto os dois últimos (dados em consistência).
"""
from __future__ import annotations

import argparse
import calendar
import gzip
import json
import time
from datetime import date

import requests

from src.collect.manifest import record
from src.paths import RAW

API = "https://apicarga.ons.org.br/prd/cargaverificada"
OUT = RAW / "ons" / "carga_verificada"


def months(start: str, end: str):
    y, m = map(int, start.split("-"))
    ye, me = map(int, end.split("-"))
    while (y, m) <= (ye, me):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--area", default="NE")
    p.add_argument("--start", default="2022-01")
    p.add_argument("--end", default=date.today().strftime("%Y-%m"))
    a = p.parse_args(argv)
    ms = list(months(a.start, a.end))
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (y, m) in enumerate(ms):
        dest = OUT / f"{a.area}_{y}_{m:02d}.json.gz"
        if dest.exists() and i < len(ms) - 2:
            continue
        last = min(calendar.monthrange(y, m)[1],
                   (date.today().day if (y, m) == (date.today().year, date.today().month) else 31))
        params = {"dat_inicio": f"{y}-{m:02d}-01", "dat_fim": f"{y}-{m:02d}-{last:02d}",
                  "cod_areacarga": a.area}
        for attempt in range(4):
            try:
                r = requests.get(API, params=params, timeout=300)
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:
                print(f"  {y}-{m:02d} tentativa {attempt+1}: {e}")
                time.sleep(10 * (attempt + 1))
        else:
            raise RuntimeError(f"falha {y}-{m:02d}")
        with gzip.open(dest, "wt", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        record(dest, source="ONS API Carga", dataset="carga-energia-verificada",
               resource=f"{a.area} {y}-{m:02d}", url=f"{API}?dat_inicio={params['dat_inicio']}"
               f"&dat_fim={params['dat_fim']}&cod_areacarga={a.area}",
               ref_period=f"{y}-{m:02d}", time_zone="UTC (fim do intervalo de 30 min)",
               units="MWmed", notes=f"{len(data)} registros")
        print(f"OK {dest.name}: {len(data)} registros")


if __name__ == "__main__":
    main()
