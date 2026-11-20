"""AISL-A wrist enclosure V3, built round carrier PCB v1 (hardware/pcb/v1). Blender 5.x, mm.

Run headless (Blender does not need to be open, the Blender MCP is not needed):
    "C:\\Program Files\\Blender Foundation\\Blender 5.2\\blender.exe" --background --factory-startup --python build_enclosure_v3.py

SUPERSEDED AS THE MASTER on 2026-11-18: the CAD model and the print STLs come from
freecad/build_enclosure_v3_freecad.py. This Blender version is kept for the rendered
pictures only; keep its numbers (P, PCB_HOLES, ...) equal to the FreeCAD script.

Writes next to this file: AISL-A_Enclosure_V3.blend, validation.json and five preview PNGs.
Geometry helpers come from ../build_enclosure.py (V1).

Axes (same convention as V2): origin = centre of the carrier PCB, Z = 0 at the underside of
the box. +X = USB end of the DevKit, -Y = flex-connector edge (wires leave here), strap loops
on the two short ends (+X / -X). PCB coordinates (x, y_kicad) from hardware/pcb/v1 map to
(x - 1.0, 8.05 - y_kicad).

Nothing here has been printed. Dimensions follow the PCB design files, not a measured board.
"""
import bpy
import bmesh
import importlib.util
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('aisla_geometry', ROOT.parent / 'build_enclosure.py')
geo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(geo)

PCB_GLB = ROOT.parent.parent / 'pcb' / 'v1' / 'exports' / 'aisl_glove_carrier_assembled.glb'
SCENE = 'AISL-A | Enclosure V3 (carrier PCB v1)'
EXPLODED = 'AISL-A | V3 exploded'
LAYOUT = 'AISL-A | V3 print layout (mm)'
REFS = 'V3 REFERENCE ONLY | nominal envelopes, not print parts'
MODEL = 'V3 PCB MODEL | KiCad export, render only'
NAMES = ['V3_01_BASE', 'V3_02_LID']

P = dict(
    board_x=68.0, board_y=46.5, board_t=1.6, board_corner=2.5, board_clearance=0.6,
    wall_short=2.4,          # +X / -X walls (USB end stays thin so the plug reaches)
    wall_long=5.6,           # +Y / -Y walls, thick enough to take the M3 lid screws
    floor=2.4, lid=2.4, corner=5.0,
    standoff=3.5,            # under the PCB, room for solder joints and trimmed leads
    headroom=19.5,           # PCB top to lid underside; set by the USB plug overmould
    lip_clearance=0.30, lip_depth=2.0,
    usb_cy=8.05, usb_cz_above_pcb=14.0, usb_width=16.0, usb_height=11.0,
    wire_notch_width=50.0, wire_notch_bottom_above_pcb=9.5, wire_apron=4.0,
    button_hole_d=9.0,
    strap_slot_width=26.0, strap_slot_depth=6.0, strap_loop_thickness=6.0,
    m3_pilot=2.6, m3_clearance=3.4, mesh_weld_tolerance=.003)

CAV_X = P['board_x'] + 2 * P['board_clearance']                 # 69.2
CAV_Y = P['board_y'] + 2 * P['board_clearance']                 # 47.7
LEN = CAV_X + 2 * P['wall_short']                               # 74.0
WID = CAV_Y + 2 * P['wall_long']                                # 58.9
Z_PCB_BOTTOM = P['floor'] + P['standoff']                       # 5.9
Z_PCB_TOP = Z_PCB_BOTTOM + P['board_t']                         # 7.5
Z_SPLIT = Z_PCB_TOP + P['headroom']                             # 27.0  wall top / lid underside
Z_TOP = Z_SPLIT + P['lid']                                      # 29.4
# Carrier PCB mounting holes (M3), from hardware/pcb/v1/layout_summary.json
PCB_HOLES = [(-30.5, 19.55), (30.5, 19.55), (-30.5, -19.75), (30.5, -19.75)]
LID_SCREWS = [(x, y) for x in (-31.5, 31.5) for y in (-(CAV_Y / 2 + P['wall_long'] / 2), CAV_Y / 2 + P['wall_long'] / 2)]
BOOT_XY, EN_XY = (22.2, 15.9), (22.2, 0.2)                      # DevKit buttons, read off the KiCad render
LOOP_CX = LEN / 2 + 5.0
SLOT_CX = LEN / 2 + 6.0


