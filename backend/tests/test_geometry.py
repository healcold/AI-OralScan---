import subprocess
from pathlib import Path
import pytest
from app.geometry.pipeline import analyze_mesh
from app.geometry.routes import get_private_storage
from app.main import app
from test_api import create

FIX=Path(__file__).parent/'fixtures'/'meshes'

def run(name,unit='unknown'):
    return analyze_mesh((FIX/name).read_bytes(),name.rsplit('.',1)[-1],unit,'asset-1')

@pytest.mark.parametrize('name',['tetra_ascii.stl','tetra_binary.stl','tetra.obj','with_material.obj','tetra_ascii.ply','tetra_binary.ply'])
def test_tetrahedron_metrics_and_units(name):
    result=run(name);m=result.geometry_metrics;q=result.mesh_quality
    assert result.status=='succeeded' and m['face_count'].value==4
    assert m['bounding_box'].value==[[0,0,0],[1,1,1]]
    assert m['surface_area'].value==pytest.approx(1.5+3**.5/2)
    assert m['volume'].value==pytest.approx(1/6) and m['volume'].status=='ok'
    assert m['connected_components'].value==1 and q['watertight'].value is True
    assert result.coordinate_system['unit']=='unknown' and m['surface_area'].unit is None
    assert result.coordinate_system['scale_factor']==1 and result.regions['items']==[]
    if name.endswith('.stl'):
        assert q['duplicate_vertices'].value==8
        assert q['source_normals'].value==4 and q['source_normals'].status=='warning'
    else: assert q['source_normals'].status=='unavailable'

def test_open_degenerate_disconnected_meshes():
    opened=run('open.obj','mm');m=opened.geometry_metrics;q=opened.mesh_quality
    assert q['watertight'].value is False and q['holes'].value==1
    assert m['volume'].value is None and m['volume'].reason and m['surface_area'].unit=='mm²'
    degenerate=run('degenerate.obj');assert degenerate.mesh_quality['degenerate_faces'].value==1
    assert degenerate.mesh_quality['invalid_normals'].value==1 and degenerate.geometry_metrics['volume'].value is None
    disconnected=run('disconnected.obj');assert disconnected.geometry_metrics['connected_components'].value==2
    assert disconnected.mesh_quality['disconnected_components'].status=='warning'

def test_empty_invalid_and_corrupt_are_explicit_failures():
    for name in ['empty.obj','corrupt.stl']:
        result=run(name);assert result.status=='failed' and result.warnings
        assert all(m.status=='unavailable' for m in result.geometry_metrics.values())
    assert run('empty.obj').mesh_quality['empty_mesh'].value is True
    result=analyze_mesh(b'v nan 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n','obj','unknown','id')
    assert result.status=='failed' and 'invalid vertices' in result.warnings[0] and result.mesh_quality['invalid_vertices'].value==1

def test_inconsistent_winding_and_duplicate_vertices():
    data=b'v 0 0 0\nv 1 0 0\nv 0 1 0\nv 0 0 1\nv 0 0 0\nf 1 3 2\nf 5 2 4\nf 1 4 3\nf 2 4 3\n'
    r=analyze_mesh(data,'obj','cm','id')
    assert r.status=='succeeded' and r.mesh_quality['winding_consistency'].value is False
    assert r.mesh_quality['duplicate_vertices'].value>=1
    assert r.geometry_metrics['volume'].value is None

def test_obj_declared_invalid_normal():
    data=b'v 0 0 0\nv 1 0 0\nv 0 1 0\nvn 0 0 0\nf 1//1 2//1 3//1\n'
    result=analyze_mesh(data,'obj','unknown','id')
    assert result.status=='succeeded' and result.mesh_quality['source_normals'].value==1

def test_ply_vertex_normal_validation():
    data=(b'ply\nformat ascii 1.0\nelement vertex 3\nproperty float x\nproperty float y\nproperty float z\n'
          b'property float nx\nproperty float ny\nproperty float nz\nelement face 1\nproperty list uchar int vertex_indices\nend_header\n'
          b'0 0 0 0 0 1\n1 0 0 0 0 0\n0 1 0 0 0 1\n3 0 1 2\n')
    result=analyze_mesh(data,'ply','unknown','id')
    assert result.status=='succeeded' and result.mesh_quality['source_normals'].value==1

@pytest.fixture
def geometry_setup(setup):
    client,storage,factory=setup
    app.dependency_overrides[get_private_storage]=lambda:storage
    return client,storage,factory

def upload_mesh(client,scan_id,name):
    data=(FIX/name).read_bytes();r=client.post(f'/api/scans/{scan_id}/assets',data={'source_type':'model_import','unit':'unknown'},files={'file':(name,data,'application/octet-stream')})
    assert r.status_code==201,r.text
    return r.json(),data

