"""Image preparation without modifying source files; caller supplies the model contract."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps

@dataclass(frozen=True)
class ImageTransform:
    raw_size: tuple[int, int]
    oriented_size: tuple[int, int]
    input_size: tuple[int, int]
    orientation: int

    def input_to_raw(self, x: float, y: float) -> tuple[float, float]:
        """Map continuous pixel-edge coordinates through resize and inverse EXIF orientation."""
        ow, oh = self.oriented_size
        w, h = self.raw_size
        x, y = x * ow / self.input_size[0], y * oh / self.input_size[1]
        return {1: lambda: (x,y), 2: lambda: (w-x,y), 3: lambda: (w-x,h-y), 4: lambda: (x,h-y),
                5: lambda: (y,x), 6: lambda: (y,h-x), 7: lambda: (w-y,h-x), 8: lambda: (w-y,x)}[self.orientation]()

def read_metadata(path: Path) -> dict:
    with Image.open(path) as image:
        width, height = image.size
        orientation = image.getexif().get(274, 1)
        orientation = orientation if orientation in range(1, 9) else 1
    with Image.open(path) as image:
        image.verify()
    if width < 1 or height < 1 or width * height > 40_000_000:
        raise ValueError('Image dimensions exceed the supported limit')
    return {'width': width, 'height': height, 'orientation': orientation,
            'oriented_width': height if orientation >= 5 else width,
            'oriented_height': width if orientation >= 5 else height}

def prepare_image(path: Path, input_size: tuple[int, int], *, color_order: str, dtype: str, scale: float) -> tuple[np.ndarray, ImageTransform]:
    """Direct resize, NCHW; explicit color, dtype and scale must match the real model."""
    if min(input_size) <= 0 or color_order not in ('RGB', 'BGR') or dtype not in ('uint8', 'float32'):
        raise ValueError('Invalid preprocessing configuration')
    if dtype == 'uint8' and scale != 1:
        raise ValueError('Scaled uint8 output is not supported')
    meta = read_metadata(path)
    with Image.open(path) as original:
        image = ImageOps.exif_transpose(original).convert('RGB')
        image = image.resize(input_size, Image.Resampling.BILINEAR)
        arr = np.asarray(image)
    if color_order == 'BGR': arr = arr[..., ::-1]
    arr = arr.astype(dtype)
    if dtype == 'float32': arr *= scale
    tensor = np.ascontiguousarray(arr.transpose(2, 0, 1)[None, ...])
    return tensor, ImageTransform((meta['width'], meta['height']), (meta['oriented_width'], meta['oriented_height']), input_size, meta['orientation'])
