from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def _plate_faces(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> list[list[tuple[float, float, float]]]:
    return [
        [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)],
        [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)],
        [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)],
        [(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)],
        [(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)],
        [(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)],
    ]


def _add_plate(ax, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> None:
    faces = _plate_faces(x0, x1, y0, y1, z0, z1)
    poly = Poly3DCollection(faces, facecolor="#636e72", edgecolor="#2d3436", linewidth=0.6, alpha=0.38)
    ax.add_collection3d(poly)


def render_frame_3d(
    points: np.ndarray,
    left_plate_m: float,
    right_plate_m: float,
    plate_thickness_m: float,
    plate_y_min_m: float,
    plate_y_max_m: float,
    plate_z_min_m: float,
    plate_z_max_m: float,
    domain_size_m: float,
    output_path: Path,
    title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(7, 6), dpi=130)
    ax = fig.add_subplot(111, projection="3d")
    ax.scatter(points[:, 0], points[:, 1], points[:, 2], s=2.0, c="#1976d2", alpha=0.72, depthshade=False)
    _add_plate(
        ax,
        left_plate_m - plate_thickness_m,
        left_plate_m,
        plate_y_min_m,
        plate_y_max_m,
        plate_z_min_m,
        plate_z_max_m,
    )
    _add_plate(
        ax,
        right_plate_m,
        right_plate_m + plate_thickness_m,
        plate_y_min_m,
        plate_y_max_m,
        plate_z_min_m,
        plate_z_max_m,
    )
    ax.set_xlim(0.0, domain_size_m)
    ax.set_ylim(0.0, domain_size_m)
    ax.set_zlim(0.0, domain_size_m)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=20, azim=-58)
    ax.set_title(title)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_zlabel("z (m)")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def write_preview_gif(frame_paths: list[Path], gif_path: Path, fps: int) -> None:
    if not frame_paths:
        return
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    images = [imageio.imread(path) for path in frame_paths]
    imageio.mimsave(gif_path, images, duration=1.0 / fps)


def render_frame_auto(
    points: np.ndarray,
    left_plate_m: float,
    right_plate_m: float,
    plate_thickness_m: float,
    plate_y_min_m: float,
    plate_y_max_m: float,
    plate_z_min_m: float,
    plate_z_max_m: float,
    domain_size_m: float,
    output_path: Path,
    title: str,
    render_backend: str = "pyvista",
    particle_radius_m: float = 0.0008,
) -> str:
    if render_backend.lower() == "pyvista":
        try:
            from taichi_squeeze.src.render_pyvista import load_camera_params, load_color_scheme, render_frame_pyvista

            render_frame_pyvista(
                points,
                left_plate_m,
                right_plate_m,
                plate_thickness_m,
                plate_y_min_m,
                plate_y_max_m,
                plate_z_min_m,
                plate_z_max_m,
                domain_size_m,
                output_path,
                title,
                camera_params=load_camera_params(Path("taichi_squeeze/configs/camera.json")),
                color_scheme=load_color_scheme(Path("taichi_squeeze/configs/color_scheme.json")),
                particle_radius=particle_radius_m,
            )
            return "pyvista"
        except Exception as exc:
            print(f"Warning: PyVista render failed ({exc}); falling back to matplotlib.")

    render_frame_3d(
        points,
        left_plate_m,
        right_plate_m,
        plate_thickness_m,
        plate_y_min_m,
        plate_y_max_m,
        plate_z_min_m,
        plate_z_max_m,
        domain_size_m,
        output_path,
        title,
    )
    return "matplotlib"
