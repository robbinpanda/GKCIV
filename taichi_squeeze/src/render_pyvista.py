from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

try:
    import pyvista as pv
except ImportError:  # pragma: no cover - exercised only on machines without PyVista.
    pv = None

DEFAULT_CAMERA = {
    "elev": 22,
    "azim": -38,
    "zoom": 1.75,
    "resolution": [960, 720],
    "bgcolor": "#f8fafc",
}

DEFAULT_COLORS = {
    "soft_body": "#2f8fd8",
    "plate": "#d86b5f",
    "background": "#f8fafc",
    "floor": "#e5e7eb",
    "shadow": "#94a3b8",
}


def load_camera_params(camera_path: Path | None = None) -> dict:
    if camera_path and camera_path.exists():
        with camera_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CAMERA.copy()


def load_color_scheme(color_path: Path | None = None) -> dict:
    if color_path and color_path.exists():
        with color_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_COLORS.copy()


def hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def render_frame_pyvista(
    points: np.ndarray,
    left_plate: float,
    right_plate: float,
    plate_thickness: float,
    plate_y_min: float,
    plate_y_max: float,
    plate_z_min: float,
    plate_z_max: float,
    domain_size: float,
    output_path: Path,
    title: str = "",
    camera_params: dict | None = None,
    color_scheme: dict | None = None,
    particle_radius: float = 0.0008,
    opacity: float = 0.85,
) -> None:
    if pv is None:
        raise ImportError("PyVista is not installed")

    camera = camera_params or DEFAULT_CAMERA
    colors = color_scheme or DEFAULT_COLORS

    resolution = tuple(camera.get("resolution", [960, 720]))
    bgcolor = hex_to_rgb(camera.get("bgcolor", "#f8fafc"))
    body_color = hex_to_rgb(colors.get("soft_body", "#4a90d9"))
    plate_color = hex_to_rgb(colors.get("plate", "#e74c3c"))
    floor_color = hex_to_rgb(colors.get("floor", "#e5e7eb"))
    shadow_color = hex_to_rgb(colors.get("shadow", "#94a3b8"))

    plotter = pv.Plotter(off_screen=True, window_size=resolution)
    plotter.set_background(bgcolor)
    plotter.enable_anti_aliasing("ssaa")
    plotter.enable_eye_dome_lighting()

    left_box = pv.Box(
        bounds=[
            left_plate - plate_thickness, left_plate,
            plate_y_min, plate_y_max,
            plate_z_min, plate_z_max,
        ]
    )
    plotter.add_mesh(left_box, color=plate_color, opacity=0.42, lighting=True, show_edges=True, edge_color="#7f1d1d")

    right_box = pv.Box(
        bounds=[
            right_plate, right_plate + plate_thickness,
            plate_y_min, plate_y_max,
            plate_z_min, plate_z_max,
        ]
    )
    plotter.add_mesh(right_box, color=plate_color, opacity=0.42, lighting=True, show_edges=True, edge_color="#7f1d1d")

    floor_y = max(0.0, plate_y_min - domain_size * 0.06)
    floor = pv.Plane(
        center=(domain_size * 0.5, floor_y, domain_size * 0.5),
        direction=(0, 1, 0),
        i_size=domain_size * 1.05,
        j_size=domain_size * 1.05,
    )
    plotter.add_mesh(floor, color=floor_color, opacity=0.32, lighting=False)

    if len(points):
        mins = points.min(axis=0)
        maxs = points.max(axis=0)
        shadow_center = ((mins[0] + maxs[0]) * 0.5, floor_y + domain_size * 0.001, (mins[2] + maxs[2]) * 0.5)
        shadow = pv.Disc(
            center=shadow_center,
            inner=0.0,
            outer=max(maxs[0] - mins[0], maxs[2] - mins[2]) * 0.62,
            normal=(0, 1, 0),
            r_res=1,
            c_res=64,
        )
        plotter.add_mesh(shadow, color=shadow_color, opacity=0.18, lighting=False)

    cloud = pv.PolyData(points)
    if len(points) <= 6000:
        glyph = cloud.glyph(geom=pv.Sphere(radius=particle_radius, theta_resolution=8, phi_resolution=8), scale=False, orient=False)
        plotter.add_mesh(glyph, color=body_color, opacity=opacity, lighting=True, smooth_shading=True)
    else:
        plotter.add_points(
            cloud,
            color=body_color,
            point_size=max(5.0, particle_radius * 8000),
            render_points_as_spheres=True,
            opacity=opacity,
        )

    target = np.array([domain_size * 0.5, domain_size * 0.5, domain_size * 0.5], dtype=float)
    light = pv.Light(position=(domain_size * 0.1, -domain_size * 1.2, domain_size * 2.0), focal_point=target, intensity=1.1)
    plotter.add_light(light)
    fill = pv.Light(position=(domain_size * 1.4, domain_size * 1.2, domain_size * 0.8), focal_point=target, intensity=0.35)
    plotter.add_light(fill)

    elev = math.radians(float(camera.get("elev", 30)))
    azim = math.radians(float(camera.get("azim", 45)))
    distance = domain_size * float(camera.get("zoom", 1.9))
    camera_pos = target + distance * np.array(
        [
            math.cos(elev) * math.cos(azim),
            math.sin(elev),
            math.cos(elev) * math.sin(azim),
        ],
        dtype=float,
    )
    plotter.camera_position = [camera_pos.tolist(), target.tolist(), [0, 1, 0]]
    plotter.camera.parallel_projection = bool(camera.get("parallel_projection", False))
    if plotter.camera.parallel_projection:
        plotter.camera.parallel_scale = domain_size * float(camera.get("parallel_scale", 0.62))

    if title:
        plotter.add_title(title, font_size=12)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plotter.screenshot(str(output_path))
    plotter.close()


def write_preview_gif_pyvista(
    frame_paths: list[Path],
    output_path: Path,
    fps: int = 60,
) -> None:
    from PIL import Image

    if not frame_paths:
        return

    images = []
    for fp in frame_paths:
        if fp.exists():
            img = Image.open(fp)
            images.append(img)

    if not images:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = int(1000 / fps)
    images[0].save(
        str(output_path),
        save_all=True,
        append_images=images[1:],
        duration=duration,
        loop=0,
    )


def write_preview_mp4_pyvista(
    frame_paths: list[Path],
    output_path: Path,
    fps: int = 60,
) -> None:
    try:
        import cv2
    except ImportError:
        print("Warning: opencv-python not installed, skipping MP4 export")
        return

    if not frame_paths:
        return

    first = cv2.imread(str(frame_paths[0]))
    if first is None:
        return

    h, w = first.shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))

    for fp in frame_paths:
        if fp.exists():
            img = cv2.imread(str(fp))
            if img is not None:
                writer.write(img)

    writer.release()


def render_side_by_side(
    run_dirs: list[Path],
    output_path: Path,
    frame_idx: int = 0,
    camera_params: dict | None = None,
    color_scheme: dict | None = None,
) -> None:
    camera = camera_params or DEFAULT_CAMERA
    resolution = tuple(camera.get("resolution", [960, 720]))

    frames = []
    for run_dir in run_dirs:
        frame_path = run_dir / "frames" / f"frame_{frame_idx:04d}.png"
        if frame_path.exists():
            from PIL import Image
            frames.append(Image.open(frame_path))

    if not frames:
        return

    total_width = resolution[0] * len(frames)
    combined = Image.new("RGB", (total_width, resolution[1]))

    for i, img in enumerate(frames):
        if img.size != resolution:
            img = img.resize(resolution)
        combined.paste(img, (i * resolution[0], 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined.save(str(output_path))
