import sys
import time
from pathlib import Path

# Ensure config and backends can be imported
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP
from config import OUTPUTS
from blender_client import send
from backends import triposr, vlm

mcp = FastMCP("blender-image-3d")


@mcp.tool()
def check_blender() -> dict:
    """Check that Blender and its MCP bridge add-on are running and accessible."""
    return send("ping")


@mcp.tool()
def describe_image(image_path: str) -> str:
    """Describe an input image for 3D modeling using the local Ollama vision model."""
    return vlm.describe(image_path)


@mcp.tool()
def generate_3d_from_image(image_path: str, mc_resolution: int = 256) -> str:
    """Generate a .glb 3D mesh from an image using local TripoSR. Returns the absolute file path."""
    return triposr.run(image_path, mc_resolution=mc_resolution)


@mcp.tool()
def import_to_blender(model_path: str, normalize: bool = True, target_size: float = 2.0) -> dict:
    """Import a .glb/.obj/.fbx into the active Blender scene, auto-centered and ground-aligned."""
    return send("import_model", {
        "path": model_path,
        "normalize": normalize,
        "target_size": target_size,
    })


@mcp.tool()
def image_to_blender(image_path: str, mc_resolution: int = 256) -> dict:
    """Full pipeline: image -> 3D model generation -> automatic import into Blender."""
    glb = triposr.run(image_path, mc_resolution=mc_resolution)
    res = send("import_model", {"path": glb, "normalize": True, "target_size": 2.0})
    res["model_path"] = glb
    return res


@mcp.tool()
def get_scene_info() -> dict:
    """List all objects, their types, coordinates, and dimensions in the current Blender scene."""
    return send("scene_info")


@mcp.tool()
def apply_material(object_name: str, r: float = 0.8, g: float = 0.8, b: float = 0.8) -> dict:
    """Apply a coloured Principled BSDF material to a mesh object (RGB values in [0, 1])."""
    return send("apply_material", {"object_name": object_name, "color": [r, g, b]})


@mcp.tool()
def render_preview(width: int = 768, height: int = 768) -> str:
    """Render the current Blender scene viewport to a high quality PNG preview and return its path."""
    path = str(OUTPUTS / f"preview_{int(time.time())}.png")
    send("render_preview", {"path": path, "width": width, "height": height})
    return path


@mcp.tool()
def describe_render(render_path: str) -> str:
    """Analyze a rendered preview image using the local vision LLM to inspect quality and defects."""
    return vlm.compare("", render_path)


@mcp.tool()
def export_model(filename: str = "final.glb") -> str:
    """Export the active Blender scene to a 3D model file (.glb, .fbx, .obj, .stl)."""
    path = str(OUTPUTS / filename)
    send("export_model", {"path": path})
    return path


@mcp.tool()
def execute_blender_code(code: str) -> dict:
    """Execute arbitrary Python (bpy) code inside Blender for custom modifications and materials."""
    return send("execute_code", {"code": code})


@mcp.tool()
def clear_scene() -> dict:
    """Clear all objects from the current Blender scene."""
    return send("clear_scene")


if __name__ == "__main__":
    mcp.run()
