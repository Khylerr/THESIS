"""Photo-based enclosure for the assembled AISL-A perfboard. Blender 5.x, mm.

Uses geometry helpers from ../build_enclosure.py. V1 files and scenes are preserved.
User supplied 9 x 6 x 3 cm; conservatively interpreted as main board/assembly envelope.
The extra MPU overhang, component offsets and corner hole positions remain provisional.
"""
import bpy
import bmesh
import importlib.util
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('aisla_geometry',ROOT.parent/'build_enclosure.py')
geo=importlib.util.module_from_spec(spec)
spec.loader.exec_module(geo)
SCENE='AISL-A | Enclosure V2 (perfboard)'
EXPLODED='AISL-A | V2 exploded'
LAYOUT='AISL-A | V2 print layout (mm)'
P=dict(length=122.0,width=86.0,height=42.0,wall=2.8,floor=2.8,lid=2.8,
       board_length=90.0,board_width=60.0,assembly_height=30.0,board_cx=8.0,
       board_bottom_z=14.0,solder_lowest_z=6.0,assembly_ceiling_z=36.0,
       usb_width=26.0,usb_height=16.0,usb_cy=17.0,usb_cz=26.5,
       imu_opening_width=26.0,imu_opening_height=14.0,imu_opening_cy=17.0,imu_opening_cz=25.4,
       cable_width=76.0,cable_floor_z=16.0,cable_roof_z=27.0,
       lip_clearance=.30,mpu_projection_allowance=16.0,mesh_weld_tolerance=.003,
       strap_loop_cx=66.0,strap_slot_cx=67.0,strap_slot_width=26.0,strap_slot_depth=6.0)
NAMES=['V2_01_BASE','V2_02_LID','V2_03_PERFBOARD_CRADLE']
SCREWS=[(x,y) for x in (-54.4,54.4) for y in (-36.4,36.4)]
CRADLE_SCREWS=[(x,y) for x in (-28,44) for y in (-35,35)]
BOARD_SLOTS=[(x,y) for x in (-34,50) for y in (-27,27)]
REFS='V2 REFERENCE ONLY | photo layout, not print parts'


def remove_skinny_faces(bm):
    # Collapse only sub-0.02 mm edges of near-zero-area triangles before float32 STL.
    for _ in range(100):
        candidate=None
        for f in bm.faces:
            if len(f.verts)!=3:continue
            a,b,c=[tuple(float(v) for v in p.co) for p in f.verts]
            u=[b[j]-a[j] for j in range(3)];v=[c[j]-a[j] for j in range(3)]
            cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
            edge=min(f.edges,key=lambda e:e.calc_length())
            if sum(x*x for x in cross)<1e-14 and edge.calc_length()<.02:
                candidate=edge;break
        if candidate is None:return
        bmesh.ops.collapse(bm,edges=[candidate])
    raise RuntimeError('Excessive microscopic triangles')


def finish(obj):
    bm=bmesh.new();bm.from_mesh(obj.data)
    tolerance=.0001 if 'CRADLE' in obj.name else P['mesh_weld_tolerance']
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=tolerance)
    bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=tolerance)
    wires=[e for e in bm.edges if not e.link_faces]
    if wires:bmesh.ops.delete(bm,geom=wires,context='EDGES')
    loose=[v for v in bm.verts if not v.link_edges]
    if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
    bmesh.ops.triangulate(bm,faces=list(bm.faces))
    # Remove only microscopic, single-sided triangular fins at Boolean junctions.
    fins=[f for f in bm.faces if len(f.verts)==3 and f.calc_area()<.00001
          and all(e.is_boundary for e in f.edges)]
    if fins:bmesh.ops.delete(bm,geom=fins,context='FACES')
    boundary=[e for e in bm.edges if e.is_boundary]
    # The triangulator may omit a microscopic sliver at a coplanar Boolean junction.
    # Repair only triangular loops whose every edge is shorter than 0.02 mm.
    if boundary and all(e.calc_length()<.02 for e in boundary):
        bmesh.ops.holes_fill(bm,edges=boundary,sides=3)
    remove_skinny_faces(bm)
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
    assert all(e.is_manifold for e in bm.edges),obj.name+' is not manifold'
    bm.to_mesh(obj.data);bm.free();obj.data.update()
    for face in obj.data.polygons:face.use_smooth=abs(face.normal.z)<.9999
    bm=bmesh.new();bm.from_mesh(obj.data)
    for edge in bm.edges:
        if edge.is_manifold:edge.smooth=edge.calc_face_angle()<.72
    bm.to_mesh(obj.data);bm.free()
    mod=obj.modifiers.new('Flat surface normals','WEIGHTED_NORMAL');mod.keep_sharp=True
    obj['AISLA_V2']=True;obj['AISLA_print_part']=True


