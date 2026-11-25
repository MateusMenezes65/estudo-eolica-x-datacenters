# Registro de decisões técnicas

Formato: decisão — justificativa — status (adotada / provisória / pendente do usuário).

## Ambiente

1. **Python 3.14.1** em `.venv` — é o único Python instalado (não há 3.11/3.12);
   pandas 3.1, numpy 2.5, pyarrow 26, scikit-learn 1.9 têm wheels para 3.14 e
   instalaram sem compilação. — adotada.
2. **Git local inicializado** (a pasta não pertencia a nenhum repositório).
   Identidade configurada só neste repositório (`git config --local`), informada
   pelo usuário em 2026-11-11; configuração global não alterada. — adotada.

## Coleta

3. **Parquet** como formato preferido do ONS (≈ 10× menor que CSV); CSV quando o
   ONS não publica Parquet no período (intercâmbio 2022). — adotada.
4. **Limiar de "download grande" = 50 MB por conjunto**; acima disso, pedido de
   confirmação. Autorizados em 2026-11-11: geração e FC por usina, constrained-off
   eólico/solar, MMGD ANEEL, Open-Meteo. — adotada.
5. **Carga verificada semi-horária via API do ONS** (`apicarga.ons.org.br`),
   fonte não listada no catálogo original, incluída porque separa carga global,
   carga líquida de MMGD e MMGD (regra 8). — adotada.
6. **Meteorologia: Open-Meteo com `models=era5`** (0,25°), fixado para
   homogeneidade temporal e extensão futura a anos anteriores (papel 2 dos
   modelos). 34 pontos: 8 capitais + 16 clusters eólicos + 10 solares (k-means
   pesado pela potência SIGA em operação/construção; semente 20261111). — adotada.
7. **Calendário**: biblioteca `holidays` (nacionais + estaduais das 8 UFs);
   São João (23–24/06) e Carnaval como eventos; feriados municipais não incluídos. — adotada.
8. **Temperatura ponderada pela população da UF (Censo 2022)**, não pela carga
   (não há carga horária por UF). — adotada.

## Tempo e unidades

9. `t` = início da hora em Brasília. ONS horário já está assim; API de carga
   (fim do intervalo, UTC) → início em Brasília; ERA5 instantâneo → média de t e
   t+1h; radiação (média da hora anterior) → valor rotulado t+1h. — adotada.
10. 30 min → hora: média dos dois MWmed (equivale a MWh na hora). Nenhuma hora
    incompleta encontrada. — adotada.
11. **Corte analítico do histórico: 2022-01-01 a 2025-12-31** (anos completos);
    2026-01 a 2026-10 apenas complementar; dados do mês corrente são preliminares
    (a identidade carga global = líquida + MMGD falha nas últimas horas). — adotada.

## Definições (afetam resultados — validar)

12. **Quebra de definição no balanço ONS em 2023-04-29 00h**: a partir daí
    `val_carga` inclui a MMGD estimada e `val_gersolar` inclui a mesma MMGD
    (linhas "Pequenas Usinas (MMGD)" em geração por usina). O balanço fecha nos
    dois regimes, mas a série de carga tem degrau de ~0,5 GW. — fato observado.
13. **Proposta para L_base: carga líquida de MMGD da API** (`val_cargaglobalsmmgd`,
    definição homogênea 2022+) e **MMGD como geração distribuída separada**
    (`val_cargammgd`, API), projetada para 2030 pelo PDE/ANEEL. A geração
    centralizada e o intercâmbio vêm do balanço (excluindo a MMGD). Diferença
    residual entre as fontes: ±100 MWmed até 2025-T2, −300 a −500 MWmed de
    2025-T3 em diante (a investigar). Alternativa: balanço líquido (`val_carga`
    − MMGD por usina), que fecha exatamente mas mistura duas estimativas de MMGD. — **adotada pelo usuário em 2026-11-11**.
    Consequência: no balanço futuro, G_NE inclui a MMGD projetada como geração
    distribuída e L_base é a carga líquida de MMGD; a MMGD nunca é descontada da
    carga e somada à geração ao mesmo tempo (regra 8).
