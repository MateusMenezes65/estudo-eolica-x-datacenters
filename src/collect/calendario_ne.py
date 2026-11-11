"""Calendário diário de feriados e eventos do subsistema NE (item #6).

Uso: python -m src.collect.calendario_ne [--start 2015] [--end 2030]
Gera config/calendario_ne.csv (versionado; reprodutível a partir da biblioteca
`holidays`, versão em requirements.txt).

Colunas:
- feriado_nacional: feriados públicos nacionais (categoria 'public').
- n_uf_feriado_estadual: nº de UFs do subsistema NE (AL, BA, CE, PB, PE, PI,
  RN, SE) com feriado estadual na data (além dos nacionais).
- ponto_facultativo: categoria 'optional' da biblioteca (Carnaval, Quarta de
  Cinzas, Corpus Christi quando opcional, vésperas de Natal/Ano-Novo, Dia do
  Servidor Público).
- carnaval: segunda e terça de Carnaval + Quarta-feira de Cinzas.
- sao_joao: 23 e 24/06 (festas juninas; feriado municipal em muitas cidades do
  NE e estadual em AL — hipótese de evento regional, não feriado oficial geral).
- ponte: dia útil isolado entre feriado nacional e fim de semana.
- vespera_feriado / pos_feriado: dia anterior/seguinte a feriado nacional.
Feriados municipais (capitais) não estão incluídos: limitação declarada.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

import holidays
import pandas as pd

from src.paths import CONFIG

NE_UFS = ["AL", "BA", "CE", "PB", "PE", "PI", "RN", "SE"]


def build(start: int, end: int) -> pd.DataFrame:
    years = range(start, end + 1)
    nat = holidays.BR(years=years, categories=("public",))
    opt = holidays.BR(years=years, categories=("optional",))
    est = {uf: holidays.BR(subdiv=uf, years=years, categories=("public",)) for uf in NE_UFS}
    days = pd.date_range(f"{start}-01-01", f"{end}-12-31", freq="D")
    rows = []
    for ts in days:
        d = ts.date()
        n_est = sum(1 for uf in NE_UFS if d in est[uf] and d not in nat)
        rows.append({
            "data": d, "feriado_nacional": int(d in nat),
            "nome_nacional": nat.get(d, ""),
            "n_uf_feriado_estadual": n_est,
            "ufs_feriado_estadual": ",".join(uf for uf in NE_UFS if d in est[uf] and d not in nat),
            "ponto_facultativo": int(d in opt), "nome_facultativo": opt.get(d, ""),
            "carnaval": int("Carnaval" in opt.get(d, "") or "Cinzas" in opt.get(d, "")),
            "sao_joao": int((d.month, d.day) in {(6, 23), (6, 24)}),
        })
    c = pd.DataFrame(rows)
    dow = pd.to_datetime(c.data).dt.day_of_week
    fer = c.feriado_nacional.astype(bool)
    c["vespera_feriado"] = fer.shift(-1, fill_value=False).astype(int)
    c["pos_feriado"] = fer.shift(1, fill_value=False).astype(int)
    util = (dow < 5) & ~fer
    ponte = (util & (((dow == 0) & fer.shift(-1, fill_value=False))      # seg antes de ter feriado
                     | ((dow == 4) & fer.shift(1, fill_value=False))))   # sex após qui feriado
    c["ponte"] = ponte.astype(int)
    return c


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=2015)
    p.add_argument("--end", type=int, default=2030)
    a = p.parse_args(argv)
    c = build(a.start, a.end)
    c.to_csv(CONFIG / "calendario_ne.csv", index=False, encoding="utf-8")
    print(f"{len(c)} dias; feriados nacionais={c.feriado_nacional.sum()}; pontes={c.ponte.sum()}; "
          f"dias com feriado estadual NE={(c.n_uf_feriado_estadual>0).sum()}")


if __name__ == "__main__":
    main()
