"""AISL-A glove carrier PCB v1 - generated schematic (KiCad 9 file format).

Run (any Python 3 works; KiCad's own is always there):
    "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" build_schematic.py

Writes, next to this file (overwriting):
    aisl_glove_carrier.kicad_sch     the schematic, opens in KiCad 9 with the PCB
    lib/aisl.kicad_sym               project symbol library (DevKit + MPU6050 module)
    sym-lib-table                    tells KiCad where that library is
    schematic/*.pdf, *.svg           printable copies
    checks/erc.json, erc_report.txt  KiCad electrical rules check
    checks/schematic_netlist.xml     netlist exported by KiCad, read by check_schematic_vs_pcb.py

KiCad 9 has no scripting API for schematics, so this script writes the file as text. Every
wire starts from a pin position computed out of the symbol library, and every point is
checked to be on the 1.27 mm grid. The proof that it is right is not this script but the
checks: KiCad's ERC, check_schematic_vs_pcb.py, and `kicad-cli pcb drc --schematic-parity`.

The circuit must stay equal to build_carrier_pcb.py. Decisions: THESIS/HANDOFF.md section 13.
"""
import math
import os
import re
import subprocess
import sys
import tempfile

from aisl_ids import PROJECT, ROOT_UUID, symbol_uuid, uid

HERE = os.path.dirname(os.path.abspath(__file__))
KICAD = os.environ.get("KICAD_DIR", r"C:\Program Files\KiCad\9.0")
CLI = os.path.join(KICAD, "bin", "kicad-cli.exe")
SYMDIR = os.path.join(KICAD, "share", "kicad", "symbols")
SNAP = os.path.join(HERE, "lib", "snapeda_original_symbols")   # untouched SnapEDA symbols
SYMLIB = os.path.join(HERE, "lib", "aisl.kicad_sym")
OUT = os.path.join(HERE, PROJECT + ".kicad_sch")

GRID = 1.27
DATE = "2026-11-18"

# Same order as FLEX in build_carrier_pcb.py and FLEX_PINS[] in the firmware.
# (net, DevKit pad, GPIO)
FLEX = [
    ("FLEX1", "J2-4", 39),
    ("FLEX2", "J2-5", 34),
    ("FLEX3", "J2-6", 35),
    ("FLEX4", "J2-7", 32),
    ("FLEX5", "J2-8", 33),
]

FP = {
    "U1": "aisl:ESP32-DevKitC-32D_socketed",
    "U2": "aisl:MPU6050_GY-521_module",
    "R": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal",
    "C": "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
    "JST": "Connector_JST:JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical",
    "HDR": "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    "HOLE": "MountingHole:MountingHole_3.2mm_M3",
}


# ---- symbol library handling ------------------------------------------------------------
def block(text, name):
    """Raw text of the top-level (symbol "name" ...) block of a .kicad_sym file."""
    m = re.search(r'\n\s*\(symbol "%s"' % re.escape(name), text)
    if not m:
        raise SystemExit("symbol not found: " + name)
    start = text.index("(", m.start())
    depth, i, in_str = 0, start, False
    while True:
        ch = text[i]
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
                return text[start:i + 1]
        i += 1


PIN_RE = re.compile(
    r'\(pin (\w+) (\w+)\s*\(at ([-\d.]+) ([-\d.]+) [-\d.]+\)[\s\S]*?'
    r'\(name "([^"]*)"[\s\S]*?\(number "([^"]*)"')


def pins_of(blk):
    """{pin number: (x, y, name, electrical type)} in library coordinates (Y up)."""
    return {m.group(6): (float(m.group(3)), float(m.group(4)), m.group(5), m.group(1))
            for m in PIN_RE.finditer(blk)}


def upgraded(path):
    """Text of a SnapEDA symbol file converted to the KiCad 9 format by kicad-cli."""
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "upgraded.kicad_sym")
        subprocess.run([CLI, "sym", "upgrade", "--force", "-o", out, path],
                       check=True, capture_output=True)
        with open(out, encoding="utf-8") as f:
            return f.read()


