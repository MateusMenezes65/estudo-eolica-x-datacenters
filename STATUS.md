# STATUS — Estudo Eólica × Data Centers (NE, 2030)

Última atualização: 2026-11-17 (β da regra hidráulica sobre a carga líquida potencial adotado; resultados de 2030 regenerados) · Etapas concluídas: **Dia 1** (dados e auditoria), **Dia 2** (modelos, cenários, simulador determinístico), **Dia 3** (Monte Carlo, sensibilidades e relatório final) e o **simulador interativo** pedido pelo usuário.

**Entregas:**
- [reports/relatorio_final.md](reports/relatorio_final.md): relatório final, gerado por `python -m src.report.final`.
- [reports/relatorio_tecnico.md](reports/relatorio_tecnico.md): relatório técnico passo a passo para o mentor, base recomendada para apresentação, com 31 figuras (18 delas didáticas, de `src/report/figuras_didaticas.py`), gerado por `python -m src.report.tecnico`.
- Versões HTML: `python -m src.report.html --doc final|tecnico`.
- [reports/site/simulador/index.html](reports/site/simulador/index.html): simulador interativo 2026–2030 (página estática), gerado por `python -m src.report.simulador`. Os relatórios ganharam só um anexo com os níveis de 2026–2029; o restante é idêntico.

Os números dos dois relatórios vêm das tabelas do pipeline; valores de análises exploratórias citam a decisão em que estão registrados.

## 1. Como reproduzir

- Ambiente: Python 3.14.1 em `.venv` (`requirements.lock.txt`). Na máquina usada em 2026-11-16 só havia Python 3.13.7: `.venv` criado com ele e as mesmas versões fixadas; testes aprovados e Monte Carlo de 2030 recalculado idêntico ao do estudo.
- `python -m src.pipeline` refaz tudo a partir de `data/raw`, em cerca de 20 min. A coleta dos dados brutos está no README.
- Sementes: 20261111 (modelos) e 20261112 (Monte Carlo).
- Testes: `pytest -q` (41 casos coletados; 39 funções de teste, que é o número citado no relatório técnico).
- Git local com identidade só neste repositório. Nenhum dado é versionado; só código, configuração, manifesto e tabelas de resultado.
- Remoto (2026-11-16, a pedido do usuário): repositório **privado** `github.com/MateusMenezes65/estudo-eolica-x-datacenters`, branch `master`. Colegas entram como colaboradores; instruções de clone no README. `logs/` passou a ser ignorado. `reports/site/` (HTML dos relatórios final e técnico) passou a ser versionado. Os dados seguem fora do Git e foram publicados como anexos da Release `dados-2026-11-16` (zips de `data/raw`, `data/interim` e `data/processed` + SHA256SUMS), gerados e restaurados por `python -m src.tools.pacote_dados empacotar|extrair`.

## 2. O que foi feito

- **Dia 1 — dados.**
  - Coleta com manifesto (URL, SHA-256): ONS, ANEEL, EPE, PLAN, IBGE e ERA5 de 1995–2026.
  - Auditoria em `reports/quality/relatorio_qualidade.md`.
  - Achados: quebra da definição de carga em 29/04/2023 (inclusão da MMGD); corte eólico de 0,6% para 20,2% do potencial; geração de referência ≠ potencial; anomalias no balanço de jan–mai/2026.
- **Dia 2 — modelos e cenários** (`reports/dia2_modelos_cenarios.md`).
  - Backtesting de curto prazo: HGB vence o melhor baseline em 10 a 12 de 12 meses.
  - Funções de transferência clima → sistema.
  - Inventário de data centers e trajetória oficial (2ª RQ do PLAN: 2.098 MWmed no NE em 2030).
  - Simulador determinístico.
  - Classificador de cortes: viável só como uso descritivo.
