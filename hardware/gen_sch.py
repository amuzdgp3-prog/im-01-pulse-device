#!/usr/bin/env python3
"""Схема ИМ-01 (im01.kicad_sch) из design.py.

Каждый вывод получает глобальную метку с именем цепи, неподключённый — флажок «не подключён».
Так схема по построению совпадает с design.py, а KiCad сверяет её с платой (DRC --schematic-parity).
Детали сгруппированы по функциональным блокам с заголовками.
"""
from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path

import design
import kilib

HW = Path(__file__).resolve().parent
OUT = HW / "im01.kicad_sch"
GRID = 1.27
ROOT = str(uuid.uuid4())
PWR_FLAG_NETS = ["GND", "VIN", "VBAT", "VMCU_IN", "VIN_CONN", "VDD_EXT"]


def snap(v: float) -> float:
    return round(round(v / GRID) * GRID, 4)


def uid() -> str:
    return str(uuid.uuid4())


def q(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def label_len(net: str) -> float:
    return len(net) * 1.05 + 3.5


def label_rot(pin_angle: float) -> int:
    return int((pin_angle + 180) % 360)


def extents(sym: dict, pins_map: dict) -> tuple[float, float, float, float]:
    """Габарит символа вместе с метками в координатах схемы (y вниз) относительно точки вставки."""
    xs, ys = [], []
    for p in sym["pins"]:
        sx, sy = p["x"], -p["y"]
        xs.append(sx)
        ys.append(sy)
        net = pins_map.get(p["number"])
        length = label_len(net) if net else 2.0
        rot = label_rot(p["angle"])
        if rot == 0:
            xs.append(sx + length)
        elif rot == 180:
            xs.append(sx - length)
        elif rot == 90:
            ys.append(sy - length)
        else:
            ys.append(sy + length)
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if x1 - x0 < 10:
        x1 = x0 + 10
    return x0, y0 - 5, x1 + 8, y1 + 5


def prop(name: str, value: str, x: float, y: float, hide: bool = False, size: float = 1.27) -> str:
    h = " (hide yes)" if hide else ""
    return (f'\t\t(property {q(name)} {q(value)} (at {x} {y} 0)\n'
            f'\t\t\t(effects (font (size {size} {size})) (justify left){h}))\n')


def symbol_instance(lib_id: str, ref: str, value: str, footprint: str, x: float, y: float, sym: dict,
                    extra: dict[str, str], in_bom: bool, on_board: bool, dnp: bool) -> str:
    x0, y0, x1, y1 = (min(p["x"] for p in sym["pins"]), -max(p["y"] for p in sym["pins"]),
                      max(p["x"] for p in sym["pins"]), -min(p["y"] for p in sym["pins"]))
    narrow = x1 - x0 < 1
    if narrow:
        ref_at, val_at = (x + 2.54, y - 1.27), (x + 2.54, y + 1.27)
    else:
        ref_at, val_at = (x + x0, y + y0 - 2.54), (x + x0, y + y1 + 2.54)
    s = (f'\t(symbol (lib_id {q(lib_id)}) (at {x} {y} 0) (unit 1)\n'
         f'\t\t(exclude_from_sim no) (in_bom {"yes" if in_bom else "no"}) (on_board {"yes" if on_board else "no"})'
         f' (dnp {"yes" if dnp else "no"})\n'
         f'\t\t(uuid {q(uid())})\n')
    s += prop("Reference", ref, *ref_at)
    s += prop("Value", value, *val_at)
    s += prop("Footprint", footprint, x, y, hide=True)
    s += prop("Datasheet", "", x, y, hide=True)
    s += prop("Description", "", x, y, hide=True)
    for k, v in extra.items():
        s += prop(k, v, x, y, hide=True)
    for num in sorted({p["number"] for p in sym["pins"]}, key=lambda n: (len(n), n)):
        s += f'\t\t(pin {q(num)} (uuid {q(uid())}))\n'
    s += (f'\t\t(instances (project "im01" (path {q("/" + ROOT)} (reference {q(ref)}) (unit 1))))\n'
          f'\t)\n')
    return s


def global_label(net: str, x: float, y: float, rot: int) -> str:
    just = "left" if rot in (0, 90) else "right"
    return (f'\t(global_label {q(net)} (shape passive) (at {x} {y} {rot}) (fields_autoplaced yes)\n'
            f'\t\t(effects (font (size 1.27 1.27)) (justify {just}))\n'
            f'\t\t(uuid {q(uid())})\n'
            f'\t\t(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {x} {y} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes)))\n'
            f'\t)\n')


def no_connect(x: float, y: float) -> str:
    return f'\t(no_connect (at {x} {y}) (uuid {q(uid())}))\n'


def text(t: str, x: float, y: float, size: float = 2.54) -> str:
    return (f'\t(text {q(t)} (exclude_from_sim no) (at {x} {y} 0)\n'
            f'\t\t(effects (font (size {size} {size}) (bold yes)) (justify left))\n'
            f'\t\t(uuid {q(uid())})\n\t)\n')


def place_part(lib_id, ref, value, footprint, pins_map, x_left, y_top, extra, in_bom, on_board, dnp):
    sym = kilib.symbol(lib_id)
    ex = extents(sym, pins_map)
    x = snap(x_left - ex[0])
    y = snap(y_top - ex[1])
    body = symbol_instance(lib_id, ref, value, footprint, x, y, sym, extra, in_bom, on_board, dnp)
    for p in sym["pins"]:
        px, py = snap(x + p["x"]), snap(y - p["y"])
        net = pins_map.get(p["number"])
        body += global_label(net, px, py, label_rot(p["angle"])) if net else no_connect(px, py)
    return body, ex[2] - ex[0], ex[3] - ex[1]


def layout(sheet_w: float) -> tuple[str, float]:
    items = []
    blocks: list[str] = []
    for p in design.PARTS:
        if p.block not in blocks:
            blocks.append(p.block)
    margin, gap = 15.0, 6.0
    y = 25.0
    for block in blocks:
        items.append(text(block, margin, y))
        y += 8
        x, row_h = margin, 0.0
        for p in [p for p in design.PARTS if p.block == block]:
            sym = kilib.symbol(p.symbol)
            ex = extents(sym, p.pins)
            w, h = ex[2] - ex[0], ex[3] - ex[1]
            if x + w > sheet_w - margin and x > margin:
                x, y, row_h = margin, y + row_h + gap, 0.0
            extra = {"LCSC": p.lcsc, "MPN": p.mpn}
            if p.note:
                extra["Примечание"] = p.note
            body, w, h = place_part(p.symbol, p.ref, p.value, p.footprint, p.pins, x, y, extra,
                                    p.in_bom and not p.dnp, True, p.dnp)
            items.append(body)
            x += w + gap
            row_h = max(row_h, h)
        y += row_h + 14
    # флажки питания для ERC: цепи питания, у которых нет вывода-источника
    items.append(text("Флажки питания (ERC)", margin, y))
    y += 8
    x = margin
    for i, net in enumerate(PWR_FLAG_NETS, start=1):
        body, w, h = place_part("power:PWR_FLAG", f"#FLG{i:02d}", "PWR_FLAG", "", {"1": net}, x, y, {},
                                False, False, False)
        items.append(body)
        x += w + gap
    y += 25
    return "".join(items), y


def main():
    used = sorted({p.symbol for p in design.PARTS} | {"power:PWR_FLAG"})
    for paper, (w, h) in (("A2", (594, 420)), ("A1", (841, 594)), ("A0", (1189, 841))):
        body, height = layout(w)
        if height <= h - 15:
            break
    lib = "".join("\t\t" + kilib.symbol(s)["text"].replace("\n", "\n\t\t") + "\n" for s in used)
    doc = (f'(kicad_sch (version 20250114) (generator "im01-gen_sch") (generator_version "9.0")\n'
           f'\t(uuid {q(ROOT)})\n'
           f'\t(paper {q(paper)})\n'
           f'\t(title_block (title "ИМ-01 — устройство учёта импульсов") (date {q(date.today().isoformat())})'
           f' (rev "A") (company "apixspb.ru")\n'
           f'\t\t(comment 1 "Сгенерировано hardware/gen_sch.py из hardware/design.py — правки вносить в design.py"))\n'
           f'\t(lib_symbols\n{lib}\t)\n'
           f'{body}'
           f'\t(sheet_instances (path "/" (page "1")))\n'
           f'\t(embedded_fonts no)\n'
           f')\n')
    OUT.write_text(doc, encoding="utf-8")
    print(f"схема: {OUT.name}, лист {paper}, деталей {len(design.PARTS)}")


if __name__ == "__main__":
    main()
