import numpy as np

def class_aware_nms(boxes,scores,classes,iou_threshold,max_detections):
    if not 0<=iou_threshold<=1 or max_detections<1: raise ValueError('Invalid NMS configuration')
    order=np.argsort(-scores,kind='stable').astype(np.int64);keep=[]
    while order.size and len(keep)<max_detections:
        i=int(order[0]);keep.append(i);other=order[1:]
        if not len(other):break
        tl=np.maximum(boxes[i,:2],boxes[other,:2]);br=np.minimum(boxes[i,2:],boxes[other,2:]);wh=np.maximum(br-tl,0);inter=wh[:,0]*wh[:,1]
        area=(boxes[:,2]-boxes[:,0])*(boxes[:,3]-boxes[:,1]);union=area[i]+area[other]-inter
        iou=np.divide(inter,union,out=np.zeros_like(inter),where=union>0)
        order=other[(classes[other]!=classes[i])|(iou<=iou_threshold)]
    return np.asarray(keep,dtype=np.int64)