def set_property(blk, key, value):
    return re.sub(r'\(property "%s" "[^"]*"' % key, '(property "%s" "%s"' % (key, value), blk, count=1)


def rename(blk, old, new):
    blk = blk.replace('(symbol "%s"' % old, '(symbol "%s"' % new, 1)
    return blk.replace('(symbol "%s_' % old, '(symbol "%s_' % new)


def prepare_symbol_library():
    """Write lib/aisl.kicad_sym from the untouched SnapEDA symbols.

    Changes: KiCad 9 format, names that match the footprints, and the Footprint field
    pointing at our own footprints in lib/aisl.pretty. Pins are not touched.
    """
    esp = block(upgraded(os.path.join(SNAP, "ESP32-DEVKITC-32D.kicad_sym")), "ESP32-DEVKITC-32D")
    esp = rename(esp, "ESP32-DEVKITC-32D", "ESP32-DevKitC-32D")
    esp = set_property(esp, "Value", "ESP32-DevKitC-32D")
    esp = set_property(esp, "Footprint", FP["U1"])
    mpu = block(upgraded(os.path.join(SNAP, "OC09600.kicad_sym")), "OC09600")
    mpu = rename(mpu, "OC09600", "MPU6050_GY-521_module")
    mpu = set_property(mpu, "Value", "MPU6050_GY-521_module")
    mpu = set_property(mpu, "Footprint", FP["U2"])
    with open(SYMLIB, "w", encoding="utf-8", newline="\n") as f:
        f.write('(kicad_symbol_lib\n\t(version 20241209)\n\t(generator "kicad_symbol_editor")\n'
                '\t(generator_version "9.0")\n\t%s\n\t%s\n)\n' % (esp, mpu))
    with open(os.path.join(HERE, "sym-lib-table"), "w", encoding="utf-8", newline="\n") as f:
        f.write('(sym_lib_table\n  (version 7)\n  (lib (name "aisl")(type "KiCad")'
                '(uri "${KIPRJMOD}/lib/aisl.kicad_sym")(options "")'
                '(descr "AISL-A glove carrier: DevKit and MPU6050 module symbols"))\n)\n')
    return {"aisl:ESP32-DevKitC-32D": esp, "aisl:MPU6050_GY-521_module": mpu}


def stock_symbols():
    out = {}
    for lib, name in (("Device", "R"), ("Device", "C"), ("Connector_Generic", "Conn_01x02"),
                      ("power", "+3V3"), ("power", "GND"), ("power", "PWR_FLAG"),
                      ("Mechanical", "MountingHole")):
        with open(os.path.join(SYMDIR, lib + ".kicad_sym"), encoding="utf-8") as f:
            out["%s:%s" % (lib, name)] = block(f.read(), name)
    return out


SYMBOLS = prepare_symbol_library()
SYMBOLS.update(stock_symbols())
PINS = {lib_id: pins_of(blk) for lib_id, blk in SYMBOLS.items()}
assert len(PINS["aisl:ESP32-DevKitC-32D"]) == 38, len(PINS["aisl:ESP32-DevKitC-32D"])
assert len(PINS["aisl:MPU6050_GY-521_module"]) == 8, len(PINS["aisl:MPU6050_GY-521_module"])
assert len(PINS["Device:R"]) == 2 and len(PINS["Connector_Generic:Conn_01x02"]) == 2

# ---- schematic writer -------------------------------------------------------------------
ITEMS = []        # text of every schematic item, in order
PLACED = {}       # ref -> (lib_id, x, y, rotation)
CONNECTED = set() # (ref, pin number) that got a wire, label or power symbol
COUNT = {}


def n(kind):
    COUNT[kind] = COUNT.get(kind, 0) + 1
    return COUNT[kind]


def num(v):
    return ("%.4f" % v).rstrip("0").rstrip(".")


def q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def on_grid(*pts):
    for x, y in pts:
        for v in (x, y):
            assert abs(v / GRID - round(v / GRID)) < 1e-6, "off the 1.27 mm grid: %r" % ((x, y),)


def effects(justify=None, hide=False, size=1.27):
    s = "(effects (font (size %s %s))" % (num(size), num(size))
    if justify:
        s += " (justify %s)" % justify
    if hide:
        s += " (hide yes)"
    return s + ")"


