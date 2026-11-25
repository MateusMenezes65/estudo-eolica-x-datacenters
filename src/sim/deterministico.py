"""Simulador determinístico do balanço horário do NE em 2030.

Uso: python -m src.sim.deterministico
Saídas: reports/sim/resultados_2030.csv, compensacao_eolica_2030.csv, resumo.md, figuras s*.png

Para cada ano climático y (2022–2025), cenário de data centers e cenário eólico:
  L_gross(t) = forma_y(t) × L̄_gross,2030 sem DC          (2ª RQ PLAN 2026-2030)
  MMGD(t)    = forma_MMGD,y(t) × MMGD̄_2030                (2ª RQ PLAN 2026-2030)
  G_c(t)     = hid_y(t) + ter_y(t) + k_eol,y·CF_eol,y(t)·Cap_eol + k_sol,y·CF_sol,y(t)·Cap_sol
  M(t)       = G_c(t) − [L_gross(t) − MMGD(t) + L_DC]      (regra 6; MMGD como geração distribuída)
  importação = max(0, −M); excedente = max(0, M)
k_*,y = fator de frota: média do modelo de transferência treinado na frota recente,
aplicado ao clima de y, dividida pela média observada em y (preserva a variabilidade
horária observada e corrige o nível para a frota atual).
Mesmos perfis em todos os cenários (comparações pareadas). Margem negativa não é déficit
de suprimento: é necessidade de importação do restante do SIN.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from src.paths import CONFIG, FIGURES, PROCESSED, REPORTS, rel

OUT = REPORTS / "sim"


# ------------------------------------------------------------------ entradas
def load_cfg():
    with open(CONFIG / "cenarios.yaml", encoding="utf-8") as f:
        c = yaml.safe_load(f)
    with open(CONFIG / "cenarios_dc.yaml", encoding="utf-8") as f:
        d = yaml.safe_load(f)
    return c, d


def fleet_factors(X: pd.DataFrame) -> pd.DataFrame:
    """Fatores de frota por ano climático: as mesmas funções de transferência B0/C0 do Monte Carlo
    (features e clima de pesos fixos de src.sim.sinteticos), treinadas na frota recente."""
    from src.sim import sinteticos as sint
    rows = {}
    D = sint.dados_treino()
    preds = {}
    for k, nome in [("eol", "B0"), ("sol", "C0")]:
        ex = sint.MODELOS[nome]["ex"]
        ok = D[ex].notna().all(axis=1)
        p = pd.Series(sint.fit(D, nome).predict(D.loc[ok, ex]), index=D.t[ok])
        preds[k] = pd.Series(p.reindex(X.t).to_numpy(), index=X.index)
    for y, g in X.groupby("ano"):
        cfe = g.cf_eol_pot
        cfs = g.cf_sol_pot.fillna(g.cf_sol_obs)
        rows[y] = {"k_eol": preds["eol"][g.index].mean() / cfe.mean(),
                   "k_sol": preds["sol"][g.index].mean() / cfs.mean(),
                   "cf_eol_pot_obs": cfe.mean(), "cf_sol_usado": cfs.mean(),
                   "sol_fonte": "pot" if g.cf_sol_pot.notna().all() else "obs/pot"}
    return pd.DataFrame(rows).T


def profiles(X: pd.DataFrame, y: int, c: dict, ff: pd.DataFrame, mmgd_MWmed: float | None = None,
             L_gross_MWmed: float | None = None, hidraulica_plana: bool = False) -> pd.DataFrame:
    g = X[X.ano == y].set_index("t")
    p = pd.DataFrame(index=g.index)
    Lg = L_gross_MWmed if L_gross_MWmed is not None else c["carga"]["L_gross_sem_dc_MWmed"]["valor"]
    p["L_gross"] = g.L_gross / g.L_gross.mean() * Lg
    mm = mmgd_MWmed if mmgd_MWmed is not None else c["mmgd"]["media_2030_MWmed"]["valor"]
    p["MMGD"] = g.MMGD / g.MMGD.mean() * mm
    p["hid"] = g.hid if not hidraulica_plana else pd.Series(g.hid.mean(), index=g.index)
    p["ter"] = g.ter
    p["cf_eol"] = g.cf_eol_pot * ff.loc[y, "k_eol"]
    p["cf_sol"] = g.cf_sol_pot.fillna(g.cf_sol_obs) * ff.loc[y, "k_sol"]
    return p


def l_dc_2030(cen: str, d: dict, ano: int = 2030) -> tuple[float, pd.DataFrame]:
    """Carga incremental média de DC no ano `ano` (padrão 2030), em MWmed, e sua decomposição."""
    of = pd.read_csv(CONFIG / "dc_trajetoria_oficial_ne.csv")
    of = of[(of.estudo == "2a RQ PLAN 2026-2030") & (of.ano == ano)].set_index("componente").mwmed
    if "pareceres_favoraveis_50pct" not in of and {"total", "contratos_assinados"} <= set(of.index):
        # 2026: rótulo ilegível no slide 71; parecer (já a 50%) = total − contratos (112 − 98)
        of["pareceres_favoraveis_50pct"] = of["total"] - of["contratos_assinados"]
    inv = pd.read_csv(CONFIG / "data_centers_ne.csv").set_index("id")
    pi = d["parametros_inventario"]
    parts = []
    for comp in d["cenarios"][cen]["componentes"]:
        if comp["fonte"] == "oficial":
            parts.append({"parcela": f"oficial:{comp['componente']}x{comp['peso']}",
                          "MWmed": float(of[comp["componente"]]) * comp["peso"]})
        else:
            for i in comp["ids"]:
                r = inv.loc[i]
                entrada = pd.Timestamp(r.data_info) + pd.DateOffset(months=36)  # entrada_sem_data
                meses = pd.date_range(f"{ano}-01-01", f"{ano}-12-01", freq="MS") + pd.Timedelta(days=14)
                idade = np.clip(np.asarray((meses - entrada).days, dtype=float) / 30.44, 0, None)
                frac = np.minimum(idade / pi["rampa_meses"]["central"], 1.0).mean()
                mw = float(r.potencia_mw) * pi["utilizacao_madura"]["central"] * frac
                parts.append({"parcela": f"inventario:{i}", "MWmed": mw})
    P = pd.DataFrame(parts)
    return float(P.MWmed.sum()) if len(P) else 0.0, P


# ------------------------------------------------------------------ balanço e métricas
def margin(p: pd.DataFrame, cap_eol: float, cap_sol: float, l_dc: float) -> pd.Series:
    G = p.hid + p.ter + p.cf_eol * cap_eol + p.cf_sol * cap_sol
    return G - (p.L_gross - p.MMGD + l_dc)


def max_run(mask: pd.Series) -> int:
    run = best = 0
    for v in mask.values:
        run = run + 1 if v else 0
        best = max(best, run)
    return best


def balance_metrics(M: pd.Series, c: dict) -> dict:
    imp = (-M).clip(lower=0)
    exc = M.clip(lower=0)
    lim_exp = c["intercambio"]["limite_exportacao_MW"]["valor"]
    out = {
        "horas": len(M),
        "importacao_TWh": imp.sum() / 1e6,                # MWmed × 1 h = MWh
        "horas_importacao": int((M < 0).sum()),
        "importacao_pico_MW": imp.max(),
        "importacao_p95_MW": float(np.percentile(imp, 95)),
        "importacao_p95_horas_importadoras_MW": float(np.percentile(imp[imp > 0], 95)) if (imp > 0).any() else 0.0,
        "maior_sequencia_importacao_h": max_run(M < 0),
        "excedente_TWh": exc.sum() / 1e6,
        "horas_excedente": int((M > 0).sum()),
        "excedente_acima_limite_exp_TWh": (M - lim_exp).clip(lower=0).sum() / 1e6,
        "horas_acima_limite_exp": int((M > lim_exp).sum()),
    }
    for lim in c["intercambio"]["limites_importacao_sensibilidade_MW"]["valores"]:
        out[f"horas_import_acima_{lim//1000}GW"] = int((imp > lim).sum())
    return out


def compensation(p, c, cap_eol, cap_sol, l_dc, ref: dict, M_dc: pd.Series) -> dict:
    """Capacidade eólica adicional que compensa L_DC, por critério (busca por bisseção)."""
    out = {}
    cf_med = p.cf_eol.mean()
    out["dW_energia_anual_MW"] = l_dc / cf_med if l_dc > 0 else 0.0
    exc0 = margin(p, cap_eol, cap_sol, 0).clip(lower=0)
    out["absorcao_excedente_%"] = 100 * np.minimum(exc0, l_dc).sum() / (l_dc * len(p)) if l_dc > 0 else np.nan
    crit = {"importacao_anual": lambda m: (-m).clip(lower=0).sum() / 1e6 - ref["importacao_TWh"],
            "horas_importacao": lambda m: (m < 0).sum() - ref["horas_importacao"],
            "p95_importacao": lambda m: np.percentile((-m).clip(lower=0), 95) - ref["importacao_p95_MW"]}
    b = c["compensacao_eolica"]["busca_MW"]
    for nome, f in crit.items():
        if l_dc <= 0 or f(M_dc) <= 0:
            out[f"dW_{nome}_MW"] = 0.0
            continue
        lo, hi = b["min"], b["max"]
        if f(margin(p, cap_eol + hi, cap_sol, l_dc)) > 0:
            out[f"dW_{nome}_MW"] = np.inf   # não compensa dentro da faixa de busca
            continue
        while hi - lo > b["tolerancia"]:
            mid = (lo + hi) / 2
            if f(margin(p, cap_eol + mid, cap_sol, l_dc)) > 0:
                lo = mid
            else:
                hi = mid
        out[f"dW_{nome}_MW"] = hi
    return out


# ------------------------------------------------------------------ execução
def run(X: pd.DataFrame | None = None):
    c, d = load_cfg()
    if X is None:
        X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
        X = X[X.t < "2026-11-01"].reset_index(drop=True)
    ff = fleet_factors(X)
    cap_sol = c["solar"]["capacidade_2030_MW"]["valor"]
    rows, comp_rows, dc_parts = [], [], []
    for cen_dc in d["cenarios"]:
        ldc, P = l_dc_2030(cen_dc, d)
        dc_parts.append(P.assign(cenario_dc=cen_dc))
        for y in c["anos_climaticos_calibracao"]:
            p = profiles(X, y, c, ff)
            for cen_w, wv in c["eolica"]["capacidade_2030_MW"].items():
                cap_eol = wv["valor"]
                M = margin(p, cap_eol, cap_sol, ldc)
                met = balance_metrics(M, c)
                rows.append({"cenario_dc": cen_dc, "L_DC_MWmed": ldc, "cenario_eolico": cen_w,
                             "cap_eol_MW": cap_eol, "ano_climatico": y, **met})
    R = pd.DataFrame(rows)
    # compensação: referência = sem_dc no mesmo ano climático e mesmo cenário eólico
    for (cen_dc, cen_w, y), g in R.groupby(["cenario_dc", "cenario_eolico", "ano_climatico"]):
        if cen_dc == "sem_dc":
            continue
        ref = R[(R.cenario_dc == "sem_dc") & (R.cenario_eolico == cen_w) & (R.ano_climatico == y)].iloc[0].to_dict()
        p = profiles(X, y, c, ff)
        cap_eol = c["eolica"]["capacidade_2030_MW"][cen_w]["valor"]
        ldc = g.L_DC_MWmed.iat[0]
        comp_rows.append({"cenario_dc": cen_dc, "cenario_eolico": cen_w, "ano_climatico": y, "L_DC_MWmed": ldc,
                          **compensation(p, c, cap_eol, cap_sol, ldc, ref, margin(p, cap_eol, cap_sol, ldc))})
    return R, pd.DataFrame(comp_rows), ff, pd.concat(dc_parts)


def sensibilidades(X: pd.DataFrame, c: dict, d: dict, ff: pd.DataFrame) -> pd.DataFrame:
    """Sensibilidades univariadas sobre o caso central (DC central, eólica base), pareadas por ano."""
    cap_sol = c["solar"]["capacidade_2030_MW"]["valor"]
    cap_eol = c["eolica"]["capacidade_2030_MW"]["base"]["valor"]
    ldc = l_dc_2030("central", d)[0]
    pde = c["carga"]["sensibilidade_pde"]
    casos = {"referencia": {}, "sem_dc": {"ldc": 0.0},
             "base_PDE_2035_(dc_embutido_descontado)": {"L": pde["L_gross_MWmed"], "ldc": ldc - pde["desconto_dc_embutido_MWmed"]},
             "MMGD_baixa": {"mm": c["mmgd"]["faixa_sensibilidade_MWmed"]["valores"][0]},
             "MMGD_alta": {"mm": c["mmgd"]["faixa_sensibilidade_MWmed"]["valores"][1]},
             "carga_-5%": {"L": c["carga"]["L_gross_sem_dc_MWmed"]["valor"] * 0.95},
             "carga_+5%": {"L": c["carga"]["L_gross_sem_dc_MWmed"]["valor"] * 1.05},
             "hidraulica_plana": {"hp": True}}
    rows = []
    for nome, k in casos.items():
        for y in c["anos_climaticos_calibracao"]:
            p = profiles(X, y, c, ff, mmgd_MWmed=k.get("mm"), L_gross_MWmed=k.get("L"), hidraulica_plana=k.get("hp", False))
            m = balance_metrics(margin(p, cap_eol, cap_sol, k.get("ldc", ldc)), c)
            rows.append({"caso": nome, "ano_climatico": y, **m})
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    R, C, ff, P = run()
    R.to_csv(OUT / "resultados_2030.csv", index=False)
    C.to_csv(OUT / "compensacao_eolica_2030.csv", index=False)
    ff.to_csv(OUT / "fatores_frota.csv")
    P.to_csv(OUT / "decomposicao_L_DC_2030.csv", index=False)
    ordem = ["sem_dc", "conservador", "central", "alto"]
    S = (R.groupby(["cenario_dc", "cenario_eolico"])
         [["L_DC_MWmed", "importacao_TWh", "horas_importacao", "importacao_pico_MW", "importacao_p95_MW",
           "excedente_TWh", "excedente_acima_limite_exp_TWh", "horas_acima_limite_exp"]]
         .agg(["mean", "min", "max"]).round(2))
    S.to_csv(OUT / "resumo_cenarios_2030.csv")
    # figura: importação anual por cenário (média e faixa entre anos climáticos)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=False)
    cores = {"baixa": "#eb6834", "base": "#2a78d6", "alta": "#1baf7a"}
    for ax, met, lab in [(axes[0], "importacao_TWh", "Importação necessária (TWh/ano)"),
                         (axes[1], "horas_importacao", "Horas com importação (h/ano)")]:
        for k, (w, cor) in enumerate(cores.items()):
            g = R[R.cenario_eolico == w].groupby("cenario_dc")[met].agg(["mean", "min", "max"]).reindex(ordem)
            x = np.arange(len(ordem)) + (k - 1) * 0.25
            ax.bar(x, g["mean"], width=0.23, color=cor, label=f"eólica {w}")
            ax.errorbar(x, g["mean"], yerr=[g["mean"] - g["min"], g["max"] - g["mean"]], fmt="none", ecolor="#52514e", lw=1)
        ax.set_xticks(range(len(ordem)), ordem)
        ax.set_title(lab, loc="left", fontsize=10)
        ax.grid(axis="y", color="#e4e3df"); ax.set_axisbelow(True)
        [ax.spines[s].set_visible(False) for s in ["top", "right"]]
    axes[0].legend(frameon=False, fontsize=8)
    fig.suptitle("NE 2030 — média e faixa entre anos climáticos 2022–2025", x=0.01, ha="left", fontsize=11)
    fig.tight_layout(); fig.savefig(FIGURES / "s1_importacao_cenarios_2030.png", dpi=130); plt.close(fig)
    c, d = load_cfg()
    X = pd.read_parquet(PROCESSED / "ne_features_h.parquet")
    X = X[X.t < "2026-11-01"].reset_index(drop=True)
    SE = sensibilidades(X, c, d, ff)
    SE.to_csv(OUT / "sensibilidades_2030.csv", index=False)
    print(SE.groupby("caso", sort=False)[["importacao_TWh", "horas_importacao", "importacao_p95_MW"]].mean().round(2).to_string())
    print(ff.round(3).to_string())
    print(S.xs("mean", axis=1, level=1).to_string())
    print(C.groupby(["cenario_dc", "cenario_eolico"]).mean(numeric_only=True).round(0).to_string())


if __name__ == "__main__":
    main()
