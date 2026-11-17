# Estudo Eólica × Data Centers — subsistema Nordeste (horizonte 2030)

Estudo acadêmico de cenários condicionais: como a entrada de data centers e a
expansão eólica alteram a necessidade de importação e os excedentes horários do
subsistema Nordeste (ONS) até 2030, e quanto de expansão eólica compensaria o
consumo adicional. Não é estudo de fluxo de potência, adequação do SIN nem
viabilidade econômica. Acordo de implementação: [AGENTS.md](AGENTS.md).
Estado atual e próximos passos: [STATUS.md](STATUS.md). Decisões técnicas:
[docs/decisoes.md](docs/decisoes.md).

## Como obter o projeto (grupo)

O repositório é privado: o dono precisa adicionar cada colega em
*Settings → Collaborators*. Depois de aceitar o convite:

```bash
git clone https://github.com/MateusMenezes65/estudo-eolica-x-datacenters.git
```

O repositório contém código, configuração, manifesto de fontes, tabelas de
resultado, figuras e relatórios (`reports/`). Para apenas ler os resultados,
abra no navegador `reports/site/final/index.html` ou
`reports/site/tecnico/index.html` (ou leia os `.md` em `reports/`). Para explorar
os anos de 2026 a 2030 hora a hora, abra `reports/site/simulador/index.html`
(simulador interativo; ver a seção própria abaixo).

**Dados (`data/`, cerca de 1,2 GB):** versionados com **Git LFS** (há arquivos
acima de 100 MB, o limite do Git no GitHub). Instale o Git LFS **antes** de
clonar (já vem no Git for Windows; confira com `git lfs version`); assim o
`git clone` baixa os dados reais. Sem ele, os arquivos de `data/` chegam como
pequenos "ponteiros" de texto; nesse caso, rode na pasta do projeto:

```bash
git lfs pull
```

