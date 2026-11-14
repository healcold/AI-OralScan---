import base64
import hashlib
import io
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from PIL import Image
import pytest
from app.inference.confidence_filter import filter_candidates
from app.inference.inference_engine import RuntimeRegistry, YOLOSegmentationAdapter, get_runtime
from app.inference.image_preprocessing import prepare
from app.inference.nms import class_aware_nms
from app.inference.output_decoder import decode, OutputMismatch
from app.inference.routes import get_model_root, get_private_storage
from app.main import app
from test_api import create,upload

def spec(**changes):
    result={'name':'Synthetic test model','version':'test-1','purpose':'oral_research','contract_verified':True,'task':'detection','model_key':'test.onnx','sha256':'0'*64,'input_size':[32,32],'labels':['test-a','test-b'],'resize_mode':'letterbox','color_order':'RGB','dtype':'float32','scale':1/255,'pad_value':114,'output_layout':'BNC','mask_dim':0,'confidence_threshold':.25,'nms_threshold':.5,'max_detections':10}
    result.update(changes);return result

def make_onnx(path, predictions, proto=None, input_shape=(1,3,32,32)):
    tensors=[numpy_helper.from_array(np.asarray(predictions,dtype=np.float32),name='prediction_value')];outputs=[helper.make_tensor_value_info('predictions',TensorProto.FLOAT,list(tensors[0].dims))];nodes=[helper.make_node('Constant',[],['predictions'],value=tensors[0])]
    if proto is not None:
        tensor=numpy_helper.from_array(np.asarray(proto,dtype=np.float32),name='prototype_value');nodes.append(helper.make_node('Constant',[],['prototype'],value=tensor));outputs.append(helper.make_tensor_value_info('prototype',TensorProto.FLOAT,list(tensor.dims)))
    graph=helper.make_graph(nodes,'synthetic',[helper.make_tensor_value_info('images',TensorProto.FLOAT,list(input_shape))],outputs)
    model=helper.make_model(graph,opset_imports=[helper.make_opsetid('',13)],ir_version=10);onnx.save(model,str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()

@pytest.fixture
def inference_setup(setup,tmp_path):
    client,storage,_=setup;runtime=RuntimeRegistry();model_root=tmp_path/'models';model_root.mkdir()
    app.dependency_overrides[get_runtime]=lambda:runtime
    app.dependency_overrides[get_private_storage]=lambda:storage
    app.dependency_overrides[get_model_root]=lambda:model_root
    yield client,model_root,runtime

def test_decode_filter_nms_classes_and_large_indices():
    rows=np.zeros((1,300,6),dtype=np.float32);rows[0,:,0]=np.arange(300)*4+4;rows[0,:,1:4]=[4,2,2];rows[0,:,4]=.1;rows[0,:,5]=.05;rows[0,299,4]=.95
    boxes,scores,classes,extra=decode(rows,layout='BNC',class_count=2);b,s,c,e=filter_candidates(boxes,scores,classes,extra,.2)
    assert len(b)==1 and b[0,0]>1000 and class_aware_nms(b,s,c,.5,10).dtype==np.int64
    assert class_aware_nms(boxes,scores,classes,.5,300)[0]==299
    boxes=np.array([[0,0,10,10],[0,0,10,10],[0,0,10,10]],dtype=float);keep=class_aware_nms(boxes,np.array([.9,.8,.7]),np.array([0,0,1]),.5,10)
    assert keep.tolist()==[0,2]
    with pytest.raises(OutputMismatch): decode(np.zeros((1,2,7)),layout='BNC',class_count=2)
    with pytest.raises(OutputMismatch): decode(np.array([[[1,2,3,4,float('nan'),0]]]),layout='BNC',class_count=2)
    assert len(decode(np.empty((1,0,6)),layout='BNC',class_count=2)[0])==0

def test_resize_letterbox_and_mapping(tmp_path):
    path=tmp_path/'x.png';Image.new('RGB',(100,50),(3,20,100)).save(path)
    tensor,t=prepare(path,spec());assert tensor.shape==(1,3,32,32) and t.pad==(0,8)
    assert np.allclose(t.input_box_to_oriented([-9,0,40,40]),[0,0,100,50])
    assert np.allclose(t.oriented_box_to_raw([0,0,100,50]),[0,0,100,50])

def test_no_model_returns_clear_status(inference_setup):
    client,_,_=inference_setup;scan=create(client);asset=upload(client,scan).json();response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]})
    assert response.status_code==409 and response.json()['error']['code']=='MODEL_NOT_CONFIGURED'
    assert client.get('/api/models/status').json()['status']=='MODEL_NOT_CONFIGURED'
    assert client.get(f'/api/scans/{scan}/analysis').json()['findings']==[]

