bl_info = {
    "name": "Image3D MCP Bridge",
    "author": "Antigravity & You",
    "version": (1, 1, 0),
    "blender": (3, 6, 0),
    "location": "3D View > Sidebar > MCP",
    "description": "Cross-platform Socket bridge so an MCP server / Web Studio can control Blender",
    "category": "Interface",
}

import bpy
import socket
import threading
import json
import queue
import traceback
import os
import math
from mathutils import Vector

HOST, PORT = "127.0.0.1", 9876     # localhost only
_cmd_q = queue.Queue()
_stop = threading.Event()
_thread = None
_sock = None
_start_lock = threading.Lock()


# ---------- helpers ----------
def _mesh_objects(objs):
    return [o for o in objs if o.type == "MESH"]


def _normalize(objs, target_size=2.0):
    """Center at origin, sit on the floor, scale so the largest side == target_size."""
    meshes = _mesh_objects(objs)
    if not meshes:
        return

    # Auto-upright check: glTF imports often have +Y as up, whereas Blender uses +Z as up.
    # If the mesh height is along Y (dim_y > dim_z), rotate +90 deg around X to stand straight up.
    corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    dim_y = max(c.y for c in corners) - min(c.y for c in corners)
    dim_z = max(c.z for c in corners) - min(c.z for c in corners)
    if dim_y > dim_z * 1.15:
        for o in objs:
            if o.parent is None:
                o.rotation_euler.x += math.radians(90)
        bpy.context.view_layer.update()
        corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    mn = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    mx = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    size = max((mx - mn).x, (mx - mn).y, (mx - mn).z) or 1.0
    factor = target_size / size
    center = (mn + mx) / 2
    for o in objs:
        if o.parent is None:
            o.location = (o.location - center) * factor + Vector((0, 0, 0))
            o.scale = o.scale * factor
    bpy.context.view_layer.update()
    corners = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    min_z = min(c.z for c in corners)
    for o in objs:
        if o.parent is None:
            o.location.z -= min_z


def _polish_imported_object(obj):
    """Automatically enhance imported mesh: smooth shading, weighted normals, realistic shader, and true-to-image color vibrance."""
    if obj.type != "MESH":
        return

    # 1. Ensure sRGB accurate color reproduction without AgX clipping
    bpy.context.scene.view_settings.view_transform = 'Standard'
    bpy.context.scene.view_settings.look = 'Medium High Contrast'

    # 2. Enable smooth shading on all polygon faces
    for poly in obj.data.polygons:
        poly.use_smooth = True

    # 3. Add Weighted Normal modifier for crisp, realistic surface lighting
    if "MCP_WeightedNormal" not in obj.modifiers:
        wn = obj.modifiers.new(name="MCP_WeightedNormal", type="WEIGHTED_NORMAL")
        wn.keep_sharp = True

    # 4. Configure realistic Principled BSDF shader properties and boost color saturation
    for mat in obj.data.materials:
        if mat and mat.use_nodes:
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            bsdf = nodes.get("Principled BSDF")
            if bsdf:
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = 0.38
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.45
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = 0.0

                base_input = bsdf.inputs.get("Base Color")
                if base_input and base_input.is_linked:
                    from_socket = base_input.links[0].from_socket
                    if from_socket.node.type in ("TEX_IMAGE", "VERTEX_COLOR", "ATTRIBUTE"):
                        if not nodes.get("MCP_ColorBoost"):
                            hsv = nodes.new(type="ShaderNodeHueSaturation")
                            hsv.name = "MCP_ColorBoost"
                            hsv.inputs["Saturation"].default_value = 1.25
                            hsv.inputs["Value"].default_value = 1.05
                            hsv.inputs["Hue"].default_value = 0.50
                            links.new(from_socket, hsv.inputs["Color"])
                            links.new(hsv.outputs["Color"], base_input)


def _ensure_camera_and_light():
    scene = bpy.context.scene
    if scene.camera is None:
        cam_data = bpy.data.cameras.new("MCP_Camera")
        cam = bpy.data.objects.new("MCP_Camera", cam_data)
        scene.collection.objects.link(cam)
        cam.location = (4.5, -4.5, 3.2)
        cam.rotation_euler = (math.radians(65), 0, math.radians(45))
        scene.camera = cam
    if not any(o.type == "LIGHT" for o in scene.objects):
        light_data = bpy.data.lights.new("MCP_Sun", type="SUN")
        light_data.energy = 3.5
        light = bpy.data.objects.new("MCP_Sun", light_data)
        scene.collection.objects.link(light)
        light.rotation_euler = (math.radians(50), 0, math.radians(30))


