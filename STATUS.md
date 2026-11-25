# STATUS — Estudo Eólica × Data Centers (NE, 2030)

Última atualização: 2026-11-25 (auditoria conceitual e estatística; quatro correções de método aplicadas, decisões 54–57; textos da decisão 58 ajustados; resultados de 2030 e relatórios regenerados; publicado no `master` do repositório remoto) · Etapas concluídas: **Dia 1**, **Dia 2**, **Dia 3**, o **simulador interativo** e a **auditoria pré-push**.

**Entregas:**
- [reports/relatorio_final.md](reports/relatorio_final.md): relatório final, gerado por `python -m src.report.final`.
- [reports/relatorio_tecnico.md](reports/relatorio_tecnico.md): relatório técnico passo a passo para o mentor, base recomendada para apresentação, com 34 figuras (18 delas didáticas, de `src/report/figuras_didaticas.py`), gerado por `python -m src.report.tecnico`.
- Versões HTML: `python -m src.report.html --doc final|tecnico`.
- [reports/site/simulador/index.html](reports/site/simulador/index.html): simulador interativo 2026–2030 (página estática), gerado por `python -m src.report.simulador`. Os relatórios ganharam um anexo com os níveis de 2026–2029; o técnico também traz o backtest de 2026 e o diagnóstico da subestimação (seção 7.5), resumidos na seção 4.4 do final.

Os números dos dois relatórios vêm das tabelas do pipeline; valores de análises exploratórias citam a decisão em que estão registrados.

## 1. Como reproduzir

- Ambiente: `.venv` com as versões de `requirements.lock.txt`. A execução original usou Python 3.14.1; na máquina usada desde 2026-11-16 só há Python 3.13.7, e o `.venv` foi criado com ele e as mesmas versões fixadas (testes aprovados; Monte Carlo de 2030 recalculado idêntico ao do estudo).
- `python -m src.pipeline` refaz tudo a partir de `data/raw`, em cerca de 25 min (Monte Carlo de 2030: ~5 min). A coleta dos dados brutos está no README.
- Sementes: 20261111 (modelos) e 20261112 (Monte Carlo).
- Testes: `pytest -q` (56 casos coletados, contando os parametrizados; o relatório técnico cita a contagem do pytest).
- Git local com identidade só neste repositório. Versionados: código, configuração, manifesto, tabelas de resultado, relatórios (Markdown e HTML) e, via Git LFS, a pasta `data/` (item abaixo).
- Remoto (2026-11-16, a pedido do usuário): repositório **privado** `github.com/MateusMenezes65/estudo-eolica-x-datacenters`, branch `master`. Colegas entram como colaboradores; instruções de clone no README. `logs/` passou a ser ignorado. `reports/site/` (HTML dos relatórios final e técnico) passou a ser versionado. Os dados foram publicados como anexos da Release `dados-2026-11-16` (zips de `data/raw`, `data/interim` e `data/processed` + SHA256SUMS; `python -m src.tools.pacote_dados empacotar|extrair`) e, por decisão do usuário, também versionados com **Git LFS** (`.gitattributes`: `data/**`; 484 arquivos em 2026-11-16 e 487 em 2026-11-17, com as bases do simulador e do backtest de 2026; cerca de 1,2 GB; cota gratuita de 10 GiB de armazenamento e 10 GiB de download/mês). Isso altera a regra do AGENTS.md de não versionar bases grandes. Toda nova versão de um arquivo de `data/` consome armazenamento LFS adicional.

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
- **Revisão de coerência dos relatórios (2026-11-17).** Os relatórios regenerados a partir das tabelas atuais só mudavam na data, ou seja, os números já vinham do pipeline atual. Números digitados no código conferidos contra as tabelas; figuras dependentes do β conferidas. Corrigidos e completados:
  - relatório final: limitação da regra hidráulica desatualizada ("estimada sobre a geração já cortada"); limitação da eólica (decisão 53) incluída; backtest de 2026 e diagnóstico resumidos na seção 4.4 (figuras `mc4` e `b26` também no HTML); erro do simulador e conclusão 5 com os valores e o sentido do viés (subestimação), no lugar de "dezenas de por cento";
  - relatório técnico: correlação da regra hidráulica calculada (0,63–0,70; antes "~0,7"), agora gravada em `reports/sim/diag_beta_hidro.csv` por `montecarlo.corr_regra`; tabela do pipeline com as etapas novas; atribuição da subestimação de 2024 atualizada; ressalva sobre a métrica do quintil de menos vento (condicionada ao observado) e P5 como evidência principal; decisão 53 registrada como limitação e nas decisões do usuário; contagem de testes pelo pytest (43, com o teste novo da correlação); ambiente Python e versionamento de `data/` via Git LFS;
  - ambos: versão do Python (3.14.1 na execução original, 3.13.7 desde 2026-11-16).
  - Comandos: `python -m src.pipeline --desde diagnostico`; `pytest -q` (43 aprovados).

