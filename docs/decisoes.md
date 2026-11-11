# Registro de decisões técnicas

Formato: decisão — justificativa — status (adotada / provisória / pendente do usuário).

## Ambiente

1. **Python 3.14.1** em `.venv` — é o único Python instalado (não há 3.11/3.12);
   pandas 3.1, numpy 2.5, pyarrow 26, scikit-learn 1.9 têm wheels para 3.14 e
   instalaram sem compilação. — adotada.
2. **Git local inicializado** (a pasta não pertencia a nenhum repositório). Sem
   identidade Git configurada: **nenhum commit feito**. — pendente do usuário (nome e e-mail).

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
15. **Data centers no PDE 2035**: o cenário de referência já inclui "cargas
    especiais" (veículos elétricos, data centers, hidrogênio) ≈ 1,4 % do consumo;
    o superior ≈ 12,9 %. L_DC dos cenários deve ser incremental ao que está no PDE
    usado como base (regra 9). — pendente (Dia 2).

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
