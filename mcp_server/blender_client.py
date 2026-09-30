from __future__ import annotations
import json
import socket
import logging
try:
    from .config import BLENDER_HOST, BLENDER_PORT
except (ImportError, ValueError):
    try:
        from mcp_server.config import BLENDER_HOST, BLENDER_PORT
    except ImportError:
        from config import BLENDER_HOST, BLENDER_PORT

logger = logging.getLogger("studio.blender")


def send(cmd_type: str, params: dict | None = None, timeout: int = 600) -> dict:
    payload = {"type": cmd_type, "params": params or {}}
    logger.debug(f"🔌 [BlenderBridge] Sending command '{cmd_type}' to {BLENDER_HOST}:{BLENDER_PORT}")
    try:
        with socket.create_connection((BLENDER_HOST, BLENDER_PORT), timeout=10) as s:
            s.settimeout(timeout)
            data_to_send = (json.dumps(payload) + "\n").encode("utf-8")
            s.sendall(data_to_send)
            buf = b""
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
    except (ConnectionRefusedError, socket.timeout) as e:
        raise RuntimeError(
            f"Cannot reach Blender on {BLENDER_HOST}:{BLENDER_PORT}. "
            "Please ensure Blender is open and the 'Image3D MCP Bridge' add-on is enabled."
        ) from e

    if not buf:
        raise RuntimeError("Empty response received from Blender bridge.")

    res = json.loads(buf.decode("utf-8"))
    if res.get("status") != "ok":
        raise RuntimeError(res.get("message", "Unknown Blender error occurred"))
    return res["result"]
