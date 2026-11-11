"""Testes de integridade das bases intermediárias (pulados se a base não existir)."""
import pandas as pd
import pytest

from src.paths import INTERIM

H_PATH = INTERIM / "ne_hourly.parquet"
pytestmark = pytest.mark.skipif(not H_PATH.exists(), reason="rode python -m src.build.ne_hourly")


@pytest.fixture(scope="module")
def H():
    return pd.read_parquet(H_PATH).set_index("t")


def test_hourly_index_unique_and_regular(H):
    assert H.index.is_unique and H.index.is_monotonic_increasing
    assert (H.index.to_series().diff().dropna() == pd.Timedelta("1h")).all()


def test_balance_closes_2022_2025(H):
    x = H.loc[:"2025-12-31 23:00"]
    G = x[["bal_hid", "bal_ter", "bal_eol", "bal_sol"]].sum(axis=1)
    res = G - x.bal_carga - x.bal_interc
    assert res.abs().max() < 1.0  # MW


def test_mmgd_break_documented(H):
    # balanço passa a incluir MMGD em 29/04/2023 00h: antes não há MMGD em geração por usina
    assert H.gu_sol_mmgd.first_valid_index() == pd.Timestamp("2023-04-29 00:00")
    assert H.loc[:"2023-04-28 23:00", "gu_sol_mmgd"].isna().all()


def test_api_gross_equals_net_plus_mmgd(H):
    # identidade vale nos dados consolidados; horas do dia corrente são preliminares
    x = H.loc[:"2026-10-31 23:00"]
    d = x.api_cargaglobal - (x.api_cargaglobalsmmgd + x.api_cargammgd)
    assert d.abs().max() < 1.0


def test_join_cardinality_no_duplication(H):
    # junção não pode duplicar a carga: carga anual integrada = soma horária do balanço bruto
    from src.ingest import ons
    b = ons.balanco()
    ne = b[b.id_subsistema == "NE"]
    assert abs(ne.val_carga.sum() - H.bal_carga.sum()) < 1e-3 * ne.val_carga.sum() / 1e6


def test_cf_aggregate_in_range(H):
    cf = H.fc_eol_ger / H.fc_eol_cap
    assert cf.dropna().between(0, 1).all()
