"""Trajetórias 2026–2030, motor por ano (inclui 2028 bissexto) e dados do simulador interativo."""
import numpy as np
import pandas as pd
import pytest

from src.paths import PROCESSED

precisa_perfis = pytest.mark.skipif(not (PROCESSED / "sinteticos_anos.parquet").exists(),
                                    reason="rode python -m src.sim.anos")


@pytest.fixture(scope="module")
def traj():
    from src.sim.trajetorias import calcular
    return calcular().set_index("ano"), calcular(regras_2030=True).set_index("ano")


def test_2030_igual_ao_estudo_e_regras_reproduzem(traj):
    from src.sim.deterministico import load_cfg
    c, d = load_cfg()
    T, Tr = traj
    r = T.loc[2030]
    assert r.L_gross_sem_dc_MWmed == c["carga"]["L_gross_sem_dc_MWmed"]["valor"] == 16180
    assert r.MMGD_MWmed == c["mmgd"]["media_2030_MWmed"]["valor"]
    assert r.cap_sol_MW == c["solar"]["capacidade_2030_MW"]["valor"]
    for w in ["baixa", "base", "alta"]:
        assert r[f"cap_eol_{w}_MW"] == c["eolica"]["capacidade_2030_MW"][w]["valor"]
        assert abs(Tr.loc[2030, f"cap_eol_{w}_MW"] - r[f"cap_eol_{w}_MW"]) <= 1     # regra anual = cenário de 2030 (arredondado)
    assert abs(Tr.loc[2030, "cap_sol_MW"] - r.cap_sol_MW) < 50                       # 13.493 arredondado a 13.500
    assert Tr.loc[2030, "L_gross_sem_dc_MWmed"] == r.L_gross_sem_dc_MWmed            # 18.278 − 2.098
    assert r.L_DC_central_MWmed == 2098 and r.L_DC_conservador_MWmed == 1886


def test_trajetorias_coerentes(traj):
    T, _ = traj
    assert list(T.index) == [2026, 2027, 2028, 2029, 2030]
    assert T.loc[2026, "L_gross_sem_dc_MWmed"] == 14182 - 112                        # PLAN 2ª RQ menos DC do ano
    assert T.loc[2028, "MMGD_MWmed"] == 2152
    assert T.loc[2026, "L_DC_alto_MWmed"] == 98 + 2 * 14                              # parecer de 2026 = 112 − 98
    for col in ["cap_sol_MW", "cap_eol_baixa_MW", "cap_eol_base_MW", "cap_eol_alta_MW", "L_gross_sem_dc_MWmed", "MMGD_MWmed",
                "L_DC_central_MWmed"]:
        assert (T[col].diff().dropna() >= 0).all(), col                              # trajetórias não decrescentes
    assert (T.cap_eol_baixa_MW <= T.cap_eol_base_MW).all() and (T.cap_eol_base_MW <= T.cap_eol_alta_MW).all()
    assert (T.L_DC_sem_dc_MWmed == 0).all()
    assert ((T.L_DC_conservador_MWmed <= T.L_DC_central_MWmed) & (T.L_DC_central_MWmed <= T.L_DC_alto_MWmed)).all()
    assert T.loc[2026, "cap_eol_alta_MW"] == T.loc[2026, "cap_eol_baixa_MW"]           # 2026: sem construção nem PDE


def test_fracao_construcao():
    from src.sim.trajetorias import fracao_no_ano
    f = [fracao_no_ano(a, "2027-01-01", "2030-01-01") for a in [2026, 2027, 2028, 2029, 2030]]
    assert f[0] == 0 and f[-1] == 1
    assert f[1] == pytest.approx(1 / 6, abs=1e-3) and f[2] == pytest.approx(0.5, abs=1e-3) and f[3] == pytest.approx(5 / 6, abs=1e-3)


def test_29_de_fevereiro():
    from src.sim.anos import calendario, inserir_29fev
    a = np.arange(8760.0)[None]
    b = inserir_29fev(a, 2028)
    assert b.shape == (1, 8784) and len(calendario(2028)) == 8784
    assert (b[0, 59 * 24:60 * 24] == a[0, 58 * 24:59 * 24]).all()                    # 29/02 = 28/02
    assert (b[0, 60 * 24:] == a[0, 59 * 24:]).all()                                  # 01/03 em diante preservado
    assert inserir_29fev(a, 2027) is a


