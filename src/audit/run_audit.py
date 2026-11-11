"""Auditoria das bases (Dia 1): inventário, qualidade, reconciliação e figuras.

Uso: python -m src.audit.run_audit
Pré-requisito: python -m src.build.ne_hourly
Saídas:
- reports/quality/relatorio_qualidade.md
- reports/tables/inventario_raw.csv, cobertura.csv, reconciliacao_*.csv, cortes_anuais.csv
- reports/figures/q*.png
Nenhum modelo é treinado aqui.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from src.collect.manifest import read_manifest
from src.paths import FIGURES, INTERIM, RAW, REPORTS, TABLES, rel

QDIR = REPORTS / "quality"
BREAK_MMGD = pd.Timestamp("2023-04-29 00:00")
# Paleta categórica de referência (skill dataviz), ordem fixa por entidade
C = {"hid": "#2a78d6", "ter": "#eb6834", "eol": "#1baf7a", "sol": "#eda100",
     "mmgd": "#e87ba4", "carga": "#0b0b0b", "alt1": "#6250d6", "alt2": "#e34948"}
INK2 = "#52514e"
GRID = "#e4e3df"


def style(ax, title, ylabel):
    ax.set_title(title, loc="left", fontsize=11, color="#0b0b0b")
    ax.set_ylabel(ylabel, color=INK2, fontsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ["top", "right"]:
        ax.spines[s].set_visible(False)
    for s in ["left", "bottom"]:
        ax.spines[s].set_color("#b9b8b2")
    ax.tick_params(colors=INK2, labelsize=8)


# ---------------------------------------------------------------- inventário
def inventory() -> pd.DataFrame:
    man = {r["local_path"]: r for r in read_manifest()}
    rows = []
    for f in sorted(RAW.rglob("*")):
        if not f.is_file() or f.name.endswith(".part"):
            continue
        k = rel(f)
        n_rows = n_cols = None
        try:
            if f.suffix == ".parquet":
                md = pq.ParquetFile(f).metadata
                n_rows, n_cols = md.num_rows, md.num_columns
            elif f.suffix == ".csv":
                with open(f, encoding="utf-8", errors="replace") as fh:
                    n_rows = sum(1 for _ in fh) - 1
        except Exception as e:  # registra, não interrompe
            n_rows = f"erro: {e}"
        parts = k.split("/")
        m = man.get(k, {})
        rows.append({"arquivo": k, "fonte": parts[2] if len(parts) > 2 else "",
                     "conjunto": parts[3] if len(parts) > 4 else "(arquivos na raiz da fonte)",
                     "bytes": f.stat().st_size, "linhas": n_rows, "colunas": n_cols,
                     "periodo_ref": m.get("ref_period", "extraído de zip" if not m else ""),
                     "sha256": m.get("sha256", "")[:16], "coletado_utc": m.get("collected_at_utc", "")})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- checagens
def coverage(H: pd.DataFrame) -> pd.DataFrame:
    blocks = {
        "balanço ONS": "bal_carga", "carga verificada API": "api_cargaglobal",
        "geração por usina": "gu_eol_desp", "MMGD em geração por usina": "gu_sol_mmgd",
        "FC eólico ONS": "fc_eol_cap", "FC solar ONS": "fc_sol_cap",
        "constrained-off eólico": "coff_eol_geracao", "constrained-off solar": "coff_sol_geracao",
        "clima ERA5 (ponderado)": "w_temperature_2m_pop",
    }
    rows = []
    full = pd.date_range(H.index.min(), H.index.max(), freq="h")
    for nome, col in blocks.items():
        s = H[col]
        ok = s.dropna()
        ini, fim = ok.index.min(), ok.index.max()
        rng = full[(full >= ini) & (full <= fim)]
        rows.append({"bloco": nome, "coluna": col, "inicio": ini, "fim": fim,
                     "horas_esperadas": len(rng), "horas_presentes": int(s.loc[ini:fim].notna().sum()),
                     "lacunas_internas": int(s.loc[ini:fim].isna().sum())})
    return pd.DataFrame(rows)


def raw_checks() -> dict:
    """Duplicatas de chave e negativos nas bases brutas centrais."""
    from src.ingest import ons
    out = {}
    b = ons.balanco()
    out["balanco_duplicatas_(subsistema,t)"] = int(b.duplicated(["id_subsistema", "t"]).sum())
    vals = [c for c in b.columns if c.startswith("val_") and c != "val_intercambio"]
    out["balanco_negativos_exceto_intercambio"] = int((b[vals] < 0).sum().sum())
    out["balanco_valores_nao_numericos"] = int(b[vals].isna().sum().sum())
    cv = ons.carga_verificada()
    out["carga_api_duplicatas_t"] = int(cv.t_ini.duplicated().sum())
    out["carga_api_consistencia_nao_nula_(30min)"] = int((cv.val_consistencia.abs() > 0).sum())
    for k in ["coff_eol_usina_h", "coff_sol_usina_h"]:
        c = pd.read_parquet(INTERIM / f"ne_{k}.parquet")
        out[f"{k}_duplicatas_(usina,t)"] = int(c.duplicated(["id_ons", "t"]).sum())
        out[f"{k}_horas_incompletas_(n_sub!=2)"] = int((c.n_sub != 2).sum())
        out[f"{k}_ref<ger_(% horas-usina)"] = round(float((c.val_geracaoreferencia < c.val_geracao).mean() * 100), 1)
    fc = pd.read_parquet(INTERIM / "ne_fc_usina_h.parquet")
    out["fc_duplicatas_(usina,t)"] = int(fc.duplicated(["id_ons", "t"]).sum())
    out["fc_cf_fora_[0,1]"] = int(((fc.val_fatorcapacidade < 0) | (fc.val_fatorcapacidade > 1)).sum())
    out["fc_cf_>1.05_recalculado"] = int((fc.val_geracaoverificada > 1.05 * fc.val_capacidadeinstalada).sum())
    out["fc_capacidade_zero_ou_nula"] = int((fc.val_capacidadeinstalada.fillna(0) <= 0).sum())
    return out


def reconciliation(H: pd.DataFrame) -> dict[str, pd.DataFrame]:
    G = H[["bal_hid", "bal_ter", "bal_eol", "bal_sol"]].sum(axis=1, min_count=4)
    mm = H.gu_sol_mmgd.fillna(0)
    r = pd.DataFrame(index=H.index)
    r["res_balanco_G-L-I"] = G - H.bal_carga - H.bal_interc
    r["carga_bal_liq_menos_api_liq"] = (H.bal_carga - mm) - H.api_cargaglobalsmmgd
    r["mmgd_api_menos_mmgd_usina"] = (H.api_cargammgd - H.gu_sol_mmgd)
    r["eol_bal_menos_soma_usinas"] = H.bal_eol - H.filter(like="gu_eol").sum(axis=1, min_count=1)
    r["eol_fc_sobre_bal_%"] = 100 * H.fc_eol_ger / H.bal_eol.where(H.bal_eol > 100)
    q = r.resample("QE").agg(["mean", "std", "min", "max"]).round(1)
    q.columns = [f"{a}|{b}" for a, b in q.columns]
    bad = r["res_balanco_G-L-I"].abs() > 50
    m = bad.groupby(H.index.to_period("M")).sum()
    return {"trimestral": q, "horas_balanco_nao_fecha": m[m > 0].rename("horas").to_frame()}


def curtailment_table() -> pd.DataFrame:
    rows = []
    for s, nome in [("eol", "eólica"), ("sol", "solar")]:
        c = pd.read_parquet(INTERIM / f"ne_coff_{s}_usina_h.parquet")
        c["ano"] = c.t.dt.year
        g = c.groupby("ano")
        t = pd.DataFrame({
            "geracao_TWh": g.val_geracao.sum() / 1e6,
            "GNRa_TWh": g.val_geracaonaorealizadaapurada.sum() / 1e6,
            "ENE_TWh": g.gnr_ene.sum() / 1e6, "CNF_TWh": g.gnr_cnf.sum() / 1e6,
            "REL_TWh": g.gnr_rel.sum() / 1e6, "PAR_TWh": g.gnr_par.sum() / 1e6,
            "horas_cobertas": g.t.nunique()})
        t["corte_%_do_potencial"] = 100 * t.GNRa_TWh / (t.geracao_TWh + t.GNRa_TWh)
        t.insert(0, "fonte", nome)
        rows.append(t.reset_index())
    return pd.concat(rows).round(3)


def physics(H: pd.DataFrame) -> pd.DataFrame:
    cf = H.fc_eol_ger / H.fc_eol_cap
    cfp = (H.coff_eol_geracao + H.coff_eol_geracaonaorealizadaapurada.fillna(0)) / H.fc_eol_cap
    cfs = H.fc_sol_ger / H.fc_sol_cap
    rows = []
    for y, d in H.groupby(H.index.year):
        i = d.index
        rows.append({"ano": y,
                     "corr(vento3_100m, CF_eol_observado)": d.w_wind_speed3_100m_cap.corr(cf.loc[i]),
                     "corr(vento3_100m, CF_eol_potencial)": d.w_wind_speed3_100m_cap.corr(cfp.loc[i]),
                     "corr(GHI, CF_solar_observado)": d.w_shortwave_radiation_cap.corr(cfs.loc[i]),
                     "corr(T2m_pop, carga_liquida_api)": d.w_temperature_2m_pop.corr(d.api_cargaglobalsmmgd)})
    return pd.DataFrame(rows).round(3)


# ---------------------------------------------------------------- figuras
def figures(H: pd.DataFrame) -> list[str]:
    FIGURES.mkdir(parents=True, exist_ok=True)
    out = []
    M = H.resample("ME").mean()
    M = M[M.index < "2026-11-01"]  # novembro/2026 parcial

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(M.index, M.bal_carga / 1e3, color=C["carga"], lw=2, label="Balanço ONS (val_carga)")
    ax.plot(M.index, M.api_cargaglobal / 1e3, color=C["alt1"], lw=2, label="API: carga global (com MMGD)")
    ax.plot(M.index, M.api_cargaglobalsmmgd / 1e3, color=C["alt2"], lw=2, label="API: carga líquida de MMGD")
    ax.axvline(BREAK_MMGD, color=INK2, lw=1, ls="--")
    ax.annotate("29/04/2023: balanço passa a\nincluir MMGD na carga", (BREAK_MMGD, M.bal_carga.max() / 1e3),
                xytext=(8, -4), textcoords="offset points", fontsize=8, color=INK2, va="top")
    style(ax, "Carga do subsistema NE — média mensal", "GWmed")
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    out.append(_save(fig, "q1_carga_definicoes.png"))

    fig, ax = plt.subplots(figsize=(9, 4))
    for col, k, lab in [("bal_eol", "eol", "Eólica"), ("bal_hid", "hid", "Hidráulica"),
                        ("bal_sol", "sol", "Solar (balanço; inclui MMGD desde 29/04/2023)"),
                        ("gu_sol_mmgd", "mmgd", "MMGD estimada (geração por usina)"),
                        ("bal_ter", "ter", "Térmica")]:
        ax.plot(M.index, M[col] / 1e3, color=C[k], lw=2, label=lab)
    ax.plot(M.index, M.bal_carga / 1e3, color=C["carga"], lw=1.2, ls=":", label="Carga (balanço)")
    style(ax, "Geração do NE por fonte — média mensal", "GWmed")
    ax.legend(frameon=False, fontsize=8, ncol=2, loc="upper left")
    out.append(_save(fig, "q2_geracao_fonte.png"))

    fig, ax = plt.subplots(figsize=(9, 4))
    D = H[H.index.year == 2025]
    prof = D.groupby(D.index.hour)
    ax.plot(prof.api_cargaglobal.mean().index, prof.api_cargaglobal.mean() / 1e3, color=C["carga"], lw=2, label="Carga global (API, com MMGD)")
    ax.plot(prof.bal_eol.mean().index, prof.bal_eol.mean() / 1e3, color=C["eol"], lw=2, label="Eólica verificada")
    pot = (D.coff_eol_geracao + D.coff_eol_geracaonaorealizadaapurada.fillna(0)) * (D.bal_eol / D.coff_eol_geracao)
    ax.plot(prof.bal_eol.mean().index, pot.groupby(D.index.hour).mean() / 1e3, color=C["eol"], lw=2, ls="--", label="Eólica + corte apurado (GNRa)")
    sol_c = D.bal_sol - D.gu_sol_mmgd.fillna(0)
    ax.plot(prof.bal_sol.mean().index, sol_c.groupby(D.index.hour).mean() / 1e3, color=C["sol"], lw=2, label="Solar centralizada")
    ax.plot(prof.api_cargammgd.mean().index, prof.api_cargammgd.mean() / 1e3, color=C["mmgd"], lw=2, label="MMGD (API)")
    ax.set_xticks(range(0, 24, 3))
    ax.set_xlabel("hora (Brasília, início do intervalo)", color=INK2, fontsize=9)
    style(ax, "Perfil diário médio em 2025", "GWmed")
    ax.legend(frameon=False, fontsize=8, loc="center left", bbox_to_anchor=(0.0, 0.42))
    out.append(_save(fig, "q3_perfil_diario_2025.png"))

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, s, nome in [(axes[0], "eol", "eólica"), (axes[1], "sol", "solar")]:
        cols = [f"coff_{s}_gnr_{r}" for r in ["ene", "cnf", "rel"]]
        E = H[cols].resample("ME").sum(min_count=1) / 1e3  # MWmed·h -> GWh
        E = E[E.index < "2026-11-01"]
        bottom = np.zeros(len(E))
        for col, cc, lab in zip(cols, [C["alt1"], C["ter"], C["hid"]],
                                ["ENE (energético)", "CNF (confiabilidade)", "REL (elétrico externo)"]):
            v = E[col].fillna(0).values
            ax.bar(E.index, v, bottom=bottom, width=25, color=cc, label=lab, edgecolor="white", lw=0.5)
            bottom += v
        style(ax, f"Corte apurado (GNRa) — {nome}", "GWh/mês" if s == "eol" else "")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    out.append(_save(fig, "q4_cortes_mensais.png"))

    fig, ax = plt.subplots(figsize=(9, 4))
    x = H[H.index < "2026-01-01"]
    imp = (x.bal_interc < 0).groupby(x.index.to_period("M")).mean() * 100
    ax.plot(imp.index.to_timestamp(), imp.values, color=C["hid"], lw=2)
    style(ax, "Horas com importação líquida pelo NE (intercâmbio < 0), % do mês", "% das horas")
    out.append(_save(fig, "q5_horas_importacao.png"))

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, y in zip(axes, [2022, 2025]):
        d = H[H.index.year == y]
        cfo = d.fc_eol_ger / d.fc_eol_cap
        cfp = (d.coff_eol_geracao + d.coff_eol_geracaonaorealizadaapurada.fillna(0)) / d.fc_eol_cap
        ax.scatter(d.w_wind_speed_100m_cap, cfp, s=2, color=C["eol"], alpha=0.25, label="potencial (ger. + GNRa)", rasterized=True)
        ax.scatter(d.w_wind_speed_100m_cap, cfo, s=2, color=C["ter"], alpha=0.25, label="observado", rasterized=True)
        style(ax, f"{y}: CF eólico × vento ERA5 100 m", "CF" if y == 2022 else "")
        ax.set_xlabel("vento a 100 m ponderado pela capacidade (m/s)", color=INK2, fontsize=9)
    axes[0].legend(frameon=False, fontsize=8, markerscale=4, loc="upper left")
    out.append(_save(fig, "q6_cf_vento.png"))
    return out


def _save(fig, name) -> str:
    fig.tight_layout()
    p = FIGURES / name
    fig.savefig(p, dpi=130, facecolor="white")
    plt.close(fig)
    return rel(p)


# ---------------------------------------------------------------- relatório
def md_table(df: pd.DataFrame, index=False) -> str:
    d = df.reset_index() if index else df
    cols = [str(c) for c in d.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in d.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else (f"{v:,.3f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)) for v in r.values) + " |")
    return "\n".join(lines)


def main() -> None:
    QDIR.mkdir(parents=True, exist_ok=True)
    TABLES.mkdir(parents=True, exist_ok=True)
    H = pd.read_parquet(INTERIM / "ne_hourly.parquet").set_index("t")
    inv = inventory(); inv.to_csv(TABLES / "inventario_raw.csv", index=False)
    cov = coverage(H); cov.to_csv(TABLES / "cobertura.csv", index=False)
    chk = raw_checks()
    with open(TABLES / "checagens_brutas.json", "w", encoding="utf-8") as f:
        json.dump(chk, f, ensure_ascii=False, indent=1)
    rec = reconciliation(H)
    for k, v in rec.items():
        v.to_csv(TABLES / f"reconciliacao_{k}.csv")
    cut = curtailment_table(); cut.to_csv(TABLES / "cortes_anuais.csv", index=False)
    phy = physics(H); phy.to_csv(TABLES / "checagem_fisica.csv", index=False)
    figs = figures(H)

    inv_sum = inv.groupby(["fonte", "conjunto"]).agg(arquivos=("arquivo", "size"), MB=("bytes", lambda b: round(b.sum() / 1e6, 1))).reset_index()
    q = rec["trimestral"]
    sel = q[[c for c in q.columns if c.endswith("|mean")]]
    sel.columns = [c.split("|")[0] for c in sel.columns]
    txt = f"""# Relatório de qualidade dos dados — Dia 1

