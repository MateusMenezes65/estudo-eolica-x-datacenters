"""Perfis horários sintéticos de 2030 para anos meteorológicos 1995–2025 (papel 2 dos modelos).

Uso: python -m src.sim.sinteticos
Saídas (data/processed/): sinteticos_2030.parquet, residuos_pool.parquet, hidrotermica_pool.parquet
Relatórios: reports/sim/validacao_sinteticos.csv, extrapolacao_clima.csv; figura s2.

Funções de transferência (HGB, hiperparâmetros de src.models.backtest), com o clima de pesos
fixos (src.features.clima_historico):
- A0  carga bruta / média do ano  ~ hora, dia da semana, mês, feriado nacional, ponto facultativo,
                                    temperatura (da hora e média de 24 h), GHI nas capitais
- E0  MMGD / nível anual          ~ hora, mês, GHI nas capitais e nos polos
- B0  CF eólico potencial         ~ hora, mês, vento a 100 m em cada um dos 16 polos (frota 2024-07..2026-10)
- C0  CF solar potencial          ~ hora, mês, GHI nos polos, temperatura (idem)
As features foram escolhidas por ablação fora da amostra (src.models.ablacao, decisão 55).
Para 2030, o clima do ano y é alinhado ao calendário de 2030 por (mês, dia, hora); 29/02 é
descartado. As previsões são médias condicionais; a variabilidade não explicada é recomposta
no Monte Carlo com resíduos FORA DA AMOSTRA (validação cruzada por mês) da janela comum
2024-07..2026-10, reamostrados em blocos conjuntos (preserva a dependência entre as séries). A janela
ia só até 2025-12; a extensão dá dois anos, em vez de um, a janeiro–junho, a época em que o NE mais
importa (decisão 56).
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from src.features.build import calendar_features
from src.ingest import weather
from src.models.backtest import CAL, HGB
from src.paths import FIGURES, PROCESSED, REPORTS

ANOS_CLIMA = list(range(1995, 2026))
JANELA_RES = ("2024-07-01", "2026-10-31 23:00")
POLOS_EOL = [f"ws_{p}" for p in weather.points().query("kind == 'wind'").point_id.sort_values()]
MODELOS = {
    "A0": dict(alvo="L_shape", ex=["hora", "dia_semana", "mes", "feriado_nacional", "ponto_facultativo",
                                   "temperature_2m", "temp_mm24", "shortwave_radiation_pop"],
               treino=("2022-01-01", "2025-12-31 23:00")),
    "E0": dict(alvo="M_shape", ex=["hora", "mes", "shortwave_radiation_pop", "shortwave_radiation"],
               treino=("2022-01-01", "2026-10-31 23:00")),
    "B0": dict(alvo="cf_eol_pot", ex=["hora", "mes"] + POLOS_EOL, treino=("2024-07-01", "2026-10-31 23:00")),
    "C0": dict(alvo="cf_sol_pot", ex=["hora", "mes", "shortwave_radiation", "temperature_2m"],
               treino=("2024-07-01", "2026-10-31 23:00")),
}
LIMITES = {"A0": (None, None), "E0": (0.0, None), "B0": (0.0, 1.0), "C0": (0.0, 1.0)}


def dados_treino(extras: list[str] | None = None) -> pd.DataFrame:
    F = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    F = F[F.t < "2026-11-01"]
    Cl = pd.read_parquet(PROCESSED / "clima_ne_1995_2026.parquet")
    keep = ["t", "ano", "L_gross", "MMGD", "cf_eol_pot", "cf_sol_pot", "hid", "ter"] + CAL + (extras or [])
    D = F[keep].merge(Cl, on="t", how="inner")
    D["L_shape"] = D.L_gross / D.groupby("ano").L_gross.transform("mean")
    D["M_shape"] = D.MMGD.values / nivel_mmgd(D.set_index("t").MMGD).values
    return D


def nivel_mmgd(s: pd.Series) -> pd.Series:
    """Nível da MMGD: média móvel centrada de 365 dias; nas pontas, onde a janela não cabe inteira, o nível
    segue a taxa de crescimento dos 365 dias vizinhos.

    Truncar a janela nas pontas misturava crescimento e estação (média só de metade do ano) e distorcia a
    forma em até 12% no início de 2022 e no fim de 2026 (decisão 56).
    """
    m = s.rolling("365D", center=True, min_periods=24 * 364).mean()
    ano, t0, t1 = pd.Timedelta(days=365), m.first_valid_index(), m.last_valid_index()
    g0, g1 = m[t0 + ano] / m[t0], m[t1] / m[t1 - ano]
    antes, depois = m.index < t0, m.index > t1
    m[antes] = m[t0] * g0 ** ((m.index[antes] - t0) / ano)
    m[depois] = m[t1] * g1 ** ((m.index[depois] - t1) / ano)
    return m


def clima_2030(Cl: pd.DataFrame, ano: int) -> pd.DataFrame:
    """Clima do ano `ano` no calendário de 2030 (8.760 h), chaveado por (mês, dia, hora)."""
    c = Cl[Cl.t.dt.year == ano].copy()
    c = c[~((c.t.dt.month == 2) & (c.t.dt.day == 29))]
    t30 = pd.date_range("2030-01-01", "2030-12-31 23:00", freq="h")
    key = lambda s: s.dt.strftime("%m%d%H")
    c = c.set_index(key(c.t)).drop(columns="t")
    out = c.reindex(key(pd.Series(t30)).values)
    assert out.notna().all().all(), f"clima incompleto para {ano}"
    out.index = t30
    return out


def calendario_2030() -> pd.DataFrame:
    t30 = pd.Series(pd.date_range("2030-01-01", "2030-12-31 23:00", freq="h"))
    return calendar_features(t30).set_index(t30.values)


def fit(D: pd.DataFrame, nome: str, excluir_mes: pd.Period | None = None):
    s = MODELOS[nome]
    m = D.t.between(*s["treino"]) & D[s["alvo"]].notna() & D[s["ex"]].notna().all(axis=1)
    if excluir_mes is not None:
        m &= D.t.dt.to_period("M") != excluir_mes
    return HistGradientBoostingRegressor(**HGB).fit(D.loc[m, s["ex"]], D.loc[m, s["alvo"]])


def residuos_fora_amostra(D: pd.DataFrame) -> pd.DataFrame:
    """Resíduos por validação cruzada mensal na janela comum (cada mês previsto sem ele no treino).

    A forma da carga (A0) é carga ÷ média do ano; 2026 só vai até outubro, então a média de jan–out não é a
    do ano. Nos anos incompletos o nível é ajustado para o resíduo ter média zero no período (a forma, não o
    nível, é o que se reamostra).
    """
    horas_ano = D.groupby("ano").size()
    incompletos = [a for a, n in horas_ano.items() if n < 8760]
    J = D[D.t.between(*JANELA_RES)].copy()
    R = pd.DataFrame({"t": J.t})
    for nome, s in MODELOS.items():
        r = pd.Series(np.nan, index=J.index)
        for per in J.t.dt.to_period("M").unique():
            mdl = fit(D, nome, excluir_mes=per)
            mm = (J.t.dt.to_period("M") == per) & J[s["ex"]].notna().all(axis=1)
            r[mm] = mdl.predict(J.loc[mm, s["ex"]])
        y = J[s["alvo"]].copy()
        if nome == "A0":
            for a in incompletos:
                k = (J.ano == a) & y.notna() & r.notna()
                y[k] *= r[k].mean() / y[k].mean()
        R[nome] = (y - r).values
    return R.dropna().reset_index(drop=True)


def main(argv=None) -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--refazer-residuos", action="store_true")
    refazer_residuos = ap.parse_args(argv).refazer_residuos
    D = dados_treino()
    Cl = pd.read_parquet(PROCESSED / "clima_ne_1995_2026.parquet")
    cal30 = calendario_2030()
    modelos = {n: fit(D, n) for n in MODELOS}

    # ---- perfis sintéticos (sem resíduo) para 1995–2025 no calendário de 2030
    rows = []
    for ano in ANOS_CLIMA:
        c = clima_2030(Cl, ano).join(cal30)
        out = pd.DataFrame({"t": c.index, "ano_clima": ano})
        for n, s in MODELOS.items():
            out[n] = modelos[n].predict(c[s["ex"]])
        rows.append(out)
    S = pd.concat(rows, ignore_index=True)
    S["A0"] = S.A0 / S.groupby("ano_clima").A0.transform("mean")   # forma com média 1
    S["E0"] = S.E0 / S.groupby("ano_clima").E0.transform("mean")
    S.to_parquet(PROCESSED / "sinteticos_2030.parquet")

    # ---- resíduos fora da amostra (pool conjunto) e pool hidrotérmico 2022–2025 no calendário 2030
    rp = PROCESSED / "residuos_pool.parquet"
    if refazer_residuos or not rp.exists():
        R = residuos_fora_amostra(D)
        R.to_parquet(rp)
    else:
        R = pd.read_parquet(rp)
    Hp = []
    for ano in [2022, 2023, 2024, 2025]:
        h = D[(D.ano == ano)][["t", "hid", "ter"]].copy()
        h = h[~((h.t.dt.month == 2) & (h.t.dt.day == 29))]
        assert len(h) == 8760, (ano, len(h))
        Hp.append(pd.DataFrame({"t": pd.date_range("2030-01-01", "2030-12-31 23:00", freq="h"),
                                "ano_hidro": ano, "hid": h.hid.values, "ter": h.ter.values}))
    pd.concat(Hp).to_parquet(PROCESSED / "hidrotermica_pool.parquet")

    # ---- validação: extrapolação (fora da faixa de treino) e aderência. As colunas sem "_fora" usam os modelos
    # finais, que viram parte desses anos no treino; as "_fora" são a validação cruzada mensal dos resíduos
    ext = []
    for n, s in MODELOS.items():
        tr = D[D.t.between(*s["treino"])]
        for v in [x for x in s["ex"] if x in Cl.columns]:
            lo, hi = tr[v].min(), tr[v].max()
            for per, sub in [("1995-2021", Cl[Cl.t.dt.year.between(1995, 2021)]), ("2022-2025", Cl[Cl.t.dt.year.between(2022, 2025)])]:
                ext.append({"modelo": n, "variavel": v, "periodo": per, "min_treino": lo, "max_treino": hi,
                            "pct_abaixo": 100 * (sub[v] < lo).mean(), "pct_acima": 100 * (sub[v] > hi).mean()})
    pd.DataFrame(ext).round(3).to_csv(REPORTS / "sim" / "extrapolacao_clima.csv", index=False)

    val = []
    obs = D.set_index("t")
    for ano in [2022, 2023, 2024, 2025]:
        o = obs[obs.ano == ano]
        o = o[~((o.index.month == 2) & (o.index.day == 29))]
        s = S[S.ano_clima == ano].reset_index(drop=True)
        # A0 é validado no calendário real do ano (dia da semana e feriados importam);
        # B0/C0 não usam calendário e são comparados no alinhamento mês-dia-hora.
        pa = modelos["A0"].predict(o[MODELOS["A0"]["ex"]])
        for n, col in [("A0", "L_shape"), ("B0", "cf_eol_pot"), ("C0", "cf_sol_pot")]:
            y = o[col].values
            p = pa / pa.mean() if n == "A0" else s[n].values
            ok = ~np.isnan(y)
            if ok.sum() < 1000:
                continue
            rp = R[n].values
            # mesma comparação FORA da amostra (validação cruzada mensal dos resíduos), nas horas do pool
            j = R[R.t.dt.year == ano].set_index("t")[n]
            yf = obs[col].reindex(j.index)
            pf = yf - j
            fora = ({"n_fora": len(j), "MAE_fora": j.abs().mean(), "corr_fora": np.corrcoef(pf, yf)[0, 1],
                     "dp_fora_com_residuo": np.sqrt(pf.var() + j.var()), "dp_obs_fora": yf.std()} if len(j) > 1000 else {})
            val.append({"modelo": n, "ano": ano, "media_obs": y[ok].mean(), "media_sint": p[ok].mean(),
                        "MAE": np.abs(p[ok] - y[ok]).mean(), "corr": np.corrcoef(p[ok], y[ok])[0, 1],
                        "dp_obs": y[ok].std(), "dp_sint": p[ok].std(),
                        "dp_sint_com_residuo_aprox": np.sqrt(p[ok].var() + rp.var()), **fora})
    V = pd.DataFrame(val).round(4)
    V.to_csv(REPORTS / "sim" / "validacao_sinteticos.csv", index=False)

    # ---- figura: clima eólico e CF sintético por ano meteorológico
    a = S.groupby("ano_clima")[["B0", "C0"]].mean()
    v3 = Cl[Cl.t.dt.year.between(1995, 2025)].groupby(Cl.t.dt.year).wind_speed3_100m.mean()
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.bar(a.index, a.B0, color="#1baf7a", width=0.7)
    ax.axhline(a.B0.mean(), color="#52514e", lw=1, ls="--")
    for y in [2022, 2023, 2024, 2025]:
        ax.bar(y, a.B0[y], color="#2a78d6", width=0.7)
    ax.set_ylim(a.B0.min() * 0.9, a.B0.max() * 1.03)
    ax.set_title("CF eólico potencial sintético de 2030 por ano meteorológico (frota atual; azul = anos com dados ONS)",
                 loc="left", fontsize=10)
    ax.grid(axis="y", color="#e4e3df"); ax.set_axisbelow(True)
    [ax.spines[k].set_visible(False) for k in ["top", "right"]]
    fig.tight_layout(); fig.savefig(FIGURES / "s2_cf_eolico_anos_meteorologicos.png", dpi=130); plt.close(fig)

    print("CF eólico sintético por ano:", a.B0.round(3).to_dict())
    print("resíduos (desvio):", R[list(MODELOS)].std().round(4).to_dict(), "n =", len(R))
    print(V.to_string())
    print(pd.read_csv(REPORTS / "sim" / "extrapolacao_clima.csv").query("pct_abaixo>0 or pct_acima>0").to_string())


if __name__ == "__main__":
    main()
