from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, Mapping

import numpy as np

from .types import BakedFace, PaletteEntry

try:  # pragma: no cover - optional dependency placeholder
    from minecraft_model_reader import ModelLoader  # type: ignore
except Exception:  # pragma: no cover - library not available
    ModelLoader = None  # type: ignore


@dataclass(frozen=True)
class BakedBlock:
    faces: Mapping[str, BakedFace]
    texture_key: str


class ModelBaker:
    """Fallback-friendly block baker.

    The implementation uses simple unit-cube meshes to ensure the preview works
    even when the optional minecraft-model-reader dependency is missing. When
    the library is available the class can be extended to bake accurate models.
    """

    def __init__(self, resource_pack_path: str | None = None) -> None:
        self._resource_pack_path = resource_pack_path
        self._cache: Dict[str, BakedBlock] = {}
        self._texture_cache: Dict[str, np.ndarray] = {}
        self._model_loader = None
        if ModelLoader is not None and resource_pack_path:
            try:
                self._model_loader = ModelLoader(resource_pack_path)
            except Exception:
                self._model_loader = None

    @property
    def textures(self) -> Mapping[str, np.ndarray]:
        return self._texture_cache

    def bake_blockstate(self, entry: PaletteEntry) -> BakedBlock:
        cache_key = entry.cache_key
        if cache_key in self._cache:
            return self._cache[cache_key]

        baked = self._bake_with_reader(entry)
        if baked is None:
            baked = self._bake_fallback(entry)
        self._cache[cache_key] = baked
        return baked

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _bake_with_reader(self, entry: PaletteEntry) -> BakedBlock | None:
        if self._model_loader is None:
            return None
        # Placeholder: minecraft-model-reader integration would go here.
        # We return None so that the fallback path handles rendering.
        return None

    def _bake_fallback(self, entry: PaletteEntry) -> BakedBlock:
        texture_key = entry.cache_key
        if texture_key not in self._texture_cache:
            color = self._color_from_key(texture_key)
            tile = np.full((16, 16, 4), color, dtype=np.uint8)
            self._texture_cache[texture_key] = tile

        cube_faces = self._unit_cube_faces(texture_key)
        return BakedBlock(cube_faces, texture_key)

    @staticmethod
    def _color_from_key(key: str) -> np.ndarray:
        digest = hashlib.sha1(key.encode("utf-8")).digest()
        r, g, b = digest[0], digest[1], digest[2]
        # Mix with a lighter base so even dark blocks remain visible.
        r = (r + 64) % 256
        g = (g + 64) % 256
        b = (b + 64) % 256
        return np.array([r, g, b, 255], dtype=np.uint8)

    @staticmethod
    def _unit_cube_faces(texture_key: str) -> Dict[str, BakedFace]:
        faces: Dict[str, BakedFace] = {}
        # Define vertices for each face (quad) in counter-clockwise order.
        face_definitions = {
            "north": (np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float32), (0.0, 0.0, -1.0)),
            "south": (np.array([[1, 0, 1], [0, 0, 1], [0, 1, 1], [1, 1, 1]], dtype=np.float32), (0.0, 0.0, 1.0)),
            "west": (np.array([[0, 0, 1], [0, 0, 0], [0, 1, 0], [0, 1, 1]], dtype=np.float32), (-1.0, 0.0, 0.0)),
            "east": (np.array([[1, 0, 0], [1, 0, 1], [1, 1, 1], [1, 1, 0]], dtype=np.float32), (1.0, 0.0, 0.0)),
            "down": (np.array([[0, 0, 1], [1, 0, 1], [1, 0, 0], [0, 0, 0]], dtype=np.float32), (0.0, -1.0, 0.0)),
            "up": (np.array([[0, 1, 0], [1, 1, 0], [1, 1, 1], [0, 1, 1]], dtype=np.float32), (0.0, 1.0, 0.0)),
        }
        uvs = np.array([[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]], dtype=np.float32)
        for name, (positions, normal) in face_definitions.items():
            faces[name] = BakedFace(
                positions=positions,
                uvs=uvs.copy(),
                normal=normal,
                texture_key=texture_key,
            )
        return faces