- **Dia 3 — incerteza.**
  - Clima ponderado com a frota atual fixa (`src/features/clima_historico.py`).
  - Perfis sintéticos de 2030 para 31 anos meteorológicos, com resíduos fora da amostra (`src/sim/sinteticos.py`). Extrapolação desprezível (≤ 0,15% das horas fora da faixa de treino).
  - Monte Carlo (`src/sim/montecarlo.py`): 2.000 sorteios, blocos conjuntos de 7 dias, números aleatórios comuns, regra hidráulica emulada (decisões 34 e 52). Convergência (1.500 → 2.000 sorteios): média ±0,2% e P95 ±0,5%.
  - Sensibilidades com efeito pareado dos data centers; decomposição da variância; limites de importação.
  - Relatório final reprodutível; referências acadêmicas com metadados conferidos.

- **Revisão de verificação (2026-11-15)** — decisões 38–46.
  - Resíduos do Monte Carlo recentrados (não deslocam mais o nível anual); regra hidráulica conserva a energia diária exatamente.
  - Validação retrospectiva nova (`src/sim/backcast.py`): com os níveis observados de 2022–2025, o simulador errava a importação anual de +4% a −30% com a regra emulada e de +35% a −17% com o despacho hidráulico observado (com o β adotado na decisão 52, a regra passa a errar de −20% a +8%).
  - Novas sensibilidades: resíduos sem recentrar (+0,4 TWh) e nível de carga pela API do ONS (+0,3 TWh).
  - Investigados e documentados: diferença de carga API × balanço (decisão 41) e CF solar potencial alto (decisão 43).
  - Relatórios sem literais dependentes de resultado; textos e `config/cenarios_dc.yaml` corrigidos; 29 testes.
  - Comandos: `python -m src.sim.montecarlo --n 2000`; `python -m src.pipeline --desde backcast`; `pytest -q`.

- **Simulador interativo 2026–2030 (2026-11-16)** — decisões 47–51.
  - Níveis por ano (`config/cenarios_anuais.yaml`, `src/sim/trajetorias.py` → `reports/sim/trajetorias_2026_2030.csv`): carga sem DC e MMGD da 2ª RQ do PLAN; solar e eólica do SIGA com a construção entrando de forma uniforme em 2027–2029; eólica alta com a expansão indicativa do PDE no ano; DC pela 2ª RQ do ano. Para 2030 as regras reproduzem o estudo.
  - Monte Carlo por ano (`src/sim/anos.py`): forma de carga no calendário de cada ano; 2028 bissexto (8.784 h, 29/02 = 28/02); 2.000 sorteios; 2030 idêntico ao estudo (diferença 0 em 24.000 linhas).
  - Backtest de 2026 (`src/sim/backtest_2026.py`): ver seção 3.
  - Página (`src/report/simulador.py` + `src/report/simulador_app.html` → `reports/site/simulador/`): barra de anos, M(t) horário (faixa do ano + janela), composição por fonte, mapa de calor dia × hora, meses, distribuição por cenário de DC, trajetória 2026–2030, painel de backtest em 2026, tabela e CSV do sorteio. O motor em JavaScript confere com o Python em 5 casos (diferença relativa ~3e-14). Conferida no navegador: interações, tooltips, 2026 e 2028.
  - Anexo "Níveis de cenário por ano, 2026–2029" nos relatórios final e técnico (`src/report/anexo_anos.py`); HTML dos relatórios regenerado.
  - Comandos: `python -m src.sim.trajetorias`; `python -m src.sim.anos`; `python -m src.sim.backtest_2026`; `python -m src.report.simulador`; também como etapas do `src.pipeline`.

- **Diagnóstico da subestimação (2026-11-17)** — decisões 52–53; relatório técnico, seções 7.2 (perfil horário da hidráulica emulada, nova figura) e 7.5 (backtest de 2026 e diagnóstico, duas figuras novas); sumário e limitações do técnico atualizados. Painel de backtest do simulador com a coluna do coeficiente anterior.
  - Módulo `src/sim/diagnostico_importacao.py` (etapa `diagnostico` do pipeline): beta por ano sobre carga líquida realizada × potencial, validação retrospectiva com os dois, substituição de formas 2022–2026 (modelos sem o próprio ano) e efeito em 2030.
  - `src/sim/backtest_2026.py` compara o beta adotado com o anterior; `src/report/backtest_tecnico.py` gera os trechos do relatório a partir das tabelas.
