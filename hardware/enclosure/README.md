# AISL-A wrist enclosure — V1 fit prototype

**Current revision: [V2 assembled-perfboard enclosure](v2/README.md).** The supplied photos
show one 90 × 60 × 30 mm assembly, so V2 replaces the separate board mounts/IMU shelf below.
V1 remains available as an earlier prototype; use the V2 files for the current assembly.

Designed through Blender MCP on 2026-10-28. User decisions: **USB power for now;
MPU6050 on the back of the wrist.** The IMU sits inside the box on a rigid removable
shelf. Wear the box on the back of the right wrist.

This is a dimensioned fit prototype. Board illustrations are nominal clearance
envelopes, not imported STEP assemblies. Physical board, connector, wiring and strap
fit still need checking before final fabrication.

Access revision (2026-10-28): enlarged USB to **26 × 16 mm** and BOOT/EN to **16 × 10 mm
each**, following the user's note that the ESP32 sits at the edge of the soldered board.
Opening centres remain at the nominal positions below; measure the actual assembly to
confirm alignment. The screw pilot sizes and circuit mounting geometry remain unchanged.

## Files

- `AISL-A_Enclosure_V1.blend`: editable model; assembled, exploded and print-layout scenes.
- `AISL-A_V1_Print_Files.zip`: four STLs, these notes and the standalone STL checker/report.
- `exports/01_base.stl`: shell, strap loops, screw bosses and cable anchors.
- `exports/02_lid.stl`: lid, locating lip, button access and recessed lettering.
- `exports/03_carrier.stl`: electronics tray, support rails and IMU shelf towers.
- `exports/04_imu_shelf.stl`: MPU6050 shelf, locating pocket and tie slots.
- `assembly_preview.png`, `exploded_preview.png`: renders; electronics are schematic.
- `build_enclosure.py`: rebuildable Blender source, also embedded in the blend file.
- `validation.json`: mesh topology and nominal assembly collision checks.
- `verify_stl.py`, `stl_validation.json`: independent exported-triangle verification.

## Dimensions and layout

All dimensions are millimetres. Import the STLs at **100% in millimetres**. Blender uses
a 0.001 metre scene scale. +X faces the fingers/cable exit; -X faces the forearm/USB.
Z=0 is the underside of the shell in the assembled scene.

| Feature | Dimension / location |
|---|---|
| Closed body | 90 × 60 × 30 |
| Including strap loops | 90 × 84 × 30 |
| Walls / floor | 2.4 / 2.4 |
| Lid | 2.8 thick, with a 1.8-deep locating lip |
| Lip fit allowance | 0.30 per side against the inner wall |
| Strap slots | 26 × 6 clear; for a 20–25 wide strap |
| USB wall opening | 26 wide × 16 high; centre (-45, 0, 15.8) |
| Flex-wire exit | 22 wide × 6 high, at the +X lid split |
| BOOT / EN tool openings | 16 × 10 each; centres (-35, -8) / (-35, +8) |
| Lid screws | M3; XY centres (±38.4, ±23.4) |
| Carrier screws | M2.5; XY centres (±30, ±19) |
| Shelf screws | M2.5; XY centres (20, ±18.5) |
| Carrier | 76 × 43; deck 2 thick, total height 15 including towers |
| ESP32 PCB envelope | 54.4 × 27.9; centre (-14, 0); underside Z=13 |
| Divider perfboard envelope | 18 × 30; centre (27.5, 0); underside Z=11 |
| MPU6050 envelope | 20.3 × 15.7 × 3; centre (27, 0); underside Z=22.4 |
| IMU pocket | 20.8 × 16.2; 0.25 allowance per side |

ESP32 outline source: the F.Fab outline in
`Glove kicad/ESP32-DE-KIT/MODULE_ESP32-DEVKITC-32D.kicad_mod`. USB/button locations and
component heights are approximate. MPU6050 size comes from the vertex extents in
`Glove kicad/MPU-6050/OC09600.step`. The perfboard size is proposed; the actual populated
divider assembly has not been measured.

ESP32 support rails sit between its header rows, with nominal 5.6 clearance for pin tails
above the carrier deck. Two cable ties retain the board; no ESP32 mounting holes are assumed.
The divider board sits on shorter rails at the finger end. The MPU shelf fits above it;
removing two screws exposes the divider board. The IMU locating pocket and a small tie
hold the module against the shelf.

## Hardware and assembly

Starting fasteners, subject to checking the printed pilot fit:

- 4 × M3 × 10 pan-head screws for the lid; 3.4 clearance and 2.6 blind pilots.
- 6 × M2.5 × 5 pan-head screws: four carrier and two shelf screws;
  2.8 clearance and 2.0 blind pilots.
- Small cable ties, up to 2.5 wide, for boards and harness.
- One 20–25 wide Velcro strap and optional 2-thick EVA foam under the body.

The screws engage direct plastic pilot holes. Check engagement on a print and stop when
snug. Electronics, screws, strap and foam are not included in the STLs.

1. Tie the ESP32 and divider assembly to the carrier. Insulate wire joints from the ESP32
   underside. Check actual USB and BOOT/EN alignment.
2. Fasten the carrier to the four base pedestals.
3. Screw the IMU shelf onto its towers. Tie the MPU6050 into its pocket. Use low-profile
   soldered leads or a horizontal connection: tall pin headers are outside the 3 mm module
   envelope. Check lead bends and tie-head clearance beneath the lid.
4. Route the flex leads through the +X notch. Use the two internal anchor tunnels for a
   harness tie. Keep wires and the tie head below the lid seating surface. This is a flat
   loom opening; its clear height is 6 mm.
5. Screw on the lid, thread the strap through both loops and add foam underneath.

Record the installed IMU orientation and keep that orientation and wrist position the same
for training and inference. This location measures wrist motion. Account for placement
changes when collecting data if earlier takes used another IMU position.

## Printing and fit checks

STLs are already on Z=0: base open side up, lid exterior down, carrier deck down and shelf
underside down. A starting fit print is 0.2 layer height, 0.4 nozzle, 4 walls and 4–5
top/bottom layers. Inspect the slicer preview. PLA can be used for an initial fit sample;
select the eventual material after strap and opening-cycle trials. The USB roof is a
26 mm bridge; use local support if needed. Strap slots, tie tunnels and cosmetic lid text
may also need slicer adjustments.

Measure the actual PCB, USB plug overmould, buttons, header tails, IMU connections and
populated perfboard before a final print. Button openings provide tool access, without
button extenders. Check that screws do not bottom out, strap slots fit, and tie slots can
be threaded before final assembly.

Each print mesh is one closed component with positive volume. Nominal collision checks
separate coincident seating faces by 0.02 mm to avoid coplanar calculation artifacts;
they do not establish printer tolerances or physical fit. Sub-micron Boolean slivers are
welded within 0.001 mm before triangulation. The binary STLs are separately checked for
dimensions, Z=0, edge pairing, degenerate triangles and positive volume. Repeat with:

```powershell
python hardware/enclosure/verify_stl.py
```

To rebuild, run `build_enclosure.py` in Blender without an existing enclosure scene. It
creates dedicated scenes and preserves the original scene. Dimensions are editable in
the source; some derived coordinates are explicit and must be updated together. It refuses
to replace an existing enclosure scene automatically.
