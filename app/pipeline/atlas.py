from __future__ import annotations

import math
from typing import Dict, Mapping

import numpy as np
from PIL import Image

from .types import AtlasResult


def build_atlas(
    images: Mapping[str, np.ndarray],
    tile_size: int = 32,
    padding: int = 6,
) -> AtlasResult:
    if not images:
        blank = Image.new("RGBA", (tile_size, tile_size), (255, 255, 255, 255))
        return AtlasResult(blank, {"default": (0.0, 0.0, 1.0, 1.0)})

    keys = list(images.keys())
    count = len(keys)
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    # Each texture tile gains mirrored padding to avoid bleeding when sampling.
    stride = tile_size + padding * 2
    width = columns * stride
    height = rows * stride
    atlas = Image.new("RGBA", (width, height))
    uv_rects: Dict[str, tuple[float, float, float, float]] = {}

    for idx, key in enumerate(keys):
        img = images[key]
        if isinstance(img, Image.Image):
            tile = img
        else:
            tile = Image.fromarray(np.asarray(img, dtype=np.uint8), mode="RGBA")
        tile = tile.resize((tile_size, tile_size), resample=Image.NEAREST)
        if padding > 0:
            array = np.asarray(tile, dtype=np.uint8)
            padded = np.pad(
                array,
                ((padding, padding), (padding, padding), (0, 0)),
                mode="edge",
            )
            tile = Image.fromarray(padded, mode="RGBA")
        x = (idx % columns) * stride
        y = (idx // columns) * stride
        atlas.paste(tile, (x, y))
        inner_left = x + padding
        inner_top = y + padding
        inner_right = inner_left + tile_size
        inner_bottom = inner_top + tile_size
        half_px = 0.5
        u0 = (inner_left + half_px) / width
        v0 = (inner_top + half_px) / height
        u1 = (inner_right - half_px) / width
        v1 = (inner_bottom - half_px) / height
        uv_rects[key] = (u0, v0, u1, v1)

    return AtlasResult(atlas, uv_rects)
