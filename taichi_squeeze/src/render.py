from __future__ import annotations

from pathlib import Path

import imageio.v2 as imageio
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def render_frame(
    points: np.ndarray,
    left_plate_m: float,
    right_plate_m: float,
    plate_thickness_m: float,
    plate_y_min_m: float,
    plate_y_max_m: float,
    domain_size_m: float,
    output_path: Path,
    title: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(6, 6), dpi=130)
    ax.scatter(points[:, 0], points[:, 1], s=0.45, c="#2f80ed", alpha=0.8, linewidths=0)
    plate_height = plate_y_max_m - plate_y_min_m
    left_plate = plt.Rectangle(
        (left_plate_m - plate_thickness_m, plate_y_min_m),
        plate_thickness_m,
        plate_height,
        facecolor="#636e72",
        edgecolor="#2d3436",
        linewidth=1.5,
    )
    right_plate = plt.Rectangle(
        (right_plate_m, plate_y_min_m),
        plate_thickness_m,
        plate_height,
        facecolor="#636e72",
        edgecolor="#2d3436",
        linewidth=1.5,
    )
    ax.add_patch(left_plate)
    ax.add_patch(right_plate)
    ax.set_xlim(0.0, domain_size_m)
    ax.set_ylim(0.0, domain_size_m)
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title)
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.grid(True, color="#dfe6e9", linewidth=0.6)
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def write_preview_gif(frame_paths: list[Path], gif_path: Path, fps: int) -> None:
    if not frame_paths:
        return
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    images = [imageio.imread(path) for path in frame_paths]
    imageio.mimsave(gif_path, images, duration=1.0 / fps)
