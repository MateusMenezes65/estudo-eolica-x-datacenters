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


def test_correlacao_da_regra():
    from src.sim.montecarlo import corr_regra
    g = serie_com_corte(0.3)
    # sem ruído na hidráulica, a resposta à carga líquida potencial é exata
    assert corr_regra(g, potencial=True) == pytest.approx(1.0, abs=1e-12)
    # com ruído, a correlação cai; medida sobre a carga já cortada, cai mais
    r = np.random.default_rng(1)
    g["hid"] = g.hid + r.normal(0, 600, len(g))
    assert 0.5 < corr_regra(g, potencial=True) < 1.0
    assert corr_regra(g, potencial=False) < corr_regra(g, potencial=True)


@pytest.mark.skipif(not (PROCESSED / "ne_features_h.parquet").exists(), reason="sem dados processados")
def test_insumos_usam_beta_do_regime_de_referencia():
    from src.sim import montecarlo as mc
    from src.sim.backtest_2026 import beta_hidro, observado
    from src.sim.trajetorias import load_cfg_anual
    ins = mc.Insumos()
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet").set_index("t")
    for j, ano in enumerate(ins.anos_h):
        assert ins.beta_ano[j] == pytest.approx(mc.beta_regra(X[X.ano == ano], True))
    # caso central (decisão 57): um só coeficiente, o de 2026, igual ao do backtest de 2026
    assert (ins.beta == ins.beta_ref).all()
    assert ins.beta_ref == pytest.approx(beta_hidro(observado(load_cfg_anual()), True), abs=1e-9)
    # motivo: o beta cai quando a carga líquida oscila mais, e 2026 é o regime observado mais próximo de 2030
    assert (np.diff(ins.dp_ano) > 0).all() and (np.diff(ins.beta_ano) < 0).all() and ins.dp_ref > ins.dp_ano.max()


@pytest.mark.skipif(not (PROCESSED / "sinteticos_2030.parquet").exists(), reason="sem perfis")
def test_beta_por_argumento_substitui_o_dos_insumos():
    from src.sim import montecarlo as mc
    c, _ = mc.load_cfg()
    ins = mc.Insumos()
    sd = mc.sortear(ins, 4, 7, 2)
    base, cfe, _, h = mc.series(ins, sd, np.arange(4), c)
    nl = -(base + cfe * 34288)
    a = mc.hidraulica(ins, h, nl, "regra_historica")
    assert np.array_equal(a, mc.hidraulica(ins, h, nl, "regra_historica", beta=ins.beta))
    plano = mc.hidraulica(ins, h, nl, "regra_historica", beta=np.zeros(4)).reshape(4, 365, 24)
    assert np.allclose(plano, plano.mean(2, keepdims=True), atol=0.2)          # beta zero: sem resposta intradiária


def test_potencial_da_frota_nao_depende_da_forma_das_usinas_com_fc():
    from src.sim.observado import potencial_frota
    # usinas sem FC geram 100 MW constantes; as com FC variam. Sem corte, o potencial é o balanço, hora a hora
    g = pd.DataFrame({"ger_eol_fc": [0.0, 400.0, 200.0], "ger_sol_fc": [1.0, 1.0, 1.0]})
    g["eol_bal"], g["sol_central"] = g.ger_eol_fc + 100, g.ger_sol_fc
    g["pot_eol_fc"], g["pot_sol_fc"] = g.ger_eol_fc, g.ger_sol_fc
    assert np.allclose(potencial_frota(g).eol_pot, [100.0, 500.0, 300.0])
    g.loc[1, "pot_eol_fc"] += 40                               # 40 MW de corte × razão 900/600
    P = potencial_frota(g)
    assert np.allclose(P.eol_pot, [100.0, 560.0, 300.0]) and np.allclose(P.corte_eol, [0, 60, 0])
    assert (P.eol_pot >= g.eol_bal).all()


@pytest.mark.skipif(not (PROCESSED / "ne_features_h.parquet").exists(), reason="sem dados processados")
def test_importacao_potencial_nunca_excede_a_realizada():
    from src.sim.diagnostico_importacao import observado_ano
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    for ano in [2022, 2023, 2024, 2025]:
        v = observado_ano(X, ano).query("valida")
        assert np.clip(-v.M, 0, None).sum() <= np.clip(-v.interc, 0, None).sum() + 1e-6, ano   # cortes só reduzem


@pytest.mark.skipif(not (PROCESSED / "ne_features_h.parquet").exists(), reason="sem dados processados")
def test_m_observado_fecha_com_intercambio_mais_cortes():
    from src.sim.diagnostico_importacao import observado_ano
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    O = observado_ano(X, 2025)
    v = O[O.valida]
    esperado = v.interc + (v.eol_pot - v.eol_real) + (v.sol_pot - v.sol_real)
    assert np.allclose(v.M, esperado)
    assert len(O) == 8760 and O.valida.mean() > 0.99
