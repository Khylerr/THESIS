"""AISL-A wrist enclosure V3 as real CAD solids (FreeCAD 1.1, Part workbench, millimetres).

This is the MASTER model of enclosure V3. Run it headless, FreeCAD does not need to be open:
    "%LOCALAPPDATA%\\Programs\\FreeCAD 1.1\\bin\\freecadcmd.exe" build_enclosure_v3_freecad.py

Writes next to this file:
    AISL-A_Enclosure_V3.FCStd            open this in FreeCAD (Base, Lid, PCB_assembly, USB plug)
    step/01_base.step, step/02_lid.step  exact CAD geometry of the two printed parts
    step/AISL-A_V3_assembly.step         base + lid + the populated PCB from KiCad
    exports/01_base.stl, 02_lid.stl      print files (lid already flipped, outer face on the bed)
    drawings/AISL-A_V3_views.svg         top / front / side outlines with the main dimensions
    validation.json                      solid checks and the collision check against the PCB STEP

Axes: origin = centre of the carrier PCB, Z = 0 at the underside of the box, +X = USB end,
-Y = flex-connector edge. A PCB coordinate (x, y_kicad) from hardware/pcb/v1 is
(x - 1.0, 8.05 - y_kicad) here. Same numbers as ../build_enclosure_v3.py (the Blender
version, now kept only for rendered pictures).
"""
import json
import math
import sys
import time
from pathlib import Path

import FreeCAD as App
import Part
import MeshPart
from FreeCAD import Vector as V

try:
    ROOT = Path(__file__).resolve().parent
except NameError:  # freecadcmd on some versions does not define __file__
    ROOT = Path(next(a for a in sys.argv if a.lower().endswith('.py'))).resolve().parent
PCB_DIR = ROOT.parents[2] / 'pcb' / 'v1'
PCB_STEP = PCB_DIR / 'exports' / 'aisl_glove_carrier_assembled.step'
PCB_SHEET_CENTRE = (101.0, 88.05)     # board centre on the KiCad sheet (mm)
FONT_DIR, FONT_FILE = 'C:/Windows/Fonts/', 'arial.ttf'

P = dict(
    board_x=68.0, board_y=46.5, board_t=1.6, board_clearance=0.6,
    wall_short=2.4,          # +X / -X walls (USB end stays thin so the plug reaches)
    wall_long=5.6,           # +Y / -Y walls, thick enough to take the M3 lid screws
    floor=2.4, lid=2.4, corner=5.0, cavity_corner=3.0,
    standoff=3.5,            # under the PCB, room for solder joints and trimmed leads
    headroom=19.5,           # PCB top to lid underside; set by the USB plug body
    lip_clearance=0.30, lip_depth=2.0, lip_thickness=1.5,
    usb_cy=8.05, usb_cz_above_pcb=14.0, usb_width=16.0, usb_height=11.0,
    wire_notch_width=50.0, wire_notch_bottom_above_pcb=9.5, wire_apron=4.0,
    button_hole_d=9.0,
    strap_slot_width=26.0, strap_slot_depth=6.0, strap_loop_thickness=6.0,
    m3_pilot=2.6, m3_clearance=3.4, head_recess_d=6.4, head_recess_depth=0.8,
    edge_chamfer=0.6, engrave_depth=0.4)

CAV_X = P['board_x'] + 2 * P['board_clearance']                 # 69.2
CAV_Y = P['board_y'] + 2 * P['board_clearance']                 # 47.7
LEN = CAV_X + 2 * P['wall_short']                               # 74.0
WID = CAV_Y + 2 * P['wall_long']                                # 58.9
Z_PCB_BOTTOM = P['floor'] + P['standoff']                       # 5.9
Z_PCB_TOP = Z_PCB_BOTTOM + P['board_t']                         # 7.5
Z_SPLIT = Z_PCB_TOP + P['headroom']                             # 27.0
Z_TOP = Z_SPLIT + P['lid']                                      # 29.4
PCB_HOLES = [(-30.5, 19.55), (30.5, 19.55), (-30.5, -19.75), (30.5, -19.75)]
WALL_MID_Y = CAV_Y / 2 + P['wall_long'] / 2                     # 26.65
LID_SCREWS = [(x, y) for x in (-31.5, 31.5) for y in (-WALL_MID_Y, WALL_MID_Y)]
BOOT_XY, EN_XY = (22.2, 15.9), (22.2, 0.2)
LOOP_CX = LEN / 2 + 5.0
SLOT_CX = LEN / 2 + 6.0


