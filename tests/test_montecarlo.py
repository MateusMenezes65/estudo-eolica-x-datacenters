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
    mes = np.repeat(mc.mes_dos_dias(365), 24)
    for m in range(12):                                       # e em cada mês (centro mensal, decisão 56)
        assert np.abs(r[:, mes == m].mean(axis=(0, 1))).max() < 4e-3, m
    k = mc.componentes(ins, sd, np.arange(300), c)
    assert np.allclose(k["L"].mean(1), c["carga"]["L_gross_sem_dc_MWmed"]["valor"])   # nível anual = cenário
    assert np.allclose(k["MMGD"].mean(1), c["mmgd"]["media_2030_MWmed"]["valor"])
    assert (k["MMGD"] >= 0).all() and (k["cfe"] >= 0).all() and (k["cfe"] <= 1).all()
    assert abs(k["cfe"].mean() / ins.B0[sd["w"]].mean() - 1) < 2e-3   # resíduo não desloca o CF médio


def test_centro_mensal_e_exato_no_esperado(ctx):
    mc, ins, c, d = ctx
    cm = mc.centro_residuos(ins, 7)
    assert cm.shape == (12, 24, 4) and np.isfinite(cm).all()
    # valor esperado do sorteio, mês a mês, calculado diretamente dos candidatos
    dm, mes, e = ins.res.mean(axis=1), mc.mes_dos_dias(365), np.zeros((365, 4))
    for k, L, cand in mc.candidatos(ins, 7):
        for i in range(L):
            e[k + i] = dm[cand + i].mean(axis=0)
    for m in range(12):
        assert np.allclose(e[mes == m].mean(axis=0), cm[m].mean(axis=0))
    assert (np.ptp(cm[:, :, [0, 2]], axis=1) < 1e-15).all()                    # carga e eólica: um valor por mês
    assert mc.expandir_centro(cm, 365).shape == (8760, 4) and mc.expandir_centro(cm, 366).shape == (8784, 4)
    assert np.allclose(mc.expandir_centro(cm, 366)[59 * 24:60 * 24], cm[1])    # 29/02 usa o centro de fevereiro


def test_recentramento_nao_cria_geracao_solar_a_noite(ctx):
    mc, ins, c, d = ctx
    sd = mc.sortear(ins, 100, 7, 4)
    k, k0 = (mc.componentes(ins, sd, np.arange(100), c, o) for o in (None, {"sem_residuo": True}))
    hora = np.tile(np.arange(24), 365)
    noite = (hora <= 3) | (hora >= 21)
    cap = c["solar"]["capacidade_2030_MW"]["valor"]
    assert k["cfs"][:, noite].mean() * cap < 15                                        # MW (antes da correção: ~57)
    # a MMGD noturna é a da própria série do ONS (~1,8% da média); o resíduo não a desloca
    assert abs(k["MMGD"][:, noite].mean() - k0["MMGD"][:, noite].mean()) < 10


def test_pool_de_residuos_cobre_dois_anos_de_jan_a_out(ctx):
    mc, ins, c, d = ctx
    import pandas as pd
    R = pd.read_parquet(PROCESSED / "residuos_pool.parquet")
    n = R.t.dt.normalize().drop_duplicates().dt.month.value_counts()
    assert (n.loc[list(range(1, 11))] >= 2 * 28).all()


def test_validacao_nao_usa_residuos_do_proprio_ano(ctx):
    import types
    mc, ins, c, d = ctx
    for ano in [2024, 2025, 2026]:
        r = types.SimpleNamespace(res=ins.res, dia_ok=mc.dias_fora_do_ano(ins, ano), doy_pool=ins.doy_pool, nd=304,
                                  anos=np.array([ano]), anos_h=np.array([ano]))
        sd = mc.sortear(r, 20, 7, 1)
        assert (ins.ano_pool[sd["dias"]] != ano).all()
        assert all(len(cand) >= 10 for _, _, cand in mc.candidatos(r, 7))     # ainda há candidatos em todo bloco


