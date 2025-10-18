import base64
import json
import math
import os
import uuid
from typing import Optional

import mcschematic
import streamlit as st
from streamlit.components.v1 import html

import artifact_manager
from component_base import BaseComponent
from utils import LLM
from . import core
from .app.preview import PreviewOptions, build_preview

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
    _viewer_template: Optional[str] = None

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

    def _load_viewer_template(self) -> str:
        if BuilderGPTComponent._viewer_template is None:
            viewer_dir = os.path.join(os.path.dirname(__file__), "app", "viewer")
            viewer_path = os.path.join(viewer_dir, "index.html")
            with open(viewer_path, "r", encoding="utf-8") as fp:
                template = fp.read()

            def encode_asset(*relative_path: str) -> str:
                asset_path = os.path.join(viewer_dir, *relative_path)
                with open(asset_path, "rb") as asset_fp:
                    return base64.b64encode(asset_fp.read()).decode("ascii")

            replacements = {
                "__THREE_MODULE__": encode_asset("lib", "three.module.js"),
                "__ORBIT_CONTROLS__": encode_asset("lib", "jsm", "controls", "OrbitControls.js"),
                "__GLTF_LOADER__": encode_asset("lib", "jsm", "loaders", "GLTFLoader.js"),
                "__BUFFER_GEOMETRY_UTILS__": encode_asset("lib", "jsm", "utils", "BufferGeometryUtils.js"),
            }

            for placeholder, encoded in replacements.items():
                template = template.replace(placeholder, encoded)

            BuilderGPTComponent._viewer_template = template
        return BuilderGPTComponent._viewer_template

    def render(self):
        st.title("BuilderGPT")

        # Game version and export type selection
        versions = [attr.name for attr in mcschematic.Version]
        version = st.selectbox("Game Version", versions)
        export_type = st.radio("Export Type", ["schem", "mcfunction"])

        # Text input (required)
        description = st.text_area("Description", placeholder="Describe the structure you want to build...")

        # Init session state for preview reuse
        if "bgpt_last_schem_path" not in st.session_state:
            st.session_state["bgpt_last_schem_path"] = None  # type: ignore[assignment]

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

        button_row = st.container()
        preview_settings_container = st.container()

        with preview_settings_container.expander("Preview Settings", expanded=False):
            resource_pack_file = st.file_uploader(
                "Optional resource pack (.zip)",
                type=["zip"],
                help="Upload a resource pack to colourise the preview (optional)",
            )
            resource_pack_bytes = resource_pack_file.getvalue() if resource_pack_file else None

            col1, col2, col3 = st.columns(3)
            sun_az_deg = col1.slider("Sun azimuth (°)", 0.0, 360.0, 60.0)
            sun_el_deg = col1.slider("Sun elevation (°)", -30.0, 90.0, 35.0)
            max_dpr = col1.slider("Max device pixel ratio", 0.5, 3.0, 1.6)

            render_scale = col2.slider("Render scale", 0.5, 2.0, 1.0, help="Clamp renderer pixel ratio for performance")
            max_distance = col2.slider("Max draw distance", 64.0, 2048.0, 512.0)
            show_grid = col2.checkbox("Show grid", value=True)

            wireframe = col3.checkbox("Wireframe", value=False)
            ambient_occlusion = col3.checkbox("Ambient occlusion", value=True)

            preview_options = PreviewOptions(
                sun_azimuth=math.radians(sun_az_deg),
                sun_elevation=math.radians(sun_el_deg),
                max_dpr=max_dpr,
                render_scale=render_scale,
                max_draw_distance=max_distance,
                show_grid=show_grid,
                wireframe=wireframe,
                ambient_occlusion=ambient_occlusion,
            )

            st.divider()
            st.markdown("**Render existing .schem (skip generation)**")
            schem_upload = st.file_uploader(
                "Upload a .schem file to preview",
                type=["schem"],
                key="schem_upload_direct",
                help="Directly preview an existing schematic without running generation",
            )
            render_uploaded = st.button("Render Uploaded Schem", disabled=schem_upload is None)
            if render_uploaded and schem_upload is not None:
                try:
                    tmp_dir = os.path.join("temp_uploads", "schem")
                    os.makedirs(tmp_dir, exist_ok=True)
                    tmp_path = os.path.join(tmp_dir, schem_upload.name)
                    with open(tmp_path, "wb") as f:
                        f.write(schem_upload.getbuffer())
                except Exception as exc:
                    st.error(f"Failed to persist uploaded schem: {exc}")
                else:
                    with st.spinner("Building preview from uploaded schematic..."):
                        self._render_preview(tmp_path, resource_pack_bytes, preview_options)
                    st.session_state["bgpt_last_schem_path"] = tmp_path

        with button_row:
            # Generate button - only enabled if description is provided
            col_gen, col_rerender = st.columns([1, 1])

            # Re-render button uses last schem and current settings; no regeneration
            with col_rerender:
                last_path = st.session_state.get("bgpt_last_schem_path")
                can_rerender = bool(last_path and os.path.exists(last_path))
                if st.button(
                    "Re-render",
                    disabled=not can_rerender,
                    help="Refresh the preview using the last schematic without regenerating",
                ):
                    self._render_preview(last_path, resource_pack_bytes, preview_options)  # type: ignore[arg-type]

            with col_gen:
                gen_clicked = st.button("Generate", disabled=not description.strip())

        if gen_clicked:
            if description.strip():
                progress = st.progress(0.0)
                path = self.generate(description, version, export_type, image_path, progress)
                if path:
                    st.success(f"File saved to {path} and added to Artifact Center")
                    if export_type == "schem":
                        self._render_preview(path, resource_pack_bytes, preview_options)
                        # Remember last rendered schem path for Re-render
                        st.session_state["bgpt_last_schem_path"] = path
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

    @staticmethod
    @st.cache_data(show_spinner=False)
    def _cached_preview(
        schem_bytes: bytes,
        resource_pack_bytes: Optional[bytes],
        options_dict: dict,
    ) -> dict:
        options = PreviewOptions(**options_dict)
        payload = build_preview(schem_bytes, resource_pack_bytes, options)
        params = payload.to_viewer_params(options)
        params_json = json.dumps(params).replace("</", "<\\/")
        return {
            "params_json": params_json,
            "center": payload.center,
            "size": payload.size,
        }

    def _render_preview(
        self,
        schem_path: str,
        resource_pack_bytes: Optional[bytes],
        options: PreviewOptions,
    ) -> None:
        try:
            with open(schem_path, "rb") as fp:
                schem_bytes = fp.read()
        except OSError as exc:
            st.warning(f"Preview unavailable: {exc}")
            return

        try:
            preview_data = self._cached_preview(
                schem_bytes,
                resource_pack_bytes,
                options.to_serializable(),
            )
        except Exception as exc:
            st.warning(f"Failed to build preview: {exc}")
            return

        viewer_html = self._load_viewer_template()
        html_content = viewer_html.replace("__PAYLOAD__", preview_data["params_json"])
        html(html_content, height=720)

        center = preview_data.get("center", (0, 0, 0))
        size = preview_data.get("size", (0, 0, 0))
        st.caption(
            "Preview bounds center: "
            f"({center[0]:.2f}, {center[1]:.2f}, {center[2]:.2f}) · size: "
            f"({size[0]:.2f}, {size[1]:.2f}, {size[2]:.2f})"
        )


def get_component():
    # Return existing instance if available to prevent multiple initializations
    if BuilderGPTComponent._instance and BuilderGPTComponent._initialized:
        return BuilderGPTComponent._instance
    return BuilderGPTComponent()
