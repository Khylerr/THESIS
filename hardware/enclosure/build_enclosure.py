"""AISL-A wrist enclosure V1. Run inside Blender 5.x, using millimetre coordinates.

Via Blender MCP: exec(compile(open(PATH).read(), PATH, 'exec'), ns); ns['build']()
Then call present(), validate(), export_parts(), and save_project() in that namespace.
Nominal fit prototype: read README.md before printing or placing electronics.
"""
import bpy
import bmesh
import json
import math
from pathlib import Path
from mathutils import Vector, Quaternion

ROOT = Path(__file__).resolve().parent
SCENE = 'AISL-A | Enclosure V1'
P = dict(length=90.0, width=60.0, height=30.0, corner=6.0,
         wall=2.4, floor=2.4, lid=2.8, lid_gap=0.30, lip_depth=1.8,
         strap_clear_width=26.0, strap_clear_depth=6.0,
         m3_clearance=3.4, m3_pilot=2.6, m25_clearance=2.8, m25_pilot=2.0,
         usb_width=26.0, usb_height=16.0, button_length=16.0, button_width=10.0)
SCREWS = [(x,y) for x in (-38.4,38.4) for y in (-23.4,23.4)]
TRAY_SCREWS = [(x,y) for x in (-30.0,30.0) for y in (-19.0,19.0)]
IMU_SCREWS = [(20,y) for y in (-18.5,18.5)]
PART_NAMES = ['01_BASE', '02_LID', '03_CARRIER', '04_IMU_SHELF']


