import json
import cube_mcschematic as mcschematic
from log_writer import logger
from utils import LLM

VERSION = "2.0.0"

llm = LLM()


def text_to_schem(text: str, export_type: str = "schem"):
    """Convert a JSON string to a Minecraft schematic or mcfunction file."""
    try:
        data = json.loads(text)
        logger(f"text_to_schem: loaded JSON data {data}")

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
            with open("generated/temp.mcfunction", "w") as f:
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
            return None
    except Exception as e:
        logger(f"text_to_schem: failed to load JSON data. Error: {e}")
        return None


def input_version_to_mcs_tag(input_version: str):
    """Convert an input version string to the corresponding MCSchematic tag."""
    try:
        return getattr(mcschematic.Version, input_version)
    except Exception as e:
        logger(f"input_version_to_mcs_tag: failed to convert version {input_version}; {e}")
        return None
