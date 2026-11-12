# STATUS — Estudo Eólica × Data Centers (NE, 2030)

Última atualização: 2026-11-12 (revisão de hipóteses) · Etapas concluídas: **Dia 1** (ambiente, coleta, auditoria) e **Dia 2** (modelos, cenários, simulador determinístico) · Próxima: **Dia 3 — incerteza (Monte Carlo), sensibilidades e relatório final**.

## 1. Ambiente e repositório

- Windows 11; Git 2.56; Python 3.14.1 em `.venv` (o alias da Microsoft Store existe, mas não é usado). Dependências em `requirements.txt` / `requirements.lock.txt`.
- Git local com identidade configurada só neste repositório (MateusMenezes65). Histórico em `git log`. Nenhum dado bruto, intermediário ou processado é versionado.
- `AGENTS.md` e o plano orientador estão preservados. Onde divergem, vale o AGENTS.md (horizonte 2030).
- Comandos reproduzíveis: README (Dia 1 e Dia 2).
- Testes: `pytest -q` → **23 aprovados**:
  - fuso horário, agregação 30 min → hora, MW×h = MWh, cardinalidade da junção;
  - fechamento do balanço, quebra da MMGD, identidade carga global = líquida + MMGD;
  - extração do PDE e trajetória oficial de data centers;
  - cenários-limite do simulador: carga de data centers zero reproduz o caso-base; mais carga não reduz a importação; a compensação devolve a importação ao caso-base.

## 2. Dados (Dia 1)

- **Manifesto:** 451 registros em `docs/manifest/manifest.csv`, com URL, tamanho, SHA-256 e data de coleta; sem pendências em `python -m src.collect.manifest`.
- **ONS, histórico de 2022-01 até nov/2026:** balanço, intercâmbio, carga verificada pela API (separa a MMGD), geração e fator de capacidade por usina, constrained-off eólico e solar (solar só desde 2024-04), capacidade.
- **ANEEL:** SIGA e MMGD.
- **EPE:** PDE 2035, relatório e planilhas.
- **ONS/EPE/CCEE:** notas de previsão de carga do PLAN 2026–2030 e slides da 2ª Revisão Quadrimestral.
- **Clima:** ERA5 via Open-Meteo em 34 pontos, para 2022–2026 e **1995–2021** (102 blocos, completo).
- **Outros:** IBGE (população) e calendário do NE.
- **Base integrada:** `data/interim/ne_hourly.parquet`.
- **Base analítica:** `data/processed/ne_features_h.parquet`.
- **Auditoria:** `reports/quality/relatorio_qualidade.md`.

Principais achados do Dia 1:
- Em 29/04/2023 o balanço ONS passou a incluir a MMGD na carga e na solar.
- O corte eólico apurado subiu de 0,6% (2022) para 20,2% (2025) do potencial.
- O balanço de jan–mai/2026 não fecha em 878 horas.
- A geração de referência do constrained-off não equivale ao potencial.
- O ERA5 não reproduz o jato noturno.

## 3. Dia 2 — executado

Relatório: `reports/dia2_modelos_cenarios.md`.

- **PDE 2035** (`config/pde2035_extraido.csv`, 213 valores, cada um com fonte):
  - carga do NE, referência: 16.340 MWmed em 2030 (agora só como sensibilidade);
  - MMGD do Brasil: 40,0 → 60,3 GW;
  - expansão indicativa de eólica no SIN: +5,1 GW até 2030;
  - exportação do NE limitada a 21 GW a partir de 2030; nenhum limite de importação documentado.
- **Data centers:**
  - trajetória oficial da 2ª RQ do PLAN 2026–2030: 2.098 MWmed no NE em 2030;
  - inventário de 17 projetos (`config/data_centers_ne.csv`);
  - cenários em `config/cenarios_dc.yaml`: sem_dc 0, conservador 1.886, central 2.098, alto 2.753 MWmed.
