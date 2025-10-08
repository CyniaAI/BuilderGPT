from __future__ import annotations

import io
import os
from typing import Dict, Iterable, Tuple

import numpy as np

from .types import PaletteEntry, StructureBounds, StructureData

try:
    import nbtlib
except ImportError as exc:  # pragma: no cover - dependency missing at runtime
    nbtlib = None  # type: ignore
    _nbt_import_error = exc
else:
    _nbt_import_error = None


def _require_nbtlib() -> None:
    if nbtlib is None:
        raise RuntimeError(
            "nbtlib is required to load schematic files but could not be imported"
        ) from _nbt_import_error


def _parse_palette_entry(block_state: str) -> PaletteEntry:
    if "[" not in block_state:
        return PaletteEntry(block_state, {})
    name, props = block_state.split("[", 1)
    props = props.rstrip("]")
    prop_dict: Dict[str, str] = {}
    for part in props.split(","):
        if not part:
            continue
        if "=" not in part:
            prop_dict[part] = "true"
            continue
        key, value = part.split("=", 1)
        prop_dict[key] = value
    return PaletteEntry(name, prop_dict)


def _decode_block_data(
    data: Iterable[int],
    palette_size: int,
    total_blocks: int,
) -> np.ndarray:
    """Decode Sponge schematic block data bitstream."""

    # Minimum bits per block is 4 according to the Sponge schematic spec.
    bits_per_block = max(4, (palette_size - 1).bit_length())
    mask = (1 << bits_per_block) - 1

    values = np.zeros(total_blocks, dtype=np.int32)
    bit_buffer = 0
    bit_count = 0
    index = 0

    for byte in data:
        bit_buffer |= (byte & 0xFF) << bit_count
        bit_count += 8
        while bit_count >= bits_per_block and index < total_blocks:
            values[index] = bit_buffer & mask
            bit_buffer >>= bits_per_block
            bit_count -= bits_per_block
            index += 1

    if index < total_blocks:
        # Pad remaining values with zeros (air)
        values[index:] = 0
    return values


def load_structure(input_path: str) -> StructureData:
    """Load a schematic structure from disk.

    This loader implements the Sponge `.schem` format which is produced by the
    `mcschematic` library. The function avoids heavy dependencies while keeping
    the API surface compatible with the downstream preview pipeline.
    """

    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)

    _require_nbtlib()
    data = nbtlib.load(input_path)  # type: ignore[operator]
    root = data

    width = int(root["Width"])
    height = int(root["Height"])
    length = int(root["Length"])

    palette_tag = root["Palette"]
    palette_reverse: Dict[int, PaletteEntry] = {}
    for block_state, value in palette_tag.items():
        palette_reverse[int(value)] = _parse_palette_entry(block_state)

    palette: Tuple[PaletteEntry, ...] = tuple(
        palette_reverse[index]
        for index in sorted(palette_reverse.keys())
    )

    total_blocks = width * height * length
    block_data: Iterable[int]
    block_data_tag = root.get("BlockData")
    if block_data_tag is not None:
        block_data = block_data_tag
    else:
        # Legacy schematics may store data as a LongArray named `BlockStates`
        block_states_tag = root.get("BlockStates")
        if block_states_tag is None:
            raise ValueError("Schematic does not contain BlockData or BlockStates")
        # Expand the packed longs into bytes
        raw_bytes = bytearray()
        for long_val in block_states_tag:
            value = int(long_val)
            raw_bytes.extend(value.to_bytes(8, byteorder="little", signed=False))
        block_data = raw_bytes

    indices = _decode_block_data(block_data, len(palette), total_blocks)

    voxels = np.zeros((width, height, length), dtype=np.int32)
    for i, palette_index in enumerate(indices[:total_blocks]):
        x = i % width
        z = (i // width) % length
        y = i // (width * length)
        voxels[x, y, z] = palette_index

    bounds = StructureBounds(0, 0, 0, width - 1, height - 1, length - 1)
    return StructureData(bounds, list(palette), voxels)
