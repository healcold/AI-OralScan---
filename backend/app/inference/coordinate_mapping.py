from dataclasses import dataclass
import numpy as np
from ..image_processing import ImageTransform

@dataclass(frozen=True)
class Transform:
    raw_size: tuple[int,int]
    oriented_size: tuple[int,int]
    input_size: tuple[int,int]
    orientation: int
    resized_size: tuple[int,int]
    pad: tuple[int,int]

    def input_box_to_oriented(self, box):
        x1,y1,x2,y2=map(float,box); ow,oh=self.oriented_size; rw,rh=self.resized_size; px,py=self.pad
        out=np.array([(x1-px)*ow/rw,(y1-py)*oh/rh,(x2-px)*ow/rw,(y2-py)*oh/rh],dtype=float)
        out[[0,2]]=np.clip(out[[0,2]],0,ow);out[[1,3]]=np.clip(out[[1,3]],0,oh)
        return out

    def oriented_box_to_raw(self,box):
        x1,y1,x2,y2=box; ow,oh=self.oriented_size; iw,ih=self.input_size
        inverse=ImageTransform(self.raw_size,self.oriented_size,self.input_size,self.orientation)
        points=[inverse.input_to_raw(x*iw/ow,y*ih/oh) for x,y in ((x1,y1),(x2,y1),(x1,y2),(x2,y2))]
        return [min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)]
