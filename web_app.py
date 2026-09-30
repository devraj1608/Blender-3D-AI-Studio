import os
import sys
import time
import shutil
import logging
from typing import Optional
from pathlib import Path

# Add project root and mcp_server to sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "mcp_server"))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import mimetypes
mimetypes.add_type('model/gltf-binary', '.glb')
mimetypes.add_type('model/gltf+json', '.gltf')

from config import WORKSPACE, INPUTS, OUTPUTS
import blender_client
from backends import vlm

# ----------------- Backend Logging Setup -----------------
# Logs print directly to the terminal when starting the project
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("studio")

# ----------------- FastAPI App -----------------
app = FastAPI(title="Blender Image-to-3D Studio", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount outputs and inputs for direct HTTP access (3D model viewer and previews)
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS)), name="outputs")
app.mount("/inputs", StaticFiles(directory=str(INPUTS)), name="inputs")

@app.get("/api/logs")
def get_logs():
    return {"status": "ok"}


@app.get("/api/status")
def get_status():
    """Check connectivity to Blender, Ollama local vision model, and TripoSR neural 3D engine."""
    blender_ok = False
    blender_version = None
    try:
        ping_res = blender_client.send("ping", timeout=2)
        blender_ok = ping_res.get("pong", False)
        blender_version = ping_res.get("blender")
    except Exception:
        blender_ok = False

    ollama_models = vlm.get_available_models()
    active_vlm = vlm.resolve_model()

    triposr_available = False
    triposr_device = "cpu"
    try:
        from mcp_server.config import TRIPOSR_PYTHON, TRIPOSR_DEVICE
        triposr_available = Path(TRIPOSR_PYTHON).exists()
        triposr_device = TRIPOSR_DEVICE
    except Exception:
        pass

    return {
        "blender": {
            "connected": blender_ok,
            "version": blender_version,
            "port": 9876,
        },
        "vlm": {
            "available": len(ollama_models) > 0,
            "models": ollama_models,
            "active_model": active_vlm,
        },
        "triposr": {
            "available": triposr_available,
            "device": triposr_device,
        }
    }


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """Upload an image file to workspace/inputs/."""
    ext = Path(file.filename or "image.png").suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        logger.warning(f"Rejected upload with unsupported extension: {ext}")
        raise HTTPException(status_code=400, detail="Only PNG, JPG, JPEG, and WebP images are supported.")

    timestamp = int(time.time())
    safe_stem = "".join(c for c in Path(file.filename).stem if c.isalnum() or c in ("-", "_")) or "uploaded"
    saved_filename = f"{safe_stem}_{timestamp}{ext}"
    target_path = INPUTS / saved_filename

    with open(target_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = os.path.getsize(target_path)
    logger.info(f"📥 [Upload] Saved {saved_filename} ({file_size:,} bytes) to workspace/inputs/")

    return {
        "filename": saved_filename,
        "path": str(target_path),
        "url": f"/inputs/{saved_filename}",
    }



@app.get("/api/samples")
def get_sample_images():
    """List sample images available in workspace/inputs/."""
    samples = []
    for p in sorted(INPUTS.glob("*.*")):
        if p.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
            samples.append({
                "name": p.name,
                "path": str(p),
                "url": f"/inputs/{p.name}",
            })
    return {"samples": samples}


@app.post("/api/generate")
async def generate_3d(
    image_path: str = Form(...),
    left_image_path: Optional[str] = Form(None),
    right_image_path: Optional[str] = Form(None),
    back_image_path: Optional[str] = Form(None),
    mc_resolution: int = Form(256),
    no_remove_bg: bool = Form(False),
    bake_texture: bool = Form(False),
    foreground_ratio: float = Form(0.88),
    send_to_blender: bool = Form(True),
    target_size: float = Form(2.0),
):
    """Run 100% offline 3D reconstruction with TripoSR and auto-import to Blender."""
    img_file = Path(image_path).expanduser().resolve()
    if not img_file.is_file():
        candidate1 = INPUTS / Path(image_path).name
        candidate2 = WORKSPACE / image_path.lstrip("/")
        if candidate1.is_file():
            img_file = candidate1
        elif candidate2.is_file():
            img_file = candidate2
        else:
            logger.error(f"❌ [Generate] Image file not found at: {image_path}")
            raise HTTPException(status_code=404, detail=f"Image not found at {image_path}")

    def _find_img(p_str):
        if not p_str: return None
        cand = Path(p_str).expanduser().resolve()
        if cand.is_file(): return cand
        c1 = INPUTS / Path(p_str).name
        if c1.is_file(): return c1
        c2 = WORKSPACE / p_str.lstrip("/")
        if c2.is_file(): return c2
        return None

    left_file = _find_img(left_image_path)
    right_file = _find_img(right_image_path)
    back_file = _find_img(back_image_path)

    import math
    try:
        foreground_ratio = float(foreground_ratio)
        if math.isnan(foreground_ratio) or foreground_ratio <= 0.05 or foreground_ratio > 1.0:
            foreground_ratio = 0.88
    except Exception:
        foreground_ratio = 0.88
    start_time = time.time()
    try:
        glb_path = triposr.run(
            str(img_file),
            mc_resolution=mc_resolution,
            no_remove_bg=no_remove_bg,
            bake_texture=bake_texture,
            foreground_ratio=foreground_ratio,
        )
    except Exception as e:
        logger.error(f"❌ [Generate] 3D reconstruction error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"3D reconstruction failed: {str(e)}")

    elapsed = round(time.time() - start_time, 2)
    relative_glb = Path(glb_path).relative_to(OUTPUTS)
    glb_url = f"/outputs/{relative_glb}"

    blender_result = None
    if send_to_blender:
        try:
            logger.info("📦 [Blender] Dispatching model to Blender socket (127.0.0.1:9876)...")
            blender_result = blender_client.send(
                "import_model",
                {"path": glb_path, "normalize": True, "target_size": target_size},
                timeout=120,
            )
            logger.info(f"✅ [Blender] Imported: {blender_result.get('imported', [])}")
            if any([left_file, right_file, back_file]):
                logger.info("📐 [Blender] Setting up multi-view reference planes (Front, Left, Right, Back)...")
                ref_res = blender_client.send(
                    "setup_reference_views",
                    {
                        "front_path": str(img_file),
                        "left_path": str(left_file) if left_file else None,
                        "right_path": str(right_file) if right_file else None,
                        "back_path": str(back_file) if back_file else None,
                    }
                )
                blender_result["reference_planes"] = ref_res.get("reference_planes", [])
        except Exception as e:
            logger.warning(f"⚠️ [Blender] Auto-import skipped: {str(e)}")
            blender_result = {"error": str(e)}

    return {
        "status": "success",
        "glb_path": glb_path,
        "glb_url": glb_url,
        "elapsed_seconds": elapsed,
        "blender": blender_result,
    }



@app.post("/api/blender/polish")
def polish_blender_mesh(object_name: str = Form(None)):
    """Apply photorealistic mesh polish, smooth shading, subdivision, weighted normals & studio lighting."""
    try:
        logger.info("✨ [Blender] Applying surface polish, organic smoothing, weighted normals & studio lighting...")
        res = blender_client.send("polish_mesh", {"object_name": object_name, "subdivide": False} if object_name else {"subdivide": False})
        logger.info(f"✅ [Blender] Polished: {res}")
        
        # Auto-render updated view
        filename = f"render_polished_{int(time.time())}.png"
        target_path = str(OUTPUTS / filename)
        render_res = blender_client.send("render_preview", {"path": target_path, "width": 768, "height": 768})
        logger.info(f"📸 [Blender] Polished render snapshot saved: {filename}")
        return {
            "status": "ok",
            "result": res,
            "render_path": target_path,
            "render_url": f"/outputs/{filename}",
        }
    except Exception as e:
        logger.error(f"❌ [Blender] Polish failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/blender/rotate")
def rotate_blender_mesh(
    axis: str = Form("X"),
    angle: float = Form(90.0),
    object_name: str = Form(None),
):
    """Rotate object by specified degrees around X, Y, or Z axis in Blender and re-align floor."""
    try:
        logger.info(f"🔄 [Blender] Rotating object around {axis} by {angle}°...")
        params = {"axis": axis, "angle": angle}
        if object_name:
            params["object_name"] = object_name
        res = blender_client.send("rotate_object", params)
        logger.info(f"✅ [Blender] Rotated: {res}")
        return {"status": "ok", "result": res}
    except Exception as e:
        logger.error(f"❌ [Blender] Rotate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/send_to_blender")
def import_to_blender(
    model_path: str = Form(...),
    target_size: float = Form(2.0),
):
    """Import an existing .glb model directly into Blender."""
    try:
        logger.info(f"📦 [Blender] Importing GLB from {model_path}...")
        res = blender_client.send(
            "import_model",
            {"path": model_path, "normalize": True, "target_size": target_size},
        )
        logger.info(f"✅ [Blender] Imported: {res}")
        return {"status": "ok", "result": res}
    except Exception as e:
        logger.error(f"❌ [Blender] Import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/blender/render")
def render_blender_preview(width: int = 768, height: int = 768):
    """Trigger Blender viewport camera render."""
    try:
        filename = f"render_{int(time.time())}.png"
        target_path = str(OUTPUTS / filename)
        logger.info(f"📸 [Blender] Rendering EEVEE Next viewport snapshot ({width}x{height})...")
        blender_client.send("render_preview", {"path": target_path, "width": width, "height": height})
        logger.info(f"✅ [Blender] Render snapshot saved: {filename}")
        return {
            "status": "ok",
            "render_path": target_path,
            "render_url": f"/outputs/{filename}",
        }
    except Exception as e:
        logger.error(f"❌ [Blender] Viewport render failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/blender/clear")
def clear_blender_scene():
    """Clear all objects from Blender scene and reset outputs."""
    try:
        logger.info("🧹 [Blender] Clearing all objects from scene...")
        res = blender_client.send("clear_scene")
        import shutil
        for item in OUTPUTS.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                elif item.is_file():
                    item.unlink(missing_ok=True)
            except Exception:
                pass
        logger.info(f"✅ [Blender] Scene & output cache cleared: {res}")
        return {"status": "ok", "result": res}
    except Exception as e:
        logger.error(f"❌ [Blender] Clear failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/blender/material")
def apply_material(
    object_name: str = Form(...),
    r: float = Form(0.8),
    g: float = Form(0.8),
    b: float = Form(0.8),
):
    """Apply a Principled BSDF color material to an object."""
    try:
        logger.info(f"🎨 [Blender] Applying color ({r:.2f}, {g:.2f}, {b:.2f}) to {object_name}...")
        res = blender_client.send("apply_material", {"object_name": object_name, "color": [r, g, b]})
        logger.info(f"✅ [Blender] Material applied: {res}")
        return {"status": "ok", "result": res}
    except Exception as e:
        logger.error(f"❌ [Blender] Material failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/blender/scene")
def get_scene():
    """Get active scene objects."""
    try:
        res = blender_client.send("scene_info")
        return {"status": "ok", "scene": res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vlm/generate")
async def vlm_generate_3d(
    image_path: str = Form(...),
    engine: str = Form("trellis"),
    hf_token: Optional[str] = Form(None),
    left_image_path: Optional[str] = Form(None),
    right_image_path: Optional[str] = Form(None),
    back_image_path: Optional[str] = Form(None),
):
    """Run full End-to-End AI Vision 3D Reconstruction using local Qwen2.5-VL and Blender."""
    def _find_img(p_str):
        if not p_str: return None
        cand = Path(p_str).expanduser().resolve()
        if cand.is_file(): return cand
        c1 = INPUTS / Path(p_str).name
        if c1.is_file(): return c1
        c2 = WORKSPACE / p_str.lstrip("/")
        if c2.is_file(): return c2
        return None

    img_file = _find_img(image_path)
    if not img_file:
        raise HTTPException(status_code=404, detail=f"Image not found at {image_path}")

    left_file = _find_img(left_image_path)
    right_file = _find_img(right_image_path)
    back_file = _find_img(back_image_path)

    active_token = (hf_token or "").strip() or os.getenv("HF_TOKEN", "").strip()
    if not active_token and (ROOT / ".env").exists():
        try:
            from dotenv import dotenv_values
            active_token = (dotenv_values(ROOT / ".env").get("HF_TOKEN") or "").strip()
        except Exception:
            pass

    try:
        res = vlm.generate_3d_from_image(
            str(img_file),
            engine=engine,
            hf_token=active_token,
            left_path=str(left_file) if left_file else "",
            right_path=str(right_file) if right_file else "",
            back_path=str(back_file) if back_file else "",
        )
        return res
    except Exception as e:
        logger.error(f"❌ [VLM-3D] Reconstruction failed: {e}")
        raise HTTPException(status_code=500, detail=f"VLM 3D Reconstruction failed: {str(e)}")


@app.post("/api/vlm/analyze")
def vlm_analyze(image_path: str = Form(...)):
    """Analyze image using local Vision LLM to extract 3D parameters and description."""
    try:
        cand = Path(image_path).expanduser().resolve()
        if not cand.is_file():
            c1 = INPUTS / Path(image_path).name
            if c1.is_file():
                cand = c1
            else:
                cand = WORKSPACE / image_path.lstrip("/")
        if not cand.is_file():
            raise HTTPException(status_code=404, detail=f"Image not found at {image_path}")

        analysis = vlm.analyze_for_3d(str(cand))
        colors = vlm.extract_dominant_colors(str(cand))
        return {"status": "ok", "analysis": analysis, "colors": colors}
    except Exception as e:
        logger.error(f"❌ [VLM] Analyze failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vlm/describe")
def vlm_describe(image_path: str = Form(...)):
    """Ask Ollama vision model to describe the input image for 3D modeling."""
    try:
        logger.info(f"🔬 [VLM] Inspecting image {Path(image_path).name} with local vision LLM...")
        desc = vlm.describe(image_path)
        logger.info("✅ [VLM] Assessment complete")
        return {"status": "ok", "description": desc}
    except Exception as e:
        logger.error(f"❌ [VLM] Describe failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vlm/critique")
def vlm_critique(render_path: str = Form(...)):
    """Ask Ollama vision model to inspect the Blender render for 3D quality and defects."""
    try:
        logger.info(f"🔬 [VLM] Critiquing 3D render {Path(render_path).name} with local vision LLM...")
        critique = vlm.compare("", render_path)
        logger.info("✅ [VLM] 3D critique complete")
        return {"status": "ok", "critique": critique}
    except Exception as e:
        logger.error(f"❌ [VLM] Critique failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/settings/token")
def save_hf_token(token: str = Form(...)):
    """Save Hugging Face user access token to .env for persistent priority compute."""
    clean_token = token.strip()
    env_file = ROOT / ".env"
    lines = []
    if env_file.exists():
        with open(env_file, "r") as f:
            for l in f:
                if not l.startswith("HF_TOKEN="):
                    lines.append(l.rstrip("\r\n"))
    lines.append(f"HF_TOKEN={clean_token}")
    with open(env_file, "w") as f:
        f.write("\n".join(lines) + "\n")
    os.environ["HF_TOKEN"] = clean_token
    logger.info("🔑 [Settings] Hugging Face Access Token saved successfully!")
    masked = (clean_token[:4] + "..." + clean_token[-4:]) if len(clean_token) > 8 else "***"
    return {"status": "ok", "message": "Token saved successfully", "masked": masked}


@app.get("/api/settings/token")
def get_hf_token():
    """Get current Hugging Face token configuration status."""
    token = os.getenv("HF_TOKEN", "")
    if not token and (ROOT / ".env").exists():
        try:
            from dotenv import dotenv_values
            token = dotenv_values(ROOT / ".env").get("HF_TOKEN", "")
            if token:
                os.environ["HF_TOKEN"] = token
        except Exception:
            pass
    is_set = bool(token and token.startswith("hf_"))
    masked = (token[:4] + "..." + token[-4:]) if is_set and len(token) > 8 else ""
    return {"configured": is_set, "masked": masked}


@app.get("/api/models/latest")
def get_latest_model():
    """Returns URLs for the latest generated 3D model if an object is present in Blender."""
    try:
        has_mesh = False
        try:
            info = blender_client.send("scene_info", timeout=2)
            has_mesh = any(o.get("type") == "MESH" for o in info.get("objects", []))
        except Exception:
            pass

        if not has_mesh:
            return {"has_model": False, "glb_url": None, "render_url": None, "name": None}

        glbs = sorted(OUTPUTS.glob("**/*.glb"), key=lambda p: p.stat().st_mtime, reverse=True)
        renders = sorted(OUTPUTS.glob("**/studio_render.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        latest_glb = f"/outputs/{glbs[0].relative_to(OUTPUTS)}" if glbs else None
        latest_render = f"/outputs/{renders[0].relative_to(OUTPUTS)}" if renders else None
        latest_name = glbs[0].parent.parent.name if glbs and glbs[0].name in ["model.glb", "mesh.glb"] else (glbs[0].stem if glbs else None)
        return {
            "has_model": bool(latest_glb),
            "glb_url": latest_glb,
            "render_url": latest_render,
            "name": latest_name,
        }
    except Exception as e:
        return {"has_model": False, "error": str(e)}


# Serve Web UI
WEB_UI_DIR = ROOT / "web_ui"
if WEB_UI_DIR.exists():
    @app.get("/")
    def serve_index():
        return FileResponse(
            WEB_UI_DIR / "index.html",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    app.mount("/static", StaticFiles(directory=str(WEB_UI_DIR)), name="static")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"==========================================================")
    logger.info(f"🚀 Blender Image-to-3D Studio starting at http://127.0.0.1:{port}")
    logger.info(f"• All execution logs will appear live in this terminal")
    logger.info(f"==========================================================")
    uvicorn.run("web_app:app", host="127.0.0.1", port=port, reload=True)
