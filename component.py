import json
import os
import uuid
import mcschematic
from component_base import BaseComponent
import streamlit as st
import artifact_manager

from utils import LLM
from . import core

class BuilderGPTComponent(BaseComponent):
    name = "BuilderGPT"
    description = "Generate Minecraft structures"
    version = "3.0.0"
    supported_framework_versions = ">=1.0.0"
    author_name = "CyniaAI Team"
    author_link = "https://github.com/CyniaAI/BuilderGPT"
    
    # Class-level flag to prevent multiple initializations
    _initialized = False
    _instance = None

    def __init__(self):
        # Prevent multiple initializations
        if BuilderGPTComponent._initialized:
            if BuilderGPTComponent._instance:
                # Copy attributes from existing instance
                self.llm = BuilderGPTComponent._instance.llm
                self.prompts = BuilderGPTComponent._instance.prompts
                self.block_id_list = BuilderGPTComponent._instance.block_id_list
                return
        
        self.llm = LLM()
        with open(os.path.join(os.path.dirname(__file__), "prompts.json"), "r") as f:
            raw_prompts = json.load(f)
            # Convert list prompts to strings
            self.prompts = {}
            for key, value in raw_prompts.items():
                if isinstance(value, list):
                    self.prompts[key] = "".join(value)
                else:
                    self.prompts[key] = value
        with open(os.path.join(os.path.dirname(__file__), "block_id_list.txt"), "r") as f:
            self.block_id_list = f.read()
        
        # Register artifact types (only once)
        if not BuilderGPTComponent._initialized:
            artifact_manager.register_artifact_type("schem")
            artifact_manager.register_artifact_type("mcfunction")
            BuilderGPTComponent._initialized = True
            BuilderGPTComponent._instance = self

    def generate(self, description, version, export_type, image_path=None, progress=None):
        # Build the new JS-based prompt
        from .core import format_version_for_prompt
        human_version = format_version_for_prompt(version)
        sys_prompt = (
            self.prompts["SYS_GEN"]
            .replace("%MINECRAFT_VERSION%", human_version)
            .replace("%BUILD_SPEC%", description)
            .replace("%BLOCK_TYPES_LIST%", self.block_id_list)
        )
        # Keep user prompt minimal to satisfy providers that require both roles
        user_prompt = ""
        
        if progress:
            progress.progress(0.2)
        
        # Call LLM with optional image
        if image_path:
            response = self.llm.ask(sys_prompt, user_prompt, image_path=image_path)
        else:
            response = self.llm.ask(sys_prompt, user_prompt)
            
        if progress:
            progress.progress(0.6)
        result = core.text_to_schem(response, export_type=export_type)
        if progress:
            progress.progress(0.8)
            
        raw_name = self.llm.ask(self.prompts["SYS_GEN_NAME"], self.prompts["USR_GEN_NAME"].replace("%DESCRIPTION%", description))
        name = f"{raw_name}-{uuid.uuid4()}"
        version_tag = core.input_version_to_mcs_tag(version)
        if not os.path.isdir("generated"):
            os.makedirs("generated")
        if result is None:
            return None
        
        if export_type == "schem":
            # result is an MCSchematic
            result.save("generated", name, version_tag)
            path = os.path.join("generated", name + ".schem")
            # Register artifact for schematic file
            artifact_manager.write_artifact(
                self.name,
                path,
                f"Minecraft schematic: {description[:50]}{'...' if len(description) > 50 else ''}",
                "schem"
            )
        else:
            # result is a temp mcfunction path; rename to final name
            final_path = os.path.join("generated", name + ".mcfunction")
            try:
                if os.path.exists(result):
                    os.replace(result, final_path)
                else:
                    # If core returned non-existing path, just write empty file to avoid UI error
                    with open(final_path, "w", encoding="utf-8") as f:
                        f.write("")
            except Exception:
                # Fallback: ensure file exists
                with open(final_path, "a", encoding="utf-8"):
                    pass
            path = final_path
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
    # Return existing instance if available to prevent multiple initializations
    if BuilderGPTComponent._instance and BuilderGPTComponent._initialized:
        return BuilderGPTComponent._instance
    return BuilderGPTComponent()