# ---------- command handlers (run on main thread) ----------
def h_ping(p):
    return {"pong": True, "blender": bpy.app.version_string}


def h_scene_info(p):
    return {
        "blender": bpy.app.version_string,
        "objects": [
            {"name": o.name, "type": o.type, "location": [round(v, 3) for v in o.location],
             "dimensions": [round(v, 3) for v in o.dimensions]}
            for o in bpy.context.scene.objects
        ],
    }


def h_import_model(p):
    path = p["path"]
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    
    # Automatically remove Blender's default startup cube so it doesn't block models
    default_cube = bpy.data.objects.get("Cube")
    if default_cube and default_cube.type == "MESH":
        bpy.data.objects.remove(default_cube, do_unlink=True)

    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    with open(path, "rb") as f:
        magic = f.read(4)

    if ext in (".glb", ".gltf") and magic == b"glTF":
        bpy.ops.import_scene.gltf(filepath=path)
    elif ext == ".obj" or (ext in (".glb", ".gltf") and magic != b"glTF"):
        # Auto-detect standard OBJ or misnamed OBJ
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=path)
        else:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    new = [o for o in bpy.data.objects if o not in before]
    
    # Auto-center and ground on floor
    if p.get("normalize", True):
        _normalize(new, float(p.get("target_size", 2.0)))

    # Auto-polish imported meshes for realism
    for o in new:
        _polish_imported_object(o)

    names = [o.name for o in new]
    return {"imported": names}


def h_execute_code(p):
    ns = {"bpy": bpy, "math": math, "Vector": Vector}
    exec(p["code"], ns)
    return {"executed": True, "result": ns.get("result")}


def h_apply_material(p):
    obj = bpy.data.objects.get(p["object_name"])
    if obj is None or obj.type != "MESH":
        raise ValueError("Mesh object not found")
    color = list(p.get("color", [0.8, 0.8, 0.8])) + [1.0]
    mat = bpy.data.materials.new(name=f"MCP_{obj.name}")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color[:4]
        if "Roughness" in bsdf.inputs:
            bsdf.inputs["Roughness"].default_value = 0.45
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return {"material": mat.name}


def h_render_preview(p):
    scene = bpy.context.scene
    _ensure_camera_and_light()
    path = p["path"]
    scene.render.filepath = path
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x = int(p.get("width", 768))
    scene.render.resolution_y = int(p.get("height", 768))
    engines = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else (
        "BLENDER_EEVEE" if "BLENDER_EEVEE" in engines else scene.render.engine)
    bpy.ops.render.render(write_still=True)
    return {"path": path}


def h_export_model(p):
    path = p["path"]
    ext = os.path.splitext(path)[1].lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.export_scene.gltf(filepath=path)
    elif ext == ".fbx":
        bpy.ops.export_scene.fbx(filepath=path)
    elif ext == ".obj":
        if hasattr(bpy.ops.wm, "obj_export"):
            bpy.ops.wm.obj_export(filepath=path)
        else:
            bpy.ops.export_scene.obj(filepath=path)
    elif ext == ".stl":
        if hasattr(bpy.ops.wm, "stl_export"):
            bpy.ops.wm.stl_export(filepath=path)
        else:
            bpy.ops.export_mesh.stl(filepath=path)
    else:
        raise ValueError(f"Unsupported format: {ext}")
    return {"path": path}


def h_clear_scene(p):
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    return {"cleared": True}


