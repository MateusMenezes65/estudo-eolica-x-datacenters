"""Features das funções de transferência: colunas, ausência de informação futura e resultado da ablação (decisão 55)."""
import numpy as np
import pandas as pd
import pytest

from src.paths import PROCESSED, REPORTS

CLIMA = PROCESSED / "clima_ne_1995_2026.parquet"


@pytest.mark.skipif(not CLIMA.exists(), reason="rode python -m src.features.clima_historico")
def test_colunas_dos_modelos_existem_e_sem_repeticao():
    from src.sim import sinteticos as sint
    D = sint.dados_treino()
    for nome, s in sint.MODELOS.items():
        assert len(set(s["ex"])) == len(s["ex"]) and set(s["ex"]) <= set(D.columns), nome
        assert "dia_ano" not in s["ex"], nome                     # piora o erro fora da amostra em B0 e C0
    assert len(sint.POLOS_EOL) == 16


@pytest.mark.skipif(not CLIMA.exists(), reason="rode python -m src.features.clima_historico")
def test_media_movel_da_temperatura_nao_usa_o_futuro():
    C = pd.read_parquet(CLIMA, columns=["t", "temperature_2m", "temp_mm24"]).iloc[:400]
    x = C.temperature_2m.to_numpy()
    for i in [5, 30, 399]:
        assert C.temp_mm24.iat[i] == pytest.approx(x[max(0, i - 23):i + 1].mean())


@pytest.mark.skipif(not CLIMA.exists(), reason="rode python -m src.features.clima_historico")
def test_vento_por_polo_fecha_com_a_media_ponderada():
    from src.features.clima_historico import fixed_weights
    from src.sim.sinteticos import POLOS_EOL
    C = pd.read_parquet(CLIMA).iloc[::5000]
    w = fixed_weights()["wind"]
    media = sum(C[f"ws_{p}"] * v for p, v in w.items()) / w.sum()
    assert sorted(POLOS_EOL) == sorted(f"ws_{p}" for p in w.index)
    assert np.allclose(media, C.wind_speed_100m, atol=1e-4)


@pytest.mark.skipif(not (REPORTS / "models" / "ablacao_features.csv").exists(), reason="rode python -m src.models.ablacao")
def test_ablacao_especificacao_adotada_melhor_que_a_anterior():
    A = pd.read_csv(REPORTS / "models" / "ablacao_features.csv")
    ad = A[A.variante == "adotada"]
    assert set(ad.modelo) == {"A0", "B0", "C0", "E0"}
    assert (ad.significativa == "melhor").all() and (ad["dif_RMSE_%"] < 0).all()
    assert (A[(A.variante == "anterior sem dia_ano") & A.modelo.isin(["B0", "C0"])].significativa == "melhor").all()
