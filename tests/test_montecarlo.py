"""Testes do Monte Carlo: reprodutibilidade, sorteios comuns, blocos e conservação de energia."""
import numpy as np
import pytest

from src.paths import PROCESSED

pytestmark = pytest.mark.skipif(not (PROCESSED / "sinteticos_2030.parquet").exists(),
                                reason="rode python -m src.sim.sinteticos")


@pytest.fixture(scope="module")
def ctx():
    from src.sim import montecarlo as mc
    c, d = mc.load_cfg()
    return mc, mc.Insumos(), c, d


def test_sorteio_reprodutivel_e_blocos_alinhados(ctx):
    mc, ins, c, d = ctx
    a = mc.sortear(ins, 20, 7, 123)
    b = mc.sortear(ins, 20, 7, 123)
    assert (a["w"] == b["w"]).all() and (a["dias"] == b["dias"]).all()
    # dentro de cada bloco de 7 dias, os dias de resíduo são consecutivos
    blocos = a["dias"][:, :364].reshape(20, 52, 7)
    assert (np.diff(blocos, axis=2) == 1).all()
    assert ins.dia_ok[a["dias"]].all()


def test_sem_dc_reproduz_caso_base_e_diferenca_pareada(ctx):
    mc, ins, c, d = ctx
    sd = mc.sortear(ins, 30, 7, 7)
    D, _ = mc.simular(ins, sd, c, d, [("sem_dc", "base"), ("central", "base")])
    D0, _ = mc.simular(ins, sd, c, d, [("sem_dc", "base")], ldc_override=0.0)
    a = D[D.cenario_dc == "sem_dc"].importacao_TWh.to_numpy()
    assert np.allclose(a, D0.importacao_TWh.to_numpy())
    b = D[D.cenario_dc == "central"].importacao_TWh.to_numpy()
    assert (b >= a).all()  # mais carga não reduz importação (mesmo sorteio)


def test_hidraulica_conserva_energia_diaria(ctx):
    mc, ins, c, d = ctx
    sd = mc.sortear(ins, 10, 7, 3)
    base, cfe, _, h = mc.series(ins, sd, np.arange(10), c)
    x = mc.hidraulica(ins, h, -(base + cfe * 34288), "regra_historica")
    Ed = ins.hid[h].reshape(10, 365, 24).mean(2)
    assert np.abs(x.reshape(10, 365, 24).mean(2) - Ed).max() < 0.1   # energia de cada dia conservada (MWmed)
    assert (x >= ins.hmin[h] - 1e-6).all() and (x <= ins.hmax[h] + 1e-6).all()
    plana = mc.hidraulica(ins, h, -(base + cfe * 34288), "plana")
    assert np.allclose(plana.mean(1), ins.hid[h].mean(1))


def test_residuos_recentrados_e_niveis_do_cenario(ctx):
    mc, ins, c, d = ctx
    sd = mc.sortear(ins, 300, 7, 11)
    r = ins.res[sd["dias"]].reshape(300, 8760, 4) - sd["centro"]
    assert np.abs(r.mean(axis=(0, 1))).max() < 5e-4          # resíduo sorteado com média ~0 em cada série
    k = mc.componentes(ins, sd, np.arange(300), c)
    assert np.allclose(k["L"].mean(1), c["carga"]["L_gross_sem_dc_MWmed"]["valor"])   # nível anual = cenário
    assert np.allclose(k["MMGD"].mean(1), c["mmgd"]["media_2030_MWmed"]["valor"])
    assert (k["MMGD"] >= 0).all() and (k["cfe"] >= 0).all() and (k["cfe"] <= 1).all()
    assert abs(k["cfe"].mean() / ins.B0[sd["w"]].mean() - 1) < 2e-3   # resíduo não desloca o CF médio


def test_backcast_metricas_observadas():
    import pandas as pd
    from src.sim.backcast import niveis_observados
    g = pd.DataFrame({"hid": [100.0] * 4, "ter": [0.0] * 4, "eol_bal": [200.0] * 4, "sol_central": [0.0] * 4,
                      "interc": [50.0, -100.0, -300.0, 150.0], "MMGD": [10.0] * 4, "ger_eol_fc": [100.0] * 4,
                      "pot_eol_fc": [100.0, 120.0, 100.0, 100.0], "ger_sol_fc": [1.0] * 4, "pot_sol_fc": [1.0] * 4})
    nv = niveis_observados(g)
    assert nv["obs_horas"] == 2 and np.isclose(nv["obs_TWh"], 400 / 1e6) and nv["obs_pico_MW"] == 300
    assert np.isclose(nv["L_gross"], 300 - (-50) + 10)        # carga líquida = geração − intercâmbio
    assert np.isclose(nv["eol_pot"], 105 * 2)                 # potencial levado à frota inteira (×2)
    assert np.isclose(nv["corte_eol_em_horas_de_importacao_TWh"], 20 * 2 / 1e6)


def test_max_run():
    from src.sim.montecarlo import max_run
    b = np.array([[True, True, False, True, True, True, False], [False] * 7])
    assert max_run(b).tolist() == [3, 0]
