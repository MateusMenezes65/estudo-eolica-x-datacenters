"""Caminhos do projeto, relativos à raiz (funcionam com espaços no nome da pasta)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAW = DATA / "raw"
INTERIM = DATA / "interim"
PROCESSED = DATA / "processed"
CONFIG = ROOT / "config"
DOCS = ROOT / "docs"
MANIFEST_DIR = DOCS / "manifest"
REPORTS = ROOT / "reports"
FIGURES = REPORTS / "figures"
TABLES = REPORTS / "tables"


def rel(p: Path) -> str:
    """Caminho relativo à raiz, com barras '/' (portável)."""
    return Path(p).resolve().relative_to(ROOT).as_posix()
