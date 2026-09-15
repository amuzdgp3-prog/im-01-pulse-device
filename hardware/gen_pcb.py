#!/usr/bin/env python3
"""Плата ИМ-01 (im01.kicad_pcb) из design.py: расстановка, контур, крепёж, надписи, заливки.

Трассировка — отдельно: критичные цепи руками (route_manual.py), остальное — Freerouting (route_auto.py).
Координаты в таблице PLACE — миллиметры от левого верхнего угла платы, ось Y вниз, поворот в градусах
против часовой стрелки, как в KiCad.
"""
from __future__ import annotations

from pathlib import Path

import pcbnew
from pcbnew import FromMM, VECTOR2I

import design
import kilib

HW = Path(__file__).resolve().parent
PCB = HW / "im01.kicad_pcb"
OX, OY = 100.0, 100.0
W, H = 80.0, 55.0

PLACE: dict[str, tuple[float, float, float]] = {
    # разъёмы по левому краю и крепёж
    "J1": (4.5, 10.0, 270), "J2": (4.5, 28.0, 270), "J3": (4.5, 40.0, 270),
    "H1": (3.5, 3.5, 0), "H2": (76.5, 3.5, 0), "H3": (3.5, 51.5, 0), "H4": (76.5, 51.5, 0),
    # защита входа
    "F1": (12.3, 10.0, 90), "D2": (16.9, 10.0, 90), "D1": (12.3, 17.0, 90), "C1": (18.8, 19.5, 0),
    "C2": (20.6, 9.0, 90), "C3": (23.0, 9.0, 90),
    # преобразователь; U1 повёрнут на 270°: слева BOOT/VIN/EN/RT, справа SW/GND/PGOOD/FB
    "U1": (30.0, 8.0, 270), "C4": (25.2, 7.4, 270), "C5": (30.0, 3.8, 0),
    "R1": (26.2, 14.0, 90), "R2": (27.9, 14.0, 90), "R3": (29.6, 14.0, 90),
    "R4": (31.3, 14.0, 90), "R5": (33.0, 14.0, 90),
    "L1": (39.5, 7.5, 0), "D3": (36.2, 14.4, 270), "C6": (45.0, 5.0, 90), "C7": (45.0, 10.0, 90),
    # VBAT: три полимерных конденсатора, стабилитрон, массив у выводов модема
    "C8": (52.0, 7.0, 90), "C9": (60.0, 7.0, 90), "C33": (67.5, 7.0, 90), "D4": (73.3, 11.5, 90),
    "C12": (54.6, 12.6, 0), "C13": (56.5, 12.6, 0), "C31": (58.4, 12.6, 0), "C32": (60.3, 12.6, 0),
    "C10": (53.8, 14.9, 0), "C11": (58.6, 14.9, 0),
    "D5": (48.5, 15.0, 0),
    # модем и антенна
    "U7": (60.0, 25.0, 0),
    "R26": (70.0, 18.4, 0), "C28": (69.0, 20.2, 270), "C29": (72.6, 20.2, 270), "J5": (75.5, 18.4, 0),
    # SIM
    # U8 развёрнут: земляной вывод 2 смотрит вправо, в свободное место под модемом
    "J4": (60.0, 45.0, 0), "U8": (51.5, 37.5, 180), "R30": (48.3, 38.6, 90),
    # R23–R25 развёрнуты: вывод со стороны модема (1) — справа, к модему; линии SIM прямые и короткие
    "R23": (50.2, 29.4, 180), "R24": (50.2, 31.0, 180), "R25": (50.2, 32.6, 180),
    "C24": (50.0, 41.0, 90), "C25": (50.0, 44.0, 90), "C26": (50.0, 46.5, 90), "C27": (50.0, 49.0, 90),
    # питание MCU
    "U2": (27.0, 23.0, 0), "C15": (24.0, 23.0, 90), "C16": (27.0, 26.2, 0), "C14": (31.5, 44.8, 0),
    # MCU, FRAM, транслятор уровней
    "U3": (37.0, 31.0, 0), "C17": (29.0, 28.8, 90), "C18": (30.9, 30.6, 90), "C20": (29.3, 32.6, 90),
    "R6": (28.5, 38.5, 90), "R7": (30.2, 38.5, 90), "C19": (31.9, 38.5, 90),
    # U9 развёрнут: земляной вывод 2 смотрит вправо, в свободное место (слева тесно — датчик 12 В)
    "U9": (36.0, 39.5, 180), "C34": (38.0, 36.95, 0), "C35": (34.2, 36.95, 0),
    "U4": (37.5, 21.0, 0), "C21": (42.0, 20.0, 90), "R10": (42.0, 23.0, 90),
    # управление модемом и SWD
    "J6": (46.3, 19.0, 0),
    "Q1": (47.5, 24.0, 0), "R18": (44.5, 24.5, 90), "R19": (44.5, 27.6, 90),
    "Q2": (46.6, 32.0, 0), "R20": (43.2, 33.0, 90), "R21": (43.2, 36.1, 90), "R22": (47.5, 36.2, 0),
    # вход МОНЕТА
    "R11": (10.5, 26.0, 0), "D6": (10.5, 29.0, 0), "D7": (10.5, 32.0, 0), "U5": (19.5, 29.5, 0),
    "R12": (22.0, 34.5, 90), "R13": (24.0, 34.5, 90), "C22": (26.0, 34.5, 90),
    # вход КУПЮРА
    "R14": (10.5, 38.5, 0), "D8": (10.5, 41.5, 0), "D9": (10.5, 44.5, 0), "U6": (19.5, 42.0, 0),
    "R15": (22.0, 47.0, 90), "R16": (24.0, 47.0, 90), "C23": (26.0, 47.0, 90),
    # индикация и кнопка
    "D10": (30.0, 52.4, 0), "R27": (30.0, 50.2, 0), "D11": (34.0, 52.4, 0), "R28": (34.0, 50.2, 0),
    "SW1": (42.5, 48.5, 0), "R29": (38.5, 44.0, 90), "C30": (40.2, 44.0, 90),
    # контрольные точки
    "TP1": (15.0, 3.8, 0), "TP2": (47.45, 11.5, 0), "TP3": (31.0, 23.8, 0), "TP4": (8.0, 3.8, 0),
    "TP5": (44.5, 41.0, 0), "TP6": (46.5, 41.0, 0),     "TP9": (71.0, 27.0, 0), "TP10": (71.0, 29.0, 0), "TP11": (71.0, 31.0, 0), "TP12": (71.0, 33.0, 0),
    "TP13": (57.8, 35.3, 0),
}