def rr(sx, sy, z0, z1, r, cx=0.0, cy=0.0):
    """Box with its four vertical edges rounded (a rounded rectangle extruded in Z)."""
    box = Part.makeBox(sx, sy, z1 - z0, V(cx - sx / 2, cy - sy / 2, z0))
    r = min(r, sx / 2 - 1e-3, sy / 2 - 1e-3)
    if r > 0.01:
        vertical = [e for e in box.Edges if abs(e.Vertexes[0].X - e.Vertexes[-1].X) < 1e-9
                    and abs(e.Vertexes[0].Y - e.Vertexes[-1].Y) < 1e-9]
        box = box.makeFillet(r, vertical)
    return box


def cyl(d, z0, z1, x, y):
    return Part.makeCylinder(d / 2, z1 - z0, V(x, y, z0))


def chamfer_at_z(shape, z, size):
    edges = [e for e in shape.Edges if all(abs(v.Z - z) < 1e-6 for v in e.Vertexes)]
    return shape.makeChamfer(size, edges)


def engraving(text, cx, cy, height, z_top, depth):
    """Solid letters to cut `depth` into a face at z_top, centred on (cx, cy)."""
    chars = Part.makeWireString(text, FONT_DIR, FONT_FILE, height, 0)
    faces = [Part.makeFace(wires, 'Part::FaceMakerBullseye') for wires in chars if wires]
    comp = Part.makeCompound(faces)
    bb = comp.BoundBox
    comp.translate(V(cx - (bb.XMin + bb.XMax) / 2, cy - (bb.YMin + bb.YMax) / 2, z_top - depth))
    return comp.extrude(V(0, 0, depth + 1))


def clean(shape, name):
    shape = shape.removeSplitter()
    assert shape.isValid(), name + ' is not a valid solid'
    assert len(shape.Solids) == 1, '%s has %d solids' % (name, len(shape.Solids))
    return shape.Solids[0]


def build_base():
    s = rr(LEN, WID, 0, Z_SPLIT, P['corner'])
    s = chamfer_at_z(s, 0.0, P['edge_chamfer'])                      # easier on the wrist, hides elephant foot
    s = s.cut(rr(CAV_X, CAV_Y, P['floor'], Z_SPLIT + 4, P['cavity_corner']))
    for side in (-1, 1):                                             # strap loops, low on the short ends
        s = s.fuse(rr(14, 34, 0, P['strap_loop_thickness'], 3, cx=side * LOOP_CX))
        s = s.cut(rr(P['strap_slot_depth'], P['strap_slot_width'], -1, P['strap_loop_thickness'] + 1, 1.5,
                     cx=side * SLOT_CX))
    for hx, hy in PCB_HOLES:                                         # corner pads the PCB sits on
        sx, sy = math.copysign(1, hx), math.copysign(1, hy)
        x0, x1 = hx - sx * 3.5, sx * (CAV_X / 2 + .4)
        y0, y1 = hy - sy * 3.5, sy * (CAV_Y / 2 + .4)
        s = s.fuse(rr(abs(x1 - x0), abs(y1 - y0), P['floor'] - .2, Z_PCB_BOTTOM, 1.0,
                      cx=(x0 + x1) / 2, cy=(y0 + y1) / 2))
        s = s.cut(cyl(P['m3_pilot'], Z_PCB_BOTTOM - 5.2, Z_PCB_BOTTOM + 1, hx, hy))
    for x, y in LID_SCREWS:
        s = s.cut(cyl(P['m3_pilot'], Z_SPLIT - 12, Z_SPLIT + 1, x, y))
    usb_bottom = Z_PCB_TOP + P['usb_cz_above_pcb'] - P['usb_height'] / 2
    s = s.cut(rr(6, P['usb_width'], usb_bottom, Z_SPLIT + 4, 1.0, cx=LEN / 2 - 1.2, cy=P['usb_cy']))
    wire_bottom = Z_PCB_TOP + P['wire_notch_bottom_above_pcb']
    s = s.cut(rr(P['wire_notch_width'], P['wall_long'] + 2.4, wire_bottom, Z_SPLIT + 4, 1.0, cy=-WALL_MID_Y))
    return clean(s, 'base')