def engrave(obj,body,xy,size):
    tool=geo.text('V2 engraving cutter',body,(*xy,41.65),size,extrude=.5)
    geo.activate(tool);bpy.ops.object.convert(target='MESH')
    geo.boolean(obj,bpy.context.object)


def build():
    if bpy.data.scenes.get(SCENE):raise RuntimeError('Preserve existing V2 scene before rebuilding.')
    scene=bpy.data.scenes.new(SCENE);bpy.context.window.scene=scene
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=.001
    scene.unit_settings.length_unit='MILLIMETERS'
    scene['parameters_mm']=json.dumps(P)
    scene['measurement_status']='90 x 60 x 30 mm user supplied; overhang and feature offsets estimated from photos'
    scene['design_status']='V2 fit prototype, assembled perfboard stays intact'
    ink=geo.material('AISLA V2 / graphite',(.045,.071,.085),.5)
    frost=geo.material('AISLA V2 / ceramic',(.77,.80,.78),.45)
    teal=geo.material('AISLA V2 / teal',(.025,.38,.36),.5)
    brown=geo.material('AISLA V2 / perfboard',(.30,.105,.035),.65)
    pcb=geo.material('AISLA V2 / black PCB',(.025,.03,.035),.6)
    blue=geo.material('AISLA V2 / MPU PCB',(.015,.23,.36),.55)
    metal=geo.material('AISLA V2 / shield',(.48,.51,.50),.3,.7)
    gold=geo.material('AISLA V2 / pins',(.57,.37,.10),.35,.7)
    cream=geo.material('AISLA V2 / resistors',(.66,.51,.29),.65)
    orange=geo.material('AISLA V2 / caps',(.48,.16,.035),.6)

    base=geo.rr(NAMES[0],122,86,0,39.2,6)
    geo.boolean(base,geo.rr('V2 cavity',116.4,80.4,2.8,44,3.2))
    # Strap loops on the two short end faces; kept below the USB opening.
    for side in (-1,1):
        geo.boolean(base,geo.rr('V2 short-end strap loop',14,34,0,6,3,cx=side*P['strap_loop_cx']),'UNION')
        geo.boolean(base,geo.rr('V2 short-end strap slot 26 x 6',P['strap_slot_depth'],P['strap_slot_width'],
                               -1,7,1.5,cx=side*P['strap_slot_cx']))
    for x,y in SCREWS:
        geo.boolean(base,geo.cylinder('V2 lid tower',4.6,36.8,(x,y,20.8)),'UNION')
        geo.boolean(base,geo.cylinder('V2 M3 pilot',1.3,15,(x,y,32.7)))
    for x,y in CRADLE_SCREWS:
        geo.boolean(base,geo.cylinder('V2 cradle pedestal',3.5,8.6,(x,y,6.7)),'UNION')
        geo.boolean(base,geo.cylinder('V2 M2.5 pilot',1,7,(x,y,8.5)))
    usb=geo.rr('V2 corner USB opening',26,16,0,12,2)
    usb.rotation_euler=(math.pi/2,0,math.pi/2)
    usb.location=(54,17,26.5);geo.boolean(base,usb)
    imu=geo.rr('V2 opposite-end IMU opening',P['imu_opening_width'],P['imu_opening_height'],0,12,2)
    imu.rotation_euler=(math.pi/2,0,math.pi/2)
    imu.location=(-66,P['imu_opening_cy'],P['imu_opening_cz']);geo.boolean(base,imu)
    # Drop-in wiring: the lid's removable apron closes the upper part of this notch.
    geo.boolean(base,geo.rr('V2 long-side wire notch',76,12,16,44,1,cx=8,cy=-43))
    for x in (-16,28):
        geo.boolean(base,geo.rr('V2 harness tie anchor',8,4,2.4,24,1,cx=x,cy=-36.5),'UNION')
        geo.boolean(base,geo.cylinder('V2 tie tunnel',1.7,12,(x,-36.5,20),axis='X'))
    geo.bevel(base,.30,3);geo.assign(base,ink)

    lid=geo.rr(NAMES[1],122,86,39.2,42,6)
    lip=geo.rr('V2 locating lip',115.8,79.8,37.4,39.5,2.9)
    geo.boolean(lip,geo.rr('V2 lip hollow',112.8,76.8,36.4,40,1.4))
    geo.boolean(lip,geo.rr('V2 lip harness clearance',76.6,13,36,40,1,cx=8,cy=-43))
    geo.boolean(lid,lip,'UNION')
    geo.boolean(lid,geo.rr('V2 removable cable-wall apron',75.4,2.8,27,39.5,.4,cx=8,cy=-41.6),'UNION')
    for x,y in SCREWS:
        geo.boolean(lid,geo.cylinder('V2 lip tower relief',4.95,3,(x,y,38)))
        geo.boolean(lid,geo.cylinder('V2 M3 clearance',1.7,18,(x,y,35)))
        geo.boolean(lid,geo.cylinder('V2 pan-head recess',3.2,2,(x,y,42.4)))
    for y in (8,26):geo.boolean(lid,geo.rr('V2 button access',16,10,36,44,2,cx=46,cy=y))
    geo.bevel(lid,.25,3)
    engrave(lid,'FSL  /  PERFBOARD V2',(-12,-10),2.8)
    engrave(lid,'EN',(31,8),2.4);engrave(lid,'BOOT',(30,26),2.4)
    geo.assign(lid,frost)

    # Open under the pin field; four corner pads contact only nominal bare board corners.
    cradle=geo.rr(NAMES[2],96,66,11,14,3,cx=8)
    geo.boolean(cradle,geo.rr('V2 open solder underside',92,62,10,15,1,cx=8))
    for x in (-35.5,51.5):
        for y in (-28.5,28.5):
            geo.boolean(cradle,geo.rr('V2 corner support pad',9,9,11,14,1,cx=x,cy=y),'UNION')
    for x,y in BOARD_SLOTS:
        geo.boolean(cradle,geo.rr('V2 adjustable board corner slot',4.5,4,10,15,1,cx=x,cy=y))
    # Outside the board edge: a shallow guide prevents sliding without touching headers.
    rim=geo.rr('V2 perfboard locating rim',94.4,64.4,13.7,15.4,2,cx=8)
    geo.boolean(rim,geo.rr('V2 91.2 x 61.2 board pocket',91.2,61.2,13,18,.6,cx=8))
    geo.boolean(cradle,rim,'UNION')
    for x,y in CRADLE_SCREWS:
        geo.boolean(cradle,geo.cylinder('V2 cradle ear',3.4,3,(x,y,12.5)),'UNION')
        geo.boolean(cradle,geo.cylinder('V2 cradle clearance',1.4,6,(x,y,12.5)))
    for x,y in SCREWS:
        geo.boolean(cradle,geo.cylinder('V2 cradle tower clearance',4.95,10,(x,y,14)))
    geo.bevel(cradle,.20,2);geo.assign(cradle,teal)
    for obj in (base,lid,cradle):finish(obj)

    refs=bpy.data.collections.new(REFS);scene.collection.children.link(refs)
    def ref(obj,mat,check=True):
        for c in list(obj.users_collection):c.objects.unlink(obj)
        refs.objects.link(obj);geo.assign(obj,mat)
        obj['AISLA_V2']=True;obj['reference_only']=True;obj['clearance_check']=check
        return obj
    board=ref(geo.rr('V2 REF assembled perfboard 90 x 60',90,60,14,15.6,.5,cx=8),brown)
    for y in (4.3,29.7):
        ref(geo.rr('V2 REF female socket',46.2,2.54,15.6,23.6,.2,cx=22.5,cy=y),pcb)
        ref(geo.rr('V2 REF solder pin envelope',46.2,.9,6,15.6,.1,cx=22.5,cy=y),gold)
    ref(geo.rr('V2 REF ESP32 at upper right',54.4,27.9,23.6,25.2,.5,cx=25.5,cy=17),pcb)
    ref(geo.rr('V2 REF ESP32 shield',25,18,25.2,29.2,.5,cx=16,cy=17),metal)
    ref(geo.rr('V2 REF USB connector at board edge',6,8,25.2,28.2,.4,cx=53.5,cy=17),metal)
    for y in (8,26):ref(geo.rr('V2 REF approximate button',5,4,25.2,27.5,.4,cx=46,cy=y),pcb)
    ref(geo.rr('V2 REF overhanging MPU6050',15.7,20.3,23.6,25.2,.4,cx=-44.8,cy=17),blue)
    ref(geo.rr('V2 REF MPU IC',4,4,25.2,26.6,.2,cx=-44.8,cy=17),pcb)
    ref(geo.rr('V2 REF MPU header support',6,17.8,15.6,23.6,.3,cx=-35,cy=17),pcb)
    for x in (-25,-8,9,26,43):
        ref(geo.cylinder('V2 REF divider resistor',1.5,7,(x,-10,17.7),axis='Y',vertices=24),cream)
        ref(geo.cylinder('V2 REF divider capacitor',2.1,1.7,(x,-21,18.2),axis='Y',vertices=24),orange)
    # USB overmould is a trial envelope, not a connector manufacturing model.
    plug=ref(geo.rr('V2 REF USB plug envelope',24,14,22,31,2,cx=66,cy=17),pcb)
    plug.hide_render=True;plug.hide_set(True)
    refs.hide_render=True;refs.hide_viewport=True
    scene['reference_note']='Layout reconstructed from user photos. Brown board 90x60 mm; module offsets estimated.'
    scene['imu_mount']='MPU remains connected to perfboard; no separate shelf or relocated sensor'
    scene['assembly_envelope_top_z_mm']=36.0
    geo.activate(base)
    print('Built V2: intact perfboard, corner USB, overhanging IMU and long-side harness exit.')