# надписи: (текст, x, y, высота мм, сторона, поворот)
TEXTS = [
    ("apixspb.ru", 40.0, 20.0, 4.0, "B", 0),
    ("ИМ-01  устройство учёта импульсов", 40.0, 27.0, 1.8, "B", 0),
    ("rev.A  09.2026", 40.0, 31.0, 1.5, "B", 0),
    ("ПИТ 9-30В", 4.5, 6.2, 1.0, "F", 0),
    ("МОНЕТА", 4.5, 24.6, 1.0, "F", 0),
    ("КУПЮРА", 4.5, 36.6, 1.0, "F", 0),
    ("ИМП", 26.8, 52.4, 0.9, "F", 0),
    ("СЕТЬ", 37.3, 52.4, 0.9, "F", 0),
    ("ВЫГРУЗКА", 42.5, 44.9, 0.9, "F", 0),
    ("ANT", 75.5, 15.6, 0.9, "F", 0),
    ("SIM", 60.0, 53.6, 0.9, "F", 0),
    ("apixspb.ru", 14.0, 53.4, 1.2, "F", 0),
]


def P(x: float, y: float) -> VECTOR2I:
    return VECTOR2I(FromMM(OX + x), FromMM(OY + y))


def fix_models(fp, footprint_id: str | None = None) -> None:
    """Пути 3D-моделей LCSC — относительно проекта (.step). Список пересоздаётся целиком:
    присваивание m_Filename элементу fp.Models() меняет временную копию, а не модель."""
    if footprint_id is not None and footprint_id.split(":", 1)[0] != kilib.LCSC_LIB:
        return
    rebuilt = []
    for m in fp.Models():
        if m.m_Filename.startswith("${"):
            return
        nm = pcbnew.FP_3DMODEL()
        nm.m_Filename = f"${{KIPRJMOD}}/lib/lcsc.3dshapes/{Path(Path(m.m_Filename).name).with_suffix('.step').name}"
        nm.m_Scale, nm.m_Rotation, nm.m_Offset = m.m_Scale, m.m_Rotation, m.m_Offset
        nm.m_Show = True
        rebuilt.append(nm)
    if not rebuilt:
        return
    fp.Models().clear()
    for nm in rebuilt:
        fp.Add3DModel(nm)


