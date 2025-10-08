from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Tuple

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class StructureBounds:
    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int

    @property
    def size(self) -> Tuple[int, int, int]:
        return (
            self.max_x - self.min_x + 1,
            self.max_y - self.min_y + 1,
            self.max_z - self.min_z + 1,
        )


@dataclass(frozen=True)
class PaletteEntry:
    namespaced_name: str
    properties: Mapping[str, str]

    @property
    def cache_key(self) -> str:
        if not self.properties:
            return self.namespaced_name
        props = ",".join(
            f"{key}={value}" for key, value in sorted(self.properties.items())
        )
        return f"{self.namespaced_name}[{props}]"

    @property
    def is_air(self) -> bool:
        name = self.namespaced_name
        return name.endswith(":air") or name in {"air", "minecraft:air"}

    @property
    def is_transparent(self) -> bool:
        if self.is_air:
            return True
        name = self.namespaced_name
        transparent_prefixes = (
            "minecraft:glass",
            "minecraft:ice",
            "minecraft:water",
            "minecraft:kelp",
            "minecraft:torch",
        )
        if any(name.startswith(prefix) for prefix in transparent_prefixes):
            return True
        return name in {
            "minecraft:barrier",
            "minecraft:light",
            "minecraft:cave_air",
            "minecraft:void_air",
        }


@dataclass
class StructureData:
    bounds: StructureBounds
    palette: List[PaletteEntry]
    voxels: np.ndarray  # np.int32 array with palette indices


@dataclass
class BakedFace:
    positions: np.ndarray  # shape (4, 3)
    uvs: np.ndarray  # shape (4, 2)
    normal: Tuple[float, float, float]
    texture_key: str

    def offset(self, dx: float, dy: float, dz: float) -> "BakedFace":
        return BakedFace(
            positions=self.positions + np.array([[dx, dy, dz]], dtype=np.float32),
            uvs=self.uvs.copy(),
            normal=self.normal,
            texture_key=self.texture_key,
        )


@dataclass
class MeshBuffers:
    positions: np.ndarray  # float32
    normals: np.ndarray  # float32
    uvs: np.ndarray  # float32
    indices: np.ndarray  # uint32


@dataclass
class AtlasResult:
    image: Image.Image
    uv_rects: Dict[str, Tuple[float, float, float, float]]


@dataclass
class GLBResult:
    glb_bytes: bytes
    center: Tuple[float, float, float]
    size: Tuple[float, float, float]
