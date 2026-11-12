"""Consistência da trajetória oficial de DC e do inventário."""
import pandas as pd
import yaml

from src.paths import CONFIG


def test_oficial_componentes_somam_total():
    d = pd.read_csv(CONFIG / "dc_trajetoria_oficial_ne.csv")
    r = d[d.estudo == "2a RQ PLAN 2026-2030"].pivot_table(index="ano", columns="componente", values="mwmed")
    x = r.loc[2027:2030]
    assert ((x.contratos_assinados + x.pareceres_favoraveis_50pct - x.total).abs() <= 2).all()
    assert r.loc[2030, "total"] == 2098


def test_inventario_campos_e_maturidade():
    d = pd.read_csv(CONFIG / "data_centers_ne.csv")
    assert d.id.is_unique
    assert set(d.maturidade) <= {"M0", "M1", "M2", "M3"}
    assert d.fonte_url.notna().all()
    assert set(d.verificacao) <= {"verificado", "relatado_agente", "via_busca"}


def test_cenarios_referenciam_ids_existentes():
    c = yaml.safe_load(open(CONFIG / "cenarios_dc.yaml", encoding="utf-8"))
    ids = set(pd.read_csv(CONFIG / "data_centers_ne.csv").id)
    for nome, cen in c["cenarios"].items():
        for comp in cen["componentes"]:
            assert set(comp.get("ids", [])) <= ids, nome


def test_plan_2rq_ne_base_sem_dc():
    p = pd.read_csv(CONFIG / "plan_2rq_ne.csv").set_index(["variavel", "ano"]).mwmed
    of = pd.read_csv(CONFIG / "dc_trajetoria_oficial_ne.csv")
    dc30 = of[(of.estudo == "2a RQ PLAN 2026-2030") & (of.ano == 2030) & (of.componente == "total")].mwmed.iat[0]
    c = yaml.safe_load(open(CONFIG / "cenarios.yaml", encoding="utf-8"))
    assert c["carga"]["L_gross_sem_dc_MWmed"]["valor"] == p[("carga_global", 2030)] - dc30 == 16180
    assert c["mmgd"]["media_2030_MWmed"]["valor"] == p[("mmgd_total", 2030)]
