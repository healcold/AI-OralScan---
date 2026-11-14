import numpy as np

def filter_candidates(boxes,scores,classes,extras,threshold):
    if not 0<=threshold<=1: raise ValueError('Invalid confidence threshold')
    valid=(scores>=threshold)&np.isfinite(boxes).all(axis=1)&(boxes[:,2]>boxes[:,0])&(boxes[:,3]>boxes[:,1])
    return boxes[valid],scores[valid],classes[valid],extras[valid]
