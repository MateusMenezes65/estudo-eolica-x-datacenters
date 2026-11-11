"""Leitores padronizados das bases do ONS.

Convenções adotadas (confirmadas nos dicionários/dados, ver docs/decisoes.md):
- ONS horário (balanço, curva de carga, intercâmbio, geração/FC por usina):
  `din_instante` = INÍCIO da hora, horário de Brasília (UTC-3; sem horário de
  verão desde 2019). Mantido como timestamp ingênuo em horário de Brasília.
- Carga verificada (API): `din_referenciautc` = FIM do intervalo de 30 min em
  UTC -> convertido para início do intervalo em Brasília.
- Valores `val_*` em MWmed no intervalo. Alguns arquivos trazem `val_*` como
  texto: convertidos com pd.to_numeric (erros contados, não descartados em silêncio).
- Tipos de usina variam entre conjuntos ('Eólica', 'EOLIELÉTRICA', 'Solar',
  'FOTOVOLTAICA'...); são normalizados por padrões ASCII robustos a acentos.
"""
from __future__ import annotations

import glob
import gzip
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.paths import RAW

BRT_OFFSET = pd.Timedelta(hours=-3)
NE = "NE"


def _num(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s.astype("float64")
    s = s.astype("string").str.strip().replace({"": pd.NA, "-": pd.NA})
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _read_file(f: str) -> pd.DataFrame:
    if f.endswith(".parquet"):
        d = pd.read_parquet(f)
    else:
        d = pd.read_csv(f, sep=";", dtype=str, encoding="utf-8", encoding_errors="replace")
    for c in d.columns:
        if c.startswith("val_"):
            d[c] = _num(d[c])
        elif c.startswith("din_"):
            d[c] = pd.to_datetime(d[c])
        elif d[c].dtype != object and not pd.api.types.is_string_dtype(d[c]):
            continue
        else:
            d[c] = d[c].astype("string").str.strip()
    d["_arquivo"] = Path(f).name
    return d


def read_dataset(key: str, columns_filter=None) -> pd.DataFrame:
    """Concatena todos os arquivos de data/raw/ons/<key>/ (parquet/csv)."""
    files = sorted(glob.glob(str(RAW / "ons" / key / "*.parquet"))
                   + glob.glob(str(RAW / "ons" / key / "*.csv")))
    if not files:
        raise FileNotFoundError(f"sem arquivos em data/raw/ons/{key}")
    parts = []
    for f in files:
        d = _read_file(f)
        if columns_filter is not None:
            d = columns_filter(d)
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def tipo_fonte(s: pd.Series) -> pd.Series:
    """Normaliza o tipo de usina/fonte para EOL, SOL, HID, TER, NUC."""
    u = s.astype("string").str.upper()
    out = pd.Series(pd.NA, index=s.index, dtype="string")
    out[u.str.contains("LICA|EOL", na=False)] = "EOL"
    out[u.str.contains("FOTOV|SOLAR", na=False)] = "SOL"
    out[u.str.contains("HIDR", na=False)] = "HID"
    out[u.str.contains("NUCL", na=False)] = "NUC"
    out[u.str.contains("RMICA|TERM|TÉRM", na=False) & out.isna()] = "TER"
    return out


# ---------------------------------------------------------------- leitores
def balanco() -> pd.DataFrame:
    d = read_dataset("balanco")
    return d.rename(columns={"din_instante": "t"})


def curva_carga() -> pd.DataFrame:
    return read_dataset("curva_carga").rename(columns={"din_instante": "t"})


def intercambio() -> pd.DataFrame:
    return read_dataset("intercambio").rename(columns={"din_instante": "t"})


def capacidade() -> pd.DataFrame:
    d = read_dataset("capacidade")
    for c in ["dat_entradateste", "dat_entradaoperacao", "dat_desativacao"]:
        d[c] = pd.to_datetime(d[c], errors="coerce")
    d["fonte"] = tipo_fonte(d["nom_tipousina"])
    return d


def geracao_usina(subsistema: str | None = NE) -> pd.DataFrame:
    f = (lambda d: d[d.id_subsistema == subsistema]) if subsistema else None
    d = read_dataset("geracao_usina", f).rename(columns={"din_instante": "t"})
    d["fonte"] = tipo_fonte(d["nom_tipousina"])
    return d


def fator_capacidade(subsistema: str | None = NE) -> pd.DataFrame:
    f = (lambda d: d[d.id_subsistema == subsistema]) if subsistema else None
    d = read_dataset("fator_capacidade", f).rename(columns={"din_instante": "t"})
    d["fonte"] = tipo_fonte(d["nom_tipousina"])
    return d


def coff(key: str = "coff_eolica", subsistema: str | None = NE) -> pd.DataFrame:
    f = (lambda d: d[d.id_subsistema == subsistema]) if subsistema else None
    return read_dataset(key, f).rename(columns={"din_instante": "t"})


def carga_verificada(area: str = NE) -> pd.DataFrame:
    """Semi-horária; retorna t_ini (início do intervalo, horário de Brasília)."""
    rows = []
    for f in sorted(glob.glob(str(RAW / "ons" / "carga_verificada" / f"{area}_*.json.gz"))):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            rows.extend(json.load(fh))
    d = pd.DataFrame(rows)
    fim_utc = pd.to_datetime(d["din_referenciautc"], utc=True).dt.tz_localize(None)
    d["t_ini"] = fim_utc + BRT_OFFSET - pd.Timedelta(minutes=30)
    for c in d.columns:
        if c.startswith("val_"):
            d[c] = _num(d[c])
    return d.drop(columns=["din_referenciautc"])


def to_hourly_mean(d: pd.DataFrame, tcol: str, cols: list[str], by: list[str] | None = None,
                   expected: int = 2) -> pd.DataFrame:
    """Agrega intervalos de 30 min (MWmed) para hora: média dos sub-intervalos.

    MWmed horário = (E_1 + E_2) / 1 h = média das potências médias de 30 min.
    Retorna também n_sub (nº de sub-intervalos) para auditar horas incompletas.
    """
    by = by or []
    d = d.assign(t=d[tcol].dt.floor("h"))
    g = d.groupby(by + ["t"], sort=True)
    out = g[cols].mean()
    out["n_sub"] = g.size()
    out["incompleta"] = out["n_sub"] != expected
    return out.reset_index()
