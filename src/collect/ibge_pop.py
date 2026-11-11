"""População residente por UF (Censo 2022, IBGE/SIDRA tabela 4709, variável 93).

Uso: python -m src.collect.ibge_pop
Peso das capitais na temperatura ponderada (proxy de carga; ver AGENTS.md #7).
Salva a resposta bruta em data/raw/ibge/pop_censo2022_uf_ne.json e a tabela
config/pop_uf_ne.csv.
"""
from __future__ import annotations

import json

import pandas as pd
import requests

from src.collect.manifest import record
from src.paths import CONFIG, RAW

UF_COD = {"27": "AL", "29": "BA", "23": "CE", "25": "PB", "26": "PE", "22": "PI", "24": "RN", "28": "SE"}
URL = ("https://apisidra.ibge.gov.br/values/t/4709/n3/" + ",".join(UF_COD) + "/v/93/p/2022")


def main() -> None:
    r = requests.get(URL, timeout=60)
    r.raise_for_status()
    dest = RAW / "ibge" / "pop_censo2022_uf_ne.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    record(dest, source="IBGE SIDRA", dataset="Censo 2022 tabela 4709", resource="pop residente UF NE",
           url=URL, ref_period="2022", units="pessoas")
    rows = json.loads(r.content.decode("utf-8"))[1:]
    d = pd.DataFrame({"uf": [UF_COD[x["D1C"]] for x in rows], "pop_2022": [int(x["V"]) for x in rows]})
    d["peso"] = (d.pop_2022 / d.pop_2022.sum()).round(5)
    d.to_csv(CONFIG / "pop_uf_ne.csv", index=False)
    print(d.to_string())


if __name__ == "__main__":
    main()
