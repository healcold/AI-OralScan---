"""Generate deterministic synthetic mesh fixtures and manifest; no external files."""
import json
import struct
from pathlib import Path

ROOT=Path(__file__).resolve().parent/'meshes'
VERTICES=[(0.,0.,0.),(1.,0.,0.),(0.,1.,0.),(0.,0.,1.)]
FACES=[(0,2,1),(0,1,3),(0,3,2),(1,2,3)]

def obj(vertices,faces):
    return ''.join('v %g %g %g\n'%v for v in vertices)+''.join('f %d %d %d\n'%(a+1,b+1,c+1) for a,b,c in faces)
def stl_ascii(vertices,faces):
    return 'solid fixture\n'+''.join(' facet normal 0 0 0\n  outer loop\n'+''.join('   vertex %g %g %g\n'%vertices[i] for i in face)+'  endloop\n endfacet\n' for face in faces)+'endsolid fixture\n'
def stl_binary():
    return b'fixture'.ljust(80,b'\0')+struct.pack('<I',len(FACES))+b''.join(struct.pack('<12fH',0,0,0,*VERTICES[a],*VERTICES[b],*VERTICES[c],0) for a,b,c in FACES)
def ply(binary=False):
    header=('ply\nformat '+('binary_little_endian' if binary else 'ascii')+' 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\nelement face 4\nproperty list uchar int vertex_indices\nend_header\n').encode()
    if binary:return header+b''.join(struct.pack('<fff',*v) for v in VERTICES)+b''.join(struct.pack('<Biii',3,*f) for f in FACES)
    return header+(''.join('%g %g %g\n'%v for v in VERTICES)+''.join('3 %d %d %d\n'%f for f in FACES)).encode()
def generate():
    ROOT.mkdir(parents=True,exist_ok=True)
    meshes={'tetra_ascii.stl':stl_ascii(VERTICES,FACES).encode(),'tetra_binary.stl':stl_binary(),'tetra.obj':obj(VERTICES,FACES).encode(),'with_material.obj':('mtllib fixture.mtl\nusemtl example\n'+obj(VERTICES,FACES)).encode(),'fixture.mtl':b'newmtl example\nKd 1 0 0\nmap_Kd ../outside.png\n','tetra_ascii.ply':ply(),'tetra_binary.ply':ply(True),'empty.obj':b'# empty\n','corrupt.stl':b'broken','open.obj':obj(VERTICES,FACES[:3]).encode(),'degenerate.obj':obj(VERTICES,[(0,0,1)]).encode(),'disconnected.obj':obj(VERTICES+[(x+3,y,z) for x,y,z in VERTICES],FACES+[(a+4,b+4,c+4) for a,b,c in FACES]).encode()}
    for name,content in meshes.items(): (ROOT/name).write_bytes(content)
    manifest={name:{'vertex_count':4,'face_count':4,'bounds':[[0,0,0],[1,1,1]],'surface_area':1.5+3**0.5/2,'watertight':True,'volume':1/6} for name in ('tetra_ascii.stl','tetra_binary.stl','tetra.obj','with_material.obj','tetra_ascii.ply','tetra_binary.ply')}
    manifest.update({'open.obj':{'watertight':False,'volume':None},'empty.obj':{'valid':False},'corrupt.stl':{'valid':False},'degenerate.obj':{'face_count':1,'surface_area':0},'disconnected.obj':{'vertex_count':8,'face_count':8,'components':2}})
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
if __name__=='__main__': generate()
