"""Trechos do relatório técnico sobre o perfil horário da regra hidráulica, o backtest de 2026 e o
diagnóstico da subestimação da importação.

Lê as tabelas de src.sim.backtest_2026 e src.sim.diagnostico_importacao; nenhum número é digitado.
"""
from __future__ import annotations

import json

import pandas as pd

from src.paths import REPORTS
from src.report.final import f, sg, tab

SIM, MC = REPORTS / "sim", REPORTS / "mc"
REGRA_ANT = "simulado com resíduos, regra com beta anterior"     # método anterior
REGRA_ADOT = "simulado com resíduos, regra com beta do ano"     # método atual (decisões 52 e 57)


def dados() -> dict:
    d = {k: pd.read_csv(SIM / f"{k}.csv") for k in
         ["backtest_2026", "backtest_2026_componentes", "backtest_2026_mensal", "diag_beta_hidro", "diag_backcast_beta",
          "diag_substituicao", "diag_2030_beta", "diag_perfil_hidro"]}
    d["info"] = json.loads((SIM / "backtest_2026_config.json").read_text(encoding="utf-8"))
    d["bk"] = pd.read_csv(MC / "mc_backcast.csv")
    d["mcc"] = json.loads((MC / "mc_config.json").read_text(encoding="utf-8"))
    return d


def numeros(d: dict | None = None) -> dict:
    """Números usados também no sumário e nas limitações."""
    d = d or dados()
    tb = d["backtest_2026"].set_index("metrica")
    sb = d["diag_substituicao"].set_index("ano")
    e30 = d["diag_2030_beta"].set_index(["beta", "cenario_eolico"])
    c34, c52, c57 = list(dict.fromkeys(e30.index.get_level_values(0)))      # por ano/realizada, por ano/potencial, 2026
    erro = lambda col: 100 * (sb[col] / sb.observado_TWh - 1)
    rec = [a for a in sb.index if a >= 2024]
    tb_beta = d["diag_beta_hidro"].set_index("ano")
    corr = tb_beta.loc[[a for a in tb_beta.index if a <= 2025], "corr_potencial"]
    efe_eol = sb["forma eólica observada (beta do ano)"] - sb["simulado, regra com beta do ano"]
    p5_dif = sb.eolica_p5_simulada_com_residuos_MW - sb.eolica_p5_observada_MW
    return {
        "corr_min": corr.min(), "corr_max": corr.max(),
        # P5 horário da eólica simulada (com resíduos) menos o observado: compara distribuições, sem condicionar
        # às horas de pouco vento observado
        "p5_min": p5_dif.min(), "p5_max": p5_dif.max(), "p5_exc_rec_min": p5_dif[rec].min(), "p5_exc_rec_max": p5_dif[rec].max(),
        "efe_eol_min": efe_eol.min(), "efe_eol_max": efe_eol.max(),
        # a importação potencial é o conceito do simulador (decisão 54); a realizada difere pouco em 2026
        "obs": tb.loc["importacao_TWh", "observado_potencial"], "A_pct": tb.loc["importacao_TWh", "A_percentil_do_observado_potencial"],
        "A_p5": tb.loc["importacao_TWh", "A_p5"], "A_p95": tb.loc["importacao_TWh", "A_p95"],
        "B_cen": tb.loc["importacao_TWh", "B_regra_media"], "B_ant": tb.loc["importacao_TWh", "B_regra_beta_anterior_media"],
        "B_hid": tb.loc["importacao_TWh", "B_despacho_obs_media"],
        "erro_min": erro(REGRA_ADOT).min(), "erro_max": erro(REGRA_ADOT).max(), "erro_por_ano": erro(REGRA_ADOT).to_dict(),
        "erro_rec_min": erro(REGRA_ADOT)[rec].min(), "erro_rec_max": erro(REGRA_ADOT)[rec].max(),
        "erro_rec_ant_min": erro(REGRA_ANT)[rec].min(), "erro_rec_ant_max": erro(REGRA_ANT)[rec].max(),
        "anos_rec": rec,
        "imp30_real": e30.loc[(c34, "base"), "central_media_TWh"], "imp30_ano": e30.loc[(c52, "base"), "central_media_TWh"],
        "imp30": e30.loc[(c57, "base"), "central_media_TWh"], "dc30_real": e30.loc[(c34, "base"), "efeito_DC_TWh"],
        "dc30_ano": e30.loc[(c52, "base"), "efeito_DC_TWh"], "dc30": e30.loc[(c57, "base"), "efeito_DC_TWh"],
        "beta26": tb_beta.loc[2026, "beta_potencial"], "dp26": tb_beta.loc[2026, "dp_intradiario_carga_liq_potencial_MW"],
        "beta_min": tb_beta.beta_potencial[[2022, 2023, 2024, 2025]].min(), "beta_max": tb_beta.beta_potencial[[2022, 2023, 2024, 2025]].max(),
    }


