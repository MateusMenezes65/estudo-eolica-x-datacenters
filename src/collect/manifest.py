"""Manifesto de fontes: um registro por arquivo coletado.

Grava docs/manifest/manifest.csv (versionado) com origem, URL, caminho local,
tamanho, SHA-256, data de coleta (UTC) e notas. Reexecuções atualizam o
registro do mesmo caminho local em vez de duplicá-lo.
"""
from __future__ import annotations

import csv
import hashlib
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.paths import MANIFEST_DIR, rel

FIELDS = [
    "local_path", "source", "dataset", "resource", "url", "ref_period",
    "size_bytes", "sha256", "collected_at_utc", "time_zone", "units", "notes",
]
MANIFEST = MANIFEST_DIR / "manifest.csv"


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    with open(MANIFEST, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def record(path: Path, *, source: str, dataset: str, resource: str, url: str,
           ref_period: str = "", time_zone: str = "", units: str = "",
           notes: str = "", collected_at_utc: str | None = None) -> dict:
    path = Path(path)
    row = {
        "local_path": rel(path), "source": source, "dataset": dataset,
        "resource": resource, "url": url, "ref_period": ref_period,
        "size_bytes": path.stat().st_size, "sha256": sha256(path),
        "collected_at_utc": collected_at_utc
        or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "time_zone": time_zone, "units": units, "notes": notes,
    }
    with _lock():
        old = {r["local_path"]: r for r in read_manifest()}
        prev = old.get(row["local_path"])
        if prev and prev["sha256"] == row["sha256"] and not collected_at_utc:
            row["collected_at_utc"] = prev["collected_at_utc"]  # mesmo arquivo: preserva data
        old[row["local_path"]] = row
        rows = sorted(old.values(), key=lambda r: r["local_path"])
        MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
        tmp = MANIFEST.with_suffix(".tmp")
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        os.replace(tmp, MANIFEST)
    return row


@contextmanager
def _lock(timeout: float = 120.0):
    """Trava simples por arquivo (coletores podem rodar em paralelo)."""
    lock = MANIFEST.with_suffix(".lock")
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.time() - t0 > timeout:
                raise TimeoutError(f"manifesto travado: remova {lock} se nenhum coletor estiver rodando")
            time.sleep(0.2)
    try:
        yield
    finally:
        os.close(fd)
        os.remove(lock)


def check() -> int:
    """Confere data/raw x manifesto: arquivos sem registro, registros órfãos e hash divergente."""
    from src.paths import RAW, ROOT
    reg = {r["local_path"]: r for r in read_manifest()}
    files = {rel(f): f for f in RAW.rglob("*") if f.is_file() and not f.name.endswith(".part")}
    zipped = {k for k in files if any(k.startswith(z[:-4] + "/") for z in reg if z.endswith(".zip"))}
    missing = sorted(set(files) - set(reg) - zipped)
    orphan = sorted(set(reg) - set(files))
    bad = [k for k in reg if k in files and (int(reg[k]["size_bytes"]) != files[k].stat().st_size)]
    print(f"registros={len(reg)} arquivos={len(files)} (extraídos de zip={len(zipped)})")
    for k in missing: print("SEM REGISTRO:", k)
    for k in orphan: print("ÓRFÃO:", k)
    for k in bad: print("TAMANHO DIVERGENTE:", k)
    return len(missing) + len(orphan) + len(bad)


if __name__ == "__main__":
    raise SystemExit(1 if check() else 0)
