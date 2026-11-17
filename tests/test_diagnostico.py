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
    # colunas no formato de ne_features_h (frota inteira = usinas com FC: razão 1)
    g = pd.DataFrame({"L_net": L, "pot_eol_fc": eol_pot, "ger_eol_fc": eol_real, "eol_bal": eol_real,
                      "pot_sol_fc": sol, "ger_sol_fc": sol, "sol_central": sol, "interc": 0.0, "ter": 500.0,
                      "MMGD": 0.0, "anomalia_balanco": 0}, index=t)
    nl = g.L_net - g.pot_eol_fc - g.pot_sol_fc
    d = g.index.date
    g["hid"] = 4000 + beta_verdadeiro * (nl - nl.groupby(d).transform("mean"))
    return g


def test_beta_adotado_recupera_o_coeficiente_e_o_anterior_exagera():
    from src.sim.montecarlo import beta_regra
    g = serie_com_corte(0.3)
    assert beta_regra(g, potencial=True) == pytest.approx(0.3, abs=1e-9)
    # sobre a carga líquida realizada (com corte) o coeficiente sai maior: aplicado à potencial, exagera a resposta
    assert beta_regra(g, potencial=False) > 0.33


@pytest.mark.skipif(not (PROCESSED / "ne_features_h.parquet").exists(), reason="sem dados processados")
def test_insumos_usam_beta_adotado():
    from src.sim import montecarlo as mc
    ins = mc.Insumos()
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet").set_index("t")
    for j, ano in enumerate(ins.anos_h):
        g = X[X.ano == ano]
        assert ins.beta[j] == pytest.approx(mc.beta_regra(g, True))
        assert ins.beta_realizada[j] == pytest.approx(mc.beta_regra(g, False))
    assert (ins.beta[-2:] < ins.beta_realizada[-2:]).all()      # anos de corte alto: adotado menor


@pytest.mark.skipif(not (PROCESSED / "ne_features_h.parquet").exists(), reason="sem dados processados")
def test_m_observado_fecha_com_intercambio_mais_cortes():
    from src.sim.diagnostico_importacao import observado_ano
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    O = observado_ano(X, 2025)
    v = O[O.valida]
    esperado = v.interc + (v.eol_pot - v.eol_real) + (v.sol_pot - v.sol_real)
    assert np.allclose(v.M, esperado)
    assert len(O) == 8760 and O.valida.mean() > 0.99
