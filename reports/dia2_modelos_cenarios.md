# Dia 2 — Modelos, cenários e simulador determinístico (2030)

Data: 2026-11-11. Tabelas de origem em `reports/models/` e `reports/sim/`; configuração em
`config/cenarios.yaml` e `config/cenarios_dc.yaml`. Todos os números de 2030 são **resultados
condicionais a hipóteses de cenário**, não previsões.

## 1. Base analítica

`data/processed/ne_features_h.parquet` (`python -m src.features.build`): carga líquida e bruta e
MMGD (API ONS), geração centralizada do balanço, CF eólico e solar por usina (FC ONS, só usinas
com capacidade > 0), CF **potencial** = (geração + GNRa apurada) / capacidade, clima ERA5
ponderado e calendário.

Diagnóstico do CF eólico potencial: 0,41 (2022) → 0,42 (2024) → 0,48 (2025). Duas causas
identificadas, nenhuma delas inflação da GNRa:
- 2025 foi mais ventoso (vento³ a 100 m 11–17% acima de 2022–24);
- a curva de potência da frota subiu 5–10% nas faixas de vento alto em 2025–26, igualmente
  em horas restritas e não restritas (frota mais nova).

Consequência: perfis de anos antigos subestimam a frota atual. O simulador aplica um fator de
frota por ano climático (seção 4).

## 2. Modelos de curto prazo (validação acadêmica)

Backtesting com origem móvel: 12 dobras mensais de 2025, treino em todo o histórico anterior.
Modelo: HistGradientBoosting com hiperparâmetros fixos e semente 20261111. Lags e médias
móveis usam só dados até a origem t−h. O clima ERA5 no instante-alvo é observado, então os
resultados são **limite superior** frente a uma previsão meteorológica operacional.

| Alvo | h | MAE HGB | Melhor baseline (MAE) | Ganho | Meses em que o HGB vence |
|---|---|---|---|---|---|
| A — carga líquida (MW) | 1 h | 139 | sazonal semanal (468) | 70% | 12/12 |
| A — carga líquida (MW) | 24 h | 299 | sazonal semanal (468) | 36% | 11/12 |
| B — CF eólico potencial | 1 h | 0,015 | persistência 1 h (0,026) | 41% | 12/12 |
| B — CF eólico potencial | 24 h | 0,044 | persistência 24 h (0,082) | 47% | 12/12 |
| C — CF solar observado | 1 h | 0,018 | sazonal diário (0,048) | 62% | 12/12 |
| C — CF solar observado | 24 h | 0,042 | persistência 24 h (0,048) | 13% | 10/12 |

O ganho do modelo de árvores é consistente, salvo a solar a 24 h, que é marginal (10 de 12
meses).

## 3. Funções de transferência clima → sistema (sem lags do alvo)

Servem para gerar perfis horários de anos meteorológicos, incluindo ERA5 1995–2021 no Dia 3.

- **A0 — carga bruta normalizada pelo nível anual**, validada deixando um ano de fora:
  - MAE de 2,6–3,2% com HGB, contra 2,8–3,9% do perfil mês × dia × hora; vence nos 4 anos.
  - A carga *líquida* tem forma instável: a MMGD cresce e cava o meio-dia (MAE de 3,4–9,5%).
  - Decisão: modelar a carga bruta e a MMGD separadamente.
- **B0 — CF eólico potencial**, função do vento a 100 m, vento³, hora, mês e dia do ano:
  - Treino 2022–24, teste 2025: MAE 0,048 contra 0,119 do perfil, mas com viés de −0,033 (frota nova).
  - Treino 2024-07..2025-12, teste 2026: MAE 0,044 e viés de −0,014.
  - Conclusão: usar a frota recente.
- **C0 — CF solar potencial** (corte disponível só desde 2024-04): MAE 0,024–0,027 contra
  0,028–0,035 do perfil mês × hora.

## 4. Simulador determinístico de 2030

`python -m src.sim.deterministico`. Para cada ano climático (2022–2025), cenário de data
centers e cenário eólico, com os mesmos perfis em todos os cenários (comparação pareada):

- L_bruta(t) = forma do ano × 16.340 MWmed (carga global do NE no PDE 2035 referência, Tabela 2-3).
- MMGD(t) = forma do ano × 1.527 MWmed (2025) × 1,507 (crescimento da capacidade de MMGD do
  Brasil no PDE, 2025→2030) ≈ 2,3 GWmed.
- Eólica = fator de frota × CF potencial do ano × capacidade de 2030. Os fatores de frota
  (modelo B0 da frota recente) são 1,05, 1,09, 1,05 e 1,00 para 2022–2025.
- Solar = fator de frota × CF solar × 13,5 GW.
- Hidráulica e térmica: despacho horário observado no ano climático. É hipótese: não há redespacho.
- M(t) = G_centralizada − (L_bruta − MMGD + L_DC); importação = max(0, −M).

Capacidade eólica em 2030 (o SIGA não traz datas para projetos fora de operação):
- **baixa:** 32,3 GW, só as usinas em operação;
- **base:** 34,3 GW, operação + construção;
- **alta:** 39,4 GW, base + 5,1 GW da expansão indicativa do PDE até 2030, alocada toda ao NE.

L_DC em 2030 (MWmed, flat):

