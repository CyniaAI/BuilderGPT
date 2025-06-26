import json
import os
import uuid
from component_base import BaseComponent
import streamlit as st

from utils import LLM
from . import core
import cube_mcschematic as mcschematic

class BuilderGPTComponent(BaseComponent):
    name = "BuilderGPT"
    description = "Generate Minecraft structures"

    def __init__(self):
        self.llm = LLM()
        with open(os.path.join(os.path.dirname(__file__), "prompts.json"), "r") as f:
            self.prompts = json.load(f)
        with open(os.path.join(os.path.dirname(__file__), "block_id_list.txt"), "r") as f:
            self.block_id_list = f.read()

    def generate(self, description, version, export_type, progress=None):
        sys_prompt = self.prompts["SYS_GEN"] + f"\n\nUsable Block ID List:\n{self.block_id_list}"
        user_prompt = self.prompts["USR_GEN"].replace("%DESCRIPTION%", description)
        if progress:
            progress.progress(0.2)
        response = self.llm.ask(sys_prompt, user_prompt)
        if progress:
            progress.progress(0.6)
        schem = core.text_to_schem(response, export_type=export_type)
        if progress:
            progress.progress(0.8)
        raw_name = self.llm.ask(self.prompts["SYS_GEN_NAME"], self.prompts["USR_GEN_NAME"].replace("%DESCRIPTION%", description))
        name = f"{raw_name}-{uuid.uuid4()}"
        version_tag = core.input_version_to_mcs_tag(version)
        if not os.path.isdir("generated"):
            os.makedirs("generated")
        if schem is None:
            return None
        if export_type == "schem":
            schem.save("generated", name, version_tag)
            path = os.path.join("generated", name + ".schem")
        else:
            path = os.path.join("generated", name + ".mcfunction")
        if progress:
            progress.progress(1.0)
        return path

    def render(self):
        st.title("BuilderGPT")
        versions = [attr.name for attr in mcschematic.Version]
        version = st.selectbox("Game Version", versions)
        export_type = st.radio("Export Type", ["schem", "mcfunction"])
        description = st.text_area("Description")
        if st.button("Generate") and description:
            progress = st.progress(0.0)
            path = self.generate(description, version, export_type, progress)
            if path:
                st.success(f"File saved to {path}")
            else:
                st.error("Failed to generate schematic")


def get_component():
    return BuilderGPTComponent()
