"""ИМ-01: единственное описание схемы.

Детали, номиналы, посадочные места, артикулы LCSC и соединения. Из этого файла генерируются схема
(gen_sch.py), плата (gen_pcb.py) и перечень компонентов (gen_bom.py), поэтому схема, плата и BOM
не могут разойтись между собой.

Номиналы обоснованы в docs/step1-analog-sim.md и docs/hardware.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field

LCSC_LIB = "im01_lcsc"  # символы и посадочные места, загруженные с LCSC: hardware/lib/lcsc.*


@dataclass
class Part:
    ref: str
    value: str
    symbol: str
    footprint: str
    pins: dict[str, str | None]
    lcsc: str = ""
    mpn: str = ""
    block: str = ""
    dnp: bool = False
    in_bom: bool = True
    note: str = ""


FP = {
    ("R", "0402"): "Resistor_SMD:R_0402_1005Metric",
    ("R", "0603"): "Resistor_SMD:R_0603_1608Metric",
    ("R", "1206"): "Resistor_SMD:R_1206_3216Metric",
    ("C", "0402"): "Capacitor_SMD:C_0402_1005Metric",
    ("C", "0603"): "Capacitor_SMD:C_0603_1608Metric",
    ("C", "0805"): "Capacitor_SMD:C_0805_2012Metric",
    ("C", "1206"): "Capacitor_SMD:C_1206_3216Metric",
}

# Резисторы и конденсаторы: номинал -> (корпус, артикул LCSC, партномер)
RES = {
    "0R_0402": ("0402", "C17168", "0402WGF0000TCE"),
    "0R": ("0603", "C21189", "0603WAF0000T5E"),
    "22R": ("0603", "C23345", "0603WAF220JT5E"),
    "1k": ("0603", "C21190", "0603WAF1001T5E"),
    "4.7k": ("0603", "C23162", "0603WAF4701T5E"),
    "10k": ("0603", "C25804", "0603WAF1002T5E"),
    "15k": ("0603", "C22809", "0603WAF1502T5E"),
    "41.2k": ("0603", "C23166", "0603WAF4122T5E"),
    "49.9k": ("0603", "C23184", "0603WAF4992T5E"),
    "100k": ("0603", "C25803", "0603WAF1003T5E"),
    "270k": ("0603", "C22965", "0603WAF2703T5E"),
    "2.2k_1206": ("1206", "C17948", "1206W4F2201T5E"),
}
CAP = {
    "10pF": ("0402", "C32949", "CL05C100JB5NNNC"),
    "33pF": ("0402", "C1562", "0402CG330J500NT"),
    "100nF": ("0603", "C14663", "CC0603KRX7R9BB104"),
    "1uF": ("0603", "C15849", "CL10A105KB8NNNC"),
    "10uF": ("0805", "C15850", "CL21A106KAYNNNE"),
    "22uF": ("1206", "C87996", "CL31B226KPHNNNE"),
    "4.7uF_50V": ("1206", "C29823", "1206B475K500NT"),
}

PARTS: list[Part] = []


def add(part: Part) -> Part:
    PARTS.append(part)
    return part


def R(ref, key, a, b, block, **kw):
    size, lcsc, mpn = RES[key]
    value = key.split("_")[0].replace("R", "Ω") if key.startswith(("0R", "22R")) else key.split("_")[0]
    return add(Part(ref, value, "Device:R", FP[("R", size)], {"1": a, "2": b}, lcsc, mpn, block, **kw))


def C(ref, key, a, b, block, **kw):
    size, lcsc, mpn = CAP[key]
    return add(Part(ref, key.split("_")[0], "Device:C", FP[("C", size)], {"1": a, "2": b}, lcsc, mpn, block, **kw))


def CP(ref, value, plus, minus, block, lcsc, mpn, fp="Capacitor_SMD:CP_Elec_6.3x7.7", **kw):
    return add(Part(ref, value, "Device:C_Polarized", fp, {"1": plus, "2": minus}, lcsc, mpn, block, **kw))


def D(ref, value, anode, cathode, block, lcsc, mpn, fp, symbol="Device:D", **kw):
    return add(Part(ref, value, symbol, fp, {"1": cathode, "2": anode}, lcsc, mpn, block, **kw))


def TP(ref, net, block, note=""):
    return add(Part(ref, net, "Connector:TestPoint", "TestPoint:TestPoint_Pad_D1.0mm", {"1": net},
                    block=block, in_bom=False, note=note))


# ================================================================ вход питания
B = "Вход питания 9–30 В"
add(Part("J1", "ПИТАНИЕ 9-30В", "Connector_Generic:Conn_01x02",
         "Connector_JST:JST_VH_B2P-VH_1x02_P3.96mm_Vertical", {"1": "VIN_CONN", "2": "GND"},
         "C160315", "B2P-VH(LF)(SN)", B, note="1 = +, 2 = GND"))
add(Part("F1", "0.5A/60V", "Device:Polyfuse", "Fuse:Fuse_1812_4532Metric", {"1": "VIN_CONN", "2": "VIN_F"},
         "C70113", "mSMD050-60V", B))
D("D1", "SS36", "VIN_F", "VIN", B, "C16015", "SS36", "Diode_SMD:D_SMA", symbol="Device:D_Schottky",
  note="защита от переполюсовки, 60 В: при −30 В звон кабеля даёт 43 В")
D("D2", "SMBJ33A", "GND", "VIN", B, "C353366", "SMBJ33A", "Diode_SMD:D_SMB", symbol="Device:D_Zener",
  note="TVS однонаправленный")
CP("C1", "47uF/50V", "VIN", "GND", B, "C970679", "RVT1H470M0607", note="гасит звон при горячем подключении")
C("C2", "4.7uF_50V", "VIN", "GND", B)
C("C3", "4.7uF_50V", "VIN", "GND", B)
R("R6", "100k", "VIN_F", "VSENSE", B, note="датчик пропадания 12 В → АЦП MCU")
R("R7", "10k", "VSENSE", "GND", B)
C("C19", "100nF", "VSENSE", "GND", B)

# ================================================================ преобразователь 3.84 В
B = "Преобразователь VBAT 3.84 В"
add(Part("U1", "LMR16020", f"{LCSC_LIB}:LMR16020PDDAR", f"{LCSC_LIB}:SOIC-8_L4.9-W3.9-P1.27-LS6.0-BL-EP",
         {"1": "BOOT", "2": "VIN", "3": "EN", "4": "RT", "5": "FB", "6": None, "7": "GND", "8": "SW", "9": "GND"},
         "C190006", "LMR16020PDDAR", B, note="60 В, 2 А; 600 кГц"))
C("C4", "100nF", "VIN", "GND", B, note="у вывода VIN")
R("R1", "270k", "VIN", "EN", B, note="включение 7.5 В, выключение 6.5 В")
R("R2", "49.9k", "EN", "GND", B)
R("R3", "41.2k", "RT", "GND", B, note="600 кГц")
C("C5", "100nF", "BOOT", "SW", B)
add(Part("L1", "10uH", "Device:L", f"{LCSC_LIB}:IND-SMD_L7.3-W6.6_MHCI06030", {"1": "SW", "2": "VBAT"},
         "C207842", "SLO0630H100MTT", B, note="10 мкГн, насыщение 5.5 А"))
D("D3", "SS36", "GND", "SW", B, "C16015", "SS36", "Diode_SMD:D_SMA", symbol="Device:D_Schottky")
R("R4", "41.2k", "VBAT", "FB", B, note="VBAT = 0.75 × (1 + 41.2/10) = 3.84 В")
R("R5", "10k", "FB", "GND", B)
C("C6", "22uF", "VBAT", "GND", B)
C("C7", "22uF", "VBAT", "GND", B)
CP("C8", "470uF/6.3V", "VBAT", "GND", B, "C54321567", "MA6.3V470M6X8", note="полимер 20 мОм; C8+C9 = 940 мкФ")
CP("C9", "470uF/6.3V", "VBAT", "GND", B, "C54321567", "MA6.3V470M6X8")
D("D4", "SMAZ5V1", "GND", "VBAT", B, "C154748", "SMAZ5V1-13-F", "Diode_SMD:D_SMA", symbol="Device:D_Zener",
  note="по руководству Air780E: стабилитрон 5.1 В 1 Вт у VBAT")

# ================================================================ питание MCU
B = "Питание MCU и FRAM"
D("D5", "BAT54WS", "VBAT", "VMCU_IN", B, "C3040452", "BAT54WS", "Diode_SMD:D_SOD-323",
  symbol="Device:D_Schottky", note="отделяет MCU от просадок модема и пропадания питания")
CP("C14", "470uF/6.3V", "VMCU_IN", "GND", B, "C54321567", "MA6.3V470M6X8", note="запас MCU > 30 мс")
C("C15", "1uF", "VMCU_IN", "GND", B)
add(Part("U2", "ME6211C33", "Regulator_Linear:ME6211C33M5", "Package_TO_SOT_SMD:SOT-23-5",
         {"1": "VMCU_IN", "2": "GND", "3": "VMCU_IN", "4": None, "5": "+3V3"}, "C82942", "ME6211C33M5G-N", B))
C("C16", "1uF", "+3V3", "GND", B)

# ================================================================ MCU
B = "MCU STM32G030K8"
add(Part("U3", "STM32G030K8T6", "MCU_ST_STM32G0:STM32G030K8Tx", "Package_QFP:LQFP-32_7x7mm_P0.8mm", {
    "1": None, "2": None, "3": None, "4": "+3V3", "5": "GND", "6": "NRST",
    "7": "VSENSE",          # PA0  ADC1_IN0
    "8": None,
    "9": "MCU_TX",          # PA2  USART2_TX
    "10": "MCU_RX",         # PA3  USART2_RX
    "11": None, "12": None,
    "13": "COIN_IN",        # PA6  TIM16_CH1 — захват фронтов (DMA)
    "14": "BILL_IN",        # PA7  TIM17_CH1 — захват фронтов (DMA)
    "15": "PWRKEY_CTL",     # PB0
    "16": "RESET_CTL",      # PB1
    "17": "VDDEXT_SENSE",   # PB2
    "18": "COIN_IN",        # PA8  TIM1_CH1 — аппаратный счётчик фронтов
    "19": None,
    "20": "BILL_IN",        # PC6  TIM3_CH1 — аппаратный счётчик фронтов
    "21": None,
    "22": "MCU_DBG_TX",     # PA9  USART1_TX
    "23": "MCU_DBG_RX",     # PA10 USART1_RX
    "24": "SWDIO", "25": "SWCLK",
    "26": "FRAM_CS",        # PA15 SPI1_NSS
    "27": "SPI_SCK",        # PB3
    "28": "SPI_MISO",       # PB4
    "29": "SPI_MOSI",       # PB5
    "30": "LED_PULSE",      # PB6
    "31": "LED_STATUS",     # PB7
    "32": "BTN",            # PB8
}, "C724044", "STM32G030K8T6TR", B))
C("C17", "10uF", "+3V3", "GND", B)
C("C18", "100nF", "+3V3", "GND", B, note="у вывода VDD")
C("C20", "100nF", "NRST", "GND", B)

# ================================================================ FRAM
B = "FRAM"
add(Part("U4", "FM25L16B", f"{LCSC_LIB}:FM25L16B-GTR_C466849", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
         {"1": "FRAM_CS", "2": "SPI_MISO", "3": "+3V3", "4": "GND", "5": "SPI_MOSI", "6": "SPI_SCK",
          "7": "+3V3", "8": "+3V3"}, "C466849", "FM25L16B-GTR", B, note="16 кбит, от 2.7 В"))
C("C21", "100nF", "+3V3", "GND", B)
R("R10", "10k", "+3V3", "FRAM_CS", B, note="FRAM не выбрана, пока MCU в сбросе")


# ================================================================ входы импульсов
def pulse_channel(name, j_ref, j_pins, j_fp, j_lcsc, j_mpn, first):
    b = f"Вход {name}"
    n = name
    rr, dd, uu, cc = first
    add(Part(j_ref, n, f"Connector_Generic:Conn_01x0{len(j_pins)}", j_fp, j_pins, j_lcsc, j_mpn, b,
             note="1 = +12 В акцептора, 2 = импульс"))
    R(f"R{rr}", "2.2k_1206", f"{n}_V12", f"{n}_R", b, note="≈5 мА через светодиод; 1206 на 12 В — 21 % номинала")
    D(f"D{dd}", "1N4148W", f"{n}_R", f"{n}_LA", b, "C81598", "1N4148W", "Diode_SMD:D_SOD-123",
      note="последовательный: при перепутанных +12 В и GND не просаживает линию аппарата")
    D(f"D{dd + 1}", "1N4148W", f"{n}_PULSE", f"{n}_LA", b, "C81598", "1N4148W", "Diode_SMD:D_SOD-123",
      note="параллельно светодиоду: обратное на светодиоде ≤ 0.7 В")
    add(Part(f"U{uu}", "EL817S1(B)", f"{LCSC_LIB}:EL817S1", f"{LCSC_LIB}:SOP-4_L6.5-W4.6-P2.54-LS10.2-TL",
             {"1": f"{n}_LA", "2": f"{n}_PULSE", "3": "GND", "4": f"{n}_OC"}, "C63268", "EL817S1(B)(TU)-F", b))
    R(f"R{rr + 1}", "4.7k", "+3V3", f"{n}_OC", b, note="подтяжка 4.7 кОм: задержка 2.2 мс")
    R(f"R{rr + 2}", "10k", f"{n}_OC", f"{n}_IN", b)
    C(f"C{cc}", "100nF", f"{n}_IN", "GND", b)


pulse_channel("COIN", "J2", {"1": "COIN_V12", "2": "COIN_PULSE"},
              "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", "C158012", "B2B-XH-A(LF)(SN)", (11, 6, 5, 22))
pulse_channel("BILL", "J3", {"1": "BILL_V12", "2": "BILL_PULSE", "3": None},
              "Connector_JST:JST_XH_B3B-XH-A_1x03_P2.50mm_Vertical", "C144394", "B3B-XH-A(LF)(SN)", (14, 8, 6, 23))

# ================================================================ модем
B = "Модем LTE Cat.1 bis"
GND_PINS = "1 10 27 34 36 37 40 41 45 46 47 48 70 71 72 73 88 89 90 91 92 93 94 95".split()
modem_pins: dict[str, str | None] = {str(n): None for n in range(1, 110)}
modem_pins.update({p: "GND" for p in GND_PINS})
modem_pins.update({
    "7": "MODEM_PWRKEY", "11": "SIM_DATA_M", "12": "SIM_RST_M", "13": "SIM_CLK_M", "14": "SIM_VDD",
    "15": "MODEM_RESET_N", "16": "NET_STATUS", "17": "MODEM_RXD", "18": "MODEM_TXD", "24": "VDD_EXT",
    "35": "ANT_MOD", "38": "MODEM_DBG_RX", "39": "MODEM_DBG_TX", "42": "VBAT", "43": "VBAT",
    "59": "USB_DP", "60": "USB_DN", "61": "VBUS", "82": "USB_BOOT",
})
add(Part("U7", "EG800K-EU", f"{LCSC_LIB}:EG800KEULC-I03-SNNSA_C44008839", f"{LCSC_LIB}:LGA-109_L17.7-W15.8-AIR780E",
         modem_pins, "C44008839", "EG800KEULC-I03-SNNSA", B,
         note="Quectel, LTE Cat.1 bis, B1/B3/B5/B7/B8/B20/B28; VBAT 3.4–4.3 В, логика 1.8 В"))
# обвязка VBAT по Hardware Design EG800K (§3.4.4): крупный конденсатор с низким ESR + массив 100n/33p/10p/3.9p/1.8p
CP("C33", "470uF/6.3V", "VBAT", "GND", B, "C54321567", "MA6.3V470M6X8",
   note="у модема; вместе с C8/C9 — 1410 мкФ под минимум VBAT 3.4 В")
C("C10", "22uF", "VBAT", "GND", B, note="у выводов VBAT модема")
C("C11", "100nF", "VBAT", "GND", B)
C("C12", "33pF", "VBAT", "GND", B)
C("C13", "10pF", "VBAT", "GND", B)
add(Part("C31", "3.9pF", "Device:C", FP[("C", "0402")], {"1": "VBAT", "2": "GND"}, "C1566", "0402CG3R9C500NT", B))
add(Part("C32", "1.8pF", "Device:C", FP[("C", "0402")], {"1": "VBAT", "2": "GND"}, "C1553", "0402CG1R8C500NT", B))
# UART: модем 1.8 В ↔ MCU 3.3 В. Сторона A питается от VDD_EXT модема: пока модем выключен,
# транслятор отключён и MCU не запитывает модем через линию.
add(Part("U9", "TXS0102", "Logic_LevelTranslator:TXS0102DCU", "Package_SO:VSSOP-8_2.3x2mm_P0.5mm",
         {"1": "MCU_RX", "2": "GND", "3": "VDD_EXT", "4": "MODEM_TXD", "5": "MODEM_RXD", "6": "VDD_EXT",
          "7": "+3V3", "8": "MCU_TX"}, "C53434", "TXS0102DCUR", B,
         note="A1=MODEM_RXD↔B1=MCU_TX, A2=MODEM_TXD↔B2=MCU_RX; OE от VDD_EXT"))
C("C34", "100nF", "VDD_EXT", "GND", B, note="VCCA транслятора")
C("C35", "100nF", "+3V3", "GND", B, note="VCCB транслятора")
R("R22", "10k", "VDD_EXT", "VDDEXT_SENSE", B, note="VDD_EXT 1.8 В → АЦП MCU: модем включён")
add(Part("Q1", "2N7002", "Transistor_FET:2N7002", "Package_TO_SOT_SMD:SOT-23",
         {"1": "PWRKEY_G", "2": "GND", "3": "MODEM_PWRKEY"}, "C8545", "2N7002", B, note="PWRKEY > 1 с — включение"))
R("R18", "1k", "PWRKEY_CTL", "PWRKEY_G", B)
R("R19", "100k", "PWRKEY_G", "GND", B)
add(Part("Q2", "2N7002", "Transistor_FET:2N7002", "Package_TO_SOT_SMD:SOT-23",
         {"1": "RESET_G", "2": "GND", "3": "MODEM_RESET_N"}, "C8545", "2N7002", B,
         note="RESET_N > 100 мс; после сброса модем выключен — включать через PWRKEY"))
R("R20", "1k", "RESET_CTL", "RESET_G", B)
R("R21", "100k", "RESET_G", "GND", B)

# ================================================================ SIM
B = "SIM-карта"
add(Part("J4", "NANO SIM", f"{LCSC_LIB}:NANOSIMXG6PH1.35", f"{LCSC_LIB}:SIM-SMD_NANO-SIM-XG6P-H1.35",
         {"1": "SIM_VDD", "2": "SIM_RST", "3": "SIM_CLK", "5": "GND", "6": None, "7": "SIM_DATA",
          "8": "GND", "9": "GND", "10": "GND", "11": "GND"}, "C7529386", "NANO SIM XG6P H1.35", B,
         note="откидная крышка — карта не выпадет от вибрации"))
R("R23", "22R", "SIM_DATA_M", "SIM_DATA", B)
R("R24", "22R", "SIM_RST_M", "SIM_RST", B)
R("R25", "22R", "SIM_CLK_M", "SIM_CLK", B)
R("R30", "15k", "SIM_VDD", "SIM_DATA", B, note="подтяжка данных SIM по Hardware Design EG800K, рис. 17")
C("C24", "100nF", "SIM_VDD", "GND", B)
C("C25", "33pF", "SIM_DATA", "GND", B)
C("C26", "33pF", "SIM_RST", "GND", B)
C("C27", "33pF", "SIM_CLK", "GND", B)
add(Part("U8", "SRV05-4", "Power_Protection:SRV05-4", "Package_TO_SOT_SMD:SOT-23-6",
         {"1": "SIM_DATA", "2": "GND", "3": "SIM_RST", "4": "SIM_CLK", "5": "SIM_VDD", "6": None},
         "C2836319", "SRV05-4", B, note="ESD у держателя, 0.6 пФ"))

# ================================================================ антенна
B = "Антенна"
R("R26", "0R_0402", "ANT_MOD", "ANT_OUT", B, note="П-цепь согласования: подбирается с антенной")
C("C28", "10pF", "ANT_MOD", "GND", B, dnp=True, note="не устанавливается")
C("C29", "10pF", "ANT_OUT", "GND", B, dnp=True, note="не устанавливается")
add(Part("J5", "U.FL", "Connector:Conn_Coaxial", "Connector_Coaxial:U.FL_Hirose_U.FL-R-SMT-1_Vertical",
         {"1": "ANT_OUT", "2": "GND"}, "C88374", "U.FL-R-SMT-1(80)", B, note="пигтейл на SMA в стенке корпуса"))

# ================================================================ индикация и кнопка
B = "Индикация и кнопка"
D("D10", "зелёный", "LED1_A", "GND", B, "C84260", "NCD0805G1", "LED_SMD:LED_0805_2012Metric", symbol="Device:LED",
  note="LED1: мигает на каждый принятый импульс")
R("R27", "1k", "LED_PULSE", "LED1_A", B)
D("D11", "красный", "LED2_A", "GND", B, "C84256", "NCD0805R1", "LED_SMD:LED_0805_2012Metric", symbol="Device:LED",
  note="LED2: сеть и последняя выгрузка")
R("R28", "1k", "LED_STATUS", "LED2_A", B)
add(Part("SW1", "ВЫГРУЗКА", f"{LCSC_LIB}:TS-1187A-B-A-B", f"{LCSC_LIB}:SW-SMD_4P-L5.1-W5.1-P3.70-LS6.5-TL_H1.5",
         {"1": "BTN", "2": None, "3": None, "4": "GND"}, "C318884", "TS-1187A-B-A-B", B,
         note="подключены площадки по диагонали — всегда разные контакты кнопки"))
R("R29", "10k", "+3V3", "BTN", B)
C("C30", "100nF", "BTN", "GND", B)

# ================================================================ отладка, контрольные точки, крепёж
B = "Отладка и крепёж"
add(Part("J6", "SWD", "Connector:Conn_ARM_SWD_TagConnect_TC2030-NL",
         "Connector:Tag-Connect_TC2030-IDC-NL_2x03_P1.27mm_Vertical",
         {"1": "+3V3", "2": "SWDIO", "3": "NRST", "4": "SWCLK", "5": "GND", "6": None}, block=B, in_bom=False,
         note="площадки под Tag-Connect для прошивки на производстве"))
for i, (net, note) in enumerate([
    ("VIN", ""), ("VBAT", ""), ("+3V3", ""), ("GND", ""),
    ("MCU_DBG_TX", "отладочный UART MCU"), ("MCU_DBG_RX", ""),
    ("MODEM_DBG_TX", "отладка модема"), ("MODEM_DBG_RX", ""),
    ("USB_DP", "USB модема — обновление его прошивки"), ("USB_DN", ""), ("VBUS", ""), ("USB_BOOT", ""),
    ("NET_STATUS", ""),
], start=1):
    TP(f"TP{i}", net, B, note)
for i in range(1, 5):
    add(Part(f"H{i}", "M3", "Mechanical:MountingHole_Pad", "MountingHole:MountingHole_3.2mm_M3_Pad_Via",
             {"1": "GND"}, block=B, in_bom=False))


def nets() -> dict[str, list[tuple[str, str]]]:
    out: dict[str, list[tuple[str, str]]] = {}
    for p in PARTS:
        for pin, net in p.pins.items():
            if net:
                out.setdefault(net, []).append((p.ref, pin))
    return out


if __name__ == "__main__":
    n = nets()
    print(f"деталей: {len(PARTS)}, в перечне: {sum(1 for p in PARTS if p.in_bom and not p.dnp)}, цепей: {len(n)}")
    lonely = [k for k, v in n.items() if len(v) < 2]
    print("цепи с одним выводом:", lonely or "нет")
