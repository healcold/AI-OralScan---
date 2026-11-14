import hashlib
from pathlib import Path
import onnxruntime as ort

class ModelLoadError(ValueError): pass

def load_model(root: Path, key: str, expected_hash: str, config: dict):
    root=root.resolve();path=(root/key).resolve()
    if not path.is_relative_to(root) or path.suffix.lower()!='.onnx': raise ModelLoadError('Model must be an ONNX file inside the private models directory')
    if not path.is_file(): raise ModelLoadError('Model file not found')
    if path.stat().st_size>512*1024*1024: raise ModelLoadError('Model file exceeds 512 MiB')
    model_bytes=path.read_bytes()
    if hashlib.sha256(model_bytes).hexdigest()!=expected_hash.lower(): raise ModelLoadError('Model SHA-256 does not match the registered file')
    try: session=ort.InferenceSession(model_bytes,providers=['CPUExecutionProvider'])
    except Exception as exc: raise ModelLoadError('Unable to load ONNX model') from exc
    inputs=session.get_inputs();outputs=session.get_outputs();expected_type={'float32':'tensor(float)','uint8':'tensor(uint8)'}[config['dtype']]
    if len(inputs)!=1 or inputs[0].type!=expected_type: raise ModelLoadError('Model input count or type does not match configuration')
    w,h=config['input_size'];shape=inputs[0].shape
    if len(shape)!=4 or any(isinstance(actual,int) and actual!=wanted for actual,wanted in zip(shape,[1,3,h,w])): raise ModelLoadError('Model input shape does not match NCHW configuration')
    required=2 if config['task']=='segmentation' else 1
    if len(outputs)!=required: raise ModelLoadError('Model output count does not match declared task')
    expected_channels=4+len(config['labels'])+config['mask_dim']
    pred_shape=outputs[0].shape;channel_axis=1 if config['output_layout']=='BCN' else 2
    if len(pred_shape)!=3 or isinstance(pred_shape[0],int) and pred_shape[0]!=1 or isinstance(pred_shape[channel_axis],int) and pred_shape[channel_axis]!=expected_channels: raise ModelLoadError('Model output shape does not match declared contract')
    if outputs[0].type!='tensor(float)': raise ModelLoadError('Prediction output must be float32')
    if required==2:
        proto=outputs[1]
        if proto.type!='tensor(float)' or len(proto.shape)!=4 or isinstance(proto.shape[0],int) and proto.shape[0]!=1 or isinstance(proto.shape[1],int) and proto.shape[1]!=config['mask_dim']: raise ModelLoadError('Prototype output does not match declared NCHW contract')
    return session
