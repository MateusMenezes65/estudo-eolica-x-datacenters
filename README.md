# Estudo Eólica × Data Centers — subsistema Nordeste (horizonte 2030)

Estudo acadêmico de cenários condicionais: como a entrada de data centers e a
expansão eólica alteram a necessidade de importação e os excedentes horários do
subsistema Nordeste (ONS) até 2030, e quanto de expansão eólica compensaria o
consumo adicional. Não é estudo de fluxo de potência, adequação do SIN nem
viabilidade econômica. Acordo de implementação: [AGENTS.md](AGENTS.md).
Estado atual e próximos passos: [STATUS.md](STATUS.md). Decisões técnicas:
[docs/decisoes.md](docs/decisoes.md).

## Ambiente

- Windows 11, Python 3.14.1 (único Python instalado; todas as dependências têm
  wheels para 3.14 — ver `requirements.txt` e `requirements.lock.txt`).
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

```bash
.venv/Scripts/python.exe -m pytest -q
```

Volume aproximado: `data/raw` ≈ 830 MB; `data/interim` ≈ 265 MB. Downloads
grandes (> 50 MB por conjunto) foram feitos com autorização do usuário.

## Estrutura

| Caminho | Conteúdo |
| --- | --- |
| `config/` | fontes (`sources_*.yaml`), pontos meteorológicos, calendário NE, população UF |
| `src/collect/` | coletores (ONS CKAN e API de carga, ANEEL, EPE, IBGE, Open-Meteo, calendário) e manifesto |
| `src/ingest/` | leitores padronizados (tipos, fuso, agregação 30 min → hora) |
| `src/build/` | base horária integrada do NE (`data/interim/ne_hourly.parquet`) |
| `src/audit/` | relatório de qualidade, tabelas e figuras |
| `tests/` | testes de unidades, tempo, junções e balanço |
| `docs/` | plano orientador, manifesto, decisões |
| `reports/` | `quality/relatorio_qualidade.md`, `tables/`, `figures/` |

## Convenções principais

- Tempo: `t` = início da hora em horário de Brasília (UTC−3; sem horário de
  verão em 2022+). Fontes em UTC (API de carga, ERA5) são convertidas.
- Unidades: potências em MW ou MWmed por intervalo; energia = Σ MWmed × duração (h).
- Recorte elétrico: subsistema NE do ONS = AL, BA, CE, PB, PE, PI, RN, SE
  (o Maranhão pertence ao subsistema Norte).
- `M(t) = G_NE(t) − [L_base(t) + L_DC(t)]`; importação = max(0, −M); excedente = max(0, M).
  Margem negativa não implica déficit de suprimento.
