"""Diagnóstico da subestimação: estimação do coeficiente da regra hidráulica e identidade do balanço."""
import numpy as np
import pandas as pd
import pytest

from src.paths import PROCESSED


def serie_com_corte(beta_verdadeiro=0.3, dias=40, seed=0):
    """Hidráulica responde à carga líquida POTENCIAL; a eólica realizada é cortada acima de um teto."""
    r = np.random.default_rng(seed)
    t = pd.date_range("2025-01-01", periods=24 * dias, freq="h")
    h = t.hour.to_numpy()
    L = 12000 + 2500 * np.sin((h - 6) / 24 * 2 * np.pi) + r.normal(0, 300, len(t))
    eol_pot = 9000 + 5000 * np.cos(h / 24 * 2 * np.pi) + r.normal(0, 1500, len(t))
    eol_real = np.minimum(eol_pot, 10000.0)                     # corte nas horas de muito vento
    sol = np.clip(4000 * np.sin((h - 6) / 12 * np.pi), 0, None)
    g = pd.DataFrame({"L_api_liq": L, "eol_pot": eol_pot, "eol_real": eol_real, "sol_pot": sol, "sol_real": sol}, index=t)
    nl = g.L_api_liq - g.eol_pot - g.sol_pot
    d = g.index.date
    g["hid"] = 4000 + beta_verdadeiro * (nl - nl.groupby(d).transform("mean"))
    return g


def test_beta_consistente_recupera_o_coeficiente_e_o_do_estudo_exagera():
    from src.sim.diagnostico_importacao import beta
    g = serie_com_corte(0.3)
    assert beta(g, potencial=True) == pytest.approx(0.3, abs=1e-9)
    # sobre a carga líquida realizada (com corte) o coeficiente sai maior: aplicado à potencial, exagera a resposta
    assert beta(g, potencial=False) > 0.33


@pytest.mark.skipif(not (PROCESSED / "ne_features_h.parquet").exists(), reason="sem dados processados")
def test_m_observado_fecha_com_intercambio_mais_cortes():
    from src.sim.diagnostico_importacao import observado_ano
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    O = observado_ano(X, 2025)
    v = O[O.valida]
    esperado = v.interc + (v.eol_pot - v.eol_real) + (v.sol_pot - v.sol_real)
    assert np.allclose(v.M, esperado)
    assert len(O) == 8760 and O.valida.mean() > 0.99
