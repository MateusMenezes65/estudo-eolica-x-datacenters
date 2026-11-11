"""Coleta reproduzível de conjuntos do ONS Dados Abertos (CKAN).

Uso:
    python -m src.collect.ons catalog                 # lista tamanhos (sem baixar)
    python -m src.collect.ons download balanco        # baixa um conjunto
    python -m src.collect.ons download coff_eolica --start 2022 --end 2026

Baixa apenas recursos no formato configurado (Parquet) cujo nome de arquivo
contenha ano (e mês) dentro do período, mais os dicionários de dados (PDF/JSON).
Recursos sem ano no nome (ex.: capacidade instalada) são baixados integralmente.
Arquivos já presentes com mesmo tamanho não são baixados novamente.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests
import yaml

from src.collect.manifest import record
from src.paths import CONFIG, RAW

CKAN = "https://dados.ons.org.br/api/3/action/package_show"
PERIOD_RE = re.compile(r"_(\d{4})(?:_(\d{2}))?\.[a-z]+$", re.I)
UA = {"User-Agent": "estudo-academico-eolica-dc/0.1 (python-requests)"}


def load_cfg() -> dict:
    with open(CONFIG / "sources_ons.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resources(ckan_id: str) -> list[dict]:
    r = requests.get(CKAN, params={"id": ckan_id}, headers=UA, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["resources"]


def select(res: list[dict], fmt: str, start: int, end: int,
           fallback: str = "CSV") -> list[dict]:
    """Seleciona recursos de dados no formato e período, deduplicando por URL.

    Para cada período, usa o formato preferido (Parquet); se o ONS não o
    publica naquele período (ex.: intercâmbio 2022), recorre ao CSV.
    """
    dicts, by_period, seen = [], {}, set()
    for x in res:
        url = x.get("url") or ""
        if url in seen:
            continue
        seen.add(url)
        name = url.rsplit("/", 1)[-1]
        f = (x.get("format") or "").upper()
        if "dicionario" in name.lower():
            if f in {"PDF", "JSON"}:
                dicts.append({**x, "_kind": "dict", "_period": ""})
            continue
        if f not in {fmt, fallback}:
            continue
        m = PERIOD_RE.search(name)
        if m:
            if not (start <= int(m.group(1)) <= end):
                continue
            period = f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)
        else:
            period = "snapshot"
        by_period.setdefault(period, {})[f] = {**x, "_kind": "data", "_period": period}
    data = [v.get(fmt) or v[fallback] for _, v in sorted(by_period.items())]
    return dicts + data


def head_size(url: str) -> int | None:
    try:
        r = requests.head(url, headers=UA, timeout=30, allow_redirects=True)
        return int(r.headers.get("Content-Length")) if r.ok else None
    except Exception:
        return None


def catalog(cfg: dict, keys: list[str], start: int, end: int) -> None:
    fmt = cfg["format"]
    print(f"{'key':18s} {'n':>4s} {'MB':>9s}  periodo  ckan_id")
    for k in keys:
        d = cfg["datasets"][k]
        sel = [x for x in select(resources(d["ckan_id"]), fmt, start, end) if x["_kind"] == "data"]
        sizes = [x.get("size") or head_size(x["url"]) or 0 for x in sel]
        per = sorted(x["_period"] for x in sel)
        span = f"{per[0]}..{per[-1]}" if per else "-"
        print(f"{k:18s} {len(sel):4d} {sum(sizes)/1e6:9.1f}  {span}  {d['ckan_id']}")


def fetch(url: str, dest: Path, expected: int | None) -> bool:
    """Baixa url -> dest (via arquivo .part). Retorna True se baixou."""
    if dest.exists() and (expected is None or dest.stat().st_size == expected):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(4):
        try:
            with requests.get(url, headers=UA, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for b in r.iter_content(1 << 20):
                        f.write(b)
            tmp.replace(dest)
            return True
        except Exception as e:  # rede instável: novas tentativas
            print(f"  tentativa {attempt+1} falhou: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"falha ao baixar {url}")


def download(cfg: dict, key: str, start: int, end: int) -> None:
    d = cfg["datasets"][key]
    sel = select(resources(d["ckan_id"]), cfg["format"], start, end)
    outdir = RAW / "ons" / key
    for x in sel:
        url = x["url"]
        name = url.rsplit("/", 1)[-1]
        dest = outdir / ("dicionario" if x["_kind"] == "dict" else "") / name
        got = fetch(url, dest, x.get("size"))
        record(dest, source="ONS Dados Abertos", dataset=d["ckan_id"],
               resource=x.get("name", ""), url=url, ref_period=x["_period"],
               time_zone="a confirmar no dicionário (ONS: horário de Brasília)",
               notes=("baixado" if got else "já presente") + f"; CKAN last_modified={x.get('last_modified')}")
        print(("OK  " if got else "skip") + f" {dest.relative_to(RAW)}")


def main(argv=None) -> None:
    cfg = load_cfg()
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["catalog", "download"])
    p.add_argument("keys", nargs="*")
    p.add_argument("--start", type=int, default=cfg["default_period"]["start"])
    p.add_argument("--end", type=int, default=cfg["default_period"]["end"])
    a = p.parse_args(argv)
    keys = a.keys or list(cfg["datasets"])
    if a.cmd == "catalog":
        catalog(cfg, keys, a.start, a.end)
    else:
        for k in keys:
            download(cfg, k, a.start, a.end)


if __name__ == "__main__":
    main()
