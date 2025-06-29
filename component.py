import json
import os
import uuid
from component_base import BaseComponent
import streamlit as st
import artifact_manager

from utils import LLM
from . import core
from . import cmcschematic as mcschematic

class BuilderGPTComponent(BaseComponent):
    name = "BuilderGPT"
    description = "Generate Minecraft structures"
    requirements = ["nbtlib", "immutable_views"]

    def __init__(self):
        self.llm = LLM()
        with open(os.path.join(os.path.dirname(__file__), "prompts.json"), "r") as f:
            self.prompts = json.load(f)
        with open(os.path.join(os.path.dirname(__file__), "block_id_list.txt"), "r") as f:
            self.block_id_list = f.read()
        
        # Register artifact types
        artifact_manager.register_artifact_type("schem")
        artifact_manager.register_artifact_type("mcfunction")

    def generate(self, description, version, export_type, image_path=None, progress=None):
        sys_prompt = self.prompts["SYS_GEN"] + f"\n\nUsable Block ID List:\n{self.block_id_list}"
        user_prompt = self.prompts["USR_GEN"].replace("%DESCRIPTION%", description)
        
        if progress:
            progress.progress(0.2)
        
        # Call LLM with optional image
        if image_path:
            response = self.llm.ask(sys_prompt, user_prompt, image_path=image_path)
        else:
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
            # Register artifact for schematic file
            artifact_manager.write_artifact(
                self.name,
                path,
                f"Minecraft schematic: {description[:50]}{'...' if len(description) > 50 else ''}",
                "schem"
            )
        else:
            path = os.path.join("generated", name + ".mcfunction")
            # Register artifact for mcfunction file
            artifact_manager.write_artifact(
                self.name,
                path,
                f"Minecraft function: {description[:50]}{'...' if len(description) > 50 else ''}",
                "mcfunction"
            )
        
        if progress:
            progress.progress(1.0)
        return path

    def render(self):
        st.title("BuilderGPT")
        
        # Game version and export type selection
        versions = [attr.name for attr in mcschematic.Version]
        version = st.selectbox("Game Version", versions)
        export_type = st.radio("Export Type", ["schem", "mcfunction"])
        
        # Text input (required)
        description = st.text_area("Description", placeholder="Describe the structure you want to build...")
        
        # Image input (optional)
        st.markdown("**Optional: Upload Reference Image**")
        uploaded_file = st.file_uploader(
            "Upload an image for reference (optional)", 
            type=['png', 'jpg', 'jpeg', 'gif', 'bmp'],
            help="Upload an image to help the AI understand the structure you want to build"
        )
        
        # Show uploaded image preview
        image_path = None
        if uploaded_file is not None:
            # Save uploaded file temporarily
            temp_dir = "temp_uploads"
            if not os.path.exists(temp_dir):
                os.makedirs(temp_dir)
            
            image_path = os.path.join(temp_dir, uploaded_file.name)
            with open(image_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Show preview
            st.image(uploaded_file, caption="Reference Image", use_container_width=True)
        
        # Generate button - only enabled if description is provided
        if st.button("Generate", disabled=not description.strip()):
            if description.strip():
                progress = st.progress(0.0)
                path = self.generate(description, version, export_type, image_path, progress)
                if path:
                    st.success(f"File saved to {path} and added to Artifact Center")
                else:
                    st.error("Failed to generate schematic")
                
                # Clean up temporary image file
                if image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except:
                        pass  # Ignore cleanup errors
            else:
                st.warning("Please provide a description of the structure you want to build.")


def get_component():
    return BuilderGPTComponent()
