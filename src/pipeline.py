"""Executa o pipeline completo a partir de data/raw (sem baixar dados).

Uso: python -m src.pipeline [--desde etapa] [--ate etapa]
Etapas, em ordem: integracao, auditoria, pde, features, clima, backtest, cortes,
deterministico, sinteticos, montecarlo, relatorio, figuras, tecnico.
A coleta (src.collect.*) não faz parte: ver README. Cada etapa é um módulo independente,
sem estado oculto; as saídas intermediárias ficam em data/interim e data/processed.
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import time

ETAPAS = [
    ("integracao", "src.build.ne_hourly", []),
    ("auditoria", "src.audit.run_audit", []),
    ("pde", "src.collect.pde_extract", []),
    ("features", "src.features.build", []),
    ("clima", "src.features.clima_historico", []),
    ("backtest", "src.models.backtest", []),
    ("cortes", "src.models.cortes", []),
    ("deterministico", "src.sim.deterministico", []),
    ("sinteticos", "src.sim.sinteticos", ["--refazer-residuos"]),
    ("montecarlo", "src.sim.montecarlo", []),
    ("relatorio", "src.report.final", []),
    ("figuras", "src.report.figuras_didaticas", []),
    ("tecnico", "src.report.tecnico", []),
]


def main(argv=None) -> None:
    nomes = [e[0] for e in ETAPAS]
    ap = argparse.ArgumentParser()
    ap.add_argument("--desde", choices=nomes, default=nomes[0])
    ap.add_argument("--ate", choices=nomes, default=nomes[-1])
    a = ap.parse_args(argv)
    i0, i1 = nomes.index(a.desde), nomes.index(a.ate)
    for nome, mod, args in ETAPAS[i0:i1 + 1]:
        t = time.time()
        print(f"=== {nome} ({mod})", flush=True)
        m = importlib.import_module(mod)
        # módulos com argparse recebem a lista explícita (não herdam sys.argv do orquestrador)
        m.main(args) if "argv" in inspect.signature(m.main).parameters else m.main()
        print(f"=== {nome}: {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
