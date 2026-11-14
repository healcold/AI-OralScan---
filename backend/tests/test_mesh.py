import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
import pytest
from app.mesh_geometry import MeshInvalid, inspect_mesh, _preflight
from test_api import create

FIX=Path(__file__).parent/'fixtures'/'meshes'
MANIFEST=json.loads((FIX/'manifest.json').read_text())

@pytest.mark.parametrize('name',['tetra_ascii.stl','tetra_binary.stl','tetra.obj','with_material.obj','tetra_ascii.ply','tetra_binary.ply'])
def test_fixture_geometry(name):
    result=inspect_mesh((FIX/name).read_bytes(),name.rsplit('.',1)[-1],'unknown');expected=MANIFEST[name]
    assert result['vertex_count']==expected['vertex_count'] and result['face_count']==expected['face_count']
    assert result['bounding_box']==expected['bounds'] and result['watertight']
    assert result['surface_area']==pytest.approx(expected['surface_area'])
    assert result['volume']==pytest.approx(expected['volume']) and result['unit']=='unknown'
    if name=='with_material.obj': assert 'External material references ignored' in result['warnings']

def test_open_degenerate_disconnected_and_bad_indices():
    open_mesh=inspect_mesh((FIX/'open.obj').read_bytes(),'obj','mm')
    assert open_mesh['volume'] is None and not open_mesh['watertight'] and open_mesh['unit']=='mm'
    assert inspect_mesh((FIX/'degenerate.obj').read_bytes(),'obj','unknown')['face_count']==1
    assert inspect_mesh((FIX/'disconnected.obj').read_bytes(),'obj','unknown')['face_count']==8
    for name in ('empty.obj','corrupt.stl'):
        with pytest.raises(MeshInvalid): inspect_mesh((FIX/name).read_bytes(),name.rsplit('.',1)[-1],'unknown')
    with pytest.raises(MeshInvalid): inspect_mesh(b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 99\n','obj','unknown')
    with pytest.raises(MeshInvalid): inspect_mesh(b'v nan 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n','obj','unknown')
    with pytest.raises(MeshInvalid): _preflight(b'ply\nformat ascii 1.0\nelement vertex 200001\nelement face 1\nend_header\n','ply')
    invalid_ply=b'ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n0 0 0\n1 0 0\n0 1 0\n3 0 1 9\n'
    with pytest.raises(MeshInvalid): inspect_mesh(invalid_ply,'ply','unknown')
    with pytest.raises(MeshInvalid): inspect_mesh(invalid_ply.replace(b'3 0 1 9',b'255 0 1 2'),'ply','unknown')

def test_no_external_obj_references_are_resolved():
    data=b'mtllib ../../secret.mtl\nusemtl ignored\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n'
    sanitized,warnings=_preflight(data,'obj')
    assert b'mtllib' not in sanitized and b'usemtl' not in sanitized and warnings
    assert inspect_mesh(data,'obj','unknown')['face_count']==1

@pytest.mark.parametrize('name',['tetra_ascii.stl','tetra.obj','tetra_binary.ply'])
def test_mesh_api_stores_original_and_associates_session(setup,name):
    client,storage,_=setup; scan_id=create(client);data=(FIX/name).read_bytes()
    response=client.post(f'/api/scans/{scan_id}/assets',data={'source_type':'model_import','unit':'unknown'},files={'file':(name,data,'application/octet-stream')})
    assert response.status_code==201,response.text
    asset=response.json();assert asset['modality']=='mesh_3d' and asset['metadata']['unit']=='unknown'
    assert storage.path(asset['storage_key']).read_bytes()==data
    assert client.get(f'/api/scans/{scan_id}/assets/{asset["asset_id"]}/content').content==data
    assert client.get(f'/api/scans/{scan_id}').json()['source_types']==['model_import']

def test_mesh_invalid_and_timeout(setup,monkeypatch):
    client,storage,_=setup; scan_id=create(client)
    def send(data): return client.post(f'/api/scans/{scan_id}/assets',data={'source_type':'model_import'},files={'file':('bad.obj',data,'application/octet-stream')})
    assert send(b'bad data').status_code==422
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('mesh',15)
    monkeypatch.setattr(subprocess,'run',timeout)
    response=send((FIX/'tetra.obj').read_bytes())
    assert response.status_code==422 and response.json()['error']['code']=='MESH_TIMEOUT'
    assert not list(storage.scan_dir(scan_id).rglob('*.obj'))

def test_mesh_session_delete_removes_private_original(setup):
    client,storage,_=setup; scan_id=create(client);data=(FIX/'tetra.obj').read_bytes()
    response=client.post(f'/api/scans/{scan_id}/assets',data={'source_type':'model_import'},files={'file':('tetra.obj',data,'application/octet-stream')})
    assert response.status_code==201
    assert client.delete(f'/api/scans/{scan_id}').status_code==204
    assert not storage.scan_dir(scan_id).exists()

def test_fixtures_are_deterministic():
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIX.iterdir() if p.is_file()}
    spec=importlib.util.spec_from_file_location('generate_meshes',FIX.parent/'generate_meshes.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.generate()
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in FIX.iterdir() if p.is_file()}
