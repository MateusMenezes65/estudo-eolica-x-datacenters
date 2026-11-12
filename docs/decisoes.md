# Registro de decisões técnicas

Formato: decisão — justificativa — status (adotada / provisória / pendente do usuário).

## Ambiente

1. **Python 3.14.1** em `.venv` — é o único Python instalado (não há 3.11/3.12);
   pandas 3.1, numpy 2.5, pyarrow 26, scikit-learn 1.9 têm wheels para 3.14 e
   instalaram sem compilação. — adotada.
2. **Git local inicializado** (a pasta não pertencia a nenhum repositório).
   Identidade configurada só neste repositório (`git config --local`), informada
   pelo usuário em 2026-11-11; configuração global não alterada. — adotada.

## Coleta

3. **Parquet** como formato preferido do ONS (≈ 10× menor que CSV); CSV quando o
   ONS não publica Parquet no período (intercâmbio 2022). — adotada.
4. **Limiar de "download grande" = 50 MB por conjunto**; acima disso, pedido de
   confirmação. Autorizados em 2026-11-11: geração e FC por usina, constrained-off
   eólico/solar, MMGD ANEEL, Open-Meteo. — adotada.
5. **Carga verificada semi-horária via API do ONS** (`apicarga.ons.org.br`),
   fonte não listada no catálogo original, incluída porque separa carga global,
   carga líquida de MMGD e MMGD (regra 8). — adotada.
6. **Meteorologia: Open-Meteo com `models=era5`** (0,25°), fixado para
   homogeneidade temporal e extensão futura a anos anteriores (papel 2 dos
   modelos). 34 pontos: 8 capitais + 16 clusters eólicos + 10 solares (k-means
   pesado pela potência SIGA em operação/construção; semente 20261111). — adotada.
7. **Calendário**: biblioteca `holidays` (nacionais + estaduais das 8 UFs);
   São João (23–24/06) e Carnaval como eventos; feriados municipais não incluídos. — adotada.
8. **Temperatura ponderada pela população da UF (Censo 2022)**, não pela carga
   (não há carga horária por UF). — adotada.

## Tempo e unidades

9. `t` = início da hora em Brasília. ONS horário já está assim; API de carga
   (fim do intervalo, UTC) → início em Brasília; ERA5 instantâneo → média de t e
   t+1h; radiação (média da hora anterior) → valor rotulado t+1h. — adotada.
10. 30 min → hora: média dos dois MWmed (equivale a MWh na hora). Nenhuma hora
    incompleta encontrada. — adotada.
11. **Corte analítico do histórico: 2022-01-01 a 2025-12-31** (anos completos);
    2026-01 a 2026-10 apenas complementar; dados do mês corrente são preliminares
    (a identidade carga global = líquida + MMGD falha nas últimas horas). — adotada.

## Definições (afetam resultados — validar)

12. **Quebra de definição no balanço ONS em 2023-04-29 00h**: a partir daí
    `val_carga` inclui a MMGD estimada e `val_gersolar` inclui a mesma MMGD
    (linhas "Pequenas Usinas (MMGD)" em geração por usina). O balanço fecha nos
    dois regimes, mas a série de carga tem degrau de ~0,5 GW. — fato observado.
13. **Proposta para L_base: carga líquida de MMGD da API** (`val_cargaglobalsmmgd`,
    definição homogênea 2022+) e **MMGD como geração distribuída separada**
    (`val_cargammgd`, API), projetada para 2030 pelo PDE/ANEEL. A geração
    centralizada e o intercâmbio vêm do balanço (excluindo a MMGD). Diferença
    residual entre as fontes: ±100 MWmed até 2025-T2, −300 a −500 MWmed de
    2025-T3 em diante (a investigar). Alternativa: balanço líquido (`val_carga`
    − MMGD por usina), que fecha exatamente mas mistura duas estimativas de MMGD. — **adotada pelo usuário em 2026-11-11**.
    Consequência: no balanço futuro, G_NE inclui a MMGD projetada como geração
    distribuída e L_base é a carga líquida de MMGD; a MMGD nunca é descontada da
    carga e somada à geração ao mesmo tempo (regra 8).
