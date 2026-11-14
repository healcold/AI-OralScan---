"""Geometry quality and metrics on an in-memory copy; never changes the source."""
import hashlib
import io
import struct
import time
import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from ..mesh_geometry import _preflight, MAX_FACES, MAX_VERTICES, MeshInvalid
from .schemas import Measurement, MeshAnalysisResult

METRICS=('vertex_count','face_count','bounding_box','surface_area','volume','connected_components')
QUALITY=('empty_mesh','invalid_vertices','degenerate_faces','duplicate_vertices','holes','watertight','winding_consistency','disconnected_components','invalid_normals','source_normals')

def item(value=None, *, status='ok', reason=None, unit=None):
    return Measurement(status=status,value=value,reason=reason,unit=unit)

def coordinates(unit):
    return {'origin':'source-defined; anatomical origin not inferred','axis_directions':'source-defined; anatomical orientation not inferred','unit':unit,'transform_source_to_analysis':[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]],'scale_factor':1.0,'note':'Coordinates remain in the source frame. A temporary in-memory vertex merge supports topology checks.'}

def failed_result(asset_id,unit,message,elapsed_ms,sha=None):
    unavailable={name:item(status='unavailable',reason=message) for name in METRICS}
    quality={name:item(status='unavailable',reason=message) for name in QUALITY}
    return MeshAnalysisResult(asset_id=asset_id,geometry_metrics=unavailable,mesh_quality=quality,coordinate_system=coordinates(unit),warnings=[message],processing_time_ms=elapsed_ms,status='failed',source_sha256=sha)

def inspect_source_normals(data,fmt,mesh):
    """Check finite, non-zero declared normals; do not infer directional correctness."""
    normals=[];description=''
    if fmt=='stl':
        count=struct.unpack_from('<I',data,80)[0] if len(data)>=84 else 0
        if len(data)>=84 and 84+count*50==len(data):
            normals=np.ndarray((count,3),dtype='<f4',buffer=data,offset=84,strides=(50,4)).astype(np.float64)
        else:
            for line in data.decode('ascii',errors='replace').splitlines():
                p=line.strip().split()
                if len(p)>=2 and p[0].lower()=='facet' and p[1].lower()=='normal':
                    try: normals.append([float(v) for v in p[2:5]] if len(p)>=5 else [float('nan')]*3)
                    except ValueError: normals.append([float('nan')]*3)
        description='STL face normals'
    elif fmt=='obj':
        for line in data.decode('utf-8-sig').splitlines():
            p=line.strip().split()
            if p and p[0].lower()=='vn':
                try: normals.append([float(v) for v in p[1:4]] if len(p)>=4 else [float('nan')]*3)
                except ValueError: normals.append([float('nan')]*3)
        description='OBJ normal declarations'
    elif fmt=='ply':
        raw=mesh.metadata.get('_ply_raw',{}).get('vertex',{}).get('data',{})
        if isinstance(raw,dict) and all(axis in raw for axis in ('nx','ny','nz')):
            normals=np.column_stack([np.asarray(raw[axis]).reshape(-1) for axis in ('nx','ny','nz')])
        description='PLY vertex normals'
    arr=np.asarray(normals,dtype=np.float64)
    if not arr.size:return item(status='unavailable',reason=f'{description or "Source normals"} are absent or not available from the parser.')
    arr=arr.reshape(-1,3);valid=np.isfinite(arr).all(axis=1);lengths=np.linalg.norm(np.where(np.isfinite(arr),arr,0),axis=1);invalid=int(np.count_nonzero(~valid | ~np.isfinite(lengths) | (lengths<=1e-12)))
    return item(invalid,status='warning' if invalid else 'ok',reason=f'{description}: {len(arr)} checked for finite, non-zero vectors; correspondence and direction were not validated.')

