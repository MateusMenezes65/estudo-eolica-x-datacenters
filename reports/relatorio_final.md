# Data centers e expansão eólica no subsistema Nordeste — balanço horário em 2030

Relatório final gerado por `python -m src.report.final` em 2026-11-12 18:36 UTC.
Todos os números vêm de tabelas versionadas em `reports/` e `config/`. Os resultados de 2030 são
**condicionais a cenários e hipóteses declarados**, não previsões. Margem negativa indica necessidade
de importação do restante do SIN, **não** déficit de suprimento.

## Resumo

- **Data centers.** A carga de data centers de Rede Básica projetada oficialmente para o NE em 2030
  (2ª Revisão Quadrimestral do PLAN 2026–2030) é de 2.098 MWmed, dos quais
  1.886 MWmed já têm contrato assinado.
- **Importação.** Com a eólica do cenário base (34,3 GW), a necessidade média de
  importação do NE em 2030 vai de 3,0 TWh/ano sem novos data
  centers para 5,4 TWh/ano no cenário central.
- **Efeito pareado.** No mesmo clima, o cenário central acrescenta
  +2,4 TWh/ano, com P5–P95 de 1,1
  a 3,8, e +465
  horas com importação. O aumento ocorre em 100% dos sorteios.
- **Compensação em energia não basta.** 4,6 GW eólicos
  adicionais compensariam a energia anual do cenário central. Para devolver a importação anual média ao
  nível sem data centers seriam necessários 10,6 GW,
  cerca de 2,3
  vezes mais. O vento falta justamente nas horas de importação, e a razão cresce com a frota.
- **Absorção de excedente.** 87% da energia dos data
  centers cairia em horas de excedente regional. Isso é potencial de absorção, não corte evitado: o
  estudo não representa a rede interna nem as restrições locais.
- **Variabilidade climática.** O clima pesa tanto quanto a escolha de cenário. A amplitude interquartil
  da importação anual entre sorteios (cenário central, eólica base) é de
  3,5 TWh, contra 3,2
  TWh entre as medianas dos cenários de data centers. O ano meteorológico explica 77%
  da variância e o ano hidrológico, 21%.
- **Hipóteses que mais pesam,** além do próprio cenário de data centers:
  - nível da carga ±5%: -1,1 / +1,3 TWh;
  - convenção do despacho hidráulico: hidráulica plana +2,2 TWh; despacho
    histórico sorteado, sem resposta, +0,9 TWh;
  - atraso de 12 meses dos data centers: -1,6 TWh;
  - capacidade eólica: baixa +0,8, alta -1,4 TWh.

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
- **Data centers:** inventário documental em `config/data_centers_ne.csv` (17 itens com fonte,
  definição da potência e maturidade).

**Achados de qualidade que condicionam o método.**

1. **Mudança de definição da carga.** Em 29/04/2023 o balanço do ONS passou a incluir a MMGD estimada
   na carga e na geração solar; a série de carga tem um degrau de ~0,5 GW. A carga base usada é a carga
   global líquida de MMGD da API do ONS, de definição homogênea; a MMGD é tratada à parte.
2. **Corte eólico em alta.** O corte eólico apurado (GNRa) passou de 0,6% (2022) para
   20,2% (2025) do potencial.
   - A geração de referência do constrained-off fica abaixo da geração em parte relevante das horas,
     então não é o potencial.
   - O potencial adotado é geração verificada + GNRa.
   - Com o corte, a correlação vento³ × CF observado cai de 0,87 para 0,58, enquanto vento³ × CF
     potencial fica em 0,85–0,89.
3. **Anos recentes pouco ventosos.** No ERA5, 2022–2024 estão entre os anos menos ventosos de 1995–2025
   (figura `s2`). Usar só o período com dados do ONS subestimaria anos ventosos.
4. **Balanço de 2026 incompleto.** De jan a mai/2026, 878 horas não fecham. 2026 fica fora da calibração
   do balanço.

## 3. Metodologia

### 3.1 Trajetórias de 2030 (`config/cenarios.yaml`, `config/cenarios_dc.yaml`)

