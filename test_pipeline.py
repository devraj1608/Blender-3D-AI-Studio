#!/usr/bin/env python3
"""
Diagnostic test script for Blender Image-to-3D pipeline.
Run this script to verify each layer independently.
"""

import sys
import os
from pathlib import Path

# Add mcp_server to sys.path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "mcp_server"))

import config
import blender_client
from backends import triposr, vlm


def test_blender():
    print("--------------------------------------------------")
    print("1. Testing Blender Bridge (port 9876)...")
    try:
        res = blender_client.send("ping", timeout=3)
        print(f"   ✅ Blender connected! Version: {res.get('blender')}")
        scene = blender_client.send("scene_info")
        print(f"   Scene objects count: {len(scene.get('objects', []))}")
        return True
    except Exception as e:
        print(f"   ⚠️  Blender not reached: {e}")
        print("   (To fix: run ./launch_blender.sh or start Blender with the add-on)")
        return False


def test_triposr():
    print("--------------------------------------------------")
    print("2. Testing TripoSR Engine...")
    test_img = config.INPUTS / "teapot.png"
    if not test_img.exists():
        test_img = config.INPUTS / "chair.png"

    if not test_img.exists():
        print(f"   ❌ No test image found in {config.INPUTS}")
        return False

    print(f"   Input image: {test_img}")
    print(f"   Python executable: {config.TRIPOSR_PYTHON}")
    print(f"   Device: {config.TRIPOSR_DEVICE}")
    try:
        glb_path = triposr.run(str(test_img), mc_resolution=128)
        print(f"   ✅ 3D Model generated successfully: {glb_path}")
        print(f"   File size: {os.path.getsize(glb_path):,} bytes")
        return True
    except Exception as e:
        print(f"   ❌ TripoSR failed: {e}")
        return False


def test_vlm():
    print("--------------------------------------------------")
    print("3. Testing Local Vision LLM (Ollama)...")
    try:
        models = vlm.get_available_models()
        print(f"   Available models in Ollama: {models}")
        active = vlm.resolve_model()
        print(f"   Active model: {active}")
        test_img = config.INPUTS / "chair.png"
        if test_img.exists() and len(models) > 0:
            print("   Running quick image description...")
            desc = vlm.describe(str(test_img))
            print(f"   VLM description preview:\n   {desc[:150]}...")
            return True
        elif len(models) == 0:
            print("   ⚠️  Ollama is running but no vision models are loaded yet.")
            return False
        return True
    except Exception as e:
        print(f"   ⚠️  Ollama error: {e}")
        return False


def main():
    print("==================================================")
    print("🧪 Blender Image-to-3D Pipeline Verification")
    print("==================================================")
    b_ok = test_blender()
    v_ok = test_vlm()
    t_ok = test_triposr()

    print("==================================================")
    print("Summary:")
    print(f"• Blender Bridge: {'✅ OK' if b_ok else '⚠️  OFFLINE'}")
    print(f"• Vision LLM:     {'✅ OK' if v_ok else '⚠️  PENDING'}")
    print(f"• TripoSR Engine: {'✅ OK' if t_ok else '❌ FAILED'}")
    print("==================================================")


if __name__ == "__main__":
    main()