def _ensure_studio_lighting():
    scene = bpy.context.scene
    coll = scene.collection
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'Medium High Contrast'

    if scene.world and scene.world.use_nodes:
        bg = scene.world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Color"].default_value = (0.05, 0.05, 0.06, 1.0)
            bg.inputs["Strength"].default_value = 1.0

    if not bpy.data.objects.get("Studio_KeyLight"):
        ld = bpy.data.lights.new("KeyLight_Data", type="AREA")
        ld.energy = 80.0
        ld.size = 3.0
        ld.color = (1.0, 1.0, 1.0)
        obj = bpy.data.objects.new("Studio_KeyLight", ld)
        coll.objects.link(obj)
        obj.location = (2.5, -2.5, 3.5)
    else:
        obj = bpy.data.objects.get("Studio_KeyLight")
        obj.data.energy = 80.0
        obj.data.color = (1.0, 1.0, 1.0)

    if not bpy.data.objects.get("Studio_FillLight"):
        ld = bpy.data.lights.new("FillLight_Data", type="AREA")
        ld.energy = 45.0
        ld.size = 4.0
        ld.color = (1.0, 1.0, 1.0)
        obj = bpy.data.objects.new("Studio_FillLight", ld)
        coll.objects.link(obj)
        obj.location = (-2.5, -2.0, 2.0)
    else:
        obj = bpy.data.objects.get("Studio_FillLight")
        obj.data.energy = 45.0
        obj.data.color = (1.0, 1.0, 1.0)

    if not bpy.data.objects.get("Studio_RimLight"):
        ld = bpy.data.lights.new("RimLight_Data", type="POINT")
        ld.energy = 50.0
        ld.color = (1.0, 1.0, 1.0)
        obj = bpy.data.objects.new("Studio_RimLight", ld)
        coll.objects.link(obj)
        obj.location = (0.0, 3.2, 2.8)
    else:
        obj = bpy.data.objects.get("Studio_RimLight")
        obj.data.energy = 50.0
        obj.data.color = (1.0, 1.0, 1.0)


def h_polish_mesh(p):
    """Apply photorealistic mesh polish, smooth shading, subdivision, weighted normals, and studio lighting."""
    target_name = p.get("object_name")
    meshes = [bpy.data.objects.get(target_name)] if target_name else [o for o in bpy.context.scene.objects if o.type == "MESH"]
    meshes = [m for m in meshes if m is not None]
    if not meshes:
        raise ValueError("No mesh objects found in Blender scene to polish.")

    # 1. Studio Lighting & Camera Framing
    _ensure_studio_lighting()
    scene = bpy.context.scene
    if not scene.camera:
        cam_d = bpy.data.cameras.new("Studio_Camera")
        cam = bpy.data.objects.new("Studio_Camera", cam_d)
        scene.collection.objects.link(cam)
        scene.camera = cam

    all_coords = [o.matrix_world @ Vector(corner) for o in meshes for corner in o.bound_box]
    if all_coords:
        center = sum(all_coords, Vector()) / len(all_coords)
        max_dim = max(max(o.dimensions) for o in meshes) or 2.0
        dist = max_dim * 2.2
        scene.camera.location = (center.x + dist * 0.7, center.y - dist * 0.7, center.z + dist * 0.5)
        direction = center - scene.camera.location
        rot_quat = direction.to_track_quat('-Z', 'Y')
        scene.camera.rotation_euler = rot_quat.to_euler()

    # 2. Polish all mesh objects
    modified = []
    for obj in meshes:
        for poly in obj.data.polygons:
            poly.use_smooth = True

        # Remove voxel stepping from marching cubes
        if "MCP_Smooth" in obj.modifiers:
            obj.modifiers.remove(obj.modifiers["MCP_Smooth"])
        sm = obj.modifiers.new(name="MCP_Smooth", type="SMOOTH")
        sm.factor = float(p.get("smooth_factor", 0.55))
        sm.iterations = int(p.get("smooth_iterations", 3))

        # Weighted Normal for crisp realistic lighting reflections
        if "MCP_WeightedNormal" in obj.modifiers:
            obj.modifiers.remove(obj.modifiers["MCP_WeightedNormal"])
        wn = obj.modifiers.new(name="MCP_WeightedNormal", type="WEIGHTED_NORMAL")
        wn.keep_sharp = True
        wn.weight = 100

        # Subsurf only for low-poly meshes (< 25k polys) to avoid multi-million polygon slowdowns
        if p.get("subdivide", False) and len(obj.data.polygons) < 25000:
            if "MCP_Subsurf" in obj.modifiers:
                obj.modifiers.remove(obj.modifiers["MCP_Subsurf"])
            sub = obj.modifiers.new(name="MCP_Subsurf", type="SUBSURF")
            sub.levels = 1
            sub.render_levels = 1
        elif "MCP_Subsurf" in obj.modifiers:
            obj.modifiers.remove(obj.modifiers["MCP_Subsurf"])

        # PBR Shading setup
        for mat in obj.data.materials:
            if mat and mat.use_nodes:
                bsdf = mat.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    if "Roughness" in bsdf.inputs:
                        bsdf.inputs["Roughness"].default_value = 0.38
                    if "IOR" in bsdf.inputs:
                        bsdf.inputs["IOR"].default_value = 1.45
                    if "Metallic" in bsdf.inputs:
                        bsdf.inputs["Metallic"].default_value = 0.0
                    if "Specular IOR Level" in bsdf.inputs:
                        bsdf.inputs["Specular IOR Level"].default_value = 0.5

        modified.append(obj.name)

    bpy.context.view_layer.update()
    return {"polished": modified, "studio_lighting": True, "camera_framed": True}