def build_lid():
    c = P['lip_clearance']
    s = rr(LEN, WID, Z_SPLIT, Z_TOP, P['corner'])
    s = chamfer_at_z(s, Z_TOP, P['edge_chamfer'])
    lip = rr(CAV_X - 2 * c, CAV_Y - 2 * c, Z_SPLIT - P['lip_depth'], Z_SPLIT + .3, P['cavity_corner'] - c)
    t = 2 * P['lip_thickness']
    lip = lip.cut(rr(CAV_X - 2 * c - t, CAV_Y - 2 * c - t, Z_SPLIT - 3, Z_SPLIT + 1, 1.2))
    lip = lip.cut(rr(8, P['usb_width'] + 1, Z_SPLIT - 3, Z_SPLIT + 1, .5, cx=CAV_X / 2, cy=P['usb_cy']))
    lip = lip.cut(rr(P['wire_notch_width'] + 1, 6, Z_SPLIT - 3, Z_SPLIT + 1, .5, cy=-CAV_Y / 2))
    s = s.fuse(lip)
    # Apron drops into the top of the wire notch and leaves a slot for the ten flex wires.
    s = s.fuse(rr(P['wire_notch_width'] - .6, P['wall_long'], Z_SPLIT - P['wire_apron'], Z_SPLIT + .2, .4,
                  cy=-WALL_MID_Y))
    for x, y in LID_SCREWS:
        s = s.cut(cyl(P['m3_clearance'], Z_SPLIT - 5, Z_TOP + 1, x, y))
        s = s.cut(cyl(P['head_recess_d'], Z_TOP - P['head_recess_depth'], Z_TOP + 1, x, y))
    for x, y in (BOOT_XY, EN_XY):
        s = s.cut(cyl(P['button_hole_d'], Z_SPLIT - 5, Z_TOP + 1, x, y))
    s = clean(s, 'lid')
    engraved = []
    for text, cx, cy, h in (('BOOT', BOOT_XY[0] - 11.5, BOOT_XY[1], 2.6), ('EN', EN_XY[0] - 9.0, EN_XY[1], 2.6),
                            ('USB', 30.0, P['usb_cy'], 2.4)):
        try:
            s = s.cut(engraving(text, cx, cy, h, Z_TOP, P['engrave_depth']))
            engraved.append(text)
        except Exception as e:  # lettering is cosmetic; never lose the part over it
            print('ENGRAVING skipped for %s: %s' % (text, e))
    assert s.isValid() and len(s.Solids) == 1, 'lid broke while engraving'
    return s.Solids[0], engraved


def load_pcb():
    shape = Part.Shape()
    shape.read(str(PCB_STEP))
    # KiCad STEP: sheet coordinates with Y negated and the board underside at z = 0.
    shape.translate(V(-PCB_SHEET_CENTRE[0], PCB_SHEET_CENTRE[1], Z_PCB_BOTTOM))
    return shape


