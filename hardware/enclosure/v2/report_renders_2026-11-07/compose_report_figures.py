"""Prepare white-background report PNGs and measured CAD dimension annotations.

Only page composition is performed here. All object imagery comes from Blender renders.
"""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent
MANIFEST=json.loads((ROOT/'render_manifest.json').read_text(encoding='utf-8'))
INK='#24323A'
RULE='#637078'
TEAL='#196E69'
REGULAR=Path(r'C:\Windows\Fonts\arial.ttf')
BOLD=Path(r'C:\Windows\Fonts\arialbd.ttf')


def font(size,bold=False):return ImageFont.truetype(str(BOLD if bold else REGULAR),size)


def save(im,name):im.convert('RGB').save(ROOT/name,dpi=(300,300),optimize=True)


def white(raw):
    im=Image.open(ROOT/'raw'/(raw+'.png')).convert('RGBA')
    assert im.size==(2400,1600),im.size
    bg=Image.new('RGBA',im.size,'white');bg.alpha_composite(im)
    return bg.convert('RGB')


def label(im,text,xy,size=52,bold=False,vertical=False):
    f=font(size,bold)
    box=f.getbbox(text);tw=box[2]-box[0];th=box[3]-box[1]
    tag=Image.new('RGBA',(tw+30,th+24),'white')
    ImageDraw.Draw(tag).text((15-box[0],12-box[1]),text,font=f,fill=INK)
    if vertical:tag=tag.rotate(90,expand=True)
    im.paste(tag,(round(xy[0]-tag.width/2),round(xy[1]-tag.height/2)),tag)


def dim_h(im,x1,x2,y,feature_y1,feature_y2,text,size=52):
    d=ImageDraw.Draw(im)
    for x,fy in [(x1,feature_y1),(x2,feature_y2)]:
        end=y-15 if y<fy else y+15
        start=fy-10 if y<fy else fy+10
        d.line((x,start,x,end),fill=RULE,width=3)
    d.line((x1,y,x2,y),fill=RULE,width=3)
    d.polygon([(x1,y),(x1+20,y-8),(x1+20,y+8)],fill=RULE)
    d.polygon([(x2,y),(x2-20,y-8),(x2-20,y+8)],fill=RULE)
    label(im,text,((x1+x2)/2,y),size=size)


def dim_v(im,y1,y2,x,feature_x,text,size=52):
    d=ImageDraw.Draw(im)
    for y in (y1,y2):d.line((feature_x+10,y,x+15,y),fill=RULE,width=3)
    d.line((x,y1,x,y2),fill=RULE,width=3)
    d.polygon([(x,y1),(x-8,y1+20),(x+8,y1+20)],fill=RULE)
    d.polygon([(x,y2),(x-8,y2-20),(x+8,y2-20)],fill=RULE)
    label(im,text,(x,(y1+y2)/2),size=size,vertical=True)


def dimensions():
    im=white('06_top_orthographic');p=MANIFEST['top_points']
    d=ImageDraw.Draw(im);d.text((95,35),'TOP VIEW',font=font(44,True),fill=INK)
    dim_h(im,p['overall_left'][0],p['overall_right'][0],145,
          p['overall_left'][1],p['overall_right'][1],'146 mm overall')
    dim_h(im,p['body_left'][0],p['body_right'][0],1440,
          p['body_bl'][1],p['body_br'][1],'122 mm body')
    dim_v(im,p['width_top'][1],p['width_bottom'][1],2240,p['body_tr'][0],'86 mm')
    d.text((1200,1550),'Body height: 42 mm  |  All dimensions nominal',font=font(40),fill=RULE,anchor='mm')
    save(im,'06_top_dimensions.png')
    front=white('06_front_orthographic');q=MANIFEST['front_points']
    dim_v(front,q['height_top'][1],q['height_bottom'][1],2240,q['height_top'][0],'42 mm')
    crop=front.crop((0,370,2400,1185))
    page=Image.new('RGB',(2400,2580),'white');page.paste(im,(0,0))
    draw=ImageDraw.Draw(page)
    draw.line((95,1640,2305,1640),fill='#D3DADD',width=2)
    draw.text((95,1680),'FRONT VIEW — GLOVE WIRE EXIT',font=font(44,True),fill=INK)
    page.paste(crop,(0,1760))
    # Put the note inside the footer rather than over the rendered body.
    save(page,'06_dimensions.png')
    return im,page


