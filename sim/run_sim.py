#!/usr/bin/env python3
"""ИМ-01, шаг 1 плана проверки: аналоговая симуляция в ngspice.

Прогоняет все сценарии, проверяет критерии приёмки из IM-01 §9 шаг 1 и пишет сводку
sim/results_auto.md, графики — в sim/out/ (если установлен matplotlib).

Запуск:  python3 sim/run_sim.py
Нужен ngspice (проверено на 42) в PATH.
"""
from __future__ import annotations

import math
import random
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

MEAS_RE = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*=\s*([-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)", re.M)


def spice(template: str, tag: str, params: dict, tokens: dict | None = None,
          wrdata: list[str] | None = None) -> dict[str, float]:
    text = (HERE / template).read_text(encoding="utf-8")
    text = text.replace("@PARAMS@", "\n".join(f".param {k}={v}" for k, v in params.items()))
    tokens = dict(tokens or {})
    tokens["WRDATA"] = ""
    if wrdata:
        tokens["WRDATA"] = ("set wr_singlescale\nset wr_vecnames\n"
                            f"wrdata {OUT / (tag + '.dat')} {' '.join(wrdata)}")
    for key, value in tokens.items():
        text = text.replace(f"@{key}@", str(value))
    cir = OUT / f"{tag}.cir"
    cir.write_text(text, encoding="utf-8")
    proc = subprocess.run(["ngspice", "-b", str(cir)], capture_output=True, text=True, timeout=900)
    log = proc.stdout + "\n" + proc.stderr
    (OUT / f"{tag}.log").write_text(log, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"ngspice завершился с ошибкой на {tag}, см. {OUT / (tag + '.log')}")
    return {m.group(1): float(m.group(2)) for m in MEAS_RE.finditer(log)}


def read_wrdata(tag: str) -> dict[str, list[float]] | None:
    for name in (f"{tag}.dat", f"{tag}.dat.data"):
        path = OUT / name
        if path.exists():
            break
    else:
        return None
    rows = [line.split() for line in path.read_text().splitlines() if line.strip()]
    header, data = rows[0], rows[1:]
    cols = list(zip(*[[float(x) for x in row] for row in data]))
    return {h: list(c) for h, c in zip(header, cols)}


def fmt(x, scale=1.0, unit="", digits=2):
    return "—" if x is None else f"{x * scale:.{digits}f}{unit}"


def ok(flag: bool) -> str:
    return "проходит" if flag else "**НЕ проходит**"


def lt(a, b):
    return a is not None and b is not None and a < b


def gt(a, b):
    return a is not None and b is not None and a > b


def diff(a, b):
    return None if a is None or b is None else a - b


# ------------------------------------------------------------------ входной каскад
T_START, T_END = 10.01e-3, 35.01e-3


def input_stage():
    base = dict(VLINE=12, RLED="2.2k", RF="10k", CF="100n")
    variants = [
        ("RPU 10 кОм, CTR 50 %, VDD 3.3 В — номинал §4", dict(VDD=3.3, RPU="10k", CTR=0.5)),
        ("RPU 10 кОм, CTR 20 % — деградация оптопары", dict(VDD=3.3, RPU="10k", CTR=0.2)),
        ("RPU 4.7 кОм, CTR 50 %, VDD 3.3 В", dict(VDD=3.3, RPU="4.7k", CTR=0.5)),
        ("RPU 4.7 кОм, CTR 20 % — деградация оптопары", dict(VDD=3.3, RPU="4.7k", CTR=0.2)),
        ("RPU 10 кОм, CTR 50 %, VDD 1.8 В", dict(VDD=1.8, RPU="10k", CTR=0.5)),
    ]
    results = []
    for i, (label, p) in enumerate(variants):
        vdd = p["VDD"]
        vil, vih = 0.3 * vdd, 0.7 * vdd
        tag = f"input_stage_{i}"
        m = spice("input_stage.cir", tag, {**base, **p}, {"VIL": vil, "VIH": vih},
                  wrdata=["v(ctrl_no)", "v(mcu_no)", "v(ctrl_nc)", "v(mcu_nc)"] if i == 0 else None)
        g = m.get
        r = dict(
            label=label, tag=tag, vdd=vdd, vil=vil, vih=vih,
            no_d_start=diff(g("no_fall"), T_START), no_d_end=diff(g("no_rise"), T_END),
            nc_d_start=diff(g("nc_rise"), T_START), nc_d_end=diff(g("nc_fall"), T_END),
            no_spk=g("no_spk"), nc_spk=g("nc_spk"),
            no_w25=diff(g("no_rise"), g("no_fall")), nc_w25=diff(g("nc_fall"), g("nc_rise")),
            no_w10=diff(g("no_r10"), g("no_f10")), nc_w10=diff(g("nc_f10"), g("nc_r10")),
            no_w100=diff(g("no_r100"), g("no_f100")), nc_w100=diff(g("nc_f100"), g("nc_r100")),
            no_low=g("no_low"), no_high=g("no_high"), nc_low=g("nc_low"), nc_high=g("nc_high"),
            iled=g("no_iled"), isink=g("no_isink"), nc_iled=g("nc_iled"),
            prled=max([x for x in (g("no_prled"), g("nc_prled")) if x is not None], default=None),
        )
        delays = [r["no_d_start"], r["no_d_end"], r["nc_d_start"], r["nc_d_end"]]
        r["delay_ok"] = all(d is not None and 0 < d < 3e-3 for d in delays)
        r["delay_max"] = max([d for d in delays if d is not None], default=None)
        # критерий §9: спайк не доходит до порога переключения входа MCU
        r["spike_ok"] = gt(r["no_spk"], vil) and lt(r["nc_spk"], vih)
        # строже: вход даже не выходит из зоны своего логического уровня
        r["spike_strict"] = gt(r["no_spk"], vih) and lt(r["nc_spk"], vil)
        r["levels_ok"] = (lt(r["no_low"], vil) and gt(r["no_high"], vih)
                          and lt(r["nc_low"], vil) and gt(r["nc_high"], vih))
        results.append(r)
    return results


def input_reverse():
    return spice("input_reverse.cir", "input_reverse", dict(RLED="2.2k"))


# ------------------------------------------------------------------ вход питания
SCENARIOS = {
    "hot12": ("Горячее подключение 12 В через кабель 1.5 мкГн",
              "Vs src 0 PWL(0 0 1u 0 1.1u 12)", dict(RSRC="50m"), ("20n", "300u", "50n")),
    "hot30": ("Горячее подключение 30 В",
              "Vs src 0 PWL(0 0 1u 0 1.1u 30)", dict(RSRC="50m"), ("20n", "300u", "50n")),
    "hot30_noel": ("Горячее подключение 30 В без входного электролита",
                   "Vs src 0 PWL(0 0 1u 0 1.1u 30)", dict(RSRC="50m", CIN_EL="1p", ESR_EL=1),
                   ("20n", "300u", "50n")),
    "rev30": ("Переполюсовка −30 В",
              "Vs src 0 PWL(0 0 1u 0 1.1u -30)", dict(RSRC="50m"), ("20n", "300u", "50n")),
    "surge50": ("Выброс +50 В / 2 Ом / 50 мкс поверх 12 В",
                "Vs src 0 PWL(0 12 100u 12 101u 62 151u 12)", dict(RSRC=2), ("20n", "400u", "50n")),
    "surge100": ("Стресс: +100 В / 10 Ом / 1 мс поверх 12 В",
                 "Vs src 0 PWL(0 12 100u 12 101u 112 1.1m 12)", dict(RSRC=10), ("100n", "2.5m", "200n")),
    "hot12_fuse": ("Горячее подключение 12 В, плавкий предохранитель 0.05 Ом",
                   "Vs src 0 PWL(0 0 1u 0 1.1u 12)", dict(RSRC="50m", RPTC=0.05), ("20n", "300u", "50n")),
    "hot12_fuse_noel": ("Горячее подключение 12 В, плавкий предохранитель, без электролита",
                        "Vs src 0 PWL(0 0 1u 0 1.1u 12)", dict(RSRC="50m", RPTC=0.05, CIN_EL="1p", ESR_EL=1),
                        ("20n", "300u", "50n")),
    "hot30_ptcmin": ("Горячее подключение 30 В, самовосст. предохранитель на минимуме 0.15 Ом",
                     "Vs src 0 PWL(0 0 1u 0 1.1u 30)", dict(RSRC="50m", RPTC=0.15), ("20n", "300u", "50n")),
    "hot30_fuse": ("Горячее подключение 30 В, плавкий предохранитель 0.05 Ом",
                   "Vs src 0 PWL(0 0 1u 0 1.1u 30)", dict(RSRC="50m", RPTC=0.05), ("20n", "300u", "50n")),
    "hot30_fuse_noel": ("Горячее подключение 30 В, плавкий предохранитель, без электролита",
                        "Vs src 0 PWL(0 0 1u 0 1.1u 30)", dict(RSRC="50m", RPTC=0.05, CIN_EL="1p", ESR_EL=1),
                        ("20n", "300u", "50n")),
    "rev30_fuse": ("Переполюсовка −30 В, плавкий предохранитель 0.05 Ом",
                   "Vs src 0 PWL(0 0 1u 0 1.1u -30)", dict(RSRC="50m", RPTC=0.05), ("20n", "300u", "50n")),
    "steady24": ("Постоянные 24 В на входе",
                 "Vs src 0 PWL(0 0 1u 0 1.1u 24)", dict(RSRC="50m"), ("20n", "2m", "100n")),
}

OPTIONS = {
    "A": dict(title="Вариант A — вход 9–30 В: TVS SMBJ33A, преобразователь класса 60 В",
              tvs=dict(TVS_BV=37.5, TVS_RS=1.2), vin_limit=60.0,
              scenarios=["hot12", "hot30", "hot30_noel", "hot30_ptcmin", "hot30_fuse", "hot30_fuse_noel",
                         "rev30", "rev30_fuse", "surge50", "surge100", "steady24"]),
    "B": dict(title="Вариант B — только 12 В (9–18 В): TVS SMBJ18A, MP1584 (рабочий вход до 28 В)",
              tvs=dict(TVS_BV=20.5, TVS_RS=0.4), vin_limit=28.0,
              scenarios=["hot12", "hot12_fuse", "hot12_fuse_noel", "rev30", "surge50", "surge100", "steady24"]),
}
SCHOTTKY_VRRM = 60.0
TVS_ENERGY_LIMIT = 0.4  # Дж, с запасом ~2x к SMBJ 600 Вт на импульсе 10/1000 мкс


def power_input():
    common = dict(LCAB="1.5u", RCAB="50m", RPTC=0.5, CIN_CER="10u", CIN_EL="47u", ESR_EL=0.4, PLOAD=0.5)
    out = {}
    for opt_key, opt in OPTIONS.items():
        rows = []
        for sc in opt["scenarios"]:
            title, src, extra, (tstep, tstop, tmax) = SCENARIOS[sc]
            params = {**common, **opt["tvs"], **extra}
            tstop_s = float(tstop.replace("u", "e-6").replace("m", "e-3"))
            tag = f"power_{opt_key}_{sc}"
            m = spice("power_input.cir", tag, params,
                      dict(SOURCE=src, TSTEP=tstep, TSTOP=tstop, TMAX=tmax, TEND0=f"{0.8 * tstop_s:.6g}"),
                      wrdata=["v(vin)", "v(nin)", "i(Vtvs)"] if sc in ("hot30", "hot30_noel", "surge50") else None)
            g = m.get
            vin_ok = lt(g("vin_max"), opt["vin_limit"]) and gt(g("vin_min"), -1.0)
            sch_ok = lt(g("vsch_rev"), SCHOTTKY_VRRM)
            tvs_ok = lt(g("etvs"), TVS_ENERGY_LIMIT) and lt(g("itvs_end"), 1e-3)
            rows.append(dict(sc=sc, title=title, m=m, vin_ok=vin_ok, sch_ok=sch_ok, tvs_ok=tvs_ok,
                             all_ok=vin_ok and sch_ok and tvs_ok))
        out[opt_key] = dict(opt=opt, rows=rows)
    return out


# ------------------------------------------------------------------ VBAT
CAPS = [(100e-6, 0.10), (220e-6, 0.06), (470e-6, 0.04), (1000e-6, 0.025), (2200e-6, 0.018)]
# 0.5–1 кГц — компенсация не перенастроена под большую ёмкость (частота среза падает обратно
# пропорционально Cout); 5–40 кГц — перенастроена.
FCS = [0.5e3, 1e3, 5e3, 15e3, 40e3]
ILIMS = [2.0, 3.0]
CCER = 22e-6
V_MOD_MIN, V_MOD_MIN_STRICT, V_MOD_MAX = 3.3, 3.4, 4.3


def pi_gains(fc: float, cb: float, esr: float) -> tuple[float, float]:
    """Пропорциональный коэффициент — такой, чтобы на частоте fc петля имела единичное усиление
    с реальным импедансом выходного конденсатора (ёмкость + ESR); ноль ПИ на fc/5."""
    w = 2 * math.pi * fc
    z = math.hypot(esr, 1 / (w * (cb + CCER)))
    kp = 1 / z
    return kp, kp * w / 5


def lte_like_profile() -> str:
    rnd = random.Random(1)
    pts = [(0.0, 0.0), (2e-3, 0.0)]
    t = 2e-3
    for _ in range(50):
        amp = rnd.uniform(0.4, 1.0) if rnd.random() < 0.6 else 0.0
        pts += [(t + 20e-6, amp), (t + 980e-6, amp), (t + 1e-3, 0.0)]
        t += 1e-3
    return "Iload vmod 0 PWL(" + " ".join(f"{a:.6g} {b:.4g}" for a, b in pts) + ")"


PROFILES = {
    "P1": ("GSM-подобный худший случай: пики 2 А по 577 мкс каждые 4.615 мс (расчёт §5.2)",
           "Iload vmod 0 PULSE(0 1.9 2m 5u 5u 577u 4.615m)", "58m"),
    "P2": ("LTE Cat.1-подобный: подкадры 1 мс, 0.5–1.1 А, случайная занятость 60 %",
           lte_like_profile(), "53m"),
    "P3": ("Длинный пик 2 А на 20 мс (регистрация/передача на максимальной мощности)",
           "Iload vmod 0 PWL(0 0 2m 0 2.02m 1.9 22m 1.9 22.02m 0)", "35m"),
}


def vbat_sweep():
    results = []
    for prof_key, (_, load, tstop) in PROFILES.items():
        for cb, esr in CAPS:
            for fc in FCS:
                for ilim in ILIMS:
                    kp, ki = pi_gains(fc, cb, esr)
                    tag = f"vbat_{prof_key}_{int(cb * 1e6)}u_{fc:.0f}Hz_{ilim:.0f}A"
                    wr = None
                    if cb == 1000e-6 and ilim == 3.0 and fc in (1e3, 15e3):
                        wr = ["v(vmod)", "v(bulk)", "v(il)"]
                    params = dict(CB=cb, ESRB=esr, KP=f"{kp:.6g}", KI=f"{ki:.6g}", ILIM=ilim,
                                  TAU_I="0.8u", RTRACE="10m", LTRACE="5n", CCER=CCER)
                    m = spice("vbat.cir", tag, params,
                              dict(LOAD=load, TSTEP="1u", TSTOP=tstop, TMAX="2u", TMEAS="1.5m"), wrdata=wr)
                    results.append(dict(profile=prof_key, cb=cb, esr=esr, fc=fc, ilim=ilim, tag=tag,
                                        vmin=m.get("vmod_min"), vmax=m.get("vmod_max"),
                                        ilmax=m.get("il_max")))
    return results


def holdup():
    kp, ki = pi_gains(15e3, 1000e-6, 0.025)
    small, big = "10 мкФ керамика + 47 мкФ электролит", "+100 мкФ"
    combos = [
        (57e-6, small, 0.1, "модем в ожидании, 100 мА", 0),
        (57e-6, small, 0.5, "идёт передача, 500 мА в среднем", 0),
        (57e-6, small, 0.5, "передача; модем отключается ключом, когда вход < 9 В", 1),
        (157e-6, big, 0.1, "модем в ожидании, 100 мА", 0),
        (157e-6, big, 0.5, "идёт передача, 500 мА в среднем", 0),
    ]
    rows = []
    for cin, cin_label, ibase, ib_label, shed in combos:
        tag = f"holdup_{int(cin * 1e6)}u_{int(ibase * 1000)}mA_shed{shed}"
        params = dict(CIN=cin, VDROP=0.5, EFF=0.85, ILIM=3.0, KP=f"{kp:.6g}", KI=f"{ki:.6g}",
                      TAU_I="0.8u", CB=1000e-6, ESRB=0.025, IBASE=ibase, SHED=shed)
        m = spice("holdup.cir", tag, params,
                  wrdata=["v(vin)", "v(bulk)", "v(vmcu)"] if (cin == 57e-6 and ibase == 0.1) else None)
        rel = {k: (None if m.get(k) is None else m[k] - 10e-3)
               for k in ("t_vin9", "t_vb33", "t_vb30", "t_mcu27")}
        rows.append(dict(cin_label=cin_label, ib_label=ib_label, **rel))
    return rows


# ------------------------------------------------------------------ графики
def plots(inp):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return []
    made = []

    d = read_wrdata("input_stage_0")
    if d:
        t = [x * 1e3 for x in d["time"]]
        vdd = inp[0]["vdd"]
        fig, axes = plt.subplots(2, 2, figsize=(12, 7))
        for row, ch in enumerate(("no", "nc")):
            for col, (lo, hi, name) in enumerate(((5, 45, "импульс 25 мс"), (59.5, 64, "спайк 0.2 мс"))):
                ax = axes[row][col]
                idx = [i for i, x in enumerate(t) if lo <= x <= hi]
                ax.plot([t[i] for i in idx], [d[f"v(ctrl_{ch})"][i] * vdd for i in idx],
                        label="выход акцептора (1 = замкнут), масштаб VDD", alpha=0.6)
                ax.plot([t[i] for i in idx], [d[f"v(mcu_{ch})"][i] for i in idx], label="вход MCU", lw=2)
                ax.axhline(0.3 * vdd, ls="--", c="grey", lw=0.8)
                ax.axhline(0.7 * vdd, ls="--", c="grey", lw=0.8)
                ax.set_title(f"{ch.upper()}: {name}")
                ax.set_xlabel("мс")
                ax.set_ylabel("В")
                ax.grid(alpha=0.3)
                if row == 0 and col == 0:
                    ax.legend(fontsize=8)
        fig.tight_layout()
        path = OUT / "input_stage.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        made.append(path)

    for prof, fc in [(p, f) for p in PROFILES for f in (1e3, 15e3)]:
        tag = f"vbat_{prof}_1000u_{fc:.0f}Hz_3A"
        d = read_wrdata(tag)
        if not d:
            continue
        t = [x * 1e3 for x in d["time"]]
        fig, ax1 = plt.subplots(figsize=(11, 4))
        ax1.plot(t, d["v(vmod)"], label="VBAT у выводов модуля", lw=1.5)
        ax1.axhline(V_MOD_MIN, ls="--", c="red", lw=0.9, label="минимум модуля 3.3 В")
        ax1.set_ylabel("В")
        ax1.set_xlabel("мс")
        ax2 = ax1.twinx()
        ax2.plot(t, d["v(il)"], c="orange", alpha=0.5, label="ток преобразователя, А")
        ax2.set_ylabel("А")
        ax1.set_title(f"{prof}: 1000 мкФ, частота среза {fc / 1e3:g} кГц, ограничение тока 3 А")
        ax1.grid(alpha=0.3)
        ax1.legend(loc="lower left", fontsize=8)
        ax2.legend(loc="lower right", fontsize=8)
        fig.tight_layout()
        path = OUT / f"vbat_{prof}_{fc:.0f}Hz.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        made.append(path)

    d = read_wrdata("holdup_57u_100mA_shed0")
    if d:
        t = [x * 1e3 for x in d["time"]]
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(t, d["v(vin)"], label="вход преобразователя")
        ax.plot(t, d["v(bulk)"], label="VBAT")
        ax.plot(t, d["v(vmcu)"], label="питание MCU/FRAM (LDO 3.3 В)")
        ax.axvline(10, ls=":", c="grey")
        ax.axhline(3.3, ls="--", c="red", lw=0.8)
        ax.axhline(2.7, ls="--", c="purple", lw=0.8)
        ax.set_xlim(0, 60)
        ax.set_xlabel("мс")
        ax.set_ylabel("В")
        ax.set_title("Пропадание 12 В в 10 мс: модем в ожидании (100 мА), вход 10+47 мкФ")
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = OUT / "holdup.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        made.append(path)

    for tag in ("power_A_hot30", "power_A_hot30_noel", "power_A_surge50"):
        d = read_wrdata(tag)
        if not d:
            continue
        t = [x * 1e6 for x in d["time"]]
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(t, d["v(nin)"], label="разъём устройства", alpha=0.6)
        ax.plot(t, d["v(vin)"], label="вход преобразователя", lw=1.5)
        ax.set_xlabel("мкс")
        ax.set_ylabel("В")
        ax.set_title(tag)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        path = OUT / f"{tag}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        made.append(path)
    return made


# ------------------------------------------------------------------ отчёт
def report(inp, rev, pwr, vb, hold, pics) -> str:
    L = []
    ver = subprocess.run(["ngspice", "-v"], capture_output=True, text=True).stdout.splitlines()
    ver = next((s.strip("* ").strip() for s in ver if "ngspice" in s.lower()), "ngspice")
    L += ["# ИМ-01, шаг 1 — сводка аналоговой симуляции (сгенерировано run_sim.py)", "",
          f"Симулятор: {ver}. Файл перезаписывается при каждом прогоне.", ""]

    L += ["## 1. Входной каскад: задержка фильтра и подавление спайка", "",
          "Пороги входа MCU — худший случай STM32: низкий уровень ≤ 0.3·VDD, высокий ≥ 0.7·VDD.",
          "Задержка — от фронта на выходе акцептора до пересечения худшего порога на входе MCU.", "",
          "Спайк: критерий §9 — не доходит до порога переключения (NO: остаётся выше 0.3·VDD, NC: ниже 0.7·VDD); "
          "строже — вход вообще не выходит из зоны своего уровня.", "",
          "| Вариант | NO: начало / конец | NC: начало / конец | Спайк 0.2 мс: NO мин. / NC макс. | Уровни | Задержка < 3 мс | Спайк подавлен (§9) | Строже |",
          "|---|---|---|---|---|---|---|---|"]
    for r in inp:
        L.append(f"| {r['label']} | {fmt(r['no_d_start'], 1e3, ' мс')} / {fmt(r['no_d_end'], 1e3, ' мс')} "
                 f"| {fmt(r['nc_d_start'], 1e3, ' мс')} / {fmt(r['nc_d_end'], 1e3, ' мс')} "
                 f"| {fmt(r['no_spk'], 1, ' В')} / {fmt(r['nc_spk'], 1, ' В')} "
                 f"| {ok(r['levels_ok'])} | {ok(r['delay_ok'])} | {ok(r['spike_ok'])} | {ok(r['spike_strict'])} |")
    L += ["", "Длительность импульса, которую увидит прошивка (важно для порога 10 мс из §7):", "",
          "| Вариант | NO: 10 / 25 / 100 мс | NC: 10 / 25 / 100 мс |", "|---|---|---|"]
    for r in inp:
        L.append(f"| {r['label']} | {fmt(r['no_w10'], 1e3)} / {fmt(r['no_w25'], 1e3)} / {fmt(r['no_w100'], 1e3)} мс "
                 f"| {fmt(r['nc_w10'], 1e3)} / {fmt(r['nc_w25'], 1e3)} / {fmt(r['nc_w100'], 1e3)} мс |")
    r0 = inp[0]
    L += ["", f"Нагрузка на линию акцептора (номинал): ток светодиода {fmt(r0['iled'], 1e3, ' мА')}, "
              f"суммарный ток открытого коллектора (наш канал + штатная подтяжка 10 кОм) {fmt(r0['isink'], 1e3, ' мА')}; "
              f"в режиме NC светодиод горит постоянно, средний ток {fmt(r0['nc_iled'], 1e3, ' мА')}; "
              f"мощность на резисторе 2.2 кОм до {fmt(r0['prled'], 1e3, ' мВт')}.", ""]

    g = rev.get
    L += ["## 2. Ошибки монтажа и 24 В на линии импульса", "",
          "Предельное обратное напряжение светодиода PC817 — 6 В.", "",
          "| Случай | Результат |", "|---|---|",
          f"| Штатно, только диод параллельно светодиоду (§4) | ток светодиода {fmt(g('n1_iled'), 1e3, ' мА')}, линия аппарата в покое {fmt(g('ref_line'), 1, ' В')} |",
          f"| Штатно, + последовательный диод | ток светодиода {fmt(g('n2_iled'), 1e3, ' мА')} |",
          f"| A: перепутаны «+12 В» и «импульс», диод есть | обратное на светодиоде {fmt(g('a_vr'), 1, ' В')} — {ok(lt(g('a_vr'), 6))}; линия аппарата в покое {fmt(g('a_line'), 1, ' В')}; импульсы не видны (LED1 не мигает — ошибка видна на монтаже) |",
          f"| B: то же, диода нет | обратное на светодиоде {fmt(g('b_vr'), 1, ' В')} — {ok(lt(g('b_vr'), 6))} |",
          f"| C1: перепутаны «+12 В» и GND, только параллельный диод | обратное {fmt(g('c1_vr'), 1, ' В')}; **линия аппарата в покое проседает до {fmt(g('c1_line'), 1, ' В')}** (штатно {fmt(g('ref_line'), 1, ' В')}) |",
          f"| C2: то же, + последовательный диод | обратное {fmt(g('c2_vr'), 1, ' В')}; линия аппарата в покое {fmt(g('c2_line'), 1, ' В')} |",
          f"| D: линия 24 В, режим NC | ток светодиода {fmt(g('d_iled'), 1e3, ' мА')}, мощность на 2.2 кОм {fmt(g('d_p'), 1e3, ' мВт')} (0805 — 125 мВт, 1206 — 250 мВт) |",
          ""]

    L += ["## 3. Защита входа питания", "",
          f"Критерии: пик на входе преобразователя ниже его предела; обратное на диоде Шоттки < {SCHOTTKY_VRRM:.0f} В; "
          f"энергия в TVS < {TVS_ENERGY_LIMIT} Дж и нет постоянного тока через TVS.", ""]
    for key, block in pwr.items():
        opt = block["opt"]
        L += [f"### {opt['title']}", "",
              f"Предел по входу преобразователя: {opt['vin_limit']:.0f} В.", "",
              "| Сценарий | Пик / минимум на входе преобр. | Обратное на Шоттки | Ток TVS макс. | Энергия TVS | Ток TVS в конце | Итог |",
              "|---|---|---|---|---|---|---|"]
        for row in block["rows"]:
            m = row["m"].get
            L.append(f"| {row['title']} | {fmt(m('vin_max'), 1, ' В', 1)} / {fmt(m('vin_min'), 1, ' В', 1)} "
                     f"| {fmt(m('vsch_rev'), 1, ' В', 1)} | {fmt(m('itvs_max'), 1, ' А')} "
                     f"| {fmt(m('etvs'), 1e3, ' мДж', 1)} | {fmt(m('itvs_end'), 1e3, ' мА', 2)} | {ok(row['all_ok'])} |")
        L.append("")

    L += ["## 4. Просадка VBAT у выводов модуля", "",
          f"Критерий: минимум не ниже {V_MOD_MIN} В (минимум питания Cat.1-модулей класса Air780E — "
          f"уточнить по даташиту выбранного SKU); для запаса показан и {V_MOD_MIN_STRICT} В. "
          f"Выброс при сбросе нагрузки не выше {V_MOD_MAX} В. "
          f"Дорожка до модуля 10 мОм / 5 нГн, керамика 22 мкФ у выводов.", ""]
    L += ["Частота среза петли перебирается, потому что компенсацию конкретной микросхемы модель не знает: "
          "0.5–1 кГц — случай, когда компенсацию из даташита не перенастроили под большую ёмкость "
          "(частота среза падает обратно пропорционально ёмкости выхода), 5–40 кГц — перенастроили.", ""]
    for prof_key, (title, _, _) in PROFILES.items():
        rows = [x for x in vb if x["profile"] == prof_key]
        L += [f"### {prof_key}. {title}", ""]
        for il in ILIMS:
            L += [f"Ограничение тока преобразователя {il:.0f} А. Минимум / максимум VBAT у модуля, В; "
                  "столбцы — частота среза петли.", "",
                  "| Объёмная ёмкость (ESR) | " + " | ".join(f"{fc / 1e3:g} кГц" for fc in FCS) + " |",
                  "|---|" + "---|" * len(FCS)]
            for cb, esr in CAPS:
                cells = []
                for fc in FCS:
                    x = next(v for v in rows if v["cb"] == cb and v["fc"] == fc and v["ilim"] == il)
                    mark = "" if gt(x["vmin"], V_MOD_MIN) and lt(x["vmax"], V_MOD_MAX) else " ✘"
                    cells.append(f"{fmt(x['vmin'], 1, '', 3)} / {fmt(x['vmax'], 1, '', 2)}{mark}")
                L.append(f"| {cb * 1e6:.0f} мкФ ({esr * 1e3:.0f} мОм) | " + " | ".join(cells) + " |")
            L.append("")
    L += ["✘ — не выполнен хотя бы один критерий.", ""]

    L += ["## 5. Удержание питания при пропадании линии 12 В", "",
          "Время отсчитывается от пропадания 12 В. Объёмная ёмкость 1000 мкФ.", "",
          "| Вход | Нагрузка | Вход < 9 В | VBAT < 3.3 В (модем) | VBAT < 3.0 В | Питание MCU/FRAM < 2.7 В |",
          "|---|---|---|---|---|---|"]
    for r in hold:
        L.append(f"| {r['cin_label']} | {r['ib_label']} | {fmt(r['t_vin9'], 1e3, ' мс')} | {fmt(r['t_vb33'], 1e3, ' мс')} "
                 f"| {fmt(r['t_vb30'], 1e3, ' мс')} | {fmt(r['t_mcu27'], 1e3, ' мс')} |")
    L.append("")

    if pics:
        L += ["## Графики", ""] + [f"- `sim/out/{p.name}`" for p in pics] + [""]
    return "\n".join(L)


def main():
    print("входной каскад…", flush=True)
    inp = input_stage()
    print("ошибки монтажа…", flush=True)
    rev = input_reverse()
    print("вход питания…", flush=True)
    pwr = power_input()
    print("VBAT (перебор)…", flush=True)
    vb = vbat_sweep()
    print("удержание…", flush=True)
    hold = holdup()
    pics = plots(inp)
    text = report(inp, rev, pwr, vb, hold, pics)
    (HERE / "results_auto.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