| Cenário | L_DC |
|---|---|
| sem_dc | 0 (data centers do PDE embutidos na carga) |
| conservador | 1.886 (contratos assinados, 2ª RQ do PLAN) |
| central | 2.098 (2ª RQ do PLAN) |
| alto | 2.753 (contratos + 100% dos pareceres + 443 MWmed do inventário M3 em rampa) |

### Resultados — eólica base (média e faixa entre os 4 anos climáticos)

| Cenário de DC | Importação (TWh/ano) | Horas com importação | P95 da importação (MW) | Pico (MW) | Excedente (TWh) | Excedente acima de 21 GW (TWh) | Horas com importação > 8 GW |
|---|---|---|---|---|---|---|---|
| sem_dc | 3,1 [2,2–4,7] | 920 [786–1.226] | 2.917 | 10.713 | 87,9 | 3,1 | 63 |
| conservador | 5,2 [4,3–7,4] | 1.382 [1.196–1.697] | 4.803 | 12.599 | 73,5 | 1,9 | 165 |
| central | 5,5 [4,6–7,8] | 1.440 [1.247–1.768] | 5.015 | 12.811 | 71,9 | 1,7 | 176 |
| alto | 6,5 [5,6–9,0] | 1.629 [1.428–1.963] | 5.670 | 13.466 | 67,2 | 1,4 | 221 |

Com eólica baixa, a importação do cenário central é de 6,3 TWh; com eólica alta, 4,1 TWh
(`reports/sim/resumo_cenarios_2030.csv`; figura `reports/figures/s1_importacao_cenarios_2030.png`).

### Compensação eólica (regra 11) — eólica base, média dos anos climáticos

| Cenário de DC | Energia anual | Importação anual igual a sem_dc | Horas de importação iguais | P95 igual | Carga de DC atendível com excedente (%) |
|---|---|---|---|---|---|
| conservador | 4,2 GW | 9,4 GW [8,6–10,4] | 6,8 GW | 8,9 GW | 87% |
| central | 4,7 GW | 10,5 GW [9,7–11,7] | 7,6 GW | 9,9 GW | 87% |
| alto | 6,1 GW | 14,1 GW [12,9–15,8] | 10,1 GW | 13,1 GW | 86% |

Leitura:
- Compensar a importação anual exige cerca de 2,2 vezes a capacidade que compensa a energia anual.
- O motivo é que o vento falta justamente nas horas que importam. Quanto maior a frota, mais
  difícil a compensação temporal: as horas de importação que restam são as de vento fraco.
- Por outro lado, cerca de 87% da energia dos data centers cairia em horas de excedente regional.
  Isso é potencial de absorção, não corte evitado (regra 7).

### Limites de intercâmbio

- **Exportação:** 21 GW a partir de 2030 (PDE, seção 4.3.2). O excedente acima desse limite
  cai de 3,1 TWh (sem_dc) para 1,7 TWh (central), com eólica base.
- **Importação:** sem limite documentado. Reporta-se a sensibilidade em horas acima de 6, 8 e
  10 GW; não é risco de suprimento nem probabilidade de déficit.

## 5. Classificador de cortes (Modelo D)

Rótulo: hora com GNRa eólica no NE acima de 1% da capacidade, por motivo. As features são só
ex-ante, com clima perfeito (limite superior).

| Motivo | Teste | Taxa de eventos | PR-AUC (acaso) | ROC-AUC | Brier (climatologia) |
|---|---|---|---|---|---|
| ENE (energético) | 2025 | 0,25 | 0,77 (0,25) | 0,91 | 0,148 (0,219) |
| ENE (energético) | 2026 | 0,32 | 0,85 (0,32) | 0,93 | 0,145 (0,228) |
| CNF (confiabilidade) | 2025 / 2026 | 0,42 / 0,35 | 0,81 / 0,80 | 0,86 / 0,88 | 0,17 / 0,16 |
| REL (elétrico externo) | 2025 / 2026 | 0,16 / 0,15 | 0,19 / 0,36 | 0,54 / 0,76 | não supera a climatologia em 2025 |
| Total | 2025 / 2026 | 0,69 / 0,67 | 0,97 / 0,98 | 0,93 / 0,95 | 0,11 / 0,09 |

- A discriminação é boa para ENE, CNF e o total. A calibração, porém, não é estável: com treino
  até 2024, o modelo superestima 2025 (probabilidade média prevista de 0,39 contra 0,25
  observada); com treino até 2025, subestima 2026 (0,18 contra 0,32).
- A taxa de horas com corte subiu de 7% (2022) para 69% (2025): há mudança de regime (regra 15).
- Decisão: usar o classificador só de forma descritiva e para ordenar horas. Ele **não** gera
  probabilidades de corte em 2030. REL não é previsível com essas features.

## 6. Limitações principais

- Despacho hidrotérmico histórico, sem redespacho.
- Fatores de frota escalares por ano.
- A carga de data centers é flat, com média anual.
- O PDE pode já conter parte da carga de data centers de Rede Básica (sensibilidade de −258 MWmed).
- Só 4 anos climáticos (o Monte Carlo com ERA5 1995–2021 fica para o Dia 3).
- O excedente não é corte: não há representação da rede interna nem das restrições locais.
- Os dados de 2026 são complementares e há anomalias no balanço de jan–mai/2026.
