"""Trajetórias anuais 2026–2030 dos níveis de cenário (simulador interativo e anexo do relatório).

Uso: python -m src.sim.trajetorias
Saída: reports/sim/trajetorias_2026_2030.csv
Regras: config/cenarios_anuais.yaml. Para 2030 os valores são os de config/cenarios.yaml e
config/cenarios_dc.yaml (os resultados do estudo não mudam); as regras anuais são conferidas
contra eles (tests/test_anos.py).

Por ano:
- carga sem DC = carga global do NE (2ª RQ do PLAN, slide 79) − DC de Rede Básica (slide 71);
- MMGD = 2ª RQ do PLAN (slide 60);
- capacidade (média anual): operação no SIGA (em 2026 ponderada pela data de entrada) +
  construção × fração do ano em operação (entrada uniforme em 2027–2029, toda em 2030);
  eólica alta = base + expansão indicativa acumulada do PDE no ano;
- data centers: os mesmos componentes dos cenários de 2030, com os valores do ano.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from src.paths import CONFIG, REPORTS
from src.sim.deterministico import l_dc_2030, load_cfg

OUT = REPORTS / "sim" / "trajetorias_2026_2030.csv"
CENARIOS_DC = ["sem_dc", "conservador", "central", "alto"]
CENARIOS_EOL = ["baixa", "base", "alta"]


def load_cfg_anual() -> dict:
    with open(CONFIG / "cenarios_anuais.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def siga_ne(a: dict) -> pd.DataFrame:
    """Usinas eólicas e solares fotovoltaicas do subsistema NE no SIGA (MW, fase, data de entrada)."""
    from src.paths import ROOT
    S = pd.read_csv(ROOT / a["capacidade"]["fonte_siga"], sep=";", encoding="utf-8", dtype=str)
    S = S[S.SigUFPrincipal.isin(a["capacidade"]["ufs_subsistema_ne"]) & S.SigTipoGeracao.isin(["EOL", "UFV"])]
    return pd.DataFrame({"tipo": S.SigTipoGeracao.map({"EOL": "eol", "UFV": "sol"}),
                         "fase": S.DscFaseUsina,
                         "MW": S.MdaPotenciaOutorgadaKw.str.replace(".", "", regex=False).str.replace(",", ".").astype(float) / 1000,
                         "entrada": pd.to_datetime(S.DatEntradaOperacao, errors="coerce")})


def fracao_no_ano(ano: int, inicio: str, fim: str) -> float:
    """Fração média, ao longo do ano, de uma entrada uniforme entre `inicio` e `fim` (0 antes, 1 depois)."""
    t = pd.date_range(f"{ano}-01-01", f"{ano}-12-31 23:00", freq="h")
    i0, i1 = pd.Timestamp(inicio), pd.Timestamp(fim)
    return float(np.clip(np.asarray((t - i0) / (i1 - i0), dtype=float), 0, 1).mean())


def operacao_media(S: pd.DataFrame, tipo: str, ano: int) -> float:
    """Capacidade em operação, média do ano: entradas dentro do ano contam pela fração após a data."""
    op = S[(S.tipo == tipo) & (S.fase == "Operação")]
    ini, fim = pd.Timestamp(f"{ano}-01-01"), pd.Timestamp(f"{ano + 1}-01-01")
    frac = ((fim - op.entrada.clip(lower=ini, upper=fim)) / (fim - ini)).fillna(1.0)   # sem data = já operava
    return float((op.MW * frac).sum())


def pde_indicativa(a: dict, ano: int) -> float:
    p = a["capacidade"]["pde_indicativa"]
    P = pd.read_csv(CONFIG / "pde2035_extraido.csv")
    v = P[(P.variavel == p["variavel"]) & (P.escopo == p["escopo"]) & (P.cenario == p["cenario"]) & (P.ano == ano)].valor
    return float(v.iat[0]) if len(v) else 0.0


def plan(var: str, ano: int) -> float:
    P = pd.read_csv(CONFIG / "plan_2rq_ne.csv")
    return float(P[(P.variavel == var) & (P.ano == ano)].mwmed.iat[0])


def calcular(regras_2030: bool = False) -> pd.DataFrame:
    """Tabela por ano. `regras_2030=True` devolve 2030 pelas regras anuais (para conferência);
    por padrão 2030 traz os valores de config/cenarios.yaml (os do estudo)."""
    c, d = load_cfg()
    a = load_cfg_anual()
    S = siga_ne(a)
    k = a["capacidade"]["construcao"]
    rows = []
    for ano in a["anos"]:
        frac = fracao_no_ano(ano, k["inicio"], k["fim"])
        r = {"ano": ano, "fracao_construcao": frac}
        dc_total = l_dc_2030("central", d, ano)[0]
        r["carga_global_MWmed"] = plan("carga_global", ano)
        r["L_gross_sem_dc_MWmed"] = r["carga_global_MWmed"] - dc_total
        r["MMGD_MWmed"] = plan("mmgd_total", ano)
        for tipo in ["eol", "sol"]:
            r[f"operacao_{tipo}_MW"] = operacao_media(S, tipo, ano)
            r[f"construcao_{tipo}_MW"] = float(S[(S.tipo == tipo) & (S.fase == "Construção")].MW.sum())
        r["cap_sol_MW"] = r["operacao_sol_MW"] + r["construcao_sol_MW"] * frac
        r["cap_eol_baixa_MW"] = r["operacao_eol_MW"]
        r["cap_eol_base_MW"] = r["operacao_eol_MW"] + r["construcao_eol_MW"] * frac
        r["pde_indicativa_eol_MW"] = pde_indicativa(a, ano)
        r["cap_eol_alta_MW"] = r["cap_eol_base_MW"] + r["pde_indicativa_eol_MW"]
        for cen in CENARIOS_DC:
            r[f"L_DC_{cen}_MWmed"] = l_dc_2030(cen, d, ano)[0]
        for col in ["cap_sol_MW", "cap_eol_baixa_MW", "cap_eol_base_MW", "cap_eol_alta_MW"]:
            r[col] = float(round(r[col]))                  # capacidades em MW inteiros, como no cenário de 2030
        r["fonte_2030"] = "regras anuais"
        if ano == a["ano_referencia"] and not regras_2030:   # valores do estudo (inalterados)
            r["L_gross_sem_dc_MWmed"] = c["carga"]["L_gross_sem_dc_MWmed"]["valor"]
            r["MMGD_MWmed"] = c["mmgd"]["media_2030_MWmed"]["valor"]
            r["cap_sol_MW"] = c["solar"]["capacidade_2030_MW"]["valor"]
            for w in CENARIOS_EOL:
                r[f"cap_eol_{w}_MW"] = c["eolica"]["capacidade_2030_MW"][w]["valor"]
            r["fonte_2030"] = "config/cenarios.yaml"
        rows.append(r)
    return pd.DataFrame(rows)


def config_ano(c: dict, T: pd.DataFrame, ano: int) -> dict:
    """Cópia de config/cenarios.yaml com os níveis do ano (para as funções do Monte Carlo)."""
    import copy
    r = T.set_index("ano").loc[ano]
    cy = copy.deepcopy(c)
    cy["ano_alvo"] = ano
    cy["carga"]["L_gross_sem_dc_MWmed"]["valor"] = float(r.L_gross_sem_dc_MWmed)
    cy["mmgd"]["media_2030_MWmed"]["valor"] = float(r.MMGD_MWmed)
    cy["solar"]["capacidade_2030_MW"]["valor"] = float(r.cap_sol_MW)
    for w in CENARIOS_EOL:
        cy["eolica"]["capacidade_2030_MW"][w]["valor"] = float(r[f"cap_eol_{w}_MW"])
    return cy


def main() -> None:
    T = calcular()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    T.round(3).to_csv(OUT, index=False)
    cols = ["ano", "L_gross_sem_dc_MWmed", "MMGD_MWmed", "cap_sol_MW", "cap_eol_baixa_MW", "cap_eol_base_MW",
            "cap_eol_alta_MW"] + [f"L_DC_{c}_MWmed" for c in CENARIOS_DC]
    print(T[cols].round(0).to_string(index=False))
    R = calcular(regras_2030=True).set_index("ano").loc[2030]
    print("2030 pelas regras anuais:", {k: round(float(R[k]), 1) for k in cols[1:7]})


if __name__ == "__main__":
    main()
