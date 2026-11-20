# AISL-A enclosure V2 — assembled perfboard

**Progress-report renders (2026-11-07):** [four-view figure and captions](report_renders_2026-11-07/captions.md).
The dated folder contains white-background 2400 px renders, a dimension sheet, a combined
four-panel figure, camera source and a separate report-view Blender project.

Current photo-based fit prototype, 2026-10-28. This revision accommodates the entire
soldered board shown in the user's photos: ESP32 on sockets near the USB corner, five
divider channels on the same brown perfboard, and MPU6050 overhanging the opposite edge.
The separate ESP32/divider mounts and separate IMU shelf from V1 are superseded.

The user supplied **9 × 6 × 3 cm**. V2 conservatively treats that as a **90 × 60 mm main
perfboard and 30 mm occupied assembly height**, then reserves extra space for the MPU
overhang, mounting hardware, pins and the USB plug. Component offsets, overhang and board
hole positions are estimated from the photographs and must be measured for final fit.

Strap revision (2026-10-28): the two loops are now on the **short ends** (+X and -X),
low on the base beneath the USB opening. Slot centres are (±67, 0), with 26 mm along Y
and 6 mm along X. Overall size including the loops is now **146 × 86 × 42 mm**.

Lid revision (2026-10-28): removed the large AISL-A name engraving at the user's request.

IMU access revision (2026-10-28): added a **26 × 14 mm opening on the -X short end**,
opposite USB, centred at Y=17, Z=25.4 to match the provisional MPU6050 position.

## Delivery

- `AISL-A_Enclosure_V2.blend`: editable assembly, exploded and print-layout scenes. V1
  scenes remain available for comparison; the active scene is V2.
- `AISL-A_V2_Print_Files.zip`: three STLs, these notes, the exported STL check script/report.
- `exports/01_base.stl`: shell, strap loops, cradle pedestals and harness anchors.
- `exports/02_lid.stl`: screw lid, locating lip and integral removable cable-wall apron.
- `exports/03_perfboard_cradle.stl`: open frame supporting the complete board at its corners.
- `assembly_preview.png`, `exploded_preview.png`, `internal_layout_preview.png`: renders.
- `imu_access_preview.png`: view of the opposite end showing the new IMU opening.
  The electronic models are schematic layout envelopes, not exact component CAD.
- `build_enclosure_v2.py`: source; uses helpers in `../build_enclosure.py`, with both sources
  embedded in the blend file. Run the disk source from Blender to rebuild in fresh V2 scenes.
- `validation.json`: printed-part topology and nominal component/part collision checks.
- `verify_stl.py`, `stl_validation.json`: independent binary STL checks, without Blender.

## Dimensions

All dimensions are **mm**. Import STLs at **100% in millimetres**.

| Feature | V2 dimension / position |
|---|---|
| Closed body | 122 × 86 × 42 |
| Overall including strap loops | 146 × 86 × 42 |
| Floor / walls / lid skin | 2.8 / 2.8 / 2.8 |
| Main inner footprint | 116.4 × 80.4 |
| Main perfboard | 90 × 60, centre X=8, Y=0 |
| Perfboard underside | Z=14; top Z=15.6 in the reference model |
| Lowest solder allowance | Z=6; 3.2 clearance above the floor |
| Full occupied assembly allowance | Z=6–36, with 3.2 headroom to the lid underside |
| MPU overhang allowance | Approximately 16 beyond the -X board edge |
| Cradle board pocket | 91.2 × 61.2; 0.6 side clearance |
| Cradle locating rim top | Z=15.4, below the modeled female header bodies |
| USB opening | 26 wide × 16 high; +X short wall, centre Y=17, Z=26.5 |
| IMU opening | 26 wide × 14 high; -X short wall, centre Y=17, Z=25.4 |
| EN / BOOT lid openings | 16 × 10 each; centres (46,8) / (46,26) |
| Glove wire opening | 76 wide × 11 high along -Y long side; centre X=8, Z=16–27 |
| Strap slots | 26 × 6 on the short ends; centres (±67, 0), for a 20–25 wide strap |
| Lid screws | M3, centres (±54.4, ±36.4) |
| Cradle-to-base screws | M2.5, centres X=-28 / 44, Y=±35 |
| Board corner slots | 4.5 × 4; centres X=-34 / 50, Y=±27, nominal |

The +X end carries USB; the MPU and its access opening are at -X. The glove wires leave the -Y long side, matching
their direction relative to the ESP32 in the photos. The 76 mm base notch opens to the lid
split. The lid's apron closes its upper portion, leaving an 11 mm wire opening when shut.
Remove the lid to lay in the connected glove wiring without feeding the glove through a hole.

The main board rests on four corner pads. The large central opening leaves room for solder
joints and header tails. The cradle does not relocate the MPU or require separating the
divider circuit from the main board. Keep the existing IMU orientation fixed between takes.

## Assembly and fit checks

Starting hardware:

- 4 × M3 × 10 pan-head lid screws; 3.4 clearance / 2.6 blind plastic pilots.
- 4 × M2.5 × 8 pan-head screws for the cradle; 2.8 clearance / 2.0 plastic pilots.
- M2.5 bolts, insulating washers and nuts for accessible existing perfboard corner holes;
  8 mm is an initial bolt length to check against the actual board/washer/nut stack.
- Small cable ties for the harness, a 20–25 wide Velcro strap and optional underside EVA pad.

Check the real board corner-hole centres against the cradle slots before fastening. Use
accessible mounting holes and ensure the board is rigidly retained; some top corner holes
may be covered by the ESP32/socket assembly. Do not drill an occupied circuit to match this
prototype. The nominal slots permit about ±0.9 X / ±0.6 Y adjustment for a 2.5 mm fastener.
Check bare corner-pad areas for solder joints and use insulating washers/pads as needed.

Mount the perfboard to the removable cradle, place the cradle on its four base pedestals,
and fasten it. Route the wires through the long-side opening and use the two internal tie
tunnels to restrain the harness. Keep the bundle and tie heads within the 11 mm opening.
Close the lid while checking that the apron clears the wires. Fit the strap and comfort pad.

Before a final print, measure the total span including the MPU, the actual solder/header
stack, USB plug overmould and socket reach, button centres, and all used mounting holes.
The original foam pad is not dimensioned in this model; check any retained foam against the
under-board clearance. The supplied 90 × 60 × 30 dimension does not establish these offsets.

## Printing and verification

Each STL is exported separately near XY=0 and rests at Z=0. Print the base open side up,
the lid exterior down with its apron pointing upward, and the cradle flat underside down.
All fit inside a 146 × 86 mm footprint separately. A starting fit print is 0.2 layers,
0.4 nozzle, four walls and 4–5 top/bottom layers; inspect the slicer preview. The 26 mm USB
and IMU opening roofs may need local support. Small tie tunnels, lettering and the cradle slots may need
slicer or hole-tolerance adjustments. Validate fit before choosing the final material.

All three meshes are closed, single components with positive volume. Nominal Boolean
collision checks use Blender's Manifold solver and a 0.02 mm separation at coincident
seating faces. All modeled parts, solder pins, sockets, IMU and USB-plug envelope pass.
Microscopic Boolean slivers are cleaned before export. These checks establish geometric
consistency of this provisional layout, not physical fit or strap strength.

The independent STL check verifies dimensions, edge pairing, no degenerate triangles,
positive volume and on-bed placement. Repeat from this folder with:

```powershell
python verify_stl.py
```