def fit(im,box):
    out=im.copy();out.thumbnail(box,Image.Resampling.LANCZOS);return out


def primary_plate(top):
    canvas=Image.new('RGB',(4000,3330),'white');d=ImageDraw.Draw(canvas)
    d.text((100,65),'Enclosure design and assembly',font=font(96,True),fill=INK)
    d.text((100,185),'V2 CAD model  /  Progress report views',font=font(52),fill=RULE)
    # Larger labels keep the dimension panel readable when the full plate is reduced.
    large_top=white('06_top_orthographic');p=MANIFEST['top_points']
    dim_h(large_top,p['overall_left'][0],p['overall_right'][0],145,
          p['overall_left'][1],p['overall_right'][1],'146 mm overall',size=94)
    dim_h(large_top,p['body_left'][0],p['body_right'][0],1440,
          p['body_bl'][1],p['body_br'][1],'122 mm body',size=94)
    dim_v(large_top,p['width_top'][1],p['width_bottom'][1],2240,p['body_tr'][0],'86 mm',size=94)
    label(large_top,'Height: 42 mm',(1200,1550),size=76)
    panels=[('A','Assembled enclosure',white('01_assembled')),
            ('B','Exploded assembly',white('02_exploded')),
            ('C','Internal circuit layout',white('03_internal_layout')),
            ('D','Overall dimensions',large_top)]
    for i,(letter,title,im) in enumerate(panels):
        x=100+(i%2)*1950;y=350+(i//2)*1420
        d.text((x,y),letter,font=font(72,True),fill=TEAL)
        d.text((x+100,y),title,font=font(72,True),fill=INK)
        d.line((x,y+100,x+1850,y+100),fill='#D5DDE0',width=2)
        thumb=fit(im,(1850,1200))
        canvas.paste(thumb,(x+(1850-thumb.width)//2,y+125+(1200-thumb.height)//2))
    d.text((100,3230),'CAD design; electronics are schematic. Physical fit remains to be verified.',
           font=font(64),fill=RULE)
    save(canvas,'report_figure_4_views.png')


def overview(top):
    canvas=Image.new('RGB',(4800,2780),'white');d=ImageDraw.Draw(canvas)
    items=[('01','Assembled',white('01_assembled')),('02','Exploded',white('02_exploded')),
           ('03','Internal layout',white('03_internal_layout')),('04','USB end',white('04_usb_end')),
           ('05','IMU end',white('05_imu_end')),('06','Dimensions',top)]
    d.text((90,55),'Enclosure V2 — report render set',font=font(92,True),fill=INK)
    for i,(number,title,im) in enumerate(items):
        x=70+(i%3)*1585;y=260+(i//3)*1210
        d.text((x,y),number+'  '+title,font=font(60,True),fill=INK)
        thumb=fit(im,(1500,1070));canvas.paste(thumb,(x+(1500-thumb.width)//2,y+90+(1070-thumb.height)//2))
    d.text((90,2690),'Selection overview. Use the individual PNGs or four-view figure in the report.',font=font(48),fill=RULE)
    save(canvas,'overview_six_views.png')


if __name__=='__main__':
    for name in ('01_assembled','02_exploded','03_internal_layout','04_usb_end','05_imu_end'):
        save(white(name),name+'.png')
    top,page=dimensions();primary_plate(top);overview(top)
    qa={}
    for p in sorted((ROOT/'raw').glob('*.png')):
        im=Image.open(p).convert('RGBA');bbox=im.getchannel('A').getbbox()
        qa[p.name]=dict(pixels=im.size,visible_bbox=bbox,
                        unclipped=bool(bbox and bbox[0]>12 and bbox[1]>12 and bbox[2]<im.width-12 and bbox[3]<im.height-12))
    (ROOT/'render_qa.json').write_text(json.dumps(qa,indent=2),encoding='utf-8')
    assert all(v['unclipped'] for v in qa.values()),qa
    print('White-background report images, dimensions and figure panels created. All views fit within frame.')