- **Carga sem novos data centers.** Carga global do NE em 2030 na 2ª RQ do PLAN
  (18.278 MWmed) menos a carga de data centers de Rede Básica da mesma
  projeção (2.098), ou seja, 16.180 MWmed.
  O PDE 2035 (16.340 MWmed, com data centers embutidos) entra como sensibilidade.
- **MMGD em 2030.** 2.386 MWmed (2ª RQ do PLAN).
- **Data centers** (MWmed em 2030, carga flat):
  - conservador = contratos assinados, 1.886;
  - central = 2ª RQ do PLAN (100% dos contratos e 50% dos pareceres favoráveis), 2.098;
  - alto = contratos + 100% dos pareceres + projetos anunciados com MW, em rampa, 2.753.
  - A projeção oficial já está em MWmed de carga na rede, então não se aplica PUE.
- **Eólica.** baixa 32,3 GW (só operação, SIGA); base 34,3 GW
  (+ construção); alta 39,4 GW (+ expansão indicativa do PDE até 2030, alocada ao NE).
- **Solar.** 13,5 GW.
- **Intercâmbio.** Exportação limitada a 21 GW (PDE 2035). Não há limite de importação documentado;
  usa-se sensibilidade em 6, 8 e 10 GW.

### 3.2 Modelos

Todos os modelos são HistGradientBoosting (scikit-learn), com hiperparâmetros fixos e semente fixa.

- **Curto prazo (validação acadêmica).** Carga, CF eólico potencial e CF solar, em horizontes de 1 h e
  24 h.
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

- **Sorteios.** 2.000 sorteios, semente 20261112. Cada sorteio combina:
  - um ano meteorológico de 1995–2025 (31 anos);
  - um ano hidrotérmico de 2022–2025;
  - uma sequência de blocos de 7 dias de resíduos **fora da amostra** das quatro
    séries, reamostrados **conjuntamente**, iniciando à 00h e escolhidos a ±14
    dias do dia do ano.
- **Números aleatórios comuns.** Os mesmos sorteios valem para todos os cenários, então as diferenças
  entre cenários são pareadas.
- **Hidráulica (caso central, decidido pelo usuário).** Regra histórica emulada:
  - a energia diária é a do ano hidrológico sorteado;
  - a forma intradiária responde à carga líquida simulada com o coeficiente medido no ano (0,27–0,43);
  - a geração fica dentro dos mínimos e máximos mensais históricos.
  - O despacho histórico sorteado sem resposta e a hidráulica plana entram como sensibilidades.
  - A térmica segue o histórico do ano sorteado.
- **Separação das incertezas.** A incerteza amostrada é climática e operacional. As escolhas de
  cenário ficam como eixos separados.

## 4. Validação

### 4.1 Curto prazo (2025, fora da amostra)

| Alvo | h (horas) | MAE do HGB | Melhor baseline (MAE) | Ganho | Meses em que o HGB vence |
|---|---|---|---|---|---|
| A_carga_liquida | 1 | 139 | sazonal_semanal (468) | 70% | 12/12 |
| A_carga_liquida | 24 | 299 | sazonal_semanal (468) | 36% | 11/12 |
| B_cf_eolico_pot | 1 | 0,015 | persistencia_1h (0,025) | 41% | 12/12 |
| B_cf_eolico_pot | 24 | 0,044 | persistencia_24h (0,082) | 47% | 12/12 |
| C_cf_solar | 1 | 0,018 | sazonal_diario (0,048) | 62% | 12/12 |
| C_cf_solar | 24 | 0,042 | persistencia_24h (0,048) | 13% | 10/12 |

O modelo de árvores supera de forma consistente o baseline sazonal e a persistência. O menor ganho é
o da solar a 24 h.

### 4.2 Funções de transferência

- **Carga bruta normalizada** (validação deixando um ano de fora): MAE de 2,6–3,2%,
  contra 2,8–3,9% do perfil mês × dia × hora.
- **CF eólico potencial:**
  - frota recente (treino até 2025-12, teste em 2026): MAE 0,044 e viés -0,014;
  - correlação horária com o observado em 2022–2025: 0,96–0,98;
  - com os resíduos, o desvio-padrão horário do sintético reproduz o observado
    (0,184 contra 0,183 em 2025).
- **Diferença de nível em 2022–2023.** O CF médio sintético desses anos é maior que o observado
  (0,426 contra 0,408 em 2022). Isso reflete a frota atual,
  com curva de potência 5–10% maior nas faixas de vento alto.