- **Cenários do balanço** (`config/cenarios.yaml`), revisados com o usuário em 2026-11-12:
  - carga base sem data centers = 16.180 MWmed e MMGD = 2.386 MWmed, ambos da 2ª RQ do PLAN 2026–2030 (`config/plan_2rq_ne.csv`); assim não há dupla contagem com os cenários de data centers;
  - eólica baixa / base / alta = 32,3 / 34,3 / 39,4 GW;
  - solar 13,5 GW;
  - despacho hidrotérmico histórico, com hidráulica plana como sensibilidade.
- **Modelos** (`src/models/backtest.py`), com HGB contra baselines em 12 dobras mensais de 2025:

| Alvo | Ganho de MAE em 1 h | Ganho de MAE em 24 h |
|---|---|---|
| Carga líquida | 70% | 36% |
| CF eólico potencial | 41% | 47% |
| CF solar | 62% | 13% |

  O HGB vence em 10 a 12 dos 12 meses. O clima perfeito torna esses ganhos um limite superior.
- **Funções de transferência clima → sistema:**
  - carga bruta: MAE de 2,6–3,2% deixando um ano de fora;
  - CF eólico potencial: MAE de 0,044 com a frota recente;
  - CF solar potencial: MAE de 0,024–0,027.
- **CF eólico potencial em 2025 (0,48):** explicado por vento mais forte e frota mais nova. O simulador corrige o nível de cada ano climático com um fator de frota.
- **Simulador determinístico** (`src/sim/deterministico.py`), eólica base, média dos anos climáticos 2022–2025:
  - importação: sem_dc 2,9 TWh e 883 h → central 5,3 TWh e 1.388 h → alto 6,3 TWh e 1.570 h;
  - eólica que compensa o cenário central: 4,7 GW pelo critério de energia anual, mas 10,6 GW para manter a importação anual (regra 11);
  - sensibilidades no caso central: carga ±5% leva a importação a 4,2–6,5 TWh; hidráulica plana, a 6,8 TWh; base do PDE, a 5,2 TWh; a faixa de MMGD, a 5,2–5,4 TWh;
  - cerca de 87% da energia dos data centers cairia em horas de excedente regional (potencial de absorção, não corte evitado).
- **Classificador de cortes:** discrimina bem os motivos ENE e CNF e o total (ROC-AUC de 0,86 a 0,95), mas a calibração é instável por mudança de regime. Fica só como uso descritivo; REL não é previsível.

## 4. Limitações e lacunas abertas

- Despacho hidrotérmico histórico, sem redespacho. Fatores de frota escalares. Carga de data centers flat. Só 4 anos climáticos no determinístico.
- A carga base vem do PLAN (sem data centers); o PDE entra só como sensibilidade.
- Inventário sem MW para ExportData, Tecto Pecém e DC Xingó. Nota técnica completa da 2ª RQ não localizada.
- P2 não coletados: ENSO, hidrologia do São Francisco, IBC-Br e limites documentais de importação.
- Os dados de 2026 são complementares e há anomalias no balanço de jan–mai/2026.

## 5. Decisões pendentes do usuário

Nenhuma. Revisão de hipóteses concluída em 2026-11-12 (decisões 29–31): base de carga e MMGD pela 2ª RQ do PLAN; eólica alta mantida em 39,4 GW; despacho hidrotérmico histórico com hidráulica plana como sensibilidade.

## 6. Próxima tarefa (Dia 3)

1. Gerar perfis sintéticos de 1995–2021 com as funções de transferência. Os pesos dos pontos eólicos e solares devem ser fixados na frota atual. Validar a extrapolação nos anos fora do treino.
2. Monte Carlo por anos climáticos inteiros e/ou blocos, com sementes fixas e os mesmos sorteios em todos os cenários; aumentar o número de sorteios até as métricas estabilizarem.
3. Sensibilidades: nível da carga, MMGD, utilização e rampa dos data centers, base do PDE, capacidade eólica, limites de importação e hidráulica plana. As univariadas já existem no determinístico; no Dia 3, levá-las ao Monte Carlo.
4. Diferenças pareadas entre cenários, separando incerteza amostral de escolha de cenário.
5. Relatório final reproduzível.
