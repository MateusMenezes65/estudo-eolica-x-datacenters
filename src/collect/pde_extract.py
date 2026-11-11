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
    hdr = next(i for i, r in enumerate(rows) if r and r[0] in ("Ano", "Classe", "UF"))
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


def rows_mmgd_expansao_intercambio() -> list[dict]:
    """MMGD (Cap. 9 e 3), expansão indicativa (Fig. 3-23) e intercâmbio do NE (Fig. 3-42)."""
    out = []
    cap9 = XL / "PDE 2035_Dados_Capítulo 09_Eficiência Energética e Recursos Energéticos Distribuídos.xlsx"
    d = _sheet(cap9, "Figura 9-18")
    for _, r in d.iterrows():
        for col, cen in [("Cenário inferior (GW)", "inferior"), ("Cenário de referência (GW)", "referencia"),
                         ("Cenário superior (GW)", "superior")]:
            out.append(dict(variavel="mmgd_capacidade", escopo="Brasil", cenario=cen, ano=int(r["Ano"]),
                            valor=float(r[col]) * 1000, unidade="MW", fonte="Dados Cap. 9, Figura 9-18", nota=""))
    d = _sheet(cap9, "Figura 9-19").rename(columns={"UF": "Ano"})
    for _, r in d.iterrows():
        if r["Ano"] in ("AL", "BA", "CE", "PB", "PE", "PI", "RN", "SE"):
            out.append(dict(variavel="mmgd_capacidade", escopo=r["Ano"], cenario="referencia", ano=2035,
                            valor=float(r["Potência (GW)"]) * 1000, unidade="MW", fonte="Dados Cap. 9, Figura 9-19",
                            nota="UF do subsistema NE"))
    cap3 = XL / "PDE 2035_Dados_Capítulo 03_Geração Centralizada de Energia Elétrica.xlsx"
    d = _sheet(cap3, "Figura 3-23")
    for _, r in d.iterrows():
        for col in ["Eólica (MW)", "Solar (MW)", "Hidro (MW)"]:
            out.append(dict(variavel="expansao_indicativa_acumulada_" + col.split()[0].lower(), escopo="SIN",
                            cenario="referencia", ano=int(r["Ano"]), valor=float(r[col]), unidade="MW",
                            fonte="Dados Cap. 3, Figura 3-23", nota="indicativa (além da contratada); sem recorte por subsistema"))
    wb = openpyxl.load_workbook(cap3, read_only=True, data_only=True)
    rows = [r for r in wb["Figura 3-42"].iter_rows(values_only=True)]
    i = next(k for k, r in enumerate(rows) if r and any("Patamar" in str(x) for x in r if x))
    f = pd.DataFrame([r[1:5] for r in rows[i + 1:] if r and r[1] is not None],
                     columns=["cap2030", "cap2035", "med2030", "med2035"])
    for col, ano, pat in [("cap2030", 2030, "capacidade"), ("med2030", 2030, "media")]:
        out.append(dict(variavel=f"interc_ne_{pat}_min", escopo="Nordeste", cenario="referencia", ano=ano,
                        valor=float(f[col].min()), unidade="MW", fonte="Dados Cap. 3, Figura 3-42",
                        nota="negativo = fornecimento (exportação) do NE; mínimo da permanência de 2.000 séries x 12 meses"))
        out.append(dict(variavel=f"interc_ne_{pat}_max", escopo="Nordeste", cenario="referencia", ano=ano,
                        valor=float(f[col].max()), unidade="MW", fonte="Dados Cap. 3, Figura 3-42",
                        nota="positivo = recebimento (importação) do NE"))
    t = _pdf_text(PDE / "PDE 2035_Relatório Final_Envio MME_2026-11-05_rev4.pdf", [149])
    m = re.search(r"capacidade de exportação da Região Nordeste\s+para\s+aproximadamente\s+(\d+)\s+GW", t)
    assert m, "texto da capacidade de exportação do NE não encontrado"
    out.append(dict(variavel="limite_exportacao_ne", escopo="Nordeste", cenario="referencia", ano=2030,
                    valor=float(m.group(1)) * 1000, unidade="MW", fonte="Relatório final, seção 4.3.2, p. 149",
                    nota="a partir de 2030, com a maioria das obras licitadas; ~24 GW com bipolo Nordeste II"))
    return out


def main() -> None:
    rows = (rows_tabela_2_3() + rows_caderno_p25() + rows_fig_2_25() + rows_fig_2_24() + rows_fig_4_3()
            + rows_mmgd_expansao_intercambio())
    d = pd.DataFrame(rows)
    d.to_csv(CONFIG / "pde2035_extraido.csv", index=False, encoding="utf-8")
    ne = d[(d.escopo == "Nordeste") & (d.variavel == "carga_energia")]
    print(ne.pivot_table(index="ano", columns=["cenario", "fonte"], values="valor").round(0).to_string())
    print(f"{len(d)} valores gravados em config/pde2035_extraido.csv")


if __name__ == "__main__":
    main()