def test_nivel_mmgd_sem_distorcao_nas_pontas():
    import pandas as pd
    from src.sim.sinteticos import nivel_mmgd
    # crescimento exponencial com sazonalidade anual: a forma não deve depender da posição na série
    t = pd.date_range("2022-01-01", "2026-10-31 23:00", freq="h")
    anos = (t - t[0]) / pd.Timedelta(days=365)
    s = pd.Series(1000 * 1.2 ** anos * (1 + 0.2 * np.sin(2 * np.pi * anos)), index=t)
    forma = s / nivel_mmgd(s)
    assert np.abs(forma / forma.mean() - (1 + 0.2 * np.sin(2 * np.pi * anos))).max() < 0.02


def test_ic_da_amostra_de_anos_nao_encolhe_com_mais_sorteios():
    import pandas as pd
    from src.sim.montecarlo import ic_amostra_de_anos
    r = np.random.default_rng(0)
    ew, eh = r.normal(0, 2, 31), r.normal(0, 1, 4)                  # efeito fixo de cada ano
    def caso(n):
        w, h = r.integers(0, 31, n), r.integers(0, 4, n)
        sem = 3 + ew[w] + eh[h]
        linhas = [pd.DataFrame({"sorteio": np.arange(n), "ano_clima": w, "ano_hidro": h, "cenario_eolico": "base",
                                "cenario_dc": dc, "importacao_TWh": sem + d}) for dc, d in [("sem_dc", 0.0), ("central", 2.0)]]
        return ic_amostra_de_anos(pd.concat(linhas), 500)
    a, b = caso(2000), caso(20000)
    larg = lambda x: np.diff(x["importacao_central"]["ic95_TWh"])[0]
    assert larg(a) == pytest.approx(larg(b), rel=0.05)              # limitado pelos 31 × 4 anos
    assert b["importacao_central"]["erro_padrao_simulacao_TWh"] < 0.4 * a["importacao_central"]["erro_padrao_simulacao_TWh"]
    assert a["efeito_dc_central"]["ic95_TWh"] == pytest.approx([2.0, 2.0])     # efeito constante: sem incerteza
    assert a["n_anos_clima"] == 31 and a["n_anos_hidro"] == 4


def test_backcast_metricas_observadas():
    import pandas as pd
    from src.sim.backcast import niveis_observados
    g = pd.DataFrame({"hid": [100.0] * 4, "ter": [0.0] * 4, "eol_bal": [200.0] * 4, "sol_central": [0.0] * 4,
                      "interc": [50.0, -100.0, -300.0, 150.0], "MMGD": [10.0] * 4, "ger_eol_fc": [100.0] * 4,
                      "pot_eol_fc": [100.0, 120.0, 100.0, 100.0], "ger_sol_fc": [1.0] * 4, "pot_sol_fc": [1.0] * 4})
    nv = niveis_observados(g)
    assert np.isclose(nv["obs_real_TWh"], 400 / 1e6)          # intercâmbio: 100 + 300
    # potencial: a hora com 20 MW de corte (×2 na frota inteira) importaria 60 em vez de 100
    assert nv["obs_horas"] == 2 and np.isclose(nv["obs_TWh"], 360 / 1e6) and nv["obs_pico_MW"] == 300
    assert np.isclose(nv["importacao_evitada_se_gerado_TWh"], 40 / 1e6)
    assert np.isclose(nv["L_gross"], 300 - (-50) + 10)        # carga líquida = geração − intercâmbio
    assert np.isclose(nv["eol_pot"], 200 + 20 * 2 / 4)        # balanço + corte levado à frota inteira (×2)
    assert np.isclose(nv["corte_eol_em_horas_de_importacao_TWh"], 20 * 2 / 1e6)


def test_max_run():
    from src.sim.montecarlo import max_run
    b = np.array([[True, True, False, True, True, True, False], [False] * 7])
    assert max_run(b).tolist() == [3, 0]
