from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional

import numpy as np
from PIL import Image

from .types import BakedFace, PaletteEntry

try:  # pragma: no cover - optional dependency placeholder
    from minecraft_model_reader import ModelLoader  # type: ignore
except Exception:  # pragma: no cover - library not available
    ModelLoader = None  # type: ignore


@dataclass(frozen=True)
class BakedBlock:
    faces: Mapping[str, BakedFace]
    texture_key: str


_FACE_ORDER = ("north", "south", "east", "west", "up", "down")
_HORIZONTAL_FACES = ("north", "south", "east", "west")
_SPECIAL_FACE_RULES: Dict[str, Dict[str, list[str]]] = {
    # Dirt-like blocks with distinct top/bottom.
    "grass_block": {
        "top": ["grass_block_top"],
        "side": ["grass_block_side"],
        "bottom": ["dirt"],
    },
    "podzol": {
        "top": ["podzol_top"],
        "side": ["podzol_side"],
        "bottom": ["dirt"],
    },
    "mycelium": {
        "top": ["mycelium_top"],
        "side": ["mycelium_side"],
        "bottom": ["dirt"],
    },
    "dirt_path": {
        "top": ["dirt_path_top"],
        "side": ["dirt_path_side"],
        "bottom": ["dirt"],
    },
    "grass_path": {
        "top": ["dirt_path_top", "grass_path_top"],
        "side": ["dirt_path_side", "grass_path_side"],
        "bottom": ["dirt"],
    },
    "crimson_nylium": {
        "top": ["crimson_nylium"],
        "side": ["crimson_nylium_side"],
        "bottom": ["netherrack"],
    },
    "warped_nylium": {
        "top": ["warped_nylium"],
        "side": ["warped_nylium_side"],
        "bottom": ["netherrack"],
    },
    "snow_block": {
        "top": ["snow"],
        "side": ["snow"],
        "bottom": ["snow"],
    },
}