- **Auditoria conceitual e estatística pré-push (2026-11-25)** — decisões 54–58.
  - Auditoria feita numa cópia, sem alterar o projeto; depois, por decisão do usuário, aplicadas as quatro correções de método:
    - **54** geração potencial observada com definição única (`src/sim/observado.py`); a validação retrospectiva compara com a importação potencial;
    - **55** features das funções de transferência por ablação fora da amostra (`src/models/ablacao.py`, nova etapa `ablacao`): sai o dia do ano, entram os 16 ventos por polo; RMSE −8,0% (eólica), −5,3% (solar), −3,0% (carga), −2,8% (MMGD);
    - **56** resíduos até out/2026, recentrados por mês (solar e MMGD por mês e hora), MMGD sem distorção nas pontas, validações sem resíduos do próprio ano;
    - **57** coeficiente da regra hidráulica de 2030 = o de 2026 (0,21), com o do próprio ano e a amplitude constante como sensibilidades.
  - Achados só declarados (decisão 58): dependência clima–hidrologia, GNRa não homogênea, perfil da eólica nova, incerteza da amostra de anos, sinal do efeito dos DC por construção.
  - Comandos: `python -m src.features.clima_historico`; `python -m src.models.backtest --so-transferencia`; `python -m src.pipeline --desde ablacao`; `pytest -q` (55 aprovados). Curto prazo (modelos A, B e C) e classificador D não mudaram.
  - Textos da decisão 58 ajustados (2026-11-25): sinal do efeito dos DC como construção, convergência separada da incerteza da amostra de anos (IC95 no pipeline: `python -m src.sim.montecarlo --so-incerteza`), variabilidade entre anos no lugar de "clima pesa tanto quanto o cenário". Testes: 56.
  - Não feito: atualização dos slides (`.pptx`) e da pasta `relatorio_ptc3567/` (ambos fora do Git).

## 3. Resultados principais (2030, eólica base)

Regenerados em 2026-11-25 com as correções das decisões 54–57. Entre colchetes, P5–P95; os valores anteriores estão no histórico do Git.

| | Sem DC | DC central (2.098 MWmed) |
|---|---|---|
| Importação média (TWh/ano) | 3,2 [1,1–6,4] | 5,6 [2,4–10,2] |
| Horas com importação | 918 | 1.372 |
| Efeito pareado dos DC | — | +2,4 TWh [1,3–3,7]; +454 h |

- **Mudança com a auditoria:** importação central de 5,18 para 5,55 TWh (+7%); efeito dos DC de 2,29 para 2,38 TWh. Conclusões mantidas.
- **Compensação eólica do cenário central:** 4,6 GW em energia anual, contra 10,4 GW para neutralizar a importação anual (2,3×).
- **Absorção:** 87% da energia dos data centers cairia em horas de excedente regional (potencial de absorção, não corte evitado).
- **Incerteza:**
  - IC95 da média pela amostra de anos (31 climas × 4 hidrologias): importação central 4,5–6,8 TWh; efeito dos DC 2,0–2,8 TWh; erro-padrão de 0,59 TWh, contra 0,05 de simulação;
  - entre sorteios, o ano meteorológico explica 80% da variância da importação anual e o hidrológico, 19%;
  - as distribuições dos cenários de DC se sobrepõem (P5–P95 do central: 2,4–10,2 TWh); o efeito é medido pela diferença pareada.
- **Tamanho do efeito:** a importação cresce 13% da energia dos DC no cenário central. O sinal positivo é por construção.
- **Sensibilidades (efeito na importação):**
  - carga ±5%: −1,1 / +1,3 TWh;
  - hidráulica plana: +1,9 TWh; despacho histórico sem resposta: +0,6 TWh;
  - beta do próprio ano hidrológico: −0,2 TWh; amplitude constante em MW: +0,5 TWh;
  - atraso de 12 meses dos DC: −1,6 TWh;
  - eólica baixa/alta: +0,8 / −1,4 TWh.
- **Efeito dos DC nessas sensibilidades:** de +1,8 a +2,9 TWh, exceto com o atraso.
- **Confiança no nível:**
  - validação retrospectiva 2022–2025 (níveis observados, funções treinadas também nesses anos): −11% a +1%;
  - fora da amostra (funções re-treinadas sem o próprio ano, resíduos de outros anos): −2% (2022), −8%, −2%, −15% (2025), −27% (2026);
  - o nível de 2030 tende a estar subestimado. O efeito pareado dos DC é o resultado mais robusto.

**Anos intermediários (simulador; não alteram as conclusões).** Importação média, DC central e eólica base: 2,0 (2026), 2,5 (2027), 3,0 (2028), 3,4 (2029) e 5,6 TWh (2030). O salto em 2030 acompanha a carga de DC da 2ª RQ (813 → 2.098 MWmed).

