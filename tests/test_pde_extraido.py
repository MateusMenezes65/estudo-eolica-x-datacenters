"""Conferências da extração do PDE 2035 (config/pde2035_extraido.csv)."""
import pandas as pd

from src.paths import CONFIG


def test_pde_ne_reference_and_consistency():
    d = pd.read_csv(CONFIG / "pde2035_extraido.csv")
    ref = d[(d.variavel == "carga_energia") & (d.cenario == "referencia") & (d.fonte.str.contains("Tabela 2-3"))]
    ne = ref[ref.escopo == "Nordeste"].set_index("ano").valor
    assert ne[2025] == 13684 and ne[2030] == 16340 and ne[2035] == 19610
    sin = ref[ref.escopo == "SIN"].set_index("ano").valor
    fig = d[(d.fonte.str.contains("2-25")) & (d.cenario == "referencia")].set_index("ano").valor
    for ano in (2025, 2030, 2035):  # tabela e planilha do mesmo cenário coincidem
        assert abs(sin[ano] - fig[ano]) < 2
