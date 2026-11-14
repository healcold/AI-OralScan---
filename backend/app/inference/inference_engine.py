from abc import ABC, abstractmethod
from pathlib import Path
from threading import RLock
import numpy as np
from .image_preprocessing import prepare
from .output_decoder import decode, OutputMismatch
from .confidence_filter import filter_candidates
from .nms import class_aware_nms
from .result_visualization import segmentation_mask

class BaseInferenceAdapter(ABC):
    is_demo = False
    @abstractmethod
    def infer(self, image_path: Path) -> list[dict]: ...

class YOLODetectionAdapter(BaseInferenceAdapter):
    def __init__(self, session, config): self.session=session;self.config=config
    def infer(self,image_path: Path):
        config=self.config;tensor,transform=prepare(image_path,config)
        outputs=self.session.run(None,{self.session.get_inputs()[0].name:tensor})
        expected=2 if config['task']=='segmentation' else 1
        if len(outputs)!=expected: raise OutputMismatch('Unexpected number of output tensors')
        if expected==2:
            proto=np.asarray(outputs[1])
            if proto.ndim!=4 or proto.shape[0]!=1 or proto.shape[1]!=config['mask_dim'] or min(proto.shape[2:])<1 or not np.isfinite(proto).all(): raise OutputMismatch('Segmentation prototype does not match contract')
        boxes,scores,classes,extras=decode(outputs[0],layout=config['output_layout'],class_count=len(config['labels']),mask_dim=config['mask_dim'])
        if len(boxes)>30000: raise OutputMismatch('Too many model candidates')
        boxes,scores,classes,extras=filter_candidates(boxes,scores,classes,extras,config['confidence_threshold'])
        iw,ih=transform.input_size; boxes[:,[0,2]]=np.clip(boxes[:,[0,2]],0,iw);boxes[:,[1,3]]=np.clip(boxes[:,[1,3]],0,ih)
        boxes,scores,classes,extras=filter_candidates(boxes,scores,classes,extras,config['confidence_threshold'])
        if len(boxes)>3000: raise OutputMismatch('Too many candidates after filtering')
        keep=class_aware_nms(boxes,scores,classes,config['nms_threshold'],config['max_detections']);findings=[]
        if expected==2 and len(keep)*transform.oriented_size[0]*transform.oriented_size[1]>40_000_000: raise OutputMismatch('Mask output exceeds processing limit')
        for i in keep:
            oriented=transform.input_box_to_oriented(boxes[i]);
            if oriented[2]<=oriented[0] or oriented[3]<=oriented[1]: continue
            item={'category':config['labels'][classes[i]],'confidence':float(scores[i]),'location':{'coordinate_space':'exif_oriented_image_pixels','bbox':oriented.tolist(),'image_size':list(transform.oriented_size),'raw_bbox':transform.oriented_box_to_raw(oriented)},'evidence':{'is_demo':False}}
            if config['task']=='segmentation': item['evidence']['mask_png']=segmentation_mask(extras[i],outputs[1],boxes[i],transform)
            findings.append(item)
        return findings

class YOLOSegmentationAdapter(YOLODetectionAdapter):
    def __init__(self, session, config):
        if config['task']!='segmentation' or config['mask_dim']<=0: raise ValueError('Segmentation contract required')
        super().__init__(session,config)

class RuntimeRegistry:
    def __init__(self): self._lock=RLock();self.model_id=None;self.adapter=None;self.name=None;self.version=None
    def snapshot(self):
        with self._lock: return self.adapter,self.model_id,self.name,self.version
    def clear(self):
        with self._lock: self.model_id=None;self.adapter=None;self.name=None;self.version=None
    def activate(self,record,session):
        adapter=YOLOSegmentationAdapter(session,record.config) if record.task=='segmentation' else YOLODetectionAdapter(session,record.config)
        with self._lock:
            self.model_id=record.model_id;self.adapter=adapter;self.name=record.name;self.version=record.version

runtime=RuntimeRegistry()
def get_runtime(): return runtime
