"""Relatório técnico detalhado (passo a passo) para apresentação ao mentor.

Uso: python -m src.report.tecnico
Saída: reports/relatorio_tecnico.md (figuras em reports/figures/).
Pré-requisitos: pipeline completo e src.report.figuras_didaticas. Os números do texto são
lidos das tabelas em reports/ e config/; a narrativa explica o que foi feito e por quê.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from src.paths import CONFIG, REPORTS, ROOT
from src.report.final import f, tab

MC, SIM, MOD, TAB = REPORTS / "mc", REPORTS / "sim", REPORTS / "models", REPORTS / "tables"

# ordem das figuras (numeração automática)
FIGURAS = [
    ("r01", "r01_cobertura_dados.png", "Cobertura temporal das séries horárias usadas no estudo."),
    ("r02", "r02_mapa_usinas_pontos.png", "Usinas eólicas e solares despachadas pelo ONS no subsistema NE (área proporcional à capacidade) e pontos de reanálise ERA5 usados como features."),
    ("q1", "q1_carga_definicoes.png", "Carga do NE em três definições. O degrau em 29/04/2023 é a mudança de definição do balanço do ONS, que passou a incluir a MMGD."),
    ("r04", "r04_mapas_calor_hora_mes_2025.png", "Perfis médios por hora × mês em 2025: carga líquida, CF eólico potencial, CF solar potencial e MMGD."),
    ("q3", "q3_perfil_diario_2025.png", "Perfil diário médio de 2025: carga, eólica verificada, eólica + corte apurado, solar e MMGD."),
    ("r05", "r05_temperatura_carga.png", "Relação diária entre temperatura ponderada e carga bruta normalizada, separando dias úteis de fins de semana e feriados."),
    ("r03", "r03_capacidade_historico_cenarios.png", "Capacidade eólica e solar instalada no NE (histórico) e os valores de 2030 adotados nos cenários."),
    ("q2", "q2_geracao_fonte.png", "Geração mensal do NE por fonte e carga (balanço ONS)."),
    ("q4", "q4_cortes_mensais.png", "Corte apurado (GNRa) mensal por motivo, eólica e solar."),
    ("r06", "r06_corte_eolico_hora_mes_2025.png", "Corte eólico médio por hora × mês em 2025, separado por motivo."),
    ("q6", "q6_cf_vento.png", "CF eólico observado e potencial contra o vento ERA5 a 100 m, em 2022 e em 2025."),
    ("r09", "r09_ciclo_diurno_cf_vs_era5.png", "Ciclo diário médio do CF eólico potencial e do vento ERA5 (valores relativos à média do dia)."),
    ("q5", "q5_horas_importacao.png", "Percentual mensal de horas com importação líquida pelo NE (observado)."),
    ("r07", "r07_importacao_por_hora_historico.png", "Percentual de horas com importação líquida por hora do dia, 2022–2025 (observado)."),
    ("s2", "s2_cf_eolico_anos_meteorologicos.png", "CF eólico potencial médio de 2030 sintetizado para cada ano meteorológico 1995–2025, com a frota atual."),
    ("r08", "r08_data_centers_trajetoria_inventario.png", "Projeções oficiais de carga de data centers no NE em três revisões e inventário documental de projetos."),
    ("r10", "r10_backtest_mae_mensal.png", "Backtesting a 24 h: MAE mensal do HGB e do melhor baseline em cada dobra de 2025."),
    ("m1", "m1_backtest_semana.png", "Uma semana de previsões a 24 h (setembro/2025) para carga, CF eólico e CF solar."),
    ("r11", "r11_importancia_permutacao.png", "Importância por permutação das features dos modelos A0 (carga) e B0 (eólica), medida fora do treino."),
    ("r12", "r12_transferencia_obs_vs_pred.png", "Funções de transferência fora do treino: carga (A0) em duas semanas de 2025 e CF eólico (B0) diário em 2026."),
    ("r13", "r13_classificador_cortes.png", "Classificador de cortes: frequência de horas com corte por motivo e calibração das probabilidades."),
    ("s1", "s1_importacao_cenarios_2030.png", "Simulador determinístico: importação em 2030 por cenário, média e faixa entre os anos 2022–2025."),
    ("r15", "r15_regra_hidraulica.png", "Regra hidráulica emulada no Monte Carlo, comparada ao despacho observado nas mesmas datas."),
    ("r14", "r14_semana_simulada_2030.png", "Decomposição horária de uma semana simulada de 2030: geração por fonte, carga, data centers e importação."),
    ("mc2", "mc2_convergencia.png", "Convergência do Monte Carlo (média e P95 da importação anual)."),
    ("mc1", "mc1_distribuicao_importacao.png", "Distribuição acumulada da importação anual em 2030 por cenário de data centers e de eólica."),
    ("r16", "r16_efeito_pareado_e_anos_meteorologicos.png", "Esquerda: efeito dos data centers por sorteio (diferença pareada). Direita: importação anual por ano meteorológico sorteado."),
    ("r18", "r18_importacao_por_hora_2030.png", "2030: percentual de horas com importação por hora do dia e CF eólico médio por hora."),
    ("r17", "r17_curva_compensacao_eolica.png", "Importação média em 2030 em função da capacidade eólica adicional."),
    ("mc3", "mc3_sensibilidades.png", "Sensibilidades univariadas: variação da importação média em relação ao caso de referência."),
]
NUM = {k: i + 1 for i, (k, _, _) in enumerate(FIGURAS)}


def fig(k: str) -> str:
    _, arq, leg = FIGURAS[NUM[k] - 1]
    return f"\n![Figura {NUM[k]} — {leg}](figures/{arq})\n"


def F(k: str) -> str:
    return f"Figura {NUM[k]}"


def carregar():
    d = {}
    d["c"] = yaml.safe_load(open(CONFIG / "cenarios.yaml", encoding="utf-8"))
    d["cdc"] = yaml.safe_load(open(CONFIG / "cenarios_dc.yaml", encoding="utf-8"))
    d["mcc"] = json.load(open(MC / "mc_config.json", encoding="utf-8"))
    d["inc"] = json.load(open(MC / "mc_incerteza.json", encoding="utf-8"))
    d["chk"] = json.load(open(TAB / "checagens_brutas.json", encoding="utf-8"))
    for nome, path in {"R": MC / "mc_resumo.csv", "P": MC / "mc_diferencas_pareadas.csv", "L": MC / "mc_limites_importacao.csv",
                       "K": MC / "mc_compensacao_eolica.csv", "S": MC / "mc_sensibilidades.csv", "C": MC / "mc_convergencia.csv",
                       "B": MOD / "comparacao_hgb_baseline.csv", "T": MOD / "metricas_funcao_transferencia.csv",
                       "Dm": MOD / "cortes_metricas.csv", "taxa": MOD / "cortes_taxa_eventos_ano.csv",
                       "V": SIM / "validacao_sinteticos.csv", "E": SIM / "extrapolacao_clima.csv",
                       "cortes": TAB / "cortes_anuais.csv", "cob": TAB / "cobertura.csv", "inv": TAB / "inventario_raw.csv",
                       "det": SIM / "resultados_2030.csv", "detK": SIM / "compensacao_eolica_2030.csv",
                       "detS": SIM / "sensibilidades_2030.csv", "ff": SIM / "fatores_frota.csv",
                       "imp": TAB / "didatico_importancia_permutacao.csv", "curva": TAB / "didatico_curva_compensacao.csv",
                       "ih": TAB / "didatico_importacao_por_hora_2030.csv", "dc": CONFIG / "dc_trajetoria_oficial_ne.csv",
                       "dcinv": CONFIG / "data_centers_ne.csv", "plan": CONFIG / "plan_2rq_ne.csv",
                       "man": ROOT / "docs" / "manifest" / "manifest.csv"}.items():
        d[nome] = pd.read_csv(path)
    d["n"] = pd.read_csv(TAB / "didatico_numeros.csv", index_col=0)["valor"]
    return d


def main() -> None:
    d = carregar()
    c, mcc, inc, n = d["c"], d["mcc"], d["inc"], d["n"]
    R, P, K, S = d["R"], d["P"], d["K"], d["S"]

    def r(dc, w, m, col="media"):
        return R[(R.cenario_dc == dc) & (R.cenario_eolico == w) & (R.metrica == m)][col].iat[0]

    def p(dc, w, m, col="delta_media"):
        return P[(P.cenario_dc == dc) & (P.cenario_eolico == w) & (P.metrica == m)][col].iat[0]

    def k(dc, w, col):
        return K[(K.cenario_dc == dc) & (K.cenario_eolico == w)][col].iat[0]

    def nn(key):
        return float(n[key])

    sd = S.set_index("caso")
    cap = {w: c["eolica"]["capacidade_2030_MW"][w]["valor"] for w in ["baixa", "base", "alta"]}
    ldc = {x: K[K.cenario_dc == x].L_DC_MWmed.iat[0] for x in ["conservador", "central", "alto"]}
    dc = d["dc"]
    dc30 = dc[(dc.estudo == "2a RQ PLAN 2026-2030") & (dc.ano == 2030)].set_index("componente").mwmed
    dcrev = {e: dc[(dc.estudo == e) & (dc.ano == 2030) & (dc.componente == "total")].mwmed.iat[0]
             for e in ["PLAN 2026-2030", "1a RQ PLAN 2026-2030", "2a RQ PLAN 2026-2030"]}
    plan = d["plan"].set_index(["variavel", "ano"]).mwmed
    cortes = d["cortes"]
    ce = cortes[cortes.fonte == "eólica"].set_index("ano")
    cs = cortes[cortes.fonte == "solar"].set_index("ano")
    T = d["T"]
    a0g = T[T.modelo.str.startswith("A0 L_gross") & (T.metodo == "HGB")].MAE
    a0p = T[T.modelo.str.startswith("A0 L_gross") & (T.metodo != "HGB")].MAE
    a0n = T[T.modelo.str.startswith("A0 L_net") & (T.metodo == "HGB")].MAE
    b0 = T[(T.modelo == "B0 CF eólico pot")]
    c0 = T[(T.modelo == "C0 CF solar pot")]
    V, E = d["V"], d["E"]
    vb = V[V.modelo == "B0"].set_index("ano")
    va = V[V.modelo == "A0"].set_index("ano")
    B = d["B"].set_index(["alvo", "h"])
    Dm = d["Dm"]
    taxa = d["taxa"].set_index(d["taxa"].columns[0])
    det, detK, detS = d["det"], d["detK"], d["detS"]
    detm = det.groupby(["cenario_dc", "cenario_eolico"]).importacao_TWh.mean()
    deth = det.groupby(["cenario_dc", "cenario_eolico"]).horas_importacao.mean()
    detSm = detS.groupby("caso").importacao_TWh.mean()
    ff = d["ff"].set_index(d["ff"].columns[0])
    imp = d["imp"]
    ih = d["ih"]
    curva = d["curva"]
    cv_ref = curva[(curva.cenario_dc == "sem_dc") & (curva.dW_MW == 0)].importacao_TWh.iat[0]
    cc = curva[curva.cenario_dc == "central"]
    imp_en = float(np.interp(K[(K.cenario_dc == "central") & (K.cenario_eolico == "base")].dW_energia_anual_MW.iat[0], cc.dW_MW, cc.importacao_TWh))
    C = d["C"].set_index("n")
    inv = d["inv"]
    dcinv = d["dcinv"]
    eta = inc["eta2"]
    chk = d["chk"]
    ihc = ih[ih.cenario_dc == "central"].set_index("hora").pct_horas_importacao
    ih0 = ih[ih.cenario_dc == "sem_dc"].set_index("hora").pct_horas_importacao

    # ---------------- tabelas
    t_dados = tab(pd.DataFrame([
        ["ONS — balanço de energia por subsistema", "horária, 2022-01 → 2026-11", "carga, geração hidráulica, térmica, eólica, solar, intercâmbio", "fechamento do balanço; hidráulica e térmica do simulador; intercâmbio observado"],
        ["ONS — carga verificada (API)", "30 min → horária, 2022-01 → 2026-11", "carga global, carga líquida de MMGD, MMGD", "alvo dos modelos A e A0; MMGD (E0); nível e forma da carga"],
        ["ONS — geração por usina", "horária, 2022-01 → 2026-11", "geração de cada usina, inclusive grupos MMGD", "separar MMGD da solar do balanço; conferências"],
        ["ONS — fator de capacidade por usina", "horária, 2022-01 → 2026-11", "geração e capacidade de cada usina eólica/solar, coordenadas", "denominador do CF; alvo dos modelos B, B0, C, C0; pesos espaciais do clima"],
        ["ONS — constrained-off eólico e solar", "30 min → horária; eólica 2022-01+, solar 2024-04+", "geração, referência, corte apurado (GNRa) por motivo", "CF potencial = (geração + GNRa)/capacidade; rótulos do classificador D"],
        ["ONS — capacidade instalada", "fotografia", "unidades geradoras, datas de operação", "conferência das capacidades"],
        ["ANEEL — SIGA", "fotografia 2026-11-01", "empreendimentos por fase, potência, coordenadas", "pontos ERA5 (clusters); cenários eólicos de 2030"],
        ["ANEEL — MMGD", "fotografia 2026-11-10", "potência de micro e minigeração por UF", "caracterização; contém dados pessoais tarjados (só agregados)"],
        ["Open-Meteo (ERA5)", "horária, 1995-01 → 2026-11, 34 pontos", "temperatura, umidade, temperatura aparente, vento a 100 m, irradiância", "features de todos os modelos de carga, eólica e solar"],
        ["IBGE — Censo 2022", "por UF", "população", "pesos da temperatura das capitais"],
        ["Calendário (biblioteca holidays)", "diária, 2015–2030", "feriados nacionais e estaduais, Carnaval, São João, pontes", "features de calendário dos modelos de carga"],
        ["EPE — PDE 2035", "anual", "carga por subsistema, MMGD, expansão indicativa, limite de exportação", "sensibilidade de carga; cenário eólico alto; limite de 21 GW"],
        ["ONS/EPE/CCEE — PLAN 2026–2030 (PLAN, 1ª e 2ª RQ)", "anual, 2026–2030", "carga do NE, MMGD, carga de data centers de Rede Básica", "nível de carga e MMGD de 2030; cenários de data centers"],
        ["Inventário documental de data centers", "17 itens", "potência, definição, maturidade, fonte", "componente do cenário alto; conferência das projeções"],
    ], columns=["Fonte / conjunto", "Resolução e período", "Variáveis principais", "Como é usado no estudo"]))

    t_inconsist = tab(pd.DataFrame([
        ["Balanço do ONS passa a incluir a MMGD em 29/04/2023 (degrau de ~0,5 GW na carga)", "carga e solar com definições diferentes antes e depois", "usar a carga da API (definição homogênea) e tratar a MMGD como série própria", "modelos de carga sem quebra artificial; MMGD projetada à parte"],
        ["Duas estimativas de MMGD do ONS diferem em 30–370 MWmed por trimestre", "incerteza na parcela distribuída", "usar a estimativa da API, coerente com a carga usada", "documentado; sensibilidade de MMGD"],
        [f"Geração de referência do constrained-off abaixo da geração em {f(chk['coff_eol_usina_h_ref<ger_(% horas-usina)'])}% das horas-usina", "a referência não é o potencial físico", "potencial = geração + GNRa apurada (só nas horas restritas)", "alvo B/B0 sem contar corte em dobro"],
        [f"Corte eólico de {f(ce.loc[2022, 'corte_%_do_potencial'])}% (2022) para {f(ce.loc[2025, 'corte_%_do_potencial'])}% (2025) do potencial", "CF observado deixa de refletir o vento", "modelar o CF potencial; classificador só descritivo", "perfis de 2030 representam o recurso, não o corte histórico"],
        ["CF potencial salta de 0,42 (2024) para 0,48 (2025)", "parte é clima, parte é frota nova", "treinar B0/C0 na frota recente; fator de frota no determinístico", "não subestimar a geração de 2030"],
        ["Balanço de jan–mai/2026: 878 horas não fecham", "dados ainda em consistência", "2026 fica fora da calibração do balanço", "nenhuma"],
        [f"FC por usina: {f(chk['fc_capacidade_zero_ou_nula'], 0)} horas-usina com capacidade 0 e {f(chk['fc_cf_>1.05_recalculado'], 0)} com geração > 105% da capacidade", "registro de capacidade defasado", "excluir capacidade 0 do CF agregado; não recortar valores", "impacto ≈ 0,3 TWh em ~450 TWh"],
        ["SIGA sem datas previstas para projetos fora de operação", "não dá para datar a expansão", "cenários eólicos por fase (operação, construção) + expansão indicativa do PDE", "eólica de 2030 é hipótese de cenário"],
        ["PDE 2035 não separa data centers por subsistema", "não dá para reproduzir a projeção de DC do PDE", "usar a projeção do PLAN (ONS/EPE/CCEE), que separa", "cenários de DC com fonte oficial e sem dupla contagem"],
        ["Slides da 2ª RQ do PLAN só por download manual (HTTP 403)", "rastreabilidade", "download manual registrado no manifesto; valores lidos dos rótulos dos gráficos", "documentado"],
        ["Dados de ERA5 sem ciclo noturno do vento (jato noturno)", "o vento explica menos o padrão diário", "hora como feature; resíduos com ciclo diário preservado", "perfil diário do CF reproduzido"],
        ["Sem limite de importação documentado para o NE", "não há como medir risco de suprimento", "reportar só horas acima de 6/8/10 GW (sensibilidade)", "nenhuma afirmação de risco de déficit"],
    ], columns=["Inconsistência ou achado", "Problema", "Decisão", "Efeito nos modelos e resultados"]))

    t_modelos = tab(pd.DataFrame([
        ["A (h = 1 h, 24 h)", "validação: previsão de curto prazo", "carga líquida horária (MWmed)", "calendário, temperatura, temp. aparente, umidade, CDH, irradiância, lags do alvo (≥ h) e médias móveis", "toda a história antes do mês testado", "12 dobras mensais em 2025", "previsão da carga", "só validação acadêmica"],
        ["B (h = 1 h, 24 h)", "validação", "CF eólico potencial", "hora, mês, dia do ano, vento e vento³ a 100 m, lags e médias móveis", "idem", "idem", "previsão do CF", "só validação"],
        ["C (h = 1 h, 24 h)", "validação", "CF solar observado", "hora, mês, dia do ano, irradiância, temperatura, lags", "idem", "idem", "previsão do CF", "só validação"],
        ["A0", "função de transferência", "carga bruta / média do ano", "calendário completo + temperatura, temp. aparente, umidade, CDH, irradiância (sem lags)", "2022–2025", "deixando um ano de fora", "forma horária da carga", "perfis de 2030 (Monte Carlo)"],
        ["E0", "função de transferência", "MMGD / média móvel de 365 dias", "hora, mês, dia do ano, irradiância nas capitais e nos polos, temperatura", "2022-01 → 2026-10", "resíduos fora da amostra", "forma horária da MMGD", "perfis de 2030"],
        ["B0", "função de transferência", "CF eólico potencial", "hora, mês, dia do ano, vento e vento³ a 100 m (pesos da frota atual)", "2024-07 → 2026-10 (frota recente)", "temporal: 2025 e 2026 fora do treino", "CF eólico horário", "perfis de 2030; fator de frota do determinístico"],
        ["C0", "função de transferência", "CF solar potencial", "hora, mês, dia do ano, irradiância nos polos, temperatura", "2024-07 → 2026-10", "temporal", "CF solar horário", "perfis de 2030; fator de frota"],
        ["D", "classificador (viabilidade)", "hora com corte > 1% da capacidade, por motivo", "potencial eólico e solar, carga, MMGD, excedente bruto previsto, capacidades, calendário", "2023–2024 e 2024-07 → 2025", "temporal: 2025 e 2026", "probabilidade de corte", "só descritivo (não entra no simulador)"],
    ], columns=["Modelo", "Papel", "Alvo (saída)", "Features (entradas)", "Treino", "Validação", "Saída", "Onde é usado"]))

    nd = lambda v: 3 if v < 1 else 0
    t_bt = tab(pd.DataFrame([[a, h, f(B.loc[(a, h), "MAE"], nd(B.loc[(a, h), "MAE"])),
                              f"{B.loc[(a, h), 'metodo_melhor_baseline']} ({f(B.loc[(a, h), 'MAE_melhor_baseline'], nd(B.loc[(a, h), 'MAE_melhor_baseline']))})",
                              f"{f(B.loc[(a, h), 'ganho_MAE_%'], 0)}%", f"{B.loc[(a, h), 'meses_HGB_melhor']}/{B.loc[(a, h), 'meses']}"]
                             for a, h in B.index], columns=["Alvo", "h", "MAE HGB", "Melhor baseline (MAE)", "Ganho", "Meses em que vence"]))

    t_termos = tab(pd.DataFrame([
        ["Carga bruta L(t)", "forma horária (A0 + resíduo) × 16.180 MWmed", "2ª RQ do PLAN: 18.278 menos 2.098 de DC"],
        ["MMGD(t)", "forma horária (E0 + resíduo) × 2.386 MWmed", "2ª RQ do PLAN"],
        ["Eólica(t)", "CF (B0 + resíduo) × capacidade do cenário", "SIGA + PDE: 32,3 / 34,3 / 39,4 GW"],
        ["Solar(t)", "CF (C0 + resíduo) × 13,5 GW", "SIGA (operação + construção)"],
        ["Hidráulica(t)", "regra emulada: energia diária do ano hidrológico sorteado + resposta intradiária à carga líquida", "balanço ONS 2022–2025"],
        ["Térmica(t)", "série horária do ano hidrológico sorteado", "balanço ONS 2022–2025"],
        ["L_DC", "constante (flat) no ano", "2ª RQ do PLAN e inventário"],
        ["M(t)", "Hidr + Térm + Eól + Sol + MMGD − (L + L_DC)", "importação = max(0, −M); excedente = max(0, M)"],
    ], columns=["Termo do balanço", "Como é gerado em 2030", "De onde vem o nível"]))

    t_cen = tab(pd.DataFrame([
        ["Data centers", "sem_dc", "0", "nenhum data center novo de Rede Básica"],
        ["", "conservador", f(ldc["conservador"], 0) + " MWmed", "só contratos assinados (2ª RQ)"],
        ["", "central", f(ldc["central"], 0) + " MWmed", "2ª RQ do PLAN: 100% contratos + 50% pareceres favoráveis"],
        ["", "alto", f(ldc["alto"], 0) + " MWmed", "contratos + 100% dos pareceres + anúncios com MW (em rampa)"],
        ["Eólica", "baixa", f(cap["baixa"] / 1000) + " GW", "só usinas em operação (SIGA)"],
        ["", "base", f(cap["base"] / 1000) + " GW", "operação + construção"],
        ["", "alta", f(cap["alta"] / 1000) + " GW", "base + expansão indicativa do PDE até 2030, alocada ao NE"],
        ["Solar", "única", "13,5 GW", "operação + construção"],
        ["Carga (sem DC)", "única", "16.180 MWmed", "2ª RQ do PLAN; PDE como sensibilidade"],
        ["MMGD", "única", "2.386 MWmed", "2ª RQ do PLAN; faixa 1.939–2.718 como sensibilidade"],
        ["Intercâmbio", "—", "exportação ≤ 21 GW", "PDE 2035; importação sem limite documentado (6/8/10 GW em sensibilidade)"],
    ], columns=["Dimensão", "Cenário", "Valor em 2030", "Definição"]))

    ordem = ["sem_dc", "conservador", "central", "alto"]
    t_res = tab(pd.DataFrame([[x, f(0 if x == "sem_dc" else ldc[x], 0),
                               f"{f(r(x, 'base', 'importacao_TWh'))} [{f(r(x, 'base', 'importacao_TWh', 'p5'))}–{f(r(x, 'base', 'importacao_TWh', 'p95'))}]",
                               f(r(x, "base", "horas_importacao"), 0), f(r(x, "base", "importacao_p95_MW"), 0),
                               f(r(x, "base", "importacao_pico_MW"), 0), f(r(x, "base", "excedente_TWh"), 0),
                               f(r(x, "base", "excedente_acima_limite_exp_TWh"))] for x in ordem],
                             columns=["DC", "L_DC (MWmed)", "Importação TWh/ano [P5–P95]", "Horas com importação", "P95 horário (MW)",
                                      "Pico (MW)", "Excedente (TWh)", "Excedente > 21 GW (TWh)"]))
    t_mat = tab(pd.DataFrame([[x] + [f(r(x, w, "importacao_TWh")) for w in ["baixa", "base", "alta"]] for x in ordem],
                             columns=["DC \\ eólica", f"baixa ({f(cap['baixa']/1000)} GW)", f"base ({f(cap['base']/1000)} GW)", f"alta ({f(cap['alta']/1000)} GW)"]))
    t_par = tab(pd.DataFrame([[x, w, f"{f(p(x, w, 'importacao_TWh'))} [{f(p(x, w, 'importacao_TWh', 'delta_p5'))}–{f(p(x, w, 'importacao_TWh', 'delta_p95'))}]",
                               f"{f(p(x, w, 'horas_importacao'), 0)}"] for x in ["conservador", "central", "alto"] for w in ["baixa", "base", "alta"]],
                             columns=["DC", "eólica", "Δ importação TWh [P5–P95]", "Δ horas com importação"]))
    t_comp = tab(pd.DataFrame([[x, w, f(k(x, w, "dW_energia_anual_MW") / 1000),
                                f"{f(k(x, w, 'dW_importacao_anual_media_MW') / 1000)} [{f(k(x, w, 'dW_importacao_anual_p5_MW') / 1000)}–{f(k(x, w, 'dW_importacao_anual_p95_MW') / 1000)}]",
                                f(k(x, w, "dW_horas_importacao_media_MW") / 1000),
                                f"{f(k(x, w, 'dW_importacao_anual_media_MW') / k(x, w, 'dW_energia_anual_MW'))}×",
                                f"{f(k(x, w, 'absorcao_excedente_%'), 0)}%"] for x in ["conservador", "central", "alto"] for w in ["baixa", "base", "alta"]],
                              columns=["DC", "eólica", "ΔW energia (GW)", "ΔW importação anual (GW) [P5–P95]", "ΔW horas (GW)", "razão", "DC em horas de excedente"]))
    L = d["L"]

    def cel(x, g):
        row = L[(L.cenario_dc == x) & (L.cenario_eolico == "base")]
        return f"{f(row[f'horas_acima_{g}GW_media'].iat[0], 0)} h / {100 * row[f'P_ano_com_hora_acima_{g}GW'].iat[0]:.0f}%"
    t_lim = tab(pd.DataFrame([[x] + [cel(x, g) for g in [6, 8, 10]] for x in ordem], columns=["DC (eólica base)", "> 6 GW", "> 8 GW", "> 10 GW"]))
    t_sens = tab(pd.DataFrame([[s.caso, f(s.media_TWh, 2), f(s.delta_media_TWh, 2), f(s.efeito_DC_TWh, 2)] for s in S.itertuples()],
                              columns=["Caso (DC central, eólica base)", "Importação média (TWh)", "Δ vs. referência", "Efeito pareado dos DC (TWh)"]))
    t_conv = tab(pd.DataFrame([[f(i, 0), f(rw.media_TWh, 3), f(rw.p95_TWh, 3)] for i, rw in C.iterrows()],
                              columns=["Sorteios", "Média (TWh)", "P95 (TWh)"]))
    t_det = tab(pd.DataFrame([[x, f(detm[(x, "base")]), f(deth[(x, "base")], 0), f(detm[(x, "baixa")]), f(detm[(x, "alta")])] for x in ordem],
                             columns=["DC", "Importação, eólica base (TWh)", "Horas, eólica base", "Eólica baixa (TWh)", "Eólica alta (TWh)"]))
    t_lim_rob = tab(pd.DataFrame([
        ["Carga de data centers", f"a projeção oficial para 2030 foi de {f(dcrev['PLAN 2026-2030'], 0)} → {f(dcrev['1a RQ PLAN 2026-2030'], 0)} → {f(dcrev['2a RQ PLAN 2026-2030'], 0)} MWmed em ~8 meses", "muito rápida (a cada revisão quadrimestral)", f"atraso de 12 meses: {f(sd.loc['DC com atraso de 12 meses', 'delta_media_TWh'])} TWh; cenário alto: +{f(r('alto', 'base', 'importacao_TWh') - r('central', 'base', 'importacao_TWh'))} TWh", "próximas revisões do PLAN; pareceres e contratos do ONS"],
        ["Despacho hidráulico", "depende da hidrologia do São Francisco e da operação do ONS; só 4 anos de dados horários", "anual (hidrologia) e por política operativa", f"hidráulica plana: +{f(sd.loc['hidraulica plana', 'delta_media_TWh'])} TWh; histórico sem resposta: +{f(sd.loc['hidraulica historica sorteada (sem resposta)', 'delta_media_TWh'])} TWh", "série longa de vazões (P2 #13)"],
        ["Nível da carga", "crescimento econômico, clima, eletrificação", "anual", f"±5%: {f(sd.loc['carga -5%', 'delta_media_TWh'])} / +{f(sd.loc['carga +5%', 'delta_media_TWh'])} TWh", "revisões do PLAN"],
        ["Expansão eólica", "SIGA sem datas; cortes elevados desestimulam novos projetos", "anual", f"baixa: +{f(sd.loc['eolica baixa', 'delta_media_TWh'])}; alta: {f(sd.loc['eolica alta', 'delta_media_TWh'])} TWh", "leilões, outorgas, fase no SIGA"],
        ["Regime de cortes", "taxa de horas com corte de 7% para 69% em 3 anos; calibração do classificador instável", "rápida", "não entra no balanço (o estudo mede excedente, não corte)", "dados mensais de constrained-off"],
        ["Clima do ano", "variabilidade interanual do vento (ex.: 2009 fraco, 2012 forte)", "não previsível no horizonte", f"explica {100 * eta['ano_clima']:.0f}% da variância da importação anual", "tratado no Monte Carlo (31 anos)"],
        ["MMGD", "duas estimativas do ONS; crescimento acelerado", "anual", f"faixa 1.939–2.718 MWmed: {f(sd.loc['MMGD alta', 'delta_media_TWh'])} a +{f(sd.loc['MMGD baixa', 'delta_media_TWh'])} TWh", "PLAN; ANEEL"],
        ["Limites de intercâmbio", "importação sem limite documentado; exportação depende de obras até 2030", "por obra", "não quantificado como risco", "PAR/PEL do ONS, PDE"],
    ], columns=["Variável", "Por que é incerta", "Velocidade de mudança", "Efeito estimado (importação, caso central)", "O que acompanhar"]))

    hm = int(ihc.idxmax())
    txt = f"""# Relatório técnico — Data centers e expansão eólica no balanço horário do Nordeste (2030)

