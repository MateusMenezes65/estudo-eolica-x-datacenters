# STATUS — Estudo Eólica × Data Centers (NE, 2030)

Última atualização: 2026-11-11 · Etapa concluída: **Dia 1 — ambiente, coleta e auditoria** · Próxima: **Dia 2 — modelos e cenários** (nenhum modelo treinado ainda).

## 1. Executado

- **Ambiente**: Windows 11; Git 2.56; Python 3.14.1 real (alias da Microsoft Store também existe em `WindowsApps`, não usado); `.venv` criado no projeto; dependências fixadas em `requirements.txt` / `requirements.lock.txt`; 125 GB livres.
- **Git**: repositório local; identidade configurada só neste repositório (MateusMenezes65). Histórico em `git log`.
- **Estrutura**: `config/ src/ tests/ docs/ reports/ data/{raw,interim,processed}`, `.gitignore`, README, `docs/decisoes.md`.
- **Arquivos originais**: `AGENTS.md` e `docs/Plano_Orientador_...docx` preservados. Onde divergem, vale o AGENTS.md (horizonte 2030; o plano fala em 2035).
- **Coleta** (346 registros no manifesto `docs/manifest/manifest.csv`, com URL, tamanho, SHA-256, data de coleta; checagem `python -m src.collect.manifest` sem pendências):

| # | Fonte | Período | Volume |
|---|---|---|---|
| 1 | ONS balanço, intercâmbio, curva de carga (horário) | 2022-01 → 2026-11-09 | 18 MB |
| 1 | ONS carga verificada semi-horária (API; separa MMGD) | 2022-01 → 2026-11-11 | 3 MB |
| 2 | ONS geração por usina e fator de capacidade por usina (horário) | 2022-01 → 2026-11 | 442 MB |
| 3 | ONS constrained-off eólico (2022-01+) e solar (só existe desde 2024-04) | → 2026-11 | 229 MB |
| 4 | ONS capacidade instalada; ANEEL SIGA (fotografia 2026-11-01) | snapshot | 9 MB |
| 5 | ANEEL MMGD (fotografia 2026-11-10) | snapshot | 108 MB |
| 6 | Calendário NE (`config/calendario_ne.csv`, biblioteca holidays) | 2015–2030 | — |
| 7–9 | Open-Meteo ERA5: 8 capitais, 16 pontos eólicos, 10 solares | 2022-01-01 → 2026-11-03 (UTC) | 9 MB |
| 10 | EPE PDE 2035: relatório final, cadernos de demanda, transmissão, MMGD, planilhas | publicação 2026-11-05 | 49 MB |
| — | IBGE Censo 2022 (população por UF, pesos de temperatura) | 2022 | <1 MB |

- **Integração**: `data/interim/ne_hourly.parquet` (42 624 horas × 59 colunas) + bases por usina (FC, constrained-off) e clima por ponto.
- **Auditoria**: `reports/quality/relatorio_qualidade.md`, tabelas em `reports/tables/`, figuras `reports/figures/q1…q6`.
- **Testes**: `pytest -q` → 13 aprovados (tempo/fuso, 30 min→hora, MW×h=MWh, parsing, seleção de arquivos, calendário, unicidade horária, fechamento do balanço 2022–2025, quebra MMGD, identidade carga global = líquida + MMGD, cardinalidade da junção, CF agregado em [0,1]).

Comandos: ver README (seção "Pipeline reproduzível").

## 2. Cobertura e principais números (2022–2025, anos completos)

- Cobertura horária completa, sem duplicatas nem lacunas internas, em todas as bases centrais. Constrained-off solar só desde 2024-04; MMGD em "geração por usina" só desde 2023-04-29.
- Carga líquida de MMGD (API): 11,1 → 12,1 GWmed (2022 → 2025); MMGD estimada: 0,4 → 1,5 GWmed.
- Capacidade eólica NE (FC ONS): 19,6 → 30,6 GW médios (2022 → 2025); SIGA: 32,3 GW em operação, 2,0 GW em construção, 11,3 GW não iniciados; solar 12,3 / 1,2 / 44,9 GW.
- NE exportador líquido: exportação 34 → 56 TWh/ano; importação 1,5–3,3 TWh/ano; 7–14 % das horas com importação; pico de importação ≈ 7,1–7,9 GW.
- **Constrained-off eólico apurado (GNRa)**: 0,6 % (2022) → 3,9 % → 9,1 % → **20,2 % (2025)** do potencial; solar 16,7 % (2024-04+) → 25,6 % (2025). Em 2025 o corte energético (ENE) superou o de confiabilidade (CNF).

## 3. Problemas encontrados e tratamento

