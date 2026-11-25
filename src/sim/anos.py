"""Monte Carlo do balanço horário do NE para cada ano de 2026 a 2030 (simulador interativo).

Uso: python -m src.sim.anos [--n 2000]
Pré-requisitos: src.sim.sinteticos (perfis de 2030, resíduos, pool hidrotérmico) e
src.sim.trajetorias (níveis de cada ano).
Saídas: data/processed/sinteticos_anos.parquet (forma de carga A0 no calendário de 2026–2029),
data/processed/mc_anos_sorteios.parquet, reports/sim/anos_mc_resumo.csv (anual),
reports/sim/anos_mc_mensal.csv (faixas por mês) e reports/sim/anos_config.json.

Mesmo método do Monte Carlo de 2030 (src/sim/montecarlo.py), com os níveis do ano
(config/cenarios_anuais.yaml) e o calendário do ano:
- a forma de carga A0 depende do calendário (dia da semana, feriados): é prevista pela mesma
  função de transferência para cada ano-alvo; em 2030 usa-se o arquivo do estudo;
- MMGD, CF eólico e solar não usam calendário: os perfis de 2030 valem para qualquer ano;
- 2028 é bissexto (8.784 h): 29/02 repete o clima, os perfis e o ano hidrotérmico de 28/02, e a
  energia anual integra as 8.784 horas;
- os sorteios usam a mesma semente do estudo; em 2030 o resultado é idêntico ao do estudo
  (conferido aqui e em tests/test_anos.py).
Os anos intermediários não alteram os resultados nem as conclusões do estudo (2030).
"""
from __future__ import annotations

import argparse
import calendar
import json

import numpy as np
import pandas as pd

from src.features.build import calendar_features
from src.paths import PROCESSED, REPORTS
from src.sim import montecarlo as mc
from src.sim import sinteticos as sint
from src.sim.deterministico import load_cfg
from src.sim.trajetorias import CENARIOS_DC, CENARIOS_EOL, config_ano, load_cfg_anual

OUT = REPORTS / "sim"
ARQ_A0 = PROCESSED / "sinteticos_anos.parquet"
METRICAS = ["importacao_TWh", "horas_importacao", "importacao_p95_MW", "importacao_pico_MW",
            "maior_sequencia_importacao_h", "excedente_TWh", "excedente_acima_limite_exp_TWh",
            "horas_acima_limite_exp", "horas_import_acima_8GW"]


