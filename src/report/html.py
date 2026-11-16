"""Versão HTML do relatório final, para publicação/compartilhamento.

Uso: python -m src.report.html [--saida DIR]
Converte reports/relatorio_final.md (subconjunto de Markdown usado pelo gerador) em uma página
com sumário, destaques numéricos lidos das mesmas tabelas e figuras em `fig/`. Os números do
corpo são os do relatório Markdown; nada é redigitado.
"""
from __future__ import annotations

import argparse
import html
import re
import shutil
import unicodedata
from pathlib import Path

import pandas as pd

from src.paths import FIGURES, REPORTS
from src.report import diagramas
from src.report.diagramas import DIAGRAMAS
from src.report.final import f

FIGS = {  # figura inserida ao fim da seção cujo título começa com a chave
    "2. Dados": [("q1_carga_definicoes.png", "Carga do NE, média mensal: balanço do ONS e API, com e sem MMGD. Em 29/04/2023 o balanço passa a incluir a MMGD."),
                 ("q4_cortes_mensais.png", "Corte apurado (GNRa) por mês e motivo, eólica e solar.")],
    "4.2": [("s2_cf_eolico_anos_meteorologicos.png", "CF eólico potencial sintético de 2030 por ano meteorológico, com a frota atual. Em azul, os anos com dados do ONS."),
            ("mc2_convergencia.png", "Convergência do Monte Carlo: média e P95 da importação anual, DC central e eólica base.")],
    "5.1": [("mc1_distribuicao_importacao.png", "Distribuição acumulada da importação anual em 2030 por cenário de data centers, para cada cenário eólico.")],
    "5.5": [("mc3_sensibilidades.png", "Variação da importação média anual em relação à referência (DC central, eólica base).")],
}


def inline(s: str) -> str:
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
    return s


def render_list(items, i=0, indent=None):
    """items: [(indent, tipo, texto)]. Retorna (html, próximo índice)."""
    if indent is None:
        indent = items[i][0]
    tipo = items[i][1]
    out = [f"<{tipo}>"]
    while i < len(items) and items[i][0] >= indent:
        ind, t, txt = items[i]
        if ind > indent:
            sub, i = render_list(items, i, ind)
            out[-1] = out[-1].replace("</li>", sub + "</li>")
            continue
        out.append(f"<li>{inline(txt)}</li>")
        i += 1
    out.append(f"</{tipo}>")
    return "".join(out), i


