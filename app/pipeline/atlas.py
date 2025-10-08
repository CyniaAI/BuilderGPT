from __future__ import annotations

import math
from typing import Dict, Mapping

import numpy as np
from PIL import Image

from .types import AtlasResult


def build_atlas(images: Mapping[str, np.ndarray], tile_size: int = 32) -> AtlasResult:
    if not images:
        blank = Image.new("RGBA", (tile_size, tile_size), (255, 255, 255, 255))
        return AtlasResult(blank, {"default": (0.0, 0.0, 1.0, 1.0)})

    keys = list(images.keys())
    count = len(keys)
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    width = columns * tile_size
    height = rows * tile_size
    atlas = Image.new("RGBA", (width, height))
    uv_rects: Dict[str, tuple[float, float, float, float]] = {}

    for idx, key in enumerate(keys):
        img = images[key]
        if isinstance(img, Image.Image):
            tile = img
        else:
            tile = Image.fromarray(np.asarray(img, dtype=np.uint8), mode="RGBA")
        tile = tile.resize((tile_size, tile_size))
        x = (idx % columns) * tile_size
        y = (idx // columns) * tile_size
        atlas.paste(tile, (x, y))
        u0 = x / width
        v0 = y / height
        u1 = (x + tile_size) / width
        v1 = (y + tile_size) / height
        uv_rects[key] = (u0, v0, u1, v1)

    return AtlasResult(atlas, uv_rects)