def test_analyze_save_reload_and_preserve_original(geometry_setup):
    client,storage,_=geometry_setup;scan=create(client);asset,original=upload_mesh(client,scan,'tetra.obj')
    url=f'/api/scans/{scan}/assets/{asset["asset_id"]}/geometry-analysis'
    assert client.get(url).status_code==404
    response=client.post(url);assert response.status_code==200,response.text
    result=response.json();assert result['status']=='succeeded' and result['asset_id']==asset['asset_id']
    assert result['source_sha256']==asset['sha256'] and result['processing_time_ms']>=0
    assert client.get(url).json()==result
    assert storage.path(asset['storage_key']).read_bytes()==original
    assert client.get(f'/api/scans/{scan}/analysis').json()['findings']==[]

def test_failed_job_persisted_with_warning_and_no_overwrite(geometry_setup,monkeypatch):
    client,storage,_=geometry_setup;scan=create(client);asset,original=upload_mesh(client,scan,'tetra.obj')
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('geometry',20)
    monkeypatch.setattr(subprocess,'run',timeout)
    url=f'/api/scans/{scan}/assets/{asset["asset_id"]}/geometry-analysis'
    r=client.post(url);assert r.status_code==422 and r.json()['error']['code']=='GEOMETRY_ANALYSIS_FAILED'
    saved=client.get(url).json();assert saved['status']=='failed' and 'time limit' in saved['warnings'][0]
    assert saved['geometry_metrics']['volume']['value'] is None and storage.path(asset['storage_key']).read_bytes()==original

def test_changed_hash_is_rejected_and_failure_is_persisted(geometry_setup):
    client,storage,factory=geometry_setup;scan=create(client);asset,original=upload_mesh(client,scan,'tetra.obj')
    from app.models import ScanAsset
    with factory() as db:
        record=db.get(ScanAsset,asset['asset_id']);record.sha256='0'*64;db.commit()
    url=f'/api/scans/{scan}/assets/{asset["asset_id"]}/geometry-analysis'
    assert client.post(url).status_code==422
    result=client.get(url).json();assert result['status']=='failed' and 'hash' in result['warnings'][0]
    assert storage.path(asset['storage_key']).read_bytes()==original


@pytest.mark.parametrize('delete_scan',[False,True])
def test_geometry_releases_connection_and_handles_concurrent_delete(geometry_setup,monkeypatch,delete_scan):
    import json
    from sqlalchemy import delete, select
    from app.models import AnalysisJob, ScanSession
    client,_,factory=geometry_setup
    scan=create(client);asset,original=upload_mesh(client,scan,'tetra.obj')

    def worker(*args,**kwargs):
        assert factory.kw['bind'].pool.checkedout()==0
        with factory() as other:
            other.connection().exec_driver_sql('PRAGMA busy_timeout=50')
            assert other.scalar(select(AnalysisJob.status))=='running'
            if delete_scan:
                other.execute(delete(ScanSession).where(ScanSession.scan_id==scan))
            else:
                other.add(ScanSession(metadata_json={},source_types=[]))
            other.commit()
        result=analyze_mesh(original,'obj','unknown',asset['asset_id'],asset['sha256'])
        return subprocess.CompletedProcess(args[0],0,json.dumps(result.model_dump()),'')

    monkeypatch.setattr(subprocess,'run',worker)
    response=client.post(f'/api/scans/{scan}/assets/{asset["asset_id"]}/geometry-analysis')
    assert response.status_code==(404 if delete_scan else 200),response.text
    if delete_scan:assert response.json()['error']['code']=='SCAN_NOT_FOUND'


def test_geometry_backpressure_and_slot_release_after_timeout(geometry_setup,monkeypatch):
    from app.geometry.routes import geometry_slots
    client,_,_=geometry_setup
    scan=create(client);asset,_=upload_mesh(client,scan,'tetra.obj')
    url=f'/api/scans/{scan}/assets/{asset["asset_id"]}/geometry-analysis'
    geometry_slots.acquire();geometry_slots.acquire()
    try:
        response=client.post(url)
        assert response.status_code==503 and response.headers['retry-after']=='1'
        assert response.json()['error']['code']=='GEOMETRY_BUSY'
        assert client.get(url).status_code==404
    finally:
        geometry_slots.release();geometry_slots.release()
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('geometry',20)
    monkeypatch.setattr(subprocess,'run',timeout)
    assert client.post(url).status_code==422
    assert geometry_slots.acquire(blocking=False)
    assert geometry_slots.acquire(blocking=False)
    assert not geometry_slots.acquire(blocking=False)
    geometry_slots.release();geometry_slots.release()
