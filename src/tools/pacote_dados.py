"""Empacota e restaura a pasta data/ para distribuição fora do Git (Release do GitHub).

Os dados não são versionados (vários arquivos passam de 100 MB). Este script gera
um .zip por subpasta de data/ e um arquivo SHA256SUMS.txt; os colegas baixam os
anexos da Release e restauram com `extrair`, que confere os hashes antes.

    python -m src.tools.pacote_dados empacotar            # gera dist/dados/*.zip
    python -m src.tools.pacote_dados extrair PASTA_ZIPS   # restaura data/ na raiz
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

from src.paths import DATA, ROOT

PARTES = ("raw", "interim", "processed")
SAIDA_PADRAO = ROOT / "dist" / "dados"
SOMAS = "SHA256SUMS.txt"


def sha256(p: Path, bloco: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(bloco):
            h.update(chunk)
    return h.hexdigest()


def empacotar(saida: Path) -> None:
    saida.mkdir(parents=True, exist_ok=True)
    linhas = []
    for parte in PARTES:
        origem = DATA / parte
        if not origem.is_dir():
            print(f"[aviso] {origem} não existe; pulando")
            continue
        destino = saida / f"data-{parte}.zip"
        arquivos = sorted(p for p in origem.rglob("*") if p.is_file())
        # Parquet já é comprimido; deflate leve evita custo sem ganho relevante.
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=1,
                             allowZip64=True) as z:
            for p in arquivos:
                z.write(p, p.relative_to(ROOT).as_posix())
        linhas.append(f"{sha256(destino)}  {destino.name}")
        print(f"{destino.name}: {len(arquivos)} arquivos, {destino.stat().st_size / 2**20:.0f} MiB")
    (saida / SOMAS).write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print(f"Somas SHA-256 em {saida / SOMAS}")


def extrair(pasta: Path) -> None:
    somas_path = pasta / SOMAS
    esperado = {}
    if somas_path.exists():
        for linha in somas_path.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                h, nome = linha.split(maxsplit=1)
                esperado[nome.strip()] = h
    else:
        print(f"[aviso] {SOMAS} ausente; extraindo sem conferir hashes")
    zips = sorted(pasta.glob("data-*.zip"))
    if not zips:
        sys.exit(f"Nenhum data-*.zip em {pasta}")
    for z in zips:
        if z.name in esperado and sha256(z) != esperado[z.name]:
            sys.exit(f"Hash divergente em {z.name}; baixe novamente")
        with zipfile.ZipFile(z) as arq:
            for nome in arq.namelist():
                alvo = (ROOT / nome).resolve()
                if not alvo.is_relative_to(DATA.resolve()):
                    sys.exit(f"Caminho fora de data/ em {z.name}: {nome}")
            arq.extractall(ROOT)
        print(f"{z.name}: extraído em data/")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("empacotar")
    e.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    x = sub.add_parser("extrair")
    x.add_argument("pasta", type=Path, help="pasta com os data-*.zip baixados")
    a = ap.parse_args(argv)
    if a.cmd == "empacotar":
        empacotar(a.saida)
    else:
        extrair(a.pasta)


if __name__ == "__main__":
    main()
