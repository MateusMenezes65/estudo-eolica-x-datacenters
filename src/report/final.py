"""Gera o relatório final (reports/relatorio_final.md) a partir das tabelas do pipeline.

Uso: python -m src.report.final
Todos os números do texto vêm de arquivos em reports/ e config/; nada é digitado à mão,
exceto a narrativa. Rodar depois de src.sim.montecarlo.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from src.paths import CONFIG, FIGURES, REPORTS

MC, SIM, MOD, TAB = REPORTS / "mc", REPORTS / "sim", REPORTS / "models", REPORTS / "tables"


def f(x, nd=1):
    """Número no formato brasileiro, arredondamento convencional (metade para cima)."""
    from decimal import ROUND_HALF_UP, Decimal
    q = Decimal(str(float(x))).quantize(Decimal(1).scaleb(-nd), rounding=ROUND_HALF_UP)
    s = f"{q:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def tab(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(out)


def sg(x, nd=0) -> str:
    """Número no formato brasileiro com sinal explícito."""
    return ("+" if float(x) > 0 else "") + f(x, nd)


def backcast(BK: pd.DataFrame) -> dict:
    """Tabela e números da validação retrospectiva (reports/mc/mc_backcast.csv)."""
    regra = BK[BK.convencao.str.startswith("regra")].set_index("ano")
    obs = BK[~BK.convencao.str.startswith("regra")].set_index("ano")
    anos = list(regra.index)
    t = tab(pd.DataFrame(
        [[int(a), f(regra.loc[a, "obs_TWh"], 2),
          f"{f(regra.loc[a, 'sim_TWh'], 2)} ({sg(regra.loc[a, 'erro_%'])}%)",
          f"{f(obs.loc[a, 'sim_TWh'], 2)} ({sg(obs.loc[a, 'erro_%'])}%)",
          f(regra.loc[a, "obs_pico_MW"] / 1000), f(regra.loc[a, "sim_pico_MW"] / 1000), f(obs.loc[a, "sim_pico_MW"] / 1000),
          f(regra.loc[a, "corte_eol_em_horas_de_importacao_TWh"], 2)] for a in anos],
        columns=["Ano", "Importação observada (TWh)", "Simulada, regra emulada (erro)",
                 "Simulada, despacho hidráulico observado (erro)", "Pico observado (GW)", "Pico simulado, regra (GW)",
                 "Pico simulado, despacho observado (GW)", "Corte eólico em horas de importação (TWh)"]))
    dp_r = (regra.sim_pico_MW - regra.obs_pico_MW) / 1000
    dp_o = (obs.sim_pico_MW - obs.obs_pico_MW) / 1000
    return {"tabela": t, "regra": regra, "obs": obs, "anos": anos, "n": int(BK.n_sorteios.iat[0]),
            "mae_regra": regra["erro_%"].abs().mean(), "mae_obs": obs["erro_%"].abs().mean(),
            "dpico_regra": dp_r, "dpico_obs": dp_o}


def postos_vento(AC: pd.DataFrame) -> dict:
    """Posto de cada ano meteorológico pelo CF eólico da frota atual (1 = menos ventoso)."""
    cf = AC.set_index("ano_clima").cf_eol
    return {"posto": cf.rank().astype(int), "cf": cf, "n": len(cf), "media": cf.mean(),
            "media_22_25": cf.loc[2022:2025].mean(), "min": cf.idxmin(), "max": cf.idxmax()}


def tornado(S: pd.DataFrame):
    s = S[~S.caso.isin(["referencia"])].copy().sort_values("delta_media_TWh")
    fig, ax = plt.subplots(figsize=(8, 5))
    cor = np.where(s.delta_media_TWh > 0, "#eb6834", "#2a78d6")
    ax.barh(s.caso, s.delta_media_TWh, color=cor, height=0.6)
    ax.axvline(0, color="#52514e", lw=1)
    ax.set_xlabel("variação da importação média anual vs. referência (TWh)", fontsize=9, color="#52514e")
    ax.set_title("Sensibilidades — DC central, eólica base, 2030 (sorteios comuns)", loc="left", fontsize=10)
    ax.grid(axis="x", color="#e4e3df"); ax.set_axisbelow(True)
    [ax.spines[k].set_visible(False) for k in ["top", "right"]]
    ax.tick_params(labelsize=8)
    fig.tight_layout(); fig.savefig(FIGURES / "mc3_sensibilidades.png", dpi=130); plt.close(fig)


def main() -> None:
    c = yaml.safe_load(open(CONFIG / "cenarios.yaml", encoding="utf-8"))
    cdc = yaml.safe_load(open(CONFIG / "cenarios_dc.yaml", encoding="utf-8"))
    mcc = json.load(open(MC / "mc_config.json", encoding="utf-8"))
    inc = json.load(open(MC / "mc_incerteza.json", encoding="utf-8"))
    R = pd.read_csv(MC / "mc_resumo.csv")
    P = pd.read_csv(MC / "mc_diferencas_pareadas.csv")
    L = pd.read_csv(MC / "mc_limites_importacao.csv")
    K = pd.read_csv(MC / "mc_compensacao_eolica.csv")
    S = pd.read_csv(MC / "mc_sensibilidades.csv")
    C = pd.read_csv(MC / "mc_convergencia.csv")
    B = pd.read_csv(MOD / "comparacao_hgb_baseline.csv")
    T = pd.read_csv(MOD / "metricas_funcao_transferencia.csv")
    Dm = pd.read_csv(MOD / "cortes_metricas.csv")
    V = pd.read_csv(SIM / "validacao_sinteticos.csv")
    E = pd.read_csv(SIM / "extrapolacao_clima.csv")
    cortes = pd.read_csv(TAB / "cortes_anuais.csv")
    det = pd.read_csv(SIM / "resultados_2030.csv")
    dc = pd.read_csv(CONFIG / "dc_trajetoria_oficial_ne.csv")
    plan = pd.read_csv(CONFIG / "plan_2rq_ne.csv").set_index(["variavel", "ano"]).mwmed
    bk = backcast(pd.read_csv(MC / "mc_backcast.csv"))
    pv = postos_vento(pd.read_csv(MC / "mc_ano_clima.csv"))
    fis = pd.read_csv(TAB / "checagem_fisica.csv").set_index("ano")
    co_obs, co_pot = fis.iloc[:, 0], fis.iloc[:, 1]       # corr(vento³, CF observado / potencial)
    taxa = pd.read_csv(MOD / "cortes_taxa_eventos_ano.csv", index_col=0).y_total
    n_inv = len(pd.read_csv(CONFIG / "data_centers_ne.csv"))
    dcp = pd.read_csv(SIM / "decomposicao_L_DC_2030.csv")
    cdv = dcp[(dcp.cenario_dc == "alto") & (dcp.parcela == "inventario:CDV_ACESSOS")].MWmed.iat[0]
    betas = [float(v) for v in mcc["beta_hidro"].values()]
    ter_med = [float(v) for v in mcc["termica_hist_media_MWmed"].values()]
    cen = mcc["centro_residuos"]
    tornado(S)

    def r(dcn, w, m, col="media"):
        return R[(R.cenario_dc == dcn) & (R.cenario_eolico == w) & (R.metrica == m)][col].iat[0]

    def p(dcn, w, m, col="delta_media"):
        return P[(P.cenario_dc == dcn) & (P.cenario_eolico == w) & (P.metrica == m)][col].iat[0]

    def k(dcn, w, col):
        return K[(K.cenario_dc == dcn) & (K.cenario_eolico == w)][col].iat[0]

    ldc = {x: K[K.cenario_dc == x].L_DC_MWmed.iat[0] for x in ["conservador", "central", "alto"]}
    cap = {w: c["eolica"]["capacidade_2030_MW"][w]["valor"] for w in ["baixa", "base", "alta"]}
    ordem = ["sem_dc", "conservador", "central", "alto"]

    # ---- tabela principal (eólica base)
    linhas = []
    for x in ordem:
        linhas.append([x, f(0 if x == "sem_dc" else ldc[x], 0),
                       f"{f(r(x, 'base', 'importacao_TWh'))} [{f(r(x, 'base', 'importacao_TWh', 'p5'))}–{f(r(x, 'base', 'importacao_TWh', 'p95'))}]",
                       f"{f(r(x, 'base', 'horas_importacao'), 0)} [{f(r(x, 'base', 'horas_importacao', 'p5'), 0)}–{f(r(x, 'base', 'horas_importacao', 'p95'), 0)}]",
                       f(r(x, "base", "importacao_p95_MW"), 0), f(r(x, "base", "importacao_pico_MW"), 0),
                       f(r(x, "base", "maior_sequencia_importacao_h"), 0),
                       f(r(x, "base", "excedente_TWh")), f(r(x, "base", "excedente_acima_limite_exp_TWh"))])
    t_main = tab(pd.DataFrame(linhas, columns=["DC", "L_DC (MWmed)", "Importação TWh/ano: média [P5–P95]",
                                                "Horas com importação: média [P5–P95]", "P95 horário (MW)", "Pico (MW)",
                                                "Maior sequência (h)", "Excedente (TWh)", "Excedente > 21 GW (TWh)"]))
    # ---- matriz DC × eólica (média de importação)
    mat = pd.DataFrame([[x] + [f(r(x, w, "importacao_TWh")) for w in ["baixa", "base", "alta"]] for x in ordem],
                       columns=["DC \\ eólica", f"baixa ({f(cap['baixa']/1000)} GW)", f"base ({f(cap['base']/1000)} GW)",
                                f"alta ({f(cap['alta']/1000)} GW)"])
    # ---- diferenças pareadas
    dpar = pd.DataFrame([[x, w, f"{f(p(x, w, 'importacao_TWh'))} [{f(p(x, w, 'importacao_TWh', 'delta_p5'))}–{f(p(x, w, 'importacao_TWh', 'delta_p95'))}]",
                          f"{f(p(x, w, 'horas_importacao'), 0)} [{f(p(x, w, 'horas_importacao', 'delta_p5'), 0)}–{f(p(x, w, 'horas_importacao', 'delta_p95'), 0)}]",
                          f"{100 * p(x, w, 'importacao_TWh', 'frac_sorteios_delta_pos'):.0f}%"]
                         for x in ["conservador", "central", "alto"] for w in ["baixa", "base", "alta"]],
                        columns=["DC", "eólica", "Δ importação TWh: média [P5–P95]", "Δ horas: média [P5–P95]", "sorteios com Δ > 0"])
    # ---- compensação
    comp = pd.DataFrame([[x, w, f(k(x, w, "dW_energia_anual_MW") / 1000),
                          f"{f(k(x, w, 'dW_importacao_anual_media_MW') / 1000)} [{f(k(x, w, 'dW_importacao_anual_p5_MW') / 1000)}–{f(k(x, w, 'dW_importacao_anual_p95_MW') / 1000)}]",
                          f(k(x, w, "dW_horas_importacao_media_MW") / 1000), f(k(x, w, "dW_p95_importacao_media_MW") / 1000),
                          f"{f(k(x, w, 'dW_importacao_anual_media_MW') / k(x, w, 'dW_energia_anual_MW'))}×",
                          f"{f(k(x, w, 'absorcao_excedente_%'), 0)}%"]
                         for x in ["conservador", "central", "alto"] for w in ["baixa", "base", "alta"]],
                        columns=["DC", "eólica", "ΔW energia anual (GW)", "ΔW importação anual (GW) [P5–P95 por sorteio]",
                                 "ΔW horas de importação (GW)", "ΔW P95 horário (GW)", "razão temporal/energia",
                                 "energia de DC em horas de excedente"])
    # ---- limites de importação
    def cel(x, g):
        row = L[(L.cenario_dc == x) & (L.cenario_eolico == "base")]
        return f"{f(row[f'horas_acima_{g}GW_media'].iat[0], 0)} h / {100 * row[f'P_ano_com_hora_acima_{g}GW'].iat[0]:.0f}%"
    lim = pd.DataFrame([[x] + [cel(x, g) for g in [6, 8, 10]] for x in ordem],
                       columns=["DC (eólica base)", "> 6 GW", "> 8 GW", "> 10 GW"])
    # ---- sensibilidades
    sens = S.copy()
    sens_t = tab(pd.DataFrame([[s.caso, f(s.media_TWh, 2), f(s.delta_media_TWh, 2), f(s.p95_TWh, 2), f(s.horas_media, 0),
                                f"{f(s.efeito_DC_TWh, 2)} [{f(s.efeito_DC_p5, 2)}–{f(s.efeito_DC_p95, 2)}]"]
                               for s in sens.itertuples()],
                              columns=["Caso", "Importação média (TWh)", "Δ vs. referência", "P95 anual (TWh)", "Horas com importação",
                                       "Efeito pareado dos DC (TWh) [P5–P95]"]))
    efx = S.set_index("caso").efeito_DC_TWh
    efx_outros = efx.drop(["referencia", "sem_dc", "DC com atraso de 12 meses"])
    # ---- validação
    nd = lambda v: 3 if v < 1 else 0
    bt = tab(pd.DataFrame([[b["alvo"], b["h"], f(b["MAE"], nd(b["MAE"])),
                            f"{b['metodo_melhor_baseline']} ({f(b['MAE_melhor_baseline'], nd(b['MAE_melhor_baseline']))})",
                            f"{f(b['ganho_MAE_%'], 0)}%", f"{b['meses_HGB_melhor']}/{b['meses']}"] for _, b in B.iterrows()],
                          columns=["Alvo", "h (horas)", "MAE do HGB", "Melhor baseline (MAE)", "Ganho", "Meses em que o HGB vence"]))
    a0 = T[T.modelo.str.startswith("A0 L_gross")]
    a0_hgb = a0[a0.metodo == "HGB"].MAE
    a0_pf = a0[a0.metodo != "HGB"].MAE
    b0 = T[(T.modelo == "B0 CF eólico pot") & (T.metodo == "HGB")]
    vb = V[V.modelo == "B0"]
    ext_max = E[["pct_abaixo", "pct_acima"]].sum(axis=1).max()
    eta = inc["eta2"]
    conv = C.iloc[-1]
    dc30 = dc[(dc.estudo == "2a RQ PLAN 2026-2030") & (dc.ano == 2030)].set_index("componente").mwmed
    corte25 = cortes[(cortes.fonte == "eólica") & (cortes.ano == 2025)]["corte_%_do_potencial"].iat[0]
    corte22 = cortes[(cortes.fonte == "eólica") & (cortes.ano == 2022)]["corte_%_do_potencial"].iat[0]
    dm_ene = Dm[Dm.alvo == "y_ene"]
    sens_d = S.set_index("caso").delta_media_TWh
    det_c = det[(det.cenario_dc == "central") & (det.cenario_eolico == "base")].importacao_TWh.mean()
    det_0 = det[(det.cenario_dc == "sem_dc") & (det.cenario_eolico == "base")].importacao_TWh.mean()
    razao = K.dW_importacao_anual_media_MW / K.dW_energia_anual_MW
    dcrev = [dc[(dc.estudo == e) & (dc.ano == 2030) & (dc.componente == "total")].mwmed.iat[0]
             for e in ["PLAN 2026-2030", "1a RQ PLAN 2026-2030", "2a RQ PLAN 2026-2030"]]
    blocos = S[S.caso.str.startswith("blocos de")].delta_media_TWh.abs().max()
    api25, plan25 = mcc["L_gross_api_2025_MWmed"], plan[("carga_global", 2025)]
    pico0 = r("sem_dc", "base", "importacao_pico_MW")

    txt = f"""# Data centers e expansão eólica no subsistema Nordeste — balanço horário em 2030