def collisions(part, pcb):
    """Volume shared with each solid of the PCB model (mm3). Touching faces count as 0."""
    hits, total = [], 0.0
    pb = part.BoundBox
    for i, solid in enumerate(pcb.Solids):
        if not pb.intersect(solid.BoundBox):
            continue
        try:
            v = part.common(solid).Volume
        except Exception:
            v = float('nan')
        if not (v < 1e-4):
            b = solid.BoundBox
            hits.append(dict(solid=i, volume_mm3=round(v, 4),
                             bbox=[round(x, 2) for x in (b.XMin, b.XMax, b.YMin, b.YMax, b.ZMin, b.ZMax)]))
            total += v if v == v else 0.0
    return dict(overlap_mm3=round(total, 4), solids_overlapping=hits)


def solid_report(shape):
    b = shape.BoundBox
    return dict(valid=shape.isValid(), closed=shape.isClosed(), solids=len(shape.Solids),
                volume_mm3=round(shape.Volume, 3),
                dimensions_mm=[round(b.XLength, 3), round(b.YLength, 3), round(b.ZLength, 3)],
                faces=len(shape.Faces))


def export_stl(shape, path):
    mesh = MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.03, AngularDeflection=0.2, Relative=False)
    mesh.write(str(path))
    return dict(triangles=mesh.CountFacets, solid=mesh.isSolid(), non_manifold=mesh.hasNonManifolds(),
                self_intersecting=mesh.hasSelfIntersections(), volume_mm3=round(mesh.Volume, 3))


def outline_svg(shape, matrix):
    """Visible + hidden outline as 2D line segments.

    `matrix` first turns the shape so the wanted view looks straight down -Z with the wanted
    paper axes on X/Y; projecting along Z then keeps those axes (projectEx picks its own
    axes for any other direction, which rotated the side views).
    """
    import TechDraw
    groups = TechDraw.projectEx(shape.transformGeometry(matrix), V(0, 0, 1))   # V, V1, VN, VO, VI, H, H1, HN, HO, HI

    def to2d(edges_shape):
        segs = []
        if edges_shape is None or edges_shape.isNull():
            return segs
        for e in edges_shape.Edges:
            pts = e.discretize(Deflection=0.05)
            segs.append([(p.x, p.y) for p in pts])
        return segs
    visible = to2d(groups[0]) + to2d(groups[1]) + to2d(groups[3])
    hidden = to2d(groups[5]) + to2d(groups[8])
    return visible, hidden


