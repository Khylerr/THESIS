# Enclosure V2 — progress-report figures

Prepared 2026-11-07 from the saved V2 Blender model. These are CAD design renders, with
schematic electronic component envelopes. They do not document a fabricated or fit-tested case.

## Recommended figures

Use the four views in `report_figure_4_views.png` for the main progress-report figure:

| Panel | View | What it establishes |
|---|---|---|
| A | Assembled isometric | Overall form, screw lid, short-end strap loops and wiring access |
| B | Exploded assembly | Removable lid, populated perfboard/cradle and enclosure base |
| C | Internal circuit layout | Single perfboard, ESP32 placement, IMU overhang and open mounting cradle |
| D | Dimensioned top view | 122 × 86 mm body footprint and 146 mm overall length; 42 mm body height noted |

If dimensions are discussed in detail, insert `06_dimensions.png` separately. It includes
top and front orthographic views and shows the 42 mm height explicitly.

`04_usb_end.png` and `05_imu_end.png` are supplementary views for a paragraph about port
access. Use them as a paired figure if that design change is important to the report.
The overall six-view contact sheet is for selecting images, not the preferred report figure.

## Combined figure caption — ready to paste

**Figure X. Proposed wrist-enclosure CAD design:** (a) assembled enclosure with screw-fastened
lid and strap loops on the short ends; (b) exploded arrangement of the lid, populated
perfboard and removable cradle, and base; (c) schematic placement of the ESP32, divider
circuit and overhanging MPU6050 on one perfboard; and (d) nominal dimensions. The body is
122 × 86 × 42 mm, with an overall length of 146 mm including the strap loops. Electronic
shapes are schematic; physical fit remains to be verified. Source: project CAD model.

## Individual captions

1. **Assembled enclosure** (`01_assembled.png`). Proposed enclosure V2 showing the removable
   screw lid, short-end strap mounting loops, button access and long-side glove-wire opening.
2. **Exploded assembly** (`02_exploded.png`). Separated view of the lid, populated perfboard
   and its removable support cradle, and base. Vertical separation is for illustration only.
3. **Internal layout** (`03_internal_layout.png`). Schematic placement of the complete
   perfboard assembly, including the socketed ESP32, divider components and overhanging MPU6050.
4. **USB access** (`04_usb_end.png`). USB-end view showing the 26 × 16 mm opening and the
   strap loop below it. Component positions are provisional CAD offsets.
5. **IMU access** (`05_imu_end.png`). Opposite-end view showing the 26 × 14 mm opening aligned
   to the modeled MPU6050 position and the strap loop below it.
6. **Nominal dimensions** (`06_dimensions.png`). Orthographic top and front views showing a
   body footprint of 122 × 86 mm, a height of 42 mm and an overall length of 146 mm including loops.

## Optional progress-report paragraph

The enclosure CAD design was revised to accommodate the assembled perfboard and its
overhanging MPU6050. The design includes a removable screw-fastened lid, an open support
cradle providing clearance beneath the board, strap loops on the two short ends, and
separate USB and IMU access openings. A wide opening along the long side accommodates the
glove wiring, and an integral lid apron allows the connected wires to be laid into the
base during assembly. The current body dimensions are 122 × 86 × 42 mm, increasing to
146 × 86 × 42 mm when the strap loops are included. Component positions are represented
schematically; mounting-hole alignment, physical fit and strap performance remain to be
verified through measurement and a trial print.

## File use and reproduction

- Main renders: `01_assembled.png` to `05_imu_end.png`, 2400 × 1600 pixels, white background,
  PNG, 300 dpi metadata. The full dimension sheet is 2400 × 2580 pixels.
- `report_figure_4_views.png`: 4000 × 3330 pixels, white background, 300 dpi metadata.
- `overview_six_views.png`: contact sheet for reviewing all views.
- `06_top_dimensions.png`: standalone top view with dimension annotations.
- `Enclosure_Report_Views.blend`: separate Blender project containing the source design and
  report camera scenes. The original V2 file was not overwritten.
- `render_report_views.py`: native Blender renders; `compose_report_figures.py`: white page
  backgrounds, dimension annotations and report panel composition.
- `render_manifest.json`: camera settings, dimensions, source geometry fingerprints and
  projected coordinates used for dimension lines. `render_qa.json`: image frame checks.
- The electronic geometry is schematic and no physical strap, gloves, cables, screws or
  printer tolerances were added to the renders. The source design geometry was verified unchanged.

For Word, insert the PNGs with **Insert → Pictures**. Use the combined figure at the report's
full text width; use individual views if labels need more space. Keep the caption below
the figure and retain the CAD/provisional-fit wording. Replace Figure X with the report's
actual figure number.