class _ResourcePackSource:
    """Thin wrapper around either a directory or .zip file resource pack."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._is_dir = path.is_dir()
        self._zip: zipfile.ZipFile | None = None
        if not self._is_dir:
            self._zip = zipfile.ZipFile(str(path))

    def read_bytes(self, relative_path: str) -> Optional[bytes]:
        normalized = relative_path.replace("\\", "/")
        if self._is_dir:
            file_path = self._path / Path(relative_path)
            if file_path.exists():
                try:
                    return file_path.read_bytes()
                except OSError:
                    return None
            return None
        if self._zip is None:
            return None
        try:
            with self._zip.open(normalized) as fp:
                return fp.read()
        except KeyError:
            return None


class ResourcePackTextures:
    """Utility that fetches textures from user supplied or bundled packs."""

    def __init__(self, primary_path: str | None) -> None:
        self._sources: list[_ResourcePackSource] = []
        self._cache: Dict[str, np.ndarray] = {}
        self._missing: set[str] = set()

        seen: set[Path] = set()
        if primary_path:
            primary = Path(primary_path)
            if primary.exists():
                self._sources.append(_ResourcePackSource(primary))
                seen.add(primary.resolve())

        fallback = self._discover_fallback(seen)
        if fallback is not None:
            self._sources.append(_ResourcePackSource(fallback))

    @staticmethod
    def _discover_fallback(skip: set[Path]) -> Optional[Path]:
        """Look for a bundled pack inside public/ as a safety net."""
        try:
            repo_root = Path(__file__).resolve().parents[2]
        except Exception:
            return None

        public_dir = repo_root / "public"
        if not public_dir.exists():
            return None

        zip_candidates = sorted(
            (
                path
                for path in public_dir.glob("*.zip")
                if path.resolve() not in skip
            ),
            key=lambda p: (0 if "faithful" in p.stem.lower() else 1, p.name.lower()),
        )
        return zip_candidates[0] if zip_candidates else None

    @property
    def has_sources(self) -> bool:
        return bool(self._sources)

    def load_texture(self, texture_key: str) -> Optional[np.ndarray]:
        if texture_key in self._cache:
            return self._cache[texture_key]
        if texture_key in self._missing or not self._sources:
            return None

        namespace, path = self._split_key(texture_key)

        rel_candidates = self._candidate_paths(namespace, path)
        for rel_path in rel_candidates:
            for source in self._sources:
                data = source.read_bytes(rel_path)
                if data is None:
                    continue
                try:
                    with Image.open(io.BytesIO(data)) as img:
                        rgba = np.asarray(img.convert("RGBA"), dtype=np.uint8)
                except Exception:
                    continue
                self._cache[texture_key] = rgba
                return rgba

        self._missing.add(texture_key)
        return None

    @staticmethod
    def _split_key(texture_key: str) -> tuple[str, str]:
        if ":" in texture_key:
            namespace, path = texture_key.split(":", 1)
        else:
            namespace, path = "minecraft", texture_key
        path = path.strip().lstrip("/").replace("\\", "/")
        if path.startswith("textures/"):
            path = path[len("textures/") :]
        if path.endswith(".png"):
            path = path[:-4]
        return namespace, path

    @staticmethod
    def _candidate_paths(namespace: str, path: str) -> list[str]:
        rel_paths = []
        primary = f"assets/{namespace}/textures/{path}.png"
        rel_paths.append(primary)
        alternative = f"assets/{namespace}/{path}.png"
        if alternative != primary:
            rel_paths.append(alternative)
        return rel_paths


class ModelBaker:
    """Fallback-friendly block baker.

    The implementation uses simple unit-cube meshes to ensure the preview works
    even when the optional minecraft-model-reader dependency is missing. When
    the library is available the class can be extended to bake accurate models.
    """

    def __init__(self, resource_pack_path: str | None = None) -> None:
        self._cache: Dict[str, BakedBlock] = {}
        self._texture_cache: Dict[str, np.ndarray] = {}
        self._texture_source = ResourcePackTextures(resource_pack_path)
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
        textured_faces = self._cube_face_textures(entry)
        if textured_faces:
            primary_key = (
                textured_faces.get("north")
                or textured_faces.get("east")
                or textured_faces.get("west")
                or textured_faces.get("south")
                or textured_faces.get("up")
                or textured_faces.get("down")
            )
            if primary_key:
                cube_faces = self._unit_cube_faces(primary_key, textured_faces)
                return BakedBlock(cube_faces, primary_key)
        return self._hashed_color_cube(entry)

    def _hashed_color_cube(self, entry: PaletteEntry) -> BakedBlock:
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
    def _unit_cube_faces(
        texture_key: str, face_overrides: Optional[Mapping[str, str]] = None
    ) -> Dict[str, BakedFace]:
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
            key = texture_key
            if face_overrides:
                key = face_overrides.get(name, face_overrides.get("side", texture_key))
            faces[name] = BakedFace(
                positions=positions,
                uvs=uvs.copy(),
                normal=normal,
                texture_key=key,
            )
        return faces

    # ------------------------------------------------------------------
    # Texture helpers
    # ------------------------------------------------------------------
    def _cube_face_textures(self, entry: PaletteEntry) -> Optional[Dict[str, str]]:
        if not self._texture_source.has_sources:
            return None

        base_name = entry.namespaced_name.split(":")[-1]
        faces: Dict[str, str] = {}

        for face in _FACE_ORDER:
            candidates = self._face_candidates(base_name, face)
            for candidate in candidates:
                texture_key = self._normalize_texture_key(candidate)
                if self._ensure_texture_cached(texture_key):
                    faces[face] = texture_key
                    break

        if not faces:
            return None

        fallback = next(faces[face] for face in _FACE_ORDER if face in faces)
        for face in _FACE_ORDER:
            faces.setdefault(face, fallback)

        axis = entry.properties.get("axis")
        if axis in {"x", "y", "z"}:
            top_key = faces["up"]
            bottom_key = faces["down"]
            side_key = faces["north"]
            if axis == "x":
                faces["east"] = top_key
                faces["west"] = top_key
                faces["up"] = side_key
                faces["down"] = side_key
            elif axis == "z":
                faces["north"] = top_key
                faces["south"] = top_key
                faces["up"] = side_key
                faces["down"] = side_key
            else:  # axis == "y"
                faces["up"] = top_key
                faces["down"] = bottom_key

        return faces

    def _face_candidates(self, base_name: str, face: str) -> list[str]:
        normalized = base_name.replace("minecraft:", "")
        rules = _SPECIAL_FACE_RULES.get(normalized)
        if rules:
            if face == "up" and "top" in rules:
                return rules["top"]
            if face == "down" and "bottom" in rules:
                return rules["bottom"]
            if face in _HORIZONTAL_FACES and "side" in rules:
                return rules["side"]

        if face == "up":
            return [
                f"{normalized}_top",
                f"{normalized}_up",
                f"{normalized}_upper",
                f"{normalized}_end",
                f"{normalized}_face",
                normalized,
            ]
        if face == "down":
            return [
                f"{normalized}_bottom",
                f"{normalized}_down",
                f"{normalized}_lower",
                f"{normalized}_end",
                f"{normalized}_face",
                normalized,
            ]
        # Horizontal faces
        return [
            f"{normalized}_side",
            f"{normalized}_side0",
            f"{normalized}_side1",
            f"{normalized}_front",
            normalized,
        ]

    @staticmethod
    def _normalize_texture_key(name: str) -> str:
        name = name.strip()
        if not name:
            return "minecraft:block/missingno"
        if name.startswith("#"):
            name = name[1:]
        namespace = "minecraft"
        path = name
        if ":" in name:
            namespace, path = name.split(":", 1)
        path = path.strip().lstrip("/").replace("\\", "/")
        if path.endswith(".png"):
            path = path[:-4]
        if path.startswith("textures/"):
            path = path[len("textures/") :]
        if not path.startswith("block/") and not path.startswith("item/"):
            path = f"block/{path}"
        return f"{namespace}:{path}"

    def _ensure_texture_cached(self, texture_key: str) -> bool:
        if texture_key in self._texture_cache:
            return True
        texture = self._texture_source.load_texture(texture_key)
        if texture is None:
            return False
        self._texture_cache[texture_key] = texture
        return True