def md_to_html(md: str, figs_por_secao: dict | None = None):
    """Converte o subconjunto de Markdown dos relatórios. Retorna (html, sumário, imagens citadas)."""
    lines = md.splitlines()
    out, toc, para, items, table, imagens = [], [], [], [], [], []
    secao, mermaid, n_diag = None, None, 0
    figs_por_secao = FIGS if figs_por_secao is None else figs_por_secao

    def flush():
        nonlocal para, items, table
        if para:
            out.append(f"<p>{inline(' '.join(x.strip() for x in para))}</p>")
            para = []
        if items:
            out.append(render_list(items)[0])
            items = []
        if table:
            rows = [[c.strip() for c in r.strip().strip("|").split("|")] for r in table if not re.match(r"^\|\s*-", r)]
            head = "".join(f"<th>{inline(c)}</th>" for c in rows[0])
            body = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
            out.append(f'<div class="tabela"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')
            table = []

    def figs_de(titulo):
        if titulo is None:
            return
        for chave, figs in figs_por_secao.items():
            if titulo.startswith(chave):
                for arq, leg in figs:
                    out.append(f'<figure><div class="placa"><img src="fig/{arq}" alt="{html.escape(leg)}" loading="lazy"></div>'
                               f"<figcaption>{html.escape(leg)}</figcaption></figure>")

    for ln in lines:
        if mermaid is not None:
            if ln.strip() == "```":
                # cada fluxograma mermaid vira a imagem correspondente de src.report.diagramas
                if n_diag < len(DIAGRAMAS) and (FIGURES / DIAGRAMAS[n_diag][0]).exists():
                    arq, leg = DIAGRAMAS[n_diag]
                    imagens.append(f"figures/{arq}")
                    out.append(f'<figure><div class="placa"><img src="fig/{arq}" alt="{html.escape(leg)}" loading="lazy"></div>'
                               f"<figcaption>{html.escape(leg)}</figcaption></figure>")
                else:
                    out.append('<div class="diagrama"><pre class="mermaid">' + html.escape(chr(10).join(mermaid)) + "</pre></div>")
                n_diag += 1
                mermaid = None
            else:
                mermaid.append(ln)
            continue
        if ln.strip() == "```mermaid":
            flush()
            mermaid = []
            continue
        m_img = re.match(r"^!\[(.*)\]\((.*)\)\s*$", ln)
        if m_img:
            flush()
            leg, src = m_img.group(1), m_img.group(2)
            imagens.append(src)
            nome = src.rsplit("/", 1)[-1]
            out.append(f'<figure><div class="placa"><img src="fig/{nome}" alt="{html.escape(leg)}" loading="lazy"></div>'
                       f"<figcaption>{inline(leg)}</figcaption></figure>")
            continue
        if ln.startswith("> "):
            flush()
            out.append(f"<blockquote>{inline(ln[2:])}</blockquote>")
            continue
        m_h = re.match(r"^(#{1,3}) (.*)$", ln)
        m_li = re.match(r"^(\s*)(- |\d+\. )(.*)$", ln)
        if m_h:
            flush()
            nivel, titulo = len(m_h.group(1)), m_h.group(2)
            if nivel == 1:
                continue
            figs_de(secao)
            secao = titulo
            sem_acento = unicodedata.normalize("NFKD", titulo.lower()).encode("ascii", "ignore").decode()
            slug = "s-" + re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")[:48].strip("-")
            toc.append((titulo, slug, nivel))
            out.append(f'<h{nivel} id="{slug}">{inline(titulo)}</h{nivel}>')
        elif ln.startswith("|"):
            if para or items:
                flush()
            table.append(ln)
        elif m_li:
            if para or table:
                flush()
            items.append((len(m_li.group(1)), "ol" if m_li.group(2)[0].isdigit() else "ul", m_li.group(3)))
        elif not ln.strip():
            flush()
        elif items and ln.startswith(" "):
            ind, t, txt = items[-1]
            items[-1] = (ind, t, txt + " " + ln.strip())
        else:
            if items or table:
                flush()
            para.append(ln)
    flush()
    figs_de(secao)
    return "\n".join(out), toc, imagens


def destaques() -> str:
    R = pd.read_csv(REPORTS / "mc" / "mc_resumo.csv")
    P = pd.read_csv(REPORTS / "mc" / "mc_diferencas_pareadas.csv")
    K = pd.read_csv(REPORTS / "mc" / "mc_compensacao_eolica.csv")
    r = lambda d, m: R[(R.cenario_dc == d) & (R.cenario_eolico == "base") & (R.metrica == m)].media.iat[0]
    p = P[(P.cenario_dc == "central") & (P.cenario_eolico == "base") & (P.metrica == "importacao_TWh")].iloc[0]
    k = K[(K.cenario_dc == "central") & (K.cenario_eolico == "base")].iloc[0]
    tiles = [
        ("Importação do NE em 2030", f"{f(r('sem_dc', 'importacao_TWh'))} → {f(r('central', 'importacao_TWh'))}", "TWh/ano",
         "média, sem novos data centers → cenário central (2,1 GWmed)"),
        ("Efeito dos data centers", f"+{f(p.delta_media)}", "TWh/ano",
         f"mesmo clima; P5–P95 de {f(p.delta_p5)} a {f(p.delta_p95)}; positivo em {100 * p.frac_sorteios_delta_pos:.0f}% dos sorteios"),
        ("Eólica para compensar", f"{f(k.dW_energia_anual_MW / 1000)} | {f(k.dW_importacao_anual_media_MW / 1000)}", "GW",
         "pela energia anual | para manter a importação anual"),
        ("Em horas de excedente", f"{f(k['absorcao_excedente_%'], 0)}%", "",
         "da energia dos data centers: potencial de absorção, não corte evitado"),
    ]
    return "".join(
        f'<div class="tile"><div class="tile-rot">{html.escape(a)}</div>'
        f'<div class="tile-num">{html.escape(b)}<span class="un">{html.escape(u)}</span></div>'
        f'<div class="tile-nota">{html.escape(c)}</div></div>' for a, b, u, c in tiles)


