import sys
import tkinter as tk
import tkinter.messagebox as msgbox
import tkinter.simpledialog as simpledialog

from log_writer import logger
import core
import config

def get_schematic(description):
    """
    Generates a schematic based on the given description.

    Args:
        description (str): The description of the schematic.

    Returns:
        str: The generated schematic.

    Raises:
        SystemExit: If the schematic generation fails.
    """
    response = core.askgpt(config.SYS_GEN, config.USR_GEN.replace("%DESCRIPTION%", description), config.GENERATE_MODEL)

    schem = core.text_to_schem(response)

    if schem is None:
        msgbox.showerror("Error", "Failed to generate the schematic. We recommend you to change the generating model to gpt-4-turbo-preview or other smarter models.")
        sys.exit(1)
    
    return schem

def get_schematic_advanced(description):
    print("(Advanced Mode) Generating programme...")
    programme = core.askgpt(config.BTR_DESC_SYS_GEN, config.BTR_DESC_USR_GEN.replace("%DESCRIPTION%", description), config.GENERATE_MODEL, disable_json_mode=True)

    print("(Advanced Mode) Generating image tag...")
    image_tag = core.askgpt(config.IMG_TAG_SYS_GEN, config.IMG_TAG_USR_GEN.replace("%PROGRAMME%", programme), config.GENERATE_MODEL, disable_json_mode=True)

    print("(Advanced Mode) Generating image...")
    tag = image_tag + ", minecraft)"
    image_url = core.ask_dall_e(tag)

    print("(Advanced Mode) Generating schematic...")
    response = core.askgpt(config.SYS_GEN_ADV, config.USR_GEN_ADV.replace("%DESCRIPTION%", description), config.VISION_MODEL, image_url=image_url)

    schem = core.text_to_schem(response)

    return schem

def generate_schematic():
    """
    Generates a schematic file based on user input.

    This function retrieves the version, name, and description from the user interface,
    initializes the core functionality, and generates a plugin based on the provided description.
    It then saves the generated schematic file in the 'generated' folder.

    Returns:
        None
    """
    generate_button.config(state=tk.DISABLED, text="Generating...")

    if config.ADVANCED_MODE:
        msgbox.showwarning("Warning", "You are using advanced mode. This mode will generate schematic with higher quality, but it may take longer to generate.")

    msgbox.showinfo("Info", "It is expected to take 30 seconds to 5 minutes. The programme may \"not responding\", this is normal, just be patient. DO NOT CLOSE THE PROGRAM. Click the button below to start generating.")

    version = version_entry.get()
    name = name_entry.get()
    description = description_entry.get()

    logger(f"console: input version {version}")
    logger(f"console: input name {name}")
    logger(f"console: input description {description}")

    if config.ADVANCED_MODE:
        schem = get_schematic_advanced(description)
    else:
        schem = get_schematic(description)

    logger(f"console: Saving {name}.schem to generated/ folder.")
    version_tag = core.input_version_to_mcs_tag(version)

    while version_tag is None:
        msgbox.showerror("Error", "Invalid version number. Please retype the version number.")
        version = simpledialog.askstring("Reinput", "Please retype the version number (eg. 1.20.1): ")
        core.input_version_to_mcs_tag(version)

    schem.save("generated", name, version_tag)

    msgbox.showinfo("Success", "Generated. Get your schem file in folder generated.")

    generate_button.config(state=tk.NORMAL, text="Generate")

def Application():
    global version_entry, name_entry, description_entry, generate_button

    window = tk.Tk()
    window.title("BuilderGPT")
    
    logo = tk.PhotoImage(file="logo.png")
    logo = logo.subsample(4)
    logo_label = tk.Label(window, image=logo)
    logo_label.pack()

    version_label = tk.Label(window, text="What's your minecraft version? (eg. 1.20.1):")
    version_label.pack()
    version_entry = tk.Entry(window)
    version_entry.pack()

    name_label = tk.Label(window, text="What's the name of your structure? It will be the name of the generated *.schem file:")
    name_label.pack()
    name_entry = tk.Entry(window)
    name_entry.pack()

    description_label = tk.Label(window, text="What kind of structure would you like to generate? Describe as clear as possible:")
    description_label.pack()
    description_entry = tk.Entry(window)
    description_entry.pack()

    generate_button = tk.Button(window, text="Generate", command=generate_schematic)
    generate_button.pack()

    window.mainloop()

if __name__ == "__main__":
    core.initialize()
    Application()
else:
    print("Error: Please run ui.py as the main program instead of importing it from another program.")
    logger("Exit: Running ui.py as an imported module.")