def add_field(fp, name: str, value: str) -> None:
    if not value:
        return
    try:
        field = pcbnew.PCB_FIELD(fp, fp.GetNextFieldId(), name)
    except (AttributeError, TypeError):
        field = pcbnew.PCB_FIELD(fp, fp.GetFieldCount(), name)
    field.SetText(value)
    field.SetVisible(False)
    field.SetLayer(pcbnew.F_Fab)
    fp.AddField(field)


def build() -> pcbnew.BOARD:
    board = pcbnew.BOARD()
    netinfo = {}
    for name in sorted(design.nets()):
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        netinfo[name] = ni

    missing = [p.ref for p in design.PARTS if p.ref not in PLACE]
    if missing:
        raise SystemExit(f"нет координат для: {' '.join(missing)}")
    extra = sorted(set(PLACE) - {p.ref for p in design.PARTS})
    if extra:
        print("предупреждение: координаты для несуществующих деталей:", " ".join(extra))

    for p in design.PARTS:
        nick, name = p.footprint.split(":", 1)
        fp = pcbnew.FootprintLoad(str(kilib.fp_path(p.footprint).parent), name)
        fp.SetFPID(pcbnew.LIB_ID(nick, name))
        fp.SetReference(p.ref)
        fp.SetValue(p.value)
        x, y, rot = PLACE[p.ref]
        fp.SetPosition(P(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetDNP(p.dnp)
        fp.SetExcludedFromBOM(not p.in_bom)
        fp.SetExcludedFromPosFiles(not p.in_bom)
        add_field(fp, "LCSC", p.lcsc)
        add_field(fp, "MPN", p.mpn)
        fix_models(fp, p.footprint)
        fp.Value().SetVisible(False)
        # обозначения 0.8 мм (минимум JLCPCB для читаемой шелкографии) — меньше наложений у мелочи
        fp.Reference().SetTextSize(VECTOR2I(FromMM(0.8), FromMM(0.8)))
        fp.Reference().SetTextThickness(FromMM(0.15))
        if p.ref == "U1":
            # преобразователь: сплошное соединение с заливкой — отвод тепла через площадку и вывод 7
            fp.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        board.Add(fp)
        # безымянные металлизированные отверстия (теплоотвод под корпусом) — в цепь центральной площадки
        ep_net = None
        for pad in fp.Pads():
            if pad.GetNumber() in p.pins and pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD \
                    and pad.GetSizeX() > FromMM(1.5) and pad.GetSizeY() > FromMM(1.5):
                ep_net = p.pins[pad.GetNumber()]
        for pad in fp.Pads():
            net = p.pins.get(pad.GetNumber())
            if not pad.GetNumber() and pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and ep_net:
                net = ep_net
            if net:
                pad.SetNet(netinfo[net])

    outline = pcbnew.PCB_SHAPE(board)
    outline.SetShape(pcbnew.SHAPE_T_RECT)
    outline.SetStart(P(0, 0))
    outline.SetEnd(P(W, H))
    outline.SetLayer(pcbnew.Edge_Cuts)
    outline.SetWidth(FromMM(0.1))
    board.Add(outline)

    for txt, x, y, size, side, rot in TEXTS:
        t = pcbnew.PCB_TEXT(board)
        t.SetText(txt)
        t.SetPosition(P(x, y))
        t.SetLayer(pcbnew.B_SilkS if side == "B" else pcbnew.F_SilkS)
        t.SetTextSize(VECTOR2I(FromMM(size), FromMM(size)))
        t.SetTextThickness(FromMM(max(0.15, size * 0.15)))
        t.SetTextAngleDegrees(rot)
        if side == "B":
            t.SetMirrored(True)
        board.Add(t)

    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(netinfo["GND"])
        z.SetLocalClearance(FromMM(0.2))
        z.SetMinThickness(FromMM(0.2))
        z.SetThermalReliefGap(FromMM(0.3))
        z.SetThermalReliefSpokeWidth(FromMM(0.4))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        ol = z.Outline()
        ol.NewOutline()
        for cx, cy in ((0.3, 0.3), (W - 0.3, 0.3), (W - 0.3, H - 0.3), (0.3, H - 0.3)):
            ol.Append(FromMM(OX + cx), FromMM(OY + cy))
        board.Add(z)
    return board


def main():
    board = build()
    # правила и классы цепей живут в im01.kicad_pro — не даём сохранению перезаписать их умолчаниями
    pcbnew.SaveBoard(str(PCB), board, True)
    print(f"плата: {PCB.name}, {W:.0f}×{H:.0f} мм, деталей {len(design.PARTS)}")


if __name__ == "__main__":
    main()