CSS = """
:root {
  /* Relatório técnico de planejamento: coluna de leitura + sumário lateral; azul-petróleo como única cor de destaque */
  --bg: #f4f7f7; --surface: #ffffff; --ink: #142120; --muted: #4f5f5d; --line: #d5dfdd; --accent: #0e6a6a; --accent-soft: #e2efee;
  --f-display: "IBM Plex Sans Condensed", "Arial Narrow", system-ui, sans-serif;
  --f-body: "IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #0e1514; --surface: #151f1e; --ink: #e2ebe9; --muted: #9caeab; --line: #293937; --accent: #55b8b1; --accent-soft: #19302e; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #0e1514; --surface: #151f1e; --ink: #e2ebe9; --muted: #9caeab; --line: #293937; --accent: #55b8b1; --accent-soft: #19302e; color-scheme: dark }
body { background: var(--bg); color: var(--ink); font: 16px/1.62 var(--f-body); }
.pagina { max-width: 1180px; margin: 0 auto; padding-block: 32px 64px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }
header.topo { display: grid; gap: 14px; padding-bottom: 28px; border-bottom: 1px solid var(--line); }
.sobre { font: 600 12px/1.4 var(--f-mono); letter-spacing: .06em; text-transform: uppercase; color: var(--accent); }
h1 { font: 600 clamp(30px, 4.4vw, 46px)/1.08 var(--f-display); margin: 0; text-wrap: balance; max-width: 22ch; }
.lead { color: var(--muted); max-width: 70ch; margin: 0; }
.formula { font: 500 15px/1.4 var(--f-mono); background: var(--accent-soft); color: var(--ink); padding: 10px 14px; border-radius: 6px; justify-self: start; max-width: 100%; overflow-x: auto; }
.tiles { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 8px; }
.tile { background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; display: grid; gap: 4px; align-content: start; }
.tile-rot { font: 600 12px/1.3 var(--f-mono); letter-spacing: .04em; text-transform: uppercase; color: var(--muted); }
.tile-num { font: 600 30px/1.1 var(--f-display); font-variant-numeric: tabular-nums; color: var(--accent); }
.tile-num .un { font: 500 14px var(--f-body); color: var(--muted); margin-left: 6px; }
.tile-nota { font-size: 13px; line-height: 1.45; color: var(--muted); }
.corpo { display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 48px; margin-top: 32px; }
nav.sumario { position: sticky; top: calc(env(safe-area-inset-top, 0px) + 16px); align-self: start; max-height: calc(100vh - 32px); overflow-y: auto; font-size: 13.5px; }
nav.sumario p { font: 600 12px var(--f-mono); letter-spacing: .06em; text-transform: uppercase; color: var(--muted); margin: 0 0 8px; }
nav.sumario a { display: block; color: var(--muted); text-decoration: none; padding: 3px 0 3px 10px; border-left: 2px solid transparent; line-height: 1.35; }
nav.sumario a.n3 { padding-left: 22px; font-size: 12.5px; }
nav.sumario a:hover, nav.sumario a:focus-visible { color: var(--ink); border-left-color: var(--accent); outline: none; }
article { min-width: 0; max-width: 820px; }
article h2 { font: 600 26px/1.2 var(--f-display); margin: 44px 0 12px; padding-top: 6px; text-wrap: balance; scroll-margin-top: 16px; }
article h2:first-child { margin-top: 0; }
article h3 { font: 600 19px/1.3 var(--f-display); margin: 30px 0 8px; text-wrap: balance; scroll-margin-top: 16px; }
article p, article li { max-width: 72ch; }
article ul, article ol { padding-left: 1.3em; display: grid; gap: 4px; }
article li > ul, article li > ol { margin-top: 4px; }
code { font: 0.86em var(--f-mono); background: var(--accent-soft); padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere; }
strong { font-weight: 600; }
.tabela { overflow-x: auto; margin: 14px 0 18px; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; font-size: 13.5px; font-variant-numeric: tabular-nums; }
th, td { padding: 7px 10px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--line); }
th { font: 600 12.5px/1.3 var(--f-body); color: var(--muted); background: var(--accent-soft); }
tbody tr:last-child td { border-bottom: 0; }
td:not(:first-child) { white-space: nowrap; }
figure { margin: 18px 0 22px; display: grid; gap: 8px; }
.placa { background: #ffffff; border: 1px solid var(--line); border-radius: 8px; padding: 8px; overflow-x: auto; }
.placa img { display: block; width: 100%; max-width: 100%; height: auto; }
figcaption { font-size: 13px; color: var(--muted); max-width: 72ch; }
blockquote { margin: 14px 0; padding: 10px 14px; border-left: 3px solid var(--accent); background: var(--accent-soft); font: 500 14.5px/1.5 var(--f-mono); overflow-x: auto; }
.diagrama { margin: 16px 0 20px; padding: 12px; background: var(--surface); border: 1px solid var(--line); border-radius: 8px; overflow-x: auto; }
footer { margin-top: 48px; padding-top: 16px; border-top: 1px solid var(--line); font-size: 13px; color: var(--muted); }
@media (max-width: 900px) {
  .corpo { grid-template-columns: minmax(0, 1fr); gap: 20px; }
  nav.sumario { position: static; max-height: none; border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: var(--surface); }
  .tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 480px) { .tiles { grid-template-columns: minmax(0, 1fr); } td:not(:first-child) { white-space: normal; } }
@media (prefers-reduced-motion: no-preference) { html { scroll-behavior: smooth; } }
"""


