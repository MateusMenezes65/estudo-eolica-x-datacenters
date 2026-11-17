"""Anexo dos relatórios: níveis de cenário por ano, 2026–2029 (simulador interativo).

Lido de reports/sim/trajetorias_2026_2030.csv (src.sim.trajetorias). Não altera nenhum resultado
de 2030: a coluna de 2030 repete os valores do estudo, para referência.
"""
from __future__ import annotations

import pandas as pd

from src.paths import REPORTS


def _f(x: float, nd: int = 0) -> str:
    return f"{x:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def markdown(titulo: str = "## Anexo — Níveis de cenário por ano, 2026–2029 (simulador interativo)") -> str:
    T = pd.read_csv(REPORTS / "sim" / "trajetorias_2026_2030.csv").set_index("ano")
    anos = [a for a in T.index if a != 2030]
    cab = "| | " + " | ".join(str(a) for a in anos) + " | 2030 (estudo) |"
    sep = "|---|" + "---:|" * (len(anos) + 1)
    linhas = [
        ("Carga sem DC (MWmed)", "L_gross_sem_dc_MWmed", 1, 0),
        ("MMGD (MWmed)", "MMGD_MWmed", 1, 0),
        ("Solar (MW)", "cap_sol_MW", 1, 0),
        ("Eólica baixa (MW)", "cap_eol_baixa_MW", 1, 0),
        ("Eólica base (MW)", "cap_eol_base_MW", 1, 0),
        ("Eólica alta (MW)", "cap_eol_alta_MW", 1, 0),
        ("Data centers: sem DC (MWmed)", "L_DC_sem_dc_MWmed", 1, 0),
        ("Data centers: conservador (MWmed)", "L_DC_conservador_MWmed", 1, 0),
        ("Data centers: central (MWmed)", "L_DC_central_MWmed", 1, 0),
        ("Data centers: alto (MWmed)", "L_DC_alto_MWmed", 1, 0),
    ]
    tab = [cab, sep] + ["| " + rot + " | " + " | ".join(_f(T.loc[a, col] * k, nd) for a in anos + [2030]) + " |"
                        for rot, col, k, nd in linhas]
    fr = {a: T.loc[a, "fracao_construcao"] for a in anos}
    return f"""
{titulo}

Os resultados e as conclusões deste relatório são os de 2030. Para o simulador interativo
(`reports/site/simulador/index.html`, gerado por `python -m src.report.simulador`), os mesmos cenários
foram definidos para cada ano de 2026 a 2029 com as regras de `config/cenarios_anuais.yaml`
(`python -m src.sim.trajetorias`; tabela em `reports/sim/trajetorias_2026_2030.csv`):

{chr(10).join(tab)}

- **Carga sem DC** (dado): carga global do NE na 2ª Revisão Quadrimestral do PLAN 2026–2030 menos a
  carga de data centers de Rede Básica da mesma revisão no ano (ex.: 2026 = 14.182 − 112).
- **MMGD** (dado): 2ª RQ do PLAN 2026–2030, NE, base + expansão.
- **Solar e eólica** (hipótese): capacidade média do ano. Usinas em operação no SIGA (em 2026,
  ponderadas pela data de entrada); a capacidade em construção entra de forma uniforme entre 2027 e
  2029 (fração média de {_f(fr[2027] * 100)}%, {_f(fr[2028] * 100)}% e {_f(fr[2029] * 100)}% em 2027, 2028 e 2029) e está toda em
  operação em 2030, como no cenário do estudo. Eólica baixa = só operação; base = operação +
  construção; alta = base + expansão indicativa acumulada do PDE 2035 no ano (0; 0; 1,7; 3,4 GW de
  2026 a 2029), toda no NE. Em 2026 os três cenários eólicos coincidem.
- **Data centers**: os mesmos componentes dos cenários de 2030 aplicados à 2ª RQ de cada ano
  (conservador = contratos assinados; central = contratos + 50% dos pareceres; alto = contratos +
  100% dos pareceres + inventário M3 com a mesma rampa). O parecer de 2026 (rótulo ilegível no slide)
  é total − contratos = 14 MWmed.
- 2028 é bissexto: o simulador integra 8.784 horas, com 29/02 repetindo o clima e a hidrologia de 28/02.
- O simulador traz também um backtest de 2026 com os dados observados de janeiro a outubro.
"""