def h_rotate_object(p):
    """Rotate object by specified degrees around X, Y, or Z axis and re-align to floor."""
    axis = p.get("axis", "X").upper()
    angle_deg = float(p.get("angle", 90.0))
    target_name = p.get("object_name")
    meshes = [bpy.data.objects.get(target_name)] if target_name else [o for o in bpy.context.scene.objects if o.type == "MESH"]
    meshes = [m for m in meshes if m is not None]
    if not meshes:
        raise ValueError("No mesh objects found in Blender scene to rotate.")

    angle_rad = math.radians(angle_deg)
    for obj in meshes:
        if axis == "X":
            obj.rotation_euler.x += angle_rad
        elif axis == "Y":
            obj.rotation_euler.y += angle_rad
        elif axis == "Z":
            obj.rotation_euler.z += angle_rad

    bpy.context.view_layer.update()
    # Re-ground on floor after rotating
    _normalize(meshes, target_size=max(max(o.dimensions) for o in meshes) or 2.0)
    return {"rotated": [m.name for m in meshes], "axis": axis, "angle": angle_deg}



def h_setup_reference_views(p):
    """Set up Front, Left, Right, Back reference images in Blender 3D viewport with alpha transparency."""
    views = {
        "Front": (p.get("front_path"), (0, -1.8, 0.45), (math.radians(90), 0, 0)),
        "Left": (p.get("left_path"), (-1.8, 0, 0.45), (math.radians(90), 0, math.radians(-90))),
        "Right": (p.get("right_path"), (1.8, 0, 0.45), (math.radians(90), 0, math.radians(90))),
        "Back": (p.get("back_path"), (0, 1.8, 0.45), (math.radians(90), 0, math.radians(180))),
    }
    created = []
    for name, (img_path, loc, rot) in views.items():
        if img_path and os.path.isfile(img_path):
            old_empty = bpy.data.objects.get(f"Ref_{name}")
            if old_empty:
                bpy.data.objects.remove(old_empty, do_unlink=True)
            try:
                empty_data = bpy.data.images.load(img_path, check_existing=True)
                empty = bpy.data.objects.new(f"Ref_{name}", None)
                empty.empty_display_type = 'IMAGE'
                empty.data = empty_data
                empty.location = loc
                empty.rotation_euler = rot
                empty.empty_display_size = 1.0
                empty.use_empty_image_alpha = True
                empty.color = (1.0, 1.0, 1.0, 0.6)
                if hasattr(empty, 'empty_image_depth'):
                    empty.empty_image_depth = 'BACK'
                bpy.context.scene.collection.objects.link(empty)
                created.append(f"Ref_{name}")
            except Exception as e:
                print(f"Error loading reference {name}: {e}")

    # Set viewport to Material Preview
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'MATERIAL'

    return {"reference_planes": created}