def place(lib_id, ref, value, x, y, rot=0, footprint="", ref_at=None, val_at=None,
          in_bom=True, on_board=True):
    """Add a symbol. ref_at / val_at = (x, y, justify or None); None hides the field."""
    on_grid((x, y))
    PLACED[ref] = (lib_id, x, y, rot)
    key = "symbol:" + ref
    props = []
    for name, val, at in (("Reference", ref, ref_at), ("Value", value, val_at)):
        if at:
            props.append('(property "%s" %s (at %s %s 0) %s)'
                         % (name, q(val), num(at[0]), num(at[1]), effects(at[2])))
        else:
            props.append('(property "%s" %s (at %s %s 0) %s)'
                         % (name, q(val), num(x), num(y), effects(hide=True)))
    for name, val in (("Footprint", footprint), ("Datasheet", ""), ("Description", "")):
        props.append('(property "%s" %s (at %s %s 0) %s)' % (name, q(val), num(x), num(y), effects(hide=True)))
    pin_txt = "".join('\n\t\t(pin %s (uuid "%s"))' % (q(p), uid("%s:pin:%s" % (key, p)))
                      for p in PINS[lib_id])
    ITEMS.append(
        '(symbol (lib_id %s) (at %s %s %d) (unit 1)\n'
        '\t\t(exclude_from_sim no) (in_bom %s) (on_board %s) (dnp no)\n'
        '\t\t(uuid "%s")\n\t\t%s%s\n'
        '\t\t(instances (project %s (path "/%s" (reference %s) (unit 1))))\n\t)'
        % (q(lib_id), num(x), num(y), rot, "yes" if in_bom else "no",
           "yes" if on_board else "no", symbol_uuid(ref), "\n\t\t".join(props), pin_txt,
           q(PROJECT), ROOT_UUID, q(ref)))


def pin(ref, number):
    """Sheet position of a pin's connection point; marks the pin as used."""
    lib_id, x, y, rot = PLACED[ref]
    px, py = PINS[lib_id][number][:2]
    a = math.radians(rot)
    rx = px * math.cos(a) - py * math.sin(a)
    ry = px * math.sin(a) + py * math.cos(a)
    CONNECTED.add((ref, number))
    p = (round(x + rx, 4), round(y - ry, 4))     # the sheet's Y axis points down
    on_grid(p)
    return p


def wire(*pts):
    on_grid(*pts)
    for a, b in zip(pts, pts[1:]):
        assert a != b and (a[0] == b[0] or a[1] == b[1]), "wire must be horizontal or vertical: %r %r" % (a, b)
        ITEMS.append('(wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))'
                     % (num(a[0]), num(a[1]), num(b[0]), num(b[1]), uid("wire:%d" % n("wire"))))


def junction(p):
    on_grid(p)
    ITEMS.append('(junction (at %s %s) (diameter 0) (color 0 0 0 0) (uuid "%s"))'
                 % (num(p[0]), num(p[1]), uid("junction:%d" % n("junction"))))


def no_connect(p):
    ITEMS.append('(no_connect (at %s %s) (uuid "%s"))' % (num(p[0]), num(p[1]), uid("nc:%d" % n("nc"))))


def glabel(name, p, side, shape):
    """Global label. side 'right' = text runs to the right of p, 'left' = to the left."""
    on_grid(p)
    angle, just = (0, "left") if side == "right" else (180, "right")
    ITEMS.append(
        '(global_label %s (shape %s) (at %s %s %d) (fields_autoplaced yes) %s (uuid "%s")\n'
        '\t\t(property "Intersheetrefs" "${INTERSHEET_REFS}" (at %s %s 0) %s)\n\t)'
        % (q(name), shape, num(p[0]), num(p[1]), angle, effects(just),
           uid("glabel:%d" % n("glabel")), num(p[0]), num(p[1]), effects(just, hide=True)))


