"""Check delivered binary STLs using ordinary Python, without Blender."""
from collections import Counter
from pathlib import Path
import json
import math
import struct

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    '01_base.stl': (98,58.9,27.0),
    '02_lid.stl': (74,58.9,6.4),
}


def check(path):
    data=path.read_bytes()
    count=struct.unpack_from('<I',data,80)[0]
    assert len(data)==84+50*count, 'Invalid binary STL length: '+path.name
    edges=Counter()
    lo=[math.inf]*3
    hi=[-math.inf]*3
    volume=0.0
    bad=0
    for i in range(count):
        row=struct.unpack_from('<12fH',data,84+50*i)
        vertices=[tuple(row[j:j+3]) for j in (3,6,9)]
        for vertex in vertices:
            for j in range(3):
                lo[j]=min(lo[j],vertex[j])
                hi[j]=max(hi[j],vertex[j])
        for a,b in [(vertices[0],vertices[1]),(vertices[1],vertices[2]),(vertices[2],vertices[0])]:
            edges[tuple(sorted((a,b)))]+=1
        a,b,c=vertices
        u=[b[j]-a[j] for j in range(3)]
        v=[c[j]-a[j] for j in range(3)]
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        bad+=sum(value*value for value in cross)<1e-16
        volume+=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6
    result=dict(triangles=count,dimensions_mm=[round(y-x,4) for x,y in zip(lo,hi)],
                minimum_z_mm=round(lo[2],6),unpaired_or_nonmanifold_edges=sum(n!=2 for n in edges.values()),
                degenerate_triangles=bad,volume_mm3=round(volume,3))
    assert result['unpaired_or_nonmanifold_edges']==0,(path.name,result)
    assert result['degenerate_triangles']==0,(path.name,result)
    assert abs(lo[2])<1e-4 and volume>0,(path.name,result)
    assert all(abs(a-b)<.001 for a,b in zip(result['dimensions_mm'],EXPECTED[path.name])),(path.name,result)
    return result


if __name__=='__main__':
    result={name:check(ROOT/'exports'/name) for name in EXPECTED}
    (ROOT/'stl_validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
