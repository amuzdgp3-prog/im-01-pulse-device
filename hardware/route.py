#!/usr/bin/env python3
"""Трассировка ИМ-01: критичные цепи по заданной геометрии, остальное — Freerouting.

Порядок (IM-01 §9 шаг 5):
  1. руками и с фиксацией (locked) — три цепи, которые нельзя отдавать автороутеру:
     трасса до U.FL, коммутирующий узел преобразователя, путь VBAT;
  2. переходные отверстия на землю у силовых деталей;
  3. Freerouting — всё остальное;
  4. заливки земли, сшивка слоёв, сохранение.

Запуск: python3 route.py            — всё целиком
        python3 route.py --manual   — только шаги 1–2 (для просмотра)
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import pcbnew
from pcbnew import FromMM, ToMM, VECTOR2I

HW = Path(__file__).resolve().parent
PCB = HW / "im01.kicad_pcb"
OUT = HW / "out"
FREEROUTING = HW.parent / "tools" / "freerouting.jar"
OX, OY = 100.0, 100.0
W, H = 80.0, 55.0

board: pcbnew.BOARD = None  # type: ignore


def P(x: float, y: float) -> VECTOR2I:
    return VECTOR2I(FromMM(OX + x), FromMM(OY + y))


def net(name: str):
    n = board.FindNet(name)
    if n is None:
        raise KeyError(name)
    return n


def pad(ref: str, num: str):
    fp = board.FindFootprintByReference(ref)
    for p in fp.Pads():
        if p.GetNumber() == num:
            return p
    raise KeyError(f"{ref}.{num}")


def xy(ref: str, num: str) -> tuple[float, float]:
    pos = pad(ref, num).GetPosition()
    return ToMM(pos.x) - OX, ToMM(pos.y) - OY


def track(netname: str, pts: list[tuple[float, float]], width: float, layer=pcbnew.F_Cu, locked=True):
    for a, b in zip(pts, pts[1:]):
        if a == b:
            continue
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(P(*a))
        t.SetEnd(P(*b))
        t.SetWidth(FromMM(width))
        t.SetLayer(layer)
        t.SetNet(net(netname))
        t.SetLocked(locked)
        board.Add(t)


def via(netname: str, x: float, y: float, d: float = 0.6, drill: float = 0.3, locked=True):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(P(x, y))
    try:
        v.SetWidth(FromMM(d))
    except TypeError:
        v.SetWidth(pcbnew.F_Cu, FromMM(d))
    v.SetDrill(FromMM(drill))
    v.SetNet(net(netname))
    v.SetLocked(locked)
    board.Add(v)
    return v


def zone(netname: str, layer, pts: list[tuple[float, float]], priority: int, clearance=0.25):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    z.SetNet(net(netname))
    z.SetAssignedPriority(priority)
    z.SetLocalClearance(FromMM(clearance))
    z.SetMinThickness(FromMM(0.25))
    z.SetThermalReliefGap(FromMM(0.3))
    z.SetThermalReliefSpokeWidth(FromMM(0.5))
    # силовые площадки — сплошным соединением, без термобарьеров (ток до 2 А)
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(FromMM(OX + x), FromMM(OY + y))
    board.Add(z)
    return z


# ------------------------------------------------------------------ проверка свободного места
def _pad_obstacles():
    obs = []
    for fp in board.GetFootprints():
        for p in fp.Pads():
            bb = p.GetBoundingBox()
            obs.append((ToMM(bb.GetLeft()) - OX, ToMM(bb.GetTop()) - OY,
                        ToMM(bb.GetRight()) - OX, ToMM(bb.GetBottom()) - OY,
                        p.GetNetname(), p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH))
    return obs


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def free_for_via(x, y, netname="GND", r=0.3, clearance=0.25, pads=None, avoid_courtyards=True) -> bool:
    if not (1.0 < x < W - 1.0 and 1.0 < y < H - 1.0):
        return False
    for x0, y0, x1, y1, pnet, npth in pads if pads is not None else _pad_obstacles():
        dx = max(x0 - x, 0, x - x1)
        dy = max(y0 - y, 0, y - y1)
        need = r + (max(clearance, net_clearance(pnet)) + 0.01 if (pnet != netname or npth) else 0.15)
        if math.hypot(dx, dy) < need:
            return False
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            p = t.GetPosition()
            if math.hypot(ToMM(p.x) - OX - x, ToMM(p.y) - OY - y) < 2 * r + 0.3:
                return False
            continue
        s, e = t.GetStart(), t.GetEnd()
        d = _seg_dist(x, y, ToMM(s.x) - OX, ToMM(s.y) - OY, ToMM(e.x) - OX, ToMM(e.y) - OY)
        need = r + ToMM(t.GetWidth()) / 2 + (clearance if t.GetNetname() != netname else 0.0)
        if d < need:
            return False
    if avoid_courtyards:
        for fp in board.GetFootprints():
            try:
                cy = fp.GetCourtyard(pcbnew.F_CrtYd)
                if cy.OutlineCount() and cy.Contains(P(x, y)):
                    return False
            except Exception:
                pass
    return True


# ------------------------------------------------------------------ 1. критичные цепи
def route_rf():
    """Антенна: вывод 35 модема → R26 → U.FL, 1.0 мм (≈54 Ом CPWG с зазором 0.2 мм), строчка GND-отверстий."""
    ax, ay = xy("U7", "35")
    r1 = xy("R26", "1")
    r2 = xy("R26", "2")
    j = xy("J5", "1")
    c28 = xy("C28", "1")
    c29 = xy("C29", "1")
    # у площадок модуля и 0402 линия сужается: между площадками R26 всего ~0.5 мм
    track("ANT_MOD", [(ax, ay), (ax + 1.0, ay)], 0.6)
    track("ANT_MOD", [(ax + 1.0, ay), (r1[0] - 0.8, ay)], 1.0)
    track("ANT_MOD", [(r1[0] - 0.8, ay), r1], 0.5)
    track("ANT_MOD", [(c28[0], ay), c28], 0.5)
    track("ANT_OUT", [r2, (r2[0] + 0.8, ay)], 0.5)
    track("ANT_OUT", [(r2[0] + 0.8, ay), (j[0] - 0.6, ay)], 1.0)
    track("ANT_OUT", [(j[0] - 0.6, ay), j], 0.6)
    track("ANT_OUT", [(c29[0], ay), c29], 0.5)
    pads = _pad_obstacles()
    for x in [ax + 1.6 + i * 1.3 for i in range(8)]:
        for dy in (-1.35, 1.35):
            if x < j[0] - 0.8 and free_for_via(x, ay + dy, pads=pads, avoid_courtyards=False):
                via("GND", x, ay + dy)


def route_buck():
    """Коммутирующий узел SW и петля вольтодобавки — кратчайшие широкие дорожки."""
    sw = xy("U1", "8")
    l1 = xy("L1", "1")
    d3 = xy("D3", "1")
    c5a, c5b = xy("C5", "1"), xy("C5", "2")
    boot = xy("U1", "1")
    vin = xy("U1", "2")
    c4v, c4g = xy("C4", "1"), xy("C4", "2")
    # SW: вывод 8 → дроссель; первый участок уже (соседний вывод 7 — земля)
    track("SW", [sw, (sw[0] + 1.6, sw[1])], 1.0)
    track("SW", [(sw[0] + 1.6, sw[1]), l1], 1.5)
    track("SW", [d3, (d3[0], l1[1] + 1.8), l1], 1.5)
    # вольтодобавочный конденсатор BOOT–SW
    track("SW", [c5b, (sw[0], c5b[1]), sw], 0.4)
    track("BOOT", [c5a, (boot[0], c5a[1]), boot], 0.4)
    # входной конденсатор 100 нФ вплотную к VIN
    track("VIN", [c4v, (c4v[0] + 0.8, vin[1]), vin], 0.6)
    via("GND", c4g[0] - 1.0, c4g[1])
    track("GND", [c4g, (c4g[0] - 1.0, c4g[1])], 0.6)
    # земляной вывод 7 — прямо на центральную площадку (там теплоотводящие отверстия)
    g7 = xy("U1", "7")
    ep = xy("U1", "9")
    track("GND", [g7, (ep[0] + 0.9, g7[1])], 0.4)


def route_vbat():
    """Путь VBAT — медная заливка от дросселя через C6…C33 к выводам 42/43 модема (IM-01: ≥ 2 мм)."""
    l1x, l1y = xy("L1", "2")
    v42 = xy("U7", "42")
    v43 = xy("U7", "43")
    d4k = xy("D4", "1")
    x_l, x_r = min(v42[0], v43[0]) - 0.6, max(v42[0], v43[0]) + 0.6
    zone("VBAT", pcbnew.F_Cu, [
        (l1x - 1.2, l1y - 2.0), (46.3, l1y - 2.0), (46.3, 8.8), (71.0, 8.8), (71.0, 15.9),
        (x_r, 15.9), (x_r, v42[1] + 0.2), (x_l, v42[1] + 0.2), (x_l, 15.9),
        (46.3, 15.9), (46.3, 12.6), (l1x - 1.2, 12.6),
    ], priority=2)
    track("VBAT", [(70.5, d4k[1]), d4k], 1.5)
    track("VBAT", [(70.5, 12.0), (70.5, d4k[1])], 1.5)
    # перемычка: земляная площадка C7 отрезает кусок заливки у дросселя от основной части.
    # Доводим прямо до «+» C8, чтобы соединение не зависело от того, как ляжет заливка.
    c8p = xy("C8", "1")
    track("VBAT", [(l1x, l1y), (l1x, 12.2), (c8p[0] - 1.2, 12.2), c8p], 1.5)


def net_clearance(name: str) -> float:
    """Зазор класса цепи — те же числа, что в im01.kicad_pro."""
    if name.startswith("VIN") or name in ("VBAT", "SW", "VMCU_IN"):
        return 0.25
    if name.startswith("ANT_"):
        return 0.2
    return 0.15


def segment_clear(ax, ay, bx, by, netname, width, pads, clearance=0.2) -> bool:
    """Дорожка a→b не подходит к площадкам и дорожкам других цепей ближе зазора (с учётом класса цепи)."""
    samples = [(ax + (bx - ax) * k / 10, ay + (by - ay) * k / 10) for k in range(11)]
    for x0, y0, x1, y1, pnet, _ in pads:
        if pnet == netname:
            continue
        need = width / 2 + max(clearance, net_clearance(pnet)) + 0.01
        for x, y in samples:
            dx = max(x0 - x, 0, x - x1)
            dy = max(y0 - y, 0, y - y1)
            if math.hypot(dx, dy) < need:
                return False
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetNetname() == netname or t.GetLayer() != pcbnew.F_Cu:
            continue
        s, e = t.GetStart(), t.GetEnd()
        need = width / 2 + ToMM(t.GetWidth()) / 2 + max(clearance, net_clearance(t.GetNetname())) + 0.01
        for x, y in samples:
            d = _seg_dist(x, y, ToMM(s.x) - OX, ToMM(s.y) - OY, ToMM(e.x) - OX, ToMM(e.y) - OY)
            if d < need:
                return False
    return True


def gnd_fanout():
    """Переходные на нижний слой земли у земляных площадок силовых деталей и конденсаторов.

    Отвод проверяется целиком (segment_clear), поэтому микросхемы с мелким шагом тоже здесь: отвод
    от земляного вывода уходит наружу, перпендикулярно ряду выводов, и соседей не задевает.
    """
    refs = ["C1", "C2", "C3", "D2", "D3", "C6", "C7", "C8", "C9", "C33", "D4",
            "C10", "C11", "C12", "C13", "C31", "C32", "C14", "C17", "C16", "C15", "C18", "C21", "C34", "C35",
            "C19", "C20", "C22", "C23", "C24", "C25", "C26", "C27", "C30", "R19", "R21", "R2", "R3", "R5",
            "R7", "U2", "U3", "U4", "U5", "U6", "U8", "U9", "Q1", "Q2", "J4", "J5", "U7"]
    pads = _pad_obstacles()
    placed = 0
    for ref in refs:
        fp = board.FindFootprintByReference(ref)
        if fp is None:
            continue
        c = fp.GetPosition()
        cx, cy = ToMM(c.x) - OX, ToMM(c.y) - OY
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            px, py = ToMM(p.GetPosition().x) - OX, ToMM(p.GetPosition().y) - OY
            # у модема внутренние земляные площадки соединяем с соседней земляной, под модулем отверстий нет
            if ref == "U7" and max(abs(px - cx), abs(py - cy)) < 7.0:
                near = sorted((math.hypot(qx - px, qy - py), qx, qy) for q in fp.Pads()
                              if q.GetNetname() == "GND" and q.GetNumber() != p.GetNumber()
                              for qx, qy in [(ToMM(q.GetPosition().x) - OX, ToMM(q.GetPosition().y) - OY)])
                for dist, qx, qy in near:
                    if 0.05 < dist < 2.6 and segment_clear(px, py, qx, qy, "GND", 0.25, pads, clearance=0.15):
                        track("GND", [(px, py), (qx, qy)], 0.25)
                        placed += 1
                        break
                continue
            if pad_fanout(fp, p, pads):
                placed += 1
    print(f"  переходных у земляных площадок: {placed}")


def pad_fanout(fp, p, pads, dists=(0.55, 0.9, 1.3, 1.8, 2.4), clearance=0.2) -> bool:
    """Переходное на нижнюю землю рядом с площадкой p; отвод не шире площадки. True — если поставлено."""
    c = fp.GetPosition()
    cx, cy = ToMM(c.x) - OX, ToMM(c.y) - OY
    px, py = ToMM(p.GetPosition().x) - OX, ToMM(p.GetPosition().y) - OY
    bbp = p.GetBoundingBox()
    short = min(ToMM(bbp.GetWidth()), ToMM(bbp.GetHeight()))
    half = max(ToMM(bbp.GetWidth()), ToMM(bbp.GetHeight())) / 2
    width = min(0.4, max(0.2, short * 0.8))
    base = math.atan2(py - cy, px - cx) if (px, py) != (cx, cy) else 0.0
    for k in range(16):
        ang = base + ((k + 1) // 2) * (math.pi / 8) * (1 if k % 2 else -1)
        for d in dists:
            vx, vy = px + (half + d) * math.cos(ang), py + (half + d) * math.sin(ang)
            if free_for_via(vx, vy, pads=pads, clearance=clearance, avoid_courtyards=False) and \
                    segment_clear(px, py, vx, vy, "GND", width, pads, clearance=0.15):
                via("GND", vx, vy)
                track("GND", [(px, py), (vx, vy)], width)
                return True
    return False


def stitch_grid(step=3.5):
    pads = _pad_obstacles()
    n = 0
    y = 2.0
    while y < H - 1.5:
        x = 2.0
        while x < W - 1.5:
            if free_for_via(x, y, pads=pads, clearance=0.35):
                via("GND", x, y, locked=False)
                n += 1
            x += step
        y += step
    print(f"  сшивающих переходных: {n}")


# ------------------------------------------------------------------ 3. Freerouting
def unrouted() -> int | None:
    try:
        board.BuildConnectivity()
        return board.GetConnectivity().GetUnconnectedCount(False)
    except Exception:
        return None


def autoroute(passes: int = 2):
    """Freerouting; если после прохода остались неразведённые связи — ещё проход поверх готового."""
    OUT.mkdir(exist_ok=True)
    for n in range(1, passes + 1):
        dsn, ses = OUT / "im01.dsn", OUT / "im01.ses"
        for f in (dsn, ses):
            f.unlink(missing_ok=True)
        if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
            raise SystemExit("экспорт DSN не удался")
        cmd = ["java", "-jar", str(FREEROUTING), "-de", str(dsn), "-do", str(ses), "-mp", "100",
               "--gui.enabled=false"]
        print(f"  Freerouting, проход {n}…", flush=True)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        (OUT / f"freerouting_{n}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        if not ses.exists():
            raise SystemExit(f"Freerouting не выдал результат, см. out/freerouting_{n}.log")
        if not pcbnew.ImportSpecctraSES(board, str(ses)):
            raise SystemExit("импорт SES не удался")
        fill_zones()
        left = unrouted()
        print(f"  неразведённых связей после прохода: {left if left is not None else 'неизвестно'}")
        if left == 0:
            break


def connect_islands():
    """Обрывки земляной заливки: внутри каждого ищем точку над основной заливкой другого слоя
    и ставим туда переходное — обрывок становится частью земли."""
    fill_zones()
    zones = {z.GetLayer(): z for z in board.Zones() if z.GetNetname() == "GND"}

    def outlines(layer):
        polys = zones[layer].GetFilledPolysList(layer)
        return [polys.Outline(i) for i in range(polys.OutlineCount())]

    pads = _pad_obstacles()
    added = 0
    gnd_vias = [t.GetPosition() for t in board.GetTracks()
                if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == "GND"]
    for layer, other in ((pcbnew.F_Cu, pcbnew.B_Cu), (pcbnew.B_Cu, pcbnew.F_Cu)):
        outs, others = outlines(layer), outlines(other)
        if not outs or not others:
            continue
        main_i = max(range(len(outs)), key=lambda i: abs(outs[i].Area()))
        other_main = max(others, key=lambda o: abs(o.Area()))
        for i, ch in enumerate(outs):
            if i == main_i:
                continue
            # подключён, только если его переходное попадает в основную заливку другого слоя
            if any(ch.PointInside(v) and other_main.PointInside(v) for v in gnd_vias):
                continue
            bb = ch.BBox()
            x0, y0 = ToMM(bb.GetLeft()) - OX, ToMM(bb.GetTop()) - OY
            x1, y1 = ToMM(bb.GetRight()) - OX, ToMM(bb.GetBottom()) - OY
            done = False
            y = y0 + 0.2
            while y < y1 and not done:
                x = x0 + 0.2
                while x < x1:
                    pt = P(x, y)
                    if ch.PointInside(pt) and other_main.PointInside(pt) and \
                            free_for_via(x, y, pads=pads, clearance=0.2, avoid_courtyards=False):
                        via("GND", x, y)
                        added += 1
                        done = True
                        break
                    x += 0.2
                y += 0.2
            # переходное внутрь не влезает — отвод от земляной площадки, лежащей в этом кармане
            if not done and layer == pcbnew.F_Cu:
                for fp in board.GetFootprints():
                    for p in fp.Pads():
                        if p.GetNetname() == "GND" \
                                and p.GetAttribute() in (pcbnew.PAD_ATTRIB_SMD, pcbnew.PAD_ATTRIB_CONN) \
                                and ch.PointInside(p.GetPosition()) and pad_fanout(fp, p, pads):
                            added += 1
                            done = True
                            break
                    if done:
                        break
    fill_zones()
    print(f"  переходных в обрывки заливки: {added}")


def fill_zones():
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())


def prune_stitch():
    """Убрать сшивающие отверстия, попавшие в карманы между дорожками.

    Такое отверстие само становится «соединением» кармана, и заливка перестаёт считать карман
    островом — он остаётся висеть неподключённым. Оставляем только отверстия, которые лежат в самом
    большом куске земляной заливки на обоих слоях.
    """
    fill_zones()
    main = {}
    for z in board.Zones():
        if z.GetNetname() != "GND":
            continue
        layer = z.GetLayer()
        polys = z.GetFilledPolysList(layer)
        best, area = None, -1.0
        for i in range(polys.OutlineCount()):
            a = abs(polys.Outline(i).Area())
            if a > area:
                best, area = polys.Outline(i), a
        main[layer] = best
    removed = 0
    for t in list(board.GetTracks()):
        if t.Type() != pcbnew.PCB_VIA_T or t.IsLocked() or t.GetNetname() != "GND":
            continue
        pos = t.GetPosition()
        if not all(ch is not None and ch.PointInside(pos) for ch in main.values()):
            board.Remove(t)
            removed += 1
    fill_zones()
    print(f"  убрано сшивающих отверстий в карманах: {removed}")


def main():
    global board
    board = pcbnew.LoadBoard(str(PCB))
    for t in list(board.GetTracks()):
        board.Remove(t)
    for z in list(board.Zones()):
        if z.GetNetname() != "GND":
            board.Remove(z)
    print("1. критичные цепи")
    route_rf()
    route_buck()
    route_vbat()
    print("2. земля у силовых деталей")
    gnd_fanout()
    if "--manual" not in sys.argv:
        print("3. автотрассировка")
        autoroute()
        print("4. сшивка и заливки")
        stitch_grid(step=2.5)
        prune_stitch()
        connect_islands()
    fill_zones()
    pcbnew.SaveBoard(str(PCB), board, True)
    print("сохранено:", PCB.name)


if __name__ == "__main__":
    main()
