"""Coleta dos documentos do PDE 2035 (EPE) listados em config/sources_epe.yaml.

Uso: python -m src.collect.epe
ZIPs são extraídos em data/raw/epe/pde2035/<nome_do_zip>/ (com proteção contra
caminhos absolutos/'..'); o ZIP original é preservado.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from urllib.parse import quote

import requests
import yaml

from src.collect.manifest import record
from src.collect.ons import fetch
from src.paths import CONFIG, RAW

OUT = RAW / "epe" / "pde2035"


def safe_extract(zpath: Path, dest: Path) -> int:
    n = 0
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            name = m.filename
            try:  # nomes cp437 de ZIPs gerados no Windows
                name = name.encode("cp437").decode("utf-8") if not (m.flag_bits & 0x800) else name
            except UnicodeError:
                pass
            target = (dest / name).resolve()
            if dest.resolve() not in target.parents and target != dest.resolve():
                raise ValueError(f"caminho inseguro no zip: {name}")
            if m.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(target, "wb") as dst:
                dst.write(src.read())
            n += 1
    return n


def main() -> None:
    with open(CONFIG / "sources_epe.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    for item in cfg["files"]:
        url = cfg["base_url"] + quote(item["path"], safe="/")
        name = item["path"].rsplit("/", 1)[-1]
        dest = OUT / name
        size = None
        try:
            h = requests.head(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            size = int(h.headers.get("Content-Length")) if h.ok else None
        except Exception:
            pass
        got = fetch(url, dest, size)
        record(dest, source="EPE", dataset="PDE 2035", resource=name, url=url,
               ref_period="horizonte 2026-2035 (usar até 2030)",
               notes=("baixado" if got else "já presente") + f"; uso: {item['use']}")
        print(("OK  " if got else "skip") + f" {name}")
        if dest.suffix.lower() == ".zip":
            n = safe_extract(dest, OUT / dest.stem)
            print(f"     extraídos {n} arquivos em {dest.stem}/")


if __name__ == "__main__":
    main()
