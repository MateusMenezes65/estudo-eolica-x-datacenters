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
    rel = np.abs(x.mean(1) / ins.hid[h].mean(1) - 1)
    assert rel.max() < 0.01                       # energia anual conservada a menos de 1%
    assert (x >= ins.hmin[h] - 1e-6).all() and (x <= ins.hmax[h] + 1e-6).all()
    plana = mc.hidraulica(ins, h, -(base + cfe * 34288), "plana")
    assert np.allclose(plana.mean(1), ins.hid[h].mean(1))


def test_max_run():
    from src.sim.montecarlo import max_run
    b = np.array([[True, True, False, True, True, True, False], [False] * 7])
    assert max_run(b).tolist() == [3, 0]
