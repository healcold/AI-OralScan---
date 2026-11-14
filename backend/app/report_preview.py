"""Render a fixed camera preview from the stored mesh in a timed subprocess."""
import io
import sys
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

from .mesh_geometry import MAX_FACES, MAX_VERTICES, _preflight


def mesh_preview(data: bytes, file_format: str) -> bytes:
    cleaned, _ = _preflight(data, file_format)
    mesh = trimesh.load_mesh(io.BytesIO(cleaned), file_type=file_format, process=False, skip_materials=True)
    vertices, faces = np.asarray(mesh.vertices), np.asarray(mesh.faces)
    if not 0 < len(vertices) <= MAX_VERTICES or not 0 < len(faces) <= MAX_FACES:
        raise ValueError("Mesh is empty or exceeds preview limits")
    if not np.isfinite(vertices).all() or faces.min() < 0 or faces.max() >= len(vertices):
        raise ValueError("Invalid mesh data")
    forward = np.array([1, 1.2, 1.7])
    forward /= np.linalg.norm(forward)
    right = np.cross([0, 1, 0], forward)
    right /= np.linalg.norm(right)
    up = np.cross(forward, right)
    plane = vertices @ np.stack([right, up], axis=1)
    low, high = plane.min(axis=0), plane.max(axis=0)
    span = float(max(high - low))
    if not np.isfinite(span) or span <= 0:
        raise ValueError("Mesh has no visible extent")
    points = (plane - (low + high) / 2) * (382 / span)
    points = points * [1, -1] + [320, 220]
    depths = (vertices @ forward)[faces].mean(axis=1)
    light = np.abs(mesh.face_normals @ forward)
    image = Image.new("RGB", (640, 440), "#edf4f6")
    draw = ImageDraw.Draw(image)
    for index in np.argsort(depths):
        shade = float(np.clip(light[index], 0, 1))
        color = (int(68 + 106 * shade), int(116 + 92 * shade), int(135 + 85 * shade))
        draw.polygon([tuple(point) for point in points[faces[index]]], fill=color)
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


if __name__ == "__main__":
    sys.stdout.buffer.write(mesh_preview(Path(sys.argv[1]).read_bytes(), sys.argv[2]))