- **β adotado no caso central (2026-11-17, decisão do usuário; decisão 52).** `montecarlo.beta_regra` estima o coeficiente da regra hidráulica sobre a carga líquida potencial; o anterior virou a sensibilidade "hidraulica: beta anterior (carga liquida realizada)". Pipeline regenerado a partir do Monte Carlo (`python -m src.pipeline --desde montecarlo`): Monte Carlo de 2030, validação retrospectiva, anos 2026–2030, backtest, diagnóstico, relatórios final e técnico (Markdown e HTML) e simulador.

## 3. Resultados principais (2030, eólica base)

Regenerados em 2026-11-17 com o β da regra hidráulica sobre a carga líquida potencial (decisão 52). Entre colchetes, P5–P95; os valores anteriores à correção estão no histórico do Git.

| | Sem DC | DC central (2.098 MWmed) |
|---|---|---|
| Importação média (TWh/ano) | 2,9 [0,8–5,9] | 5,2 [1,9–9,6] |
| Horas com importação | 877 | 1.326 |
| Efeito pareado dos DC | — | +2,3 TWh [1,1–3,7]; +449 h; positivo em 100% dos sorteios |

- **Mudança com a correção do β:** importação central de 5,04 para 5,18 TWh (+3%); efeito dos DC de 2,25 para 2,29 TWh.
- **Compensação eólica do cenário central:** 4,6 GW em energia anual, contra 10,4 GW para neutralizar a importação anual (2,3×).
- **Absorção:** 88% da energia dos data centers cairia em horas de excedente regional (potencial de absorção, não corte evitado).
- **Incerteza:**
  - o ano meteorológico explica 73% da variância da importação anual e o hidrológico, 25%;
  - a amplitude interquartil climática (3,5 TWh) é comparável à amplitude entre os cenários de DC (3,1 TWh).
- **Sensibilidades (efeito na importação):**
  - carga ±5%: −1,0 / +1,2 TWh;
  - hidráulica plana: +2,0 TWh;
  - despacho histórico sem resposta: +0,7 TWh;
  - β anterior da regra (carga já cortada): −0,15 TWh;
  - atraso de 12 meses dos DC: −1,5 TWh;
  - eólica baixa/alta: +0,7 / −1,4 TWh.
- **Efeito dos DC nessas sensibilidades:** sempre positivo, de +1,7 a +2,9 TWh, exceto com o atraso.
- **Confiança:** o nível absoluto carrega erro de dezenas de por cento (validação retrospectiva); o efeito pareado dos DC é o resultado mais robusto.

**Anos intermediários (simulador; não alteram as conclusões).** Importação média, DC central e eólica base: 1,8 (2026), 2,3 (2027), 2,7 (2028), 3,1 (2029) e 5,2 TWh (2030). O salto em 2030 acompanha a carga de DC da 2ª RQ (813 → 2.098 MWmed).

**Backtest de 2026 (jan–out, 6.418 horas válidas; decisão 50).**
- Importação observada: 1,68 TWh. Distribuição ex-ante do cenário de 2026 (clima e hidrologia sorteados): mediana 0,98, P5–P95 0,21–2,90 TWh; o observado fica no percentil 74.
- Com o clima ERA5 e a hidrologia de 2026 (modelos treinados só até 2025): 1,13 TWh com a regra emulada (β adotado), 0,90 TWh com o β anterior e 1,25 TWh com o despacho hidráulico observado (subestima 33%, 47% e 26%). M horário: correlação 0,96, sinal certo em 97% das horas, viés −753 MW.
- O viés de nível empurraria a importação para cima; a subestimação vem da forma horária (regra hidráulica e poucas horas extremas). Confirma a limitação da validação retrospectiva.

**Diagnóstico: esperado ou erro de metodologia? (decisões 52–53)**
- **Erro de método, corrigido (decisão 52, adotada pelo usuário em 2026-11-17).** O β da regra hidráulica era estimado sobre a carga líquida realizada (com corte) e aplicado à potencial. A diferença cresce com o corte: em 2026, 0,37 contra 0,21. Com a correção:
  - o erro retrospectivo cai de −24% para −18% (2024) e de −30% para −20% (2025);
  - B de 2026 sobe de 0,90 para 1,13 TWh;
  - em 2030, a importação central/base passa de 5,04 para 5,18 TWh (+3%) e o efeito dos DC de 2,25 para 2,29 TWh.