Relatório final gerado por `python -m src.report.final` em {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC.
Os números vêm de tabelas versionadas em `reports/` e `config/`; os poucos valores de análises
exploratórias trazem a decisão de `docs/decisoes.md` em que estão registrados. Os resultados de 2030 são
**condicionais a cenários e hipóteses declarados**, não previsões. Margem negativa indica necessidade
de importação do restante do SIN, **não** déficit de suprimento.

## Resumo

- **Data centers.** A carga de data centers de Rede Básica projetada oficialmente para o NE em 2030
  (2ª Revisão Quadrimestral do PLAN 2026–2030) é de {f(dc30['total'], 0)} MWmed, dos quais
  {f(dc30['contratos_assinados'], 0)} MWmed já têm contrato assinado.
- **Importação.** Com a eólica do cenário base ({f(cap['base']/1000)} GW), a necessidade média de
  importação do NE em 2030 vai de {f(r('sem_dc', 'base', 'importacao_TWh'))} TWh/ano sem novos data
  centers para {f(r('central', 'base', 'importacao_TWh'))} TWh/ano no cenário central.
- **Efeito pareado.** No mesmo clima, o cenário central acrescenta
  +{f(p('central', 'base', 'importacao_TWh'))} TWh/ano, com P5–P95 de {f(p('central', 'base', 'importacao_TWh', 'delta_p5'))}
  a {f(p('central', 'base', 'importacao_TWh', 'delta_p95'))}, e +{f(p('central', 'base', 'horas_importacao'), 0)}
  horas com importação. O aumento ocorre em 100% dos sorteios.
- **Compensação em energia não basta.** {f(k('central', 'base', 'dW_energia_anual_MW')/1000)} GW eólicos
  adicionais compensariam a energia anual do cenário central. Para devolver a importação anual média ao
  nível sem data centers seriam necessários {f(k('central', 'base', 'dW_importacao_anual_media_MW')/1000)} GW,
  cerca de {f(k('central', 'base', 'dW_importacao_anual_media_MW') / k('central', 'base', 'dW_energia_anual_MW'))}
  vezes mais. O vento falta justamente nas horas de importação, e a razão cresce com a frota.
- **Absorção de excedente.** {f(k('central', 'base', 'absorcao_excedente_%'), 0)}% da energia dos data
  centers cairia em horas de excedente regional. Isso é potencial de absorção, não corte evitado: o
  estudo não representa a rede interna nem as restrições locais.
- **Variabilidade climática.** O clima pesa tanto quanto a escolha de cenário. A amplitude interquartil
  da importação anual entre sorteios (cenário central, eólica base) é de
  {f(inc['iqr_amostral_central_base_TWh'])} TWh, contra {f(inc['amplitude_medianas_dc_com_eolica_base_TWh'])}
  TWh entre as medianas dos cenários de data centers. O ano meteorológico explica {100*eta['ano_clima']:.0f}%
  da variância e o ano hidrológico, {100*eta['ano_hidro']:.0f}%.
- **Hipóteses que mais pesam,** além do próprio cenário de data centers:
  - nível da carga ±5%: {f(sens_d['carga -5%'])} / +{f(sens_d['carga +5%'])} TWh;
  - convenção do despacho hidráulico: hidráulica plana +{f(sens_d['hidraulica plana'])} TWh; despacho
    histórico sorteado, sem resposta, +{f(sens_d['hidraulica historica sorteada (sem resposta)'])} TWh;
  - atraso de 12 meses dos data centers: {f(sens_d['DC com atraso de 12 meses'])} TWh;
  - capacidade eólica: baixa +{f(sens_d['eolica baixa'])}, alta {f(sens_d['eolica alta'])} TWh.
- **Quanto confiar no nível.** Rodado com os níveis observados de 2022–2025, o simulador erra a
  importação anual entre {sg(bk['regra']['erro_%'].min())}% e {sg(bk['regra']['erro_%'].max())}% com a regra
  hidráulica do caso central (seção 4.4). O nível absoluto de 2030 carrega um erro dessa ordem; as
  diferenças pareadas entre cenários variam menos.

## 1. Pergunta e recorte

**Pergunta.** Sob diferentes cenários de entrada de data centers e de expansão eólica, como mudam a
necessidade de importação e os excedentes horários do subsistema Nordeste em 2030, e quanto de expansão
eólica compensaria o consumo adicional?

**Recorte.**
- Subsistema NE do ONS: AL, BA, CE, PB, PE, PI, RN e SE. O MA pertence ao subsistema Norte.
- Histórico de 2022–2025; 2026 entra só como complemento. Ano-alvo: 2030.
- Fora do escopo: fluxo de potência, adequação do SIN e viabilidade econômica.

**Variável central.**
- M(t) = G_NE(t) − [L_base(t) + L_DC(t)].
- Importação = max(0, −M); excedente = max(0, M).
- G_NE inclui hidráulica, térmica, eólica, solar centralizada e MMGD. A MMGD também é descontada da
  carga bruta, de modo que a carga líquida não a conta duas vezes.

## 2. Dados

Detalhes em `reports/quality/relatorio_qualidade.md`; origem, URL e SHA-256 de cada arquivo em
`docs/manifest/manifest.csv`.

- **ONS:**
  - balanço horário por subsistema, intercâmbio, carga verificada semi-horária (API; separa a MMGD);
  - geração e fator de capacidade por usina, constrained-off eólico e solar com motivo;
  - capacidade instalada.
- **ANEEL:** SIGA e MMGD.
- **EPE:** PDE 2035, relatório e planilhas.
- **ONS/EPE/CCEE:** notas de previsão de carga do PLAN 2026–2030 e workshop da 2ª Revisão Quadrimestral.
- **Clima:** ERA5 via Open-Meteo em 34 pontos (8 capitais, 16 clusters eólicos, 10 polos solares),
  1995–2026.
- **Outros:** IBGE (população) e calendário de feriados e eventos do NE.
- **Data centers:** inventário documental em `config/data_centers_ne.csv` ({n_inv} itens com fonte,
  definição da potência e maturidade).

**Achados de qualidade que condicionam o método.**

1. **Mudança de definição da carga.** Em 29/04/2023 o balanço do ONS passou a incluir a MMGD estimada
   na carga e na geração solar; a série de carga tem um degrau de ~0,5 GW (decisão 12). A forma horária
   da carga vem da API de carga do ONS, de definição homogênea, e a MMGD é tratada à parte. O nível de
   2030 vem do PLAN (seção 3.1).
2. **Corte eólico em alta.** O corte eólico apurado (GNRa) passou de {f(corte22)}% (2022) para
   {f(corte25)}% (2025) do potencial.
   - A geração de referência do constrained-off fica abaixo da geração em parte relevante das horas,
     então não é o potencial.
   - O potencial adotado é geração verificada + GNRa.
   - Com o corte, a correlação vento³ × CF observado cai de {f(co_obs.loc[2022], 2)} (2022) para
     {f(co_obs.loc[2025], 2)} (2025), enquanto vento³ × CF potencial fica em
     {f(co_pot.loc[2022:2025].min(), 2)}–{f(co_pot.loc[2022:2025].max(), 2)}.
3. **Anos com dados abaixo da média de vento.** Pelo CF eólico que a frota atual teria em cada ano do
   ERA5 (figura `s2`), 2022 é o {pv['posto'].loc[2022]}º ano menos ventoso de {pv['n']}, 2024 o
   {pv['posto'].loc[2024]}º e 2023 o {pv['posto'].loc[2023]}º; 2025 é o {pv['posto'].loc[2025]}º. A
   média de 2022–2025 ({f(pv['media_22_25'], 3)}) fica abaixo da média dos {pv['n']} anos
   ({f(pv['media'], 3)}), e o período não contém nem o ano mais fraco ({pv['min']}) nem o mais forte
   ({pv['max']}).
4. **Balanço de 2026 incompleto.** De jan a mai/2026, 878 horas não fecham (decisão 16). 2026 fica fora
   da calibração do balanço.

## 3. Metodologia

### 3.1 Trajetórias de 2030 (`config/cenarios.yaml`, `config/cenarios_dc.yaml`)

- **Carga sem novos data centers.** Carga global do NE em 2030 na 2ª RQ do PLAN
  ({f(plan[('carga_global', 2030)], 0)} MWmed) menos a carga de data centers de Rede Básica da mesma
  projeção ({f(dc30['total'], 0)}), ou seja, {f(c['carga']['L_gross_sem_dc_MWmed']['valor'], 0)} MWmed.
  É um contrafactual sem nenhum data center de Rede Básica, inclusive os que entram a partir de 2026.
  O PDE 2035 ({f(c['carga']['sensibilidade_pde']['L_gross_MWmed'], 0)} MWmed, com data centers embutidos)
  entra como sensibilidade.
- **MMGD em 2030.** {f(c['mmgd']['media_2030_MWmed']['valor'], 0)} MWmed (2ª RQ do PLAN).
- **Data centers** (MWmed em 2030, carga flat):
  - conservador = contratos assinados, {f(ldc['conservador'], 0)};
  - central = 2ª RQ do PLAN (100% dos contratos e 50% dos pareceres favoráveis), {f(ldc['central'], 0)};
  - alto = contratos + 100% dos pareceres + projetos anunciados com MW, em rampa, {f(ldc['alto'], 0)}.
  - A projeção oficial já está em MWmed de carga na rede, então não se aplica PUE.
- **Eólica.** baixa {f(cap['baixa']/1000)} GW (só operação, SIGA); base {f(cap['base']/1000)} GW
  (+ construção); alta {f(cap['alta']/1000)} GW (+ expansão indicativa do PDE até 2030, alocada ao NE).
- **Solar.** {f(c['solar']['capacidade_2030_MW']['valor']/1000)} GW.
- **Intercâmbio.** Exportação limitada a 21 GW (PDE 2035). Não há limite de importação documentado;
  usa-se sensibilidade em 6, 8 e 10 GW.

### 3.2 Modelos

Todos os modelos são HistGradientBoosting (scikit-learn), com hiperparâmetros fixos e semente fixa.

- **Curto prazo (validação acadêmica).** Carga líquida, CF eólico potencial e CF solar observado, em
  horizontes de 1 h e 24 h. A solar usa o CF observado, que inclui o corte, porque o potencial só existe
  desde 2024-04.
  - Backtesting com origem móvel em 12 dobras mensais de 2025.
  - Lags só até a origem da previsão.
  - Clima ERA5 tratado como previsão perfeita, então o desempenho é um limite superior.
- **Funções de transferência clima → sistema (sem lags).** Geram perfis horários de 2030 para cada ano
  meteorológico, no calendário de 2030, com clima ponderado pela frota atual fixa. São quatro:
  - forma da carga bruta;
  - forma da MMGD;
  - CF eólico potencial (frota 2024-07..2026-10);
  - CF solar potencial.
- **Classificador de cortes por motivo.** Avaliado apenas quanto à viabilidade.

### 3.3 Monte Carlo (`src/sim/montecarlo.py`)

- **Sorteios.** {f(mcc['n'], 0)} sorteios, semente {mcc['semente']}. Cada sorteio combina:
  - um ano meteorológico de {mcc['anos_clima'][0]}–{mcc['anos_clima'][-1]} ({len(mcc['anos_clima'])} anos);
  - um ano hidrotérmico de 2022–2025;
  - uma sequência de blocos de {mcc['bloco_dias']} dias de resíduos **fora da amostra** das quatro
    séries, reamostrados **conjuntamente**, iniciando à 00h e escolhidos a ±{mcc['janela_doy_dias']}
    dias do dia do ano.
- **Resíduos recentrados.** Os resíduos fora da amostra não têm média zero. De cada série subtrai-se a
  média esperada sob o próprio sorteio (carga {sg(cen['A0'], 4)}; MMGD {sg(cen['E0'], 4)}; CF eólico
  {sg(cen['B0'], 4)}; CF solar {sg(cen['C0'], 4)}), e as formas de carga e MMGD voltam a ter média 1 em cada
  sorteio. Assim os resíduos repõem variabilidade horária sem deslocar o nível anual. Sem a correção, a
  importação média do caso central seria {sg(sens_d['residuos sem recentrar'], 2)} TWh diferente (tabela 5.5).
- **Números aleatórios comuns.** Os mesmos sorteios valem para todos os cenários, então as diferenças
  entre cenários são pareadas.
- **Hidráulica (caso central, decidido pelo usuário).** Regra histórica emulada:
  - a energia diária é a do ano hidrológico sorteado;
  - a forma intradiária responde à carga líquida simulada com o coeficiente medido no ano
    ({f(min(betas), 2)}–{f(max(betas), 2)}), estimado sobre a geração observada, já com corte;
  - a geração fica dentro dos mínimos e máximos mensais históricos, e a energia diária é conservada.
  - O despacho histórico sorteado sem resposta e a hidráulica plana entram como sensibilidades.
  - A térmica segue o histórico do ano sorteado.
- **Separação das incertezas.** A incerteza amostrada é climática e operacional. As escolhas de
  cenário ficam como eixos separados.

## 4. Validação

### 4.1 Curto prazo (2025, fora da amostra)

{bt}

O modelo de árvores supera de forma consistente o baseline sazonal e a persistência. O menor ganho é
o da solar a 24 h.

### 4.2 Funções de transferência

- **Carga bruta normalizada** (validação deixando um ano de fora): MAE de {f(100*a0_hgb.min())}–{f(100*a0_hgb.max())}%,
  contra {f(100*a0_pf.min())}–{f(100*a0_pf.max())}% do perfil mês × dia × hora.
- **CF eólico potencial:**
  - frota recente (treino até 2025-12, teste em 2026): MAE {f(b0.MAE.iat[-1], 3)} e viés {f(b0.vies.iat[-1], 3)};
  - correlação horária com o observado em 2022–2025: {f(vb['corr'].min(), 2)}–{f(vb['corr'].max(), 2)};
  - com os resíduos, o desvio-padrão horário do sintético reproduz o observado
    ({f(vb.dp_sint_com_residuo_aprox.iat[-1], 3)} contra {f(vb.dp_obs.iat[-1], 3)} em 2025).
- **Diferença de nível em 2022–2023.** O CF médio sintético desses anos é maior que o observado
  ({f(vb.media_sint.iat[0], 3)} contra {f(vb.media_obs.iat[0], 3)} em 2022). Isso reflete a frota atual,
  com curva de potência 5–10% maior nas faixas de vento alto (decisão 20).
- **Extrapolação.** No máximo {f(ext_max, 2)}% das horas de 1995–2021 ficam fora da faixa de treino de
  alguma variável.
- **Convergência do Monte Carlo** (cenário central, eólica base): de 1.500 para {f(conv.n, 0)} sorteios,
  a média variou {f(abs(conv['var_media_%']), 2)}% e o P95, {f(abs(conv['var_p95_%']), 2)}% (figura `mc2`).
- **Blocos de resíduos.** Trocar os blocos de 7 dias por blocos de 3 ou 14 dias muda a média em até
  {f(blocos, 2)} TWh.

### 4.3 Classificador de cortes (Modelo D)

- **Desempenho.** Para o corte por razão energética, ROC-AUC de {f(dm_ene.ROC_AUC.min(), 2)}–{f(dm_ene.ROC_AUC.max(), 2)}
  e PR-AUC de {f(dm_ene.PR_AUC.min(), 2)}–{f(dm_ene.PR_AUC.max(), 2)}, contra
  {f(dm_ene.PR_AUC_aleatorio.min(), 2)}–{f(dm_ene.PR_AUC_aleatorio.max(), 2)} ao acaso.
- **Instabilidade.** A calibração muda com o regime: a taxa de horas com corte subiu de
  {f(100 * taxa.loc[2022], 0)}% para {f(100 * taxa.loc[2025], 0)}% entre 2022 e 2025.
- **REL não é previsível** com as features ex-ante.
- **Uso.** O classificador fica descritivo. Não gera probabilidade de corte em 2030, e a importância
  das variáveis não tem interpretação causal.

### 4.4 Validação retrospectiva do simulador (`src/sim/backcast.py`)

O simulador do Monte Carlo foi rodado com o clima, o ano hidrotérmico e os **níveis observados** de cada
ano de 2022–2025: carga coerente com o balanço do ONS, MMGD e energia eólica e solar potenciais. Só os
resíduos são sorteados ({bk['n']} sorteios). O teste mede as formas horárias e a convenção hidráulica, não
os cenários de 2030.

{bk['tabela']}

- **Erro da importação anual.** Com a regra emulada (caso central), de
  {sg(bk['regra']['erro_%'].min())}% a {sg(bk['regra']['erro_%'].max())}%, erro absoluto médio de
  {f(bk['mae_regra'], 0)}%. Com o despacho hidráulico observado no próprio ano, de
  {sg(bk['obs']['erro_%'].min())}% a {sg(bk['obs']['erro_%'].max())}%, erro absoluto médio de
  {f(bk['mae_obs'], 0)}%. Nenhuma convenção é melhor em todos os anos.
- **O erro muda ao longo dos anos.** Com a regra, vai de {sg(bk['regra'].loc[2022, 'erro_%'])}% em 2022 a
  {sg(bk['regra'].loc[2025, 'erro_%'])}% em 2025; com o despacho observado, de
  {sg(bk['obs'].loc[2022, 'erro_%'])}% a {sg(bk['obs'].loc[2025, 'erro_%'])}%.
  - Em 2025, {f(bk['regra'].loc[2025, 'corte_eol_em_horas_de_importacao_TWh'], 2)} TWh de corte eólico
    ocorreram em horas de importação. O simulador usa a geração potencial e não representa esses cortes.
  - Em 2024 esse corte foi de {f(bk['regra'].loc[2024, 'corte_eol_em_horas_de_importacao_TWh'], 2)} TWh,
    então a subestimação daquele ano tem outra origem, não identificada.
- **Picos.** Com a regra, o pico simulado difere do observado em
  {sg(bk['dpico_regra'].min(), 1)} a {sg(bk['dpico_regra'].max(), 1)} GW; com o despacho observado, em
  {sg(bk['dpico_obs'].min(), 1)} a {sg(bk['dpico_obs'].max(), 1)} GW.
- **Leitura.** O nível absoluto da importação de 2030 carrega um erro estrutural dessa ordem, comparável
  ao efeito de trocar a convenção hidráulica (tabela 5.5). As diferenças pareadas usam o mesmo sorteio
  nos dois lados da comparação e variam menos entre hipóteses (seção 5.2).

Figura: `reports/figures/mc4_backcast.png`.

## 5. Resultados para 2030

### 5.1 Distribuições condicionais — eólica base ({f(mcc['n'], 0)} sorteios)

{t_main}

Importação média (TWh/ano) por cenário de data centers × eólica:

{tab(mat)}

O simulador determinístico, com os 4 anos observados, dá {f(det_0)} → {f(det_c)} TWh (sem DC → central,
eólica base). Ele difere do Monte Carlo em três escolhas de método:
- despacho histórico pareado ao ano, em vez da regra emulada;
- 4 anos meteorológicos, em vez de 31;
- perfis observados, em vez de sintéticos com resíduos.
A tabela 5.5 quantifica o efeito de cada uma. Figura: `reports/figures/mc1_distribuicao_importacao.png`.

### 5.2 Efeito dos data centers (diferenças pareadas contra sem_dc, mesmo sorteio)

{tab(dpar)}

O efeito incremental dos data centers é positivo em todas as hipóteses testadas e fica na mesma
ordem de grandeza (tabela 5.5, {mcc['n_sens']} sorteios comuns, DC central):
- convenção hidráulica: +{f(efx['referencia'], 2)} TWh/ano com a regra emulada, +{f(efx['hidraulica historica sorteada (sem resposta)'], 2)}
  com o despacho histórico sorteado e +{f(efx['hidraulica plana'], 2)} com a hidráulica plana;
- demais sensibilidades (exceto o atraso dos data centers): de +{f(efx_outros.min(), 2)} a +{f(efx_outros.max(), 2)} TWh/ano.
O nível absoluto da importação, em contraste, depende bastante dessas hipóteses.

### 5.3 Compensação eólica (regra 11)

Capacidade eólica adicional que devolve cada métrica ao nível sem data centers, calculada sobre a média
dos sorteios. Para a importação anual, a faixa P5–P95 vem do cálculo sorteio a sorteio.

{tab(comp)}

Leitura:
- A compensação temporal exige {f(razao.min())}–{f(razao.max())} vezes a capacidade equivalente em energia.
- Quanto maior a frota, mais difícil compensar no tempo: as horas de importação que restam são as de
  vento fraco.
- A compensação pelo P95 horário varia menos com a frota do que a compensação pela importação anual.

### 5.4 Limites de importação (sensibilidade; não é risco de déficit)

Horas por ano com importação acima de cada limite / fração dos anos simulados com ao menos uma hora
acima dele:

{tab(lim)}

**Como ler.**
- Não há limite de importação documentado para o NE. O maior fluxo observado em 2022–2025 foi de
  {f(mcc['import_max_hist_MW'] / 1000)} GW, e fluxo não é capacidade.
- Nos níveis históricos, a regra emulada não superestima os picos (seção 4.4).
- Os picos de 2030 ficam acima desse patamar já sem data centers ({f(pico0 / 1000)} GW em média). Isso vem
  do crescimento da carga com a térmica mantida no despacho histórico: {f(min(ter_med), 0)}–{f(max(ter_med), 0)}
  MWmed de média anual e máximo horário de {f(mcc['termica_hist_max_MW'] / 1000)} GW. O estudo não representa
  o redespacho térmico ou hidráulico que ocorreria nessas horas.
- A tabela mede quanto da necessidade simulada passaria de cada patamar se nada mais respondesse. Não é
  probabilidade de déficit de suprimento.

### 5.5 Sensibilidades (DC central, eólica base, {mcc['n_sens']} sorteios comuns)

{sens_t}

Figura: `reports/figures/mc3_sensibilidades.png`. A referência desta tabela usa {mcc['n_sens']} sorteios,
por isso difere ligeiramente da tabela 5.1.

## 6. Limitações

- **Sem rede.** Excedente regional não é corte. Não há representação da rede interna do NE, das
  restrições locais nem das restrições externas além dos limites agregados. Cortes por restrição de rede
  em horas de importação aumentam a importação real e também ficam de fora.
- **Erro do simulador.** Nos anos observados, a importação anual simulada difere da real em dezenas de
  por cento, com sinal que muda de ano para ano (seção 4.4).
- **Despacho hidrotérmico.** A regra emulada não otimiza o sistema e foi estimada sobre a geração já
  cortada; a térmica é histórica. A hidrologia do São Francisco é amostrada só em 2022–2025.
- **Nível de carga.** A forma horária vem da API de carga do ONS e o nível, do PLAN. Em 2025 a carga
  global da API ({f(api25, 0)} MWmed) é {f(100 * (api25 / plan25 - 1))}% maior que a do PLAN
  ({f(plan25, 0)}). Com o nível da API, a importação média mudaria
  {sg(sens_d['nivel de carga pela API do ONS'], 2)} TWh (tabela 5.5).
- **Data centers.** Carga flat, igual à média anual de 2030. A projeção oficial muda rápido: em 2030 foi
  de {f(dcrev[0], 0)} → {f(dcrev[1], 0)} → {f(dcrev[2], 0)} MWmed em três revisões de 2025–2026. O
  inventário não tem MW de vários projetos.
- **Cenário alto.** Um dos projetos do inventário (CDV_ACESSOS, {f(cdv, 0)} MWmed em 2030) é um direito de
  acesso com processo oficial. Não foi possível verificar se já está entre os pareceres favoráveis da
  2ª RQ; se estiver, o cenário alto o conta duas vezes.
- **Funções de transferência.** Partem da frota atual e do clima ERA5, cuja resolução de 0,25° não
  reproduz o jato noturno; o padrão diário entra pela hora × mês e pelos resíduos. Os resíduos vêm de
  18 meses.
- **Eólica e solar.** O SIGA aberto não traz datas para projetos fora de operação; os cenários eólicos
  são hipóteses de fase. A solar fica fixa.
- **Dados de 2026.** São complementares, e o balanço de jan–mai/2026 tem anomalias.

## 7. Conclusões

1. **Data centers ampliam a importação.** Na projeção oficial vigente ({f(dc30['total'] / 1000)} GWmed no NE em 2030), eles
   aumentam a necessidade de importação do Nordeste em ~{f(p('central', 'base', 'importacao_TWh'))} TWh/ano
   e em ~{f(p('central', 'base', 'horas_importacao'), 0)} horas por ano, com eólica base. O aumento ocorre
   em todos os anos climáticos simulados e não muda o caráter exportador da região (excedente de
   {f(r('central', 'base', 'excedente_TWh'), 0)} TWh/ano).
2. **Compensar no tempo exige mais que compensar em energia.** Cerca de
   {f(k('central', 'base', 'dW_energia_anual_MW')/1000)} GW eólicos bastam em energia anual, mas são
   necessários ~{f(k('central', 'base', 'dW_importacao_anual_media_MW')/1000)} GW para neutralizar a
   importação anual. Sem armazenamento ou outra flexibilidade, cobrir a importação noturna e de baixo
   vento só com eólica exige capacidade muito maior que a energia consumida sugere. O custo dessa
   alternativa não foi avaliado.
3. **A carga de data centers absorveria excedente.** Grande parte da energia dos data centers
   (~{f(k('central', 'base', 'absorcao_excedente_%'), 0)}%) cairia em horas de excedente regional, o que
   reduz o excedente acima do limite de exportação. Transformar isso em redução de cortes exigiria
   análise de rede.
4. **A incerteza climática e operacional é do mesmo tamanho que as escolhas de cenário.** Por isso os
   resultados devem ser lidos como distribuições condicionais e diferenças pareadas, não como um número
   pontual.
5. **O efeito dos data centers é mais confiável que o nível.** A validação retrospectiva mostra erro de
   dezenas de por cento no nível anual da importação, enquanto o efeito pareado fica entre
   +{f(efx_outros.min(), 1)} e +{f(efx_outros.max(), 1)} TWh/ano em todas as hipóteses testadas, exceto
   o atraso.

## 8. Referências e fontes

Referências metodológicas de apoio. A existência e os metadados de cada uma foram conferidos via
Crossref, JMLR ou DOI em 2026-11-12; o texto não reproduz o conteúdo delas:
- Hersbach, H., Bell, B., Berrisford, P. et al. (2020). The ERA5 global reanalysis. *Quarterly Journal
  of the Royal Meteorological Society*, 146(730), 1999–2049. doi:10.1002/qj.3803. Referência da
  reanálise usada nas variáveis meteorológicas.
- Staffell, I.; Pfenninger, S. (2016). Using bias-corrected reanalysis to simulate current and future
  wind power output. *Energy*, 114, 1224–1239. doi:10.1016/j.energy.2016.08.068. Referência para a
  abordagem de converter vento de reanálise em geração eólica (aqui sem a correção de viés dos autores).
- Hong, T.; Fan, S. (2016). Probabilistic electric load forecasting: A tutorial review. *International
  Journal of Forecasting*, 32(3), 914–938. doi:10.1016/j.ijforecast.2015.11.011. Referência para as
  features de carga (calendário e temperatura) e para a avaliação temporal.
- Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of
  Statistics*, 17(3). doi:10.1214/aos/1176347265. Referência para a reamostragem
  em blocos.
- Pedregosa, F., Varoquaux, G., Gramfort, A. et al. (2011). Scikit-learn: Machine Learning in Python.
  *JMLR*, 12, 2825–2830. Biblioteca dos modelos.

Fontes de dados e documentos oficiais: ONS Dados Abertos e API de carga; ANEEL Dados Abertos (SIGA,
MMGD); EPE, PDE 2035; ONS/EPE/CCEE, notas e workshop do PLAN 2026–2030; IBGE/SIDRA; Open-Meteo
(ERA5); portarias SNTEP/MME e imprensa setorial citadas em `config/data_centers_ne.csv`.

## 9. Reprodutibilidade

- **Ambiente:** Python 3.14.1; dependências em `requirements.lock.txt`; sementes 20261111 (modelos) e
  {mcc['semente']} (Monte Carlo).
- **Execução:** `python -m src.pipeline` refaz tudo a partir de `data/raw`. A coleta dos dados brutos
  está no README.
- **Rastreabilidade:** decisões e hipóteses em `docs/decisoes.md`; estado em `STATUS.md`.
"""
    (REPORTS / "relatorio_final.md").write_text(txt, encoding="utf-8")
    print("reports/relatorio_final.md")


if __name__ == "__main__":
    main()