def h_project_texture(p):
    """
    Project reference image directly onto 3D mesh (Camera UV Projection) for 1:1 pixel accuracy.
    Parameters:
      image_path: str (path to reference image)
      object_name: str (optional, defaults to active or first mesh)
    """
    img_path = p.get("image_path")
    if not img_path or not os.path.isfile(img_path):
        raise FileNotFoundError(f"Image not found at {img_path}")

    target_name = p.get("object_name")
    obj = None
    if target_name:
        obj = bpy.data.objects.get(target_name)
    if not obj:
        mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']
        if not mesh_objs:
            raise RuntimeError("No mesh object found in scene")
        obj = mesh_objs[0]

    mesh = obj.data
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()

    # Orientation check: ensure Width is along X, Height along Z, Depth along Y
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    dx = max(c.x for c in corners) - min(c.x for c in corners)
    dy = max(c.y for c in corners) - min(c.y for c in corners)

    # If Y is wider than X, rotate 90 deg around Z
    if dy > dx * 1.15:
        R = Matrix.Rotation(math.radians(90), 4, 'Z')
        mesh.transform(R)
        mesh.update()
        corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]

    min_x, max_x = min(c.x for c in corners), max(c.x for c in corners)
    min_y, max_y = min(c.y for c in corners), max(c.y for c in corners)
    min_z, max_z = min(c.z for c in corners), max(c.z for c in corners)

    width = max(max_x - min_x, 0.001)
    height = max(max_z - min_z, 0.001)

    img = bpy.data.images.load(img_path, check_existing=True)

    if 'Projected_UV' not in mesh.uv_layers:
        uv_layer = mesh.uv_layers.new(name='Projected_UV')
    else:
        uv_layer = mesh.uv_layers['Projected_UV']
    mesh.uv_layers.active = uv_layer

    img_aspect = img.size[0] / max(img.size[1], 1)
    mesh_aspect = width / max(height, 0.001)

    uv_data = uv_layer.data
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            vert_idx = mesh.loops[loop_idx].vertex_index
            v = obj.matrix_world @ mesh.vertices[vert_idx].co
            u = (v.x - min_x) / width
            v_coord = (v.z - min_z) / height

            if mesh_aspect > img_aspect:
                v_coord = (v_coord - 0.5) * (img_aspect / mesh_aspect) + 0.5
            else:
                u = (u - 0.5) * (mesh_aspect / img_aspect) + 0.5

            uv_data[loop_idx].uv = (u, v_coord)

    mat = bpy.data.materials.new(name='Camera_Projected_PBR')
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    n_out = nodes.new(type='ShaderNodeOutputMaterial')
    n_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    n_bsdf.inputs['Roughness'].default_value = 0.35
    links.new(n_bsdf.outputs['BSDF'], n_out.inputs['Surface'])

    n_uv = nodes.new(type='ShaderNodeUVMap')
    n_uv.uv_map = 'Projected_UV'

    n_tex = nodes.new(type='ShaderNodeTexImage')
    n_tex.image = img
    n_tex.extension = 'CLIP'
    n_tex.interpolation = 'Smart'
    links.new(n_uv.outputs['UV'], n_tex.inputs['Vector'])

    base_color_param = p.get("base_color_rgba")
    if base_color_param and len(base_color_param) >= 3:
        r, g, b = [float(c)/255.0 if float(c) > 1.0 else float(c) for c in base_color_param[:3]]
        default_color = (r, g, b, 1.0)
    else:
        default_color = (0.12, 0.12, 0.14, 1.0)

    if len(mesh.color_attributes) > 0:
        n_vc = nodes.new(type='ShaderNodeVertexColor')
        n_vc.layer_name = mesh.color_attributes[0].name
        base_color = n_vc.outputs['Color']
    else:
        n_rgb = nodes.new(type='ShaderNodeRGB')
        n_rgb.outputs['Color'].default_value = default_color
        base_color = n_rgb.outputs['Color']

    # Front facing check: Normal along Y axis (pointing towards -Y)
    n_geom = nodes.new(type='ShaderNodeNewGeometry')
    n_sep = nodes.new(type='ShaderNodeSeparateXYZ')
    links.new(n_geom.outputs['Normal'], n_sep.inputs['Vector'])

    n_map = nodes.new(type='ShaderNodeMapRange')
    n_map.interpolation_type = 'SMOOTHSTEP'
    n_map.inputs['From Min'].default_value = 0.1
    n_map.inputs['From Max'].default_value = -0.1
    n_map.inputs['To Min'].default_value = 0.0
    n_map.inputs['To Max'].default_value = 1.0
    links.new(n_sep.outputs['Y'], n_map.inputs['Value'])

    # Multiply facing by alpha
    n_mult = nodes.new(type='ShaderNodeMath')
    n_mult.operation = 'MULTIPLY'
    links.new(n_map.outputs['Result'], n_mult.inputs[0])
    links.new(n_tex.outputs['Alpha'], n_mult.inputs[1])

    n_mix = nodes.new(type='ShaderNodeMix')
    n_mix.data_type = 'RGBA'
    links.new(n_mult.outputs['Value'], n_mix.inputs['Factor'])
    links.new(base_color, n_mix.inputs['A'])
    links.new(n_tex.outputs['Color'], n_mix.inputs['B'])

    links.new(n_mix.outputs['Result'], n_bsdf.inputs['Base Color'])

    mesh.materials.clear()
    mesh.materials.append(mat)
    return {"projected": True, "object": obj.name}


