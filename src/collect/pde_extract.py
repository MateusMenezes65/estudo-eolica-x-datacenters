"""Extrai do PDE 2035 (EPE) os números usados nas trajetórias de cenário (até 2030).

Uso: python -m src.collect.pde_extract
Saída: config/pde2035_extraido.csv (versionado), uma linha por valor, com
unidade, escopo geográfico, cenário e localização exata na fonte.

Fontes lidas (data/raw/epe/pde2035/):
- Planilha do Cap. 2 (Figuras 2-24 e 2-25) e do Cap. 4 (Figura 4-3);
- Relatório final, Tabela 2-3 (carga de energia por subsistema, p. 53);
- Caderno de Demanda de Eletricidade, tabela da p. 25 (carga global por
  subsistema e cenário, 2025 e 2035).
Valores de texto são extraídos por expressão regular e conferidos por asserções;
se o PDF mudar, o script falha em vez de gravar números errados.
"""
from __future__ import annotations

import re

import openpyxl
import pandas as pd
from pypdf import PdfReader

from src.paths import CONFIG, RAW

PDE = RAW / "epe" / "pde2035"
XL = PDE / "PDE 2035_Dados_Relatório Final"
SUBS = ["Norte", "Nordeste", "Sudeste/CO", "Sul", "SIN"]


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def _sheet(path, name_like):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    name = next(s for s in wb.sheetnames if s.replace("‑", "-") == name_like)
    rows = [[c for c in r] for r in wb[name].iter_rows(values_only=True)]
    hdr = next(i for i, r in enumerate(rows) if r and r[0] in ("Ano", "Classe"))
    cols = [c for c in rows[hdr] if c is not None]
    body = [r[:len(cols)] for r in rows[hdr + 1:] if r and r[0] is not None]
    return pd.DataFrame(body, columns=cols)


def rows_fig_2_25() -> list[dict]:
    d = _sheet(XL / "PDE 2035_Dados_Capítulo 02_Demanda de Energia.xlsx", "Figura 2-25")
    out = []
    for _, r in d.iterrows():
        for col, cen in [("Cenário Inferior (GWmédio)", "inferior"), ("Cenário Referência (GWmédio)", "referencia"),
                         ("Cenário Superior (GWmédio)", "superior")]:
            out.append(dict(variavel="carga_energia", escopo="SIN", cenario=cen, ano=int(r["Ano"]),
                            valor=float(r[col]) * 1000, unidade="MWmed",
                            fonte="Dados Cap. 2, Figura 2-25", nota="carga global (conceito ONS, inclui MMGD)"))
    return out


def rows_fig_2_24() -> list[dict]:
    d = _sheet(XL / "PDE 2035_Dados_Capítulo 02_Demanda de Energia.xlsx", "Figura 2-24")
    r = d.iloc[0]
    out = []
    for col, cen in [("Cenário menos favorável (TWh)", "inferior"), ("Referência (TWh)", "referencia"),
                     ("Cenário mais favorável (TWh)", "superior")]:
        out.append(dict(variavel="consumo_cargas_especiais", escopo="Brasil", cenario=cen, ano=int(r["Ano"]),
                        valor=float(r[col]), unidade="TWh", fonte="Dados Cap. 2, Figura 2-24",
                        nota="veículos elétricos + data centers + H2 eletrolítico, somados; sem separação por tipo nem subsistema"))
    return out


def rows_fig_4_3() -> list[dict]:
    d = _sheet(XL / "PDE 2035_Dados_Capítulo 04_Transmissão de Energia Elétrica.xlsx", "Figura 4-3")
    out = []
    acc = 0.0
    for _, r in d.iterrows():
        acc += float(r["Data Center (GW)"])
        out.append(dict(variavel="pedidos_conexao_dc_acrescimo", escopo="Brasil", cenario="pipeline_MME",
                        ano=int(r["Ano"]), valor=float(r["Data Center (GW)"]) * 1000, unidade="MW",
                        fonte="Dados Cap. 4, Figura 4-3 (MME, out/2025)",
                        nota="potência instalada de processos de conexão à Rede Básica protocolados no MME; não é previsão de carga"))
        out.append(dict(variavel="pedidos_conexao_dc_acumulado", escopo="Brasil", cenario="pipeline_MME",
                        ano=int(r["Ano"]), valor=acc * 1000, unidade="MW",
                        fonte="Dados Cap. 4, Figura 4-3 (MME, out/2025)", nota="acumulado calculado"))
    assert abs(acc - 26.3) < 0.1, acc  # texto do PDE: 26,3 GW de data centers até 2038
    return out


def _pdf_text(path, pages) -> str:
    r = PdfReader(path)
    return "\n".join(r.pages[p - 1].extract_text() or "" for p in pages)


def rows_tabela_2_3() -> list[dict]:
    t = _pdf_text(PDE / "PDE 2035_Relatório Final_Envio MME_2026-11-05_rev4.pdf", [53])
    out = []
    for ano in (2025, 2030, 2035):
        m = re.search(rf"^{ano} ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)\s*$", t, re.M)
        assert m, f"Tabela 2-3: linha {ano} não encontrada"
        vals = [_num(x) for x in m.groups()]
        assert abs(sum(vals[:4]) - vals[4]) <= 2, (ano, vals)  # subsistemas somam o SIN
        for s, v in zip(SUBS, vals):
            out.append(dict(variavel="carga_energia", escopo=s, cenario="referencia", ano=ano, valor=v,
                            unidade="MWmed", fonte="Relatório final, Tabela 2-3, p. 53",
                            nota="carga de energia (inclui MMGD, conceito de carga global ONS)"))
    return out


def rows_caderno_p25() -> list[dict]:
    t = _pdf_text(PDE / "PDE 2035_Caderno_Demanda_Eletricidade_rev_mme_20250914.pdf", [25])
    out = []
    for s in ["Norte", "Nordeste", "Sudeste-CO", "Sul"]:
        m = re.search(rf"^{s} ((?:[\d,]+ [\d,]+ [\d,]+% ?){{3}})", t, re.M)
        assert m, f"caderno p. 25: {s} não encontrado"
        v = m.group(1).split()
        for k, cen in enumerate(["inferior", "referencia", "superior"]):
            for j, ano in enumerate((2025, 2035)):
                out.append(dict(variavel="carga_energia", escopo=s.replace("Sudeste-CO", "Sudeste/CO"),
                                cenario=cen, ano=ano, valor=_num(v[3 * k + j]) * 1000, unidade="MWmed",
                                fonte="Caderno Demanda de Eletricidade, p. 25",
                                nota="carga global (GWmed no original, arredondado a 0,1 GW)"))
    return out


def main() -> None:
    rows = (rows_tabela_2_3() + rows_caderno_p25() + rows_fig_2_25() + rows_fig_2_24() + rows_fig_4_3())
    d = pd.DataFrame(rows)
    d.to_csv(CONFIG / "pde2035_extraido.csv", index=False, encoding="utf-8")
    ne = d[(d.escopo == "Nordeste") & (d.variavel == "carga_energia")]
    print(ne.pivot_table(index="ano", columns=["cenario", "fonte"], values="valor").round(0).to_string())
    print(f"{len(d)} valores gravados em config/pde2035_extraido.csv")


if __name__ == "__main__":
    main()
