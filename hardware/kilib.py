"""Чтение библиотек KiCad 9 без GUI: символы (с развёрнутым extends) и посадочные места.

Используется генераторами схемы и платы и проверкой design.py.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

HW = Path(__file__).resolve().parent
KICAD_SYM = Path("/usr/share/kicad/symbols")
KICAD_FP = Path("/usr/share/kicad/footprints")
LCSC_SYM = HW / "lib" / "lcsc.kicad_sym"
LCSC_FP = HW / "lib" / "lcsc.pretty"
LCSC_LIB = "im01_lcsc"


def balanced(src: str, start: int) -> str:
    """Сбалансированное S-выражение, начиная с '(' в позиции start; строки в кавычках учитываются."""
    depth, i, in_str = 0, start, False
    while i < len(src):
        ch = src[i]
        if in_str:
            if ch == "\\":
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise ValueError("несбалансированное выражение")


def _sym_file(nick: str) -> Path:
    return LCSC_SYM if nick == LCSC_LIB else KICAD_SYM / f"{nick}.kicad_sym"


@lru_cache(maxsize=None)
def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _raw_symbol(nick: str, name: str) -> str:
    src = _read(_sym_file(nick))
    m = re.search(r'\(symbol\s+"' + re.escape(name) + r'"', src)
    if not m:
        raise KeyError(f"символ {nick}:{name} не найден")
    return balanced(src, m.start())


def _rename(block: str, old: str, new_top: str, new_units: str) -> str:
    """Переименовать символ: верхний уровень в new_top, подъединицы old_N_M в new_units_N_M."""
    block = re.sub(r'\(symbol\s+"' + re.escape(old) + r'_(\d+)_(\d+)"',
                   lambda m: f'(symbol "{new_units}_{m.group(1)}_{m.group(2)}"', block)
    return re.sub(r'\(symbol\s+"' + re.escape(old) + r'"', f'(symbol "{new_top}"', block, count=1)


@lru_cache(maxsize=None)
def symbol(lib_id: str) -> dict:
    """Символ, готовый к вставке в lib_symbols схемы, и список его выводов."""
    nick, name = lib_id.split(":", 1)
    block = _raw_symbol(nick, name)
    ext = re.search(r'\(extends\s+"([^"]+)"\)', block)
    if ext:
        base = _raw_symbol(nick, ext.group(1))
        derived_props = {m.group(1): balanced(block, m.start()) for m in re.finditer(r'\(property\s+"([^"]+)"', block)}
        for key, prop in derived_props.items():
            m = re.search(r'\(property\s+"' + re.escape(key) + r'"', base)
            if m:
                old = balanced(base, m.start())
                base = base.replace(old, prop, 1)
        block = _rename(base, ext.group(1), name, name)
    safe = re.sub(r"[^A-Za-z0-9_.+-]", "_", name)
    text = _rename(block, name, lib_id, safe)
    pins = []
    for m in re.finditer(r"\(pin\s+(\w+)\s+(\w+)", text):
        pb = balanced(text, m.start())
        at = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)", pb)
        ln = re.search(r"\(length\s+([-\d.]+)\)", pb)
        nm = re.search(r'\(name\s+"([^"]*)"', pb)
        num = re.search(r'\(number\s+"([^"]*)"', pb)
        pins.append(dict(type=m.group(1), number=num.group(1), name=nm.group(1),
                         x=float(at.group(1)), y=float(at.group(2)), angle=float(at.group(3) or 0),
                         length=float(ln.group(1)) if ln else 0.0))
    xs = [p["x"] for p in pins] or [0.0]
    ys = [p["y"] for p in pins] or [0.0]
    return dict(lib_id=lib_id, text=text, pins=pins, bbox=(min(xs), min(ys), max(xs), max(ys)))


def fp_path(fp_id: str) -> Path:
    nick, name = fp_id.split(":", 1)
    if nick == LCSC_LIB:
        return LCSC_FP / f"{name}.kicad_mod"
    return KICAD_FP / f"{nick}.pretty" / f"{name}.kicad_mod"


@lru_cache(maxsize=None)
def footprint_pads(fp_id: str) -> list[dict]:
    src = _read(fp_path(fp_id))
    pads = []
    for m in re.finditer(r'\(pad\s+"?([^"\s)]*)"?\s+(\w+)', src):
        pb = balanced(src, m.start())
        at = re.search(r"\(at\s+([-\d.]+)\s+([-\d.]+)", pb)
        pads.append(dict(number=m.group(1), kind=m.group(2), x=float(at.group(1)), y=float(at.group(2))))
    return pads
