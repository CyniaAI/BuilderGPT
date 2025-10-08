from __future__ import annotations

import io
import json
import struct
from typing import Tuple

import numpy as np

from .types import AtlasResult, GLBResult, MeshBuffers

GLTF_HEADER_MAGIC = 0x46546C67
GLTF_VERSION = 2


def _append_with_padding(target: bytearray, data: bytes) -> Tuple[int, int]:
    offset = len(target)
    length = len(data)
    target.extend(data)
    padding = (4 - (length % 4)) % 4
    if padding:
        target.extend(b"\x00" * padding)
    return offset, length


def mesh_to_glb(mesh: MeshBuffers, atlas: AtlasResult) -> GLBResult:
    if mesh.positions.size == 0:
        empty = {
            "asset": {"version": "2.0", "generator": "BuilderGPT Preview"},
            "scenes": [{"nodes": [0]}],
            "scene": 0,
            "nodes": [{"mesh": 0}],
            "meshes": [{"primitives": []}],
            "buffers": [{"byteLength": 0}],
            "bufferViews": [],
            "accessors": [],
            "materials": [],
        }
        json_bytes = json.dumps(empty).encode("utf-8")
        json_padding = (4 - (len(json_bytes) % 4)) % 4
        json_bytes += b" " * json_padding
        header = struct.pack("<III", GLTF_HEADER_MAGIC, GLTF_VERSION, 12 + 8 + len(json_bytes))
        json_chunk_header = struct.pack("<II", len(json_bytes), 0x4E4F534A)
        return GLBResult(header + json_chunk_header + json_bytes, (0, 0, 0), (0, 0, 0))

    positions = mesh.positions.astype(np.float32)
    normals = mesh.normals.astype(np.float32)
    uvs = mesh.uvs.astype(np.float32)
    indices = mesh.indices.astype(np.uint32)

    image_bytes = io.BytesIO()
    atlas.image.save(image_bytes, format="PNG")
    atlas_bytes = image_bytes.getvalue()

    bin_chunk = bytearray()
    buffer_views = []
    accessors = []

    pos_offset, pos_length = _append_with_padding(bin_chunk, positions.tobytes())
    buffer_views.append({
        "buffer": 0,
        "byteOffset": pos_offset,
        "byteLength": pos_length,
        "target": 34962,
    })
    pos_min = positions.min(axis=0).tolist()
    pos_max = positions.max(axis=0).tolist()
    accessors.append({
        "bufferView": len(buffer_views) - 1,
        "componentType": 5126,
        "count": len(positions),
        "type": "VEC3",
        "min": pos_min,
        "max": pos_max,
    })
    normal_offset, normal_length = _append_with_padding(bin_chunk, normals.tobytes())
    buffer_views.append({
        "buffer": 0,
        "byteOffset": normal_offset,
        "byteLength": normal_length,
        "target": 34962,
    })
    accessors.append({
        "bufferView": len(buffer_views) - 1,
        "componentType": 5126,
        "count": len(normals),
        "type": "VEC3",
    })
    uv_offset, uv_length = _append_with_padding(bin_chunk, uvs.tobytes())
    buffer_views.append({
        "buffer": 0,
        "byteOffset": uv_offset,
        "byteLength": uv_length,
        "target": 34962,
    })
    accessors.append({
        "bufferView": len(buffer_views) - 1,
        "componentType": 5126,
        "count": len(uvs),
        "type": "VEC2",
    })
    idx_offset, idx_length = _append_with_padding(bin_chunk, indices.tobytes())
    buffer_views.append({
        "buffer": 0,
        "byteOffset": idx_offset,
        "byteLength": idx_length,
        "target": 34963,
    })
    accessors.append({
        "bufferView": len(buffer_views) - 1,
        "componentType": 5125,
        "count": len(indices),
        "type": "SCALAR",
    })
    image_offset, image_length = _append_with_padding(bin_chunk, atlas_bytes)
    buffer_views.append({
        "buffer": 0,
        "byteOffset": image_offset,
        "byteLength": image_length,
    })

    gltf = {
        "asset": {"version": "2.0", "generator": "BuilderGPT Preview"},
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "nodes": [{"mesh": 0}],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {
                            "POSITION": 0,
                            "NORMAL": 1,
                            "TEXCOORD_0": 2,
                        },
                        "indices": 3,
                        "material": 0,
                    }
                ]
            }
        ],
        "buffers": [{"byteLength": len(bin_chunk)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "materials": [
            {
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": 0},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 1.0,
                },
            }
        ],
        "samplers": [
            {
                "magFilter": 9729,
                "minFilter": 9987,
                "wrapS": 10497,
                "wrapT": 10497,
            }
        ],
        "images": [
            {
                "bufferView": len(buffer_views) - 1,
                "mimeType": "image/png",
            }
        ],
        "textures": [{"sampler": 0, "source": 0}],
    }

    json_bytes = json.dumps(gltf).encode("utf-8")
    json_padding = (4 - (len(json_bytes) % 4)) % 4
    if json_padding:
        json_bytes += b" " * json_padding

    total_length = 12 + 8 + len(json_bytes) + 8 + len(bin_chunk)
    header = struct.pack("<III", GLTF_HEADER_MAGIC, GLTF_VERSION, total_length)
    json_chunk_header = struct.pack("<II", len(json_bytes), 0x4E4F534A)
    bin_chunk_header = struct.pack("<II", len(bin_chunk), 0x004E4942)
    glb_bytes = header + json_chunk_header + json_bytes + bin_chunk_header + bytes(bin_chunk)

    pos_min_arr = positions.min(axis=0)
    pos_max_arr = positions.max(axis=0)
    center = tuple(((pos_min_arr + pos_max_arr) / 2.0).tolist())
    size = tuple((pos_max_arr - pos_min_arr).tolist())

    return GLBResult(glb_bytes, center, size)