def calendario(ano: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{ano}-01-01", f"{ano}-12-31 23:00", freq="h")


def inserir_29fev(a: np.ndarray, ano: int) -> np.ndarray:
    """Série horária no calendário de 365 dias (último eixo) → calendário de `ano` (29/02 = 28/02)."""
    if not calendar.isleap(ano):
        return a
    i0, i1 = 58 * 24, 59 * 24                                   # horas de 28/02
    return np.concatenate([a[..., :i1], a[..., i0:i1], a[..., i1:]], axis=-1)


def chave(t: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    s = pd.Series(t)
    return s.dt.strftime("%m%d%H").to_numpy()


def clima_ano(Cl: pd.DataFrame, ano_clima: int, ano_alvo: int) -> pd.DataFrame:
    """Clima de `ano_clima` no calendário de `ano_alvo`, por (mês, dia, hora); 29/02 do alvo usa 28/02."""
    c = Cl[Cl.t.dt.year == ano_clima]
    c = c[~((c.t.dt.month == 2) & (c.t.dt.day == 29))]
    c = c.set_index(chave(c.t)).drop(columns="t")
    t = calendario(ano_alvo)
    k = np.char.replace(chave(t).astype(str), "0229", "0228")
    out = c.reindex(k)
    assert out.notna().all().all(), f"clima incompleto: {ano_clima} → {ano_alvo}"
    out.index = t
    return out


def perfis_carga(anos_alvo: list[int]) -> tuple[pd.DataFrame, float]:
    """Forma de carga A0 (média 1 por ano) para cada ano meteorológico no calendário de cada ano-alvo.

    Devolve também a maior diferença entre o A0 refeito no calendário de 2030 e o do estudo
    (conferência de que o modelo é o mesmo).
    """
    D = sint.dados_treino()
    mdl = sint.fit(D, "A0")
    ex = sint.MODELOS["A0"]["ex"]
    Cl = pd.read_parquet(PROCESSED / "clima_ne_1995_2026.parquet")
    rows = []
    for ano in anos_alvo + [2030]:
        t = calendario(ano)
        cal = calendar_features(pd.Series(t)).set_index(t)
        for w in sint.ANOS_CLIMA:
            p = mdl.predict(clima_ano(Cl, w, ano).join(cal)[ex])
            rows.append(pd.DataFrame({"t": t, "ano_alvo": ano, "ano_clima": w, "A0": p / p.mean()}))
    A = pd.concat(rows, ignore_index=True)
    S = pd.read_parquet(PROCESSED / "sinteticos_2030.parquet")
    a30 = A[A.ano_alvo == 2030].pivot(index="t", columns="ano_clima", values="A0")
    s30 = S.pivot(index="t", columns="ano_clima", values="A0")[a30.columns]
    dif = float(np.abs(a30.to_numpy() - s30.to_numpy()).max())
    return A[A.ano_alvo != 2030].reset_index(drop=True), dif


class InsumosAno(mc.Insumos):
    """Insumos do Monte Carlo no calendário de `ano` (2030 = insumos do estudo, sem alteração)."""

    def __init__(self, ano: int, anos_clima=None):
        super().__init__(anos_clima)
        self.ano = ano
        if ano == 2030:
            return
        A = pd.read_parquet(ARQ_A0)
        A = A[A.ano_alvo == ano].pivot(index="t", columns="ano_clima", values="A0")
        self.A0 = A[self.anos].to_numpy().T
        self.E0, self.B0, self.C0 = (inserir_29fev(x, ano) for x in (self.E0, self.B0, self.C0))
        self.hid, self.ter = inserir_29fev(self.hid, ano), inserir_29fev(self.ter, ano)
        self.hmin, self.hmax = inserir_29fev(self.hmin, ano), inserir_29fev(self.hmax, ano)
        self.nd = len(calendario(ano)) // 24
        assert self.A0.shape[1] == self.nd * 24 == self.B0.shape[1] == self.hid.shape[1]


def simular_ano(ins: mc.Insumos, cy: dict, ldc: dict, sd: dict, ws=CENARIOS_EOL, modo="regra_historica",
                lote: int = 250, mascara: np.ndarray | None = None, mensal: bool = False):
    """Métricas anuais por sorteio para os cenários eólicos `ws` e de DC `ldc` ({nome: MWmed}).

    `mascara` (booleana por hora) restringe as métricas a um subconjunto de horas (backtest);
    `mensal=True` devolve também importação e excedente por mês (TWh).
    """
    rows, mens = [], []
    n = len(sd["w"])
    mes = calendario(ins.ano).month.to_numpy() if mensal else None
    for i0 in range(0, n, lote):
        idx = np.arange(i0, min(n, i0 + lote))
        base, cfe, _, h = mc.series(ins, sd, idx, cy)
        for w in ws:
            cap = cy["eolica"]["capacidade_2030_MW"][w]["valor"]
            G = base + cfe * cap + mc.hidraulica(ins, h, -(base + cfe * cap), modo)
            for cen, l in ldc.items():
                M = G - l
                Mm = M[:, mascara] if mascara is not None else M
                rows.append(pd.DataFrame({"sorteio": idx, "ano_clima": ins.anos[sd["w"][idx]],
                                          "ano_hidro": ins.anos_h[sd["h"][idx]], "cenario_dc": cen,
                                          "cenario_eolico": w, "L_DC_MWmed": l, **mc.metricas(Mm, cy)}))
                if mensal:
                    for m in range(1, 13):
                        sel = (mes == m) & (mascara if mascara is not None else True)
                        if not sel.any():
                            continue
                        mens.append(pd.DataFrame({"sorteio": idx, "cenario_dc": cen, "cenario_eolico": w, "mes": m,
                                                  "importacao_TWh": np.clip(-M[:, sel], 0, None).sum(1) / 1e6,
                                                  "excedente_TWh": np.clip(M[:, sel], 0, None).sum(1) / 1e6,
                                                  "horas_importacao": (M[:, sel] < 0).sum(1)}))
    D = pd.concat(rows, ignore_index=True)
    return (D, pd.concat(mens, ignore_index=True)) if mensal else D


def niveis_dc(T: pd.DataFrame, ano: int) -> dict:
    r = T.set_index("ano").loc[ano]
    return {c: float(r[f"L_DC_{c}_MWmed"]) for c in CENARIOS_DC}


def resumo(D: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (ano, a, b), g in D.groupby(["ano", "cenario_dc", "cenario_eolico"], sort=False):
        for m in METRICAS:
            s = g[m].to_numpy()
            p = np.percentile(s, [5, 25, 50, 75, 95])
            rows.append({"ano": ano, "cenario_dc": a, "cenario_eolico": b, "metrica": m, "media": s.mean(),
                         "p5": p[0], "p25": p[1], "p50": p[2], "p75": p[3], "p95": p[4]})
    return pd.DataFrame(rows)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--so-perfis", action="store_true")
    a = ap.parse_args(argv)
    cfa = load_cfg_anual()
    n = a.n or cfa["simulador"]["n_sorteios_mc"]
    anos = cfa["anos"]
    from src.sim.trajetorias import calcular
    T = calcular()

    A, dif = perfis_carga([y for y in anos if y != 2030])
    A.to_parquet(ARQ_A0)
    print(f"A0 refeito no calendário de 2030 × estudo: diferença máxima {dif:.2e}")
    if a.so_perfis:
        return

    c, _ = load_cfg()
    todos, mensais, info = [], [], {"n": n, "bloco_dias": 7, "semente": mc.SEMENTE, "dif_max_A0_2030_refeito": dif, "anos": {}}
    for ano in anos:
        ins = InsumosAno(ano)
        sd = mc.sortear(ins, n, 7, mc.SEMENTE)
        cy = config_ano(c, T, ano)
        D, Dm = simular_ano(ins, cy, niveis_dc(T, ano), sd, mensal=True)
        todos.append(D.assign(ano=ano))
        q = lambda p: (lambda s: np.percentile(s, p))
        mensais.append(Dm.groupby(["cenario_dc", "cenario_eolico", "mes"], sort=False)
                       .agg(importacao_p5_TWh=("importacao_TWh", q(5)), importacao_p50_TWh=("importacao_TWh", q(50)),
                            importacao_p95_TWh=("importacao_TWh", q(95)), excedente_p5_TWh=("excedente_TWh", q(5)),
                            excedente_p50_TWh=("excedente_TWh", q(50)), excedente_p95_TWh=("excedente_TWh", q(95)))
                       .reset_index().assign(ano=ano))
        info["anos"][ano] = {"horas": int(ins.nd * 24),
                             "centro_residuos_mensal": [[round(float(x), 6) for x in v] for v in sd["centro_mensal"]]}
        g = D[(D.cenario_dc == "central") & (D.cenario_eolico == "base")].importacao_TWh
        print(f"{ano}: importação central/base média {g.mean():.2f} TWh [{np.percentile(g, 5):.2f}–{np.percentile(g, 95):.2f}]")
    D = pd.concat(todos, ignore_index=True)
    D.to_parquet(PROCESSED / "mc_anos_sorteios.parquet")

    # conferência: 2030 idêntico ao Monte Carlo do estudo (mesmos sorteios)
    ref = PROCESSED / "mc_sorteios.parquet"
    if ref.exists() and n == 2000:
        R = pd.read_parquet(ref)
        x = D[D.ano == 2030].merge(R, on=["sorteio", "cenario_dc", "cenario_eolico"], suffixes=("", "_estudo"))
        info["dif_max_importacao_2030_vs_estudo_TWh"] = float(np.abs(x.importacao_TWh - x.importacao_TWh_estudo).max())
        info["linhas_comparadas_2030"] = int(len(x))
        print(f"2030 × estudo: {len(x)} linhas, diferença máxima {info['dif_max_importacao_2030_vs_estudo_TWh']:.2e} TWh")

    S = resumo(D)
    S.round(4).to_csv(OUT / "anos_mc_resumo.csv", index=False)
    pd.concat(mensais, ignore_index=True).round(4).to_csv(OUT / "anos_mc_mensal.csv", index=False)
    with open(OUT / "anos_config.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    print(S[S.metrica == "importacao_TWh"].pivot_table(index=["cenario_dc", "cenario_eolico"], columns="ano",
                                                       values="media").round(2).to_string())


if __name__ == "__main__":
    main()