HANDLERS = {
    "project_texture": h_project_texture,
    "setup_reference_views": h_setup_reference_views,
        "ping": h_ping,
    "scene_info": h_scene_info,
    "import_model": h_import_model,
    "execute_code": h_execute_code,
    "apply_material": h_apply_material,
    "render_preview": h_render_preview,
    "export_model": h_export_model,
    "clear_scene": h_clear_scene,
    "polish_mesh": h_polish_mesh,
    "rotate_object": h_rotate_object,
}


# ---------- main thread timer pump ----------
def _pump():
    while not _cmd_q.empty():
        try:
            cmd, res_q = _cmd_q.get_nowait()
        except queue.Empty:
            break
        fn = HANDLERS.get(cmd.get("type"))
        if fn is None:
            res_q.put({"status": "error", "message": f"Unknown command: {cmd.get('type')}"})
            continue
        try:
            out = fn(cmd.get("params") or {})
            res_q.put({"status": "ok", "result": out})
        except Exception as e:
            traceback.print_exc()
            res_q.put({"status": "error", "message": str(e)})
    return 0.05  # poll 20 times/sec


# ---------- socket listener thread ----------
def _read_line(conn):
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = conn.recv(65536)
        if not chunk:
            break
        buf += chunk
    return buf


def _serve():
    global _sock
    try:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                _sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except Exception:
                pass
        _sock.bind((HOST, PORT))
        _sock.listen(5)
        _sock.settimeout(0.5)
        print(f"Image3D MCP Bridge listening on {HOST}:{PORT}")
    except Exception as e:
        print(f"Image3D MCP Bridge could not bind {HOST}:{PORT}: {e}")
        return

    while not _stop.is_set():
        try:
            conn, _ = _sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        with conn:
            try:
                data = _read_line(conn)
                if not data:
                    continue
                cmd = json.loads(data.decode("utf-8"))
                res_q = queue.Queue()
                _cmd_q.put((cmd, res_q))
                try:
                    res = res_q.get(timeout=600)
                except queue.Empty:
                    res = {"status": "error", "message": "Blender command timed out"}
                conn.sendall((json.dumps(res) + "\n").encode("utf-8"))
            except Exception as e:
                try:
                    conn.sendall((json.dumps({"status": "error", "message": str(e)}) + "\n").encode())
                except Exception:
                    pass
    try:
        if _sock:
            _sock.close()
    except Exception:
        pass


def _start():
    global _thread
    with _start_lock:
        if _thread and _thread.is_alive():
            return
        _stop.clear()
        _thread = threading.Thread(target=_serve, daemon=True, name="Image3D_Bridge")
        _thread.start()


def _shutdown():
    _stop.set()
    global _sock
    try:
        if _sock:
            _sock.close()
    except Exception:
        pass


# ---------- UI ----------
class MCP_PT_panel(bpy.types.Panel):
    bl_label = "Image3D MCP"
    bl_idname = "MCP_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MCP"

    def draw(self, context):
        running = _thread is not None and _thread.is_alive()
        box = self.layout.box()
        box.label(
            text=f"Server running on port {PORT}" if running else "Server stopped",
            icon="CHECKMARK" if running else "ERROR"
        )
        if running:
            box.label(text="Ready for Image-to-3D commands", icon="INFO")


def register():
    try:
        bpy.utils.register_class(MCP_PT_panel)
    except Exception:
        pass  # already registered

    if not bpy.app.timers.is_registered(_pump):
        bpy.app.timers.register(_pump, persistent=True)
    _start()


def unregister():
    _shutdown()
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)
    try:
        bpy.utils.unregister_class(MCP_PT_panel)
    except Exception:
        pass


if __name__ == "__main__":
    register()