def power(kind, p, rot=0, show=True):
    """Power symbol (+3V3, GND or PWR_FLAG) with its pin at p."""
    i = n("pwr")
    ref = "#FLG%02d" % i if kind == "PWR_FLAG" else "#PWR%02d" % i
    val_at = None
    if show and rot == 0:
        dy = {"+3V3": -3.81, "GND": 5.08, "PWR_FLAG": -5.08}[kind]
        val_at = (p[0], p[1] + dy, None)
    place("power:" + kind, ref, kind, p[0], p[1], rot, val_at=val_at)
    return ref


def text(s, x, y, size=1.27, bold=False):
    font = "(font (size %s %s)%s)" % (num(size), num(size), " (bold yes)" if bold else "")
    ITEMS.append('(text %s (exclude_from_sim no) (at %s %s 0) (effects %s (justify left bottom)) (uuid "%s"))'
                 % (q(s), num(x), num(y), font, uid("text:%d" % n("text"))))


def rect(x0, y0, x1, y1):
    ITEMS.append('(rectangle (start %s %s) (end %s %s) (stroke (width 0) (type dash)) (fill (type none)) (uuid "%s"))'
                 % (num(x0), num(y0), num(x1), num(y1), uid("rect:%d" % n("rect"))))


# ---- the circuit ------------------------------------------------------------------------
# U1: ESP32 DevKit in the middle of the sheet
U1X, U1Y = 147.32, 99.06
place("aisl:ESP32-DevKitC-32D", "U1", "ESP32-DevKitC-32D (socketed)", U1X, U1Y, footprint=FP["U1"],
      ref_at=(U1X - 15.24, U1Y - 26.67, "left bottom"), val_at=(U1X - 15.24, U1Y + 29.21, "left bottom"))

x, y = pin("U1", "J2-1")                                   # 3V3
wire((x, y), (x - 5.08, y), (x - 5.08, y - 2.54))
power("+3V3", (x - 5.08, y - 2.54))
for name, pad, gpio in FLEX:
    x, y = pin("U1", pad)
    wire((x, y), (x - 5.08, y))
    glabel(name, (x - 5.08, y), "left", "input")
x, y = pin("U1", "J2-14")                                  # GND1
wire((x, y), (x - 5.08, y), (x - 5.08, y + 2.54))
power("GND", (x - 5.08, y + 2.54))
x, y = pin("U1", "J2-19")                                  # EXT_5V
wire((x, y), (x - 5.08, y))
glabel("+5V_EXT", (x - 5.08, y), "left", "passive")
for pad in ("J3-1", "J3-7"):                               # GND3, GND2: sideways symbols
    x, y = pin("U1", pad)
    wire((x, y), (x + 5.08, y))
    power("GND", (x + 5.08, y), rot=90, show=False)
for pad, name in (("J3-3", "I2C_SCL"), ("J3-6", "I2C_SDA")):   # IO22, IO21
    x, y = pin("U1", pad)
    wire((x, y), (x + 5.08, y))
    glabel(name, (x + 5.08, y), "right", "bidirectional")

# Flex channels: 3V3 -> J pin 2 -> flex sensor -> J pin 1 -> node -> 10k -> GND, 100n node -> GND
CELL_X, CELL_Y0, CELL_PITCH = 30.48, 38.1, 27.94
for i, (name, pad, gpio) in enumerate(FLEX, start=1):
    cy = CELL_Y0 + (i - 1) * CELL_PITCH
    j, r, c = "J%d" % i, "R%d" % i, "C%d" % i
    place("Connector_Generic:Conn_01x02", j, "Flex %d" % i, CELL_X, cy, rot=180, footprint=FP["JST"],
          ref_at=(CELL_X - 6.35, cy - 2.54, None), val_at=(CELL_X - 8.89, cy + 1.27, None))
    place("Device:R", r, "10k", CELL_X + 20.32, cy + 5.08, footprint=FP["R"],
          ref_at=(CELL_X + 22.86, cy + 3.81, "left"), val_at=(CELL_X + 22.86, cy + 6.35, "left"))
    place("Device:C", c, "100n", CELL_X + 33.02, cy + 5.08, footprint=FP["C"],
          ref_at=(CELL_X + 36.83, cy + 3.81, "left"), val_at=(CELL_X + 36.83, cy + 6.35, "left"))
    sig, v33 = pin(j, "1"), pin(j, "2")
    cy = sig[1]                                            # same value, without float noise
    assert sig[0] == v33[0] and abs(v33[1] - (cy - 2.54)) < 1e-6, (sig, v33)   # pin 2 above pin 1
    r1, r2, c1, c2 = pin(r, "1"), pin(r, "2"), pin(c, "1"), pin(c, "2")
    assert r1[1] < r2[1] and c1[1] < c2[1]                 # pin 1 on top = the signal node
    wire(v33, (v33[0] + 5.08, v33[1]), (v33[0] + 5.08, v33[1] - 2.54))
    power("+3V3", (v33[0] + 5.08, v33[1] - 2.54))
    end = (CELL_X + 45.72, cy)
    wire(sig, (r1[0], cy), (c1[0], cy), end)
    wire((r1[0], cy), r1)
    wire((c1[0], cy), c1)
    junction((r1[0], cy))
    junction((c1[0], cy))
    power("GND", r2)
    power("GND", c2)
    glabel(name, end, "right", "output")
    text("to U1 GPIO%d" % gpio, end[0], cy + 5.08)

