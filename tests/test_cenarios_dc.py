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
