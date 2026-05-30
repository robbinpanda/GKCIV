from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def after_double_dash() -> list[str]:
    import sys

    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Blender scene for the Taichi MPM squeeze mesh sequence.")
    parser.add_argument("--mesh-dir", type=Path, required=True)
    parser.add_argument("--plates-json", type=Path, required=True)
    parser.add_argument("--output-blend", type=Path, default=Path("taichi_blender_squeeze/outputs/blender/scene/squishy_mpm_cube.blend"))
    parser.add_argument("--render-keyframes", action="store_true")
    parser.add_argument("--preview-dir", type=Path, default=Path("taichi_blender_squeeze/outputs/blender/preview_keyframes"))
    parser.add_argument("--keyframes", type=str, default="0,60,90,150,389")
    parser.add_argument("--resolution", type=str, default="1920x1080")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--engine", type=str, default="CYCLES", choices=["CYCLES", "BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"])
    parser.add_argument("--samples", type=int, default=96)
    return parser.parse_args(after_double_dash())


def parse_resolution(raw: str) -> tuple[int, int]:
    width, height = raw.lower().split("x", maxsplit=1)
    return int(width), int(height)


def parse_keyframes(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def load_plates(path: Path) -> list[dict[str, float]]:
    with path.open("r", encoding="utf-8") as f:
        rows = json.load(f)
    return [{key: float(value) for key, value in row.items()} for row in rows]


def clear_scene(bpy) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def set_principled_input(mat, names: tuple[str, ...], value) -> None:
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        return
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return


def make_soft_material(bpy):
    mat = bpy.data.materials.new("soft translucent blue rubber")
    mat.use_nodes = True
    mat.diffuse_color = (0.55, 0.76, 1.0, 0.96)
    set_principled_input(mat, ("Base Color",), (0.55, 0.76, 1.0, 1.0))
    set_principled_input(mat, ("Roughness",), 0.42)
    set_principled_input(mat, ("Alpha",), 0.96)
    set_principled_input(mat, ("Subsurface Weight", "Subsurface"), 0.25)
    set_principled_input(mat, ("Subsurface Radius",), (1.0, 0.75, 0.55))
    mat.use_screen_refraction = True
    return mat


def make_plate_material(bpy):
    mat = bpy.data.materials.new("frosted acrylic plates")
    mat.use_nodes = True
    mat.diffuse_color = (0.94, 0.97, 1.0, 0.36)
    set_principled_input(mat, ("Base Color",), (0.94, 0.97, 1.0, 0.36))
    set_principled_input(mat, ("Alpha",), 0.36)
    set_principled_input(mat, ("Roughness",), 0.18)
    set_principled_input(mat, ("Transmission Weight", "Transmission"), 0.45)
    set_principled_input(mat, ("IOR",), 1.45)
    mat.blend_method = "BLEND"
    mat.use_screen_refraction = True
    return mat


def make_floor_material(bpy):
    mat = bpy.data.materials.new("warm matte studio floor")
    mat.use_nodes = True
    set_principled_input(mat, ("Base Color",), (0.78, 0.79, 0.76, 1.0))
    set_principled_input(mat, ("Roughness",), 0.62)
    return mat


def import_ply(bpy, path: Path):
    before = set(bpy.data.objects)
    if hasattr(bpy.ops.wm, "ply_import"):
        bpy.ops.wm.ply_import(filepath=str(path))
    else:
        bpy.ops.import_mesh.ply(filepath=str(path))
    created = [obj for obj in bpy.data.objects if obj not in before]
    if not created:
        raise RuntimeError(f"Blender did not import {path}")
    return created[0]


def set_hidden(obj, frame: int, hidden: bool) -> None:
    obj.hide_viewport = hidden
    obj.hide_render = hidden
    obj.keyframe_insert(data_path="hide_viewport", frame=frame)
    obj.keyframe_insert(data_path="hide_render", frame=frame)


def import_mesh_sequence(bpy, mesh_dir: Path, material):
    mesh_files = sorted(mesh_dir.glob("mesh_*.ply"))
    if not mesh_files:
        raise FileNotFoundError(f"No mesh_*.ply files found in {mesh_dir}")

    objects = []
    for path in mesh_files:
        frame = int(path.stem.split("_")[-1])
        obj = import_ply(bpy, path)
        obj.name = f"squishy_mesh_{frame:04d}"
        obj.data.materials.append(material)
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.shade_smooth()
        obj.select_set(False)

        modifier = obj.modifiers.new("soft render smoothing", "WEIGHTED_NORMAL")
        modifier.keep_sharp = True
        objects.append((frame, obj))

    frames = [frame for frame, _obj in objects]
    for idx, (frame, obj) in enumerate(objects):
        next_frame = objects[idx + 1][0] if idx + 1 < len(objects) else frame + 1
        set_hidden(obj, max(min(frames), frame - 1), True)
        set_hidden(obj, frame, False)
        set_hidden(obj, max(frame, next_frame - 1), False)
        set_hidden(obj, next_frame, True)

    return objects


def create_cube(bpy, name: str, location: tuple[float, float, float], scale: tuple[float, float, float], material):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    bevel = obj.modifiers.new("polished bevel", "BEVEL")
    bevel.width = min(scale) * 0.22
    bevel.segments = 6
    obj.modifiers.new("weighted acrylic normals", "WEIGHTED_NORMAL")
    return obj


def create_and_animate_plates(bpy, plates: list[dict[str, float]], material):
    first = plates[0]
    thickness = first["plate_thickness"]
    taichi_span_y = first["plate_y_max"] - first["plate_y_min"]
    taichi_span_z = first["plate_z_max"] - first["plate_z_min"]
    blender_y = 0.5 * (first["plate_z_min"] + first["plate_z_max"])
    blender_z = 0.5 * (first["plate_y_min"] + first["plate_y_max"])

    left = create_cube(
        bpy,
        "left frosted acrylic press plate",
        (first["left_plate"] - thickness * 0.5, blender_y, blender_z),
        (thickness, taichi_span_z, taichi_span_y),
        material,
    )
    right = create_cube(
        bpy,
        "right frosted acrylic press plate",
        (first["right_plate"] + thickness * 0.5, blender_y, blender_z),
        (thickness, taichi_span_z, taichi_span_y),
        material,
    )

    for row in plates:
        frame = int(row["frame"])
        left.location.x = row["left_plate"] - thickness * 0.5
        right.location.x = row["right_plate"] + thickness * 0.5
        left.keyframe_insert(data_path="location", frame=frame)
        right.keyframe_insert(data_path="location", frame=frame)

    return left, right


def create_studio(bpy, floor_material) -> None:
    bpy.ops.mesh.primitive_plane_add(size=0.22, location=(0.05, 0.05, -0.003))
    floor = bpy.context.object
    floor.name = "matte studio surface"
    floor.data.materials.append(floor_material)

    bpy.ops.object.light_add(type="AREA", location=(-0.045, -0.055, 0.16))
    key = bpy.context.object
    key.name = "large softbox key light"
    key.data.energy = 650
    key.data.size = 0.11

    bpy.ops.object.light_add(type="AREA", location=(0.15, 0.11, 0.11))
    rim = bpy.context.object
    rim.name = "thin rim highlight"
    rim.data.energy = 160
    rim.data.size = 0.055

    bpy.ops.object.camera_add(location=(0.145, -0.105, 0.082), rotation=(math.radians(63), 0, math.radians(46)))
    camera = bpy.context.object
    bpy.context.scene.camera = camera
    camera.name = "low product camera"
    camera.data.lens = 80
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = 0.14
    camera.data.dof.aperture_fstop = 6.5


def configure_render(bpy, width: int, height: int, fps: int, engine: str, samples: int, frame_start: int, frame_end: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.fps = fps
    scene.frame_start = frame_start
    scene.frame_end = frame_end
    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    if engine == "CYCLES":
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True


def render_keyframes(bpy, frames: list[int], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.render.image_settings.file_format = "PNG"
    for frame in frames:
        scene.frame_set(frame)
        scene.render.filepath = str(output_dir / f"key_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)


def main() -> None:
    import bpy

    args = parse_args()
    width, height = parse_resolution(args.resolution)
    plates = load_plates(args.plates_json)
    keyframes = parse_keyframes(args.keyframes)

    clear_scene(bpy)
    soft_material = make_soft_material(bpy)
    plate_material = make_plate_material(bpy)
    floor_material = make_floor_material(bpy)

    mesh_objects = import_mesh_sequence(bpy, args.mesh_dir, soft_material)
    create_and_animate_plates(bpy, plates, plate_material)
    create_studio(bpy, floor_material)

    all_frames = sorted({frame for frame, _obj in mesh_objects} | {int(row["frame"]) for row in plates})
    configure_render(bpy, width, height, args.fps, args.engine, args.samples, min(all_frames), max(all_frames))

    args.output_blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_blend))
    print(f"Wrote Blender scene to {args.output_blend}")

    if args.render_keyframes:
        render_keyframes(bpy, keyframes, args.preview_dir)


if __name__ == "__main__":
    main()
