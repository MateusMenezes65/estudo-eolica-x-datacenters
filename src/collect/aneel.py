"""Coleta reproduzível de conjuntos da ANEEL Dados Abertos (CKAN).

Uso:
    python -m src.collect.aneel catalog
    python -m src.collect.aneel download siga
    python -m src.collect.aneel download mmgd

Os recursos são escolhidos pelo nome do arquivo (config/sources_aneel.yaml),
pois os IDs de recurso da ANEEL mudam quando o conjunto é republicado.
SIGA e MMGD são fotografias (snapshot): a data de coleta define a referência.
"""
from __future__ import annotations

import argparse

import requests
import yaml

from src.collect.manifest import record
from src.collect.ons import UA, fetch
from src.paths import CONFIG, RAW

CKAN = "https://dadosabertos.aneel.gov.br/api/3/action/package_show"


def load_cfg() -> dict:
    with open(CONFIG / "sources_aneel.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pick(key: str, d: dict) -> list[dict]:
    r = requests.get(CKAN, params={"id": d["ckan_id"]}, headers=UA, timeout=60)
    r.raise_for_status()
    res = r.json()["result"]["resources"]
    want = set(d["files"])
    return [x for x in res if x["url"].rsplit("/", 1)[-1] in want]


def main(argv=None) -> None:
    cfg = load_cfg()
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["catalog", "download"])
    p.add_argument("keys", nargs="*")
    a = p.parse_args(argv)
    for k in a.keys or list(cfg["datasets"]):
        d = cfg["datasets"][k]
        sel = pick(k, d)
        if a.cmd == "catalog":
            print(f"{k:8s} {sum((x.get('size') or 0) for x in sel)/1e6:8.1f} MB  "
                  + ", ".join(x['url'].rsplit('/', 1)[-1] for x in sel))
            continue
        for x in sel:
            name = x["url"].rsplit("/", 1)[-1]
            dest = RAW / "aneel" / k / name
            got = fetch(x["url"], dest, x.get("size"))
            record(dest, source="ANEEL Dados Abertos", dataset=d["ckan_id"],
                   resource=x.get("name", ""), url=x["url"], ref_period="snapshot",
                   notes=("baixado" if got else "já presente")
                   + f"; CKAN last_modified={x.get('last_modified')}")
            print(("OK  " if got else "skip") + f" {dest.relative_to(RAW)}")


if __name__ == "__main__":
    main()
