"""Constrói as bases intermediárias horárias do subsistema NE (data/interim/).

Uso: python -m src.build.ne_hourly

Saídas (todas com `t` = início da hora, horário de Brasília):
- ne_balanco_h.parquet        balanço ONS (carga, geração por fonte, intercâmbio)
- ne_carga_api_h.parquet      carga verificada (API) agregada de 30 min para hora
- ne_geracao_fonte_h.parquet  geração por usina somada por fonte e grupo (MMGD x centralizada)
- ne_fc_usina_h.parquet       FC por usina/conjunto eólico e solar (ONS)
- ne_coff_{eol,sol}_usina_h.parquet  constrained-off por usina, agregado para hora
- ne_weather_h.parquet        ERA5 por ponto, alinhado à hora ONS (formato longo)
- ne_hourly.parquet           tabela integrada (uma linha por hora)
Nenhum valor é imputado aqui; lacunas permanecem NaN e são reportadas na auditoria.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.ingest import ons, weather
from src.paths import CONFIG, INTERIM

COFF_VALS = ["val_geracao", "val_geracaolimitada", "val_disponibilidade",
             "val_geracaoreferencia", "val_geracaoreferenciafinal",
             "val_geracaonaorealizadaapurada"]


def build_balanco() -> pd.DataFrame:
    b = ons.balanco()
    ne = b[b.id_subsistema == "NE"].drop(columns=["id_subsistema", "nom_subsistema", "_arquivo"])
    ne = ne.rename(columns={"val_gerhidraulica": "bal_hid", "val_gertermica": "bal_ter",
                            "val_gereolica": "bal_eol", "val_gersolar": "bal_sol",
                            "val_carga": "bal_carga", "val_intercambio": "bal_interc"})
    return ne.sort_values("t").reset_index(drop=True)


def build_carga_api() -> pd.DataFrame:
    cv = ons.carga_verificada("NE")
    cols = [c for c in cv.columns if c.startswith("val_")]
    h = ons.to_hourly_mean(cv, "t_ini", cols)
    return h.rename(columns={c: "api_" + c[4:] for c in cols})


def build_geracao_fonte() -> pd.DataFrame:
    g = ons.geracao_usina("NE")
    g["grupo"] = np.where(g.cod_modalidadeoperacao.str.contains("MMGD", na=False), "mmgd",
                          np.where(g.cod_modalidadeoperacao.str.contains("Tipo III", na=False),
                                   "tipo3", "desp"))
    a = g.groupby(["t", "fonte", "grupo"]).val_geracao.sum().unstack(["fonte", "grupo"])
    a.columns = [f"gu_{f.lower()}_{gr}" for f, gr in a.columns]
    n = g.groupby("t").size().rename("gu_n_registros")
    return a.join(n).reset_index()


def build_fc() -> pd.DataFrame:
    fc = ons.fator_capacidade("NE")
    keep = ["t", "id_ons", "nom_usina_conjunto", "nom_modalidadeoperacao", "fonte", "id_estado",
            "val_latitudesecoletora", "val_longitudesecoletora", "val_geracaoprogramada",
            "val_geracaoverificada", "val_capacidadeinstalada", "val_fatorcapacidade"]
    return fc[keep].sort_values(["id_ons", "t"]).reset_index(drop=True)


def build_coff(key: str) -> pd.DataFrame:
    c = ons.coff(key, "NE")
    for r in ["ENE", "CNF", "REL", "PAR"]:
        c[f"gnr_{r.lower()}"] = c.val_geracaonaorealizadaapurada.where(c.cod_razaorestricao == r)
    c["restrito"] = c.cod_razaorestricao.notna().astype(float)
    vals = [v for v in COFF_VALS if v in c.columns] + [f"gnr_{r}" for r in ["ene", "cnf", "rel", "par"]] + ["restrito"]
    h = c.assign(t=c.t.dt.floor("h")).groupby(["id_ons", "t"])
    out = h[vals].mean()  # média de MWmed de 30 min = MWmed horário; NaN se ambos NaN
    out["n_sub"] = h.size()
    out["id_estado"] = h.id_estado.first()
    return out.reset_index()


def build_weather() -> pd.DataFrame:
    parts = []
    for _, p in weather.points().iterrows():
        d = weather.to_ons_hour(weather.read_point(p.point_id))
        d = d.reset_index().melt(id_vars="t", var_name="var", value_name="valor")
        d["point_id"] = p.point_id
        parts.append(d)
    return pd.concat(parts, ignore_index=True)


def nearest_point(lat: np.ndarray, lon: np.ndarray, pts: pd.DataFrame) -> np.ndarray:
    d2 = (lat[:, None] - pts.lat.values[None]) ** 2 + \
         ((lon[:, None] - pts.lon.values[None]) * np.cos(np.deg2rad(lat[:, None]))) ** 2
    return pts.point_id.values[d2.argmin(1)]


def weighted_weather(w: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    """Agrega o clima em séries do NE.

    - temperatura/umidade/temp. aparente: capitais ponderadas pela população da UF.
    - vento a 100 m e velocidade³: pontos eólicos ponderados pela capacidade
      instalada VIGENTE em cada hora (FC ONS), via usina -> ponto mais próximo.
    - irradiância: pontos solares ponderados pela capacidade solar vigente.
    """
    pts = weather.points()
    wide = w.pivot_table(index="t", columns=["point_id", "var"], values="valor")
    out = pd.DataFrame(index=wide.index)
    pop = pd.read_csv(CONFIG / "pop_uf_ne.csv").set_index("uf").peso
    caps = pts[pts.kind == "capital"]
    for v in ["temperature_2m", "apparent_temperature", "relative_humidity_2m"]:
        acc = sum(wide[(r.point_id, v)] * pop[r.uf] for r in caps.itertuples())
        out[f"w_{v}_pop"] = acc / pop[caps.uf].sum()
    for fonte, kind, vname in [("EOL", "wind", "wind_speed_100m"), ("SOL", "solar", "shortwave_radiation")]:
        P = pts[pts.kind == kind]
        u = fc[fc.fonte == fonte].drop_duplicates("id_ons")
        u = u.dropna(subset=["val_latitudesecoletora", "val_longitudesecoletora"])
        pmap = dict(zip(u.id_ons, nearest_point(u.val_latitudesecoletora.values,
                                                 u.val_longitudesecoletora.values, P)))
        f = fc[fc.fonte == fonte].assign(point_id=lambda d: d.id_ons.map(pmap)).dropna(subset=["point_id"])
        capw = f.groupby(["t", "point_id"]).val_capacidadeinstalada.sum().unstack().reindex(out.index)
        val = wide.xs(vname, axis=1, level="var")[capw.columns]
        wsum = capw.sum(axis=1)
        out[f"w_{vname}_cap"] = (val * capw).sum(axis=1, min_count=1) / wsum
        if vname == "wind_speed_100m":
            out["w_wind_speed3_100m_cap"] = (val ** 3 * capw).sum(axis=1, min_count=1) / wsum
        out[f"w_cap_{fonte.lower()}_mapeada"] = wsum
    return out.reset_index()


def main() -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    print("balanço..."); bal = build_balanco(); bal.to_parquet(INTERIM / "ne_balanco_h.parquet")
    print("carga API..."); api = build_carga_api(); api.to_parquet(INTERIM / "ne_carga_api_h.parquet")
    print("geração por usina..."); gf = build_geracao_fonte(); gf.to_parquet(INTERIM / "ne_geracao_fonte_h.parquet")
    print("fator de capacidade..."); fc = build_fc(); fc.to_parquet(INTERIM / "ne_fc_usina_h.parquet")
    coffs = {}
    for k, s in [("coff_eolica", "eol"), ("coff_solar", "sol")]:
        print(f"{k}..."); coffs[s] = build_coff(k); coffs[s].to_parquet(INTERIM / f"ne_coff_{s}_usina_h.parquet")
    print("clima..."); w = build_weather(); w.to_parquet(INTERIM / "ne_weather_h.parquet")
    ww = weighted_weather(w, fc)

    # ---- tabela integrada
    H = bal.set_index("t")
    H = H.join(api.set_index("t").drop(columns=["incompleta"]).rename(columns={"n_sub": "api_n_sub"}), how="outer")
    H = H.join(gf.set_index("t"), how="left")
    for fonte in ["EOL", "SOL"]:
        f = fc[fc.fonte == fonte].groupby("t")
        H[f"fc_{fonte.lower()}_ger"] = f.val_geracaoverificada.sum(min_count=1)
        H[f"fc_{fonte.lower()}_cap"] = f.val_capacidadeinstalada.sum(min_count=1)
        H[f"fc_{fonte.lower()}_n"] = f.size()
    for s, c in coffs.items():
        g = c.groupby("t")
        for v in ["val_geracao", "val_geracaoreferencia", "val_disponibilidade",
                  "val_geracaonaorealizadaapurada", "gnr_ene", "gnr_cnf", "gnr_rel", "gnr_par"]:
            H[f"coff_{s}_{v.replace('val_', '')}"] = g[v].sum(min_count=1)
        H[f"coff_{s}_n_usinas"] = g.size()
        H[f"coff_{s}_n_restritas"] = (c.restrito > 0).groupby(c.t).sum()
    H = H.join(ww.set_index("t"), how="left")
    H.index.name = "t"
    H = H.reset_index()
    H.to_parquet(INTERIM / "ne_hourly.parquet")
    print(f"ne_hourly: {H.shape}, {H.t.min()} .. {H.t.max()}")


if __name__ == "__main__":
    main()
