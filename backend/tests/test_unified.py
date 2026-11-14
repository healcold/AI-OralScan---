from app.main import app
from app.inference.inference_engine import get_runtime, RuntimeRegistry
from app.inference.routes import get_private_storage as get_image_storage
from app.geometry.routes import get_private_storage as get_mesh_storage
from test_api import create, upload
from test_geometry import upload_mesh

def test_multimodal_summary_preserves_success_when_other_modality_fails(setup):
    client,storage,_=setup;runtime=RuntimeRegistry()
    class FailingDemo:
        is_demo=True
        def infer(self,_):raise ValueError('simulated failure')
    runtime.model_id='test';runtime.name='DEMO';runtime.version='test';runtime.adapter=FailingDemo()
    app.dependency_overrides[get_runtime]=lambda:runtime
    app.dependency_overrides[get_image_storage]=lambda:storage
    app.dependency_overrides[get_mesh_storage]=lambda:storage
    scan=create(client);image=upload(client,scan).json();mesh,_=upload_mesh(client,scan,'open.obj')
    geometry=client.post(f'/api/scans/{scan}/assets/{mesh["asset_id"]}/geometry-analysis');assert geometry.status_code==200
    failure=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[image['asset_id']]});assert failure.status_code==422
    result=client.get(f'/api/scans/{scan}/unified-analysis').json();assets={a['asset_id']:a for a in result['assets']}
    assert assets[image['asset_id']]['analysis_status']=='failed' and assets[mesh['asset_id']]['analysis_status']=='succeeded'
    assert assets[mesh['asset_id']]['jobs'][0]['result_summary']['geometry_metrics']['volume']['value'] is None
    assert assets[image['asset_id']]['jobs'][0]['result_summary']['is_demo'] is True
    assert 'no spatial registration' in result['limitations'][1]
