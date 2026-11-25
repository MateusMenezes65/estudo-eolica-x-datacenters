"""Simulador interativo do balanço horário do NE, 2026–2030 (página HTML estática, sem servidor).

Uso: python -m src.report.simulador [--saida reports/site/simulador]
Pré-requisitos: src.sim.trajetorias, src.sim.anos e src.sim.backtest_2026.
Saídas: <saida>/index.html (cópia de src/report/simulador_app.html) e <saida>/dados.js.

A página recalcula no navegador o mesmo balanço do Monte Carlo (src/sim/montecarlo.py) para um
sorteio por vez: ano meteorológico (1995–2025), ano hidrotérmico (2022–2025) com a regra hidráulica
emulada e blocos de 7 dias de resíduos fora da amostra. Os insumos horários vão quantizados
(passo 1e-4 nas formas e CF, 0,1 MW na hidráulica e térmica), com diferenças codificadas e gzip.
As distribuições de referência (2.000 sorteios por ano) vêm de src.sim.anos; o backtest de 2026
vem de src.sim.backtest_2026. A página confere o próprio motor contra os casos de referência
calculados aqui (`verificacao`), com os mesmos insumos quantizados.
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from src.paths import PROCESSED, REPORTS, ROOT
from src.sim import montecarlo as mc
from src.sim.anos import InsumosAno, calendario
from src.sim.deterministico import load_cfg
from src.sim.trajetorias import CENARIOS_DC, CENARIOS_EOL, calcular, load_cfg_anual

APP = Path(__file__).with_name("simulador_app.html")
SAIDA = REPORTS / "site" / "simulador"
ESCALAS = {"A0": 1e-4, "E0": 1e-4, "B0": 1e-4, "C0": 1e-4, "res": 1e-4, "hid": 0.1, "ter": 0.1, "mw": 0.1}


# ------------------------------------------------------------------ codificação
def quantizar(x: np.ndarray, escala: float) -> np.ndarray:
    return np.round(np.asarray(x, dtype=float) / escala).astype(np.int64)


def codificar(x: np.ndarray, escala: float) -> dict:
    """Matriz (linhas × colunas) → inteiros quantizados, diferenças ao longo das colunas, int32, gzip, base64."""
    x = np.atleast_2d(x)
    q = quantizar(x, escala)
    d = np.diff(q, axis=1, prepend=0).astype(np.int32)
    assert np.abs(np.diff(q, axis=1, prepend=0)).max() < 2 ** 31
    b = gzip.compress(d.tobytes(order="C"), compresslevel=9, mtime=0)
    return {"forma": list(x.shape), "escala": escala, "b64": base64.b64encode(b).decode("ascii")}


def decodificar(e: dict) -> np.ndarray:
    """Inverso de `codificar` (o que a página vê)."""
    d = np.frombuffer(gzip.decompress(base64.b64decode(e["b64"])), dtype=np.int32).reshape(e["forma"])
    return np.cumsum(d.astype(np.int64), axis=1) * e["escala"]


# ------------------------------------------------------------------ motor de referência (espelha a página)
def motor(I: dict, ano: int, w: int, h: int, dias: np.ndarray, centro: np.ndarray, niv: dict,
          cen_w: str, modo: str = "regra_historica") -> dict:
    """Um sorteio, com os insumos decodificados `I` (mesma aritmética da página).

    Devolve as séries horárias e o M sem DC (`M0`); o DC entra como deslocamento constante.
    """
    nh = I[f"A0_{ano}"].shape[1]
    leap = nh == 8784
    ins = lambda a: np.concatenate([a[:, :59 * 24], a[:, 58 * 24:59 * 24], a[:, 59 * 24:]], axis=1) if leap else a
    E0, B0, C0 = (ins(I[k][[w]])[0] for k in ("E0", "B0", "C0"))     # ano meteorológico w
    hid_p, ter_p = (ins(I[k][[h]])[0] for k in ("hid", "ter"))         # ano hidrotérmico h
    mes = calendario(ano).month.to_numpy() - 1
    lo, hi = I["hmin"][h][mes], I["hmax"][h][mes]
    r = I["res"].reshape(-1, 24, 4)[dias].reshape(nh, 4) - centro
    L = I[f"A0_{ano}"][w] + r[:, 0]
    L = L / L.mean() * niv["L"]
    MM = np.clip(E0 + r[:, 1], 0, None)
    MM = MM / MM.mean() * niv["MMGD"]
    cfe = np.clip(B0 + r[:, 2], 0, 1)
    cfs = np.clip(C0 + r[:, 3], 0, 1)
    cap = niv["cap_eol"][cen_w]
    base = ter_p + cfs * niv["cap_sol"] - (L - MM)
    obj = type("o", (), {})()
    obj.hid, obj.hmin, obj.hmax, obj.beta = hid_p[None], lo[None], hi[None], np.array([I["beta"][h]])
    hid = mc.hidraulica(obj, np.array([0]), -(base + cfe * cap)[None], modo)[0]
    return {"M0": base + cfe * cap + hid, "L": L, "MMGD": MM, "eol": cfe * cap, "sol": cfs * niv["cap_sol"],
            "hid": hid, "ter": ter_p}


# ------------------------------------------------------------------ montagem
def niveis(T: pd.DataFrame) -> dict:
    out = {}
    for r in T.itertuples():
        out[int(r.ano)] = {"L": float(r.L_gross_sem_dc_MWmed), "MMGD": float(r.MMGD_MWmed), "cap_sol": float(r.cap_sol_MW),
                           "cap_eol": {w: float(getattr(r, f"cap_eol_{w}_MW")) for w in CENARIOS_EOL},
                           "ldc": {c: float(getattr(r, f"L_DC_{c}_MWmed")) for c in CENARIOS_DC},
                           "fracao_construcao": float(r.fracao_construcao), "fonte": r.fonte_2030,
                           "carga_global": float(r.carga_global_MWmed), "pde_indicativa": float(r.pde_indicativa_eol_MW)}
    return out


def candidatos(ins, bloco: int = 7) -> list[list[int]]:
    return [[int(j) for j in cand] for _, _, cand in mc.candidatos(ins, bloco)]


def resumo_mc() -> dict:
    S = pd.read_csv(REPORTS / "sim" / "anos_mc_resumo.csv")
    out: dict = {}
    for r in S.itertuples():
        out.setdefault(str(r.ano), {}).setdefault(r.cenario_dc, {}).setdefault(r.cenario_eolico, {})[r.metrica] = \
            [round(float(v), 4) for v in (r.p5, r.p25, r.p50, r.p75, r.p95, r.media)]
    M = pd.read_csv(REPORTS / "sim" / "anos_mc_mensal.csv")
    mens: dict = {}
    for (ano, dc, w), g in M.groupby(["ano", "cenario_dc", "cenario_eolico"]):
        g = g.sort_values("mes")
        mens.setdefault(str(ano), {}).setdefault(dc, {})[w] = {
            k: [round(float(v), 4) for v in g[k]] for k in g.columns if k.endswith("_TWh")}
    return {"anual": out, "mensal": mens}


def backtest() -> dict:
    H = pd.read_parquet(PROCESSED / "backtest_2026_horario.parquet")
    TB = pd.read_csv(REPORTS / "sim" / "backtest_2026.csv")
    TM = pd.read_csv(REPORTS / "sim" / "backtest_2026_mensal.csv")
    TC = pd.read_csv(REPORTS / "sim" / "backtest_2026_componentes.csv")
    info = json.loads((REPORTS / "sim" / "backtest_2026_config.json").read_text(encoding="utf-8"))
    v = H.valida.to_numpy()
    serie = lambda c: codificar(np.where(v, H[c].to_numpy(), 0.0)[None], ESCALAS["mw"])
    return {"inicio": str(H.t.iat[0]), "horas": int(len(H)), "valida": "".join("1" if x else "0" for x in v),
            "M_obs_pot": serie("M_obs_pot"), "M_obs_real": serie("M_obs_real"),
            "M_B": codificar(H.M_B.to_numpy()[None], ESCALAS["mw"]),
            "tabela": json.loads(TB.round(4).to_json(orient="records", force_ascii=False)),
            "mensal": json.loads(TM.round(4).to_json(orient="records", force_ascii=False)),
            "componentes": json.loads(TC.round(1).to_json(orient="records", force_ascii=False)),
            "info": info}


def metricas_ref(M: np.ndarray, c: dict) -> dict:
    m = mc.metricas(M[None], c)
    return {k: float(v[0]) for k, v in m.items()}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", default=str(SAIDA))
    a = ap.parse_args(argv)
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    c, d = load_cfg()
    cfa = load_cfg_anual()
    T = calcular()
    niv = niveis(T)
    anos = cfa["anos"]

    ins30 = InsumosAno(2030)
    enc, I = {}, {}
    for k in ["E0", "B0", "C0"]:
        enc[k] = codificar(getattr(ins30, k), ESCALAS[k])
    enc["hid"], enc["ter"] = codificar(ins30.hid, ESCALAS["hid"]), codificar(ins30.ter, ESCALAS["ter"])
    res = np.nan_to_num(ins30.res, nan=0.0).reshape(-1, 24 * 4)       # dias sem resíduo nunca são sorteados
    enc["res"] = codificar(res.reshape(1, -1), ESCALAS["res"])
    centro, cand = {}, {}
    for ano in anos:
        ins = ins30 if ano == 2030 else InsumosAno(ano)
        enc[f"A0_{ano}"] = codificar(ins.A0, ESCALAS["A0"])
        centro[str(ano)] = mc.centro_residuos(ins, 7).tolist()                 # 12 meses × 24 h × 4 séries
        cand.setdefault(str(ins.nd), candidatos(ins))
    mes30 = calendario(2030).month.to_numpy() - 1
    primeira = np.array([np.flatnonzero(mes30 == m)[0] for m in range(12)])
    hmin = [[float(x) for x in ins30.hmin[j][primeira]] for j in range(len(ins30.anos_h))]
    hmax = [[float(x) for x in ins30.hmax[j][primeira]] for j in range(len(ins30.anos_h))]
    for j in range(len(ins30.anos_h)):                               # limites mensais constantes no mês
        assert np.allclose(np.array(hmin[j])[mes30], ins30.hmin[j]) and np.allclose(np.array(hmax[j])[mes30], ins30.hmax[j])

    # insumos como a página os vê
    for k, e in enc.items():
        I[k] = decodificar(e)
    I["res"] = I["res"].reshape(-1)
    I["hmin"], I["hmax"], I["beta"] = np.array(hmin), np.array(hmax), np.array([float(b) for b in ins30.beta])

    # casos de referência para a autoverificação da página (um por ano, inclui o bissexto)
    rng = np.random.default_rng(cfa["simulador"]["semente_navegador"])
    verif = []
    for ano, cen_w, cen_dc, modo in [(2026, "base", "central", "regra_historica"), (2028, "alta", "alto", "regra_historica"),
                                     (2030, "base", "central", "regra_historica"), (2029, "baixa", "conservador", "plana"),
                                     (2027, "base", "sem_dc", "historico_sorteado")]:
        nd = I[f"A0_{ano}"].shape[1] // 24
        w, h = int(rng.integers(0, len(ins30.anos))), int(rng.integers(0, len(ins30.anos_h)))
        dias = np.empty(nd, dtype=int)
        for k, cnd in enumerate(cand[str(nd)]):
            j = int(rng.choice(cnd))
            L = min(7, nd - 7 * k)
            dias[7 * k:7 * k + L] = j + np.arange(L)
        out = motor(I, ano, w, h, dias, mc.expandir_centro(np.array(centro[str(ano)]), nd), niv[ano], cen_w, modo)
        verif.append({"ano": ano, "w": w, "h": h, "dias": dias.tolist(), "cenario_eolico": cen_w, "cenario_dc": cen_dc,
                      "hidro": modo, "esperado": metricas_ref(out["M0"] - niv[ano]["ldc"][cen_dc], c),
                      "M0_soma": float(out["M0"].sum())})

    dados = {
        "gerado_por": "python -m src.report.simulador",
        "anos": anos, "anos_clima": [int(x) for x in ins30.anos], "anos_hidro": [int(x) for x in ins30.anos_h],
        "cenarios_dc": CENARIOS_DC, "cenarios_eolicos": CENARIOS_EOL, "niveis": {str(k): v for k, v in niv.items()},
        "limite_exportacao_MW": c["intercambio"]["limite_exportacao_MW"]["valor"],
        "limites_importacao_MW": c["intercambio"]["limites_importacao_sensibilidade_MW"]["valores"],
        "beta": I["beta"].tolist(), "hmin": hmin, "hmax": hmax, "centro": centro, "candidatos": cand,
        "bloco_dias": 7, "semente": cfa["simulador"]["semente_navegador"],
        "mc": resumo_mc(), "mc_n": cfa["simulador"]["n_sorteios_mc"], "backtest": backtest(),
        "binarios": enc, "verificacao": verif,
    }
    js = "window.SIM_DADOS = " + json.dumps(dados, ensure_ascii=False, separators=(",", ":")) + ";\n"
    (saida / "dados.js").write_text(js, encoding="utf-8")
    shutil.copyfile(APP, saida / "index.html")
    print(f"{saida.relative_to(ROOT).as_posix()}: dados.js {len(js) / 1e6:.2f} MB; index.html")
    for v in verif:
        print(v["ano"], v["cenario_eolico"], v["cenario_dc"], v["hidro"], {k: round(x, 3) for k, x in v["esperado"].items()
                                                                            if k in ("importacao_TWh", "horas_importacao")})


if __name__ == "__main__":
    main()