Documento de apresentação do projeto, passo a passo. Gerado por `python -m src.report.tecnico` em
{datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC, a partir das tabelas produzidas pelo pipeline.
Todos os números citados vêm de arquivos em `reports/` e `config/`.

## Sumário executivo

**Pergunta.** Se data centers entrarem no subsistema Nordeste até 2030, quanto aumenta a energia que a
região precisa importar do resto do país, em que horas isso acontece, e quanta capacidade eólica nova
compensaria esse consumo?

**Como respondemos.** Em quatro etapas, cada uma alimentando a seguinte:
1. **Dados.** Coletamos e auditamos dados horários de operação do ONS (2022–2025), cadastros da ANEEL,
   planos oficiais (PDE 2035 e PLAN 2026–2030) e 31 anos de reanálise climática ERA5.
2. **Modelos.** Treinamos modelos de *machine learning* (gradient boosting) que transformam clima e
   calendário em perfis horários de carga, geração eólica, geração solar e MMGD.
3. **Simulador.** Um simulador monta, hora a hora, o balanço de 2030 sob cenários de data centers e de
   expansão eólica.
4. **Monte Carlo.** Uma simulação Monte Carlo repete esse balanço 2.000 vezes com climas e hidrologias
   diferentes, para medir a incerteza.

**Principais resultados (2030, eólica base).**
- **Importação.** A importação média vai de **{f(r('sem_dc', 'base', 'importacao_TWh'))} TWh/ano** sem
  novos data centers para **{f(r('central', 'base', 'importacao_TWh'))} TWh/ano** com a carga de data
  centers projetada oficialmente ({f(dc30['total'], 0)} MWmed).
  - No mesmo clima, o acréscimo é de +{f(p('central', 'base', 'importacao_TWh'))} TWh e
    +{f(p('central', 'base', 'horas_importacao'), 0)} horas com importação por ano.
  - O acréscimo aparece em 100% dos cenários climáticos simulados.
- **Quando a importação acontece.** No fim da tarde (pico às {hm}h, quando a solar cai) e de madrugada.
  Ao meio-dia ela é praticamente nula.
- **Compensação eólica.** Compensar em **energia anual** exigiria
  {f(k('central', 'base', 'dW_energia_anual_MW') / 1000)} GW eólicos a mais. Compensar a **importação
  anual** exigiria {f(k('central', 'base', 'dW_importacao_anual_media_MW') / 1000)} GW,
  {f(k('central', 'base', 'dW_importacao_anual_media_MW') / k('central', 'base', 'dW_energia_anual_MW'))}
  vezes mais.
- **Excedente.** O NE continua fortemente exportador (excedente de
  ~{f(r('central', 'base', 'excedente_TWh'), 0)} TWh/ano). {f(k('central', 'base', 'absorcao_excedente_%'), 0)}%
  da energia dos data centers cairia em horas de excedente regional.
- **Clima e hipóteses.** O clima do ano pesa tanto quanto a escolha de cenário. Os resultados também são
  sensíveis à carga de data centers, que a projeção oficial revisou de {f(dcrev['PLAN 2026-2030'], 0)}
  para {f(dcrev['2a RQ PLAN 2026-2030'], 0)} MWmed em oito meses, e à operação hidráulica.

## 1. Contexto, pergunta e escopo

**Contexto.**
- O Nordeste concentra a maior parte da geração eólica do Brasil e hoje exporta energia para o resto do
  SIN na grande maioria das horas (86–93% das horas em 2022–2025).
- Ao mesmo tempo, há um volume crescente de pedidos de conexão de grandes cargas, sobretudo data centers
  e hidrogênio, na região (Pecém/CE, Bahia, Piauí).
- Uma carga de data center é praticamente constante nas 24 horas, enquanto a eólica e a solar variam ao
  longo do dia e do ano. A pergunta não é só "há energia suficiente no ano?", mas "em quais horas falta?".

**Pergunta de pesquisa.** Sob diferentes cenários de entrada de data centers e de expansão eólica, como
mudam a necessidade de importação e os excedentes horários do subsistema Nordeste em 2030, e quanto de
expansão eólica compensaria o consumo adicional?

**Variável central.** A margem horária do NE:

> M(t) = G_NE(t) − [L_base(t) + L_DC(t)] · importação = max(0, −M) · excedente = max(0, M)

G_NE é a geração do subsistema, L_base a carga sem novos data centers e L_DC a carga incremental de data
centers.
- M negativa significa que o NE precisa **importar** do restante do SIN naquela hora. **Não** significa
  déficit de suprimento ou blackout.
- M positiva é **excedente** regional, que pode ser exportado ou cortado.

**Recorte e escopo.**
- **Região.** Subsistema Nordeste do ONS, formado por AL, BA, CE, PB, PE, PI, RN e SE. O Maranhão
  pertence ao subsistema Norte.
- **Período.** Histórico de calibração 2022–2025; ano-alvo 2030.
- **Fora do escopo.** Fluxo de potência e rede elétrica interna, adequação de suprimento do SIN e
  viabilidade econômica.
- **Natureza dos resultados.** São **condicionais a cenários** declarados, não previsões.

**Glossário mínimo.**
- **MWmed:** potência média num intervalo. 1 MWmed durante 1 hora = 1 MWh; a média anual em MWmed × 8.760
  h = energia anual em MWh.
- **CF (fator de capacidade):** geração ÷ capacidade instalada, entre 0 e 1.
- **Constrained-off / GNRa:** redução da geração eólica ou solar por ordem do ONS. A GNRa (geração não
  realizada apurada) é a estimativa oficial da energia cortada.
- **CF potencial:** (geração + GNRa) ÷ capacidade, isto é, o que o vento permitiria gerar sem corte.
- **MMGD:** micro e minigeração distribuída, a solar nos telhados. Reduz a carga vista pela rede durante o dia.
- **Rede Básica:** rede de transmissão de alta tensão. Os grandes data centers se conectam a ela.
- **PLAN / RQ:** Planejamento Anual da Operação Energética do ONS/EPE/CCEE e suas Revisões Quadrimestrais
  da previsão de carga.
- **PDE:** Plano Decenal de Expansão de Energia (EPE).
- **ERA5:** reanálise climática global do ECMWF, uma "reconstrução" horária do clima desde 1940.
- **HGB:** HistGradientBoosting, o algoritmo de *machine learning* usado (seção 5.1).

## 2. Visão geral do pipeline

O projeto é um pipeline reprodutível em Python: cada etapa é um módulo que lê arquivos da etapa anterior
e grava os seus. O comando `python -m src.pipeline` refaz tudo a partir dos dados brutos, e foi conferido
que a reexecução reproduz exatamente os mesmos números.

```mermaid
flowchart LR
  subgraph D[1. Dados]
    ONS[ONS: balanço, carga API, usinas, cortes] --> INT[Base horária integrada 2022-2026]
    ERA[ERA5 1995-2026, 34 pontos] --> CLI[Clima ponderado]
    ANEEL[ANEEL SIGA e MMGD] --> CEN
    PLAN[PLAN 2026-30 e PDE 2035] --> CEN[Cenários 2030]
    INV[Inventário de data centers] --> CEN
  end
  subgraph M[2. Modelos]
    INT --> BT[Backtesting curto prazo A, B, C]
    INT --> TF[Funções de transferência A0, E0, B0, C0]
    CLI --> TF
    INT --> CL[Classificador de cortes D]
  end
  subgraph S[3. Simulador 2030]
    TF --> SIN[Perfis sintéticos de 2030 para 31 anos]
    CEN --> DET[Simulador determinístico]
    INT --> DET
    SIN --> MCS[Monte Carlo 2.000 sorteios]
    CEN --> MCS
  end
  subgraph R[4. Resultados]
    MCS --> RES[Importação, excedente, compensação eólica, sensibilidades]
    DET --> RES
  end
```

| Etapa | Módulo | Entrada | Saída |
|---|---|---|---|
| Coleta | `src/collect/*` | APIs e portais oficiais | `data/raw/` e manifesto com SHA-256 |
| Integração | `src/build/ne_hourly.py` | brutos ONS e ERA5 | base horária do NE (`data/interim/`) |
| Auditoria | `src/audit/run_audit.py` | base integrada | relatório de qualidade, tabelas, figuras |
| Features | `src/features/build.py`, `clima_historico.py` | base integrada, ERA5 | base analítica; clima 1995–2026 |
| Modelos | `src/models/backtest.py`, `cortes.py` | base analítica | métricas de validação |
| Perfis sintéticos | `src/sim/sinteticos.py` | modelos A0/E0/B0/C0, clima | perfis de 2030 para 31 anos e resíduos |
| Simulador | `src/sim/deterministico.py`, `montecarlo.py` | perfis, cenários | distribuições de importação etc. |
| Relatórios | `src/report/*` | tabelas | este documento |

## 3. Dados coletados e onde cada um entra

A coleta foi feita por scripts. Cada arquivo foi registrado num manifesto (`docs/manifest/manifest.csv`,
{len(d['man'])} registros) com URL de origem, data de coleta, tamanho e hash SHA-256. No total são
{len(inv)} arquivos brutos e {f(inv.bytes.sum() / 1e9, 2)} GB.

{t_dados}
{fig('r01')}
As séries do ONS cobrem de 2022 a 2026 sem lacunas internas ({F('r01')}). Duas exceções: o
constrained-off solar só existe desde 2024-04, e a MMGD aparece na geração por usina só desde 2023-04-29.

O clima é amostrado em 34 pontos ({F('r02')}):
- **8 capitais:** temperatura, umidade e irradiância, ponderadas pela população de cada UF. Representam a
  demanda.
- **16 pontos eólicos e 10 solares:** escolhidos por *k-means* sobre as coordenadas das usinas do SIGA,
  ponderado pela potência. Cada usina é associada ao ponto mais próximo, e o vento de cada ponto é
  ponderado pela capacidade das usinas que ele representa.

A rede de usinas despachadas pelo ONS no NE soma {f(nn('n_usinas_eol'), 0)} usinas ou conjuntos eólicos
({f(nn('cap_eol_mapa_MW') / 1000)} GW) e {f(nn('n_usinas_sol'), 0)} solares ({f(nn('cap_sol_mapa_MW') / 1000)} GW).
{fig('r02')}

## 4. Tratamento e caracterização dos dados

### 4.1 Harmonização temporal e de unidades

Todas as séries foram levadas a uma mesma convenção: `t` = início da hora, no horário de Brasília (UTC−3;
não há horário de verão desde 2019).
- **API de carga.** Informa o *fim* do intervalo de 30 minutos em UTC. Foi convertida para o início do
  intervalo em Brasília.
- **Agregação para hora.** Os pares de 30 minutos foram agregados pela média dos MWmed, que equivale à
  energia da hora em MWh.
- **ERA5.** As variáveis instantâneas (vento, temperatura) foram alinhadas à hora do ONS pela média dos
  instantes t e t+1h. A irradiância, que é média da hora anterior, foi alinhada pelo valor rotulado t+1h.
- **Sem imputação.** Nenhuma lacuna foi preenchida, e anomalias foram marcadas, não recortadas.
- **Testes automatizados.** Verificam a conversão de fuso, a agregação, MW × h = MWh, a ausência de
  duplicatas e a cardinalidade das junções.

### 4.2 Qualidade e reconciliação

- **Duplicatas e lacunas.** Nenhuma duplicata de chave e nenhuma lacuna interna nas bases centrais.
- **Fechamento do balanço.** O balanço do ONS fecha exatamente (geração − carga − intercâmbio = 0) em
  2022–2025. Em jan–mai/2026 há 878 horas que não fecham, porque os dados ainda estão em consistência.
- **Intercâmbio.** O intercâmbio entre subsistemas reconcilia com o do balanço quando somado com sinal.
- **Inconsistências.** A tabela abaixo consolida as inconsistências encontradas e o que foi decidido para
  seguir.

{t_inconsist}

### 4.3 Carga e MMGD

**Mudança de definição.** A análise exploratória da carga revelou um degrau de cerca de 0,5 GW em
29/04/2023 ({F('q1')}). Nessa data o balanço do ONS passou a somar a MMGD estimada tanto à carga quanto à
geração solar. O balanço continuou fechando, mas a série de carga mudou de definição. Se usada
diretamente, essa mudança seria interpretada pelos modelos como um salto real de consumo.
- **Decisão.** Usar a carga da API de carga verificada do ONS, que traz separadamente a carga global, a
  carga líquida de MMGD e a MMGD, com definição homogênea desde 2022.
- **Na modelagem**, a forma horária é modelada sobre a **carga bruta**. A carga líquida muda de forma ao
  longo dos anos porque a MMGD "cava" o meio-dia cada vez mais. A MMGD tem um modelo próprio (E0).
{fig('q1')}
**Perfis horários.** Os mapas de calor hora × mês ({F('r04')}) e o perfil diário médio ({F('q3')})
mostram a complementaridade das fontes:
- **Carga líquida:** mínima ao meio-dia, por causa da MMGD, e máxima entre 18h e 22h.
- **Eólica:** forte à noite e na madrugada, com safra entre julho e novembro.
- **Solar e MMGD:** só durante o dia.

A janela crítica é o início da noite: a solar já caiu e a eólica ainda não subiu totalmente. Esses
padrões justificam usar **hora e mês como features** em todos os modelos e reaparecem nos resultados de
2030.
{fig('r04')}{fig('q3')}
**Temperatura e calendário.** A carga diária cresce com a temperatura ({F('r05')}), com correlação de
{f(nn('temp_corr_util'), 2)} nos dias úteis e ~{f(nn('temp_slope_util_pct_por_C'))}% de carga a mais por
°C. Fins de semana e feriados ficam ~{f(abs(nn('fim_semana_nivel_pct')))}% abaixo. Daí as features de
temperatura (temperatura, temperatura aparente, graus-hora de resfriamento) e de calendário (dia da
semana, feriados nacionais e estaduais, Carnaval, São João, pontes) dos modelos de carga.
{fig('r05')}
### 4.4 Geração eólica e cortes

**Capacidade.** A capacidade eólica do NE cresceu de ~20 GW para ~32 GW entre 2022 e 2026; a solar
centralizada, de ~3,5 para ~11,5 GW ({F('r03')}). A geração por fonte está na {F('q2')}.
- **Ponto de partida dos cenários.** A capacidade observada em 2026 é a base dos cenários de 2030.
- **Limite do SIGA.** O cadastro aberto do SIGA não traz datas previstas para projetos fora de operação,
  por isso os cenários eólicos são definidos por fase do empreendimento (seção 6).
{fig('r03')}{fig('q2')}
**Cortes (constrained-off).** O corte eólico apurado subiu de {f(ce.loc[2022, 'corte_%_do_potencial'])}%
do potencial em 2022 para {f(ce.loc[2023, 'corte_%_do_potencial'])}% (2023),
{f(ce.loc[2024, 'corte_%_do_potencial'])}% (2024) e {f(ce.loc[2025, 'corte_%_do_potencial'])}% em 2025
({f(ce.loc[2025, 'GNRa_TWh'])} TWh). O corte solar foi de {f(cs.loc[2025, 'corte_%_do_potencial'])}% em
2025 ({F('q4')}). Em 2025 o motivo energético (ENE, excesso de oferta no sistema) passou a dominar.

**Quando os cortes acontecem** ({F('r06')}).
- **Corte energético (ENE):** concentra-se **de dia**, entre ~9h e 15h, de maio a novembro. É quando a
  solar, a MMGD e uma eólica ainda forte se somam a uma carga líquida baixa.
- **Corte por confiabilidade (CNF):** concentra-se nas manhãs de julho a outubro.
- **Corte elétrico externo (REL):** em 2025, vem sobretudo de um evento em fevereiro.

Esse padrão indica que o excedente atual é, em grande parte, diurno, e é nessas horas que uma carga
constante de data centers absorveria energia.
{fig('q4')}{fig('r06')}
**Consequência para a modelagem.** O CF eólico *observado* deixou de refletir o vento ({F('q6')}).
- **Correlação.** A correlação entre vento³ e CF observado caiu de 0,87 (2022) para 0,58 (2025), enquanto
  com o CF *potencial* (geração + corte apurado) ela fica em 0,85–0,89.
- **Alvo.** Por isso o alvo dos modelos eólicos é o **CF potencial**: queremos o recurso físico, e o corte
  é justamente uma das saídas que o balanço deve revelar, não um dado de entrada.
- **Por que não a geração de referência.** O ONS publica uma "geração de referência", mas ela não serve
  como potencial: fica abaixo da geração verificada em {f(chk['coff_eol_usina_h_ref<ger_(% horas-usina)'])}%
  das horas-usina. Por isso o corte vem da GNRa, que o ONS apura apenas nas horas com restrição.
{fig('q6')}
**Frota mais eficiente.** O CF potencial médio subiu de 0,42 (2024) para 0,48 (2025). A análise por faixa
de vento mostrou duas causas: 2025 foi mais ventoso, e a frota nova tem curva de potência 5–10% maior.
Por isso os modelos que projetam 2030 são treinados só na frota recente (2024-07 em diante), e o simulador
determinístico aplica um **fator de frota** por ano (1,05–1,09 para 2022–2024; ~1,00 para 2025).

**Ciclo diurno e limitação do ERA5.** O CF potencial é ~{f(100 * (nn('cf_noite_rel') - 1), 0)}% maior à
noite e ~{f(100 * (1 - nn('cf_meiodia_rel')), 0)}% menor ao meio-dia em relação à média do dia. O vento³
do ERA5 varia menos: ~{f(100 * (nn('v3_noite_rel') - 1), 0)}% à noite ({F('r09')}). A reanálise, com
resolução de ~30 km, suaviza o reforço noturno do vento observado nos parques do NE. Por isso a **hora do dia** é
uma feature importante do modelo eólico (seção 5.4), e os resíduos reamostrados no Monte Carlo preservam
o ciclo diário.
{fig('r09')}
### 4.5 Balanço, intercâmbio e importação

O NE foi exportador líquido em todo o período, de 34 TWh em 2022 a 56 TWh em 2025. Ainda assim importou
em 7–14% das horas ({F('q5')}).
- **Horários.** As importações históricas concentram-se de madrugada
  (~{f(nn('imp_hist_pct_madrugada'), 0)}% das horas entre 1h e 4h) e às 17h
  (~{f(nn('imp_hist_pct_17h'), 0)}%), e são raras ao meio-dia (~{f(nn('imp_hist_pct_meiodia'), 0)}%)
  ({F('r07')}).
- **Consequência.** Esse padrão antecipa o resultado principal: carga constante de data centers aumenta
  a importação justamente nas horas em que a eólica e a solar não cobrem a carga.
{fig('q5')}{fig('r07')}
### 4.6 Clima de longo prazo

**Os anos com dados não são típicos.** A série ERA5 de 1995–2025 mostra que 2022–2024, os anos com
dados de operação, estão entre os menos ventosos ({F('s2')}).
- **Variação entre anos.** O CF eólico potencial que a frota atual teria em cada ano varia de 0,39
  (2009) a 0,52 (2012).
- **Risco.** Calibrar só em 2022–2025 subestimaria anos ventosos e não mostraria anos muito fracos.
- **Consequência.** Por isso o Monte Carlo usa os 31 anos.
{fig('s2')}
### 4.7 Data centers: da pesquisa documental aos cenários

**O PDE 2035 não serve para os cenários de data centers.** A pergunta exige saber quanta carga de data
centers entra no NE. O PDE 2035, na carga de referência, embute data centers, mas não os separa por
subsistema nem por ano.

**A fonte usada: a previsão de carga do PLAN 2026–2030 (ONS/EPE/CCEE).** Ela publica a carga de data
centers de Rede Básica por subsistema. O critério soma 100% dos acessos com contrato assinado e 50% dos
que têm parecer favorável.
- **Revisões.** Para o NE em 2030, a projeção passou de {f(dcrev['PLAN 2026-2030'], 0)} MWmed (PLAN,
  nov/2025) para {f(dcrev['1a RQ PLAN 2026-2030'], 0)} (1ª RQ, mar/2026) e
  {f(dcrev['2a RQ PLAN 2026-2030'], 0)} MWmed (2ª RQ, jul/2026), dos quais
  {f(dc30['contratos_assinados'], 0)} já contratados ({F('r08')}).
- **Inventário.** Paralelamente, montamos um inventário documental de {len(dcinv)} projetos (portarias
  do MME, ANEEL, imprensa setorial), com a definição de potência de cada fonte e um grau de maturidade
  (M0 a M3).
- **Peso do principal projeto.** O maior projeto com obra iniciada (Pecém fase 1) tem ~300 MW de consumo
  previsto a partir de 2027.

**Decisões tomadas com o usuário.**
- **Caso-base.** Carga do PLAN sem os data centers de Rede Básica: 18.278 − 2.098 = 16.180 MWmed.
- **Cenários de data centers.** Conservador (só contratos), central (2ª RQ) e alto (contratos + 100% dos
  pareceres + anúncios com MW). O PDE ficou como sensibilidade.

Como a projeção oficial já é "MWmed de carga na rede", não se aplica PUE (eficiência do data center) sobre
ela; PUE e utilização só entram para os itens do inventário.
{fig('r08')}
## 5. Modelos implementados

### 5.1 O algoritmo: HistGradientBoosting (HGB)

Todos os modelos de *machine learning* usam o `HistGradientBoostingRegressor` (e o classificador
equivalente) do scikit-learn.

**Como funciona.**
- É um *gradient boosting* de árvores de decisão: o modelo é uma soma de muitas árvores pequenas, cada
  uma ajustada para corrigir o erro das anteriores.
- A versão "Hist" agrupa cada feature em até 255 faixas (histogramas), o que torna o treino rápido mesmo
  com dezenas de milhares de horas.

**Por que foi escolhido.**
- Captura relações não lineares (a curva de potência eólica é em forma de S) e interações (hora × mês)
  sem que seja preciso especificá-las.
- Não exige normalização das variáveis.
- Lida bem com tabelas de algumas dezenas de features.
- É o tipo de modelo recomendado pelo plano do projeto ("um modelo principal de árvores").
- Redes neurais (LSTM, MLP) ficaram fora do escopo obrigatório.

**Hiperparâmetros.** Fixos, sem busca, para evitar ajuste fino à amostra de teste: 400 iterações, taxa de
aprendizado 0,05, até 31 folhas por árvore, ≥ 40 amostras por folha, regularização L2 = 1, parada
antecipada automática e semente 20261111.

**Baselines.** Todo modelo é comparado a baselines ingênuos que qualquer operador usaria:
- *sazonal semanal:* o valor da mesma hora uma semana antes;
- *persistência:* o valor h horas antes;
- *perfil climatológico:* a média por mês e hora.

Só se considera que o modelo funciona quando ele supera o baseline de forma consistente.

### 5.2 Catálogo de modelos

Os modelos têm três papéis, conforme o acordo do projeto: (1) **validação acadêmica** de previsão de
curto prazo; (2) **função de transferência** clima → sistema, que gera os perfis de 2030; (3)
**classificação de cortes**. Nenhum modelo projeta 2030 por recursão hora a hora, o que acumularia erro.

{t_modelos}

### 5.3 Previsão de curto prazo (validação acadêmica)

**Objetivo.** Mostrar que as relações entre clima, calendário, carga e geração foram de fato capturadas.

**Desenho.**
- Para cada hora de 2025, prevemos o valor 1 hora e 24 horas à frente usando só informação disponível
  no momento da previsão: lags do alvo de pelo menos h horas e médias móveis que terminam na origem.
- O backtesting é de origem móvel: 12 dobras mensais, cada uma treinada com todo o histórico anterior ao
  mês testado.
- O clima do instante-alvo é o observado (ERA5), equivalente a uma previsão meteorológica perfeita. Por
  isso o desempenho é um **limite superior** do que se obteria em operação.

{t_bt}

**Resultado.**
- O HGB vence o melhor baseline em 10 a 12 dos 12 meses para todos os alvos ({F('r10')}).
- O ganho é grande para carga e eólica e pequeno (13%) para a solar a 24 h. Para a solar, a persistência
  de 24 h já é muito boa, porque o sol de hoje se parece com o de ontem.
- A {F('m1')} mostra uma semana típica.
{fig('r10')}{fig('m1')}
### 5.4 Funções de transferência clima → sistema (o coração da projeção)

**Por que são necessárias.** Para 2030 não temos carga nem geração observadas. A estratégia é:
1. Aprender, nos dados de 2022–2026, como o clima e o calendário determinam a **forma** horária de cada
   série.
2. Aplicar esse aprendizado ao clima de cada um dos 31 anos meteorológicos (1995–2025), dispostos no
   calendário de 2030.
3. Multiplicar a forma pelo **nível** de 2030 dado pelos cenários (carga e MMGD do PLAN, capacidades do
   SIGA/PDE).

Esses modelos não usam lags do alvo, porque em 2030 não há "valor da hora anterior" observado.

**As quatro funções.**
- **A0 — forma da carga bruta** (carga ÷ média do ano). Validada deixando um ano inteiro de fora: MAE
  de {f(100 * a0g.min())}–{f(100 * a0g.max())}% contra {f(100 * a0p.min())}–{f(100 * a0p.max())}% do
  perfil médio. Vence nos 4 anos.
  - Com a carga *líquida* o erro chegaria a {f(100 * a0n.max())}%, porque a forma muda com a MMGD. Isso
    confirmou a decisão da seção 4.3.
- **E0 — forma da MMGD** (MMGD ÷ média móvel de 365 dias, o que remove o crescimento da capacidade).
  Depende da irradiância.
- **B0 — CF eólico potencial.** Treinado só na frota recente (2024-07 a 2025-12) e testado em 2026: MAE
  {f(b0[b0.metodo == 'HGB'].MAE.iat[1], 3)} contra {f(b0[b0.metodo != 'HGB'].MAE.iat[1], 3)} do perfil
  médio, com viés de {f(b0[b0.metodo == 'HGB'].vies.iat[1], 3)}.
  - Treinado em 2022–2024 e testado em 2025, o viés seria de {f(b0[b0.metodo == 'HGB'].vies.iat[0], 3)},
    efeito da frota nova. Isso justifica a janela recente.
- **C0 — CF solar potencial.** MAE {f(c0[c0.metodo == 'HGB'].MAE.min(), 3)}–{f(c0[c0.metodo == 'HGB'].MAE.max(), 3)}
  contra {f(c0[c0.metodo != 'HGB'].MAE.min(), 3)}–{f(c0[c0.metodo != 'HGB'].MAE.max(), 3)} do perfil.

**O que os modelos usam.** A importância por permutação mede quanto o erro aumenta quando uma feature é
embaralhada ({F('r11')}).
- **B0:** o vento a 100 m domina, seguido da hora do dia, que corrige o ciclo noturno subestimado pelo
  ERA5.
- **A0:** hora, dia da semana e dia do ano dominam. A temperatura aparece com peso menor porque divide a
  informação sazonal com o dia do ano.

Importância por permutação **não** tem interpretação causal.
{fig('r11')}
A {F('r12')} mostra as previsões fora do treino. A carga acompanha o ciclo diário e semanal, com erros
maiores nos domingos, quando o modelo prevê uma queda menor que a observada. O CF eólico diário segue as
variações do vento ao longo de 2026.
{fig('r12')}
**Da previsão ao perfil sintético.**
- **Calendário e clima.** O clima de cada ano é colocado no calendário de 2030 por (mês, dia, hora); 29/02
  é descartado. O clima usa **pesos fixos** da frota de out/2026, para que todos os anos representem a
  mesma população de usinas.
- **Variabilidade.** Como as previsões são médias condicionais, mais "lisas" que a realidade, a
  variabilidade que falta é recomposta com **resíduos fora da amostra**: erros de previsão medidos por
  validação cruzada mensal na janela 2024-07..2025-12, reamostrados no Monte Carlo (seção 7).
- **Validação.**
  - O CF eólico sintético tem correlação horária de {f(vb['corr'].min(), 2)}–{f(vb['corr'].max(), 2)}
    com o observado.
  - Com os resíduos, o desvio-padrão horário reproduz o observado ({f(vb.loc[2025, 'dp_sint_com_residuo_aprox'], 3)}
    contra {f(vb.loc[2025, 'dp_obs'], 3)} em 2025).
  - Só {f(E[['pct_abaixo', 'pct_acima']].sum(axis=1).max(), 2)}% das horas de 1995–2021 ficam fora da
    faixa de treino de alguma variável, ou seja, quase não há extrapolação.

### 5.5 Classificador de cortes (Modelo D)

**Pergunta.** É possível prever, com informação disponível antes, as horas em que haverá corte eólico?

**Desenho.**
- Rótulo: hora com corte > 1% da capacidade, separado por motivo.
- Features: só variáveis ex-ante (potencial previsto, carga, MMGD, excedente bruto previsto, capacidades,
  calendário). Nunca o intercâmbio ou o despacho do mesmo instante.

**Resultados.**
- **Ordenação boa.** Para o corte energético, ROC-AUC de {f(Dm[Dm.alvo == 'y_ene'].ROC_AUC.min(), 2)}–{f(Dm[Dm.alvo == 'y_ene'].ROC_AUC.max(), 2)}
  e PR-AUC de {f(Dm[Dm.alvo == 'y_ene'].PR_AUC.min(), 2)}–{f(Dm[Dm.alvo == 'y_ene'].PR_AUC.max(), 2)},
  contra {f(Dm[Dm.alvo == 'y_ene'].PR_AUC_aleatorio.min(), 2)}–{f(Dm[Dm.alvo == 'y_ene'].PR_AUC_aleatorio.max(), 2)}
  ao acaso.
- **Calibração instável.** A frequência de horas com corte subiu de {f(100 * taxa.loc[2022, 'y_total'], 0)}%
  (2022) para {f(100 * taxa.loc[2025, 'y_total'], 0)}% (2025) ({F('r13')}). Um modelo treinado até 2024
  superestima as probabilidades de 2025, e um treinado até 2025 subestima as de 2026.
- **REL não é previsível.** O corte por indisponibilidade elétrica externa depende de eventos de rede que
  essas features não captam.

**Decisão.** O classificador fica como análise descritiva e **não** é usado para projetar probabilidades
de corte em 2030. É uma redução de escopo registrada, coerente com a regra de não aplicar modelos sob
mudança de regime.
{fig('r13')}
## 6. O simulador do balanço horário de 2030

### 6.1 O que é e como foi construído

O simulador é uma "contabilidade" hora a hora do NE em 2030 (8.760 horas). Para cada hora ele soma a
geração de cada fonte, subtrai a carga e a carga de data centers e registra se sobra (excedente) ou falta
(importação). Cada termo vem de uma etapa anterior:

{t_termos}

Os cenários combinam três eixos de data centers × eólica:

{t_cen}

**Métricas por ano simulado.**
- importação anual (TWh) e horas com importação;
- P95 horário e pico da importação (MW);
- maior sequência de horas importando;
- excedente e excedente acima do limite de exportação;
- horas com importação acima de 6/8/10 GW.

**Compensação eólica.** O simulador também calcula quanta capacidade eólica adicional (ΔW) compensa os
data centers, por quatro critérios:
1. **energia anual:** L_DC ÷ CF médio;
2. **importação anual** igual à do caso sem data centers;
3. **horas de importação** iguais;
4. **P95 horário** igual.

A busca é feita por bisseção, porque a importação diminui de forma monótona com ΔW.

### 6.2 Versão determinística (4 anos observados)

**Construção.** A primeira versão usa os perfis *observados* de 2022–2025 como quatro "anos climáticos":
- a forma é a de cada ano, escalada aos níveis de 2030;
- o CF eólico e o solar são corrigidos pelo fator de frota;
- a hidráulica e a térmica repetem o despacho histórico daquele ano.

Serve de verificação simples e transparente ({F('s1')}).

**Testes-limite automatizados.**
- carga de data centers zero reproduz o caso-base;
- mais carga nunca reduz a importação;
- MW × h fecha com MWh;
- a compensação encontrada devolve a importação ao caso-base.

{t_det}
{fig('s1')}
### 6.3 Por que não parar no determinístico

A versão determinística tem três limitações:
- só 4 anos climáticos, justamente anos pouco ventosos (seção 4.6);
- nenhuma medida de incerteza;
- extremos (picos, P95) mal representados.

Daí o Monte Carlo.

## 7. Monte Carlo

### 7.1 Propósito

O Monte Carlo transforma "um resultado por cenário" em uma **distribuição condicional** de resultados.
Ele responde perguntas como:
- quão diferente pode ser 2030 conforme o clima do ano;
- o efeito dos data centers aparece sempre ou só em anos ruins;
- quão estável é a estimativa.

A incerteza amostrada é **climática e operacional**. As escolhas de cenário (quantos data centers, quanta
eólica) ficam como eixos separados, porque não são aleatórias: são hipóteses de política e de mercado.

### 7.2 Como é feito um sorteio

```mermaid
flowchart TB
  W[Sorteia um ano meteorológico entre 1995 e 2025] --> P[Perfis sintéticos de 2030: carga, MMGD, CF eólico, CF solar]
  R[Sorteia blocos de 7 dias de resíduos, os 4 juntos, da mesma época do ano] --> P
  H[Sorteia um ano hidrológico entre 2022 e 2025] --> HT[Energia hidráulica diária e térmica]
  P --> B[Balanço horário 2030 para cada cenário]
  HT --> HR[Regra hidráulica emulada]
  HR --> B
  B --> M[Métricas do ano: importação, horas, P95, excedente]
```

**Componentes do sorteio.**
- **Ano meteorológico** (31 opções): define os perfis sintéticos gerados pelas funções de transferência.
- **Resíduos em blocos.** Sequências de 7 dias de erros fora da amostra das quatro séries, sorteadas
  **juntas** e de épocas do ano parecidas (±14 dias). Isso preserva a autocorrelação e a dependência
  entre carga, vento e sol (por exemplo, um dia nublado reduz a solar e a MMGD ao mesmo tempo). O tamanho
  do bloco foi testado: 3 e 14 dias dão o mesmo resultado.
- **Ano hidrológico** (2022–2025): define a energia hidráulica diária e a térmica.
- **Números aleatórios comuns.** O mesmo sorteio é aplicado a todos os cenários, de modo que as diferenças
  entre cenários são **pareadas**: medem o efeito do cenário no mesmo clima.

**Regra hidráulica emulada (decisão do usuário).**
- **Por que.** O despacho horário da hidráulica do NE responde às variações intradiárias da carga líquida
  (correlação ~0,7). Repetir o despacho de um ano qualquer, sem essa resposta, quebraria a dependência
  entre clima e despacho.
- **Como.** A regra mantém a energia diária do ano hidrológico sorteado e redistribui a geração dentro do
  dia seguindo a carga líquida simulada, com o coeficiente medido em cada ano (0,27–0,43), dentro dos
  mínimos e máximos mensais históricos ({F('r15')}).
- **Sensibilidades.** As alternativas (despacho histórico sem resposta, hidráulica plana) aparecem como
  sensibilidades.
{fig('r15')}
A {F('r14')} mostra uma semana de 2030 decomposta, extraída de um sorteio com importação próxima da
mediana: a eólica sustenta a noite, a solar e a MMGD sustentam o dia, e a importação (hachurada) aparece
no fim da tarde e em noites de pouco vento.
{fig('r14')}
### 7.3 Convergência

Foram usados {f(mcc['n'], 0)} sorteios (semente {mcc['semente']}). De 1.500 para 2.000 sorteios, a média
da importação anual mudou {f(abs(C.loc[2000, 'var_media_%']), 2)}% e o P95,
{f(abs(C.loc[2000, 'var_p95_%']), 2)}% ({F('mc2')}).

{t_conv}
{fig('mc2')}
## 8. Resultados

### 8.1 Distribuições de 2030

{t_res}

Importação média (TWh/ano) por cenário de data centers × eólica:

{t_mat}

As faixas P5–P95 são largas ({F('mc1')}): o mesmo cenário central pode resultar em
{f(r('central', 'base', 'importacao_TWh', 'p5'))} ou {f(r('central', 'base', 'importacao_TWh', 'p95'))}
TWh conforme o clima e a hidrologia. As curvas de cenários diferentes, porém, ficam claramente separadas.
{fig('mc1')}
### 8.2 O efeito dos data centers

Comparando cada sorteio consigo mesmo (diferença pareada):

{t_par}

- **Sempre positivo.** O efeito é positivo em 100% dos sorteios ({F('r16')}, esquerda).
- **Depende da eólica.** É maior com eólica baixa: menos vento noturno significa mais horas sem
  cobertura.
- **Peso do clima.** A importação anual por ano meteorológico ({F('r16')}, direita) varia muito: anos de
  pouco vento, como 2009, levam a importação central a ~11 TWh, e anos de muito vento, como 2012, a
  ~1,5 TWh.
- **Decomposição da variância.** O ano meteorológico explica {100 * eta['ano_clima']:.0f}% da variância
  da importação anual; o ano hidrológico, {100 * eta['ano_hidro']:.0f}%; e os resíduos,
  {100 * eta['residuos_e_interacao']:.0f}%.
{fig('r16')}
### 8.3 Quando a importação acontece

Em 2030, com o cenário central, a probabilidade de uma hora importar chega a {f(ihc.max(), 0)}% às
{hm}h, contra {f(ih0.loc[hm], 0)}% sem data centers. De madrugada fica em ~{f(ihc.loc[[1, 2, 3, 4]].mean(), 0)}%
e ao meio-dia é praticamente zero ({F('r18')}). É o padrão histórico da seção 4.5, ampliado: a carga
flat dos data centers "transborda" para as horas em que a geração renovável é menor que a carga.
{fig('r18')}
### 8.4 Quanto de eólica compensaria

{t_comp}

A {F('r17')} mostra a curva de importação em função da eólica adicional.
- **Retornos decrescentes.** Cada GW a mais reduz a importação cada vez menos, porque as horas de
  importação que restam são as de vento fraco.
- **Compensação em energia não basta.** Compensar a energia anual
  ({f(k('central', 'base', 'dW_energia_anual_MW') / 1000)} GW) ainda deixa ~{f(imp_en)} TWh de
  importação, contra {f(cv_ref)} TWh sem data centers (curva com 300 sorteios comuns).
- **Compensação temporal.** Igualar a importação exige ~{f(k('central', 'base', 'dW_importacao_anual_media_MW') / 1000)} GW.
- **Frota maior, razão maior.** A razão entre os dois critérios fica entre 2,2 e 2,7 e cresce com a frota.

Essa é a resposta quantitativa à regra de "separar compensação energética de compensação temporal".
{fig('r17')}
### 8.5 Excedente e limites de intercâmbio

- **Exportação.** O NE segue exportando ~{f(r('central', 'base', 'excedente_TWh'), 0)} TWh/ano no
  cenário central. Os data centers reduzem o excedente acima do limite de exportação de 21 GW de
  {f(r('sem_dc', 'base', 'excedente_acima_limite_exp_TWh'))} para
  {f(r('central', 'base', 'excedente_acima_limite_exp_TWh'))} TWh/ano.
- **Importação.** Não há limite documentado, então reportamos a exposição (horas acima de cada patamar e
  fração dos anos com pelo menos uma hora acima). Não é probabilidade de déficit.

{t_lim}

### 8.6 Sensibilidades

{t_sens}

**Leitura** ({F('mc3')}).
- **Nível absoluto.** A importação depende bastante das hipóteses de hidráulica, de nível de carga e de
  atraso dos data centers.
- **Efeito dos data centers.** O efeito pareado fica positivo e na mesma ordem em todas as hipóteses
  (+1,8 a +3,0 TWh), exceto com 12 meses de atraso, em que a carga de 2030 seria a de 2029 (813 MWmed).
{fig('mc3')}
## 9. Conclusões

1. **A carga de data centers aumenta a importação.** Com a projeção oficial vigente (2,1 GWmed), a
   necessidade de importação do NE em 2030 aumenta ~{f(p('central', 'base', 'importacao_TWh'))} TWh/ano e
   ~{f(p('central', 'base', 'horas_importacao'), 0)} horas/ano com eólica base. O aumento aparece em
   todos os climas simulados, mas não muda o caráter exportador da região.
2. **O problema é temporal, não de energia.** A importação adicional concentra-se no fim da tarde e à
   noite. A eólica compensa a energia anual com ~{f(k('central', 'base', 'dW_energia_anual_MW') / 1000)} GW,
   mas compensar a importação exige ~{f(k('central', 'base', 'dW_importacao_anual_media_MW') / 1000)} GW.
   Isso sugere que armazenamento ou flexibilidade (deslocar carga, baterias, hidráulica) seriam
   complementos naturais. O custo dessas alternativas não foi avaliado.
3. **A carga de data centers aproveitaria excedente.** {f(k('central', 'base', 'absorcao_excedente_%'), 0)}%
   da energia dos data centers cairia em horas de excedente regional. Isso reduz o excedente acima do
   limite de exportação. Transformar isso em "corte evitado" exige análise de rede, fora do escopo.
4. **O clima pesa tanto quanto a decisão.** A variabilidade entre anos é da mesma ordem que a diferença
   entre cenários. Por isso os resultados devem ser comunicados como distribuições e diferenças pareadas,
   não como um número único.

## 10. Limitações e robustez

Algumas variáveis do estudo mudam rápido ou são pouco previsíveis:

{t_lim_rob}

**Limitações de método.**
- **Rede.** Não há representação da rede: excedente regional ≠ corte, e importação ≠ déficit.
- **Despacho.** A hidráulica segue uma regra emulada, não uma otimização; a térmica é histórica; a
  hidrologia é amostrada em só 4 anos.
- **Data centers.** A carga é flat e igual à média anual; não há rampas dentro de 2030.
- **Funções de transferência.** Partem da frota atual e do ERA5, que suaviza o jato noturno. Os resíduos
  vêm de 18 meses.
- **Cenários eólicos.** São hipóteses de fase, não um cronograma.
- **Dados de 2026.** São complementares, com anomalias no balanço de jan–mai.

## 11. Reprodutibilidade e engenharia

- **Execução.** `python -m src.pipeline` refaz tudo a partir de `data/raw` em ~20 min. A reexecução
  completa reproduziu os resultados com diferença zero.
- **Ambiente.** Python 3.14.1; dependências fixadas em `requirements.lock.txt`; sementes 20261111
  (modelos) e {mcc['semente']} (Monte Carlo).
- **Testes.** 27 testes automatizados (`pytest`):
  - unidades e fuso horário;
  - agregação 30 min → hora;
  - fechamento do balanço;
  - quebra da MMGD;
  - cardinalidade das junções;
  - extração do PDE e do PLAN;
  - cenários-limite do simulador;
  - reprodutibilidade dos sorteios;
  - conservação da energia hidráulica.
- **Rastreabilidade.** Manifesto com SHA-256 de cada arquivo bruto; `docs/decisoes.md` com 37 decisões
  numeradas (técnicas e do usuário); `STATUS.md` com o estado do projeto.
- **Versionamento.** Git local com commits por etapa. Dados não são versionados, só código, configuração
  e tabelas de resultado.

## 12. Decisões tomadas com o usuário

- **Carga base.** Carga líquida de MMGD da API do ONS, com a MMGD tratada como série própria.
- **Data centers.** Caso-base sem novos data centers; cenários pela projeção oficial e pelo inventário. O
  cenário alto inclui todos os pareceres e anúncios com MW.
- **Nível de carga e MMGD de 2030.** Ambos pela 2ª RQ do PLAN 2026–2030; PDE 2035 como sensibilidade.
- **Eólica alta.** 39,4 GW, com toda a expansão indicativa do PDE alocada ao NE.
- **Hidráulica.** Despacho histórico no determinístico; regra emulada no Monte Carlo; hidráulica plana
  como sensibilidade.
- **Clima.** ERA5 de 1995–2021 incluído para o Monte Carlo.

## 13. Referências

Referências metodológicas de apoio. A existência e os metadados de cada uma foram conferidos (Crossref,
JMLR ou DOI) em 2026-11-12; o texto não reproduz o conteúdo delas:
- Hersbach, H. et al. (2020). The ERA5 global reanalysis. *Q. J. R. Meteorol. Soc.*, 146(730),
  1999–2049. doi:10.1002/qj.3803.
- Staffell, I.; Pfenninger, S. (2016). Using bias-corrected reanalysis to simulate current and future
  wind power output. *Energy*, 114, 1224–1239. doi:10.1016/j.energy.2016.08.068.
- Hong, T.; Fan, S. (2016). Probabilistic electric load forecasting: A tutorial review. *Int. J.
  Forecasting*, 32(3), 914–938. doi:10.1016/j.ijforecast.2015.11.011.
- Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of
  Statistics*, 17(3). doi:10.1214/aos/1176347265.
- Pedregosa, F. et al. (2011). Scikit-learn: Machine Learning in Python. *JMLR*, 12, 2825–2830.

**Fontes de dados.**
- ONS Dados Abertos e API de carga verificada.
- ANEEL Dados Abertos (SIGA, MMGD).
- EPE, PDE 2035.
- ONS/EPE/CCEE, notas técnicas e workshop do PLAN 2026–2030.
- IBGE/SIDRA (Censo 2022).
- Open-Meteo (ERA5).
- Portarias SNTEP/MME e imprensa setorial, citadas por projeto em `config/data_centers_ne.csv`.
"""
    (REPORTS / "relatorio_tecnico.md").write_text(txt, encoding="utf-8")
    faltando = [arq for _, arq, _ in FIGURAS if not (REPORTS / "figures" / arq).exists()]
    assert not faltando, faltando
    print("reports/relatorio_tecnico.md", f"({len(FIGURAS)} figuras)")


if __name__ == "__main__":
    main()
