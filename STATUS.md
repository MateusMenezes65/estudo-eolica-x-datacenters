# STATUS — Estudo Eólica × Data Centers (NE, 2030)

Última atualização: 2026-11-15 (revisão de verificação) · Etapas concluídas: **Dia 1** (dados e auditoria), **Dia 2** (modelos, cenários, simulador determinístico), **Dia 3** (Monte Carlo, sensibilidades e relatório final).

**Entregas:**
- [reports/relatorio_final.md](reports/relatorio_final.md): relatório final, gerado por `python -m src.report.final`.
- [reports/relatorio_tecnico.md](reports/relatorio_tecnico.md): relatório técnico passo a passo para o mentor, base recomendada para apresentação, com 31 figuras (18 delas didáticas, de `src/report/figuras_didaticas.py`), gerado por `python -m src.report.tecnico`.
- Versões HTML: `python -m src.report.html --doc final|tecnico`.

Os números dos dois relatórios vêm das tabelas do pipeline; valores de análises exploratórias citam a decisão em que estão registrados.

## 1. Como reproduzir

- Ambiente: Python 3.14.1 em `.venv` (`requirements.lock.txt`).
- `python -m src.pipeline` refaz tudo a partir de `data/raw`, em cerca de 20 min. A coleta dos dados brutos está no README.
- Sementes: 20261111 (modelos) e 20261112 (Monte Carlo).
- Testes: `pytest -q`.
- Git local com identidade só neste repositório. Nenhum dado é versionado; só código, configuração, manifesto e tabelas de resultado.

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
  - Monte Carlo (`src/sim/montecarlo.py`): 2.000 sorteios, blocos conjuntos de 7 dias, números aleatórios comuns, regra hidráulica emulada (decisão 34). Convergência: média ±0,3% e P95 ±0,2%.
  - Sensibilidades com efeito pareado dos data centers; decomposição da variância; limites de importação.
  - Relatório final reprodutível; referências acadêmicas com metadados conferidos.

- **Revisão de verificação (2026-11-15)** — decisões 38–46.
  - Resíduos do Monte Carlo recentrados (não deslocam mais o nível anual); regra hidráulica conserva a energia diária exatamente.
  - Validação retrospectiva nova (`src/sim/backcast.py`): com os níveis observados de 2022–2025, o simulador erra a importação anual de +4% a −30% com a regra emulada e de +35% a −17% com o despacho hidráulico observado.
  - Novas sensibilidades: resíduos sem recentrar (+0,4 TWh) e nível de carga pela API do ONS (+0,3 TWh).
  - Investigados e documentados: diferença de carga API × balanço (decisão 41) e CF solar potencial alto (decisão 43).
  - Relatórios sem literais dependentes de resultado; textos e `config/cenarios_dc.yaml` corrigidos; 29 testes.
  - Comandos: `python -m src.sim.montecarlo --n 2000`; `python -m src.pipeline --desde backcast`; `pytest -q`.

## 3. Resultados principais (2030, eólica base)

| | Sem DC | DC central (2.098 MWmed) |
|---|---|---|
| Importação média (TWh/ano) | 2,8 [0,8–5,8] | 5,0 [1,8–9,4] |
| Horas com importação | 860 | 1.309 |
| Efeito pareado dos DC | — | +2,3 TWh [1,0–3,7]; +448 h; positivo em 100% dos sorteios |

- **Compensação eólica do cenário central:** 4,6 GW em energia anual, contra 10,5 GW para neutralizar a importação anual (2,3×).
- **Absorção:** 88% da energia dos data centers cairia em horas de excedente regional (potencial de absorção, não corte evitado).
- **Incerteza:**
  - o ano meteorológico explica 77% da variância da importação anual e o hidrológico, 21%;
  - a amplitude interquartil climática (3,4 TWh) é comparável à amplitude entre os cenários de DC (3,1 TWh).
- **Sensibilidades (efeito na importação):**
  - carga ±5%: −1,0 / +1,2 TWh;
  - hidráulica plana: +2,1 TWh;
  - despacho histórico sem resposta: +0,9 TWh;
  - atraso de 12 meses dos DC: −1,5 TWh;
  - eólica baixa/alta: +0,7 / −1,3 TWh.
- **Efeito dos DC nessas sensibilidades:** sempre positivo, de +1,7 a +2,8 TWh, exceto com o atraso.
- **Confiança:** o nível absoluto carrega erro de dezenas de por cento (validação retrospectiva); o efeito pareado dos DC é o resultado mais robusto.

## 4. Limitações principais

- Não há representação de rede: excedente ≠ corte; cortes de rede em horas de importação (0,37 TWh em 2025) ficam de fora.
- Erro retrospectivo da importação anual de +7% a −30% (regra emulada); a subestimação de 2024 não tem origem identificada.
- Picos de importação de 2030 supõem térmica no despacho histórico (sem redespacho): medem exposição, não risco.
- Despacho hidrotérmico por regra emulada, sem otimização.
- Hidrologia amostrada só em 2022–2025.
- Carga de data centers flat; a projeção oficial muda rápido entre revisões (716 → 1.291 → 2.098 MWmed para 2030).
- Funções de transferência baseadas na frota atual; resíduos de 18 meses.
- Cenários eólicos sem datas do SIGA.
- Não há limite de importação documentado.

## 5. Decisões

Todas registradas em `docs/decisoes.md` (1–46). As do usuário são: L_base = carga líquida da API (Dia 1); data centers pela opção A + C com o cenário alto aceito; base de carga e MMGD pela 2ª RQ do PLAN; eólica alta = 39,4 GW; despacho histórico com hidráulica plana como sensibilidade (determinístico); regra hidráulica emulada no Monte Carlo.

Pendências do usuário:
- **Decisão 44:** manter ou retirar o CDV_ACESSOS do cenário alto (possível dupla contagem de 266 MWmed com os pareceres da 2ª RQ).
- **Decisão 45:** manter a regra hidráulica emulada como caso central ou adotar outra convenção, à luz da validação retrospectiva.

## 6. Próximos passos possíveis (fora do escopo obrigatório)

- Investigar a subestimação da importação de 2024 na validação retrospectiva (formas horárias do vento ou da hidráulica).

- Representação simplificada da rede do NE ou dos limites por região (Pecém, Parnaíba) para estimar o corte evitado.
- Hidrologia de longo prazo do São Francisco (P2 #13) para ampliar a amostra hidrológica.
- Armazenamento ou flexibilidade como alternativa à expansão eólica para cobrir a importação noturna.
- Atualizar com a nota técnica completa da 2ª RQ e com o 1º PLAN 2027–2031 quando forem publicados.
