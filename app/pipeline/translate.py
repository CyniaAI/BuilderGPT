from __future__ import annotations

from .types import PaletteEntry, StructureData

try:
    from pymctranslate import TranslationManager
except ImportError:  # pragma: no cover - optional dependency
    TranslationManager = None  # type: ignore


def normalize_palette(struct: StructureData, target: str = "java_1_20_1") -> StructureData:
    """Best-effort palette normalisation using PyMCTranslate.

    The normalisation step keeps palette indices intact and rewrites the block
    descriptors so that downstream systems can rely on stable blockstate names.
    When PyMCTranslate is not available we simply return the structure
    unchanged.
    """

    if TranslationManager is None:
        return struct

    try:
        manager = TranslationManager(target_platform="java", resource_pack="vanilla")
        translator = manager.get_version(target)
    except Exception:
        # If translation data is missing we fall back to the original structure.
        return struct

    new_palette = []
    for entry in struct.palette:
        try:
            block = translator.block.from_universal(  # type: ignore[attr-defined]
                entry.namespaced_name, entry.properties
            )
            normalized = translator.block.to_universal(block)  # type: ignore[attr-defined]
        except Exception:
            new_palette.append(entry)
            continue
        if normalized is None:
            new_palette.append(entry)
            continue
        name, properties = normalized
        if isinstance(properties, list) and properties:
            merged = {}
            for prop in properties:
                merged.update(prop)
            properties = merged
        new_palette.append(PaletteEntry(name, dict(properties)))
    return StructureData(struct.bounds, new_palette, struct.voxels)
