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
REGRA_ADOT = "simulado com resíduos, regra com beta adotado"     # método atual (decisão 52)


def dados() -> dict:
    d = {k: pd.read_csv(SIM / f"{k}.csv") for k in
         ["backtest_2026", "backtest_2026_componentes", "backtest_2026_mensal", "diag_beta_hidro", "diag_backcast_beta",
          "diag_substituicao", "diag_2030_beta", "diag_perfil_hidro"]}
    d["info"] = json.loads((SIM / "backtest_2026_config.json").read_text(encoding="utf-8"))
    d["bk"] = pd.read_csv(MC / "mc_backcast.csv")
    return d


def numeros(d: dict | None = None) -> dict:
    """Números usados também no sumário e nas limitações."""
    d = d or dados()
    tb = d["backtest_2026"].set_index("metrica")
    sb = d["diag_substituicao"].set_index("ano")
    e30 = d["diag_2030_beta"].set_index(["beta", "cenario_eolico"])
    ant_, adot = [i for i in e30.index.get_level_values(0).unique()]
    erro = lambda col: 100 * (sb[col] / sb.observado_TWh - 1)
    rec = [a for a in sb.index if a >= 2024]
    return {
        "obs": tb.loc["importacao_TWh", "observado_realizado"], "A_pct": tb.loc["importacao_TWh", "A_percentil_do_observado_realizado"],
        "A_p5": tb.loc["importacao_TWh", "A_p5"], "A_p95": tb.loc["importacao_TWh", "A_p95"],
        "B_cen": tb.loc["importacao_TWh", "B_regra_media"], "B_ant": tb.loc["importacao_TWh", "B_regra_beta_anterior_media"],
        "B_hid": tb.loc["importacao_TWh", "B_despacho_obs_media"],
        "erro_rec_min": erro(REGRA_ADOT)[rec].min(), "erro_rec_max": erro(REGRA_ADOT)[rec].max(),
        "erro_rec_ant_min": erro(REGRA_ANT)[rec].min(), "erro_rec_ant_max": erro(REGRA_ANT)[rec].max(),
        "anos_rec": rec,
        "imp30_ant": e30.loc[(ant_, "base"), "central_media_TWh"], "imp30": e30.loc[(adot, "base"), "central_media_TWh"],
        "dc30_ant": e30.loc[(ant_, "base"), "efeito_DC_TWh"], "dc30": e30.loc[(adot, "base"), "efeito_DC_TWh"],
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
  contra {f(v('2030', 'jan–abr', 'obs', dia))} GW.
- O despacho real concentra a hidráulica no início da noite. Em 2026 (jan–abr), de 18 h a 21 h, a hidráulica
  observada foi de {f(v('2026', 'jan–abr', 'obs', tarde))} GW; a regra entrega
  {f(v('2026', 'jan–abr', 'pot', tarde))} GW com o coeficiente adotado e
  {f(v('2026', 'jan–abr', 'real', tarde))} GW com o anterior (seção 7.5).
- O coeficiente adotado (decisão 52) responde menos que o anterior nos anos de corte alto.
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
        "B: regra, beta anterior": f(tb.loc[k, "B_regra_beta_anterior_media"], nd),
        "B: despacho hidráulico observado": f(tb.loc[k, "B_despacho_obs_media"], nd)} for k, rot, nd in linhas])

    t_comp = pd.DataFrame([{"Parcela": r.parcela,
                            "Observado (MWmed)": "—" if pd.isna(r.observado_MWmed) else f(r.observado_MWmed, 0),
                            "Simulado B (MWmed)": "—" if pd.isna(r.simulado_B_MWmed) else f(r.simulado_B_MWmed, 0),
                            "Efeito em M (MWmed)": sg(r.efeito_em_M_MWmed, 0)} for r in tc.itertuples()])
    vies = tc.efeito_em_M_MWmed.iat[-1]

    # ---- beta
    Tb = d["diag_beta_hidro"]
    t_beta = pd.DataFrame([{"Ano": int(r.ano), "Corte eólico (%)": f(r._6, 1), "Beta anterior (carga líquida realizada)": f(r.beta_realizada, 2),
                            "Beta adotado (carga líquida potencial)": f(r.beta_potencial, 2),
                            "Desvio intradiário, realizada (MW)": f(r.dp_intradiario_carga_liq_realizada_MW, 0),
                            "Desvio intradiário, potencial (MW)": f(r.dp_intradiario_carga_liq_potencial_MW, 0)} for r in Tb.itertuples()])
    BK = d["diag_backcast_beta"]
    nomes = list(BK.beta.unique())
    piv = BK.pivot(index="ano", columns="beta", values=["obs_TWh", "sim_TWh", "erro_%"])
    t_bk = pd.DataFrame([{"Ano": int(a), "Observado (TWh)": f(piv.loc[a, ("obs_TWh", nomes[0])], 2),
                          "Beta anterior (erro)": f"{f(piv.loc[a, ('sim_TWh', nomes[0])], 2)} ({sg(piv.loc[a, ('erro_%', nomes[0])])}%)",
                          "Beta adotado (erro)": f"{f(piv.loc[a, ('sim_TWh', nomes[1])], 2)} ({sg(piv.loc[a, ('erro_%', nomes[1])])}%)"}
                         for a in piv.index])

    # ---- substituição
    SB = d["diag_substituicao"].set_index("ano")
    casos = [(REGRA_ADOT, "Método atual (formas simuladas + resíduos, beta adotado)"),
             (REGRA_ANT, "Método anterior (formas simuladas + resíduos, beta anterior)"),
             ("simulado, regra com beta adotado", "Formas simuladas sem resíduos, beta adotado"),
             ("forma eólica observada (beta adotado)", "… só a forma eólica observada"),
             ("forma da carga observada (beta adotado)", "… só a forma da carga observada"),
             ("formas solar e MMGD observadas (beta adotado)", "… só as formas solar e MMGD observadas"),
             ("todas as formas observadas, regra com beta anterior", "Todas as formas observadas, beta anterior"),
             ("todas as formas observadas, regra com beta adotado", "Todas as formas observadas, beta adotado"),
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
    efe = lambda a: SB.loc[a, "forma eólica observada (beta adotado)"] - SB.loc[a, "simulado, regra com beta adotado"]
    res = lambda a: SB.loc[a, REGRA_ADOT] - SB.loc[a, "simulado, regra com beta adotado"]
    rec = nb["anos_rec"]
    ant = [a for a in anos if a not in rec]
    tod = lambda col, aa: [100 * (SB.loc[a, col] / SB.loc[a, "observado_TWh"] - 1) for a in aa]
    lista = lambda aa: ", ".join(str(a) for a in aa[:-1]) + " e " + str(aa[-1]) if len(aa) > 1 else str(aa[0])
    sm = lambda a: SB.loc[a, "formas solar e MMGD observadas (beta adotado)"] - SB.loc[a, "simulado, regra com beta adotado"]

    # ---- 2030
    E = d["diag_2030_beta"]
    ant_, adot = list(E.beta.unique())
    t_30 = pd.DataFrame([{"Cenário eólico": w,
                          "Importação, DC central: beta anterior (TWh)": f(E[(E.beta == ant_) & (E.cenario_eolico == w)].central_media_TWh.iat[0], 2),
                          "Importação, DC central: beta adotado (TWh)": f(E[(E.beta == adot) & (E.cenario_eolico == w)].central_media_TWh.iat[0], 2),
                          "Efeito dos DC: beta anterior (TWh)": f(E[(E.beta == ant_) & (E.cenario_eolico == w)].efeito_DC_TWh.iat[0], 2),
                          "Efeito dos DC: beta adotado (TWh)": f(E[(E.beta == adot) & (E.cenario_eolico == w)].efeito_DC_TWh.iat[0], 2)}
                         for w in ["baixa", "base", "alta"]])
    corte25 = d["bk"].set_index("ano").loc[2025, "corte_eol_em_horas_de_importacao_TWh"].iat[0]

    return f"""
### 7.5 Backtest de 2026 e diagnóstico da subestimação

**Teste.** O simulador recebe os níveis de cenário de 2026 (anexo; DC central, porque a carga do PLAN de
2026 inclui os data centers da 2ª RQ) e é comparado ao balanço observado de janeiro a outubro, só nas
{f(info['horas_validas'], 0)} das {f(info['horas_periodo'], 0)} horas em que o balanço do ONS fecha (decisão 16).
O observado "potencial" soma ao intercâmbio os cortes eólicos e solares, que é o conceito do simulador.
- **(A) ex-ante.** Os {f(info['n_sorteios_A'], 0)} sorteios do Monte Carlo de 2026 (clima 1995–2025,
  hidrologia 2022–2025): o ano observado cai dentro da faixa?
- **(B) clima e hidrologia conhecidos.** As funções de transferência são re-treinadas só com dados até
  2025-12-31 (fora da amostra) e aplicadas ao ERA5 de 2026. A térmica é a observada e a hidráulica segue a
  energia diária observada de 2026, pela regra emulada (coeficiente adotado e, para comparação, o anterior)
  ou pelo despacho real. Os níveis continuam sendo os do cenário.

{tab(t_bt)}

- **A contém o ano observado.** A importação de {f(nb['obs'], 2)} TWh fica no percentil
  {f(nb['A_pct'], 0)} da distribuição ex-ante (P5–P95 {f(nb['A_p5'], 2)}–{f(nb['A_p95'], 2)} TWh).
- **B subestima.** Com o clima e a hidrologia de 2026, o simulador dá {f(nb['B_cen'], 2)} TWh com a regra
  do caso central ({sg(100 * (nb['B_cen'] / nb['obs'] - 1))}%). A forma horária de M é boa: correlação
  {f(e['corr'], 2)} e sinal certo em {f(e['acerto_sinal_%'], 0)}% das horas. Os extremos ficam curtos: o P95 da
  importação horária simulada é {f(100 * tb.loc['importacao_p95_MW', 'B_regra_media'] / tb.loc['importacao_p95_MW', 'observado_potencial'], 0)}%
  do observado.
- **Não é o nível médio.** O M médio de B fica {f(abs(vies), 0)} MW abaixo do observado, o que aumentaria
  a importação. A decomposição abaixo fecha esse viés; a parcela "carga: balanço × API" é a diferença entre
  os dois conceitos de carga (decisão 41).

{tab(t_comp)}
{fig('b26')}
**Esperado ou erro de metodologia?** Três testes (`src/sim/diagnostico_importacao.py`) separam as causas.

**1. Inconsistência no coeficiente da regra hidráulica: erro de método, corrigido (decisão 52).**
- **O problema.** O coeficiente beta era estimado sobre a carga líquida **realizada**, com a eólica e a
  solar já cortadas. A regra, porém, é aplicada à carga líquida **potencial** do simulador, que não tem
  corte. Com corte alto, a carga líquida potencial oscila muito mais dentro do dia. Multiplicar essa
  oscilação maior por um beta medido na oscilação menor exagera a resposta: a hidráulica vai demais para
  as horas de carga líquida alta, e a importação cai.
- **A correção.** Desde 2026-11-17 o caso central usa o beta estimado sobre a grandeza a que é aplicado,
  a carga líquida potencial (adotado). Ele fica próximo do anterior em 2022 e bem menor a partir de 2024:

{tab(t_beta)}

- **Validação retrospectiva com os dois coeficientes** (mesmos sorteios da seção 7.4):

{tab(t_bk)}

- **Efeito no backtest de 2026.** B passa de {f(nb['B_ant'], 2)} TWh (beta anterior) para {f(nb['B_cen'], 2)} TWh
  (despacho observado: {f(nb['B_hid'], 2)} TWh).
- **Com as formas observadas, a regra corrigida acerta.** Aplicada às parcelas observadas, a regra com o
  beta adotado erra a importação em {f(min(tod('todas as formas observadas, regra com beta adotado', rec)), 0)}% a
  {sg(max(tod('todas as formas observadas, regra com beta adotado', rec)), 0)}% em {rec[0]}–{rec[-1]}. Com o beta
  anterior, errava {f(min(tod('todas as formas observadas, regra com beta anterior', rec)), 0)}% a
  {sg(max(tod('todas as formas observadas, regra com beta anterior', rec)), 0)}%.

**2. Formas horárias: a eólica simulada tem poucas horas de pouco vento. É sistemático nos anos recentes.**
Com os **níveis observados** de cada ano, a forma simulada de cada parcela é trocada pela observada.
As funções de transferência foram re-treinadas sem o próprio ano. A tabela mostra a importação e o erro.

{tab(t_sb)}

- **A eólica é a parcela que mais pesa.** Trocar só a forma eólica pela observada aumenta a importação em
  {f(min(efe(a) for a in rec), 2)} a {f(max(efe(a) for a in rec), 2)} TWh em {rec[0]}–{rec[-1]}; em {ant[0]} o efeito é
  {sg(efe(ant[0]), 2)} TWh. A forma da carga muda de sinal entre os anos (acaso). As formas solar e MMGD somam
  {sg(min(sm(a) for a in anos), 2)} a {sg(max(sm(a) for a in anos), 2)} TWh.
- **O erro cresce ano a ano.** Nas horas de menos vento, a eólica simulada superestima a observada em
  {sg(SB.loc[anos[0], 'erro_eolica_quintil_inferior_MW'], 0)} MW em {anos[0]} e
  {sg(SB.loc[anos[-1], 'erro_eolica_quintil_inferior_MW'], 0)} MW em {anos[-1]}.
- **Os resíduos não corrigem a cauda.** Eles foram desenhados para repor essa variabilidade.
  - Em {lista(ant)}, repõem: +{f(min(res(a) for a in ant), 2)} a +{f(max(res(a) for a in ant), 2)} TWh,
    e o P5 da eólica simulada chega ao observado ou fica abaixo dele.
  - Em {rec[0]}–{rec[-1]}, quase nada: {sg(min(res(a) for a in rec), 2)} a {sg(max(res(a) for a in rec), 2)} TWh;
    o P5 simulado continua acima do observado.
  - Os resíduos são sorteados em blocos independentes do tempo meteorológico. Repõem a variância média, mas
    não a frequência de calmarias observada nos anos recentes.
  - A causa exata não foi isolada. Candidatas: os pesos espaciais fixos da frota de out/2026 aplicados ao
    ERA5; a geração potencial reconstruída em anos de corte alto; indisponibilidades que não entram na GNRa.
- **Resultado.** Com o método atual (beta adotado e resíduos), o simulador ainda subestima a importação em
  {f(-max(tod(REGRA_ADOT, rec)), 0)}% a {f(-min(tod(REGRA_ADOT, rec)), 0)}% em {rec[0]}–{rec[-1]}. Em
  {lista(ant)}, o erro fica entre {sg(min(tod(REGRA_ADOT, ant)), 0)}% e {sg(max(tod(REGRA_ADOT, ant)), 0)}%.

**3. O que é esperado.**
- Um único ano não testa a distribuição: o observado de 2026 está no percentil {f(nb['A_pct'], 0)} de A.
- Cortes por restrição de rede em horas de importação não são representados. Em 2025 somaram
  {f(corte25, 2)} TWh.
- A diferença entre os conceitos de carga (API × balanço) muda o nível de M, mas no sentido de aumentar a
  importação simulada.
- O momento exato das calmarias de um ano não é previsível pelo ERA5 com uma função de transferência média.

**Conclusão.**
- **Erro de método (corrigido).** A inconsistência do beta era um erro, e o efeito crescia com o corte.
  Corrigida, a regra reproduz a importação quando recebe as formas observadas.
- **Limitação sistemática (não é erro de código).** A maior parte da subestimação de {rec[0]}–{rec[-1]} vem da
  forma eólica simulada. Ela não representa as horas de pouco vento da frota recente, e os resíduos
  sorteados não corrigem isso. O sinal se repete em três anos seguidos, então não é acaso de 2026.
- **Consequência para 2030.**
  - Com o beta adotado, a importação média (DC central, eólica base) passou de {f(nb['imp30_ant'], 2)} TWh
    (versão anterior) para {f(nb['imp30'], 2)} TWh. O efeito dos data centers passou de {f(nb['dc30_ant'], 2)}
    para {f(nb['dc30'], 2)} TWh (tabela abaixo; mesmos sorteios).
  - A limitação da forma eólica pesa mais: indica que a importação de 2030 tende a estar **subestimada**.
    Nos anos recentes, com os níveis observados, o déficit foi de {f(-max(tod(REGRA_ADOT, rec)), 0)}% a
    {f(-min(tod(REGRA_ADOT, rec)), 0)}%.
  - O efeito pareado dos data centers também tende a crescer quando há mais horas perto de zero.
  - Essa limitação não foi corrigida; uma correção possível está nos próximos passos (STATUS.md).

{tab(t_30)}
{fig('r27')}"""
