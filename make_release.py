#!/usr/bin/env python3
"""Архив с полной документацией ИМ-01: описание, картинки, перечень деталей, схема, файлы для завода.

Запуск: python3 make_release.py   →   release/ИМ-01_документация_rev.A.zip
Перед запуском плата и документы должны быть собраны (hardware/fab.py, sim/run_final.py).
"""
from __future__ import annotations

import shutil
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "ИМ-01_документация_rev.A"
STAGE = ROOT / "release" / NAME
ZIP = ROOT / "release" / f"{NAME}.zip"

FILES = {
    "01_Описание": [
        ("docs/hardware.md", "Плата_описание.md"),
        ("docs/step1-analog-sim.md", "Проверка_схемы_симуляция.md"),
        ("sim/results_final.md", "Виртуальная_модель_результаты.md"),
        ("docs/IM-01_FULL_BRIEF.md", "Задание_IM-01.md"),
    ],
    "02_Картинки": [
        ("hardware/fab/im01_3d_top.png", "Собранное_устройство_сверху.png"),
        ("hardware/fab/im01_3d_bottom.png", "Собранное_устройство_снизу.png"),
        ("hardware/out/routed_F.png", "Разводка_верхний_слой.png"),
        ("hardware/out/routed_B.png", "Разводка_нижний_слой.png"),
        ("sim/out/final_0.png", "Модель_устройства_обычная_работа.png"),
        ("sim/out/final_4.png", "Модель_устройства_худший_случай.png"),
        ("sim/out/input_stage.png", "Входы_импульсов_осциллограмма.png"),
    ],
    "03_Перечень_деталей": [
        ("docs/ИМ-01_перечень_комплектующих.xlsx", "Перечень_комплектующих_с_ценами.xlsx"),
        ("hardware/fab/im01_bom_jlcpcb.csv", "BOM_для_JLCPCB.csv"),
    ],
    "04_Схема_и_плата": [
        ("hardware/fab/im01_schematic.pdf", "Схема.pdf"),
        ("hardware/fab/im01_assembly_top.pdf", "Сборочный_чертёж.pdf"),
        ("hardware/fab/im01.step", "3D_модель_платы.step"),
    ],
    "05_Для_заказа_JLCPCB": [
        ("hardware/fab/im01_gerbers.zip", "Гербер_файлы_im01.zip"),
        ("hardware/fab/im01_bom_jlcpcb.csv", "BOM_im01.csv"),
        ("hardware/fab/im01_cpl_jlcpcb.csv", "CPL_координаты_im01.csv"),
    ],
}

README = f"""ИМ-01 — устройство учёта импульсов для игровых аппаратов
Документация, ревизия A, {date.today().strftime('%d.%m.%Y')}. apixspb.ru

Состав архива

01_Описание
  Плата_описание.md                 — что на плате, принятые решения, проверки, что делать перед заказом
  Проверка_схемы_симуляция.md       — шаг 1: симуляция входов, защиты питания, питания модема
  Виртуальная_модель_результаты.md  — модель всего устройства с окончательными номиналами
  Задание_IM-01.md                  — исходное задание
  (файлы .md открываются любым текстовым редактором или браузером)

02_Картинки
  Собранное_устройство_сверху/снизу — 3D-вид собранной платы
  Разводка_верхний/нижний_слой      — медь платы (нижний слой показан зеркально, как при взгляде снизу)
  Модель_устройства_*               — графики виртуальной модели: питание, датчик 12 В, входы
  Входы_импульсов_осциллограмма     — как проходят импульс 25 мс и помеха 0.2 мс

03_Перечень_деталей
  Перечень_комплектующих_с_ценами.xlsx — артикулы, цены LCSC и в России (ЧипДип, efind), итог на 500 плат
  BOM_для_JLCPCB.csv                   — перечень для заказа монтажа на JLCPCB

04_Схема_и_плата
  Схема.pdf, Сборочный_чертёж.pdf, 3D_модель_платы.step (для проверки корпуса)

05_Для_заказа_JLCPCB
  Гербер_файлы_im01.zip  — загрузить на jlcpcb.com как есть: 2 слоя, 1.6 мм, 1 oz
  BOM_im01.csv, CPL_координаты_im01.csv — для заказа монтажа (SMT Assembly)

Проверки: схема (ERC) — 0 ошибок; плата (DRC) — 0 нарушений, 0 неподключённых; плата совпадает со схемой.

Важно перед заказом
  1. Партию 500 шт. не заказывать без просмотра платы инженером-схемотехником; сначала 5–10 шт. на пилот.
  2. В предпросмотре монтажа JLCPCB проверить повороты деталей (EL817, SOT-23, держатель SIM, модем).
  3. Модем Quectel EG800K-EU на складе JLCPCB почти отсутствует — поставлять давальчески.
  4. Цены в перечне — ориентир на дату сборки, не оферта.

Исходники (схема, плата, скрипты) — в репозитории im-01-pulse-device.
"""


def main():
    shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)
    missing = []
    for folder, items in FILES.items():
        (STAGE / folder).mkdir()
        for src, dst in items:
            s = ROOT / src
            if s.exists():
                shutil.copy2(s, STAGE / folder / dst)
            else:
                missing.append(src)
    (STAGE / "00_ПРОЧИТАЙ_МЕНЯ.txt").write_text(README, encoding="utf-8")
    ZIP.unlink(missing_ok=True)
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(STAGE.rglob("*")):
            if f.is_file():
                zf.write(f, Path(NAME) / f.relative_to(STAGE))
    n = sum(1 for f in STAGE.rglob("*") if f.is_file())
    print(f"архив: {ZIP} — {n} файлов, {ZIP.stat().st_size / 1e6:.1f} МБ")
    if missing:
        print("не найдены:", ", ".join(missing))


if __name__ == "__main__":
    main()