# U2: MPU6050 module
U2X, U2Y = 236.22, 88.9
place("aisl:MPU6050_GY-521_module", "U2", "MPU6050 module (GY-521)", U2X, U2Y, footprint=FP["U2"],
      ref_at=(U2X - 10.16, U2Y - 11.43, "left bottom"), val_at=(U2X - 10.16, U2Y + 16.51, "left bottom"))
for pad, name in (("SCL", "I2C_SCL"), ("SDA", "I2C_SDA")):
    x, y = pin("U2", pad)
    wire((x, y), (x - 5.08, y))
    glabel(name, (x - 5.08, y), "left", "bidirectional")
x, y = pin("U2", "AD0")                                    # AD0 low = I2C address 0x68
wire((x, y), (x - 5.08, y))
power("GND", (x - 5.08, y), rot=270, show=False)
x, y = pin("U2", "VCC")
wire((x, y), (x + 5.08, y), (x + 5.08, y - 2.54))
power("+3V3", (x + 5.08, y - 2.54))
x, y = pin("U2", "GND")
wire((x, y), (x + 5.08, y), (x + 5.08, y + 2.54))
power("GND", (x + 5.08, y + 2.54))

# J6: optional 5 V input
J6X, J6Y = 228.6, 132.08
place("Connector_Generic:Conn_01x02", "J6", "5V IN", J6X, J6Y, footprint=FP["HDR"],
      ref_at=(J6X, J6Y - 3.81, None), val_at=(J6X + 3.81, J6Y + 1.27, "left"))
x, y = pin("J6", "1")
wire((x, y), (x - 2.54, y))
wire((x - 2.54, y), (x - 7.62, y))
power("PWR_FLAG", (x - 2.54, y))
glabel("+5V_EXT", (x - 7.62, y), "left", "passive")
x, y = pin("J6", "2")
wire((x, y), (x - 2.54, y), (x - 2.54, y + 2.54))
power("GND", (x - 2.54, y + 2.54))

# Power flags for the two rails the DevKit supplies
FY = 147.32
wire((132.08, FY), (142.24, FY))
power("+3V3", (132.08, FY))
power("PWR_FLAG", (142.24, FY))
wire((154.94, FY), (165.1, FY))
power("GND", (154.94, FY))
power("PWR_FLAG", (165.1, FY))

# Mounting holes (no electrical connection)
for k in range(1, 5):
    hx, hy = 185.42 + k * 10.16, 152.4
    place("Mechanical:MountingHole", "H%d" % k, "M3", hx, hy, footprint=FP["HOLE"], in_bom=False,
          ref_at=(hx, hy - 3.81, None), val_at=(hx, hy + 3.81, None))

# Every pin that got nothing above is deliberately unused: mark it.
for ref in ("U1", "U2"):
    for number in PINS[PLACED[ref][0]]:
        if (ref, number) not in CONNECTED:
            no_connect(pin(ref, number))
            CONNECTED.discard((ref, number))