14. **Curtailment**: usar a GNRa apurada pelo ONS (`val_geracaonaorealizadaapurada`,
    só nos patamares restritos) como corte; potencial = geração + GNRa. Não usar
    `referência − geração` em todas as horas: a referência é menor que a geração
    em 45 % das horas-usina eólicas (65 % em 2022), logo não é potencial puro. — adotada (regra 4).
15. **Data centers no PDE 2035** — usuário (2026-11-11): L_DC é incremental ao
    PDE de referência e, num primeiro momento, deve reproduzir a projeção do PDE.
    O que o PDE publica (extraído por `src/collect/pde_extract.py` →
    `config/pde2035_extraido.csv`):
    - carga do NE, referência: 13 684 (2025) → 16 340 (2030) → 19 610 MWmed (2035)
      (Tabela 2-3); inferior/superior só em 2025 e 2035 (18,1 e 28,7 GWmed em 2035);
    - "cargas especiais" (VE + data centers + H2) no Brasil em 2035: 9,5 / 11,7 /
      131,1 TWh (inferior / referência / superior), sem separação por tipo,
      subsistema nem ano;
    - pedidos de conexão de data centers à Rede Básica no MME (out/2025), Brasil:
      17,4 GW acumulados até 2030, 26,3 GW até 2038; a distribuição por UF existe
      só como mapa (Figura 4-4), sem valores legíveis por tipo e UF.
    Conclusão: **o PDE não publica uma trajetória de data centers para o NE**. Os
    data centers do cenário de referência estão embutidos na carga do NE e não são
    separáveis.
    **Decisão do usuário (2026-11-11): opção A + C.** Caso-base = PDE de
    referência puro (L_DC incremental = 0; os DC do PDE ficam embutidos na carga
    do NE). Cenários de DC (conservador/central/alto) = inventário documentado de
    projetos no NE (#11), somado ao caso-base, com o pipeline do MME como teto. A
    diferença PDE superior − referência (opção B) fica apenas como estresse. —
    adotada.
16b. **Projeção oficial de DC usada nos cenários**: a previsão de carga do PLAN
    2026-2030 (ONS/EPE/CCEE) publica a carga de DC de Rede Básica por subsistema.
    NE, 2ª Revisão Quadrimestral (acessos de 22/07/2026): 112 / 333 / 628 / 813 /
    2.098 MWmed (2026–2030), dos quais 1.886 MWmed de contratos assinados em 2030.
    Valores lidos dos rótulos dos gráficos (slides do workshop; a nota técnica da
    2ª RQ não foi localizada) e conferidos com o texto (incremento de 807 MWmed
    sobre a 1ª RQ). Cenários: conservador = contratos; central = 2ª RQ; alto =
    contratos + 100% pareceres + inventário M3 (CDV_ACESSOS, QAIR2, ENEGIX). Os
    valores oficiais já são MWmed de carga: sem PUE nem utilização. — adotada;
    cenário alto aceito pelo usuário em 2026-11-11.
19. **ERA5 1995–2021** nos mesmos 34 pontos, em blocos de 9 anos
    (`data/raw/openmeteo/hist/`), autorizado pelo usuário em 2026-11-11. Mesma
    grade e modelo (`models=era5`) do período de calibração. — adotada.

## Anomalias conhecidas (não corrigidas; tratadas na análise)

16. Balanço ONS 2026-01 a 2026-05: 878 horas em que G − L − I não fecha (até
    −17,5 GW) e eólica do balanço muito abaixo da soma por usina (72 horas
    < 50 %). Dados em consistência pelo ONS; 2026 é complementar. Ação: excluir
    essas horas do balanço ou usar geração por usina. — adotada.
17. FC por usina: 3 888 horas-usina com capacidade 0 e 1 796 com geração > 105 %
    da capacidade (registro de capacidade defasado). Impacto agregado ≈ 0,3 TWh em
    ~450 TWh. Ação proposta (Dia 2): CF agregado só com usinas de capacidade > 0;
    não recortar valores. — provisória.
18. MMGD ANEEL: a única data por empreendimento é a **última atualização
    cadastral**, não a data de conexão; a capacidade acumulada por data é viesada
    para datas recentes. Uso: fotografia atual por UF; trajetória histórica pela
    MMGD estimada do ONS. Base contém dados pessoais tarjados: só agregados. — adotada.

## Dia 2 — modelos e cenários (2026-11-11)

20. **CF eólico potencial plausível**: o salto para 0,48 em 2025 vem de ano mais ventoso
    (vento³ +11–17%) e de curva de potência 5–10% maior da frota nova, em horas restritas e
    não restritas; não há sinal de GNRa inflada. — fato observado.
21. **Fator de frota por ano climático** no simulador: k = média do modelo B0/C0 treinado na
    frota recente (2024-07..2026-10) / média observada no ano. Preserva a variabilidade
    horária observada. — adotada.
22. **Carga modelada como bruta** (forma estável) e MMGD separada; a carga líquida muda de forma
    com a MMGD (A0 líquida: MAE 3,4–9,5%; bruta: 2,6–3,2%). — adotada.
23. **Nível de carga em 2030** = carga global do NE no PDE referência (16.340 MWmed). **MMGD em
    2030** = MMGD média do NE em 2025 (API, 1.527 MWmed) × crescimento da capacidade de MMGD
    do Brasil no PDE (1,507; faixa 1,27–1,78). — hipótese adotada.
24. **Eólica em 2030**: baixa = operação (32,3 GW); base = operação + construção (34,3 GW);
    alta = base + 5,1 GW da expansão indicativa do PDE alocada ao NE (39,4 GW). Solar =
    13,5 GW. O SIGA aberto não traz datas para projetos fora de operação. — hipótese adotada.
25. **Hidráulica e térmica**: despacho horário histórico do ano climático. — hipótese; sem redespacho.
26. **Intercâmbio**: exportação limitada a 21 GW (PDE, seção 4.3.2); importação sem limite
    documentado, então sensibilidade em 6, 8 e 10 GW. — adotada.
27. **Classificador de cortes**: viável para ordenar horas (ENE, CNF, total), mas mal calibrado
    sob mudança de regime; não gera probabilidade de corte em 2030. REL não é previsível. —
    adotada (uso descritivo).
28. **Backtesting**: 12 dobras mensais em 2025 com janela expansível, HGB com hiperparâmetros
    fixos e semente 20261111; o clima ERA5 conta como previsão perfeita (limite superior). — adotada.

## Revisão de hipóteses com o usuário (2026-11-12)

29. **Base de carga de 2030 = 2ª Revisão Quadrimestral do PLAN 2026–2030** (ONS/EPE/CCEE,
    ago/2026). Carga global do NE em 2030 = 18.278 MWmed, menos 2.098 MWmed de DC de Rede
    Básica = **16.180 MWmed sem DC**. **MMGD em 2030 = 2.386 MWmed** (oficial). Valores em
    `config/plan_2rq_ne.csv`. Substitui as decisões 23 (carga do PDE, MMGD estimada) e a
    sensibilidade de dupla contagem. O PDE (16.340 MWmed, −258 MWmed) fica como sensibilidade. —
    adotada pelo usuário.
30. **Eólica alta mantida**: 39,4 GW (base + 5,1 GW da expansão indicativa do PDE, toda no NE). —
    confirmada pelo usuário.
31. **Despacho hidrotérmico histórico** como caso central, com **hidráulica plana** (mesma
    energia anual, perfil constante) como sensibilidade pessimista. — adotada pelo usuário.

## Dia 3 — incerteza e relatório final (2026-11-12)

32. **Clima com pesos fixos da frota atual** (out/2026) para todos os anos 1995–2026
    (`src/features/clima_historico.py`): todos os anos meteorológicos representam a mesma
    população de usinas. — adotada.
33. **Perfis sintéticos de 2030** por funções de transferência (carga bruta, MMGD, CF eólico e
    solar potenciais), com o clima de cada ano alinhado ao calendário de 2030 (29/02 descartado).
    A variabilidade não explicada é recomposta com resíduos FORA DA AMOSTRA (validação cruzada
    mensal, janela 2024-07..2025-12), reamostrados juntos em blocos de 7 dias iniciados à 00h,
    a ±14 dias do dia do ano. CF limitado a [0, 1]: ajusta <0,1% da energia. — adotada.
34. **Hidráulica no Monte Carlo = regra histórica emulada** (decisão do usuário, 2026-11-12; coeficiente
    redefinido na decisão 52):
    energia diária do ano hidrológico sorteado (2022–2025); forma intradiária = média diária +
    beta × desvio intradiário da carga líquida simulada (beta do próprio ano: 0,27–0,43),
    limitada ao mínimo e ao máximo mensais históricos e reajustada para conservar a energia
    diária. Despacho histórico sorteado (sem resposta) e hidráulica plana ficam como
    sensibilidades. A térmica segue o histórico do ano sorteado. Motivo: sortear o despacho de
    outro ano quebra a dependência entre clima e despacho (a hidráulica do NE responde às
    variações intradiárias da carga líquida, correlação ~0,7). — adotada.
35. **Monte Carlo**: 2.000 sorteios (semente 20261112); números aleatórios comuns entre
    cenários; a incerteza amostrada é só climática e operacional, e as escolhas de cenário
    ficam como eixos separados. Convergência: média ±0,3% e P95 ±0,5% entre 1.500 e 2.000
    sorteios. Sensibilidades com 500 sorteios comuns. — adotada.
36. **Limites de importação** (6, 8 e 10 GW) são reportados como horas acima do limite e como a
    fração dos anos simulados com ao menos uma hora acima dele, sem interpretação de risco de
    déficit. — adotada.
37. **Referências acadêmicas** citadas apenas após conferir os metadados (Crossref, JMLR ou
    DOI). — adotada.

## Revisão de verificação (2026-11-15)

Verificação completa do projeto; correções técnicas aplicadas e resultados regerados.

38. **Resíduos recentrados no Monte Carlo.** Os resíduos fora da amostra não têm média zero (CF
    eólico −0,0055; CF solar −0,0042; MMGD −0,0042; carga +0,0019 sob o esquema de sorteio), e o
    sorteio por época do ano pesa os meses de forma desigual. De cada série subtrai-se a média
    esperada sob o próprio sorteio, e as formas de carga e MMGD são renormalizadas para média 1 em
    cada sorteio. O nível anual passa a vir só dos cenários e das funções de transferência; os
    resíduos repõem variabilidade horária. O caso sem a correção fica como sensibilidade
    ("residuos sem recentrar"). — adotada (correção técnica).
39. **Regra hidráulica conserva a energia diária exatamente.** A energia cortada pelos limites
    mensais é devolvida às horas com folga até fechar o dia (antes, 3 iterações deixavam +0,4% de
    energia anual). O coeficiente beta é estimado sobre a carga líquida observada (geração já
    cortada); descontar ou não a térmica muda beta em menos de 0,005. — adotada.
40. **Validação retrospectiva do simulador** (`src/sim/backcast.py`, etapa `backcast` do pipeline):
    o simulador roda com clima, ano hidrotérmico e níveis observados de 2022–2025 e é comparado à
    importação observada. Erro da importação anual: +4% a −30% com a regra emulada e +35% a −17%
    com o despacho hidráulico observado; nenhuma convenção é melhor em todos os anos. Em 2025,
    0,36 TWh de corte eólico ocorreram em horas de importação (não representados); a
    subestimação de 2024 não tem origem identificada. Consequência: o nível absoluto da importação
    de 2030 carrega erro dessa ordem; as diferenças pareadas são mais robustas. — adotada.
41. **Diferença de carga entre API e balanço (pendência da decisão 13, investigada).** O resíduo
    é exatamente carga líquida do balanço (`val_carga` − MMGD por usina) menos carga líquida da
    API: +57 (2022), −24 (2023), −62 (2024) e −171 MWmed (2025; −313 no 3º e −431 no 4º
    trimestre). A causa da divergência a partir de 2025-T3 não foi identificada nos dados
    abertos. A carga global de 2025 é 13.623 MWmed na API e 13.445 no PLAN (fonte do nível de
    2030). O nível do PLAN é mantido; o nível da API (+1,3%) entra como sensibilidade. — adotada.
42. **Limites de importação: leitura.** A validação retrospectiva mostrava que a regra emulada não
    superestima os picos nos níveis históricos; com o β da decisão 52, o pico simulado fica de −1,1 a +0,1 GW
    do observado. Os picos de 2030 acima do maior fluxo observado
    (7,9 GW) vêm do crescimento da carga com a térmica mantida no despacho histórico; o
    redespacho térmico não é representado. A tabela mede exposição, não risco. — adotada.
43. **CF solar potencial agregado acima de 0,85** (228 horas, quase todas em ago–out/2026):
    investigado. O potencial passa da capacidade em menos de 1% das horas-usina (≤ 0,04 TWh por
    ano), então não é capacidade defasada; nessas horas a GNRa é 31% do potencial. Mantido sem
    recorte. Afeta excedente e absorção, não a importação. — fato observado.
44. **Cenário alto: possível sobreposição do CDV_ACESSOS.** É um direito de acesso comprado, com
    processo oficial (Portaria 2.835/2024). Não foi possível verificar se já está entre os
    pareceres favoráveis da 2ª RQ; se estiver, o cenário alto o conta duas vezes (266 MWmed;
    sem ele, 2.487 MWmed). — **mantido pelo usuário em 2026-11-15**, com a ressalva registrada nos relatórios.
45. **Convenção hidráulica do caso central.** A regra emulada (decisão 34) foi mantida. A
    validação retrospectiva não aponta uma convenção melhor; trocar o caso central é escolha de
    premissa. — **regra emulada mantida pelo usuário em 2026-11-15**.
46. **Relatórios sem literais dependentes de resultado.** Correlações, postos de vento, betas,
    fluxo máximo, razões de compensação e faixas de sensibilidade passam a ser lidos das tabelas.
    Valores de análises exploratórias (degrau de ~0,5 GW, curva de potência 5–10%, 878 horas)
    citam a decisão em que estão registrados. — adotada.

## Simulador interativo 2026–2030 (2026-11-16)

Pedido do usuário: simulador interativo com barra de anos 2026–2030, M(t) horário ao longo do ano,
resorteio do ano de clima e do ano hidrotérmico (regra emulada) e escolha dos cenários eólico e de
data centers de cada ano; anexo com os níveis de 2026–2029; backtest de 2026 com os dados observados.
Os resultados e as conclusões de 2030 não mudam.

47. **Níveis por ano** (`config/cenarios_anuais.yaml`, `src/sim/trajetorias.py`). Carga sem DC =
    carga global da 2ª RQ do PLAN − DC de Rede Básica do ano (dado); MMGD = 2ª RQ (dado). Solar e
    eólica = capacidade média do ano: operação no SIGA (em 2026 ponderada pela data de entrada) +
    construção com entrada uniforme em 2027–2029 (frações 1/6, 1/2, 5/6; toda em 2030) — hipótese,
    porque o SIGA não traz datas para projetos fora de operação (decisão 24). Eólica alta = base +
    expansão indicativa acumulada do PDE no ano (0; 0; 1,7; 3,4; 5,1 GW). DC: componentes dos
    cenários de 2030 sobre a 2ª RQ do ano; parecer de 2026 = total − contratos (112 − 98). As regras
    reproduzem 2030 (eólica ±1 MW; solar 13.493 × 13.500 arredondado); a coluna de 2030 usa os
    valores do estudo. — adotada.
48. **Calendário de cada ano.** A forma de carga (A0) depende do calendário e é prevista pela mesma
    função de transferência para 2026–2029 (refeita no calendário de 2030, difere do estudo em
    4e-16). MMGD, CF eólico e solar e o pool hidrotérmico não usam calendário e são reaproveitados.
    **2028 é bissexto**: 29/02 repete o clima, os perfis e o ano hidrotérmico de 28/02, e a energia
    anual integra 8.784 horas. — adotada.
49. **Monte Carlo por ano** (`src/sim/anos.py`): 2.000 sorteios, semente do estudo, mesmas funções
    de `src/sim/montecarlo.py` (generalizadas para 365/366 dias sem mudar 2030). 2030 recalculado é
    idêntico ao do estudo (24.000 linhas, diferença 0). Faixas anuais e mensais alimentam o simulador. — adotada.
50. **Backtest de 2026** (`src/sim/backtest_2026.py`): jan–out/2026, só horas em que o balanço fecha
    (6.418 de 7.296); níveis do cenário de 2026 com DC central. Observado "potencial" = intercâmbio +
    cortes (conceito do simulador). (A) ex-ante, 2.000 sorteios de clima e hidrologia: a importação
    observada (1,68 TWh) fica no percentil 78 (P5–P95 0,21–2,73). (B) clima ERA5 e hidrologia de 2026,
    funções de transferência re-treinadas só até 2025-12-31: 0,88 TWh com a regra emulada e 1,25 TWh
    com o despacho hidráulico observado (subestima 48% e 25%). O M médio de B é 742 MW menor que o
    observado (eólica potencial −507, MMGD −125, carga +302, conceito de carga API × balanço −419,
    decisão 41), o que empurraria a importação para cima; a subestimação vem da forma horária: a
    regra emulada leva mais hidráulica às horas de importação que o despacho real, e os perfis têm
    menos horas extremas (P95 da importação 976 × 2.305 MW). Reforça a decisão 40: nível absoluto com
    erro de dezenas de por cento. — fato observado.
51. **Simulador interativo** (`src/report/simulador.py` → `reports/site/simulador/`): página
    estática, sem servidor nem dependências externas; o motor em JavaScript espelha o do Python e
    se autoverifica contra 5 casos de referência (um por ano, inclui 2028; diferença relativa
    ~3e-14). Insumos quantizados (1e-4 nas formas e CF; 0,1 MW na hidrotérmica). Os sorteios da
    página usam gerador próprio (semente na URL); as faixas P5–P95 exibidas vêm do Monte Carlo da
    decisão 49. — adotada.

## Diagnóstico da subestimação da importação (2026-11-17)

Pedido do usuário: incluir o backtest de 2026 no relatório técnico, com o perfil horário da hidráulica
emulada, e identificar se a subestimação é esperada ou vem de erro de metodologia
(`src/sim/diagnostico_importacao.py`; relatório técnico, seção 7.5).

52. **Inconsistência no coeficiente da regra hidráulica (erro de método).** O beta da regra emulada
    (decisões 34 e 39) é estimado sobre a carga líquida REALIZADA (eólica e solar já cortadas), mas
    aplicado à carga líquida POTENCIAL do simulador. Com corte alto, o desvio intradiário da potencial é
    bem maior (2025: 4,6 × 2,6 GW) e o beta exagera a resposta: leva hidráulica demais para as horas de
    carga líquida alta e reduz a importação. O beta estimado sobre a carga líquida potencial
    (consistente) é 0,42 / 0,32 / 0,27 / 0,17 / 0,21 em 2022–2026, contra 0,43 / 0,35 / 0,37 / 0,27 / 0,37.
    Com ele, o erro retrospectivo cai de −24% para −18% (2024) e de −30% para −20% (2025); no backtest
    de 2026, B passa de 0,88 para 1,12 TWh; com as formas observadas, a regra consistente erra −1% a −7%
    em 2024–2026. Em 2030 (mesmos sorteios): importação central/base 5,04 → 5,18 TWh; efeito dos DC
    2,25 → 2,29 TWh. — **adotada pelo usuário em 2026-11-17**: o caso central do Monte Carlo (e dos anos
    2026–2030, do backtest e do simulador) usa o beta sobre a carga líquida potencial
    (`montecarlo.beta_regra`); o anterior fica como sensibilidade ("hidraulica: beta anterior (carga
    liquida realizada)"). Pipeline regenerado a partir do Monte Carlo; os números de 2030 mudaram.
53. **Forma eólica simulada: poucas horas de pouco vento na frota recente (limitação sistemática).**
    Com os níveis observados e funções de transferência re-treinadas sem o próprio ano, trocar só a
    forma eólica pela observada aumenta a importação em 0,27–0,50 TWh em 2024–2026 (−0,16 em 2022). A
    eólica simulada superestima as horas de menos vento em +74 MW (2022) a +806 MW (2026). Os resíduos
    sorteados repõem a cauda em 2022–2023, mas não em 2024–2026. Com beta consistente e resíduos, a
    importação ainda fica 13% a 45% abaixo da observada em 2024–2026. Não é erro de código (com as
    formas observadas a regra reproduz o observado) nem acaso de 2026 (o sinal se repete em três anos).
    Causa exata não isolada (candidatas: pesos espaciais fixos da frota aplicados ao ERA5, geração
    potencial em anos de corte alto, indisponibilidades fora da GNRa). Consequência: a importação de
    2030 tende a estar subestimada. Correção possível (quantile mapping do CF eólico ou resíduos
    condicionados ao nível previsto) não aplicada. — fato observado; em 2026-11-17 o usuário decidiu não
    corrigir por enquanto (limitação mantida e declarada nos relatórios).
    — **revista em 2026-11-25 (decisões 54–56): a limitação não se confirma.** Com o observado corrigido, o vento
    por polo e os resíduos novos, o P5 horário da eólica simulada fica entre −480 e +111 MW do observado em
    2022–2026 (−120 a +111 em 2024–2026).

## Auditoria conceitual e estatística (2026-11-25)

Pedido do usuário antes do push final: procurar inconsistências conceituais e estatísticas, sobretudo no
feature selection das funções de transferência. A auditoria rodou numa cópia, sem alterar o projeto; em
seguida o usuário decidiu aplicar as quatro correções de método ("Aplicar as quatro"). Efeito passo a passo
(Monte Carlo de 2.000 sorteios, DC central, eólica base; importação média / efeito dos DC, em TWh):

| Passo | Importação | Efeito dos DC | Erro retrospectivo 2022–2025 (beta do ano) |
|---|---|---|---|
| antes (commit 1d1252d) | 5,18 | 2,29 | −20% a +8% (contra a realizada) |
| + observado do diagnóstico (54) | 5,18 | 2,29 | −17% a +9% (contra a potencial) |
| + features (55) | 5,06 | 2,22 | −17% a −7% |
| + resíduos (56) | 5,37 | 2,32 | −12% a +2% |
| + beta de 2026 em 2030 (57) | 5,57 | 2,38 | −12% a +2% |
| ajustes finais: MMGD com mês, centro da solar e da MMGD por hora, validação sem resíduos do próprio ano | 5,55 | 2,38 | −11% a +1% |

54. **Geração potencial observada: uma só definição** (`src/sim/observado.py`). Potencial = balanço do ONS +
    corte apurado (GNRa das usinas com FC × razão balanço/FC). O diagnóstico usava (geração + corte das usinas
    com FC) × razão anual: mesma média, outra forma. As usinas sem FC geram relativamente mais nas calmarias, e
    a versão escalada subestimava a eólica em 132–213 MW nas horas de importação (137–262 MW no P5), o que
    inflava a importação "observada" em 4% a 10% (2022: 1,62 contra 1,47 TWh). A validação retrospectiva passa a
    comparar com a importação potencial, o conceito do simulador. O corte eólico em horas de importação
    (0,37 TWh em 2025) só reduziria a importação em 0,07 TWh se gerado. Não muda 2030. — adotada pelo usuário.
55. **Features das funções de transferência por ablação fora da amostra** (`src/models/ablacao.py`,
    `reports/models/ablacao_features.csv`): cada variante é re-treinada e avaliada em anos ou blocos longos fora
    do treino, com IC95 por bootstrap em blocos de 7 dias. Saem o dia do ano (os quatro modelos), vento médio e
    vento³, CDH, temperatura aparente, umidade, irradiância dos polos na carga e os feriados menores; entram o
    vento de cada um dos 16 polos, a média de 24 h da temperatura e a irradiância das capitais na carga.
    RMSE fora da amostra: B0 −8,0%, C0 −5,3%, A0 −3,0%, E0 −2,8%, todos significativos. A escolha anterior se
    apoiava em importância por permutação, que premiava o dia do ano porque o modelo se apoiava nele.
    Ressalvas: features escolhidas nas mesmas dobras (ganho ligeiramente otimista); diferenças abaixo de 1% não
    se interpretam (o ruído as produz). A versão de E0 com 3 features, proposta ao usuário, foi descartada: com
    a forma da MMGD corrigida (decisão 56) ela piora 3%; E0 ficou com hora, mês e as duas irradiâncias. O fator
    de frota do determinístico passou a usar as mesmas funções e o clima de pesos fixos. O erro médio da carga
    com o ano fora do treino varia pouco entre os dias da semana (2,7% a 3,0%). — adotada pelo usuário.
56. **Resíduos do Monte Carlo.** (a) Janela até 2026-10-31: de 82% a 94% da importação observada ocorre de
    janeiro a junho, época em que a janela anterior só tinha 2025. (b) Centro mensal no lugar de um centro
    único do ano: o viés de B0 vinha do 2º semestre de 2024 (−0,05 em jul/2024) e era compensado também em
    janeiro–junho, onde não existe. (c) Solar e MMGD centradas por mês e hora: o centro único somava ~57 MW de
    solar à noite. (d) Nível da MMGD com taxa de crescimento vizinha nas pontas da série: a janela truncada
    distorcia a forma em até 12%. (e) Nas validações, o ano testado não recebe os próprios resíduos. A carga de
    2026 (jan–out) tem o nível ajustado para resíduo médio zero. — adotada pelo usuário (a, b); c, d e e são
    consequências técnicas.
57. **Coeficiente da regra hidráulica em 2030 = o de 2026 (0,21).** O beta cai quando a carga líquida oscila
    mais: 0,42 (2022, desvio intradiário de 1,9 GW) → 0,16 (2025, 4,7 GW) e, dentro de cada ano, dos dias de
    menor para os de maior oscilação (2026: 0,27 → 0,19). Em 2030 o desvio simulado é 6,9 GW; aplicar o beta de
    cada ano hidrológico era o mesmo erro da decisão 52. 2026 (6,0 GW) é o regime observado mais próximo; em
    2026 o beta sobe em relação a 2025, porque a hidrologia também pesa. Na validação retrospectiva cada ano usa
    o próprio beta. Sensibilidades: beta do próprio ano hidrológico (−0,19 TWh) e amplitude constante em MW
    (+0,54 TWh; contrariada por 2026, em que a resposta foi de ~1,3 GW contra 0,75–0,94 GW em 2022–2025).
    Ressalva: 6.418 horas válidas de jan–out/2026. Configuração em `config/cenarios.yaml`. — adotada pelo usuário.
58. **Achados da auditoria declarados nos relatórios, sem mudar o método.** (a) Clima e hidrologia são sorteados como
    independentes; nos quatro anos comuns a correlação entre CF eólico anual e hidráulica anual é −0,86 (n = 4,
    indicativo): os pares reais davam média 7% menor e dispersão 30% menor que os independentes. (b) A razão
    entre a geração de referência do ONS e a verificada, em horas sem restrição, vai de 0,75 (2022) a 1,05
    (2026): a GNRa, e com ela o CF potencial, não é homogênea; a deriva do resíduo de B0 se concentra nas horas
    com risco de corte e é nula nas sem risco, onde a importação ocorre. Enfraquece a decisão 20. (c) A
    compensação eólica supõe o perfil da frota. (d) Os 2.000 sorteios têm erro de simulação pequeno, mas a
    amostra real é de 31 climas × 4 hidrologias: IC95 da média por reamostragem dos anos, antes das correções,
    3,9–6,5 TWh (efeito dos DC, 1,9–2,7). (e) O sinal do efeito dos DC é positivo por construção (carga constante
    nunca reduz a importação): não é evidência. (f) Comparar o intervalo interquartil entre sorteios com a
    amplitude entre cenários ("o clima pesa tanto quanto o cenário") mistura coisas de natureza diferente. —
    fato observado.
    **Textos ajustados em 2026-11-25, por decisão do usuário.** Saem "100% dos sorteios", "o clima pesa tanto
    quanto o cenário" e "curvas claramente separadas" (a mediana do central, 5,3 TWh, fica abaixo do P95 sem DC,
    6,4). Entra o tamanho do efeito em relação à energia dos DC (13% no central) e o IC95 da amostra de anos,
    calculado no pipeline (`montecarlo.ic_amostra_de_anos`, `reports/mc/mc_incerteza.json`): importação central
    4,5–6,8 TWh, sem DC 2,4–4,0, efeito dos DC 2,0–2,8. O erro-padrão da amostra de anos (0,59 TWh) é 12 vezes o
    de simulação. Com 4 anos hidrológicos, o intervalo é aproximado.
