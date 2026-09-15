#!/usr/bin/env python3
"""Проверка design.py по библиотекам: у каждого вывода есть символ и площадка, ничего не забыто.

Запуск: python3 hardware/check_design.py — код возврата 1, если есть ошибки.
"""
from __future__ import annotations

import sys
from collections import Counter

import design
import kilib

errors, warnings = [], []
refs = Counter(p.ref for p in design.PARTS)
for ref, n in refs.items():
    if n > 1:
        errors.append(f"{ref}: позиционное обозначение повторяется {n} раз")

for p in design.PARTS:
    try:
        sym = kilib.symbol(p.symbol)
    except (KeyError, FileNotFoundError) as e:
        errors.append(f"{p.ref}: {e}")
        continue
    if not kilib.fp_path(p.footprint).exists():
        errors.append(f"{p.ref}: нет посадочного места {p.footprint}")
        continue
    sym_pins = {pin["number"] for pin in sym["pins"]}
    pads = {pad["number"] for pad in kilib.footprint_pads(p.footprint) if pad["number"]}
    listed = set(p.pins)
    for num in sorted(listed - sym_pins, key=lambda s: (len(s), s)):
        errors.append(f"{p.ref} ({p.symbol}): вывода {num} нет в символе")
    for num in sorted(sym_pins - listed, key=lambda s: (len(s), s)):
        warnings.append(f"{p.ref}: вывод {num} символа не описан в design.py (будет не подключён)")
    for num, net in p.pins.items():
        if net and num not in pads:
            errors.append(f"{p.ref} ({p.footprint}): вывод {num} → {net}, но площадки {num} нет")
    extra = sorted(pads - sym_pins, key=lambda s: (len(s), s))
    if extra:
        warnings.append(f"{p.ref}: площадки без вывода в символе: {' '.join(extra)}")
    if p.in_bom and not p.dnp and not p.lcsc:
        errors.append(f"{p.ref}: в перечне, но без артикула LCSC")

for net, members in design.nets().items():
    if len(members) < 2:
        errors.append(f"цепь {net} подключена только к {members[0][0]}.{members[0][1]}")

for w in warnings:
    print("предупреждение:", w)
for e in errors:
    print("ОШИБКА:", e)
print(f"деталей {len(design.PARTS)}, цепей {len(design.nets())}, ошибок {len(errors)}, предупреждений {len(warnings)}")
sys.exit(1 if errors else 0)