# Notes
rect(15.24, 20.32, 101.6, 165.1)
text("Flex sensor inputs: 5 identical channels", 17.78, 25.4, 1.6, bold=True)
text("AISL-A glove carrier PCB v1", 106.68, 22.86, 2.2, bold=True)
text("\n".join([
    "FLEX: 3V3 -> flex sensor -> FLEXn node -> 10k -> GND. The ESP32 reads the node voltage (ADC1).",
    "  The 100 nF from each node to GND smooths the reading.",
    "  Each sensor plugs into a 2-pin JST-XH socket (J1-J5). Either way round works.",
    "  FLEX1-5 = GPIO 39, 34, 35, 32, 33: the same order as FLEX_PINS[] in hand_sign_glove_ble.ino.",
    "  GPIO39 is the DevKit pin named SENSOR_VN (printed VN on the board).",
    "IMU: MPU6050 module (GY-521) on I2C. SDA = GPIO21, SCL = GPIO22. AD0 to GND = address 0x68.",
    "  The module has its own I2C pull-up resistors, so the carrier has none.",
    "POWER: USB on the DevKit. J6 is an optional 5 V input to the DevKit EXT_5V pin.",
    "  Use USB or J6, never both at once. 3V3 comes from the DevKit's regulator.",
    "PWR_FLAG is not a part. It only tells KiCad's rule check that the net has a supply.",
    "Pins marked X are unused. H1-H4 are M3 mounting holes.",
]), 106.68, 48.26)
text("MPU6050 under the DevKit on the PCB", U2X - 10.16, U2Y - 15.24)
text("Optional 5 V input", J6X - 12.7, J6Y - 8.89)
text("Rule-check flags (not parts)", 132.08, FY + 11.43)
text("Mounting holes", 195.58, 144.78)

# ---- write the file ---------------------------------------------------------------------
lib_symbols = "\n".join(
    "\t\t" + blk.replace('(symbol "%s"' % lib_id.split(":")[1], '(symbol "%s"' % lib_id, 1)
    for lib_id, blk in sorted(SYMBOLS.items()))
sch = (
    '(kicad_sch\n\t(version 20250114)\n\t(generator "eeschema")\n\t(generator_version "9.0")\n'
    '\t(uuid "%s")\n\t(paper "A4")\n'
    '\t(title_block\n\t\t(title "AISL-A glove carrier PCB v1")\n\t\t(date "%s")\n\t\t(rev "v1")\n'
    '\t\t(comment 1 "Generated by build_schematic.py. Edit the script, not this file.")\n'
    '\t\t(comment 2 "Matches aisl_glove_carrier.kicad_pcb (checked by KiCad schematic parity).")\n\t)\n'
    '\t(lib_symbols\n%s\n\t)\n\t%s\n'
    '\t(sheet_instances\n\t\t(path "/"\n\t\t\t(page "1")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n'
    % (ROOT_UUID, DATE, lib_symbols, "\n\t".join(ITEMS)))
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(sch)
print("wrote", OUT, "-", len(PLACED), "symbols,", COUNT.get("wire", 0), "wires,", COUNT.get("nc", 0), "no-connects")

# ---- KiCad's own checks and exports -----------------------------------------------------
if "--no-export" not in sys.argv:
    os.makedirs(os.path.join(HERE, "checks"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "schematic"), exist_ok=True)
    jobs = [
        ["sch", "erc", "--severity-all", "--format", "json", "-o", "checks/erc.json"],
        ["sch", "erc", "--severity-all", "-o", "checks/erc_report.txt"],
        ["sch", "export", "netlist", "--format", "kicadxml", "-o", "checks/schematic_netlist.xml"],
        ["sch", "export", "pdf", "-o", "schematic/aisl_glove_carrier_schematic.pdf"],
        ["sch", "export", "svg", "-o", "schematic"],
    ]
    for job in jobs:
        res = subprocess.run([CLI] + job + [os.path.basename(OUT)], cwd=HERE, capture_output=True, text=True)
        print(" ".join(job[:3]), "->", (res.stdout + res.stderr).strip().splitlines()[-1:] or "ok")
