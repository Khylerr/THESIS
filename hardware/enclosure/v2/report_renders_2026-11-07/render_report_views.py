"""Render report views from the saved enclosure V2; design geometry is read-only.

Run in Blender 5.2. PNGs are written into raw/ with alpha. compose_report_figures.py
adds the white page background, dimensions, panel layout and 300 dpi metadata.
"""
import bpy
import hashlib
import json
import math
import struct
from pathlib import Path
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'AISL-A_Enclosure_V2.blend'
SOURCE_SCENE='AISL-A | Enclosure V2 (perfboard)'
PREFIX='REPORT 2026-11-07 | '
PARTS=('V2_01_BASE','V2_02_LID','V2_03_PERFBOARD_CRADLE')
W,H=2400,1600
VIEWS={
 '01_assembled':dict(at=(180,-190,175),target=(0,0,21),refs=True,lid=True,spread=False),
 '02_exploded':dict(at=(185,-205,225),target=(0,0,68),refs=True,lid=True,spread=True),
 '03_internal_layout':dict(at=(110,-155,225),target=(0,0,18),refs=True,lid=False,spread=False),
 '04_usb_end':dict(at=(235,65,105),target=(15,0,20),refs=True,lid=True,spread=False),
 '05_imu_end':dict(at=(-235,65,105),target=(-15,0,20),refs=True,lid=True,spread=False),
 '06_top_orthographic':dict(at=(0,0,300),target=(0,0,21),refs=False,lid=True,spread=False,ortho=190),
 '06_front_orthographic':dict(at=(0,-300,21),target=(0,0,21),refs=False,lid=True,spread=False,ortho=190),
}


def enum(owner,prop,value):
    choices=[i.identifier for i in owner.bl_rna.properties[prop].enum_items]
    if value not in choices:raise ValueError((prop,value,choices))
    return value


def source_scene():
    if SOURCE_SCENE not in bpy.data.scenes:
        with bpy.data.libraries.load(str(SOURCE),link=False) as (src,dst):
            assert SOURCE_SCENE in src.scenes
            dst.scenes=[SOURCE_SCENE]
    return bpy.data.scenes[SOURCE_SCENE]


def fingerprint(obj):
    digest=hashlib.sha256()
    for v in obj.data.vertices:digest.update(struct.pack('<3f',*v.co))
    for p in obj.data.polygons:
        digest.update(struct.pack('<I',len(p.vertices)))
        digest.update(struct.pack('<'+'I'*len(p.vertices),*p.vertices))
    digest.update(struct.pack('<16f',*(c for row in obj.matrix_world for c in row)))
    return digest.hexdigest()


def setup_scene(key):
    source=source_scene()
    assert PREFIX+key not in bpy.data.scenes,'Report scene already exists: '+key
    scene=bpy.data.scenes.new(PREFIX+key)
    bpy.context.window.scene=scene
    scene.unit_settings.system=source.unit_settings.system
    scene.unit_settings.scale_length=source.unit_settings.scale_length
    scene.unit_settings.length_unit=source.unit_settings.length_unit
    options=VIEWS[key]
    for src in source.objects:
        if src.type!='MESH':continue
        is_part=src.get('AISLA_print_part',False)
        is_ref=src.get('reference_only',False)
        if not(is_part or (is_ref and options['refs'])):continue
        if 'plug' in src.name.lower():continue
        if src.name==PARTS[1] and not options['lid']:continue
        dup=src.copy() # Shared mesh is never edited; only object placement changes.
        dup.name=key+' / '+src.name
        scene.collection.objects.link(dup)
        dup.hide_render=False;dup.hide_viewport=False;dup.hide_set(False)
        if options['spread']:
            if src.name==PARTS[1]:dup.location.z+=95
            elif src.name==PARTS[2] or is_ref:dup.location.z+=45
        dup['report_source_object']=src.name
    scene.render.engine=source.render.engine
    scene.render.resolution_x=W;scene.render.resolution_y=H
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format=enum(scene.render.image_settings,'file_format','PNG')
    scene.render.image_settings.color_mode=enum(scene.render.image_settings,'color_mode','RGBA')
    scene.render.image_settings.color_depth=enum(scene.render.image_settings,'color_depth','8')
    scene.render.film_transparent=True
    scene.render.image_settings.compression=30
    scene.eevee.taa_render_samples=128
    scene.eevee.shadow_ray_count=4
    scene.eevee.shadow_step_count=8
    scene.view_settings.view_transform=source.view_settings.view_transform
    scene.view_settings.exposure=-.65
    scene.world=bpy.data.worlds.new(PREFIX+key+' world');scene.world.use_nodes=True
    bg=next(n for n in scene.world.node_tree.nodes if n.type=='BACKGROUND')
    bg.inputs['Color'].default_value=(.8,.86,.93,1)
    bg.inputs['Strength'].default_value=.6
    for name,pos,power,size in [('Key',(60,-120,245),1700000,170),
                              ('Fill',(-170,70,170),1200000,150),
                              ('Rim',(120,150,210),1900000,150)]:
        light=bpy.data.lights.new(PREFIX+key+' '+name,'AREA')
        light.energy=power;light.shape=enum(light,'shape','DISK');light.size=size
        obj=bpy.data.objects.new(light.name,light);scene.collection.objects.link(obj)
        obj.location=pos
        obj.rotation_euler=(Vector(options['target'])-obj.location).to_track_quat('-Z','Y').to_euler()
    cam_data=bpy.data.cameras.new(PREFIX+key+' camera')
    camera=bpy.data.objects.new(cam_data.name,cam_data);scene.collection.objects.link(camera)
    camera.location=options['at']
    camera.rotation_euler=(Vector(options['target'])-camera.location).to_track_quat('-Z','Y').to_euler()
    cam_data.type=enum(cam_data,'type','ORTHO');cam_data.ortho_scale=options.get('ortho',220)
    cam_data.clip_start=.1;cam_data.clip_end=3000;scene.camera=camera
    bpy.context.view_layer.update()
    if 'ortho' not in options:
        corners=[obj.matrix_world@Vector(c) for obj in scene.objects if obj.type=='MESH' for c in obj.bound_box]
        for _ in range(2):
            points=[world_to_camera_view(scene,camera,p) for p in corners]
            span_x=max(p.x for p in points)-min(p.x for p in points)
            span_y=max(p.y for p in points)-min(p.y for p in points)
            cam_data.ortho_scale*=max(span_x/.86,span_y/.84)
            bpy.context.view_layer.update()
    scene['report_purpose']=key
    scene['report_note']='CAD design render; electronic shapes are schematic; physical fit pending'
    return scene