- **Extrapolação.** No máximo 0,15% das horas de 1995–2021 ficam fora da faixa de treino de
  alguma variável.
- **Convergência do Monte Carlo** (cenário central, eólica base): de 1.500 para 2.000 sorteios,
  a média variou 0,25% e o P95, 0,45% (figura `mc2`).
- **Blocos de resíduos.** Trocar os blocos de 7 dias por blocos de 3 ou 14 dias muda a média em menos
  de 0,05 TWh.

### 4.3 Classificador de cortes (Modelo D)

- **Desempenho.** Para o corte por razão energética, ROC-AUC de 0,91–0,93
  e PR-AUC de 0,77–0,85, contra
  0,25–0,32 ao acaso.
- **Instabilidade.** A calibração muda com o regime: a taxa de horas com corte subiu de 7% para 69%
  entre 2022 e 2025.
- **REL não é previsível** com as features ex-ante.
- **Uso.** O classificador fica descritivo. Não gera probabilidade de corte em 2030, e a importância
  das variáveis não tem interpretação causal.

## 5. Resultados para 2030

### 5.1 Distribuições condicionais — eólica base (2.000 sorteios)

| DC | L_DC (MWmed) | Importação TWh/ano: média [P5–P95] | Horas com importação: média [P5–P95] | P95 horário (MW) | Pico (MW) | Maior sequência (h) | Excedente (TWh) | Excedente > 21 GW (TWh) |
|---|---|---|---|---|---|---|---|---|
| sem_dc | 0 | 3,0 [0,9–6,2] | 909 [379–1.562] | 2.714 | 10.228 | 19 | 90,3 | 3,2 |
| conservador | 1.886 | 5,1 [1,9–9,5] | 1.321 [669–2.029] | 4.542 | 12.114 | 29 | 75,8 | 1,9 |
| central | 2.098 | 5,4 [2,0–9,9] | 1.374 [706–2.085] | 4.752 | 12.326 | 31 | 74,3 | 1,8 |
| alto | 2.753 | 6,3 [2,6–11,4] | 1.548 [835–2.294] | 5.401 | 12.981 | 38 | 69,5 | 1,4 |

Importação média (TWh/ano) por cenário de data centers × eólica:

| DC \ eólica | baixa (32,3 GW) | base (34,3 GW) | alta (39,4 GW) |
|---|---|---|---|
| sem_dc | 3,4 | 3,0 | 2,2 |
| conservador | 5,8 | 5,1 | 3,8 |
| central | 6,1 | 5,4 | 4,0 |
| alto | 7,2 | 6,3 | 4,7 |

O simulador determinístico, com os 4 anos observados, dá 2,9 → 5,3 TWh (sem DC → central,
eólica base). Ele difere do Monte Carlo em três escolhas de método:
- despacho histórico pareado ao ano, em vez da regra emulada;
- 4 anos meteorológicos, em vez de 31;
- perfis observados, em vez de sintéticos com resíduos.
A tabela 5.5 quantifica o efeito de cada uma. Figura: `reports/figures/mc1_distribuicao_importacao.png`.

### 5.2 Efeito dos data centers (diferenças pareadas contra sem_dc, mesmo sorteio)

| DC | eólica | Δ importação TWh: média [P5–P95] | Δ horas: média [P5–P95] | sorteios com Δ > 0 |
|---|---|---|---|---|
| conservador | baixa | 2,4 [1,2–3,7] | 470 [331–602] | 100% |
| conservador | base | 2,1 [1,0–3,4] | 412 [277–539] | 100% |
| conservador | alta | 1,6 [0,6–2,8] | 310 [188–425] | 100% |
| central | baixa | 2,7 [1,3–4,2] | 530 [377–674] | 100% |
| central | base | 2,4 [1,1–3,8] | 465 [314–606] | 100% |
| central | alta | 1,8 [0,7–3,1] | 349 [214–478] | 100% |
| alto | baixa | 3,8 [2,0–5,7] | 728 [532–911] | 100% |
| alto | base | 3,3 [1,6–5,3] | 639 [448–820] | 100% |
| alto | alta | 2,5 [1,1–4,3] | 478 [302–652] | 100% |

