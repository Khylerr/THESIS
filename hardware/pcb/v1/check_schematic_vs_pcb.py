"""Independent check that the schematic and the PCB describe the same circuit.

Run with KiCad's Python, after build_schematic.py and build_carrier_pcb.py:
    "C:\\Program Files\\KiCad\\9.0\\bin\\python.exe" check_schematic_vs_pcb.py

Reads checks/schematic_netlist.xml (exported from the schematic by KiCad) and the board file,
and compares part by part and pad by pad: reference, value, footprint, and the net on every
pad. Writes checks/schematic_vs_pcb.json and exits 1 on any difference.

This does not use KiCad's own parity check on purpose, so the two checks back each other up:
    kicad-cli pcb drc --schematic-parity ...
"""
import json
import os
import sys
import xml.etree.ElementTree as ET

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
root = ET.parse(os.path.join(HERE, "checks", "schematic_netlist.xml")).getroot()
board = pcbnew.LoadBoard(os.path.join(HERE, "aisl_glove_carrier.kicad_pcb"))

sch_parts = {c.get("ref"): {"value": c.findtext("value"), "footprint": c.findtext("footprint")}
             for c in root.find("components")}
sch_pads = {}
for net in root.find("nets"):
    for node in net:
        sch_pads[(node.get("ref"), node.get("pin"))] = net.get("name")

pcb_parts, pcb_pads = {}, {}
for fp in board.GetFootprints():
    ref = fp.GetReference()
    pcb_parts[ref] = {"value": fp.GetValue(), "footprint": str(fp.GetFPID().GetUniStringLibId())}
    for pad in fp.Pads():
        if pad.GetNumber():                      # unnamed pads are plain mounting holes
            pcb_pads[(ref, pad.GetNumber())] = pad.GetNetname()

problems = []
for ref in sorted(set(sch_parts) | set(pcb_parts)):
    if ref not in pcb_parts:
        problems.append("%s is in the schematic but not on the PCB" % ref)
    elif ref not in sch_parts:
        problems.append("%s is on the PCB but not in the schematic" % ref)
    else:
        for key in ("value", "footprint"):
            if sch_parts[ref][key] != pcb_parts[ref][key]:
                problems.append("%s %s: schematic %r, PCB %r" % (ref, key, sch_parts[ref][key], pcb_parts[ref][key]))
for key in sorted(set(sch_pads) | set(pcb_pads)):
    s, p = sch_pads.get(key), pcb_pads.get(key)
    if s != p:
        problems.append("%s pad %s: schematic net %r, PCB net %r" % (key[0], key[1], s, p))

nets = {}
for (ref, pad), name in sorted(pcb_pads.items()):
    if not name.startswith("unconnected-("):
        nets.setdefault(name, []).append("%s.%s" % (ref, pad))
report = {
    "parts_schematic": len(sch_parts), "parts_pcb": len(pcb_parts),
    "pads_schematic": len(sch_pads), "pads_pcb": len(pcb_pads),
    "connected_nets": len(nets),
    "unused_pads": sum(1 for v in pcb_pads.values() if v.startswith("unconnected-(")),
    "problems": problems, "nets": nets,
}
with open(os.path.join(HERE, "checks", "schematic_vs_pcb.json"), "w") as f:
    json.dump(report, f, indent=1)
print(json.dumps({k: v for k, v in report.items() if k != "nets"}, indent=1))
sys.exit(1 if problems else 0)
