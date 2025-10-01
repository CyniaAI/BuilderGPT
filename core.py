import json
import os
import re
import mcschematic
from typing import Dict, List, Optional, Tuple
from log_writer import logger
from utils import LLM

llm = LLM()

VERSION = "3.0.0"

# Lazy import for quickjs; only needed for JS execution
_quickjs_ctx = None


def _load_allowed_blocks() -> set:
    try:
        path = os.path.join(os.path.dirname(__file__), "block_id_list.txt")
        with open(path, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    except Exception as e:
        logger(f"load_allowed_blocks: failed to read block list: {e}")
        return set()


def _normalize_block(block_type: str, block_states: Optional[Dict[str, str]], allowed: set) -> Optional[str]:
    if not block_type:
        return None
    base = block_type.strip()
    if not base.startswith("minecraft:"):
        base = f"minecraft:{base}"
    # Strip states for membership check
    base_id = base.split("[", 1)[0]
    if base_id not in allowed:
        logger(f"normalize_block: skipping unsupported block '{base_id}'")
        return None
    if block_states and isinstance(block_states, dict) and len(block_states) > 0:
        # Convert to sorted state string for determinism
        items = sorted((str(k), str(v)) for k, v in block_states.items())
        state_str = ",".join([f"{k}={v}" for k, v in items])
        return f"{base_id}[{state_str}]"
    return base_id


def _extract_js_code(text: str) -> Optional[str]:
    if not text:
        return None
    # Extract between <code> ... </code>
    m = re.search(r"<code>\s*(.*?)\s*</code>", text, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1)
    return None


def _ensure_quickjs():
    # Create a fresh context each time to avoid state pollution
    try:
        import quickjs  # type: ignore
    except Exception as e:
        logger(f"quickjs not available: {e}")
        return None
    return quickjs.Context()


def _execute_js_build(code: str) -> List[Tuple[int, int, int, str]]:
    """Execute the JS build script and capture block placements.

    Returns a list of (x, y, z, blockData) placements.
    """
    ctx = _ensure_quickjs()
    if ctx is None:
        raise RuntimeError("JS engine (quickjs) not available")
    
    # Transform async code to sync for backward compatibility
    # The prompt now instructs LLM to generate synchronous code directly,
    # but we keep this transformation as a safety net in case async/await is still used
    code = re.sub(r'\basync\s+function\b', 'function', code)
    code = re.sub(r'\bawait\s+', '', code)

    allowed = _load_allowed_blocks()
    placements: Dict[Tuple[int, int, int], str] = {}

    def set_block(x, y, z, block_type, options=None):
        try:
            bx, by, bz = int(x), int(y), int(z)
            block_states = None
            mode = None
            if isinstance(options, dict):
                block_states = options.get("blockStates")
                mode = options.get("mode")
            block_data = _normalize_block(str(block_type), block_states, allowed)
            if block_data is None:
                return None
            pos = (bx, by, bz)
            if mode == "keep" and pos in placements:
                return None
            placements[pos] = block_data
        except Exception as e:
            logger(f"set_block error: {e}")
        return None

    def fill_region(x1, y1, z1, x2, y2, z2, block_type, options=None):
        try:
            x1, y1, z1 = int(x1), int(y1), int(z1)
            x2, y2, z2 = int(x2), int(y2), int(z2)
        except Exception:
            # Some engines may pass floats; coerce generically
            x1, y1, z1 = int(float(x1)), int(float(y1)), int(float(z1))
            x2, y2, z2 = int(float(x2)), int(float(y2)), int(float(z2))

        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        if z1 > z2:
            z1, z2 = z2, z1

        block_states = None
        mode = None
        replace_filter = None
        if isinstance(options, dict):
            block_states = options.get("blockStates")
            mode = options.get("mode")
            replace_filter = options.get("replaceFilter")
        block_data = _normalize_block(str(block_type), block_states, allowed)
        if block_data is None:
            return None

        # derive replace filter base id if present
        replace_base = None
        if replace_filter:
            if not str(replace_filter).startswith("minecraft:"):
                replace_base = f"minecraft:{replace_filter}"
            else:
                replace_base = str(replace_filter)

        def should_place(px, py, pz):
            if mode == "keep" and (px, py, pz) in placements:
                return False
            if mode == "replace" and replace_base is not None:
                # Treat missing as minecraft:air
                existing = placements.get((px, py, pz), "minecraft:air")
                if existing.split("[", 1)[0] != replace_base:
                    return False
            return True

        outline_only = mode in ("outline", "hollow")
        for ix in range(x1, x2 + 1):
            for iy in range(y1, y2 + 1):
                for iz in range(z1, z2 + 1):
                    if outline_only:
                        at_surface = (
                            ix == x1 or ix == x2 or iy == y1 or iy == y2 or iz == z1 or iz == z2
                        )
                        if not at_surface:
                            continue
                    if should_place(ix, iy, iz):
                        placements[(ix, iy, iz)] = block_data
        return None

    # Bridge Python functions into JS
    try:
        ctx.add_callable("pySetBlock", set_block)
        ctx.add_callable("pyFill", fill_region)
    except Exception as e:
        logger(f"quickjs bridge error: {e}")
        raise

    # Inject helper wrappers and user code
    # The helper functions execute synchronously. After removing async/await from code,
    # they no longer need to return Promises, but we still need to handle Promise.all()
    # that might be in the code.
    helper_js = (
        # Console polyfill
        "var console = { log: function() {}, warn: function() {}, error: function() {} };\n"
        # Helper functions
        "function safeSetBlock(x,y,z,blockType,options){ pySetBlock(x,y,z,blockType,options); }\n"
        "function safeFill(x1,y1,z1,x2,y2,z2,blockType,options){ pyFill(x1,y1,z1,x2,y2,z2,blockType,options); }\n"
        "function safeFillBiome(x1,y1,z1,x2,y2,z2,biome){ /* biome not supported */ }\n"
        # Minimal Promise polyfill for Promise.all() compatibility
        "if (typeof Promise === 'undefined') {\n"
        "  var Promise = {};\n"
        "}\n"
        "Promise.all = function(arr) { return null; };\n"
        "Promise.resolve = function(v) { return v; };\n"
    )
    try:
        ctx.eval(helper_js)
        ctx.eval(code)
        # Call buildCreation directly - it's now synchronous
        ctx.eval("buildCreation(0, 0, 0)")
    except Exception as e:
        logger(f"execute_js_build: JS error: {e}")
        raise

    # Return placements as a list
    out: List[Tuple[int, int, int, str]] = [
        (x, y, z, block) for (x, y, z), block in placements.items()
    ]
    # Sort for determinism
    out.sort()
    return out


def text_to_schem(text: str, export_type: str = "schem"):
    """Convert model output to a Minecraft schematic or mcfunction file.

    Supports both legacy JSON output and the new JS-in-<code> format.
    Returns MCSchematic for 'schem' or file path for 'mcfunction'.
    """
    # 1) Try JS path first. If <code> is present, we commit to this path.
    js_code = _extract_js_code(text)
    if js_code:
        try:
            placements = _execute_js_build(js_code)
            if export_type == "schem":
                schematic = mcschematic.MCSchematic()
                for (x, y, z, block) in placements:
                    schematic.setBlock((x, y, z), block)
                return schematic
            elif export_type == "mcfunction":
                if not os.path.isdir("generated"):
                    os.makedirs("generated")
                path = os.path.join("generated", "temp.mcfunction")
                with open(path, "w", encoding="utf-8") as f:
                    for (x, y, z, block) in placements:
                        f.write(f"setblock {x} {y} {z} {block}\n")
                return path
        except Exception as e:
            logger(f"text_to_schem(JS): failed with error: {e}")
            # If JS code was found but failed to execute, we stop and return None.
            # Do not fall back to JSON parsing.
            return None

    # 2) Fallback to legacy JSON format ONLY if no JS code was found
    try:
        data = json.loads(text)
        logger(f"text_to_schem(JSON): loaded JSON data")
        if export_type == "schem":
            schematic = mcschematic.MCSchematic()
            for structure in data["structures"]:
                block_id = structure["block"]
                x = structure["x"]
                y = structure["y"]
                z = structure["z"]
                if structure["type"] == "fill":
                    to_x = structure["toX"]
                    to_y = structure["toY"]
                    to_z = structure["toZ"]
                    for ix in range(x, to_x + 1):
                        for iy in range(y, to_y + 1):
                            for iz in range(z, to_z + 1):
                                schematic.setBlock((ix, iy, iz), block_id)
                else:
                    schematic.setBlock((x, y, z), block_id)
            return schematic
        elif export_type == "mcfunction":
            if not os.path.isdir("generated"):
                os.makedirs("generated")
            path = os.path.join("generated", "temp.mcfunction")
            with open(path, "w", encoding="utf-8") as f:
                for structure in data["structures"]:
                    block_id = structure["block"]
                    x = structure["x"]
                    y = structure["y"]
                    z = structure["z"]
                    if structure["type"] == "fill":
                        to_x = structure["toX"]
                        to_y = structure["toY"]
                        to_z = structure["toZ"]
                        for ix in range(x, to_x + 1):
                            for iy in range(y, to_y + 1):
                                for iz in range(z, to_z + 1):
                                    f.write(f"setblock {ix} {iy} {iz} {block_id}\n")
                    else:
                        f.write(f"setblock {x} {y} {z} {block_id}\n")
            return path
    except Exception as e:
        logger(f"text_to_schem(JSON): failed to parse JSON: {e}")
        return None


def input_version_to_mcs_tag(input_version: str):
    """Convert an input version string to the corresponding MCSchematic tag."""
    try:
        return getattr(mcschematic.Version, input_version)
    except Exception as e:
        logger(f"input_version_to_mcs_tag: failed to convert version {input_version}; {e}")
        return None


def format_version_for_prompt(version_enum_name: str) -> str:
    """Convert enum name like 'JE_1_20_4' to '1.20.4'. Fallback to enum name."""
    try:
        # Extract digits and underscores after first '_'
        # JE_1_20_4 -> 1.20.4, JE_1_21 -> 1.21
        parts = version_enum_name.split("_")
        nums = [p for p in parts if p.isdigit()]
        if not nums:
            return version_enum_name
        return ".".join(nums)
    except Exception:
        return version_enum_name