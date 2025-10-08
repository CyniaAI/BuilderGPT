from __future__ import annotations

from typing import List, Sequence

import numpy as np

from .model_baker import BakedBlock, ModelBaker
from .types import BakedFace, MeshBuffers, PaletteEntry, StructureData

_DIRECTIONS = {
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "west": (-1, 0, 0),
    "east": (1, 0, 0),
    "down": (0, -1, 0),
    "up": (0, 1, 0),
}


def culled_faces(struct: StructureData, baker: ModelBaker) -> List[BakedFace]:
    voxels = struct.voxels
    size_x, size_y, size_z = voxels.shape
    faces: List[BakedFace] = []

    def palette_entry(index: int) -> PaletteEntry:
        if index < 0 or index >= len(struct.palette):
            return PaletteEntry("minecraft:air", {})
        return struct.palette[index]

    for x in range(size_x):
        for y in range(size_y):
            for z in range(size_z):
                palette_index = int(voxels[x, y, z])
                entry = palette_entry(palette_index)
                if entry.is_air:
                    continue
                baked_block: BakedBlock = baker.bake_blockstate(entry)
                for face_name, offset in _DIRECTIONS.items():
                    dx, dy, dz = offset
                    nx, ny, nz = x + dx, y + dy, z + dz
                    neighbor: PaletteEntry
                    if 0 <= nx < size_x and 0 <= ny < size_y and 0 <= nz < size_z:
                        neighbor_index = int(voxels[nx, ny, nz])
                        neighbor = palette_entry(neighbor_index)
                        if not neighbor.is_transparent:
                            continue
                    else:
                        neighbor = PaletteEntry("minecraft:air", {})
                    baked_face = baked_block.faces.get(face_name)
                    if baked_face is None:
                        continue
                    faces.append(baked_face.offset(x, y, z))
    return faces


def build_mesh(faces: Sequence[BakedFace], atlas_uv: dict[str, tuple[float, float, float, float]]) -> MeshBuffers:
    if not faces:
        return MeshBuffers(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
        )

    positions: List[np.ndarray] = []
    normals: List[np.ndarray] = []
    uvs: List[np.ndarray] = []
    indices: List[int] = []

    vertex_offset = 0
    quad_indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)

    for face in faces:
        rect = atlas_uv.get(face.texture_key)
        if rect is None:
            # Skip faces without texture information
            continue
        u0, v0, u1, v1 = rect
        uv = face.uvs.copy()
        uv[:, 0] = u0 + (u1 - u0) * uv[:, 0]
        uv[:, 1] = v0 + (v1 - v0) * uv[:, 1]

        positions.append(face.positions.astype(np.float32))
        normals.append(np.tile(np.array(face.normal, dtype=np.float32), (4, 1)))
        uvs.append(uv.astype(np.float32))

        indices.extend((quad_indices + vertex_offset).tolist())
        vertex_offset += 4

    if not positions:
        return MeshBuffers(
            positions=np.zeros((0, 3), dtype=np.float32),
            normals=np.zeros((0, 3), dtype=np.float32),
            uvs=np.zeros((0, 2), dtype=np.float32),
            indices=np.zeros((0,), dtype=np.uint32),
        )

    return MeshBuffers(
        positions=np.concatenate(positions, axis=0),
        normals=np.concatenate(normals, axis=0),
        uvs=np.concatenate(uvs, axis=0),
        indices=np.array(indices, dtype=np.uint32),
    )