O efeito incremental dos data centers é positivo em todas as hipóteses testadas e fica na mesma
ordem de grandeza (tabela 5.5, 500 sorteios comuns, DC central):
- convenção hidráulica: +2,40 TWh/ano com a regra emulada, +2,61
  com o despacho histórico sorteado e +2,98 com a hidráulica plana;
- demais sensibilidades (exceto o atraso dos data centers): de +1,81 a +2,98 TWh/ano.
O nível absoluto da importação, em contraste, depende bastante dessas hipóteses.

### 5.3 Compensação eólica (regra 11)

Capacidade eólica adicional que devolve cada métrica ao nível sem data centers, calculada sobre a média
dos sorteios. Para a importação anual, a faixa P5–P95 vem do cálculo sorteio a sorteio.

| DC | eólica | ΔW energia anual (GW) | ΔW importação anual (GW) [P5–P95 por sorteio] | ΔW horas de importação (GW) | ΔW P95 horário (GW) | razão temporal/energia | energia de DC em horas de excedente |
|---|---|---|---|---|---|---|---|
| conservador | baixa | 4,2 | 8,9 [7,5–10,6] | 6,4 | 8,7 | 2,2× | 86% |
| conservador | base | 4,2 | 9,5 [7,8–11,3] | 6,9 | 8,8 | 2,3× | 87% |
| conservador | alta | 4,2 | 10,8 [8,8–13,0] | 7,9 | 9,5 | 2,6× | 91% |
| central | baixa | 4,6 | 10,0 [8,3–11,9] | 7,2 | 9,7 | 2,2× | 85% |
| central | base | 4,6 | 10,6 [8,8–12,7] | 7,7 | 9,9 | 2,3× | 87% |
| central | alta | 4,6 | 12,1 [9,9–14,5] | 8,8 | 10,6 | 2,6× | 90% |
| alto | baixa | 6,1 | 13,4 [11,0–16,1] | 9,5 | 12,8 | 2,2× | 84% |
| alto | base | 6,1 | 14,2 [11,6–17,0] | 10,1 | 13,1 | 2,3× | 86% |
| alto | alta | 6,1 | 16,2 [13,1–19,6] | 11,7 | 14,1 | 2,7× | 90% |

Leitura:
- A compensação temporal exige 2,2–2,7 vezes a capacidade equivalente em energia.
- Quanto maior a frota, mais difícil compensar no tempo: as horas de importação que restam são as de
  vento fraco.
- A compensação pelo P95 horário varia menos com a frota do que a compensação pela importação anual.

### 5.4 Limites de importação (sensibilidade; não é risco de déficit)

Horas por ano com importação acima de cada limite / fração dos anos simulados com ao menos uma hora
acima dele:

| DC (eólica base) | > 6 GW | > 8 GW | > 10 GW |
|---|---|---|---|
| sem_dc | 142 h / 99% | 42 h / 92% | 7 h / 60% |
| conservador | 305 h / 100% | 134 h / 99% | 39 h / 91% |
| central | 328 h / 100% | 149 h / 99% | 46 h / 93% |
| alto | 404 h / 100% | 199 h / 100% | 71 h / 97% |

Não há limite de importação documentado para o NE. O maior fluxo histórico de 2022–2025 foi de ~7,9 GW,
mas fluxo não é capacidade. Estes números indicam exposição, não probabilidade de déficit de suprimento.

### 5.5 Sensibilidades (DC central, eólica base, 500 sorteios comuns)

