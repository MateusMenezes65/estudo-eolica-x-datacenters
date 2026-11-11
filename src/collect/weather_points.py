"""Define os pontos meteorológicos (gera config/weather_points.csv e
config/weather_plant_map.csv).

- capitais: 8 capitais das UFs do subsistema NE segundo o ONS (capacidade
  instalada: AL, BA, CE, PB, PE, PI, RN, SE; MA pertence ao subsistema N).
- eólica / solar: k-means (pesado pela potência outorgada) sobre as coordenadas
  SIGA de usinas EOL/UFV nas UFs do NE em Operação ou Construção.
  A ponderação temporal (capacidade vigente em cada data) é feita depois, no
  tratamento, usando weather_plant_map.csv (usina -> ponto mais próximo).

Uso: python -m src.collect.weather_points
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from src.paths import CONFIG, RAW

NE_UFS = ["AL", "BA", "CE", "PB", "PE", "PI", "RN", "SE"]
CAPITAIS = [  # coordenadas aproximadas do centro urbano
    ("cap_SSA", "Salvador", "BA", -12.971, -38.501),
    ("cap_FOR", "Fortaleza", "CE", -3.732, -38.527),
    ("cap_REC", "Recife", "PE", -8.054, -34.881),
    ("cap_NAT", "Natal", "RN", -5.795, -35.209),
    ("cap_JPA", "João Pessoa", "PB", -7.115, -34.861),
    ("cap_MCZ", "Maceió", "AL", -9.666, -35.735),
    ("cap_THE", "Teresina", "PI", -5.089, -42.802),
    ("cap_AJU", "Aracaju", "SE", -10.947, -37.073),
]
N_CLUSTERS = {"EOL": 16, "UFV": 10}
SEED = 20261111


def load_siga() -> pd.DataFrame:
    s = pd.read_csv(RAW / "aneel/siga/siga-empreendimentos-geracao.csv", sep=";",
                    encoding="utf-8-sig", decimal=",", low_memory=False)
    s = s[s.SigUFPrincipal.isin(NE_UFS) & s.SigTipoGeracao.isin(N_CLUSTERS)
          & s.DscFaseUsina.isin(["Operação", "Construção"])].copy()
    s = s.rename(columns={"NumCoordNEmpreendimento": "lat", "NumCoordEEmpreendimento": "lon"})
    ok = s.lat.between(-18.5, -2) & s.lon.between(-47, -34)
    print(f"usinas descartadas por coordenada inválida: {(~ok).sum()} "
          f"({s.loc[~ok, 'MdaPotenciaOutorgadaKw'].sum()/1e3:.0f} MW)")
    return s[ok]


def main() -> None:
    s = load_siga()
    pts = [dict(point_id=i, kind="capital", name=n, uf=uf, lat=la, lon=lo, weight_mw=np.nan,
                n_plants=0) for i, n, uf, la, lo in CAPITAIS]
    maps = []
    for tipo, k in N_CLUSTERS.items():
        d = s[s.SigTipoGeracao == tipo]
        km = KMeans(n_clusters=k, n_init=20, random_state=SEED)
        lab = km.fit_predict(d[["lat", "lon"]], sample_weight=d.MdaPotenciaOutorgadaKw)
        pref = "eol" if tipo == "EOL" else "sol"
        for c in range(k):
            m = lab == c
            g = d[m]
            pid = f"{pref}_{c:02d}"
            pts.append(dict(point_id=pid, kind="wind" if tipo == "EOL" else "solar",
                            name=pid, uf=g.SigUFPrincipal.mode().iat[0],
                            lat=round(km.cluster_centers_[c, 0], 3),
                            lon=round(km.cluster_centers_[c, 1], 3),
                            weight_mw=round(g.MdaPotenciaOutorgadaKw.sum() / 1e3, 1),
                            n_plants=int(m.sum())))
        maps.append(pd.DataFrame({"CodCEG": d.CodCEG.values, "tipo": tipo,
                                  "point_id": [f"{pref}_{c:02d}" for c in lab]}))
    P = pd.DataFrame(pts)
    P.to_csv(CONFIG / "weather_points.csv", index=False)
    pd.concat(maps).to_csv(CONFIG / "weather_plant_map.csv", index=False)
    print(P.to_string())


if __name__ == "__main__":
    main()