def drawing(base, lid, path):
    """Three views of the closed box with the main dimensions. Scale 1.5:1 on an A4 landscape sheet."""
    box = Part.makeCompound([base, lid])
    S = 1.5                                            # drawing scale
    M = App.Matrix
    views = [  # name, matrix (model -> paper x, paper y, toward viewer), sheet position of the view centre
        ('TOP', M(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1), (95, 70)),
        ('FRONT (flex wire side, -Y)', M(1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1), (95, 163)),
        ('RIGHT (USB end, +X)', M(0, 1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1), (228, 163)),
    ]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">',
           '<rect x="0" y="0" width="297" height="210" fill="white"/>',
           '<rect x="8" y="8" width="281" height="194" fill="none" stroke="black" stroke-width="0.35"/>',
           '<g font-family="Arial, Helvetica, sans-serif" fill="black">']

    def dim_h(x0, x1, y, label):
        out.append('<g stroke="black" stroke-width="0.18" fill="none"><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
                   '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/></g>'
                   % (x0, y, x1, y, x0, y - 2, x0, y + 2, x1, y - 2, x1, y + 2))
        out.append('<text x="%.2f" y="%.2f" font-size="3.4" text-anchor="middle">%s</text>' % ((x0 + x1) / 2, y - 1.2, label))

    def dim_v(x, y0, y1, label):
        out.append('<g stroke="black" stroke-width="0.18" fill="none"><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>'
                   '<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/><line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/></g>'
                   % (x, y0, x, y1, x - 2, y0, x + 2, y0, x - 2, y1, x + 2, y1))
        out.append('<text x="%.2f" y="%.2f" font-size="3.4" text-anchor="middle" transform="rotate(-90 %.2f %.2f)">%s</text>'
                   % (x - 1.4, (y0 + y1) / 2, x - 1.4, (y0 + y1) / 2, label))

    for name, matrix, (ox, oy) in views:
        visible, hidden = outline_svg(box, matrix)
        allpts = [p for seg in visible + hidden for p in seg]
        xs, ys = [p[0] for p in allpts], [p[1] for p in allpts]
        cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
        w, h = (max(xs) - min(xs)) * S, (max(ys) - min(ys)) * S

        def path_d(seg):
            return 'M' + ' L'.join('%.3f,%.3f' % (ox + (x - cx) * S, oy - (y - cy) * S) for x, y in seg)
        out.append('<g fill="none" stroke="#888" stroke-width="0.13" stroke-dasharray="0.9,0.6">'
                   + ''.join('<path d="%s"/>' % path_d(s) for s in hidden) + '</g>')
        out.append('<g fill="none" stroke="black" stroke-width="0.3">'
                   + ''.join('<path d="%s"/>' % path_d(s) for s in visible) + '</g>')
        out.append('<text x="%.2f" y="%.2f" font-size="3.6" text-anchor="middle" font-weight="bold">%s</text>'
                   % (ox, oy + h / 2 + (12 if name == 'TOP' else 9), name))
        dim_h(ox - w / 2, ox + w / 2, oy - h / 2 - 6, '%.1f' % (w / S))
        dim_v(ox - w / 2 - 6, oy - h / 2, oy + h / 2, '%.1f' % (h / S))
        if name == 'TOP':
            dim_h(ox - LEN / 2 * S, ox + LEN / 2 * S, oy + h / 2 + 6.5, 'body %.1f' % LEN)
    notes = ['AISL-A GLOVE ENCLOSURE V3  (for carrier PCB v1)',
             'Scale 1.5:1 on A4 landscape. Dimensions in mm. Dashed = hidden edges.',
             'Walls: %.1f short ends, %.1f long sides. Floor %.1f, lid %.1f.' % (P['wall_short'], P['wall_long'], P['floor'], P['lid']),
             'Cavity %.1f x %.1f. PCB top at Z = %.1f, lid underside at Z = %.1f.' % (CAV_X, CAV_Y, Z_PCB_TOP, Z_SPLIT),
             'USB notch %.0f wide; flex wire slot %.0f x %.0f; BOOT / EN holes %.0f dia.'
             % (P['usb_width'], P['wire_notch_width'], Z_SPLIT - P['wire_apron'] - Z_PCB_TOP - P['wire_notch_bottom_above_pcb'], P['button_hole_d']),
             'Screws: 4 x M3 x 6 (PCB), 4 x M3 x 10 (lid), %.1f mm pilots. Strap slots %.0f x %.0f.'
             % (P['m3_pilot'], P['strap_slot_width'], P['strap_slot_depth']),
             'Fit prototype generated %s. Not printed, not measured.' % time.strftime('%Y-%m-%d')]
    for i, line in enumerate(notes):
        out.append('<text x="181" y="%.1f" font-size="%s"%s>%s</text>'
                   % (24 + i * 5.4, '3.9' if i == 0 else '2.9', ' font-weight="bold"' if i == 0 else '', line))
    out.append('</g></svg>')
    path.write_text('\n'.join(out), encoding='utf-8')


