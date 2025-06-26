import uuid
import json

from log_writer import logger
import core

with open("prompts.json", "r") as f:
    PROMPTS = json.load(f)

def generate_schematic(description: str):
    response = core.ask_llm(PROMPTS["SYS_GEN"], PROMPTS["USR_GEN"].replace("%DESCRIPTION%", description))
    schem = core.text_to_schem(response)
    retry_times = 0
    while schem is None and retry_times < 3:
        logger("JSON syntax error. Regenerating...")
        schem = generate_schematic(description)
        retry_times += 1
    return schem

def generate_name(description: str):
    return core.ask_llm(PROMPTS["SYS_GEN_NAME"], PROMPTS["USR_GEN_NAME"].replace("%DESCRIPTION%", description))


if __name__ == "__main__":
    core.initialize()

    print("Welcome to BuilderGPT. Answer a few questions to generate your structure.\n")
    version = input("[0/2] What's your minecraft version? (eg. 1.20.1): ")
    description = input("[1/2] What kind of structure would you like to generate? Describe as clear as possible: ")

    logger(f"console: input version {version}")
    logger(f"console: input description {description}")

    print("Generating...")
    schem = generate_schematic(description)

    raw_name = generate_name(description)
    name = raw_name + "-" + str(uuid.uuid4())

    logger(f"console: Saving {name}.schem to generated/ folder.")
    version_tag = core.input_version_to_mcs_tag(version)
    while version_tag is None:
        print("Error: Invalid version number. Please retype the version number.")
        version = input("[re-0/0] What's your minecraft version? (eg. 1.20.1): ")
        version_tag = core.input_version_to_mcs_tag(version)

    if schem:
        schem.save("generated", name, version_tag)
        print(f"Generated with file name \"{name}.schem\". Get your schem file in folder generated.")
    else:
        print("Failed to generate schematic.")
