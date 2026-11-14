"""Bounded mesh intake; referenced materials are deliberately not resolved."""
import io
import json
import struct
import numpy as np
import trimesh

MAX_VERTICES = 200_000
MAX_FACES = 400_000

class MeshInvalid(ValueError): pass

PLY_TYPES={'char':'b','int8':'b','uchar':'B','uint8':'B','short':'h','int16':'h','ushort':'H','uint16':'H','int':'i','int32':'i','uint':'I','uint32':'I','float':'f','float32':'f','double':'d','float64':'d'}

def _validate_ply(data: bytes, header_end: int, header: list[str], vertex_count: int) -> None:
    """Bound list properties before allowing a third-party parser to allocate them."""
    elements=[]; current=None; mode=None
    for line in header:
        p=line.split()
        if not p: continue
        if p[0]=='format' and len(p)==3: mode=p[1]
        elif p[0]=='element' and len(p)==3:
            try: count=int(p[2])
            except ValueError as exc: raise MeshInvalid('Invalid PLY element count') from exc
            if count<0 or count>MAX_FACES: raise MeshInvalid('PLY element exceeds limits')
            current={'name':p[1],'count':count,'properties':[]};elements.append(current)
        elif p[0]=='property':
            if current is None: raise MeshInvalid('Invalid PLY property')
            if len(p)==3 and p[1] in PLY_TYPES: current['properties'].append((p[2],None,p[1]))
            elif len(p)==5 and p[1]=='list' and p[2] in PLY_TYPES and p[3] in PLY_TYPES and PLY_TYPES[p[2]] in 'bBhHiI': current['properties'].append((p[4],p[2],p[3]))
            else: raise MeshInvalid('Unsupported PLY property')
    if mode not in ('ascii','binary_little_endian','binary_big_endian'): raise MeshInvalid('Unsupported PLY format')
    body_start=data.find(b'\n',header_end)
    if body_start<0: raise MeshInvalid('Invalid PLY data')
    body=data[body_start+1:]; pos=0
    if mode=='ascii':
        try: tokens=iter(body.decode('ascii').split())
        except UnicodeDecodeError as exc: raise MeshInvalid('Invalid PLY text') from exc
        def read(typ):
            try:
                token=next(tokens); return float(token) if PLY_TYPES[typ] in 'fd' else int(token)
            except (ValueError,StopIteration) as exc: raise MeshInvalid('Truncated or invalid PLY data') from exc
    else:
        order='<' if mode=='binary_little_endian' else '>'
        def read(typ):
            nonlocal pos
            fmt=order+PLY_TYPES[typ];size=struct.calcsize(fmt)
            if pos+size>len(body): raise MeshInvalid('Truncated PLY data')
            value=struct.unpack_from(fmt,body,pos)[0];pos+=size;return value
    for element in elements:
        for _ in range(element['count']):
            for name,count_type,item_type in element['properties']:
                if count_type is None: read(item_type);continue
                n=read(count_type)
                if n<0 or n>64: raise MeshInvalid('PLY list property exceeds limit')
                for _ in range(n):
                    value=read(item_type)
                    if element['name']=='face' and name in ('vertex_indices','vertex_index') and (not isinstance(value,int) or value<0 or value>=vertex_count): raise MeshInvalid('PLY face index out of range')