**Backtest de 2026 (jan–out, 6.418 horas válidas; decisão 50).**
- Importação potencial observada: 1,67 TWh (realizada 1,68). Com clima e hidrologia sorteados: mediana 1,17, P5–P95 0,34–2,88 TWh; percentil 72. Não é ex-ante: modelos, resíduos e coeficiente usam dados até out/2026.
- Com o clima ERA5 e a hidrologia de 2026 (modelos só até 2025, resíduos só de 2024–2025): 1,40 TWh com a regra (−16%) e 1,52 TWh com o despacho hidráulico observado. Antes da auditoria: 1,13 TWh (−33%). Parte do acerto vem do viés de nível (M médio −744 MW); com os níveis observados o erro é −27%.

**Diagnóstico (decisões 52–57).**
- Com as formas observadas, a regra hidráulica erra −7% a 0% em 2024–2026.
- A limitação da decisão 53 (poucas calmarias) não se confirma: P5 horário da eólica simulada entre −480 e +111 MW do observado.
- O erro que resta não vem de uma parcela só (eólica, carga, solar e MMGD); cresce em 2025–2026.

## 4. Limitações principais

- Não há representação de rede: excedente ≠ corte. Cortes em horas de importação pesam pouco (0,07 TWh de importação em 2025).
- Erro fora da amostra da importação anual de −27% a −2%, pior nos anos recentes; nível de 2030 tende a estar subestimado.
- Picos de importação de 2030 supõem térmica no despacho histórico (sem redespacho): medem exposição, não risco.
- Despacho hidrotérmico por regra emulada, sem otimização; o coeficiente depende do regime e o adotado vem de jan–out/2026.
- Hidrologia amostrada só em 2022–2025 e independente do clima (correlação de −0,86 nos quatro anos comuns, decisão 58).
- A amostra real é de 31 climas × 4 hidrologias: 2.000 sorteios não reduzem essa incerteza.
- Carga de data centers flat; a projeção oficial muda rápido entre revisões (716 → 1.291 → 2.098 MWmed para 2030).
- Funções de transferência baseadas na frota atual; resíduos de 28 meses; features escolhidas nas mesmas dobras em que o erro foi medido.
- CF eólico potencial depende da GNRa, cuja referência mudou entre 2022 e 2026 (decisão 58).
- A eólica adicional da compensação tem o mesmo perfil da frota.
- Cenários eólicos sem datas do SIGA. Não há limite de importação documentado.
- Anos 2026–2029: a entrada da capacidade em construção (uniforme em 2027–2029) é hipótese; o SIGA não traz datas previstas.

## 5. Decisões

Todas registradas em `docs/decisoes.md` (1–58). As do usuário são: L_base = carga líquida da API (Dia 1); data centers pela opção A + C com o cenário alto aceito; base de carga e MMGD pela 2ª RQ do PLAN; eólica alta = 39,4 GW; despacho histórico com hidráulica plana como sensibilidade (determinístico); regra hidráulica emulada no Monte Carlo.

Em 2026-11-15 o usuário manteve o CDV_ACESSOS no cenário alto (decisão 44) e a regra hidráulica emulada como caso central (decisão 45). Em 2026-11-17 adotou o β sobre a carga líquida potencial (decisão 52) e adiou a cauda de pouco vento (decisão 53, agora revista). Em 2026-11-25 decidiu aplicar as quatro correções de método da auditoria (decisões 54–57).

Pendências do usuário:
- atualizar os slides (`Eólica × Data Centers no Nordeste até 2030 - v3.pptx`, fora do Git): números de 2030, slide 13 (features), slides 19–28, curtose sem origem no repositório. O `relatorio_ptc3567/` (LaTeX, fora do Git) não cita resultados de 2030 até agora.

Outra pendência, não bloqueante: a regra de entrada da capacidade em construção nos anos 2026–2029 (decisão 47) pode ser trocada em `config/cenarios_anuais.yaml`.

## 6. Próximos passos possíveis (fora do escopo obrigatório)

- Resíduos condicionados ao CF previsto, para reproduzir a coincidência entre calmaria e carga alta (erro que resta em 2025–2026).
- Hidrologia de longo prazo do São Francisco (P2 #13): amplia a amostra e permite estimar a dependência com o vento.
- Atualizar o backtest de 2026 e o coeficiente da regra quando novembro e dezembro estiverem consolidados.
- Representação simplificada da rede do NE ou dos limites por região (Pecém, Parnaíba) para estimar o corte evitado.
- Armazenamento ou flexibilidade como alternativa à expansão eólica para cobrir a importação noturna.
- Atualizar com a nota técnica completa da 2ª RQ e com o 1º PLAN 2027–2031 quando forem publicados.