def test_real_onnx_detection_api(inference_setup):
    client,root,_=inference_setup
    rows=np.array([[[16,16,20,20,.9,.05],[16,16,20,20,.8,.01],[16,16,20,20,.1,.85],[16,16,3,3,.1,.1],[999,999,2,2,.8,.1]]],dtype=np.float32)
    digest=make_onnx(root/'test.onnx',rows);data=spec(sha256=digest);model=client.post('/api/models',json=data);assert model.status_code==201,model.text
    loaded=client.post('/api/models/load',json={'model_id':model.json()['model_id']});assert loaded.status_code==200,loaded.text
    scan=create(client);asset=upload(client,scan).json();response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]});assert response.status_code==201,response.text
    assert response.json()['finding_count']==2 and not response.json()['is_demo']
    result=client.get(f'/api/scans/{scan}/analysis').json();assert len(result['findings'])==2
    assert {f['category'] for f in result['findings']}=={'test-a','test-b'}
    for finding in result['findings']:
        assert finding['asset_id']==asset['asset_id'] and finding['model_version']=='test-1'
        assert finding['location']['coordinate_space']=='exif_oriented_image_pixels' and not finding['evidence']['is_demo']
        assert all(np.isfinite(finding['location']['bbox']))

def test_model_missing_hash_and_input_output_mismatch(inference_setup):
    client,root,_=inference_setup;registered=client.post('/api/models',json=spec()).json();mid=registered['model_id']
    assert client.post('/api/models/load',json={'model_id':mid}).json()['error']['code']=='MODEL_LOAD_FAILED'
    (root/'test.onnx').write_bytes(b'bad');assert client.post('/api/models/load',json={'model_id':mid}).status_code==422
    digest=make_onnx(root/'wrong.onnx',np.zeros((1,2,7)),input_shape=(1,3,64,64));record=client.post('/api/models',json=spec(model_key='wrong.onnx',sha256=digest)).json()
    assert client.post('/api/models/load',json={'model_id':record['model_id']}).status_code==422
    digest=make_onnx(root/'wrong_output.onnx',np.zeros((1,2,7)));record=client.post('/api/models',json=spec(model_key='wrong_output.onnx',sha256=digest)).json()
    assert client.post('/api/models/load',json={'model_id':record['model_id']}).status_code==422
    assert client.post('/api/models',json=spec(model_key='../outside.onnx')).status_code==422

def test_real_onnx_segmentation_through_api(inference_setup):
    client,root,_=inference_setup
    rows=np.array([[[16,16,20,20,.9,.1,8]]],dtype=np.float32);proto=np.ones((1,1,4,4),dtype=np.float32)
    digest=make_onnx(root/'test.onnx',rows,proto)
    record=client.post('/api/models',json=spec(task='segmentation',mask_dim=1,sha256=digest)).json()
    assert client.post('/api/models/load',json={'model_id':record['model_id']}).status_code==200
    scan=create(client);asset=upload(client,scan).json();response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]});assert response.status_code==201,response.text
    result=client.get(f'/api/scans/{scan}/analysis').json()['findings'][0]
    assert result['evidence']['mask_png'].startswith('data:image/png;base64,')

def test_inference_error_is_recorded_without_fake_findings(inference_setup):
    client,_,runtime=inference_setup
    class BrokenAdapter:
        is_demo=False
        def infer(self,_): raise OutputMismatch('shape mismatch')
    runtime.model_id='test';runtime.name='Synthetic';runtime.version='test';runtime.adapter=BrokenAdapter()
    scan=create(client);asset=upload(client,scan).json();response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]})
    assert response.status_code==422 and response.json()['error']['code']=='INFERENCE_FAILED'
    data=client.get(f'/api/scans/{scan}/analysis').json();assert data['jobs'][0]['status']=='failed' and data['findings']==[]

def test_mock_adapter_always_marks_demo(inference_setup):
    client,_,runtime=inference_setup
    class MockAdapter:
        is_demo=True
        def infer(self,_): return [{'category':'test-only','confidence':.8,'location':{'bbox':[0,0,1,1]},'evidence':{'is_demo':False}}]
    runtime.model_id='test';runtime.name='Mock';runtime.version='test';runtime.adapter=MockAdapter()
    scan=create(client);asset=upload(client,scan).json();response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]})
    assert response.json()['is_demo'] is True
    assert client.get(f'/api/scans/{scan}/analysis').json()['findings'][0]['evidence']['is_demo'] is True

