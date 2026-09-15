#!/usr/bin/env python3
"""Файлы для производства ИМ-01 (JLCPCB): гербер-файлы, сверловка, BOM, расстановка, PDF, 3D.

Запуск: python3 hardware/fab.py   →   hardware/fab/
  im01_gerbers.zip          — гербер-файлы и сверловка: загружать на jlcpcb.com как есть
  im01_bom_jlcpcb.csv       — перечень для монтажа (Comment, Designator, Footprint, LCSC Part #)
  im01_cpl_jlcpcb.csv       — координаты и повороты деталей (Designator, Mid X, Mid Y, Layer, Rotation)
  im01_schematic.pdf        — схема
  im01_assembly_top.pdf     — сборочный чертёж, верхняя сторона
  im01_3d_top.png, _bottom  — 3D-вид платы (если рендер доступен)
  im01.step                 — 3D-модель платы для проверки корпуса
"""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import design

HW = Path(__file__).resolve().parent
PCB = HW / "im01.kicad_pcb"
SCH = HW / "im01.kicad_sch"
FAB = HW / "fab"
GERB = FAB / "gerbers"
ENV = {**os.environ, "KICAD9_3DMODEL_DIR": "/usr/share/kicad/3dmodels", "LC_ALL": "C", "LANG": "C"}


def run(args: list[str], optional: bool = False) -> bool:
    r = subprocess.run(["kicad-cli", *args], capture_output=True, text=True, env=ENV, timeout=600)
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()[-3:]
        if optional:
            print("  пропущено:", " ".join(args[:3]), "—", " ".join(msg))
            return False
        raise SystemExit(f"kicad-cli {' '.join(args)}\n" + "\n".join(msg))
    return True


def gerbers():
    shutil.rmtree(GERB, ignore_errors=True)
    GERB.mkdir(parents=True)
    run(["pcb", "export", "gerbers", "--layers",
         "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts",
         "--subtract-soldermask", "-o", str(GERB) + "/", str(PCB)])
    run(["pcb", "export", "drill", "--format", "excellon", "--excellon-units", "mm",
         "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2",
         "-o", str(GERB) + "/", str(PCB)])
    z = FAB / "im01_gerbers.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(GERB.iterdir()):
            zf.write(f, f.name)
    print(f"  {z.name}: {len(list(GERB.iterdir()))} файлов")


def bom_jlc():
    rows: dict[str, dict] = {}
    for p in design.PARTS:
        if not p.in_bom or p.dnp:
            continue
        key = p.lcsc
        r = rows.setdefault(key, dict(comment=p.value if p.symbol.startswith("Device:") else p.mpn,
                                      refs=[], footprint=p.footprint.split(":", 1)[1], lcsc=p.lcsc))
        r["refs"].append(p.ref)
    out = FAB / "im01_bom_jlcpcb.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for r in rows.values():
            w.writerow([r["comment"], ",".join(sorted(r["refs"], key=lambda s: (s.rstrip('0123456789'),
                                                                             int(''.join(c for c in s if c.isdigit()) or 0)))),
                        r["footprint"], r["lcsc"]])
    print(f"  {out.name}: {len(rows)} позиций")


def cpl_jlc():
    raw = FAB / "pos_raw.csv"
    run(["pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "front", "--exclude-dnp",
         "--use-drill-file-origin", "-o", str(raw), str(PCB)])
    skip = {p.ref for p in design.PARTS if not p.in_bom or p.dnp}
    out = FAB / "im01_cpl_jlcpcb.csv"
    n = 0
    with raw.open(encoding="utf-8") as fi, out.open("w", newline="", encoding="utf-8") as fo:
        w = csv.writer(fo)
        w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        for row in csv.DictReader(fi):
            if row["Ref"] in skip:
                continue
            w.writerow([row["Ref"], f"{float(row['PosX']):.4f}mm", f"{float(row['PosY']):.4f}mm",
                        "Top" if row["Side"].lower().startswith("top") else "Bottom", f"{float(row['Rot']):.1f}"])
            n += 1
    raw.unlink()
    print(f"  {out.name}: {n} деталей")


def docs():
    run(["sch", "export", "pdf", "-o", str(FAB / "im01_schematic.pdf"), str(SCH)])
    run(["pcb", "export", "pdf", "--layers", "F.Fab,F.Silkscreen,Edge.Cuts", "--mode-single",
         "-o", str(FAB / "im01_assembly_top.pdf"), str(PCB)], optional=True)
    run(["pcb", "export", "step", "--subst-models", "-o", str(FAB / "im01.step"), str(PCB)], optional=True)
    for side in ("top", "bottom"):
        run(["pcb", "render", "--side", side, "--quality", "high", "--width", "1600", "--height", "1100",
             "--background", "opaque", "-o", str(FAB / f"im01_3d_{side}.png"), str(PCB)], optional=True)


def main():
    FAB.mkdir(exist_ok=True)
    print("гербер-файлы и сверловка")
    gerbers()
    print("BOM и расстановка для JLCPCB")
    bom_jlc()
    cpl_jlc()
    print("документы и 3D")
    docs()
    print("готово:", FAB)


if __name__ == "__main__":
    main()