1. **Quebra de definição da carga no balanço ONS em 2023-04-29**: carga e solar passam a incluir a MMGD estimada (degrau ~0,5 GW). Sem correção da série bruta; adotada a carga líquida de MMGD da API como L_base (decisão 13).
2. **Duas estimativas de MMGD do ONS** (API vs. geração por usina) diferem em 30–370 MWmed por trimestre.
3. **Balanço 2026-01 a 2026-05 inconsistente**: 878 horas sem fechamento (até −17,5 GW) e eólica do balanço muito abaixo da soma das usinas. Marcado; 2026 é só complementar.
4. **Geração de referência do constrained-off ≠ potencial**: menor que a geração em 45 % das horas-usina eólicas. Corte medido pela GNRa (regra 4).
5. **Mudança de regime dos cortes**: correlação vento³ × CF observado cai de 0,87 (2022) para 0,58 (2025), mas vento³ × CF potencial (geração + GNRa) fica em 0,85–0,89. O alvo do modelo B deve ser o potencial, e o classificador de cortes (D) precisa considerar quebra de regime 2024–2025 (regra 15).
6. **ERA5 não reproduz o jato noturno**: o CF eólico tem pico noturno forte (0,46 vs. 0,26 ao meio-dia), mas o vento ERA5 a 100 m quase não tem ciclo diário. O modelo B precisará de interação hora × mês.
7. FC por usina: horas com capacidade 0 ou geração > capacidade (registro defasado; ~0,3 TWh em ~450 TWh). Não recortado.
8. MMGD ANEEL sem data de conexão (só a última atualização cadastral); contém dados pessoais tarjados — usar apenas agregados; não versionar.
9. Intercâmbio nacional: os pares de subsistemas trocam de sentido entre anos (N→NE e NE→N); reconcilia exatamente com o balanço quando somado com sinal.
10. Curva de carga ONS = carga do balanço (redundante; mantida só como conferência).

Correções feitas no código: leitura de `val_*` gravados como texto em alguns anos; fallback para CSV (intercâmbio 2022); codificação UTF-8 do SIGA; trava de escrita no manifesto (coletores paralelos).

## 4. Lacunas

- **#11 Inventário de data centers — feito (v0.2, 2026-11-11)**:
  - Projeção oficial (PLAN 2026-2030, ONS/EPE/CCEE), carga de DC na Rede Básica do NE em MWmed: 2ª Revisão Quadrimestral 112 → 333 → 628 → 813 → **2.098** (2026→2030), dos quais 1.886 de contratos assinados; 1ª RQ 1.291 e PLAN 716 em 2030 (`config/dc_trajetoria_oficial_ne.csv`).
  - Inventário de 17 itens com fonte, data, definição da potência, maturidade M0–M3 e grupo de deduplicação (`config/data_centers_ne.csv`). Principal: Pecém fase 1 (Omnia/ByteDance), 200 MW de TI e cerca de 300 MW de consumo, operação a partir do 3T2027; Renova Satoshi (BA) já consome cerca de 80 MW médios em 2026, junto a eólica.
  - Nenhum documento oficial público traz MW por projeto (planilha do MME sem MW; MUST tarjado na carta do ONS). 7 itens foram conferidos diretamente; os demais vêm do relatório dos agentes de pesquisa ou só da busca, e estão marcados assim.
  - Lacunas: MW da ExportData (4 DCs), Tecto Pecém, DC Xingó; nota técnica completa da 2ª RQ; tipo de carga de vários pedidos na BA (Satoshi II–IV, SNRA).
- **#10 PDE 2035**: carga extraída (`config/pde2035_extraido.csv`, `src/collect/pde_extract.py`): NE referência 13 684 → 16 340 → 19 610 MWmed (2025/2030/2035); inferior e superior só para 2025 e 2035 (NE 2035: 18,1 e 28,7 GWmed). **Não há trajetória de data centers por subsistema**: o PDE só publica "cargas especiais" no Brasil em 2035 (VE + DC + H2: 9,5 / 11,7 / 131,1 TWh) e os pedidos de conexão de DC no MME (Brasil: 17,4 GW até 2030). Ainda faltam a expansão da geração e os limites de intercâmbio.
- **P2 não coletados**: ENSO/ONI (#12), hidrologia do São Francisco (#13; 74 MB disponíveis no ONS), IBC-Br (#14), limites de intercâmbio documentais (#15).
- Feriados municipais não incluídos.
- ERA5 1995–2021 (34 pontos, blocos de 9 anos, `data/raw/openmeteo/hist/`): download em andamento em 2026-11-11; retomável com `python -m src.collect.openmeteo --start 1995-01-01 --end 2021-12-31 --chunk-years 9`.

## 5. Decisões pendentes do usuário

1. ~~Identidade Git~~ — configurada em 2026-11-11.
2. ~~Definição de L_base~~ — **decidido em 2026-11-11**: carga líquida de MMGD da API (`val_cargaglobalsmmgd`) como L_base; MMGD (`val_cargammgd`) como geração distribuída separada (decisão 13).
3. **Data centers** — decidido: A + C. Caso-base = PDE referência (L_DC = 0); cenários de DC: conservador = contratos assinados da 2ª RQ (1.886 MWmed em 2030); central = 2ª RQ completa (2.098 MWmed). Alto = contratos + 100% dos pareceres + projetos M3 com MW publicado (CDV_ACESSOS 645, QAIR2 415, ENEGIX 100 MW, com utilização e rampa), ≈ 2,3 GWmed + inventário — aceito em 2026-11-11. Possível dupla contagem com o PDE: sensibilidade de −258 MWmed.
4. ~~ERA5 1995–2021~~ — autorizado e em download.

## 6. Próxima tarefa

Dia 2: (a) extrair do PDE 2035 a expansão da geração e os limites de intercâmbio até 2030 (carga do NE já extraída); (c) definir alvos e features (A: carga líquida; B: CF potencial eólico; C: solar como perfil ou modelo), com baseline sazonal e backtesting temporal; (d) configurar os cenários em YAML; (e) construir o simulador determinístico.