def lighting(scene):
    scene.render.engine=bpy.data.scenes[SCENE].render.engine
    scene.render.resolution_x=1600;scene.render.resolution_y=1100
    scene.render.resolution_percentage=100
    formats=[i.identifier for i in scene.render.image_settings.bl_rna.properties['file_format'].enum_items]
    scene.render.image_settings.file_format=next(x for x in formats if x=='PNG')
    scene.world=bpy.data.worlds.new(scene.name+' world');scene.world.use_nodes=True
    bg=next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND')
    bg.inputs['Color'].default_value=(.16,.20,.23,1);bg.inputs['Strength'].default_value=.5
    scene.view_settings.view_transform='AgX';scene.view_settings.exposure=-.65
    for name,at,power,size in [('Key',(50,-100,210),1600000,150),('Fill',(-130,0,140),900000,120),('Rim',(80,130,180),1800000,130)]:
        data=bpy.data.lights.new('V2 '+name,'AREA');data.energy=power;data.size=size
        obj=bpy.data.objects.new(data.name,data);scene.collection.objects.link(obj)
        obj.location=at;obj.rotation_euler=(Vector((0,0,25))-obj.location).to_track_quat('-Z','Y').to_euler()


def present():
    assembly=bpy.data.scenes[SCENE];bpy.context.window.scene=assembly;lighting(assembly)
    geo.camera_at(assembly,'V2 assembly camera',(160,-175,170),(0,0,20),198)
    exploded=bpy.data.scenes.new(EXPLODED)
    for name in NAMES:
        src=bpy.data.objects[name];dup=src.copy();dup.data=src.data.copy()
        dup.name='EXP '+name;exploded.collection.objects.link(dup)
        if name==NAMES[1]:dup.location.z=65
        if name==NAMES[2]:dup.location.z=25
    for src in bpy.data.collections[REFS].objects:
        if 'plug' in src.name:continue
        dup=src.copy();dup.data=src.data.copy();dup.name='EXP '+src.name
        dup.hide_render=False;dup.hide_set(False);dup.location.z+=25
        exploded.collection.objects.link(dup)
    exploded.unit_settings.system='METRIC';exploded.unit_settings.scale_length=.001
    exploded.unit_settings.length_unit='MILLIMETERS';lighting(exploded)
    geo.camera_at(exploded,'V2 exploded camera',(170,-180,215),(0,0,54),246)
    layout=bpy.data.scenes.new(LAYOUT)
    layout.unit_settings.system='METRIC';layout.unit_settings.scale_length=.001
    layout.unit_settings.length_unit='MILLIMETERS'
    for index,name in enumerate(NAMES):
        src=bpy.data.objects[name];dup=src.copy();dup.data=src.data.copy()
        dup.name='PRINT '+name;layout.collection.objects.link(dup)
        if index==1:dup.rotation_euler.x=math.pi;dup.location=(0,120,42)
        if index==2:dup.location=(0,-115,-11)
    bpy.context.window.scene=assembly
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active;space.clip_end=3000
                space.shading.type='SOLID';space.shading.color_type='MATERIAL'
                space.overlay.show_overlays=False;space.region_3d.view_perspective='CAMERA'


