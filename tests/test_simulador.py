"""Cenários-limite do simulador (AGENTS.md, Engenharia): exemplos pequenos com resultado conhecido."""
import numpy as np
import pandas as pd
import pytest
import yaml

from src.paths import CONFIG
from src.sim import deterministico as sim


@pytest.fixture(scope="module")
def cfg():
    return sim.load_cfg()


def perfil(n=48, seed=0):
    r = np.random.default_rng(seed)
    idx = pd.date_range("2030-01-01", periods=n, freq="h")
    return pd.DataFrame({"L_gross": 12000 + 2000 * r.random(n), "MMGD": 1000 * r.random(n),
                         "hid": np.full(n, 3000.0), "ter": np.full(n, 500.0),
                         "cf_eol": r.random(n) * 0.8, "cf_sol": r.random(n) * 0.6}, index=idx)


def test_carga_dc_zero_reproduz_caso_base():
    p = perfil()
    assert sim.margin(p, 30000, 13000, 0.0).equals(sim.margin(p, 30000, 13000, 0))
    assert np.allclose(sim.margin(p, 30000, 13000, 0.0),
                       p.hid + p.ter + p.cf_eol * 30000 + p.cf_sol * 13000 - (p.L_gross - p.MMGD))


def test_mais_carga_nao_reduz_importacao(cfg):
    c, _ = cfg
    p = perfil(500, 1)
    imps = [sim.balance_metrics(sim.margin(p, 20000, 10000, l), c)["importacao_TWh"] for l in [0, 500, 1000, 3000]]
    assert all(b >= a for a, b in zip(imps, imps[1:]))


def test_mw_vezes_horas_fecha_com_mwh(cfg):
    c, _ = cfg
    M = pd.Series([-1000.0, -2000.0, 500.0, 0.0])  # MWmed por hora
    m = sim.balance_metrics(M, c)
    assert m["importacao_TWh"] == pytest.approx(3000 / 1e6)   # 1000 + 2000 MWh
    assert m["excedente_TWh"] == pytest.approx(500 / 1e6)
    assert m["horas_importacao"] == 2 and m["maior_sequencia_importacao_h"] == 2


def test_l_dc_cenarios(cfg):
    _, d = cfg
    assert sim.l_dc_2030("sem_dc", d)[0] == 0
    assert sim.l_dc_2030("conservador", d)[0] == 1886
    assert sim.l_dc_2030("central", d)[0] == 2098
    alto, P = sim.l_dc_2030("alto", d)
    assert alto > 1886 + 2 * 212  # inclui inventário M3 em rampa
    assert (P.MWmed >= 0).all()


def test_compensacao_devolve_importacao_ao_caso_base(cfg):
    c, _ = cfg
    p = perfil(2000, 2)
    ref = sim.balance_metrics(sim.margin(p, 20000, 10000, 0), c)
    Mdc = sim.margin(p, 20000, 10000, 1500)
    comp = sim.compensation(p, c, 20000, 10000, 1500, ref, Mdc)
    dW = comp["dW_importacao_anual_MW"]
    assert np.isfinite(dW) and dW > 0
    novo = sim.balance_metrics(sim.margin(p, 20000 + dW, 10000, 1500), c)
    assert novo["importacao_TWh"] <= ref["importacao_TWh"] + 1e-9
    assert comp["dW_energia_anual_MW"] == pytest.approx(1500 / p.cf_eol.mean())
