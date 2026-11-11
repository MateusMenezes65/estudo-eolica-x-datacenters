"""Testes de conversão temporal e de unidades com resultados conhecidos."""
import numpy as np
import pandas as pd
import pytest

from src.collect.ons import select
from src.ingest import ons, weather


def test_hourly_mean_of_half_hours_is_mwmed():
    # 30 min a 100 MW + 30 min a 200 MW = 150 MWh na hora = 150 MWmed
    d = pd.DataFrame({"t": pd.to_datetime(["2024-01-01 00:00", "2024-01-01 00:30",
                                           "2024-01-01 01:00"]), "v": [100.0, 200.0, 50.0]})
    h = ons.to_hourly_mean(d, "t", ["v"])
    assert h.v.tolist() == [150.0, 50.0]
    assert h.incompleta.tolist() == [False, True]
    energia_mwh = (d.v * 0.5).iloc[:2].sum()
    assert energia_mwh == h.v.iloc[0] * 1.0  # MW × h fecha com MWh


def test_api_end_utc_to_start_brasilia():
    # fim do intervalo 03:30 UTC -> início 00:00 em Brasília (UTC-3)
    fim = pd.Timestamp("2022-01-01 03:30")
    assert fim + ons.BRT_OFFSET - pd.Timedelta(minutes=30) == pd.Timestamp("2022-01-01 00:00")


def test_weather_alignment():
    idx = pd.date_range("2024-01-01 03:00", periods=3, freq="h")  # UTC
    d = pd.DataFrame({"temperature_2m": [20.0, 22.0, 24.0],
                      "shortwave_radiation": [0.0, 100.0, 300.0]}, index=idx)
    o = weather.to_ons_hour(d)
    assert o.index[0] == pd.Timestamp("2024-01-01 00:00")  # 03 UTC = 00 BRT
    assert o.temperature_2m.iloc[0] == 21.0                # média de 00h e 01h BRT
    assert o.shortwave_radiation.iloc[0] == 100.0          # média de [00h,01h) rotulada 01h


def test_num_parsing_text_and_comma():
    s = pd.Series(["1.5", "2,5", "", "-", "0E-8"])
    out = ons._num(s)
    assert out.iloc[0] == 1.5 and out.iloc[1] == 2.5
    assert out.iloc[2:4].isna().all() and out.iloc[4] == 0.0


def test_select_fallback_csv_and_period():
    res = [
        {"url": "x/A_2022.csv", "format": "CSV"},
        {"url": "x/A_2023.parquet", "format": "PARQUET"},
        {"url": "x/A_2023.csv", "format": "CSV"},
        {"url": "x/A_2021.parquet", "format": "PARQUET"},
        {"url": "x/DicionarioDados_A.pdf", "format": "PDF"},
    ]
    sel = select(res, "PARQUET", 2022, 2026)
    urls = [x["url"] for x in sel]
    assert "x/A_2022.csv" in urls and "x/A_2023.parquet" in urls
    assert "x/A_2023.csv" not in urls and "x/A_2021.parquet" not in urls
    assert "x/DicionarioDados_A.pdf" in urls


def test_tipo_fonte_with_replacement_char():
    s = pd.Series(["E�lica", "FOTOVOLTAICA", "HIDROEL�TRICA", "T�RMICA", "NUCLEAR"])
    assert ons.tipo_fonte(s).tolist() == ["EOL", "SOL", "HID", "TER", "NUC"]


def test_calendario_ponte():
    from src.collect.calendario_ne import build
    c = build(2026, 2026).set_index("data")
    # 2026-04-21 (Tiradentes) é terça -> segunda 20/04 é ponte
    assert c.loc[pd.Timestamp("2026-04-20").date(), "ponte"] == 1
    assert c.loc[pd.Timestamp("2026-04-21").date(), "feriado_nacional"] == 1