- **Limitação sistemática, não corrigida (decisão 53).** A eólica simulada tem poucas horas de pouco vento na frota recente, e os resíduos não corrigem isso em 2024–2026. Mesmo com o β adotado, a importação fica 13% a 45% abaixo da observada nesses anos.
  - Não é erro de código: com as formas observadas, a regra com o β adotado erra só −1% a −7%.
  - Não é acaso de 2026: o sinal se repete em três anos.
  - A importação de 2030 tende a estar subestimada.
- **Esperado:** o ano de 2026 está dentro da faixa ex-ante (percentil 74); cortes de rede em horas de importação não são representados.

## 4. Limitações principais

- Não há representação de rede: excedente ≠ corte; cortes de rede em horas de importação (0,37 TWh em 2025) ficam de fora.
- Erro retrospectivo da importação anual de +8% a −20% (regra emulada com o β adotado). A subestimação dos anos recentes vem sobretudo da forma eólica simulada (decisão 53).
- Picos de importação de 2030 supõem térmica no despacho histórico (sem redespacho): medem exposição, não risco.
- Despacho hidrotérmico por regra emulada, sem otimização.
- Hidrologia amostrada só em 2022–2025.
- Carga de data centers flat; a projeção oficial muda rápido entre revisões (716 → 1.291 → 2.098 MWmed para 2030).
- Funções de transferência baseadas na frota atual; resíduos de 18 meses.
- Cenários eólicos sem datas do SIGA.
- Não há limite de importação documentado.
- Anos 2026–2029: a entrada da capacidade em construção (uniforme em 2027–2029) é hipótese; o SIGA não traz datas previstas.
- Regra hidráulica com β inconsistente (decisão 52) e forma eólica sem as calmarias da frota recente (decisão 53): a importação de 2030 tende a estar subestimada.

## 5. Decisões

Todas registradas em `docs/decisoes.md` (1–53). As do usuário são: L_base = carga líquida da API (Dia 1); data centers pela opção A + C com o cenário alto aceito; base de carga e MMGD pela 2ª RQ do PLAN; eólica alta = 39,4 GW; despacho histórico com hidráulica plana como sensibilidade (determinístico); regra hidráulica emulada no Monte Carlo.

Em 2026-11-15 o usuário manteve o CDV_ACESSOS no cenário alto (decisão 44) e a regra hidráulica emulada como caso central (decisão 45).

Pendências do usuário:
- corrigir ou não a cauda de pouco vento da eólica simulada (decisão 53; por exemplo, quantile mapping do CF ou resíduos condicionados ao nível previsto). Mudaria os resultados de 2030.

Em 2026-11-17 o usuário adotou o β da regra hidráulica sobre a carga líquida potencial no caso central (decisão 52).

Outras pendências, não bloqueantes: A regra de entrada da capacidade em construção nos anos 2026–2029 (uniforme em 2027–2029; decisão 47) foi escolhida por falta de datas no SIGA e pode ser trocada em `config/cenarios_anuais.yaml`.

## 6. Próximos passos possíveis (fora do escopo obrigatório)

- Isolar a causa da falta de calmarias na eólica simulada da frota recente (pesos espaciais, geração potencial em anos de corte alto, indisponibilidades) e testar uma correção (decisão 53).
- Atualizar o backtest de 2026 quando novembro e dezembro estiverem consolidados.

- Representação simplificada da rede do NE ou dos limites por região (Pecém, Parnaíba) para estimar o corte evitado.
- Hidrologia de longo prazo do São Francisco (P2 #13) para ampliar a amostra hidrológica.
- Armazenamento ou flexibilidade como alternativa à expansão eólica para cobrir a importação noturna.
- Atualizar com a nota técnica completa da 2ª RQ e com o 1º PLAN 2027–2031 quando forem publicados.