def analyze_mesh(data: bytes, fmt: str, unit: str, asset_id: str, expected_sha256: str | None=None) -> MeshAnalysisResult:
    started=time.perf_counter();sha=hashlib.sha256(data).hexdigest();invalid=None
    try:
        if expected_sha256 and sha!=expected_sha256: raise MeshInvalid('Original file hash does not match the asset record')
        if unit not in ('unknown','mm','cm','m'): raise MeshInvalid('Invalid unit')
        cleaned,warnings=_preflight(data,fmt)
        mesh=trimesh.load_mesh(file_obj=io.BytesIO(cleaned),file_type=fmt,process=False,skip_materials=True)
        if not isinstance(mesh,trimesh.Trimesh): raise MeshInvalid('Expected a triangle mesh')
        vertices=np.asarray(mesh.vertices);faces=np.asarray(mesh.faces)
        if vertices.ndim!=2 or vertices.shape[1]!=3 or faces.ndim!=2 or faces.shape[1]!=3 or not len(vertices) or not len(faces): raise MeshInvalid('Mesh is empty or contains no triangles')
        if len(vertices)>MAX_VERTICES or len(faces)>MAX_FACES: raise MeshInvalid('Mesh exceeds vertex or face limits')
        invalid=int((~np.isfinite(vertices).all(axis=1)).sum())
        if invalid: raise MeshInvalid(f'Mesh contains {invalid} invalid vertices')
        if faces.min()<0 or faces.max()>=len(vertices): raise MeshInvalid('Face indices are out of range')
        source_normals=inspect_source_normals(data,fmt,mesh)
        bounds=np.vstack((vertices.min(axis=0),vertices.max(axis=0)));extent=float(np.max(bounds[1]-bounds[0]));tri=vertices[faces]
        cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(cross,axis=1)
        threshold=1e-12*extent*extent
        degenerate=int(np.count_nonzero(length<=threshold));invalid_normals=int(np.count_nonzero(~np.isfinite(length)|(length<=threshold)))
        duplicate=int(len(vertices)-len(np.unique(vertices,axis=0)))
        area=float(np.sum(length)*.5)
        if not np.isfinite(area): raise MeshInvalid('Surface area is non-finite')
        topology=mesh.copy();topology.merge_vertices();topology.remove_unreferenced_vertices()
        topo_vertices=np.asarray(topology.vertices); edges=np.asarray(topology.edges_sorted)
        edges=edges[edges[:,0]!=edges[:,1]]
        unique_edges,counts=np.unique(edges,axis=0,return_counts=True)
        graph=coo_matrix((np.ones(len(unique_edges)*2,dtype=np.uint8),(np.r_[unique_edges[:,0],unique_edges[:,1]],np.r_[unique_edges[:,1],unique_edges[:,0]])),shape=(len(topo_vertices),len(topo_vertices))).tocsr()
        component_count=int(connected_components(graph,directed=False,return_labels=False))
        boundary=unique_edges[counts==1];nonmanifold=int(np.count_nonzero(counts>2));boundary_count=int(len(boundary))
        holes_reason='Counts closed boundary loops, not anatomical holes; self-intersections are not checked.'
        if boundary_count:
            boundary_vertices,degree=np.unique(boundary,return_counts=True)
            if np.all(degree==2):
                bgraph=coo_matrix((np.ones(len(boundary)*2,dtype=np.uint8),(np.r_[boundary[:,0],boundary[:,1]],np.r_[boundary[:,1],boundary[:,0]])),shape=(len(topo_vertices),len(topo_vertices))).tocsr()
                holes=int(connected_components(bgraph[boundary_vertices][:,boundary_vertices],directed=False,return_labels=False));holes_status='warning'
            else: holes=None;holes_status='unavailable';holes_reason='Boundary is branched or non-manifold; closed-loop count is unavailable.'
        else: holes=0;holes_status='ok'
        watertight=bool(topology.is_watertight);winding=bool(topology.is_winding_consistent)
        volume=None;volume_reason=None
        if degenerate: volume_reason='Degenerate faces prevent a reliable volume.'
        elif not watertight or not winding or not topology.is_volume: volume_reason='Requires a watertight, consistently wound mesh with positive volume.'
        else:
            volume=float(topology.volume)
            if not np.isfinite(volume): volume=None;volume_reason='Volume is non-finite.'
        if duplicate: warnings.append(f'{duplicate} exact duplicate vertex positions in the loaded representation; STL commonly repeats vertices per face.')
        if degenerate: warnings.append(f'{degenerate} degenerate or near-degenerate faces detected.')
        if boundary_count: warnings.append(f'{boundary_count} boundary edges detected; mesh is open or non-manifold.')
        if nonmanifold: warnings.append(f'{nonmanifold} non-manifold edges detected.')
        if component_count>1: warnings.append(f'{component_count} disconnected vertex-connected components detected.')
        if not winding: warnings.append('Face winding is inconsistent.')
        if volume is None: warnings.append(volume_reason)
        if volume is not None: warnings.append('Volume is algebraic; self-intersection and nested-shell correctness were not checked.')
        if source_normals.status=='unavailable': warnings.append(source_normals.reason)
        elif source_normals.value: warnings.append(f'{source_normals.value} invalid source normal vectors detected; direction was not validated.')
        else: warnings.append('Source normal correspondence and direction were not validated.')
        linear=None if unit=='unknown' else unit
        metrics={'vertex_count':item(int(len(vertices))),'face_count':item(int(len(faces))),'bounding_box':item(bounds.tolist(),unit=linear),'surface_area':item(area,unit=None if unit=='unknown' else f'{unit}²'),'volume':item(volume,status='ok' if volume is not None else 'unavailable',reason=volume_reason,unit=None if unit=='unknown' else f'{unit}³'),'connected_components':item(component_count,reason='Vertex-connected components after temporary vertex merge.')}
        quality={'empty_mesh':item(False),'invalid_vertices':item(invalid),'degenerate_faces':item(degenerate,status='warning' if degenerate else 'ok',reason='Near-zero triangle area uses 1e-12 × bounding-extent squared on cross-product magnitude.'),'duplicate_vertices':item(duplicate,status='warning' if duplicate else 'ok',reason='Exact coordinate duplicates in loaded vertices; STL may repeat vertices by design.'),'holes':item(holes,status=holes_status,reason=holes_reason),'watertight':item(watertight,status='ok' if watertight else 'warning',reason=f'{boundary_count} boundary edges, {nonmanifold} non-manifold edges.'),'winding_consistency':item(winding,status='ok' if winding else 'warning'),'disconnected_components':item(component_count,status='warning' if component_count>1 else 'ok',reason='Vertex-connected after temporary merge.'),'invalid_normals':item(invalid_normals,status='warning' if invalid_normals else 'ok',reason='Counts invalid or near-zero normals computed from face geometry.'),'source_normals':source_normals}
        return MeshAnalysisResult(asset_id=asset_id,geometry_metrics=metrics,mesh_quality=quality,coordinate_system=coordinates(unit),warnings=warnings,processing_time_ms=round((time.perf_counter()-started)*1000,3),status='succeeded',source_sha256=sha)
    except Exception as exc:
        message=str(exc) if isinstance(exc,MeshInvalid) else 'Mesh geometry processing failed'
        result=failed_result(asset_id,unit,message,round((time.perf_counter()-started)*1000,3),sha)
        if message in ('Mesh is empty','Mesh contains no faces','Mesh is empty or contains no triangles'):
            result.mesh_quality['empty_mesh']=item(True,status='warning',reason=message)
        if invalid is not None and invalid>0:
            result.mesh_quality['invalid_vertices']=item(invalid,status='warning',reason=message)
        return result