def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def mesh_object(name, verts, faces):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def rr(name, sx, sy, z0, z1, radius, cx=0, cy=0, segments=12):
    """Rounded rectangle prism, with horizontal radius and flat printing faces."""
    radius = min(radius, sx/2-0.001, sy/2-0.001)
    ring = []
    for x,y,a in [(sx/2-radius,sy/2-radius,0),
                  (-sx/2+radius,sy/2-radius,90),
                  (-sx/2+radius,-sy/2+radius,180),
                  (sx/2-radius,-sy/2+radius,270)]:
        for i in range(segments+1):
            t = math.radians(a + 90*i/segments)
            ring.append((cx+x+radius*math.cos(t),cy+y+radius*math.sin(t)))
    n = len(ring)
    verts = [(x,y,z) for z in (z0,z1) for x,y in ring]
    faces = [tuple(reversed(range(n))),tuple(range(n,2*n))]
    faces += [(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    return mesh_object(name, verts, faces)


def cylinder(name, radius, depth, at, axis='Z', vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius,
                                      depth=depth, location=at)
    obj = bpy.context.object
    obj.name = name
    if axis == 'X': obj.rotation_euler[1] = math.pi/2
    if axis == 'Y': obj.rotation_euler[0] = math.pi/2
    activate(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def boolean(obj, tool, operation='DIFFERENCE'):
    activate(obj)
    mod = obj.modifiers.new('Manufacturing feature', 'BOOLEAN')
    mod.operation = operation
    choices = [e.identifier for e in mod.bl_rna.properties['solver'].enum_items]
    mod.solver = next(e for e in choices if e == 'EXACT')
    mod.object = tool
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(tool, do_unlink=True)
    return obj


def bevel(obj, width=0.30, segments=3):
    activate(obj)
    mod = obj.modifiers.new('Edge comfort / print easing', 'BEVEL')
    mod.width,mod.segments = width,segments
    mod.affect = next(i.identifier for i in mod.bl_rna.properties['affect'].enum_items
                      if i.identifier == 'EDGES')
    mod.limit_method = next(i.identifier for i in mod.bl_rna.properties['limit_method'].enum_items
                            if i.identifier == 'ANGLE')
    bpy.ops.object.modifier_apply(modifier=mod.name)


def material(name, color, roughness=0.45, metallic=0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = (*color,1)
    mat.use_nodes = True
    node = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    node.inputs['Base Color'].default_value = (*color,1)
    node.inputs['Roughness'].default_value = roughness
    node.inputs['Metallic'].default_value = metallic
    return mat


def assign(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def text(name, body, at, size, mat=None, extrude=0):
    curve = bpy.data.curves.new(name, 'FONT')
    curve.body,curve.size,curve.align_x = body,size,'CENTER'
    curve.align_y = 'CENTER'
    curve.extrude = extrude
    obj = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = at
    if mat: assign(obj,mat)
    return obj


def engrave(obj, body, xy, size):
    tool = text('Engraving cutter',body,(*xy,29.65),size,extrude=0.5)
    activate(tool)
    bpy.ops.object.convert(target='MESH')
    boolean(obj,bpy.context.object)


def tag(obj, part=False, **kwargs):
    obj['AISLA_print_part'] = part
    for k,v in kwargs.items(): obj[k] = v


def clean_print_mesh(obj):
    """Weld sub-micron Boolean slivers before STL float32 serialization."""
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.001)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.001)
    wires=[e for e in bm.edges if not e.link_faces]
    if wires: bmesh.ops.delete(bm,geom=wires,context='EDGES')
    loose=[v for v in bm.verts if not v.link_edges]
    if loose: bmesh.ops.delete(bm,geom=loose,context='VERTS')
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    assert all(e.is_manifold for e in bm.edges), obj.name+' has an open edge after cleanup'
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def build():
    if bpy.data.scenes.get(SCENE):
        raise RuntimeError('This enclosure scene already exists. Preserve it before rebuilding.')
    scene = bpy.data.scenes.new(SCENE)
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 0.001
    scene.unit_settings.length_unit = 'MILLIMETERS'
    scene['design_status'] = 'V1 fit prototype; USB power, MPU6050 inside box on back of wrist (user confirmed)'
    scene['parameters_mm'] = json.dumps(P)
    scene['original_scene_preserved'] = True
    ink = material('AISLA / graphite',(.045,.071,.085),.5)
    frost = material('AISLA / warm ceramic',(.77,.80,.78),.45)
    teal = material('AISLA / teal',(.025,.38,.36),.5)
    pcb = material('Reference / green PCB',(.025,.16,.095),.6)
    gold = material('Reference / brass',(.5,.32,.07),.35,.65)
    metal = material('Reference / metal',(.38,.43,.46),.3,.8)

    # Main tub; no roof over USB: use a removable support in the slicer if needed.
    base = rr('01_BASE',P['length'],P['width'],0,27.2,P['corner'])
    boolean(base,rr('Cavity',85.2,55.2,2.4,31,3.6))
    for y in (-35.0,35.0):
        wing = rr('Strap wing',34,14,0,6.0,3,cx=0,cy=y)
        boolean(base,wing,'UNION')
        boolean(base,rr('26 x 6 strap slot',26,6,-1,8,1.5,cy=y+(-1 if y<0 else 1)))
    for x,y in SCREWS:
        boolean(base,cylinder('M3 screw tower',4.6,25.2,(x,y,14.6)),'UNION')
        boolean(base,cylinder('M3 blind pilot',1.3,13.0,(x,y,21.7)))
    for x,y in TRAY_SCREWS:
        boolean(base,cylinder('Carrier pedestal',3.5,3.4,(x,y,3.7)),'UNION')
        boolean(base,cylinder('M2.5 blind pilot',1.0,5,(x,y,3.7)))
    # USB clearance: x=-45 is the forearm-facing short side; nominal port centre z=15.8.
    usb = rr('USB cutter',P['usb_width'],P['usb_height'],0,10,2)
    # Orient its XY profile into the YZ face, extruding along X.
    usb.rotation_euler = (math.pi/2,0,math.pi/2)
    usb.location = (-49,0,15.8)
    boolean(base,usb)
    # A U-shaped exit is open at the split so harness installation needs no threading.
    boolean(base,rr('Finger harness notch',12,22,21.2,32,1,cx=45))
    # Solid pillars, joined to floor and right wall; transverse holes take a small cable tie.
    for y in (-12.5,12.5):
        boolean(base,rr('Strain relief anchor',5.2,6,2.0,25.0,1,cx=40,cy=y),'UNION')
        boolean(base,cylinder('Anchor tie tunnel',1.7,10,(40,y,21.5),axis='Y'))
    bevel(base,.30,3)
    assign(base,ink)
    tag(base,True,nominal_body_mm='90 x 60 x 27.2',strap_span_mm=84.0)

    lid = rr('02_LID',90,60,27.2,30,6)
    lip = rr('Locating lip',84.6,54.6,25.4,27.5,3.3)
    boolean(lip,rr('Lip hollow',81.6,51.6,24.5,28,1.8))
    boolean(lip,rr('Lip cable clearance',13,22.6,24,28,.8,cx=45))
    boolean(lid,lip,'UNION')
    # Relief lets the lip nest around the base's corner screw towers.
    for x,y in SCREWS:
        boolean(lid,cylinder('Lip tower clearance',4.95,3,(x,y,26.0)))
        boolean(lid,cylinder('M3 lid clearance',1.7,8,(x,y,28)))
        boolean(lid,cylinder('M3 pan head recess',3.2,2,(x,y,30.4)))
    for y in (-8.0,8.0):
        boolean(lid,rr('Button tool access',P['button_length'],P['button_width'],24,32,2,cx=-35,cy=y))
    bevel(lid,.25,3)
    engrave(lid,'AISL-A',(5,-2),6.8)
    engrave(lid,'FSL  /  SENSOR GLOVE',(4,-10),2.4)
    engrave(lid,'BOOT',(-22,-8),2.1)
    engrave(lid,'EN',(-22,8),2.1)
    assign(lid,frost)
    tag(lid,True,assembled_height_mm=30.0,lip_clearance_each_side_mm=.30)

    tray = rr('03_CARRIER',76,43,5.4,7.4,3,cx=-1)
    for x,y in SCREWS:
        boolean(tray,cylinder('Carrier tower clearance',4.95,14,(x,y,9)))
    for x,y in TRAY_SCREWS:
        boolean(tray,cylinder('M2.5 carrier clearance',1.4,5,(x,y,6.4)))
    # Rails fit BETWEEN the ESP32 header rows: pin tails have 5.6 mm clearance.
    for y in (-8.0,8.0):
        boolean(tray,rr('ESP32 support rail',46,3.2,7.1,13.0,.6,cx=-14,cy=y),'UNION')
    for x in (-26.0,-4.0):
        for y in (-16.8,16.8):
            boolean(tray,rr('ESP32 cable tie slot',4,2,4.4,8.4,.5,cx=x,cy=y))
    for x in (20.5,34.5):
        boolean(tray,rr('Divider perfboard support',3,26,7.1,11.0,.6,cx=x),'UNION')
    for y in (-17.0,17.0):
        boolean(tray,rr('Perfboard cable tie slot',4,2,4.4,8.4,.5,cx=27.5,cy=y))
    # Shelf towers are outside the divider board's 30 mm width; screw heads remain accessible.
    for x,y in IMU_SCREWS:
        boolean(tray,cylinder('IMU shelf tower',3,13.3,(x,y,13.75)),'UNION')
        boolean(tray,cylinder('M2.5 shelf blind pilot',1,8,(x,y,17.4)))
    bevel(tray,.22,2)
    assign(tray,teal)
    tag(tray,True,nominal_board_outline_mm='54.4 x 27.9',retention='2 cable ties; no assumed ESP32 PCB holes')

    shelf = rr('04_IMU_SHELF',24,22,20.4,22.4,2,cx=27)
    for x,y in IMU_SCREWS:
        boolean(shelf,rr('Shelf support arm',6,18,20.4,22.4,1,cx=x,cy=y/2),'UNION')
        boolean(shelf,cylinder('Shelf screw ear',3.1,2,(x,y,21.4)),'UNION')
        boolean(shelf,cylinder('M2.5 shelf clearance',1.4,5,(x,y,21.4)))
    for y in (-12.5,12.5):
        boolean(shelf,rr('Anchor pillar shelf clearance',6.0,6.8,19,24,1.2,cx=40,cy=y))
    # A shallow 20.8 x 16.2 pocket locates the 20.3 x 15.7 module; a tie supplies preload.
    pocket_rim=rr('MPU locating rim',22.4,17.8,22.1,24.0,1,cx=27)
    boolean(pocket_rim,rr('MPU pocket',20.8,16.2,21.5,25,.4,cx=27))
    boolean(shelf,pocket_rim,'UNION')
    for y in (-9.8,9.8):
        boolean(shelf,rr('IMU cable tie slot',3.2,1.5,19.4,23.4,.4,cx=27,cy=y))
    bevel(shelf,.18,2)
    assign(shelf,teal)
    tag(shelf,True,nominal_module_mm='20.3 x 15.7 x 3.0',retention='Rigid locating pocket plus 2.5 mm cable tie',location='Back of wrist, inside enclosure')

    # Engineering envelopes, deliberately not STEP imports or manufactured board claims.
    refs = bpy.data.collections.new('REFERENCE ONLY | nominal electronics / no export')
    scene.collection.children.link(refs)
    def reference(obj):
        for c in list(obj.users_collection): c.objects.unlink(obj)
        refs.objects.link(obj)
        obj.hide_render = True
        tag(obj,False,reference_only=True)
        return obj
    board = reference(rr('REF ESP32 PCB 54.4 x 27.9',54.4,27.9,13,14.6,.8,cx=-14))
    assign(board,pcb)
    for y in (-12.7,12.7):
        obj=reference(rr('REF ESP32 header keepout',46.2,2.54,7.6,13,.2,cx=-11.5,cy=y))
        assign(obj,ink)
    shield=reference(rr('REF ESP32 module envelope',25,17.5,14.6,18.3,.6,cx=1))
    assign(shield,metal)
    connector=reference(rr('REF USB shell envelope',6,8,14.6,17.5,.4,cx=-41.7))
    assign(connector,metal)
    for y in (-8,8):
        button=reference(rr('REF button position APPROXIMATE',5,4,14.6,17,.5,cx=-35,cy=y))
        assign(button,ink)
    perf=reference(rr('REF divider perfboard 18 x 30',18,30,11,12.6,.3,cx=27.5))
    assign(perf,gold)
    for y in (-10,-5,0,5,10):
        comp=reference(rr('REF divider component keepout',10,2.5,12.6,18.6,.4,cx=27.5,cy=y))
        assign(comp,ink)
    imu=reference(rr('REF MPU6050 envelope 20.3 x 15.7 x 3',20.3,15.7,22.4,25.4,.4,cx=27))
    assign(imu,pcb)
    foam=reference(rr('REF optional 2 mm EVA comfort pad',82,52,-2,0,9))
    assign(foam,ink)
    # Hide reference collection in assembled scene, reveal copies in the exploded scene.
    refs.hide_render = True
    refs.hide_viewport = True
    scene['reference_dimensions_source'] = 'Glove kicad/ESP32-DE-KIT/MODULE_ESP32-DEVKITC-32D.kicad_mod F.Fab outline'
    scene['power_decision'] = 'External USB (user confirmed); no battery compartment fit claim'
    scene['imu_decision'] = 'Inside enclosure on back of wrist (user confirmed); separate rigid removable shelf'
    for obj in (base,lid,tray,shelf):
        clean_print_mesh(obj)
        for face in obj.data.polygons:
            face.use_smooth = abs(face.normal.z)<.9999
        bm=bmesh.new()
        bm.from_mesh(obj.data)
        for edge in bm.edges:
            if edge.is_manifold: edge.smooth=edge.calc_face_angle()<.72
        bm.to_mesh(obj.data)
        bm.free()
        normals=obj.modifiers.new('Flat surface normals','WEIGHTED_NORMAL')
        normals.keep_sharp=True
    activate(base)
    print(json.dumps({'built':SCENE,'parts':PART_NAMES,'parameters_mm':P},indent=2))


def camera_at(scene, name, at, target, scale):
    data = bpy.data.cameras.new(name)
    obj = bpy.data.objects.new(name,data)
    scene.collection.objects.link(obj)
    obj.location = at
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()
    data.type = 'ORTHO'
    data.ortho_scale = scale
    data.clip_start,data.clip_end = .1,3000
    scene.camera = obj
    return obj


def settings(scene):
    # Use the connected engine (Blender 5.2 reports BLENDER_EEVEE).
    scene.render.engine = bpy.data.scenes[SCENE].render.engine
    scene.render.resolution_x,scene.render.resolution_y = 1600,1100
    scene.render.resolution_percentage = 100
    formats = [i.identifier for i in scene.render.image_settings.bl_rna.properties['file_format'].enum_items]
    scene.render.image_settings.file_format = next(f for f in formats if f == 'PNG')
    scene.world = bpy.data.worlds.new(scene.name + ' world')
    scene.world.use_nodes = True
    bg = next(n for n in scene.world.node_tree.nodes if n.type == 'BACKGROUND')
    bg.inputs['Color'].default_value=(.16,.20,.23,1)
    bg.inputs['Strength'].default_value=.5
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = -.65
    for name,at,power,size in [('Key',(40,-90,180),1300000,130),
                                ('Fill',(-100,0,110),750000,100),
                                ('Rim',(80,100,150),1600000,110)]:
        data = bpy.data.lights.new(scene.name+' '+name,'AREA')
        data.energy,data.shape,data.size=power,'DISK',size
        obj=bpy.data.objects.new(data.name,data)
        scene.collection.objects.link(obj)
        obj.location=at
        obj.rotation_euler=(Vector((0,0,20))-obj.location).to_track_quat('-Z','Y').to_euler()


def present():
    assembly=bpy.data.scenes[SCENE]
    bpy.context.window.scene=assembly
    settings(assembly)
    camera_at(assembly,'Assembly camera',(-120,-145,155),(0,0,12),147)
    # Exploded scene has independent objects and references, so the assembly stays fitted.
    exploded=bpy.data.scenes.new('AISL-A | Exploded')
    exploded.unit_settings.system='METRIC'
    exploded.unit_settings.scale_length=.001
    exploded.unit_settings.length_unit='MILLIMETERS'
    for name in PART_NAMES:
        src=bpy.data.objects[name]
        dup=src.copy()
        dup.data=src.data.copy()
        dup.name='EXP '+name
        exploded.collection.objects.link(dup)
        if name=='03_CARRIER': dup.location.z=30
        if name=='04_IMU_SHELF': dup.location.z=43
        if name=='02_LID': dup.location.z=73
    refs=bpy.data.collections.get('REFERENCE ONLY | nominal electronics / no export')
    for src in refs.objects:
        if 'EVA' in src.name: continue
        dup=src.copy()
        dup.data=src.data.copy()
        dup.name='EXP '+src.name
        dup.hide_render=False
        dup.location.z+=43 if 'MPU6050' in src.name else 30
        exploded.collection.objects.link(dup)
    settings(exploded)
    camera_at(exploded,'Exploded camera',(130,-170,200),(0,0,51),208)
    # Separate printing scene: every part rests on Z=0, lid exterior down.
    layout=bpy.data.scenes.new('AISL-A | Print layout (mm)')
    layout.unit_settings.system='METRIC'
    layout.unit_settings.scale_length=.001
    layout.unit_settings.length_unit='MILLIMETERS'
    for name in PART_NAMES:
        src=bpy.data.objects[name]
        dup=src.copy()
        dup.data=src.data.copy()
        dup.name='PRINT '+name
        layout.collection.objects.link(dup)
        if name=='02_LID':
            dup.rotation_euler.x=math.pi
            dup.location=(0,85,30)
        elif name=='03_CARRIER': dup.location=(0,-80,-5.4)
        elif name=='04_IMU_SHELF': dup.location=(-90,-20,-20.4)
    bpy.context.window.scene=assembly
    # Match viewport to the designed assembly camera, with material colors in solid mode.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active
                space.clip_end=3000
                space.shading.type='SOLID'
                space.shading.color_type='MATERIAL'
                space.overlay.show_overlays=False
                space.region_3d.view_perspective='CAMERA'
    print('Presentation scenes created: assembly, exploded, print layout.')


def mesh_health(obj):
    bm=bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    seen=set()
    components=0
    for v in bm.verts:
        if v.index in seen: continue
        components+=1
        todo=[v]
        while todo:
            cur=todo.pop()
            if cur.index in seen: continue
            seen.add(cur.index)
            todo.extend(e.other_vert(cur) for e in cur.link_edges)
    result=dict(dimensions_mm=[round(float(x),3) for x in obj.dimensions],
                vertices=len(bm.verts),faces=len(bm.faces),
                non_manifold_edges=sum(not e.is_manifold for e in bm.edges),
                boundary_edges=sum(e.is_boundary for e in bm.edges),
                connected_components=components,volume_mm3=round(bm.calc_volume(signed=True),3))
    bm.free()
    return result


def intersection_volume(a,b,contact_separation=.02):
    dup=a.copy()
    dup.data=a.data.copy()
    bpy.context.scene.collection.objects.link(dup)
    tool=b.copy()
    tool.data=b.data.copy()
    bpy.context.scene.collection.objects.link(tool)
    # Separate exactly coincident horizontal seating faces to avoid invalid Boolean
    # results. 0.02 mm is a calculation tolerance, not an added assembly clearance.
    tool.location.z+=contact_separation
    boolean(dup,tool,'INTERSECT')
    bm=bmesh.new()
    bm.from_mesh(dup.data)
    volume=abs(bm.calc_volume(signed=True))
    bm.free()
    bpy.data.objects.remove(dup,do_unlink=True)
    return round(volume,5)


def validate():
    bpy.context.window.scene=bpy.data.scenes[SCENE]
    objects=[bpy.data.objects[n] for n in PART_NAMES]
    result={'units':'millimetres','status':'nominal fit prototype, physical validation pending',
            'contact_face_separation_for_boolean_mm':.02,
            'parts':{o.name:mesh_health(o) for o in objects},
            'assembly_intersections_mm3':{
                a.name+' / '+b.name:intersection_volume(a,b)
                for i,a in enumerate(objects) for b in objects[i+1:]},
            'nominal_clearances_mm':dict(lid_per_side=.30,usb_opening_y=P['usb_width'],usb_opening_z=P['usb_height'],
                                         button_opening_x=P['button_length'],button_opening_y=P['button_width'],
                                         sensor_notch_y=22,sensor_notch_z=6,strap_slot_x=26,strap_slot_y=6),
            'parameters_mm':P}
    ref_names=['REF ESP32 PCB 54.4 x 27.9','REF USB shell envelope','REF divider perfboard 18 x 30',
               'REF MPU6050 envelope 20.3 x 15.7 x 3']
    result['nominal_reference_intersections_mm3']={
        name:{part:intersection_volume(bpy.data.objects[part],bpy.data.objects[name])
              for part in PART_NAMES} for name in ref_names}
    path=ROOT/'validation.json'
    path.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    return result


def export_parts():
    scene=bpy.data.scenes['AISL-A | Print layout (mm)']
    bpy.context.window.scene=scene
    out=ROOT/'exports'
    out.mkdir(exist_ok=True)
    for name in PART_NAMES:
        obj=bpy.data.objects['PRINT '+name]
        activate(obj)
        bpy.ops.wm.stl_export(filepath=str(out/(name.lower()+'.stl')),
                              export_selected_objects=True,global_scale=1.0,
                              use_scene_unit=False,apply_modifiers=True)
    bpy.context.window.scene=bpy.data.scenes[SCENE]
    print('STLs exported in numeric millimetres, oriented on Z=0.')


def save_project():
    bpy.context.window.scene=bpy.data.scenes[SCENE]
    # Embed the source as a Blender Text datablock for later edits.
    block=bpy.data.texts.get('build_enclosure.py') or bpy.data.texts.new('build_enclosure.py')
    block.clear()
    block.write(Path(__file__).read_text(encoding='utf-8'))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'AISL-A_Enclosure_V1.blend'))


if __name__=='__main__':
    build()
    present()
    validate()
    export_parts()
    save_project()