14. **Curtailment**: usar a GNRa apurada pelo ONS (`val_geracaonaorealizadaapurada`,
    só nos patamares restritos) como corte; potencial = geração + GNRa. Não usar
    `referência − geração` em todas as horas: a referência é menor que a geração
    em 45 % das horas-usina eólicas (65 % em 2022), logo não é potencial puro. — adotada (regra 4).
15. **Data centers no PDE 2035** — usuário (2026-11-11): L_DC é incremental ao
    PDE de referência e, num primeiro momento, deve reproduzir a projeção do PDE.
    O que o PDE publica (extraído por `src/collect/pde_extract.py` →
    `config/pde2035_extraido.csv`):
    - carga do NE, referência: 13 684 (2025) → 16 340 (2030) → 19 610 MWmed (2035)
      (Tabela 2-3); inferior/superior só em 2025 e 2035 (18,1 e 28,7 GWmed em 2035);
    - "cargas especiais" (VE + data centers + H2) no Brasil em 2035: 9,5 / 11,7 /
      131,1 TWh (inferior / referência / superior), sem separação por tipo,
      subsistema nem ano;
    - pedidos de conexão de data centers à Rede Básica no MME (out/2025), Brasil:
      17,4 GW acumulados até 2030, 26,3 GW até 2038; a distribuição por UF existe
      só como mapa (Figura 4-4), sem valores legíveis por tipo e UF.
    Conclusão: **o PDE não publica uma trajetória de data centers para o NE**. Os
    data centers do cenário de referência estão embutidos na carga do NE e não são
    separáveis.
    **Decisão do usuário (2026-11-11): opção A + C.** Caso-base = PDE de
    referência puro (L_DC incremental = 0; os DC do PDE ficam embutidos na carga
    do NE). Cenários de DC (conservador/central/alto) = inventário documentado de
    projetos no NE (#11), somado ao caso-base, com o pipeline do MME como teto. A
    diferença PDE superior − referência (opção B) fica apenas como estresse. —
    adotada.
16b. **Projeção oficial de DC usada nos cenários**: a previsão de carga do PLAN
    2026-2030 (ONS/EPE/CCEE) publica a carga de DC de Rede Básica por subsistema.
    NE, 2ª Revisão Quadrimestral (acessos de 22/07/2026): 112 / 333 / 628 / 813 /
    2.098 MWmed (2026–2030), dos quais 1.886 MWmed de contratos assinados em 2030.
    Valores lidos dos rótulos dos gráficos (slides do workshop; a nota técnica da
    2ª RQ não foi localizada) e conferidos com o texto (incremento de 807 MWmed
    sobre a 1ª RQ). Cenários: conservador = contratos; central = 2ª RQ; alto =
    contratos + 100% pareceres + inventário M3 (CDV_ACESSOS, QAIR2, ENEGIX). Os
    valores oficiais já são MWmed de carga: sem PUE nem utilização. — adotada;
    cenário alto aceito pelo usuário em 2026-11-11.
19. **ERA5 1995–2021** nos mesmos 34 pontos, em blocos de 9 anos
    (`data/raw/openmeteo/hist/`), autorizado pelo usuário em 2026-11-11. Mesma
    grade e modelo (`models=era5`) do período de calibração. — adotada.

## Anomalias conhecidas (não corrigidas; tratadas na análise)

16. Balanço ONS 2026-01 a 2026-05: 878 horas em que G − L − I não fecha (até
    −17,5 GW) e eólica do balanço muito abaixo da soma por usina (72 horas
    < 50 %). Dados em consistência pelo ONS; 2026 é complementar. Ação: excluir
    essas horas do balanço ou usar geração por usina. — adotada.
17. FC por usina: 3 888 horas-usina com capacidade 0 e 1 796 com geração > 105 %
    da capacidade (registro de capacidade defasado). Impacto agregado ≈ 0,3 TWh em
    ~450 TWh. Ação proposta (Dia 2): CF agregado só com usinas de capacidade > 0;
    não recortar valores. — provisória.
18. MMGD ANEEL: a única data por empreendimento é a **última atualização
    cadastral**, não a data de conexão; a capacidade acumulada por data é viesada
    para datas recentes. Uso: fotografia atual por UF; trajetória histórica pela
    MMGD estimada do ONS. Base contém dados pessoais tarjados: só agregados. — adotada.

## Dia 2 — modelos e cenários (2026-11-11)

20. **CF eólico potencial plausível**: o salto para 0,48 em 2025 vem de ano mais ventoso
    (vento³ +11–17%) e de curva de potência 5–10% maior da frota nova, em horas restritas e
    não restritas; não há sinal de GNRa inflada. — fato observado.
21. **Fator de frota por ano climático** no simulador: k = média do modelo B0/C0 treinado na
    frota recente (2024-07..2026-10) / média observada no ano. Preserva a variabilidade
    horária observada. — adotada.
22. **Carga modelada como bruta** (forma estável) e MMGD separada; a carga líquida muda de forma
    com a MMGD (A0 líquida: MAE 3,4–9,5%; bruta: 2,6–3,2%). — adotada.
23. **Nível de carga em 2030** = carga global do NE no PDE referência (16.340 MWmed). **MMGD em
    2030** = MMGD média do NE em 2025 (API, 1.527 MWmed) × crescimento da capacidade de MMGD
    do Brasil no PDE (1,507; faixa 1,27–1,78). — hipótese adotada.
24. **Eólica em 2030**: baixa = operação (32,3 GW); base = operação + construção (34,3 GW);
    alta = base + 5,1 GW da expansão indicativa do PDE alocada ao NE (39,4 GW). Solar =
    13,5 GW. O SIGA aberto não traz datas para projetos fora de operação. — hipótese adotada.
25. **Hidráulica e térmica**: despacho horário histórico do ano climático. — hipótese; sem redespacho.
26. **Intercâmbio**: exportação limitada a 21 GW (PDE, seção 4.3.2); importação sem limite
    documentado, então sensibilidade em 6, 8 e 10 GW. — adotada.
27. **Classificador de cortes**: viável para ordenar horas (ENE, CNF, total), mas mal calibrado
    sob mudança de regime; não gera probabilidade de corte em 2030. REL não é previsível. —
    adotada (uso descritivo).
28. **Backtesting**: 12 dobras mensais em 2025 com janela expansível, HGB com hiperparâmetros
    fixos e semente 20261111; o clima ERA5 conta como previsão perfeita (limite superior). — adotada.

## Revisão de hipóteses com o usuário (2026-11-12)

29. **Base de carga de 2030 = 2ª Revisão Quadrimestral do PLAN 2026–2030** (ONS/EPE/CCEE,
    ago/2026). Carga global do NE em 2030 = 18.278 MWmed, menos 2.098 MWmed de DC de Rede
    Básica = **16.180 MWmed sem DC**. **MMGD em 2030 = 2.386 MWmed** (oficial). Valores em
    `config/plan_2rq_ne.csv`. Substitui as decisões 23 (carga do PDE, MMGD estimada) e a
    sensibilidade de dupla contagem. O PDE (16.340 MWmed, −258 MWmed) fica como sensibilidade. —
    adotada pelo usuário.
30. **Eólica alta mantida**: 39,4 GW (base + 5,1 GW da expansão indicativa do PDE, toda no NE). —
    confirmada pelo usuário.
31. **Despacho hidrotérmico histórico** como caso central, com **hidráulica plana** (mesma
    energia anual, perfil constante) como sensibilidade pessimista. — adotada pelo usuário.
