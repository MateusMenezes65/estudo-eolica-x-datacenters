"""Notas técnicas e slides de previsão de carga do PLAN 2026-2030 (ONS/EPE/CCEE).

A nota técnica da 2ª Revisão Quadrimestral (ago/2026) não foi localizada em
2026-11-11; usam-se os slides do workshop (CCEE).

Uso: python -m src.collect.ons_plan
Contêm a projeção oficial de carga de data centers por subsistema (Rede Básica),
usada como referência para L_DC e para evitar dupla contagem (regra 9).
"""
from __future__ import annotations

import requests

from src.collect.manifest import record
from src.collect.ons import fetch
from src.paths import RAW

BASE = "https://www.ons.org.br/AcervoDigitalDocumentosEPublicacoes/"
DOCS = {
    "PLAN_2026-2030_NT_previsao_carga.pdf":
        "Nota%20T%C3%A9cnica%20-%20Previs%C3%A3o%20de%20Carga%20para%20o%20Planejamento%20Anual%20da%20Opera%C3%A7%C3%A3o%20Energ%C3%A9tica%20-%202026-2030.pdf",
    "PLAN_2026-2030_1RQ_NT_previsao_carga.pdf":
        "Nota%20T%C3%A9cnica%20da%20Previs%C3%A3o%20de%20Carga%20para%20a%201%C2%AA%20Revis%C3%A3o%20Quadrimestral%20do%20Planejamento%20Anual%20da%20Opera%C3%A7%C3%A3o%20Energ%C3%A9tica%20-%202026-2030.pdf",
}
# Obtido manualmente (a CCEE responde HTTP 403 a downloads automatizados):
MANUAIS = {
    "PLAN_2026-2030_2RQ_workshop_slides.pdf":
        "https://www.ccee.org.br/documents/80415/35709994/Apresenta%C3%A7%C3%B5es_Workshop%20da%20Previs%C3%A3o%20de%20Carga%20-%202%C2%AA%20Rev%20PLAN%202026-2030.pdf/b43d5e28-d786-73da-3396-b49789e667be",
}


def main() -> None:
    out = RAW / "ons" / "plan_carga"
    for name, path in DOCS.items():
        url = path if path.startswith("http") else BASE + path
        h = requests.head(url, timeout=60, allow_redirects=True)
        size = int(h.headers.get("Content-Length", 0)) or None
        dest = out / name
        got = fetch(url, dest, size)
        record(dest, source="ONS/EPE/CCEE", dataset="PLAN 2026-2030 previsão de carga",
               resource=name, url=url, ref_period="2026-2030", units="MWmed",
               notes="baixado" if got else "já presente")
        print(("OK  " if got else "skip") + f" {name} ({dest.stat().st_size/1e6:.1f} MB)")
    for name, url in MANUAIS.items():
        estado = "presente" if (out / name).exists() else "AUSENTE: baixar manualmente"
        print(f"manual {name}: {estado} ({url})")


if __name__ == "__main__":
    main()
