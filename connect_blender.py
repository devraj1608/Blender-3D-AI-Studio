from __future__ import annotations
#!/usr/bin/env python3
"""
Universal Cross-Platform Blender Connector & Launcher
Works identically on macOS, Windows, and Linux.

Usage:
    python connect_blender.py          # Launches Blender with the bridge
    python connect_blender.py --check  # Checks if Blender bridge is reachable on port 9876
"""

import sys
import os
import glob
import socket
import platform
import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIDGE_SCRIPT = ROOT / "blender_addon" / "mcp_bridge.py"
HOST = "127.0.0.1"
PORT = 9876


def is_bridge_running() -> bool:
    """Test if Blender bridge is currently responding on port 9876."""
    try:
        with socket.create_connection((HOST, PORT), timeout=1.5) as s:
            s.sendall(b'{"type": "ping", "params": {}}\n')
            res = json.loads(s.recv(4096).decode("utf-8"))
            if res.get("status") == "ok":
                print(f"✅ Blender Bridge is ACTIVE! Version: {res['result'].get('blender', 'Unknown')}")
                return True
    except Exception:
        pass
    return False


def find_blender() -> str | None:
    """Locate Blender binary across macOS, Windows, and Linux."""
    os_name = platform.system()

    # 1. Check in PATH first
    path_blender = subprocess.run(["which" if os_name != "Windows" else "where", "blender"], capture_output=True, text=True)
    if path_blender.returncode == 0:
        found = path_blender.stdout.splitlines()[0].strip()
        if os.path.exists(found):
            return found

    # 2. macOS common paths
    if os_name == "Darwin":
        mac_candidates = [
            "/Applications/Blender.app/Contents/MacOS/Blender",
            str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
        ]
        for p in mac_candidates:
            if os.path.exists(p):
                return p

    # 3. Windows common paths
    elif os_name == "Windows":
        win_globs = [
            r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Blender Foundation\Blender *\blender.exe"),
            r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
        ]
        for pattern in win_globs:
            matches = glob.glob(pattern)
            if matches:
                # Return latest version
                matches.sort()
                return matches[-1]

    # 4. Linux common paths
    elif os_name == "Linux":
        linux_candidates = [
            "/usr/bin/blender",
            "/snap/bin/blender",
            "/usr/local/bin/blender",
            "/var/lib/flatpak/exports/bin/org.blender.Blender",
        ]
        for p in linux_candidates:
            if os.path.exists(p):
                return p

    return None


def main():
    if "--check" in sys.argv:
        if is_bridge_running():
            sys.exit(0)
        print("⚠️ Blender bridge is not reachable on port 9876.")
        sys.exit(1)

    print("==========================================================")
    print("🔌 Blender Universal Connector (Mac, Windows, Linux)")
    print("==========================================================")

    if is_bridge_running():
        print("Blender is already running and connected on port 9876!")
        return

    blender_bin = find_blender()
    if not blender_bin:
        print("❌ Could not automatically locate Blender.")
        print("\nPlease follow one of these simple connection options:")
        print("1. Open Blender manually.")
        print(f"2. Go to the 'Scripting' tab, open: {BRIDGE_SCRIPT}")
        print("3. Click the 'Run Script' button (▶️).")
        print("\nOr install Blender from https://www.blender.org/download/")
        sys.exit(1)

    print(f"🚀 Found Blender at: {blender_bin}")
    print(f"🔌 Launching Blender with bridge script ({BRIDGE_SCRIPT})...")

    # Launch detached GUI process
    if platform.system() == "Windows":
        subprocess.Popen([blender_bin, "--python", str(BRIDGE_SCRIPT)], creationflags=subprocess.DETACHED_PROCESS)
    else:
        subprocess.Popen([blender_bin, "--python", str(BRIDGE_SCRIPT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("✅ Blender launched! Bridge will listen on 127.0.0.1:9876.")


if __name__ == "__main__":
    main()