def project(scene,point):
    p=world_to_camera_view(scene,scene.camera,Vector(point))
    return [round(p.x*W,4),round((1-p.y)*H,4)]


def build():
    source=source_scene()
    manifest=dict(date='2026-11-07',source=str(SOURCE),resolution=[W,H],
                  source_fingerprints={n:fingerprint(source.objects[n]) for n in PARTS},
                  body_mm=[122,86,42],overall_mm=[146,86,42],views={})
    for key in VIEWS:
        scene=setup_scene(key)
        manifest['views'][key]=dict(scene=scene.name,camera=list(scene.camera.location),
                                   ortho_scale=scene.camera.data.ortho_scale,
                                   objects=[o.get('report_source_object') for o in scene.objects if o.type=='MESH'])
        if key=='06_top_orthographic':
            manifest['top_points']={k:project(scene,p) for k,p in {
                'overall_left':(-73,0,0),'overall_right':(73,0,0),
                'body_left':(-61,0,0),'body_right':(61,0,0),
                'width_top':(0,43,42),'width_bottom':(0,-43,42),
                'body_tl':(-61,43,42),'body_tr':(61,43,42),
                'body_bl':(-61,-43,42),'body_br':(61,-43,42),
                'left_slot':(-67,0,3),'right_slot':(67,0,3)}.items()}
        if key=='06_front_orthographic':
            manifest['front_points']={k:project(scene,p) for k,p in {
                'height_bottom':(61,-43,0),'height_top':(61,-43,42),
                'body_left':(-61,-43,0),'body_right':(61,-43,0)}.items()}
    (ROOT/'render_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Report scenes prepared:',list(VIEWS))


def render(keys):
    for key in keys:
        scene=bpy.data.scenes[PREFIX+key];bpy.context.window.scene=scene
        scene.render.filepath=str(ROOT/'raw'/(key+'.png'))
        bpy.ops.render.render(write_still=True)
        print('Rendered',key)


def save():
    manifest=json.loads((ROOT/'render_manifest.json').read_text())
    source=source_scene()
    assert all(fingerprint(source.objects[n])==v for n,v in manifest['source_fingerprints'].items()),'Design geometry changed'
    bpy.context.window.scene=bpy.data.scenes[PREFIX+'01_assembled']
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active;space.clip_end=3000
                space.overlay.show_overlays=False
                space.region_3d.view_perspective='CAMERA'
    block=bpy.data.texts.get('render_report_views.py') or bpy.data.texts.new('render_report_views.py')
    block.clear();block.write(Path(__file__).read_text(encoding='utf-8'))
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Enclosure_Report_Views.blend'))
    print('Saved separate report-view Blender project; original V2 geometry verified unchanged.')


if __name__=='__main__':
    build();render(list(VIEWS));save()