DOCS = {
    "final": dict(md="relatorio_final.md", titulo="Data Centers e Eólica no Nordeste",
                  h1="Data centers e expansão eólica no balanço horário do Nordeste",
                  sobre="Subsistema Nordeste (ONS) · ano-alvo 2030 · estudo acadêmico de cenários",
                  lead="Como a entrada de data centers e a expansão eólica mudam a necessidade de importação e os excedentes horários do NE em 2030, e quanta eólica compensaria o consumo adicional. Resultados condicionais a cenários declarados, não previsões. Margem negativa indica importação do restante do SIN, não déficit de suprimento.",
                  gerador="src.report.final", figs=None),
    "tecnico": dict(md="relatorio_tecnico.md", titulo="Relatório Técnico NE 2030",
                    h1="Relatório técnico: como o estudo foi feito, passo a passo",
                    sobre="Data centers e expansão eólica · subsistema Nordeste (ONS) · ano-alvo 2030",
                    lead="Documento para apresentação do projeto: quais dados foram coletados e para que servem, que análises e decisões vieram deles, como os modelos de machine learning foram construídos e validados, como o simulador e o Monte Carlo funcionam, e o que os resultados permitem concluir. Resultados condicionais a cenários declarados, não previsões.",
                    gerador="src.report.tecnico", figs={}),
}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc", choices=list(DOCS), default="final")
    ap.add_argument("--saida", default=None)
    a = ap.parse_args(argv)
    cfg = DOCS[a.doc]
    out = Path(a.saida or (REPORTS / "site" / a.doc))
    (out / "fig").mkdir(parents=True, exist_ok=True)
    md = (REPORTS / cfg["md"]).read_text(encoding="utf-8")
    if "```mermaid" in md:
        diagramas.main()                                  # fluxogramas como imagem
    gerado = re.search(r"em (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) UTC", md)
    corpo, toc, imagens = md_to_html(md, cfg["figs"])
    for figs in (FIGS.values() if cfg["figs"] is None else []):
        for arq, _ in figs:
            shutil.copy(FIGURES / arq, out / "fig" / arq)
    for src in imagens:
        shutil.copy(REPORTS / src, out / "fig" / src.rsplit("/", 1)[-1])
    nav = "".join(f'<a class="n{n}" href="#{s}">{inline(t)}</a>' for t, s, n in toc)
    page = f"""<title>{cfg['titulo']}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@600&family=IBM+Plex+Sans:ital,wght@0,400;0,600;1,400&display=swap">
<style>{CSS}</style>
<div class="pagina">
<header class="topo">
  <div class="sobre">{html.escape(cfg['sobre'])}</div>
  <h1>{html.escape(cfg['h1'])}</h1>
  <p class="lead">{html.escape(cfg['lead'])}</p>
  <div class="formula">M(t) = G<sub>NE</sub>(t) − [L<sub>base</sub>(t) + L<sub>DC</sub>(t)] · importação = max(0, −M)</div>
  <div class="tiles">{destaques()}</div>
</header>
<div class="corpo">
  <nav class="sumario" aria-label="Sumário"><p>Sumário</p>{nav}</nav>
  <article>{corpo}</article>
</div>
<footer>Gerado de <code>reports/{cfg['md']}</code> ({html.escape(gerado.group(1) + ' UTC' if gerado else '')}) por <code>python -m {cfg['gerador']}</code>. Todos os números vêm das tabelas do pipeline (<code>python -m src.pipeline</code>).</footer>
</div>
"""
    (out / "index.html").write_text(page, encoding="utf-8")
    print(out / "index.html", f"({len(imagens) or sum(len(v) for v in FIGS.values())} figuras)")


if __name__ == "__main__":
    main()