def perfil(F) -> str:
    """Parágrafo da seção 7.2 sobre o perfil horário da hidráulica emulada (Figura r15b)."""
    p = dados()["diag_perfil_hidro"].astype({"conjunto": str})
    v = lambda conj, meses, serie, horas: p[(p.conjunto == conj) & (p.meses == meses) & (p.serie == serie) & p.hora.isin(horas)].MW.mean() / 1000
    noite, tarde, dia = range(0, 6), range(18, 22), range(8, 15)
    return f"""
**Perfil horário da hidráulica emulada.** A {F('r15b')} mostra a média por hora do dia: à esquerda, os
sorteios de 2030; à direita, a regra aplicada às parcelas observadas de 2026, o que isola o efeito da regra.
- A regra conserva a energia de cada dia, mas a distribui como a carga líquida **potencial**, que é alta a
  noite inteira e baixa ao meio-dia. Em 2030 (jan–abr), a hidráulica emulada fica em
  {f(v('2030', 'jan–abr', 'pot', noite))} GW de 0 h a 5 h, contra {f(v('2030', 'jan–abr', 'obs', noite))} GW no
  despacho observado dos anos hidrológicos, e em {f(v('2030', 'jan–abr', 'pot', dia))} GW de 8 h a 14 h,
  contra {f(v('2030', 'jan–abr', 'obs', dia))} GW. Com o coeficiente do próprio ano hidrológico (versão
  anterior), seriam {f(v('2030', 'jan–abr', 'ano', noite))} e {f(v('2030', 'jan–abr', 'ano', dia))} GW: a resposta
  ficava ainda mais exagerada.
- O despacho real concentra a hidráulica no início da noite. Em 2026 (jan–abr), de 18 h a 21 h, a hidráulica
  observada foi de {f(v('2026', 'jan–abr', 'obs', tarde))} GW; a regra entrega
  {f(v('2026', 'jan–abr', 'pot', tarde))} GW com o coeficiente adotado e
  {f(v('2026', 'jan–abr', 'real', tarde))} GW com o estimado sobre a carga já cortada (seção 7.5).
- A regra é uma resposta linear, sem otimização; a forma do despacho real reflete também decisões do SIN
  e restrições que o simulador não tem.
"""


