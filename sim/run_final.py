#!/usr/bin/env python3
"""ИМ-01: виртуальная модель устройства целиком с окончательными номиналами (после шага 1).

Запуск: python3 sim/run_final.py  →  sim/results_final.md и графики sim/out/final_*.png
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_sim import OUT, fmt, ok, read_wrdata, spice  # noqa: E402

TLOSS, TSTOP = 150e-3, 260e-3
C_TOTAL, ESR = 1410e-6 + 66e-6, 0.020 / 3
V_MIN, V_MAX = 3.4, 4.3  # Quectel EG800K: VBAT 3.4–4.3 В
DELAY_MAX = 3e-3
VIL, VIH = 0.99, 2.31


def pi_gains(fc: float) -> tuple[float, float]:
    w = 2 * math.pi * fc
    z = math.hypot(ESR, 1 / (w * C_TOTAL))
    kp = 1 / z
    return kp, kp * w / 5


def load(profile: str) -> str:
    """Пачки передачи от 5 мс до момента пропадания 12 В и немного после."""
    if profile == "P1":
        return "Iload vmod 0 PULSE(0 1.9 5m 5u 5u 577u 4.615m)"
    rnd = random.Random(7)
    pts = [(0.0, 0.0), (5e-3, 0.0)]
    t = 5e-3
    while t < TLOSS + 20e-3:
        amp = rnd.uniform(0.4, 1.0) if rnd.random() < 0.6 else 0.0
        pts += [(t + 20e-6, amp), (t + 980e-6, amp), (t + 1e-3, 0.0)]
        t += 1e-3
    return "Iload vmod 0 PWL(" + " ".join(f"{a:.6g} {b:.4g}" for a, b in pts) + ")"


CASES = [
    ("LTE-подобная передача, петля 2 кГц, CTR 130 % (EL817 ранг B, минимум)", "P2", 2e3, 1.3),
    ("LTE-подобная передача, петля 2 кГц, CTR 260 % (ранг B, максимум)", "P2", 2e3, 2.6),
    ("LTE-подобная передача, медленная петля 0.5 кГц", "P2", 0.5e3, 1.3),
    ("Худший случай §5.2: пачки 2 А по 577 мкс, петля 2 кГц", "P1", 2e3, 1.3),
    ("Худший случай §5.2: пачки 2 А по 577 мкс, медленная петля 0.5 кГц", "P1", 0.5e3, 1.3),
]


def main():
    rows = []
    for i, (label, prof, fc, ctr) in enumerate(CASES):
        kp, ki = pi_gains(fc)
        tag = f"final_{i}"
        m = spice("device_final.cir", tag,
                  dict(TLOSS=TLOSS, TSTOP=TSTOP, KP=f"{kp:.6g}", KI=f"{ki:.6g}", ILIM=2.5, CTR=ctr, RMCU=390),
                  dict(LOAD=load(prof)),
                  wrdata=["v(vmod)", "v(v33)", "v(vmcuin)", "v(vsense)", "v(vin)", "v(mcu_c)", "v(mcu_b)",
                          "v(ctl_c)", "v(ctl_b)"] if i in (0, 4) else None)
        g = m.get

        def rel(k, t0):
            return None if g(k) is None else g(k) - t0

        r = dict(label=label, vmin=g("vmod_min"), vmax=g("vmod_max"), v33=g("v33_min"),
                 c_start=rel("c_fall", 20.01e-3), c_end=rel("c_rise", 45.01e-3), c_spk=g("c_spk"),
                 b_start=rel("b_rise", 30.01e-3), b_end=rel("b_fall", 80.01e-3), b_spk=g("b_spk"),
                 t_sense=rel("t_sense", TLOSS), t_vmod=rel("t_vmod34", TLOSS),
                 t_v30=rel("t_v33_30", TLOSS), t_v27=rel("t_v33_27", TLOSS))
        delays = [r["c_start"], r["c_end"], r["b_start"], r["b_end"]]
        r["ok_vbat"] = r["vmin"] is not None and r["vmin"] >= V_MIN and r["vmax"] <= V_MAX
        r["ok_in"] = all(d is not None and 0 < d < DELAY_MAX for d in delays) and \
            r["c_spk"] is not None and r["c_spk"] > VIL and r["b_spk"] is not None and r["b_spk"] < VIH
        r["ok_mcu"] = r["v33"] is not None and r["v33"] > 3.2
        # запас: MCU узнаёт о пропадании (t_sense) и успевает до 2.7 В на FRAM
        hold = r["t_v27"] if r["t_v27"] is not None else (TSTOP - TLOSS)
        r["hold"] = hold
        r["ok_loss"] = r["t_sense"] is not None and r["t_sense"] + 3e-3 < hold
        rows.append(r)
        print(f"{i}: VBAT {fmt(r['vmin'], 1, '', 3)}…{fmt(r['vmax'], 1, '', 3)}  3V3 min {fmt(r['v33'], 1, '', 3)}  "
              f"датчик {fmt(r['t_sense'], 1e3, ' мс')}  MCU до 2.7 В {fmt(r['t_v27'], 1e3, ' мс')}", flush=True)

    plots = []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for i in (0, 4):
            d = read_wrdata(f"final_{i}")
            if not d:
                continue
            t = [x * 1e3 for x in d["time"]]
            fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
            ax = axes[0]
            ax.plot(t, d["v(vmod)"], label="VBAT модема")
            ax.plot(t, d["v(vmcuin)"], label="накопитель MCU (после BAT54)")
            ax.plot(t, d["v(v33)"], label="3.3 В MCU/FRAM")
            ax.axhline(V_MIN, ls="--", c="red", lw=0.8, label="минимум EG800K 3.4 В")
            ax.axhline(2.7, ls="--", c="purple", lw=0.8, label="минимум FRAM 2.7 В")
            ax.axvline(TLOSS * 1e3, ls=":", c="grey")
            ax.set_ylim(0, 4.6)
            ax.set_ylabel("В")
            ax.legend(fontsize=8, loc="lower left")
            ax.set_title(CASES[i][0])
            ax = axes[1]
            ax.plot(t, d["v(vin)"], label="вход преобразователя")
            ax.plot(t, [v * 11 for v in d["v(vsense)"]], label="датчик 12 В (×11)")
            ax.axvline(TLOSS * 1e3, ls=":", c="grey")
            ax.set_ylabel("В")
            ax.legend(fontsize=8)
            ax = axes[2]
            ax.plot(t, [3.3 * v for v in d["v(ctl_c)"]], alpha=0.5, label="выход монетника (1 = замкнут)")
            ax.plot(t, d["v(mcu_c)"], label="вход MCU: МОНЕТА (NO)")
            ax.plot(t, [3.3 * v - 3.6 for v in d["v(ctl_b)"]], alpha=0.5, label="выход купюрника (сдвиг)")
            ax.plot(t, [v - 3.6 for v in d["v(mcu_b)"]], label="вход MCU: КУПЮРА (NC), сдвиг −3.6 В")
            ax.set_xlabel("мс")
            ax.set_ylabel("В")
            ax.legend(fontsize=8, loc="lower right")
            for a in axes:
                a.grid(alpha=0.3)
            fig.tight_layout()
            path = OUT / f"final_{i}.png"
            fig.savefig(path, dpi=100)
            plt.close(fig)
            plots.append(path)
    except ImportError:
        pass

    L = ["# ИМ-01 — виртуальная модель устройства с окончательными номиналами (сгенерировано run_final.py)", "",
         "Одна схема ngspice на всё устройство: вход 12 В с защитой (mSMD050, SS36, SMBJ33A, 47 мкФ), LMR16020 "
         "(усреднённая модель, ограничение тока 2.5 А — нижняя граница по даташиту), VBAT: 2×22 мкФ + 3×470 мкФ "
         "полимер, модем EG800K-EU как нагрузка с пачками передачи, питание MCU через BAT54 и накопитель 470 мкФ, "
         "LDO 3.3 В, два оптронных входа (МОНЕТА — NO, КУПЮРА — NC) с подтяжкой 4.7 кОм, датчик 12 В 100к/10к. "
         f"В момент {TLOSS * 1e3:.0f} мс линия 12 В аппарата пропадает посреди передачи.", "",
         f"Критерии: VBAT {V_MIN}–{V_MAX} В (Quectel EG800K); задержка входного фильтра < 3 мс; спайк 0.2 мс не "
         "доходит до порога MCU; 3.3 В MCU не проседает при передаче (> 3.2 В); после пропадания 12 В датчик "
         "срабатывает, и у MCU остаётся не меньше 3 мс до 2.7 В (минимум FRAM), чтобы дописать счётчики.", "",
         "| Случай | VBAT мин / макс | 3.3 В MCU мин | Входы: задержки NO / NC | Спайк NO / NC | "
         "Датчик 12 В | MCU ≥ 2.7 В после пропадания | Итог |",
         "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        verdict = all((r["ok_vbat"], r["ok_in"], r["ok_mcu"], r["ok_loss"]))
        L.append(
            f"| {r['label']} | {fmt(r['vmin'], 1, '', 3)} / {fmt(r['vmax'], 1, '', 2)} В {'' if r['ok_vbat'] else '✘'} "
            f"| {fmt(r['v33'], 1, ' В', 3)} "
            f"| {fmt(r['c_start'], 1e3)}–{fmt(r['c_end'], 1e3)} / {fmt(r['b_start'], 1e3)}–{fmt(r['b_end'], 1e3)} мс "
            f"| {fmt(r['c_spk'], 1, '', 2)} / {fmt(r['b_spk'], 1, '', 2)} В "
            f"| {fmt(r['t_sense'], 1e3, ' мс')} "
            f"| {fmt(r['hold'], 1e3, ' мс')}{'' if r['t_v27'] is not None else ' и больше'} "
            f"| {ok(verdict)} |")
    L += ["", "✘ — не выполнен критерий по VBAT.", ""]
    if plots:
        L += ["Графики:", ""] + [f"- `sim/out/{p.name}`" for p in plots] + [""]
    (HERE / "results_final.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