def main():
    t0 = time.time()
    base = build_base()
    lid, engraved = build_lid()
    print('BUILT base %.1f mm3, lid %.1f mm3, engraved %s (%.1f s)' % (base.Volume, lid.Volume, engraved, time.time() - t0))
    pcb = load_pcb()
    pb = pcb.BoundBox
    zt = Z_PCB_TOP + P['usb_cz_above_pcb']
    plug = rr(32, 12, zt - 4.25, zt + 4.25, 2, cx=27.5 + 16, cy=P['usb_cy'])
    result = dict(
        units='millimetres', freecad='.'.join(App.Version()[:3]),
        status='V3 fit prototype from design files; not printed, no measured parts',
        parameters_mm=P,
        derived_mm=dict(body=[LEN, round(WID, 3), Z_TOP], overall_with_strap_loops=[2 * (LOOP_CX + 7), round(WID, 3), Z_TOP],
                        cavity=[CAV_X, CAV_Y], pcb_bottom_z=Z_PCB_BOTTOM, pcb_top_z=Z_PCB_TOP, lid_split_z=Z_SPLIT,
                        pcb_holes=PCB_HOLES, lid_screws=[[x, round(y, 3)] for x, y in LID_SCREWS],
                        boot_hole=BOOT_XY, en_hole=EN_XY),
        parts=dict(base=solid_report(base), lid=solid_report(lid)),
        base_vs_lid_overlap_mm3=round(base.common(lid).Volume, 5),
        pcb_model=dict(source=str(PCB_STEP.relative_to(ROOT.parents[2])), solids=len(pcb.Solids),
                       bbox_mm=[round(v, 2) for v in (pb.XMin, pb.XMax, pb.YMin, pb.YMax, pb.ZMin, pb.ZMax)]),
        clearances_mm=dict(pcb_edge_to_wall=P['board_clearance'],
                           tallest_part_to_lid_underside=round(Z_SPLIT - pb.ZMax, 2),
                           lowest_pin_to_floor=round(pb.ZMin - P['floor'], 2)),
    )
    t1 = time.time()
    result['pcb_collisions'] = dict(base=collisions(base, pcb), lid=collisions(lid, pcb))
    result['usb_plug_12x8.5_overlap_mm3'] = dict(base=round(base.common(plug).Volume, 4), lid=round(lid.common(plug).Volume, 4))
    print('CHECK base/lid overlap %s mm3; PCB vs base %s mm3, vs lid %s mm3; USB plug %s (%.1f s)'
          % (result['base_vs_lid_overlap_mm3'], result['pcb_collisions']['base']['overlap_mm3'],
             result['pcb_collisions']['lid']['overlap_mm3'], result['usb_plug_12x8.5_overlap_mm3'], time.time() - t1))
    print('CLEARANCE', result['clearances_mm'])

    for sub in ('step', 'exports', 'drawings'):
        (ROOT / sub).mkdir(exist_ok=True)
    base.exportStep(str(ROOT / 'step' / '01_base.step'))
    lid.exportStep(str(ROOT / 'step' / '02_lid.step'))
    Part.makeCompound([base, lid, pcb]).exportStep(str(ROOT / 'step' / 'AISL-A_V3_assembly.step'))
    lid_print = lid.copy()
    lid_print.rotate(V(0, 0, 0), V(1, 0, 0), 180)     # outer face down on the bed
    lid_print.translate(V(0, 0, Z_TOP))
    result['stl'] = {'01_base.stl': export_stl(base, ROOT / 'exports' / '01_base.stl'),
                     '02_lid.stl': export_stl(lid_print, ROOT / 'exports' / '02_lid.stl')}
    print('STL', result['stl'])
    try:
        drawing(base, lid, ROOT / 'drawings' / 'AISL-A_V3_views.svg')
        result['drawing'] = 'drawings/AISL-A_V3_views.svg'
    except Exception as e:
        result['drawing'] = 'failed: %s' % e
        print('DRAWING failed:', e)

    doc = App.newDocument('AISL_A_Enclosure_V3')
    for name, shape, label in (('Base', base, '01 Base (print)'), ('Lid', lid, '02 Lid (print)'),
                               ('PCB_assembly', pcb, 'Carrier PCB v1 from KiCad (reference)'),
                               ('USB_plug_envelope', plug, 'USB plug 12 x 8.5 envelope (reference)')):
        obj = doc.addObject('Part::Feature', name)
        obj.Shape = shape
        obj.Label = label
    doc.Comment = 'Generated by build_enclosure_v3_freecad.py. Edit the script, not this file.'
    doc.recompute()
    doc.saveAs(str(ROOT / 'AISL-A_Enclosure_V3.FCStd'))
    (ROOT / 'validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('DONE in %.1f s' % (time.time() - t0))


main()
