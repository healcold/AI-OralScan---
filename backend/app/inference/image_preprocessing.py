from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from ..image_processing import read_metadata
from .coordinate_mapping import Transform

def prepare(path: Path, config: dict):
    width,height=config['input_size']; mode=config['resize_mode']; dtype=config['dtype']; scale=config['scale']; order=config['color_order']
    if mode not in ('resize','letterbox') or order not in ('RGB','BGR') or dtype not in ('float32','uint8') or not np.isfinite(scale) or scale<=0 or dtype=='uint8' and scale!=1:
        raise ValueError('Unsupported preprocessing configuration')
    meta=read_metadata(path)
    with Image.open(path) as original:
        image=ImageOps.exif_transpose(original).convert('RGB')
        ow,oh=image.size
        if mode=='letterbox':
            ratio=min(width/ow,height/oh);rw=max(1,min(width,round(ow*ratio)));rh=max(1,min(height,round(oh*ratio)))
            px=(width-rw)//2;py=(height-rh)//2
            canvas=Image.new('RGB',(width,height),(config['pad_value'],)*3);canvas.paste(image.resize((rw,rh),Image.Resampling.BILINEAR),(px,py));image=canvas
        else:
            rw,rh=width,height;px=py=0;image=image.resize((width,height),Image.Resampling.BILINEAR)
        arr=np.asarray(image)
    if order=='BGR': arr=arr[...,::-1]
    arr=arr.astype(dtype)
    if dtype=='float32': arr*=scale
    return np.ascontiguousarray(arr.transpose(2,0,1)[None]),Transform((meta['width'],meta['height']),(ow,oh),(width,height),meta['orientation'],(rw,rh),(px,py))
