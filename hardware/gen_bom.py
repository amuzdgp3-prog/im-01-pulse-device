#!/usr/bin/env python3
"""Перечень комплектующих ИМ-01 в Excel: артикулы, цены LCSC и цены в России (ЧипДип, efind).

Запуск: python3 hardware/gen_bom.py [количество_плат]   (по умолчанию 500)
Результат: docs/ИМ-01_перечень_комплектующих.xlsx

Цены в России берутся с публичных страниц ЧипДипа и агрегатора efind.ru на момент запуска; это
ориентир для закупки, а не оферта. У многих поставщиков из efind есть ограничения (минимальная
сумма заказа, только юрлица) — они видны по ссылке.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import design

HW = Path(__file__).resolve().parent
OUT = HW.parent / "docs" / "ИМ-01_перечень_комплектующих.xlsx"
CACHE = HW / "out" / "bom_cache.json"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
BOARDS = int(sys.argv[1]) if len(sys.argv) > 1 else 500

# Артикул для поиска в России, если полный код с упаковкой там не встречается.
# None — позиция типовая, искать по артикулу бессмысленно (подойдёт любой производитель).
RU_SEARCH = {
    "EL817S1(B)(TU)-F": "EL817S1(B)", "B2P-VH(LF)(SN)": "B2P-VH", "B2B-XH-A(LF)(SN)": "B2B-XH-A",
    "B3B-XH-A(LF)(SN)": "B3B-XH-A", "U.FL-R-SMT-1(80)": "U.FL-R-SMT-1", "STM32G030K8T6TR": "STM32G030K8T6",
    "EG800KEULC-I03-SNNSA": "EG800K", "FM25L16B-GTR": "FM25L16B", "SMAZ5V1-13-F": "SMAZ5V1",
    "TS-1187A-B-A-B": "TS-1187A", "ME6211C33M5G-N": "ME6211C33M5G",
    "NANO SIM XG6P H1.35": None, "MA6.3V470M6X8": None, "RVT1H470M0607": None, "SLO0630H100MTT": None,
    "NCD0805G1": None, "NCD0805R1": None,
}
GENERIC_SYMBOLS = {"Device:R", "Device:C"}


def get(url: str, data: bytes | None = None, headers: dict | None = None) -> tuple[str, str]:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.geturl(), r.read().decode("utf-8", errors="ignore")
        except Exception:
            time.sleep(2 + attempt * 3)
    return url, ""


def ladder_price(ladder: list[tuple[int, float]], qty: int) -> float | None:
    """Цена за штуку для партии qty по шкале [(от_шт, цена)]."""
    ladder = sorted(ladder)
    if not ladder:
        return None
    price = ladder[0][1]
    for q, p in ladder:
        if q <= qty:
            price = p
    return price


def usd_rate() -> tuple[float, str]:
    _, body = get("https://www.cbr-xml-daily.ru/daily_json.js")
    j = json.loads(body)
    return float(j["Valute"]["USD"]["Value"]), j["Date"][:10]


def lcsc(code: str, qty: int) -> dict:
    _, body = get(f"https://wmsc.lcsc.com/ftps/wm/product/detail?productCode={code}")
    try:
        r = json.loads(body).get("result") or {}
    except ValueError:
        r = {}
    ladder = [(p["ladder"], float(p["usdPrice"])) for p in r.get("productPriceList") or []]
    return dict(brand=r.get("brandNameEn") or "", stock=r.get("stockNumber"), usd=ladder_price(ladder, qty),
                desc=r.get("productIntroEn") or "", package=r.get("encapStandard") or "",
                url=f"https://www.lcsc.com/product-detail/{code}.html")


def chipdip(mpn: str, qty: int) -> dict | None:
    url = "https://www.chipdip.ru/search?searchtext=" + urllib.parse.quote(mpn)
    final, body = get(url)
    if not body:
        return None
    best = None
    rows = re.findall(r'<tr class="with-hover" id="item(\d+)">(.*?)</tr>', body, re.S)
    if not rows and "/product/" in final:
        rows = [("", body)]
    key = re.sub(r"[^A-Z0-9]", "", mpn.upper())
    for _, row in rows:
        name = re.search(r'<b>([^<]+)</b>', row) if "/product/" not in final else re.search(r"<h1[^>]*>([^<]+)", row)
        disc = re.search(r'data-discounts="([^"]+)"', row)
        if not name or not disc:
            continue
        if not re.sub(r"[^A-Z0-9]", "", name.group(1).upper()).startswith(key[: max(6, len(key) - 3)]):
            continue
        ladder = [(int(q), float(p)) for q, p in json.loads(html.unescape(disc.group(1)))]
        avail = re.search(r'item__avail[^"]*"[^>]*>\s*([^<]+)', row)
        stock_txt = avail.group(1).strip() if avail else ""
        m = re.match(r"([\d\s]+)\s*шт", stock_txt)
        stock = int(m.group(1).replace(" ", "")) if m else 0
        link = re.search(r'href="(/product/[^"]+)"', row)
        cand = dict(price=ladder_price(ladder, qty), stock=stock, stock_txt=stock_txt,
                    url="https://www.chipdip.ru" + link.group(1) if link else final)
        if best is None or (cand["stock"] >= qty) > (best["stock"] >= qty) or \
                ((cand["stock"] >= qty) == (best["stock"] >= qty) and cand["price"] < best["price"]):
            best = cand
    return best


def efind(mpn: str, qty: int) -> dict | None:
    url = f"https://efind.ru/offer/{urllib.parse.quote(mpn)}?stock=1&c=rur&r=0&hp=1&opriv=0"
    _, body = get(url)
    if not body:
        return None
    offers = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        t = re.sub(r"<[^>]+>", " | ", row)
        t = re.sub(r"\s+", " ", t)
        t2 = re.sub(r"(\s*\|\s*)+", " | ", t)  # у efind пустые ячейки дают несколько "|" подряд
        pairs = [(int(q), float(p)) for q, p in re.findall(r"(\d+)\+ \| ([\d.]+) р\.", t2)]
        if not pairs:
            continue
        # URL уже фильтрует stock=1 (только предложения с наличием), точное число штук распарсить
        # надёжно не удаётся — верстка efind не даёт устойчивого якоря. Наличие на партию не
        # проверяем отдельно, полагаемся на фильтр запроса.
        offers.append(dict(price=ladder_price(pairs, qty)))
    if not offers:
        return dict(price=None, count=0, url=url.replace("&hp=1", "&hp=0"))
    best = min(offers, key=lambda o: o["price"])
    return dict(price=best["price"], count=len(offers), enough=len(offers), url=url)


def bom_rows() -> list[dict]:
    groups: "OrderedDict[str, dict]" = OrderedDict()
    for p in design.PARTS:
        if not p.in_bom or p.dnp:
            continue
        key = p.lcsc or p.mpn or f"{p.value}|{p.footprint}"
        g = groups.setdefault(key, dict(refs=[], value=p.value, footprint=p.footprint.split(":", 1)[1],
                                        mpn=p.mpn, lcsc=p.lcsc, symbol=p.symbol, block=p.block, notes=set()))
        g["refs"].append(p.ref)
        if p.note:
            g["notes"].add(p.note)
    return list(groups.values())


def natural(ref: str):
    m = re.match(r"([A-Z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def main():
    rate, rate_date = usd_rate()
    rows = bom_rows()
    cache = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))
    print(f"позиций: {len(rows)}, плат: {BOARDS}, курс ЦБ {rate} ₽/$ на {rate_date}", flush=True)
    for i, r in enumerate(rows, 1):
        r["refs"].sort(key=natural)
        r["qty"] = len(r["refs"])
        need = r["qty"] * BOARDS
        r["need"] = need
        ckey = f"{r['lcsc']}|{r['mpn']}|{need}"
        if ckey in cache:
            r.update(cache[ckey])
        else:
            r["lcsc_info"] = lcsc(r["lcsc"], need) if r["lcsc"] else {}
            generic = r["symbol"] in GENERIC_SYMBOLS
            term = RU_SEARCH.get(r["mpn"], r["mpn"])
            r["generic"] = generic or term is None
            if not r["generic"] and term:
                r["chipdip"] = chipdip(term, need)
                time.sleep(0.8)
                r["efind"] = efind(term, need)
                time.sleep(0.8)
                r["ru_term"] = term
            cache[ckey] = {k: r[k] for k in ("lcsc_info", "generic", "chipdip", "efind", "ru_term") if k in r}
            CACHE.parent.mkdir(exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        cd, ef = r.get("chipdip"), r.get("efind")
        print(f"  {i:>2}/{len(rows)} {r['mpn'][:24]:24} LCSC ${r['lcsc_info'].get('usd')}"
              f" | ЧипДип {cd and cd.get('price')} | efind {ef and ef.get('price')}", flush=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Перечень"
    head = ["№", "Обозначения на плате", "Кол-во на плату", f"Кол-во на {BOARDS} плат", "Номинал / тип",
            "Производитель", "Артикул производителя", "Артикул LCSC", "Корпус", "Описание", "Примечание",
            "LCSC, $/шт", "LCSC, ₽/шт", "LCSC, склад",
            "ЧипДип, ₽/шт", "ЧипДип, наличие", "efind (склады РФ), лучшая ₽/шт", "efind: предложений с наличием",
            "Цена для расчёта, ₽/шт", "Источник цены", f"Сумма на {BOARDS} плат, ₽", "Ссылки"]
    ws.append(head)
    bold = Font(bold=True)
    for c in ws[1]:
        c.font = bold
        c.alignment = Alignment(wrap_text=True, vertical="top")
        c.fill = PatternFill("solid", fgColor="DDEBF7")
    total_board, total_lcsc = 0.0, 0.0
    for i, r in enumerate(rows, 1):
        li, cd, ef = r["lcsc_info"], r.get("chipdip"), r.get("efind")
        lcsc_rub = round(li["usd"] * rate, 2) if li.get("usd") else None
        # Разметка efind ненадёжна (несколько офферов подряд без чёткой границы в вёрстке), поэтому
        # цена заметно ниже оптовой китайской (LCSC) почти наверняка — сбой разбора чужой строки,
        # а не реальное предложение: розница в РФ дешевле фабричного опта не бывает.
        floor = (lcsc_rub or 0) * 0.5
        choices = []
        if cd and cd.get("price") and cd["stock"] >= r["need"] and (not floor or cd["price"] >= floor):
            choices.append((cd["price"], "ЧипДип"))
        if ef and ef.get("price") and (not floor or ef["price"] >= floor):
            choices.append((ef["price"], "efind, склад РФ"))
        if choices:
            price, src = min(choices)
        elif lcsc_rub:
            price, src = lcsc_rub, "LCSC (Китай) по курсу ЦБ"
        else:
            price, src = None, "нет цены — запросить"
        note = "; ".join(sorted(r["notes"]))
        if r["generic"]:
            note = ("типовая позиция — подойдёт любой производитель с теми же параметрами; " + note).strip("; ")
        if r["mpn"].startswith("EG800K"):
            note = ("модем: на LCSC мало, для партии — дистрибьютор Quectel, давальческая поставка; " + note)
        links = [f"LCSC: {li.get('url', '')}"]
        if cd:
            links.append(f"ЧипДип: {cd['url']}")
        if ef:
            links.append(f"efind: {ef['url']}")
        ws.append([
            i, ", ".join(r["refs"]), r["qty"], r["need"], r["value"], li.get("brand", ""), r["mpn"], r["lcsc"],
            li.get("package") or r["footprint"], li.get("desc", ""), note,
            li.get("usd"), lcsc_rub, li.get("stock"),
            cd and cd.get("price"), cd and cd.get("stock_txt"),
            ef and ef.get("price"), ef and ef.get("count", 0),
            price, src, round(price * r["need"], 2) if price else None, "\n".join(links),
        ])
        if price:
            total_board += price * r["qty"]
        if lcsc_rub:
            total_lcsc += lcsc_rub * r["qty"]
    widths = [4, 22, 8, 10, 16, 16, 24, 11, 16, 40, 40, 9, 9, 10, 10, 12, 12, 12, 11, 20, 13, 60]
    for idx, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    for col in ("L",):
        for c in ws[col][1:]:
            c.number_format = "0.0000"
    for col in ("M", "O", "Q", "S", "U"):
        for c in ws[col][1:]:
            c.number_format = "#,##0.00"
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions

    s = wb.create_sheet("Итого")
    lines = [
        ("ИМ-01 — перечень комплектующих", ""),
        ("Дата", date.today().isoformat()),
        ("Курс ЦБ, ₽ за $", f"{rate} на {rate_date}"),
        ("Количество плат", BOARDS),
        ("Позиций в перечне", len(rows)),
        ("Деталей на одну плату", sum(r["qty"] for r in rows)),
        ("Комплектующие на 1 плату, ₽ (лучшая цена: РФ, если хватает на партию, иначе LCSC)", round(total_board, 2)),
        (f"Комплектующие на {BOARDS} плат, ₽", round(total_board * BOARDS, 2)),
        ("Для сравнения: всё с LCSC, ₽ на 1 плату (без доставки и пошлин)", round(total_lcsc, 2)),
        ("", ""),
        ("Не входит в сумму", "печатная плата, монтаж, корпус, антенна с пигтейлом, Y-жгуты, SIM и тариф, "
                               "доставка и таможня для позиций из Китая"),
        ("Как считались цены в РФ", "ЧипДип — цена за штуку для нужного количества по шкале скидок, только если "
                                    "на складе хватает на всю партию; efind.ru — лучшая цена по шкале скидок "
                                    "среди предложений с наличием (efind не даёт надёжно спарсить точное число "
                                    "штук на складе у каждого поставщика — проверяйте по ссылке перед заказом)"),
        ("Внимание", "у поставщиков из efind бывают ограничения: минимальная сумма заказа, только юрлица, требуется "
                     "уточнение наличия на нужное количество — смотрите по ссылке в перечне перед заказом"),
    ]
    for a, b in lines:
        s.append([a, b])
    s["A1"].font = Font(bold=True, size=13)
    s.column_dimensions["A"].width = 70
    s.column_dimensions["B"].width = 70
    for row in s.iter_rows():
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    n = wb.create_sheet("Не монтируются")
    n.append(["Обозначение", "Что это", "Почему нет в перечне"])
    for c in n[1]:
        c.font = bold
    for p in design.PARTS:
        if p.dnp:
            n.append([p.ref, f"{p.value} {p.footprint.split(':', 1)[1]}", "место под согласование антенны, по умолчанию пусто"])
        elif not p.in_bom:
            n.append([p.ref, p.value, "контрольная точка / отверстие / площадки программатора — только на плате"])
    for col, w in (("A", 12), ("B", 40), ("C", 70)):
        n.column_dimensions[col].width = w

    OUT.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT)
    print(f"готово: {OUT}")
    print(f"на 1 плату: {total_board:.2f} ₽ (всё с LCSC: {total_lcsc:.2f} ₽)")


if __name__ == "__main__":
    main()
