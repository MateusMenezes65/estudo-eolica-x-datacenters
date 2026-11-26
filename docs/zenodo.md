# Depósito no Zenodo (versão 1.0.0)

Ficha para preencher o formulário de novo registro em https://zenodo.org/uploads/new.
O DOI é reservado antes de publicar ("Get a DOI now!"), inserido no relatório e
só então o registro é publicado. Depois de publicado, o registro só pode ser
apagado pelo dono nos primeiros 30 dias, e trocar arquivos exige uma nova versão.

DOI reservado em 2026-11-25: **10.5281/zenodo.24545239**
(https://doi.org/10.5281/zenodo.24545239; resolve só depois da publicação).

## Arquivos

| Arquivo | Conteúdo | Origem |
|---|---|---|
| `relatorio_final.pdf` | Relatório da disciplina PTC3567, com o DOI | compilado no Prism |
| `estudo-eolica-x-datacenters-v1.0.0.zip` | Código, configuração, testes, `reports/` e fonte LaTeX, sem `data/` | `git archive` da tag `v1.0.0` |
| `data-interim.zip` | `data/interim` (8 arquivos, 223 MiB) | `src.tools.pacote_dados` |
| `data-processed.zip` | `data/processed` (10 arquivos, 54 MiB) | `src.tools.pacote_dados` |
| `SHA256SUMS.txt` | Hashes dos dois zips de dados | `src.tools.pacote_dados` |

`data/raw` fica de fora: os brutos são refeitos pelos scripts de coleta (README),
e a base de MMGD da ANEEL contém dados pessoais tarjados (decisão 112 de
docs/decisoes.md). Para restaurar os dados derivados na raiz do projeto:
`python -m src.tools.pacote_dados extrair PASTA_DOS_ZIPS`.

## Metadados

- **Resource type:** Software
- **Title:** Data centers e expansão eólica no balanço horário do subsistema Nordeste em 2030: código, dados derivados e relatório
- **Publication date:** data da publicação
- **Creators** (Personal; affiliation Universidade de São Paulo):
  - Menezes, Mateus Jeszensky de
  - Silva, Raphael Rodrigues Souza da
- **Version:** 1.0.0
- **Language:** Portuguese
- **Licenses:** MIT License; Creative Commons Attribution 4.0 International
- **Keywords:** energia eólica; data centers; balanço energético; subsistema Nordeste; importação de energia; simulação de Monte Carlo; gradient boosting; ERA5
- **Related works:** *Is supplement to* → https://github.com/MateusMenezes65/estudo-eolica-x-datacenters/tree/v1.0.0 → URL → Software (a mesma relação que a integração do Zenodo com o GitHub usa)

### Description

Material do relatório final da disciplina PTC3567 – Ciência dos Dados em
Automação e Engenharia (Escola Politécnica da USP, 2026).

O estudo estima como a entrada de data centers e a expansão eólica mudam a
necessidade de importação e os excedentes horários do subsistema Nordeste do
SIN em 2030. Funções de transferência de gradient boosting, treinadas com dados
do ONS de 2022 a 2026, convertem 31 anos de clima da reanálise ERA5 (1995–2025)
em formas horárias de carga, geração distribuída e fatores de capacidade eólico e
solar. Essas formas são combinadas aos níveis de cenários oficiais (PLAN
2026–2030 e PDE 2035) em uma simulação de Monte Carlo com 2.000 sorteios. Os
resultados são condicionais aos cenários adotados e não são previsões.

Conteúdo:
- relatorio_final.pdf: relatório da disciplina;
- estudo-eolica-x-datacenters-v1.0.0.zip: código Python, configuração dos cenários, testes,
  tabelas, figuras, relatório técnico, simulador interativo (reports/site/simulador/index.html)
  e fonte LaTeX do relatório;
- data-interim.zip e data-processed.zip: bases horárias integradas e bases analíticas
  (descompactar na raiz do projeto); SHA256SUMS.txt confere os dois arquivos.

Os dados brutos não estão incluídos e podem ser coletados de novo pelos scripts do
pacote (ver README.md). Os resultados do relatório foram gerados no commit 7b290ee;
a versão depositada acrescenta apenas documentação, o relatório e correções de
exibição do simulador.

Fontes dos dados derivados, que devem ser citadas em qualquer reuso: ONS (Dados
Abertos), ANEEL (SIGA), EPE/ONS/CCEE (PLAN 2026–2030), MME/EPE (PDE 2035), IBGE
(Censo 2022) e Copernicus Climate Change Service (ERA5), obtido pela API da
Open-Meteo.

Código sob a licença MIT; relatório, figuras e dados derivados sob CC BY 4.0.
