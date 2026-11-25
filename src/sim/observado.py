"""Geração eólica e solar POTENCIAL observada da frota inteira do NE (definição única do projeto).

Potencial = geração do balanço do ONS + corte apurado (GNRa). A GNRa existe só para as usinas com
fator de capacidade (FC); o corte delas é levado à frota inteira pela razão média balanço / usinas com
FC. A geração em si vem sempre do balanço, hora a hora.

Até 2026-11-25 vários módulos usavam (geração + corte das usinas com FC) × razão média. As duas formas
têm a mesma média anual, mas não a mesma forma horária: as usinas sem FC geram relativamente mais nas
horas de pouco vento, e a versão escalada subestimava a geração justamente nas horas de importação, o
que inflava a importação "observada" em 4% a 10% (decisão 54).
"""
from __future__ import annotations

import pandas as pd


def razoes_frota(v: pd.DataFrame) -> tuple[float, float]:
    """Razão média entre a geração do balanço e a das usinas com FC (eólica, solar) nas horas `v`."""
    return float(v.eol_bal.mean() / v.ger_eol_fc.mean()), float(v.sol_central.mean() / v.ger_sol_fc.mean())


def potencial_frota(g: pd.DataFrame, validas: pd.DataFrame | None = None) -> pd.DataFrame:
    """Séries horárias `eol_pot`, `sol_pot`, `corte_eol` e `corte_sol` (MWmed) da frota inteira.

    `validas` restringe as horas usadas na razão (2026 tem horas em que o balanço não fecha). As razões
    ficam em `attrs` (fr_e, fr_s).
    """
    fr_e, fr_s = razoes_frota(g if validas is None else validas)
    P = pd.DataFrame(index=g.index)
    P["corte_eol"] = (g.pot_eol_fc - g.ger_eol_fc) * fr_e
    P["corte_sol"] = (g.pot_sol_fc - g.ger_sol_fc) * fr_s
    P["eol_pot"] = g.eol_bal + P.corte_eol
    P["sol_pot"] = g.sol_central + P.corte_sol
    P.attrs.update(fr_e=fr_e, fr_s=fr_s)
    return P