| Caso | Importação média (TWh) | Δ vs. referência | P95 anual (TWh) | Horas com importação | Efeito pareado dos DC (TWh) [P5–P95] |
|---|---|---|---|---|---|
| referencia | 5,47 | 0,00 | 10,13 | 1.388 | 2,40 [1,21–3,87] |
| sem_dc | 3,07 | -2,40 | 6,23 | 921 | 0,00 [0,00–0,00] |
| carga -5% | 4,38 | -1,09 | 8,44 | 1.186 | 2,03 [0,95–3,43] |
| carga +5% | 6,74 | 1,27 | 12,02 | 1.612 | 2,82 [1,49–4,35] |
| MMGD baixa | 5,62 | 0,15 | 10,43 | 1.437 | 2,48 [1,25–4,00] |
| MMGD alta | 5,38 | -0,09 | 9,96 | 1.360 | 2,36 [1,19–3,80] |
| hidraulica plana | 7,72 | 2,25 | 13,02 | 1.672 | 2,98 [1,81–4,29] |
| hidraulica historica sorteada (sem resposta) | 6,40 | 0,93 | 11,23 | 1.484 | 2,61 [1,55–3,97] |
| DC com atraso de 12 meses | 3,89 | -1,59 | 7,63 | 1.088 | 0,82 [0,39–1,37] |
| base PDE 2035 | 5,35 | -0,13 | 9,94 | 1.365 | 2,36 [1,18–3,82] |
| eolica baixa | 6,23 | 0,76 | 11,14 | 1.576 | 2,72 [1,41–4,23] |
| eolica alta | 4,07 | -1,40 | 8,11 | 1.045 | 1,81 [0,83–3,17] |
| sem residuos (perfis suavizados) | 4,86 | -0,61 | 9,28 | 1.284 | 2,21 [1,09–3,64] |
| blocos de 3 dias | 5,48 | 0,01 | 10,09 | 1.390 | 2,40 [1,23–3,91] |
| blocos de 14 dias | 5,45 | -0,02 | 10,17 | 1.387 | 2,40 [1,21–3,90] |
| anos meteorológicos 2010-2025 | 4,96 | -0,51 | 8,46 | 1.294 | 2,22 [1,00–3,42] |

Figura: `reports/figures/mc3_sensibilidades.png`. A referência desta tabela usa 500 sorteios,
por isso difere ligeiramente da tabela 5.1.

## 6. Limitações

- **Sem rede.** Excedente regional não é corte. Não há representação da rede interna do NE, das
  restrições locais nem das restrições externas além dos limites agregados.
- **Despacho hidrotérmico.** A regra emulada não otimiza o sistema; a térmica é histórica. A hidrologia
  do São Francisco é amostrada só em 2022–2025.
- **Data centers.** Carga flat, igual à média anual de 2030. A projeção oficial muda rápido: em 2030 foi
  de 716 → 1.291 → 2.098 MWmed em três revisões de 2025–2026. O inventário não tem MW de vários projetos.
- **Funções de transferência.** Partem da frota atual e do clima ERA5, cuja resolução de 0,25° não
  reproduz o jato noturno; o padrão diário entra pela hora × mês e pelos resíduos. Os resíduos vêm de
  18 meses.
- **Eólica e solar.** O SIGA aberto não traz datas para projetos fora de operação; os cenários eólicos
  são hipóteses de fase. A solar fica fixa.
- **Dados de 2026.** São complementares, e o balanço de jan–mai/2026 tem anomalias.

## 7. Conclusões

1. **Data centers ampliam a importação.** Na projeção oficial vigente (2,1 GWmed no NE em 2030), eles
   aumentam a necessidade de importação do Nordeste em ~2,4 TWh/ano
   e em ~465 horas por ano, com eólica base. O aumento ocorre
   em todos os anos climáticos simulados e não muda o caráter exportador da região (excedente de
   74 TWh/ano).
2. **Compensar no tempo exige mais que compensar em energia.** Cerca de
   4,6 GW eólicos bastam em energia anual, mas são
   necessários ~10,6 GW para neutralizar a
   importação anual. Sem armazenamento ou outra flexibilidade, cobrir a importação noturna e de baixo
   vento só com eólica exige capacidade muito maior que a energia consumida sugere. O custo dessa
   alternativa não foi avaliado.
3. **A carga de data centers absorveria excedente.** Grande parte da energia dos data centers
   (~87%) cairia em horas de excedente regional, o que
   reduz o excedente acima do limite de exportação. Transformar isso em redução de cortes exigiria
   análise de rede.
4. **A incerteza climática e operacional é do mesmo tamanho que as escolhas de cenário.** Por isso os
   resultados devem ser lidos como distribuições condicionais e diferenças pareadas, não como um número
   pontual.

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
  20261112 (Monte Carlo).
- **Execução:** `python -m src.pipeline` refaz tudo a partir de `data/raw`. A coleta dos dados brutos
  está no README.
- **Rastreabilidade:** decisões e hipóteses em `docs/decisoes.md`; estado em `STATUS.md`.