def remove_skinny_faces(bm):
    for _ in range(100):
        candidate = None
        for f in bm.faces:
            if len(f.verts) != 3:
                continue
            a, b, c = [tuple(float(v) for v in p.co) for p in f.verts]
            u = [b[j] - a[j] for j in range(3)]
            v = [c[j] - a[j] for j in range(3)]
            cross = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
            edge = min(f.edges, key=lambda e: e.calc_length())
            if sum(x * x for x in cross) < 1e-14 and edge.calc_length() < .02:
                candidate = edge
                break
        if candidate is None:
            return
        bmesh.ops.collapse(bm, edges=[candidate])
    raise RuntimeError('Excessive microscopic triangles')


def finish(obj):
    """Same clean-up as V2: weld Boolean slivers, triangulate, insist on a closed mesh."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    tol = P['mesh_weld_tolerance']
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=tol)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=tol)
    wires = [e for e in bm.edges if not e.link_faces]
    if wires:
        bmesh.ops.delete(bm, geom=wires, context='EDGES')
    loose = [v for v in bm.verts if not v.link_edges]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bmesh.ops.triangulate(bm, faces=list(bm.faces))
    fins = [f for f in bm.faces if len(f.verts) == 3 and f.calc_area() < .00001
            and all(e.is_boundary for e in f.edges)]
    if fins:
        bmesh.ops.delete(bm, geom=fins, context='FACES')
    boundary = [e for e in bm.edges if e.is_boundary]
    if boundary and all(e.calc_length() < .02 for e in boundary):
        bmesh.ops.holes_fill(bm, edges=boundary, sides=3)
    remove_skinny_faces(bm)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    assert all(e.is_manifold for e in bm.edges), obj.name + ' is not manifold'
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    for face in obj.data.polygons:
        face.use_smooth = abs(face.normal.z) < .9999
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    for edge in bm.edges:
        if edge.is_manifold:
            edge.smooth = edge.calc_face_angle() < .72
    bm.to_mesh(obj.data)
    bm.free()
    mod = obj.modifiers.new('Flat surface normals', 'WEIGHTED_NORMAL')
    mod.keep_sharp = True
    obj['AISLA_V3'] = True
    obj['AISLA_print_part'] = True


def engrave(obj, body, xy, size):
    tool = geo.text('V3 engraving cutter', body, (*xy, Z_TOP - .35), size, extrude=.5)
    geo.activate(tool)
    bpy.ops.object.convert(target='MESH')
    geo.boolean(obj, bpy.context.object)


def new_scene(name):
    scene = bpy.data.scenes.new(name)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = .001
    scene.unit_settings.length_unit = 'MILLIMETERS'
    return scene


def build():
    if bpy.data.scenes.get(SCENE):
        raise RuntimeError('V3 scene already exists; start from an empty file.')
    scene = new_scene(SCENE)
    bpy.context.window.scene = scene
    scene['parameters_mm'] = json.dumps(P)
    scene['design_status'] = 'V3 fit prototype for carrier PCB v1; nothing printed or measured yet'
    ink = geo.material('AISLA V3 / graphite', (.045, .071, .085), .5)
    frost = geo.material('AISLA V3 / ceramic', (.77, .80, .78), .45)
    pcb = geo.material('AISLA V3 / PCB', (.02, .16, .09), .6)
    black = geo.material('AISLA V3 / black parts', (.025, .03, .035), .6)
    metal = geo.material('AISLA V3 / metal', (.48, .51, .50), .3, .7)
    white = geo.material('AISLA V3 / JST', (.78, .77, .70), .6)
    blue = geo.material('AISLA V3 / MPU PCB', (.015, .12, .45), .55)

    # ---- base -------------------------------------------------------------------------
    base = geo.rr(NAMES[0], LEN, WID, 0, Z_SPLIT, P['corner'])
    geo.boolean(base, geo.rr('V3 cavity', CAV_X, CAV_Y, P['floor'], Z_SPLIT + 4, 3.0))
    for side in (-1, 1):   # strap loops, low on the short ends, under the USB notch
        geo.boolean(base, geo.rr('V3 strap loop', 14, 34, 0, P['strap_loop_thickness'], 3, cx=side * LOOP_CX), 'UNION')
        geo.boolean(base, geo.rr('V3 strap slot 26 x 6', P['strap_slot_depth'], P['strap_slot_width'],
                                 -1, P['strap_loop_thickness'] + 1, 1.5, cx=side * SLOT_CX))
    for hx, hy in PCB_HOLES:   # corner pads the PCB sits on, merged into the walls
        sx, sy = math.copysign(1, hx), math.copysign(1, hy)
        x0, x1 = hx - sx * 3.5, sx * (CAV_X / 2 + .4)
        y0, y1 = hy - sy * 3.5, sy * (CAV_Y / 2 + .4)
        geo.boolean(base, geo.rr('V3 PCB corner pad', abs(x1 - x0), abs(y1 - y0), P['floor'] - .2, Z_PCB_BOTTOM,
                                 1.0, cx=(x0 + x1) / 2, cy=(y0 + y1) / 2), 'UNION')
        geo.boolean(base, geo.cylinder('V3 PCB M3 pilot', P['m3_pilot'] / 2, 6, (hx, hy, Z_PCB_BOTTOM - 2.2)))
    for x, y in LID_SCREWS:
        geo.boolean(base, geo.cylinder('V3 lid M3 pilot', P['m3_pilot'] / 2, 13, (x, y, Z_SPLIT - 5.5)))
    usb_bottom = Z_PCB_TOP + P['usb_cz_above_pcb'] - P['usb_height'] / 2
    geo.boolean(base, geo.rr('V3 USB notch', 6, P['usb_width'], usb_bottom, Z_SPLIT + 4, 1.0,
                             cx=LEN / 2 - 1.2, cy=P['usb_cy']))
    wire_bottom = Z_PCB_TOP + P['wire_notch_bottom_above_pcb']
    geo.boolean(base, geo.rr('V3 flex wire notch', P['wire_notch_width'], P['wall_long'] + 2.4, wire_bottom,
                             Z_SPLIT + 4, 1.0, cy=-(CAV_Y / 2 + P['wall_long'] / 2)))
    geo.bevel(base, .30, 3)
    geo.assign(base, ink)

    # ---- lid --------------------------------------------------------------------------
    lid = geo.rr(NAMES[1], LEN, WID, Z_SPLIT, Z_TOP, P['corner'])
    c = P['lip_clearance']
    lip = geo.rr('V3 locating lip', CAV_X - 2 * c, CAV_Y - 2 * c, Z_SPLIT - P['lip_depth'], Z_SPLIT + .3, 2.7)
    geo.boolean(lip, geo.rr('V3 lip hollow', CAV_X - 2 * c - 3, CAV_Y - 2 * c - 3, Z_SPLIT - 3, Z_SPLIT + 1, 1.2))
    geo.boolean(lip, geo.rr('V3 lip USB plug clearance', 8, P['usb_width'] + 1, Z_SPLIT - 3, Z_SPLIT + 1, .5,
                            cx=CAV_X / 2, cy=P['usb_cy']))
    geo.boolean(lip, geo.rr('V3 lip wire clearance', P['wire_notch_width'] + 1, 6, Z_SPLIT - 3, Z_SPLIT + 1, .5,
                            cy=-CAV_Y / 2))
    geo.boolean(lid, lip, 'UNION')
    # Apron drops into the top of the wire notch, leaving a slot for the ten flex wires.
    geo.boolean(lid, geo.rr('V3 wire notch apron', P['wire_notch_width'] - .6, P['wall_long'],
                            Z_SPLIT - P['wire_apron'], Z_SPLIT + .2, .4,
                            cy=-(CAV_Y / 2 + P['wall_long'] / 2)), 'UNION')
    for x, y in LID_SCREWS:
        geo.boolean(lid, geo.cylinder('V3 M3 clearance', P['m3_clearance'] / 2, 8, (x, y, Z_SPLIT + 1)))
        geo.boolean(lid, geo.cylinder('V3 pan-head recess', 3.2, 2, (x, y, Z_TOP + .2)))
    for xy in (BOOT_XY, EN_XY):
        geo.boolean(lid, geo.cylinder('V3 button access', P['button_hole_d'] / 2, 10, (*xy, Z_SPLIT)))
    geo.bevel(lid, .25, 3)
    engrave(lid, 'BOOT', (BOOT_XY[0] - 11.5, BOOT_XY[1]), 2.6)
    engrave(lid, 'EN', (EN_XY[0] - 9.0, EN_XY[1]), 2.6)
    engrave(lid, 'USB', (30.0, P['usb_cy']), 2.4)
    geo.assign(lid, frost)
    for obj in (base, lid):
        finish(obj)

    # ---- nominal envelopes of the electronics, for clearance checks only ------------------
    refs = bpy.data.collections.new(REFS)
    scene.collection.children.link(refs)

    def ref(obj, mat):
        for col in list(obj.users_collection):
            col.objects.unlink(obj)
        refs.objects.link(obj)
        geo.assign(obj, mat)
        obj['AISLA_V3'] = True
        obj['reference_only'] = True
        return obj

    zt = Z_PCB_TOP
    ref(geo.rr('V3 REF carrier PCB 68 x 46.5', P['board_x'], P['board_y'], Z_PCB_BOTTOM, zt, P['board_corner']), pcb)
    for cy in (20.75, -4.65):
        ref(geo.rr('V3 REF DevKit socket row', 48.3, 2.54, zt, zt + 8.5, .2, cx=2.1, cy=cy), black)
        ref(geo.rr('V3 REF socket solder tails', 48.3, 1.2, Z_PCB_BOTTOM - 2.0, Z_PCB_BOTTOM, .2, cx=2.1, cy=cy), metal)
        ref(geo.rr('V3 REF DevKit pin tails', 46.2, 1.0, zt + 12.64, zt + 15.0, .2, cx=2.1, cy=cy), metal)
    ref(geo.rr('V3 REF DevKit PCB', 54.9, 28.7, zt + 11.04, zt + 12.64, .5, cx=-.95, cy=7.9), black)
    ref(geo.rr('V3 REF ESP32 shield', 17.6, 15.8, zt + 12.64, zt + 15.9, .5, cx=-12.4, cy=8.05), metal)
    ref(geo.rr('V3 REF USB receptacle', 7.4, 8.0, zt + 12.64, zt + 15.4, .4, cx=23.2, cy=P['usb_cy']), metal)
    for xy in (BOOT_XY, EN_XY):
        ref(geo.rr('V3 REF DevKit button', 4.0, 3.2, zt + 12.64, zt + 15.1, .4, cx=xy[0], cy=xy[1]), black)
    plug = ref(geo.rr('V3 REF USB plug overmould 12 x 8.5', 32, 12, zt + P['usb_cz_above_pcb'] - 4.25,
                      zt + P['usb_cz_above_pcb'] + 4.25, 2, cx=27.5 + 16, cy=P['usb_cy']), black)
    ref(geo.rr('V3 REF MPU6050 module', 20.8, 16.2, zt + 2.54, zt + 5.6, .4, cx=-6.79, cy=8.05), blue)
    ref(geo.rr('V3 REF MPU header pins', 20.3, 2.54, zt, zt + 8.7, .2, cx=-6.79, cy=1.72), black)
    for i, xk in enumerate((-19, -9, 1, 11, 21), start=1):
        x = xk - 1.0
        ref(geo.rr('V3 REF JST XH socket J%d' % i, 7.4, 5.75, zt, zt + 7.0, .3, cx=x, cy=-19.575), white)
        ref(geo.rr('V3 REF JST plug + wire bend J%d' % i, 6.0, 5.75, zt + 7.0, zt + 14.0, .3, cx=x, cy=-19.575), white)
        ref(geo.rr('V3 REF resistor R%d' % i, 9.2, 2.5, zt, zt + 3.0, .3, cx=x, cy=-10.25), black)
        ref(geo.rr('V3 REF capacitor C%d' % i, 6.6, 2.5, zt, zt + 6.0, .3, cx=x, cy=-13.3), black)
    ref(geo.rr('V3 REF JST solder tails', 47.4, 2.0, Z_PCB_BOTTOM - 2.0, Z_PCB_BOTTOM, .2, cx=0, cy=-19.05), metal)
    ref(geo.rr('V3 REF 5V header J6', 2.54, 5.08, zt, zt + 8.5, .2, cx=29.5, cy=-8.22), black)
    for k, (hx, hy) in enumerate(PCB_HOLES, start=1):
        ref(geo.cylinder('V3 REF M3 pan head H%d' % k, 2.8, 2.5, (hx, hy, zt + 1.25), vertices=32), metal)
    refs.hide_render = True
    refs.hide_viewport = True
    plug.hide_render = True

    # ---- the real populated board from KiCad, for pictures only ---------------------------
    model = bpy.data.collections.new(MODEL)
    scene.collection.children.link(model)
    if PCB_GLB.exists():
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(PCB_GLB))
        new = [o for o in bpy.data.objects if o not in before]
        root = bpy.data.objects.new('V3 PCB MODEL', None)
        model.objects.link(root)
        for o in new:
            for col in list(o.users_collection):
                col.objects.unlink(o)
            model.objects.link(o)
            if o.parent is None:
                o.parent = root
            o['reference_only'] = True
        bpy.context.view_layer.update()
        raw = max(abs((o.matrix_world @ Vector(c))[0]) for o in new if o.type == 'MESH' for c in o.bound_box)
        unit = 1000 if raw < 1 else 1          # KiCad 9.0.7 writes this GLB in mm, not metres
        root.scale = (unit, unit, unit)
        root.location = (0, 0, Z_PCB_BOTTOM)   # KiCad exports the board underside at z = 0
        bpy.context.view_layer.update()
        lo = [min((o.matrix_world @ Vector(c))[i] for o in new if o.type == 'MESH' for c in o.bound_box) for i in range(3)]
        hi = [max((o.matrix_world @ Vector(c))[i] for o in new if o.type == 'MESH' for c in o.bound_box) for i in range(3)]
        scene['pcb_model_bbox_mm'] = json.dumps([[round(v, 2) for v in lo], [round(v, 2) for v in hi]])
        print('PCB model bbox mm', [round(v, 2) for v in lo], [round(v, 2) for v in hi])
    else:
        print('PCB model not found, skipped:', PCB_GLB)
    geo.activate(base)
    print('Built V3: %.1f x %.1f x %.1f mm body, %.1f mm long over the strap loops.' % (LEN, WID, Z_TOP, 2 * (LOOP_CX + 7)))


def lighting(scene):
    scene.render.engine = bpy.data.scenes[SCENE].render.engine
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    formats = [i.identifier for i in scene.render.image_settings.bl_rna.properties['file_format'].enum_items]
    scene.render.image_settings.file_format = next(x for x in formats if x == 'PNG')
    scene.world = bpy.data.worlds.new(scene.name + ' world')
    scene.world.use_nodes = True
    bg = next(n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value = (.16, .20, .23, 1)
    bg.inputs['Strength'].default_value = .5
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = -.65
    for name, at, power, size in [('Key', (35, -70, 150), 800000, 100), ('Fill', (-90, 0, 100), 450000, 80),
                                  ('Rim', (55, 90, 125), 900000, 90)]:
        data = bpy.data.lights.new('V3 ' + name, 'AREA')
        data.energy = power
        data.size = size
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        obj.location = at
        obj.rotation_euler = (Vector((0, 0, 15)) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def copy_into(scene, src, prefix, dz=0.0):
    dup = src.copy()
    if src.data is not None:
        dup.data = src.data.copy()
    dup.name = prefix + src.name
    scene.collection.objects.link(dup)
    if src.parent is None:
        dup.location.z += dz
    return dup


def copy_model(scene, prefix, dz):
    """Duplicate the imported KiCad board (a parented hierarchy) into another scene."""
    made = {}
    for src in bpy.data.collections[MODEL].objects:
        made[src] = copy_into(scene, src, prefix)
    for src, dup in made.items():
        if src.parent in made:
            dup.parent = made[src.parent]
            dup.matrix_parent_inverse = src.matrix_parent_inverse.copy()
        else:
            dup.location.z += dz


def present():
    assembly = bpy.data.scenes[SCENE]
    bpy.context.window.scene = assembly
    lighting(assembly)
    geo.camera_at(assembly, 'V3 assembly camera', (105, -115, 112), (0, 0, 13), 132)
    exploded = new_scene(EXPLODED)
    for name in NAMES:
        copy_into(exploded, bpy.data.objects[name], 'EXP ', 62 if name == NAMES[1] else 0)
    copy_model(exploded, 'EXP ', 26)
    lighting(exploded)
    geo.camera_at(exploded, 'V3 exploded camera', (115, -125, 150), (0, 0, 44), 172)
    layout = new_scene(LAYOUT)
    for index, name in enumerate(NAMES):
        dup = copy_into(layout, bpy.data.objects[name], 'PRINT ')
        if index == 1:           # lid prints upside down, outer face on the bed
            dup.rotation_euler.x = math.pi
            dup.location = (0, 80, Z_TOP)
    bpy.context.window.scene = assembly


def collision_volume(a, b):
    dup = a.copy()
    dup.data = a.data.copy()
    dup.modifiers.clear()
    tool = b.copy()
    tool.data = b.data.copy()
    tool.modifiers.clear()
    bpy.context.scene.collection.objects.link(dup)
    bpy.context.scene.collection.objects.link(tool)
    tool.location.z += .02       # split exactly coincident seating faces (calculation aid only)
    geo.activate(dup)
    mod = dup.modifiers.new('V3 intersection', 'BOOLEAN')
    mod.operation = 'INTERSECT'
    mod.object = tool
    choices = [i.identifier for i in mod.bl_rna.properties['solver'].enum_items]
    mod.solver = next(x for x in choices if x == 'MANIFOLD')
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm = bmesh.new()
    bm.from_mesh(dup.data)
    volume = round(abs(bm.calc_volume(signed=True)), 5)
    bm.free()
    bpy.data.objects.remove(dup, do_unlink=True)
    bpy.data.objects.remove(tool, do_unlink=True)
    return volume


def validate():
    bpy.context.window.scene = bpy.data.scenes[SCENE]
    parts = [bpy.data.objects[n] for n in NAMES]
    refs = bpy.data.collections[REFS]
    refs.hide_viewport = False
    result = dict(units='millimetres',
                  status='V3 fit prototype from PCB design files; not printed, no measured parts',
                  parameters_mm=P,
                  derived_mm=dict(body=[LEN, WID, Z_TOP], overall_with_strap_loops=[2 * (LOOP_CX + 7), WID, Z_TOP],
                                  cavity=[CAV_X, CAV_Y], pcb_bottom_z=Z_PCB_BOTTOM, pcb_top_z=Z_PCB_TOP,
                                  lid_split_z=Z_SPLIT, pcb_holes=PCB_HOLES, lid_screws=LID_SCREWS,
                                  boot_hole=BOOT_XY, en_hole=EN_XY),
                  collision_solver='MANIFOLD', contact_face_separation_for_boolean_mm=.02,
                  parts={o.name: geo.mesh_health(o) for o in parts},
                  assembly_intersections_mm3={parts[0].name + ' / ' + parts[1].name: collision_volume(parts[0], parts[1])})
    result['reference_intersections_mm3'] = {o.name: {p.name: collision_volume(p, o) for p in parts}
                                              for o in refs.objects}
    refs.hide_viewport = True
    worst = max([0.0] + [v for d in result['reference_intersections_mm3'].values() for v in d.values()]
                + list(result['assembly_intersections_mm3'].values()))
    result['largest_intersection_mm3'] = worst
    (ROOT / 'validation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('VALIDATION parts', json.dumps(result['parts']))
    print('VALIDATION largest intersection mm3', worst)
    for name, d in result['reference_intersections_mm3'].items():
        if any(d.values()):
            print('VALIDATION COLLISION', name, d)
    return result


def export_parts():
    bpy.context.window.scene = bpy.data.scenes[LAYOUT]
    (ROOT / 'exports').mkdir(exist_ok=True)
    for name in NAMES:
        obj = bpy.data.objects['PRINT ' + name]
        geo.activate(obj)
        position = obj.location.copy()
        obj.location.x = 0
        obj.location.y = 0
        try:
            bpy.ops.wm.stl_export(filepath=str(ROOT / 'exports' / (name[3:].lower() + '.stl')),
                                  export_selected_objects=True, global_scale=1, use_scene_unit=False,
                                  apply_modifiers=True)
        finally:
            obj.location = position
    bpy.context.window.scene = bpy.data.scenes[SCENE]


def render(scene, filename):
    bpy.context.window.scene = scene
    scene.render.filepath = str(ROOT / filename)
    bpy.ops.render.render(write_still=True)


def render_previews():
    scene = bpy.data.scenes[SCENE]
    render(scene, 'assembly_preview.png')
    render(bpy.data.scenes[EXPLODED], 'exploded_preview.png')
    lid = bpy.data.objects[NAMES[1]]
    old_camera = scene.camera
    lid.hide_render = True
    geo.camera_at(scene, 'V3 internal camera', (70, -105, 150), (0, 0, 12), 118)
    try:
        render(scene, 'internal_layout_preview.png')
    finally:
        lid.hide_render = False
    geo.camera_at(scene, 'V3 USB end camera', (150, 45, 85), (0, 3, 14), 118)
    render(scene, 'usb_end_preview.png')
    geo.camera_at(scene, 'V3 wire side camera', (-45, -150, 80), (0, 0, 14), 126)
    render(scene, 'wire_side_preview.png')
    scene.camera = old_camera
    bpy.context.window.scene = scene


def save_project():
    bpy.context.window.scene = bpy.data.scenes[SCENE]
    for filename, path in [('build_enclosure_v3.py', Path(__file__)),
                           ('V3 geometry helpers (V1 source)', ROOT.parent / 'build_enclosure.py')]:
        block = bpy.data.texts.get(filename) or bpy.data.texts.new(filename)
        block.clear()
        block.write(path.read_text(encoding='utf-8'))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'AISL-A_Enclosure_V3.blend'))


if __name__ == '__main__':
    # Pictures only. The print files (STL) and the CAD model now come from
    # freecad/build_enclosure_v3_freecad.py, which is the master. export_parts() is kept
    # for reference but no longer called, so there is only one set of STLs.
    build()
    present()
    validate()
    render_previews()
    save_project()