**Windows, erro "Filename too long" no clone:** alguns arquivos do PDE têm
caminho de até 185 caracteres. Clone numa pasta de caminho curto (por exemplo
`C:\estudos\`) ou habilite caminhos longos no Git antes de clonar:

```bash
git config --global core.longpaths true
```

A cota gratuita de LFS do dono do repositório é de 10 GiB de download por mês
(cada clone completo consome cerca de 1,2 GB). Alternativas que não consomem
essa cota: os zips anexados à Release
[`dados-2026-11-16`](https://github.com/MateusMenezes65/estudo-eolica-x-datacenters/releases/tag/dados-2026-11-16),
restaurados com `python -m src.tools.pacote_dados extrair dist/dados`, ou a
coleta direta das fontes com os comandos abaixo. Para clonar só o código, sem
baixar os dados do LFS, use a variável `GIT_LFS_SKIP_SMUDGE=1` no clone.

## Ambiente

- Windows 11, Python 3.14.1 (único Python instalado; todas as dependências têm
  wheels para 3.14 — ver `requirements.txt` e `requirements.lock.txt`). Em outra
  máquina o projeto também roda com Python 3.13.7 e as mesmas versões fixadas
  (`py -3.13 -m venv .venv`; testes aprovados e Monte Carlo de 2030 idêntico).
- Ambiente virtual dentro do projeto:

```bash
py -3.14 -m venv .venv
```

```bash
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
```

Todos os comandos abaixo são executados a partir da raiz do projeto
(caminhos relativos; funcionam com espaços no nome da pasta). Em PowerShell,
use `.venv\Scripts\python.exe`.

## Pipeline reproduzível (Dia 1: coleta → integração → auditoria)

Coleta (cada script registra arquivo, URL, tamanho, SHA-256 e data de coleta em
`docs/manifest/manifest.csv`; arquivos já presentes não são baixados de novo):

```bash
.venv/Scripts/python.exe -m src.collect.ons catalog
```

```bash
.venv/Scripts/python.exe -m src.collect.ons download balanco intercambio curva_carga capacidade geracao_usina fator_capacidade coff_eolica coff_solar
```

```bash
.venv/Scripts/python.exe -m src.collect.ons_carga_api --area NE --start 2022-01 --end 2026-11
```

```bash
.venv/Scripts/python.exe -m src.collect.aneel download siga mmgd
```

```bash
.venv/Scripts/python.exe -m src.collect.epe
```

```bash
.venv/Scripts/python.exe -m src.collect.ibge_pop
```

```bash
.venv/Scripts/python.exe -m src.collect.weather_points
```

```bash
.venv/Scripts/python.exe -m src.collect.openmeteo --start 2022-01-01
```

```bash
.venv/Scripts/python.exe -m src.collect.calendario_ne
```

Anos climáticos ERA5 para o Monte Carlo (retomável; respeita os limites da API gratuita):

```bash
.venv/Scripts/python.exe -m src.collect.openmeteo --start 1995-01-01 --end 2021-12-31 --chunk-years 9
```

Valores do PDE 2035 usados nos cenários (gera `config/pde2035_extraido.csv`):

```bash
.venv/Scripts/python.exe -m src.collect.pde_extract
```

Notas técnicas de previsão de carga do PLAN 2026-2030 (carga de data centers por
subsistema). Os slides da 2ª Revisão Quadrimestral (CCEE) recusam download
automatizado (HTTP 403) e foram obtidos manualmente; ver o manifesto:

```bash
.venv/Scripts/python.exe -m src.collect.ons_plan
```

Conferência do manifesto, integração horária, auditoria e testes:

```bash
.venv/Scripts/python.exe -m src.collect.manifest
```

```bash
.venv/Scripts/python.exe -m src.build.ne_hourly
```

```bash
.venv/Scripts/python.exe -m src.audit.run_audit
```

## Pipeline do Dia 2 (features → modelos → simulador)

```bash
.venv/Scripts/python.exe -m src.features.build
```

```bash
.venv/Scripts/python.exe -m src.models.backtest
```

```bash
.venv/Scripts/python.exe -m src.models.cortes
```

```bash
.venv/Scripts/python.exe -m src.sim.deterministico
```

Resultados: `reports/dia2_modelos_cenarios.md`, `reports/models/`, `reports/sim/`.

## Dia 3 (incerteza e relatório final)

```bash
.venv/Scripts/python.exe -m src.features.clima_historico
```

```bash
.venv/Scripts/python.exe -m src.sim.sinteticos --refazer-residuos
```

```bash
.venv/Scripts/python.exe -m src.sim.montecarlo --n 2000
```

Validação retrospectiva do simulador contra a importação observada em 2022–2025:

```bash
.venv/Scripts/python.exe -m src.sim.backcast
```

```bash
.venv/Scripts/python.exe -m src.report.final
```

## Simulador interativo 2026–2030

Página estática (sem servidor e sem internet): barra de anos de 2026 a 2030, M(t) horário ao
longo do ano, resorteio do ano meteorológico e do ano hidrotérmico (regra hidráulica emulada),
cenários eólico e de data centers de cada ano e, em 2026, backtest contra o balanço observado de
janeiro a outubro. Abra `reports/site/simulador/index.html` no navegador (Chrome/Edge 80+,
Firefox 113+ ou Safari 16.4+; `dados.js` precisa estar na mesma pasta). O estado fica na URL
(`#ano=2028&eol=base&dc=central&...`), o que permite compartilhar um sorteio. Os resultados do
estudo continuam sendo os de 2030; os níveis de 2026–2029 estão no anexo dos relatórios.

Regenerar (depois do Monte Carlo de 2030):

```bash
.venv/Scripts/python.exe -m src.sim.trajetorias
```

```bash
.venv/Scripts/python.exe -m src.sim.anos
```

```bash
.venv/Scripts/python.exe -m src.sim.backtest_2026
```

```bash
.venv/Scripts/python.exe -m src.report.simulador
```

Diagnóstico da subestimação da importação (backtest de 2026 e validação retrospectiva; relatório
técnico, seção 7.5):

```bash
.venv/Scripts/python.exe -m src.sim.diagnostico_importacao
```

Regras dos níveis por ano: `config/cenarios_anuais.yaml`; tabela em
`reports/sim/trajetorias_2026_2030.csv`; backtest em `reports/sim/backtest_2026*.csv` e
`reports/figures/b26_backtest_2026.png`. A página confere o próprio motor contra casos de
referência calculados em Python (rodapé "Autoverificação do motor").

## Pipeline completo a partir de `data/raw`

Roda, em ordem, integração, auditoria, PDE, features, clima, backtesting, cortes, simulador
determinístico, perfis sintéticos, Monte Carlo, validação retrospectiva, trajetórias e Monte Carlo
de 2026–2030, backtest de 2026, relatórios (Markdown e HTML) e simulador interativo (cerca de 25 min):

```bash
.venv/Scripts/python.exe -m src.pipeline
```

Para rodar só um trecho, use `--desde` e `--ate` (ex.: `--desde montecarlo`).
Relatório final: `reports/relatorio_final.md`. Relatório técnico detalhado (passo a passo, com 30
figuras): `reports/relatorio_tecnico.md`, gerado por `src.report.figuras_didaticas` e
`src.report.tecnico` (etapas `figuras` e `tecnico` do pipeline).

Versão HTML do relatório (com sumário e figuras), para compartilhar:

```bash
.venv/Scripts/python.exe -m src.report.html --doc tecnico --saida reports/site/tecnico
```

Testes:

```bash
.venv/Scripts/python.exe -m pytest -q
```

Volume aproximado: `data/raw` ≈ 830 MB; `data/interim` ≈ 265 MB. Downloads
grandes (> 50 MB por conjunto) foram feitos com autorização do usuário.

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| `config/` | fontes (`sources_*.yaml`), pontos meteorológicos, calendário NE, população UF, cenários de 2030 (`cenarios*.yaml`), regras dos anos 2026–2029 (`cenarios_anuais.yaml`), inventário e trajetória oficial de data centers, valores do PDE e do PLAN |
| `src/collect/` | coletores (ONS CKAN e API de carga, ANEEL, EPE, IBGE, Open-Meteo, calendário) e manifesto |
| `src/ingest/` | leitores padronizados (tipos, fuso, agregação 30 min → hora) |
| `src/build/` | base horária integrada do NE (`data/interim/ne_hourly.parquet`) |
| `src/audit/` | relatório de qualidade, tabelas e figuras |
| `src/features/` | base analítica horária e clima 1995–2026 com pesos fixos da frota |
| `src/models/` | backtesting de curto prazo, funções de transferência e classificador de cortes |
| `src/sim/` | simulador determinístico, perfis sintéticos, Monte Carlo, validação retrospectiva, trajetórias e Monte Carlo de 2026–2030, backtest de 2026 |
| `src/report/` | relatório final, relatório técnico, figuras didáticas, versão HTML, anexo 2026–2029 e simulador interativo (`simulador.py` + `simulador_app.html`) |
| `tests/` | testes de unidades, tempo, junções e balanço |
| `docs/` | plano orientador, manifesto, decisões |
| `reports/` | `relatorio_tecnico.md` (base para apresentação), `relatorio_final.md`, `quality/relatorio_qualidade.md`, `mc/`, `sim/`, `models/`, `tables/`, `figures/`, `site/` (HTML dos relatórios e `site/simulador/`) |

## Convenções principais

- Tempo: `t` = início da hora em horário de Brasília (UTC−3; sem horário de
  verão em 2022+). Fontes em UTC (API de carga, ERA5) são convertidas.
- Unidades: potências em MW ou MWmed por intervalo; energia = Σ MWmed × duração (h).
- Recorte elétrico: subsistema NE do ONS = AL, BA, CE, PB, PE, PI, RN, SE
  (o Maranhão pertence ao subsistema Norte).
- `M(t) = G_NE(t) − [L_base(t) + L_DC(t)]`; importação = max(0, −M); excedente = max(0, M).
  Margem negativa não implica déficit de suprimento.