Gerado por `python -m src.audit.run_audit` em {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.
Recorte: subsistema Nordeste (ONS) — UFs AL, BA, CE, PB, PE, PI, RN, SE (o MA pertence ao subsistema Norte).
Convenção temporal da base integrada: `t` = início da hora, horário de Brasília (UTC−3, sem horário de verão no período).

## 1. Inventário de dados brutos

{md_table(inv_sum)}

Detalhe por arquivo: `reports/tables/inventario_raw.csv`; origem, URL, SHA-256 e data de coleta: `docs/manifest/manifest.csv`.

## 2. Cobertura horária na base integrada (`data/interim/ne_hourly.parquet`)

{md_table(cov)}

## 3. Checagens nas bases brutas

{md_table(pd.DataFrame(list(chk.items()), columns=["checagem", "resultado"]))}

## 4. Reconciliação (médias trimestrais, MWmed)

- `res_balanco_G-L-I`: geração (hid+ter+eol+sol) − carga − intercâmbio no balanço ONS (intercâmbio > 0 = exportação).
- `carga_bal_liq_menos_api_liq`: carga do balanço menos MMGD de "geração por usina" versus carga líquida de MMGD da API.
- `mmgd_api_menos_mmgd_usina`: diferença entre as duas estimativas de MMGD publicadas pelo ONS.
- `eol_fc_sobre_bal_%`: geração eólica do conjunto FC (usinas despachadas) sobre a eólica do balanço.

{md_table(sel, index=True)}

Horas em que o balanço não fecha (|G−L−I| > 50 MW), por mês:

{md_table(rec['horas_balanco_nao_fecha'], index=True)}

## 5. Constrained-off apurado (GNRa) por ano

{md_table(cut)}

## 6. Checagem física das variáveis meteorológicas (correlações horárias)

{md_table(phy)}

## 7. Figuras

""" + "\n".join(f"![{p}](../../{p})" for p in figs) + "\n"
    (QDIR / "relatorio_qualidade.md").write_text(txt, encoding="utf-8")
    print(f"relatório: {rel(QDIR / 'relatorio_qualidade.md')}")
    for k, v in chk.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
