#!/usr/bin/env python3
"""Draws docs/wiring.svg. Pins must match firmware/src/config.h.  Run: python3 docs/make_wiring_svg.py"""
from pathlib import Path

W, H = 1060, 760
out = []
add = out.append

C = dict(trig="#6b46c1", echo="#0f766e", hx="#2563eb", servo="#dd6b20", ir="#b7791f",
         v5="#d62828", v33="#e67e00", gnd="#222", box="#f3f4f6", line="#444")

# ESP32-DevKitC 38-pin, USB at the bottom, chip side up
LEFT = ["3V3", "EN", "VP", "VN", "34", "35", "32", "33", "25", "26", "27", "14", "12", "GND", "13", "D2", "D3", "CMD", "5V"]
RIGHT = ["GND", "23", "22", "TX", "RX", "21", "GND", "19", "18", "5", "17", "16", "4", "0", "2", "15", "D1", "D0", "CLK"]
USED = {"32", "33", "25", "26", "19", "18", "23", "22", "21"}
BX0, BX1, PY0, PS = 410, 610, 140, 22


def py(col, label):
    return PY0 + PS * col.index(label)


def text(x, y, s, size=13, anchor="start", weight="normal", fill="#111"):
    add(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{s}</text>')


def wire(pts, color, w=2.4):
    d = " ".join(f"{x},{y}" for x, y in pts)
    add(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{w}" stroke-linejoin="round"/>')


def dot(x, y, color="#111", r=3.5):
    add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{color}"/>')


def box(x, y, w, h, title, sub=""):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{C["box"]}" stroke="{C["line"]}" stroke-width="1.5"/>')
    text(x + w / 2, y - 8, title, 14, "middle", "bold")
    if sub:
        text(x + w / 2, y + h + 16, sub, 11.5, "middle", fill="#555")


def pin(x, y, label, side):
    """Pin stub on a module edge. side='r' -> pin on the right edge, label inside to the left."""
    dot(x, y, "#111", 3)
    if side == "r":
        text(x - 8, y + 4, label, 12, "end")
    else:
        text(x + 8, y + 4, label, 12)


def tag(x, y, kind, side):
    col = {"5V": C["v5"], "3V3": C["v33"], "GND": C["gnd"]}[kind]
    w = 38
    x0 = x + 6 if side == "r" else x - 6 - w
    wire([(x, y), (x0 + (0 if side == "r" else w), y)], col, 2)
    add(f'<rect x="{x0}" y="{y - 9}" width="{w}" height="18" rx="9" fill="{col}"/>')
    text(x0 + w / 2, y + 4, kind, 11, "middle", "bold", "#fff")


def resistor(x, y, label, vertical=False):
    if vertical:
        add(f'<rect x="{x - 6}" y="{y}" width="12" height="28" fill="#fff" stroke="#111" stroke-width="1.5"/>')
        text(x - 10, y + 18, label, 11.5, "end")
    else:
        add(f'<rect x="{x}" y="{y - 6}" width="34" height="12" fill="#fff" stroke="#111" stroke-width="1.5"/>')
        text(x + 17, y - 10, label, 11.5, "middle")


def ground(x, y):
    for i, half in enumerate((9, 6, 3)):
        add(f'<line x1="{x - half}" y1="{y + i * 4}" x2="{x + half}" y2="{y + i * 4}" stroke="#111" stroke-width="1.6"/>')


add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="Helvetica, Arial, sans-serif">')
add(f'<rect width="{W}" height="{H}" fill="#fff"/>')
text(W / 2, 30, "SmartBin wiring: one ESP32 (38-pin) for both bins", 19, "middle", "bold")

# ---------------- ESP32
add(f'<rect x="{BX0}" y="{PY0 - 25}" width="{BX1 - BX0}" height="{PS * 18 + 50}" rx="10" fill="#1f2937"/>')
add(f'<rect x="{BX0 + 55}" y="{PY0 - 15}" width="90" height="70" rx="4" fill="#9ca3af"/>')
text((BX0 + BX1) / 2, PY0 + 25, "WROOM-32", 11, "middle", "bold", "#1f2937")
add(f'<rect x="{(BX0 + BX1) / 2 - 18}" y="{PY0 + PS * 18 + 18}" width="36" height="22" rx="3" fill="#9ca3af"/>')
text((BX0 + BX1) / 2, PY0 + PS * 18 + 58, "USB → Raspberry Pi 5 (power + data)", 12.5, "middle", "bold")
text((BX0 + BX1) / 2, PY0 - 52, "ESP32 DevKit 38-pin", 14, "middle", "bold")
text((BX0 + BX1) / 2, PY0 - 36, "top view, USB at the bottom", 11.5, "middle", fill="#555")
pcol = {"5V": C["v5"], "3V3": C["v33"], "GND": "#e5e7eb"}
for col, x, anchor, dx in ((LEFT, BX0, "start", 8), (RIGHT, BX1, "end", -8)):
    for lab in col:
        y = py(col, lab)
        used = lab in USED or lab in pcol
        dot(x, y, "#facc15" if used else "#6b7280", 4)
        fill = pcol.get(lab, "#fff" if used else "#9ca3af")
        name = lab if not lab.isdigit() else f"GPIO{lab}"
        text(x + dx, y + 4, name, 12, anchor, "bold" if used else "normal", fill)

# ---------------- Bin 1 HC-SR04 (left top)
x1, ys = 90, dict(VCC=130, TRIG=150, ECHO=170, GND=190)
box(x1, 112, 170, 96, "Bin 1 HC-SR04", "in bin 1 lid, pins face front")
for k, y in ys.items():
    pin(x1 + 170, y, k, "r")
tag(x1 + 170, ys["VCC"], "5V", "r")
tag(x1 + 170, ys["GND"], "GND", "r")
wire([(260, ys["TRIG"]), (380, ys["TRIG"]), (380, py(LEFT, "32")), (BX0, py(LEFT, "32"))], C["trig"])
wire([(260, ys["ECHO"]), (276, ys["ECHO"])], C["echo"])
resistor(276, ys["ECHO"], "1 kΩ")
wire([(310, ys["ECHO"]), (355, ys["ECHO"]), (355, py(LEFT, "33")), (BX0, py(LEFT, "33"))], C["echo"])
dot(324, ys["ECHO"])
wire([(324, ys["ECHO"]), (324, ys["ECHO"] + 10)], "#111", 1.6)
resistor(324, ys["ECHO"] + 10, "2 kΩ", True)
wire([(324, ys["ECHO"] + 38), (324, ys["ECHO"] + 46)], "#111", 1.6)
ground(324, ys["ECHO"] + 46)

# ---------------- Bin 2 HC-SR04 (left, lower)
y2 = dict(VCC=330, TRIG=350, ECHO=370, GND=390)
box(x1, 312, 170, 96, "Bin 2 HC-SR04 (dummy bin)", "in bin 2 lid, pins face front")
for k, y in y2.items():
    pin(x1 + 170, y, k, "r")
tag(x1 + 170, y2["VCC"], "5V", "r")
tag(x1 + 170, y2["GND"], "GND", "r")
wire([(260, y2["TRIG"]), (370, y2["TRIG"]), (370, py(LEFT, "25")), (BX0, py(LEFT, "25"))], C["trig"])
wire([(260, y2["ECHO"]), (276, y2["ECHO"])], C["echo"])
resistor(276, y2["ECHO"], "1 kΩ")
wire([(310, y2["ECHO"]), (345, y2["ECHO"]), (345, py(LEFT, "26")), (BX0, py(LEFT, "26"))], C["echo"])
dot(324, y2["ECHO"])
wire([(324, y2["ECHO"]), (324, y2["ECHO"] + 10)], "#111", 1.6)
resistor(324, y2["ECHO"] + 10, "2 kΩ", True)
wire([(324, y2["ECHO"] + 38), (324, y2["ECHO"] + 46)], "#111", 1.6)
ground(324, y2["ECHO"] + 46)

# ---------------- FC-51 IR (right top), OUT straight across to GPIO23
xr = 770
yi = dict(VCC=py(RIGHT, "23") - 40, GND=py(RIGHT, "23") - 20, OUT=py(RIGHT, "23"))
box(xr, yi["VCC"] - 14, 130, 66, "Bin 1 FC-51 IR (shell front)", "")
for k, y in yi.items():
    pin(xr, y, k, "l")
tag(xr, yi["VCC"], "3V3", "l")
tag(xr, yi["GND"], "GND", "l")
wire([(xr, yi["OUT"]), (BX1, yi["OUT"])], C["ir"])
text(xr + 140, yi["OUT"] + 4, "LOW = hand", 11.5, fill="#555")

# ---------------- HX711 (right), DT -> GPIO22, SCK -> GPIO21
yh = dict(GND=py(RIGHT, "21") - 40, DT=py(RIGHT, "21") - 20, SCK=py(RIGHT, "21"), VCC=py(RIGHT, "21") + 20)
box(xr, yh["GND"] - 12, 130, 84, "Bin 1 HX711 (deck, inside shell 1)", "")
for k, y in yh.items():
    pin(xr, y, k, "l")
tag(xr, yh["GND"], "GND", "l")
tag(xr, yh["VCC"], "3V3", "l")
wire([(xr, yh["DT"]), (690, yh["DT"]), (690, py(RIGHT, "22")), (BX1, py(RIGHT, "22"))], C["hx"])
wire([(xr, yh["SCK"]), (BX1, yh["SCK"])], C["hx"])
cell = [("E+", "red", "#d62828"), ("E−", "black", "#222"), ("A−", "white", "#bbb"), ("A+", "green", "#16a34a")]
for i, (lab, name, col) in enumerate(cell):
    y = yh["GND"] + i * 20
    pin(xr + 130, y, lab, "r")
    wire([(xr + 130, y), (960, y)], col, 3)
    text(966, y + 4, name, 11.5)
add(f'<rect x="1010" y="{yh["GND"] - 12}" width="28" height="84" rx="4" fill="#cbd5e1" stroke="#444"/>')
text(1024, yh["GND"] + 100, "1 kg", 11.5, "middle")
text(1024, yh["GND"] + 114, "load cell", 11.5, "middle")

# ---------------- Servos (right, lower)
ys1 = dict(SIG=py(RIGHT, "19") + 46, V=py(RIGHT, "19") + 66, G=py(RIGHT, "19") + 86)
box(xr, ys1["SIG"] - 14, 130, 68, "Bin 1 SG90 servo", "")
for k, lab in (("SIG", "orange"), ("V", "red"), ("G", "brown")):
    pin(xr, ys1[k], lab, "l")
tag(xr, ys1["V"], "5V", "l")
tag(xr, ys1["G"], "GND", "l")
wire([(xr, ys1["SIG"]), (720, ys1["SIG"]), (720, py(RIGHT, "19")), (BX1, py(RIGHT, "19"))], C["servo"])

ys2 = dict(SIG=ys1["G"] + 60, V=ys1["G"] + 80, G=ys1["G"] + 100)
box(xr, ys2["SIG"] - 14, 130, 68, "Bin 2 SG90 servo", "")
for k, lab in (("SIG", "orange"), ("V", "red"), ("G", "brown")):
    pin(xr, ys2[k], lab, "l")
tag(xr, ys2["V"], "5V", "l")
tag(xr, ys2["G"], "GND", "l")
wire([(xr, ys2["SIG"]), (660, ys2["SIG"]), (660, py(RIGHT, "18")), (BX1, py(RIGHT, "18"))], C["servo"])

# ---------------- 470 uF + legend
yc = ys2["G"] + 36
add(f'<rect x="{xr}" y="{yc}" width="270" height="52" rx="8" fill="#fff7ed" stroke="{C["servo"]}"/>')
text(xr + 12, yc + 21, "470 µF (≥10 V) across 5V and GND,", 12.5, weight="bold")
text(xr + 12, yc + 39, "next to the servo headers. Stripe side = GND.", 12)

yl = 470
add(f'<rect x="40" y="{yl}" width="330" height="250" rx="8" fill="#f9fafb" stroke="#ddd"/>')
text(56, yl + 26, "Power rails (on the connector perfboard)", 13.5, weight="bold")
legend = [
    ("5V", "all 5V tags ↔ ESP32 5V pin (comes from USB)"),
    ("3V3", "all 3V3 tags ↔ ESP32 3V3 pin"),
    ("GND", "all GND tags + ground symbols ↔ ESP32 GND"),
]
for i, (k, s) in enumerate(legend):
    y = yl + 54 + i * 26
    col = {"5V": C["v5"], "3V3": C["v33"], "GND": C["gnd"]}[k]
    add(f'<rect x="56" y="{y - 9}" width="38" height="18" rx="9" fill="{col}"/>')
    text(75, y + 4, k, 11, "middle", "bold", "#fff")
    text(102, y + 4, s, 12)
sig = [("trig", "TRIG (3.3 V out is fine)"), ("echo", "ECHO, via 1k / 2k divider (5 V → 3.3 V)"),
       ("hx", "HX711 DT / SCK"), ("servo", "servo signal"), ("ir", "IR output")]
for i, (k, s) in enumerate(sig):
    y = yl + 140 + i * 20
    wire([(56, y), (94, y)], C[k], 3)
    text(102, y + 4, s, 12)

add("</svg>")
Path(__file__).with_name("wiring.svg").write_text("\n".join(out))
print("wrote docs/wiring.svg")
