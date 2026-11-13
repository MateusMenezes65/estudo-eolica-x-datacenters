# STATUS — Estudo Eólica × Data Centers (NE, 2030)

Última atualização: 2026-11-12 · Etapas concluídas: **Dia 1** (dados e auditoria), **Dia 2** (modelos, cenários, simulador determinístico), **Dia 3** (Monte Carlo, sensibilidades e relatório final).

**Entregas:**
- [reports/relatorio_final.md](reports/relatorio_final.md): relatório final, gerado por `python -m src.report.final`.
- [reports/relatorio_tecnico.md](reports/relatorio_tecnico.md): relatório técnico passo a passo para o mentor, com 30 figuras (18 delas didáticas, de `src/report/figuras_didaticas.py`), gerado por `python -m src.report.tecnico`.
- Versões HTML: `python -m src.report.html --doc final|tecnico`.

Todos os números dos dois relatórios vêm das tabelas do pipeline.

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
  - Monte Carlo (`src/sim/montecarlo.py`): 2.000 sorteios, blocos conjuntos de 7 dias, números aleatórios comuns, regra hidráulica emulada (decisão 34). Convergência: média ±0,3% e P95 ±0,5%.
  - Sensibilidades com efeito pareado dos data centers; decomposição da variância; limites de importação.
  - Relatório final reprodutível; referências acadêmicas com metadados conferidos.

## 3. Resultados principais (2030, eólica base)

| | Sem DC | DC central (2.098 MWmed) |
|---|---|---|
| Importação média (TWh/ano) | 3,0 [0,9–6,2] | 5,4 [2,0–9,9] |
| Horas com importação | 909 | 1.374 |
| Efeito pareado dos DC | — | +2,4 TWh [1,1–3,8]; +465 h; positivo em 100% dos sorteios |

- **Compensação eólica do cenário central:** 4,6 GW em energia anual, contra 10,6 GW para neutralizar a importação anual (2,3×).
- **Absorção:** 87% da energia dos data centers cairia em horas de excedente regional (potencial de absorção, não corte evitado).
- **Incerteza:**
  - o ano meteorológico explica 77% da variância da importação anual e o hidrológico, 21%;
  - a amplitude interquartil climática (3,5 TWh) é comparável à amplitude entre os cenários de DC (3,2 TWh).
- **Sensibilidades (efeito na importação):**
  - carga ±5%: −1,1 / +1,3 TWh;
  - hidráulica plana: +2,2 TWh;
  - despacho histórico sem resposta: +0,9 TWh;
  - atraso de 12 meses dos DC: −1,6 TWh;
  - eólica baixa/alta: +0,8 / −1,4 TWh.
- **Efeito dos DC nessas sensibilidades:** sempre positivo, de +1,8 a +3,0 TWh, exceto com o atraso.

## 4. Limitações principais

- Não há representação de rede: excedente ≠ corte.
- Despacho hidrotérmico por regra emulada, sem otimização.
- Hidrologia amostrada só em 2022–2025.
- Carga de data centers flat; a projeção oficial muda rápido entre revisões (716 → 1.291 → 2.098 MWmed para 2030).
- Funções de transferência baseadas na frota atual; resíduos de 18 meses.
- Cenários eólicos sem datas do SIGA.
- Não há limite de importação documentado.

## 5. Decisões

Todas registradas em `docs/decisoes.md` (1–37). As do usuário são: L_base = carga líquida da API (Dia 1); data centers pela opção A + C com o cenário alto aceito; base de carga e MMGD pela 2ª RQ do PLAN; eólica alta = 39,4 GW; despacho histórico com hidráulica plana como sensibilidade (determinístico); regra hidráulica emulada no Monte Carlo.

Pendências do usuário: nenhuma.

## 6. Próximos passos possíveis (fora do escopo obrigatório)

- Representação simplificada da rede do NE ou dos limites por região (Pecém, Parnaíba) para estimar o corte evitado.
- Hidrologia de longo prazo do São Francisco (P2 #13) para ampliar a amostra hidrológica.
- Armazenamento ou flexibilidade como alternativa à expansão eólica para cobrir a importação noturna.
- Atualizar com a nota técnica completa da 2ª RQ e com o 1º PLAN 2027–2031 quando forem publicados.
