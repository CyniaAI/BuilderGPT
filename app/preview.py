from __future__ import annotations

import base64
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from typing import Dict, Optional

from .pipeline.atlas import build_atlas
from .pipeline.gltf_builder import mesh_to_glb
from .pipeline.loader import load_structure
from .pipeline.mesher import build_mesh, culled_faces
from .pipeline.model_baker import ModelBaker
from .pipeline.translate import normalize_palette


@dataclass(frozen=True)
class PreviewOptions:
    sun_azimuth: float
    sun_elevation: float
    max_dpr: float
    render_scale: float
    max_draw_distance: float
    show_grid: bool
    wireframe: bool
    ambient_occlusion: bool

    def to_serializable(self) -> Dict[str, float | bool]:
        data = asdict(self)
        return data


@dataclass
class PreviewPayload:
    base64_glb: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]

    def to_viewer_params(self, options: PreviewOptions) -> Dict[str, object]:
        params: Dict[str, object] = {
            "base64_glb": f"data:model/gltf-binary;base64,{self.base64_glb}",
            "sunAz": options.sun_azimuth,
            "sunEl": options.sun_elevation,
            "maxDPR": options.max_dpr,
            "renderScale": options.render_scale,
            "maxDistance": options.max_draw_distance,
            "showGrid": options.show_grid,
            "wireframe": options.wireframe,
            "ambientOcclusion": options.ambient_occlusion,
            "bounds": {
                "center": self.center,
                "size": self.size,
            },
        }
        return params


def build_preview(
    schem_bytes: bytes,
    resource_pack_bytes: Optional[bytes],
    options: PreviewOptions,
) -> PreviewPayload:
    # Guardrail: avoid extremely large uploads causing long CPU-bound stalls
    # 50 MB is generous for a .schem file; adjust as needed
    MAX_SCHEM_BYTES = 50 * 1024 * 1024
    if len(schem_bytes) > MAX_SCHEM_BYTES:
        raise ValueError("Schematic too large to preview (over 50 MB)")
    with tempfile.TemporaryDirectory() as tmpdir:
        schem_path = os.path.join(tmpdir, "structure.schem")
        with open(schem_path, "wb") as fp:
            fp.write(schem_bytes)

        resource_pack_path: Optional[str] = None
        if resource_pack_bytes:
            resource_pack_path = os.path.join(tmpdir, "resource_pack.zip")
            with open(resource_pack_path, "wb") as rp:
                rp.write(resource_pack_bytes)

        structure = load_structure(schem_path)
        normalized = normalize_palette(structure)

        baker = ModelBaker(resource_pack_path)
        faces = culled_faces(normalized, baker)
        atlas = build_atlas(baker.textures)
        mesh = build_mesh(faces, atlas.uv_rects)
        glb = mesh_to_glb(mesh, atlas)

    b64 = base64.b64encode(glb.glb_bytes).decode("ascii")
    return PreviewPayload(b64, glb.center, glb.size)
