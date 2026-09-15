#!/usr/bin/env python3
"""Досоединение земляных площадок, оставшихся неподключёнными после автотрассировки.

Берёт из отчёта DRC (drc_en.rpt) площадки вида «Pad N [GND] of REF» и для каждой пробует:
  1) короткую дорожку к ближайшей земляной площадке той же детали (внутренние площадки модуля);
  2) переходное на нижний слой земли рядом с площадкой, отвод — не шире площадки (мелкий шаг).
Проверки зазоров те же, что в route.py.

Запуск: python3 fix_gnd.py   (после route.py и DRC)
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import pcbnew
from pcbnew import ToMM

import route

HW = Path(__file__).resolve().parent


def pad_xy(p):
    pos = p.GetPosition()
    return ToMM(pos.x) - route.OX, ToMM(pos.y) - route.OY


def short_side(p) -> float:
    bb = p.GetBoundingBox()
    return min(ToMM(bb.GetWidth()), ToMM(bb.GetHeight()))


def main():
    txt = (HW / "drc_en.rpt").read_text(encoding="utf-8")
    targets = sorted(set(re.findall(r"Pad (\S+) \[GND\] of (\w+)", txt)))
    if not targets:
        print("неподключённых земляных площадок нет — проверяю только обрывки заливки")
    route.board = board = pcbnew.LoadBoard(str(route.PCB))
    pads = route._pad_obstacles()
    fixed = []
    for num, ref in targets:
        fp = board.FindFootprintByReference(ref)
        pad = next(p for p in fp.Pads() if p.GetNumber() == num)
        px, py = pad_xy(pad)
        width = max(0.2, min(0.25, short_side(pad) * 0.8))
        done = False
        # 1) к соседней земляной площадке той же детали
        # pcbnew отдаёт новую обёртку на каждый запрос, поэтому «ту же площадку» узнаём по номеру и месту
        others = sorted(((math.hypot(ox - px, oy - py), (ox, oy)) for q in fp.Pads()
                         if q.GetNetname() == "GND" and q.GetNumber() != num
                         for ox, oy in [pad_xy(q)]), key=lambda t: t[0])
        for dist, (ox, oy) in others:
            if dist < 0.05:
                continue
            if dist > 2.6:
                break
            if route.segment_clear(px, py, ox, oy, "GND", width, pads, clearance=0.15):
                route.track("GND", [(px, py), (ox, oy)], width)
                fixed.append(f"{ref}.{num} → соседняя земляная площадка ({dist:.2f} мм)")
                done = True
                break
        # 2) переходное рядом
        if not done:
            c = fp.GetPosition()
            cx, cy = ToMM(c.x) - route.OX, ToMM(c.y) - route.OY
            base = math.atan2(py - cy, px - cx)
            half = max(ToMM(pad.GetBoundingBox().GetWidth()), ToMM(pad.GetBoundingBox().GetHeight())) / 2
            for k in range(16):
                ang = base + (k // 2) * (math.pi / 8) * (1 if k % 2 else -1)
                for d in (half + 0.45, half + 0.7, half + 1.0, half + 1.4, half + 1.9):
                    vx, vy = px + d * math.cos(ang), py + d * math.sin(ang)
                    if route.free_for_via(vx, vy, pads=pads, clearance=0.2, avoid_courtyards=False) and \
                            route.segment_clear(px, py, vx, vy, "GND", width, pads, clearance=0.15):
                        route.via("GND", vx, vy)
                        route.track("GND", [(px, py), (vx, vy)], width)
                        fixed.append(f"{ref}.{num} → переходное на нижний слой")
                        done = True
                        break
                if done:
                    break
        if not done:
            fixed.append(f"{ref}.{num} — места не нашлось, нужно вручную")
    route.fill_zones()
    route.prune_stitch()
    route.connect_islands()
    pcbnew.SaveBoard(str(route.PCB), board, True)
    print("\n".join(fixed))


if __name__ == "__main__":
    main()
