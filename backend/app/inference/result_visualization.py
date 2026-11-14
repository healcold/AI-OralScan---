import base64
import io
import numpy as np
from PIL import Image
from .output_decoder import OutputMismatch

def segmentation_mask(coeff, prototype, box, transform):
    proto=np.asarray(prototype)
    if proto.ndim!=4 or proto.shape[0]!=1 or proto.shape[1]!=len(coeff) or not np.isfinite(proto).all(): raise OutputMismatch('Segmentation prototype shape or values do not match the declared contract')
    if transform.oriented_size[0]*transform.oriented_size[1]>10_000_000: raise OutputMismatch('Image is too large for mask visualization')
    logits=np.clip(np.asarray(coeff,dtype=np.float64)@proto[0].reshape(len(coeff),-1),-50,50).reshape(proto.shape[2:])
    prob=1/(1+np.exp(-logits));iw,ih=transform.input_size
    mask=np.asarray(Image.fromarray(prob.astype(np.float32)).resize((iw,ih),Image.Resampling.BILINEAR)).copy()
    x1,y1,x2,y2=box;xx=np.arange(iw)+.5;yy=np.arange(ih)+.5
    mask[(yy[:,None]<y1)|(yy[:,None]>=y2)|(xx[None,:]<x1)|(xx[None,:]>=x2)]=0
    px,py=transform.pad;rw,rh=transform.resized_size;mask=mask[py:py+rh,px:px+rw]
    mask=np.asarray(Image.fromarray(mask).resize(transform.oriented_size,Image.Resampling.BILINEAR))>.5
    out=io.BytesIO();Image.fromarray(mask.astype('uint8')*255).save(out,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode('ascii')