def test_segmentation_real_output_and_empty_detection(tmp_path):
    path=tmp_path/'x.png';Image.new('RGB',(32,32),'white').save(path)
    cfg=spec(task='segmentation',mask_dim=1,resize_mode='resize');rows=np.array([[[16,16,20,20,.9,.1,8]]],dtype=np.float32);proto=np.ones((1,1,4,4),dtype=np.float32)
    class Input: name='images'
    class Session:
        def get_inputs(self):return [Input()]
        def run(self,*_):return [rows,proto]
    result=YOLOSegmentationAdapter(Session(),cfg).infer(path)
    mask=Image.open(io.BytesIO(base64.b64decode(result[0]['evidence']['mask_png'].split(',')[1])))
    assert mask.size==(32,32) and mask.getpixel((16,16))==255 and mask.getpixel((0,0))==0
    rows[0,0,4:6]=0
    assert YOLOSegmentationAdapter(Session(),cfg).infer(path)==[]


def test_inference_releases_database_and_exposes_running_job(inference_setup,setup):
    from sqlalchemy import select
    from app.models import AnalysisJob, ScanSession
    client,_,runtime=inference_setup
    _,_,factory=setup
    scan=create(client);asset=upload(client,scan).json()

    class ConcurrentWriter:
        is_demo=False
        def infer(self,_):
            assert factory.kw['bind'].pool.checkedout()==0
            with factory() as other:
                other.connection().exec_driver_sql('PRAGMA busy_timeout=50')
                assert other.scalar(select(AnalysisJob.status))=='running'
                other.add(ScanSession(metadata_json={},source_types=[]))
                other.commit()
            return []

    runtime.adapter=ConcurrentWriter()
    response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]})
    assert response.status_code==201,response.text
    assert len(client.get('/api/scans').json()['items'])==2


def test_scan_deleted_during_inference_returns_not_found(inference_setup,setup):
    from sqlalchemy import delete
    from app.models import ScanSession
    client,_,runtime=inference_setup
    _,_,factory=setup
    scan=create(client);asset=upload(client,scan).json()

    class DeletingAdapter:
        is_demo=False
        def infer(self,_):
            with factory() as other:
                other.connection().exec_driver_sql('PRAGMA busy_timeout=50')
                other.execute(delete(ScanSession).where(ScanSession.scan_id==scan))
                other.commit()
            return []

    runtime.adapter=DeletingAdapter()
    response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]})
    assert response.status_code==404,response.text
    assert response.json()['error']['code']=='SCAN_NOT_FOUND'


@pytest.mark.parametrize('result',[None,[{}],[{'category':'test','confidence':float('nan'),'location':{},'evidence':{}}]])
def test_malformed_adapter_result_records_failure_and_releases_slot(inference_setup,result):
    client,_,runtime=inference_setup
    scan=create(client);asset=upload(client,scan).json()
    class Adapter:
        is_demo=False
        def infer(self,_):return result
    runtime.adapter=Adapter()
    response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]})
    assert response.status_code==422,response.text
    data=client.get(f'/api/scans/{scan}/analysis').json()
    assert data['jobs'][0]['status']=='failed' and data['findings']==[]
    assert runtime.inference_slots.acquire(blocking=False)
    assert runtime.inference_slots.acquire(blocking=False)
    assert not runtime.inference_slots.acquire(blocking=False)
    runtime.inference_slots.release();runtime.inference_slots.release()


def test_inference_backpressure_does_not_create_jobs(inference_setup):
    client,_,runtime=inference_setup
    scan=create(client);asset=upload(client,scan).json()
    runtime.inference_slots.acquire();runtime.inference_slots.acquire()
    try:
        response=client.post(f'/api/scans/{scan}/analyze',json={'asset_ids':[asset['asset_id']]})
        assert response.status_code==503 and response.headers['retry-after']=='1'
        assert response.json()['error']['code']=='INFERENCE_BUSY'
        assert client.get(f'/api/scans/{scan}/analysis').json()['jobs']==[]
    finally:
        runtime.inference_slots.release();runtime.inference_slots.release()


def test_model_loading_releases_connection_and_serializes_loads(inference_setup,setup,monkeypatch):
    from app.inference import routes
    from app.inference.model_loader import ModelLoadError
    client,_,runtime=inference_setup
    _,_,factory=setup
    record=client.post('/api/models',json=spec()).json()
    url='/api/models/load';payload={'model_id':record['model_id']}
    runtime.load_lock.acquire()
    try:
        busy=client.post(url,json=payload)
        assert busy.status_code==503 and busy.json()['error']['code']=='MODEL_LOAD_BUSY'
    finally:runtime.load_lock.release()

    def load(*_):
        assert factory.kw['bind'].pool.checkedout()==0
        assert not runtime.load_lock.acquire(blocking=False)
        return object()
    monkeypatch.setattr(routes,'load_model',load)
    assert client.post(url,json=payload).status_code==200
    active=runtime.snapshot()
    def fail(*_):raise ModelLoadError('Invalid model')
    monkeypatch.setattr(routes,'load_model',fail)
    assert client.post(url,json=payload).status_code==422
    assert runtime.snapshot()==active
    assert runtime.load_lock.acquire(blocking=False)
    runtime.load_lock.release()