@precisa_perfis
def test_bissexto_conserva_energia_e_dc_pareado():
    from src.sim import montecarlo as mc
    from src.sim.anos import InsumosAno, simular_ano
    from src.sim.deterministico import load_cfg
    from src.sim.trajetorias import calcular, config_ano
    c, _ = load_cfg()
    ins = InsumosAno(2028)
    assert ins.nd == 366 and ins.A0.shape[1] == 8784
    assert np.allclose(ins.A0.mean(axis=1), 1)
    sd = mc.sortear(ins, 8, 7, 5)
    assert sd["dias"].shape == (8, 366) and ins.dia_ok[sd["dias"]].all()
    cy = config_ano(c, calcular(), 2028)
    base, cfe, _, h = mc.series(ins, sd, np.arange(8), cy)
    assert base.shape == (8, 8784)
    x = mc.hidraulica(ins, h, -(base + cfe * 34000), "regra_historica")
    assert np.abs(x.reshape(8, 366, 24).mean(2) - ins.hid[h].reshape(8, 366, 24).mean(2)).max() < 0.1
    k = mc.componentes(ins, sd, np.arange(8), cy)
    assert np.allclose(k["L"].mean(1), cy["carga"]["L_gross_sem_dc_MWmed"]["valor"])
    D = simular_ano(ins, cy, {"sem_dc": 0.0, "x": 0.0, "y": 600.0}, sd, ws=["base"])
    a, b, y = (D[D.cenario_dc == n].importacao_TWh.to_numpy() for n in ["sem_dc", "x", "y"])
    assert np.array_equal(a, b) and (y >= a).all()                                  # DC zero reproduz o caso-base


@precisa_perfis
def test_insumos_2030_iguais_ao_estudo():
    from src.sim import montecarlo as mc
    from src.sim.anos import InsumosAno
    a, b = InsumosAno(2030), mc.Insumos()
    for k in ["A0", "E0", "B0", "C0", "hid", "ter", "hmin", "hmax", "beta"]:
        assert np.array_equal(getattr(a, k), getattr(b, k)), k
    assert a.nd == 365


@precisa_perfis
@pytest.mark.parametrize("ano,cen_w,modo", [(2028, "alta", "regra_historica"), (2027, "base", "plana"), (2030, "base", "regra_historica")])
def test_motor_da_pagina_igual_ao_monte_carlo(ano, cen_w, modo):
    """O motor de referência do simulador (o que a página reproduz) = funções do Monte Carlo."""
    from src.report.simulador import motor, niveis
    from src.sim import montecarlo as mc
    from src.sim.anos import InsumosAno, calendario
    from src.sim.deterministico import load_cfg
    from src.sim.trajetorias import calcular, config_ano
    c, _ = load_cfg()
    T = calcular()
    i30, ins = InsumosAno(2030), InsumosAno(ano)
    sd = mc.sortear(ins, 3, 7, 99)
    mes = calendario(2030).month.to_numpy() - 1
    prim = [int(np.flatnonzero(mes == m)[0]) for m in range(12)]
    I = {f"A0_{ano}": ins.A0, "E0": i30.E0, "B0": i30.B0, "C0": i30.C0, "hid": i30.hid, "ter": i30.ter,
         "res": np.nan_to_num(i30.res, nan=0.0).reshape(-1), "hmin": i30.hmin[:, prim], "hmax": i30.hmax[:, prim], "beta": i30.beta}
    cy = config_ano(c, T, ano)
    base, cfe, _, h = mc.series(ins, sd, np.arange(3), cy)
    cap = cy["eolica"]["capacidade_2030_MW"][cen_w]["valor"]
    G = base + cfe * cap + mc.hidraulica(ins, h, -(base + cfe * cap), modo)
    for j in range(3):
        out = motor(I, ano, int(sd["w"][j]), int(sd["h"][j]), sd["dias"][j], sd["centro"], niveis(T)[ano], cen_w, modo)
        assert np.allclose(out["M0"], G[j], rtol=0, atol=1e-6)


def test_codificacao_ida_e_volta():
    from src.report.simulador import codificar, decodificar
    x = np.random.default_rng(1).normal(size=(3, 500)) * 0.3 + 1
    y = decodificar(codificar(x, 1e-4))
    assert y.shape == x.shape and np.abs(y - x).max() <= 0.5e-4 + 1e-12
