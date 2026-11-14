import numpy as np

class OutputMismatch(ValueError): pass

def decode(output, *, layout: str, class_count: int, mask_dim: int = 0):
    """Only the declared raw xywh + class scores (+ mask coefficients) contract."""
    arr=np.asarray(output)
    if arr.ndim!=3 or arr.shape[0]!=1 or layout not in ('BNC','BCN') or not np.issubdtype(arr.dtype,np.number): raise OutputMismatch('Expected one batch of raw predictions in the declared layout')
    rows=arr[0].T if layout=='BCN' else arr[0]
    if rows.shape[1]!=4+class_count+mask_dim: raise OutputMismatch('Output channel count does not match declared labels and mask dimensions')
    if not np.isfinite(rows).all(): raise OutputMismatch('Output contains non-finite values')
    scores=rows[:,4:4+class_count]
    if np.any(scores<0) or np.any(scores>1): raise OutputMismatch('Declared class scores must be in [0, 1]')
    boxes=rows[:,:4].astype(np.float64,copy=True)
    xyxy=np.column_stack((boxes[:,0]-boxes[:,2]/2,boxes[:,1]-boxes[:,3]/2,boxes[:,0]+boxes[:,2]/2,boxes[:,1]+boxes[:,3]/2))
    if len(rows)==0:return xyxy,np.empty(0),np.empty(0,dtype=np.int64),rows[:,4+class_count:]
    classes=np.argmax(scores,axis=1).astype(np.int64); confidence=scores[np.arange(len(rows)),classes]
    return xyxy,confidence,classes,rows[:,4+class_count:]