def secao(F, fig) -> str:
    """Seção 7.5: backtest de 2026 e diagnóstico."""
    d = dados()
    tb, info, tc = d["backtest_2026"].set_index("metrica"), d["info"], d["backtest_2026_componentes"]
    nb = numeros(d)
    e = info["erro_horario_B"]

    # ---- tabela do backtest
    linhas = [("importacao_TWh", "Importação (TWh)", 2), ("horas_importacao", "Horas com importação", 0),
              ("importacao_p95_MW", "P95 da importação horária (MW)", 0), ("importacao_pico_MW", "Pico de importação (MW)", 0),
              ("excedente_TWh", "Excedente (TWh)", 1)]
    t_bt = pd.DataFrame([{
        "Métrica (jan–out, horas válidas)": rot,
        "Observado: intercâmbio": f(tb.loc[k, "observado_realizado"], nd),
        "Observado: potencial (+ cortes)": f(tb.loc[k, "observado_potencial"], nd),
        "A: mediana [P5–P95]": f"{f(tb.loc[k, 'A_p50'], nd)} [{f(tb.loc[k, 'A_p5'], nd)}–{f(tb.loc[k, 'A_p95'], nd)}]",
        "B: regra (caso central)": f(tb.loc[k, "B_regra_media"], nd),
        "B: regra, beta sobre carga já cortada": f(tb.loc[k, "B_regra_beta_anterior_media"], nd),
        "B: despacho hidráulico observado": f(tb.loc[k, "B_despacho_obs_media"], nd)} for k, rot, nd in linhas])

    t_comp = pd.DataFrame([{"Parcela": r.parcela,
                            "Observado (MWmed)": "—" if pd.isna(r.observado_MWmed) else f(r.observado_MWmed, 0),
                            "Simulado B (MWmed)": "—" if pd.isna(r.simulado_B_MWmed) else f(r.simulado_B_MWmed, 0),
                            "Efeito em M (MWmed)": sg(r.efeito_em_M_MWmed, 0)} for r in tc.itertuples()])
    vies = tc.efeito_em_M_MWmed.iat[-1]

    # ---- beta
    Tb = d["diag_beta_hidro"]
    t_beta = pd.DataFrame([{"Ano": int(r.ano), "Corte eólico (%)": f(r._6, 1), "Beta sobre carga líquida realizada": f(r.beta_realizada, 2),
                            "Beta sobre carga líquida potencial": f(r.beta_potencial, 2),
                            "Desvio intradiário, realizada (MW)": f(r.dp_intradiario_carga_liq_realizada_MW, 0),
                            "Desvio intradiário, potencial (MW)": f(r.dp_intradiario_carga_liq_potencial_MW, 0)} for r in Tb.itertuples()])
    BK = d["diag_backcast_beta"]
    nomes = list(BK.beta.unique())
    piv = BK.pivot(index="ano", columns="beta", values=["obs_TWh", "sim_TWh", "erro_%"])
    t_bk = pd.DataFrame([{"Ano": int(a), "Observado (TWh)": f(piv.loc[a, ("obs_TWh", nomes[0])], 2),
                          "Beta sobre carga realizada (erro)": f"{f(piv.loc[a, ('sim_TWh', nomes[0])], 2)} ({sg(piv.loc[a, ('erro_%', nomes[0])])}%)",
                          "Beta sobre carga potencial, do ano (erro)": f"{f(piv.loc[a, ('sim_TWh', nomes[1])], 2)} ({sg(piv.loc[a, ('erro_%', nomes[1])])}%)"}
                         for a in piv.index])

    # ---- substituição
    SB = d["diag_substituicao"].set_index("ano")
    casos = [(REGRA_ADOT, "Método atual (formas simuladas + resíduos, beta do ano)"),
             (REGRA_ANT, "Mesmas formas e resíduos, beta sobre carga realizada"),
             ("simulado, regra com beta do ano", "Formas simuladas sem resíduos, beta do ano"),
             ("forma eólica observada (beta do ano)", "… só a forma eólica observada"),
             ("forma da carga observada (beta do ano)", "… só a forma da carga observada"),
             ("formas solar e MMGD observadas (beta do ano)", "… só as formas solar e MMGD observadas"),
             ("todas as formas observadas, regra com beta anterior", "Todas as formas observadas, beta sobre carga realizada"),
             ("todas as formas observadas, regra com beta do ano", "Todas as formas observadas, beta do ano"),
             ("simulado, despacho hidráulico observado", "Formas simuladas sem resíduos, despacho hidráulico observado")]
    anos = list(SB.index)
    cel = lambda col, a: f"{f(SB.loc[a, col], 2)} ({sg(100 * (SB.loc[a, col] / SB.loc[a, 'observado_TWh'] - 1))}%)"
    rows = [{"Importação (TWh, erro)": "Observado (geração potencial)", **{str(a): f(SB.loc[a, "observado_TWh"], 2) for a in anos}}]
    rows += [{"Importação (TWh, erro)": rot, **{str(a): cel(col, a) for a in anos}} for col, rot in casos]
    rows += [{"Importação (TWh, erro)": "Erro da eólica simulada no quintil de menos vento (MW)",
              **{str(a): sg(SB.loc[a, "erro_eolica_quintil_inferior_MW"], 0) for a in anos}},
             {"Importação (TWh, erro)": "P5 horário da eólica: observado / simulado com resíduos (MW)",
              **{str(a): f"{f(SB.loc[a, 'eolica_p5_observada_MW'], 0)} / {f(SB.loc[a, 'eolica_p5_simulada_com_residuos_MW'], 0)}" for a in anos}}]
    t_sb = pd.DataFrame(rows)
    rec = nb["anos_rec"]
    tod = lambda col, aa: [100 * (SB.loc[a, col] / SB.loc[a, "observado_TWh"] - 1) for a in aa]
    dif = lambda col: [SB.loc[a, col] - SB.loc[a, "simulado, regra com beta do ano"] for a in anos]
    p5d = lambda a: SB.loc[a, "eolica_p5_simulada_com_residuos_MW"] - SB.loc[a, "eolica_p5_observada_MW"]

    # ---- 2030
    E = d["diag_2030_beta"]
    val = lambda b, w, col: f(E[(E.beta == b) & (E.cenario_eolico == w)][col].iat[0], 2)
    t_30 = pd.DataFrame([{"Coeficiente da regra": b, "Eólica": w, "Importação, DC central (TWh)": val(b, w, "central_media_TWh"),
                          "Importação, sem DC (TWh)": val(b, w, "sem_dc_media_TWh"), "Efeito dos DC (TWh)": val(b, w, "efeito_DC_TWh")}
                         for b in E.beta.unique() for w in ["baixa", "base", "alta"]])
    bk25 = d["bk"].set_index("ano").loc[2025].iloc[0]
    dp30 = d["mcc"]["dp_intradiario_carga_liquida_MW"]["2030_simulado"]

    return f"""
### 7.5 Backtest de 2026 e diagnóstico da subestimação

**Teste.** O simulador recebe os níveis de cenário de 2026 (anexo; DC central, porque a carga do PLAN de
2026 inclui os data centers da 2ª RQ) e é comparado ao balanço observado de janeiro a outubro, só nas
{f(info['horas_validas'], 0)} das {f(info['horas_periodo'], 0)} horas em que o balanço do ONS fecha (decisão 16).
O observado "potencial" soma ao intercâmbio os cortes eólicos e solares, que é o conceito do simulador.
- **(A) clima e hidrologia sorteados.** Os {f(info['n_sorteios_A'], 0)} sorteios do Monte Carlo de 2026 (clima
  1995–2025, hidrologia 2022–2025): o ano observado cai dentro da faixa? Não é uma previsão ex-ante: as
  funções de transferência, os resíduos e o coeficiente da regra usam dados até out/2026, e os níveis vêm de
  documentos de jul/2026 (PLAN) e nov/2026 (SIGA).
- **(B) clima e hidrologia conhecidos.** As funções de transferência são re-treinadas só com dados até
  2025-12-31 (fora da amostra) e aplicadas ao ERA5 de 2026, com resíduos só de 2024–2025. A térmica é a
  observada e a hidráulica segue a energia diária observada de 2026, pela regra emulada (coeficiente de 2026
  e, para comparação, o estimado sobre a carga já cortada) ou pelo despacho real. Os níveis continuam sendo
  os do cenário.

{tab(t_bt)}

- **A contém o ano observado.** A importação potencial de {f(nb['obs'], 2)} TWh fica no percentil
  {f(nb['A_pct'], 0)} da distribuição de A (P5–P95 {f(nb['A_p5'], 2)}–{f(nb['A_p95'], 2)} TWh).
- **B subestima.** Com o clima e a hidrologia de 2026, o simulador dá {f(nb['B_cen'], 2)} TWh com a regra
  do caso central ({sg(100 * (nb['B_cen'] / nb['obs'] - 1))}%). A forma horária de M é boa: correlação
  {f(e['corr'], 2)} e sinal certo em {f(e['acerto_sinal_%'], 0)}% das horas. Os extremos ficam curtos: o P95 da
  importação horária simulada é {f(100 * tb.loc['importacao_p95_MW', 'B_regra_media'] / tb.loc['importacao_p95_MW', 'observado_potencial'], 0)}%
  do observado.
- **Não é o nível médio.** O M médio de B fica {f(abs(vies), 0)} MW abaixo do observado, o que aumentaria
  a importação. A decomposição abaixo fecha esse viés; a parcela "carga: balanço × API" é a diferença entre
  os dois conceitos de carga (decisão 41). Esse viés de nível encobre parte do erro de forma: com os níveis
  observados, o erro de 2026 é maior (teste 2, abaixo).

{tab(t_comp)}
{fig('b26')}
**Esperado ou erro de metodologia?** Três testes (`src/sim/diagnostico_importacao.py`) separam as causas.

**1. Coeficiente da regra hidráulica: dois erros de método, corrigidos (decisões 52 e 57).**
- **Primeiro problema (decisão 52).** O coeficiente beta era estimado sobre a carga líquida **realizada**, com a eólica e a
  solar já cortadas. A regra, porém, é aplicada à carga líquida **potencial** do simulador, que não tem
  corte. Com corte alto, a carga líquida potencial oscila muito mais dentro do dia. Multiplicar essa
  oscilação maior por um beta medido na oscilação menor exagera a resposta: a hidráulica vai demais para
  as horas de carga líquida alta, e a importação cai.
  Desde 2026-11-17 o beta é estimado sobre a carga líquida potencial. Ele fica próximo do anterior em 2022 e
  bem menor a partir de 2024:

{tab(t_beta)}

- **Segundo problema (decisão 57).** O beta cai quando a carga líquida oscila mais dentro do dia, porque a
  hidráulica tem amplitude limitada: cai de 2022 a 2025 (tabela) e, em todos os anos, dos dias de menor para os
  de maior oscilação (em 2026, de {f(Tb.beta_dias_menor_oscilacao.iat[-1], 2)} para
  {f(Tb.beta_dias_maior_oscilacao.iat[-1], 2)}). Em 2026 o beta médio é maior que em 2025 apesar da oscilação maior:
  a hidrologia também pesa. Em 2030 a carga líquida simulada oscila {f(dp30, 0)} MW, e o
  simulador ainda aplicava o beta de cada ano hidrológico ({f(nb['beta_min'], 2)}–{f(nb['beta_max'], 2)}), medido
  em regimes de oscilação bem menor. Desde 2026-11-25 o caso central usa o de 2026 ({f(nb['beta26'], 2)}), o ano
  observado com a oscilação mais próxima ({f(nb['dp26'], 0)} MW). Na validação retrospectiva cada ano continua
  com o próprio beta, que é o do regime em que ele ocorreu.

- **Validação retrospectiva com o beta de cada ano** (mesmos sorteios da seção 7.4):

{tab(t_bk)}

- **Efeito no backtest de 2026.** B passa de {f(nb['B_ant'], 2)} TWh (beta sobre a carga já cortada) para
  {f(nb['B_cen'], 2)} TWh (despacho observado: {f(nb['B_hid'], 2)} TWh).
- **Com as formas observadas, a regra corrigida acerta.** Aplicada às parcelas observadas, a regra com o
  beta do ano erra a importação em {f(min(tod('todas as formas observadas, regra com beta do ano', rec)), 0)}% a
  {sg(max(tod('todas as formas observadas, regra com beta do ano', rec)), 0)}% em {rec[0]}–{rec[-1]}. Com o beta
  sobre a carga realizada, errava {f(min(tod('todas as formas observadas, regra com beta anterior', rec)), 0)}% a
  {sg(max(tod('todas as formas observadas, regra com beta anterior', rec)), 0)}%.

**2. Formas horárias: onde está o erro que sobra.**
Com os **níveis observados** de cada ano, a forma simulada de cada parcela é trocada pela observada. As
funções de transferência foram re-treinadas sem o próprio ano, e os resíduos sorteados não incluem os dele.
É, portanto, o erro **fora da amostra** do método. A importação observada é a potencial (intercâmbio mais
cortes), com a eólica do balanço do ONS mais o corte apurado (decisão 54).

{tab(t_sb)}

- **Resultado.** Com o método atual (beta do ano e resíduos), o erro da importação vai de
  {sg(min(tod(REGRA_ADOT, anos)), 0)}% a {sg(max(tod(REGRA_ADOT, anos)), 0)}%, sempre de subestimação, e cresce nos anos mais recentes ({sg(tod(REGRA_ADOT, [2025])[0], 0)}% em 2025, {sg(tod(REGRA_ADOT, [2026])[0], 0)}% em 2026).
- **Os resíduos importam.** Sem eles o erro seria de {sg(min(tod('simulado, regra com beta do ano', anos)), 0)}% a
  {sg(max(tod('simulado, regra com beta do ano', anos)), 0)}%: as funções de transferência preveem médias condicionais,
  mais lisas que a realidade.
- **Nenhuma parcela explica sozinha o que sobra.** Trocando uma forma simulada pela observada, sem resíduos, a
  importação muda:
  - eólica: {sg(min(dif('forma eólica observada (beta do ano)')), 2)} a {sg(max(dif('forma eólica observada (beta do ano)')), 2)} TWh, maior em 2026;
  - carga: {sg(min(dif('forma da carga observada (beta do ano)')), 2)} a {sg(max(dif('forma da carga observada (beta do ano)')), 2)} TWh, com sinal variável;
  - solar e MMGD: {sg(min(dif('formas solar e MMGD observadas (beta do ano)')), 2)} a {sg(max(dif('formas solar e MMGD observadas (beta do ano)')), 2)} TWh.
  O que sobra é também a coincidência entre calmaria, carga alta e fim do sol, que resíduos sorteados por época
  do ano só reproduzem em parte.
- **Cauda de pouco vento: a limitação da decisão 53 não se confirma.** O P5 horário da eólica simulada, com
  resíduos, fica entre {sg(min(p5d(a) for a in anos), 0)} e {sg(max(p5d(a) for a in anos), 0)} MW do observado
  ({sg(min(p5d(a) for a in rec), 0)} a {sg(max(p5d(a) for a in rec), 0)} MW em {rec[0]}–{rec[-1]}). A versão anterior
  apontava 314–473 MW a mais em 2024–2026. O que mudou:
  - a eólica "observada" era a das usinas com FC multiplicada por um fator anual, o que a subestimava em
    137–262 MW no P5, porque as usinas sem FC geram relativamente mais nas calmarias (decisão 54);
  - o modelo B0 passou a usar o vento de cada um dos 16 polos, em vez de uma média espacial (decisão 55);
  - os resíduos cobrem mais um ano e são recentrados por mês (decisão 56).
  Nas horas de menos vento observado (quintil inferior) a eólica simulada sem resíduos ainda fica
  {sg(SB.erro_eolica_quintil_inferior_MW.min(), 0)} a {sg(SB.erro_eolica_quintil_inferior_MW.max(), 0)} MW acima, o que é esperado de
  qualquer modelo de média quando se escolhem as horas pelo valor observado.

**3. O que é esperado.**
- Um único ano não testa a distribuição: o observado de 2026 está no percentil {f(nb['A_pct'], 0)} de A.
- Cortes em horas de importação pesam pouco. Em 2025 foram {f(bk25.corte_eol_em_horas_de_importacao_TWh, 2)} TWh, mas
  gerá-los reduziria a importação em só {f(bk25.importacao_evitada_se_gerado_TWh, 2)} TWh, porque o corte quase sempre
  excede a importação da hora.
- A diferença entre os conceitos de carga (API × balanço) muda o nível de M, mas no sentido de aumentar a
  importação simulada.
- O momento exato das calmarias de um ano não é previsível pelo ERA5 com uma função de transferência média.

**Conclusão.**
- **Erros de método, corrigidos.** Coeficiente da regra (decisões 52 e 57), importação observada inflada
  (decisão 54), features (decisão 55) e resíduos (decisão 56). Com as formas observadas, a regra reproduz a
  importação de 2024–2026 com erro de {sg(min(tod('todas as formas observadas, regra com beta do ano', rec)), 0)}% a
  {sg(max(tod('todas as formas observadas, regra com beta do ano', rec)), 0)}%.
- **O que resta.** O método ainda subestima a importação dos anos recentes fora da amostra. O nível de 2030
  tende a estar subestimado, menos do que se supunha antes da revisão.
- **Consequência para 2030** (tabela; mesmos sorteios, DC central, eólica base). A importação média é de
  {f(nb['imp30'], 2)} TWh com o beta de 2026, contra {f(nb['imp30_ano'], 2)} com o de cada ano hidrológico. O efeito
  dos data centers muda menos: {f(nb['dc30'], 2)} contra {f(nb['dc30_ano'], 2)} TWh.

{tab(t_30)}
{fig('r27')}"""