def collision_volume(a,b):
    # These operands have already passed manifold mesh checks. Blender 5.2's Exact
    # solver misclassifies some disjoint objects through an open access passage;
    # use its Manifold solver for collision volume, with modifiers excluded.
    dup=a.copy();dup.data=a.data.copy();dup.modifiers.clear()
    tool=b.copy();tool.data=b.data.copy();tool.modifiers.clear()
    bpy.context.scene.collection.objects.link(dup);bpy.context.scene.collection.objects.link(tool)
    tool.location.z+=.02;geo.activate(dup)
    mod=dup.modifiers.new('V2 verified manifold intersection','BOOLEAN')
    mod.operation='INTERSECT';mod.object=tool
    choices=[i.identifier for i in mod.bl_rna.properties['solver'].enum_items]
    mod.solver=next(x for x in choices if x=='MANIFOLD')
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bm=bmesh.new();bm.from_mesh(dup.data)
    assert all(e.is_manifold for e in bm.edges),'Invalid collision-check output'
    volume=round(abs(bm.calc_volume(signed=True)),5);bm.free()
    bpy.data.objects.remove(dup,do_unlink=True);bpy.data.objects.remove(tool,do_unlink=True)
    return volume


def validate():
    bpy.context.window.scene=bpy.data.scenes[SCENE]
    parts=[bpy.data.objects[n] for n in NAMES]
    result=dict(units='millimetres',measurement_status='User supplied 90x60x30; overhang and offsets provisional',
                parameters_mm=P,contact_face_separation_for_boolean_mm=.02,collision_solver='MANIFOLD',
                parts={o.name:geo.mesh_health(o) for o in parts},
                assembly_intersections_mm3={a.name+' / '+b.name:collision_volume(a,b)
                                           for i,a in enumerate(parts) for b in parts[i+1:]})
    result['reference_intersections_mm3']={o.name:{p.name:collision_volume(p,o) for p in parts}
        for o in bpy.data.collections[REFS].objects if o.get('clearance_check')}
    (ROOT/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2));return result