def _preflight(data: bytes, fmt: str) -> tuple[bytes, list[str]]:
    if not data: raise MeshInvalid('Mesh is empty')
    warnings = []
    if fmt == 'obj':
        try: lines=data.decode('utf-8-sig').splitlines()
        except UnicodeDecodeError as exc: raise MeshInvalid('OBJ must be UTF-8 text') from exc
        vertices=0; faces=0; output=[]
        for line in lines:
            parts=line.strip().split()
            if not parts or parts[0].startswith('#'): output.append(line); continue
            kind=parts[0].lower()
            if kind in ('mtllib','usemtl'):
                if 'External material references ignored' not in warnings: warnings.append('External material references ignored')
                continue
            if kind=='v':
                vertices+=1
                if len(parts)<4: raise MeshInvalid('Invalid OBJ vertex')
            elif kind=='f':
                if not 3<=len(parts)-1<=64: raise MeshInvalid('OBJ faces must have 3–64 vertices')
                faces+=len(parts)-3
                for item in parts[1:]:
                    try: idx=int(item.split('/')[0])
                    except ValueError as exc: raise MeshInvalid('Invalid OBJ face index') from exc
                    if idx==0 or idx>vertices or idx < -vertices: raise MeshInvalid('OBJ face index out of range')
            if vertices>MAX_VERTICES or faces>MAX_FACES: raise MeshInvalid('Mesh exceeds vertex or face limits')
            output.append(line)
        if not vertices or not faces: raise MeshInvalid('Mesh contains no faces')
        return ('\n'.join(output)+'\n').encode(),warnings
    if fmt=='ply':
        header_end=data.find(b'end_header')
        if header_end<0 or header_end>65536 or not data.startswith(b'ply\n') and not data.startswith(b'ply\r\n'): raise MeshInvalid('Invalid PLY header')
        try: header=data[:header_end].decode('ascii').splitlines()
        except UnicodeDecodeError as exc: raise MeshInvalid('Invalid PLY header') from exc
        counts={}
        for line in header:
            parts=line.split()
            if len(parts)==3 and parts[0]=='element' and parts[1] in ('vertex','face'):
                if parts[1] in counts: raise MeshInvalid('Duplicate PLY element')
                try: counts[parts[1]]=int(parts[2])
                except ValueError as exc: raise MeshInvalid('Invalid PLY counts') from exc
        if not 0<counts.get('vertex',0)<=MAX_VERTICES or not 0<counts.get('face',0)<=MAX_FACES: raise MeshInvalid('PLY is empty or exceeds limits')
        _validate_ply(data,header_end,header,counts['vertex'])
    elif fmt=='stl':
        binary_count=struct.unpack('<I',data[80:84])[0] if len(data)>=84 else 0
        if len(data)>=84 and 84+binary_count*50==len(data):
            if not 0<binary_count<=min(MAX_FACES,MAX_VERTICES//3): raise MeshInvalid('STL is empty or exceeds limits')
        else:
            if not data.lstrip().lower().startswith(b'solid'): raise MeshInvalid('Invalid STL data')
            count=data.lower().count(b'facet normal')
            if not 0<count<=min(MAX_FACES,MAX_VERTICES//3): raise MeshInvalid('STL is empty or exceeds limits')
    else: raise MeshInvalid('Unsupported mesh format')
    return data,warnings

def inspect_mesh(data: bytes, fmt: str, unit: str) -> dict:
    if unit not in ('unknown','mm','cm','m'): raise MeshInvalid('Invalid unit')
    data,warnings=_preflight(data,fmt)
    try:
        mesh=trimesh.load_mesh(file_obj=io.BytesIO(data),file_type=fmt,process=False,skip_materials=True)
        if not isinstance(mesh,trimesh.Trimesh): raise MeshInvalid('Expected one triangle mesh')
        vertices=np.asarray(mesh.vertices); faces=np.asarray(mesh.faces)
        if vertices.ndim!=2 or vertices.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3 or not len(vertices) or not len(faces): raise MeshInvalid('Mesh contains no triangles')
        if len(vertices)>MAX_VERTICES or len(faces)>MAX_FACES: raise MeshInvalid('Mesh exceeds vertex or face limits')
        if not np.isfinite(vertices).all() or faces.min()<0 or faces.max()>=len(vertices): raise MeshInvalid('Mesh contains invalid vertices or face indices')
        mesh.merge_vertices()
        mesh.remove_unreferenced_vertices()
        vertices=np.asarray(mesh.vertices); faces=np.asarray(mesh.faces)
        bounds=np.asarray(mesh.bounds,dtype=float); area=float(mesh.area)
        if not np.isfinite(bounds).all() or not np.isfinite(area): raise MeshInvalid('Mesh has non-finite geometry')
        watertight=bool(mesh.is_watertight); winding=bool(mesh.is_winding_consistent)
        volume=float(mesh.volume) if watertight and winding and mesh.is_volume else None
        if volume is not None and not np.isfinite(volume): volume=None
        if not watertight: warnings.append('Mesh is not watertight; volume is unavailable')
        if not winding: warnings.append('Face winding is inconsistent')
        if volume is None and watertight: warnings.append('Volume is unavailable for this mesh')
        return {'vertex_count':int(len(vertices)),'face_count':int(len(faces)),'bounding_box':bounds.tolist(),'surface_area':area,'volume':volume,'volume_reason':None if volume is not None else 'Requires a watertight, consistently wound positive volume','watertight':watertight,'winding_consistent':winding,'unit':unit,'warnings':warnings,'quality':'warning' if warnings else 'valid'}
    except MeshInvalid: raise
    except Exception as exc: raise MeshInvalid('Unable to parse mesh') from exc