def export_parts():
    bpy.context.window.scene=bpy.data.scenes[LAYOUT]
    (ROOT/'exports').mkdir(exist_ok=True)
    for name in NAMES:
        obj=bpy.data.objects['PRINT '+name];geo.activate(obj)
        position=obj.location.copy()
        # Export each part near XY=0; retain the on-bed Z orientation.
        obj.location.x=0;obj.location.y=0
        try:
            bpy.ops.wm.stl_export(filepath=str(ROOT/'exports'/(name[3:].lower()+'.stl')),
                                  export_selected_objects=True,global_scale=1,use_scene_unit=False,apply_modifiers=True)
        finally:obj.location=position
    bpy.context.window.scene=bpy.data.scenes[SCENE]


def render_previews():
    for name,filename in [(SCENE,'assembly_preview.png'),(EXPLODED,'exploded_preview.png')]:
        scene=bpy.data.scenes[name];bpy.context.window.scene=scene
        scene.render.filepath=str(ROOT/filename);bpy.ops.render.render(write_still=True)
    scene=bpy.data.scenes[SCENE];bpy.context.window.scene=scene
    old_camera=scene.camera;lid=bpy.data.objects[NAMES[1]];old_lid=lid.hide_render
    refs=bpy.data.collections[REFS];old_refs=refs.hide_render
    lid.hide_render=True;refs.hide_render=False
    geo.camera_at(scene,'V2 internal fit camera',(105,-150,210),(0,0,20),198)
    scene.render.filepath=str(ROOT/'internal_layout_preview.png')
    try:bpy.ops.render.render(write_still=True)
    finally:scene.camera=old_camera;lid.hide_render=old_lid;refs.hide_render=old_refs
    # Opposite end view exposes the new IMU access opening with its schematic board behind it.
    refs.hide_render=False
    geo.camera_at(scene,'V2 IMU access camera',(-175,135,145),(-10,0,20),198)
    scene.render.filepath=str(ROOT/'imu_access_preview.png')
    try:bpy.ops.render.render(write_still=True)
    finally:scene.camera=old_camera;refs.hide_render=old_refs


def save_project():
    bpy.context.window.scene=bpy.data.scenes[SCENE]
    for filename,path in [('build_enclosure_v2.py',Path(__file__)),('V2 geometry helpers (V1 source)',ROOT.parent/'build_enclosure.py')]:
        block=bpy.data.texts.get(filename) or bpy.data.texts.new(filename)
        block.clear();block.write(path.read_text(encoding='utf-8'))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'AISL-A_Enclosure_V2.blend'))


if __name__=='__main__':
    build();present();validate();export_parts();render_previews();save_project()
