from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from pathlib import Path

import numpy as np
from scipy.spatial import ConvexHull

from taichi_squeeze.src.metrics import write_metrics_csv
from taichi_squeeze.src.render3d import render_frame_3d, write_preview_gif


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def object_size(config: dict) -> np.ndarray:
    if config["shape"] == "sphere":
        d = float(config["object_diameter_m"])
        return np.array([d, d, d], dtype=np.float64)
    return np.array(config["object_size_m"], dtype=np.float64)


def object_volume(config: dict) -> float:
    if config["shape"] == "sphere":
        r = float(config["object_diameter_m"]) * 0.5
        return 4.0 / 3.0 * math.pi * r**3
    sx, sy, sz = config["object_size_m"]
    return float(sx) * float(sy) * float(sz)


def squeeze_diameter(config: dict) -> float:
    if "object_diameter_m" in config:
        return float(config["object_diameter_m"])
    return float(config["object_size_m"][0])


def plate_motion(config: dict, t: float) -> tuple[float, float, float, float, float]:
    center_x = float(config["object_center_m"][0])
    diameter = squeeze_diameter(config)
    initial_gap = diameter * float(config["initial_gap_ratio"])
    min_gap = diameter * float(config["min_gap_ratio"])
    compress_time = float(config["compress_time_s"])
    hold_time = float(config["hold_time_s"])
    release_time = float(config["release_time_s"])

    if t < compress_time:
        alpha = t / compress_time
        gap = initial_gap + (min_gap - initial_gap) * alpha
        gap_rate = (min_gap - initial_gap) / compress_time
    elif t < compress_time + hold_time:
        gap = min_gap
        gap_rate = 0.0
    elif t < compress_time + hold_time + release_time:
        alpha = (t - compress_time - hold_time) / release_time
        gap = min_gap + (initial_gap - min_gap) * alpha
        gap_rate = (initial_gap - min_gap) / release_time
    else:
        gap = initial_gap
        gap_rate = 0.0

    left = center_x - gap * 0.5
    right = center_x + gap * 0.5
    return left, right, -0.5 * gap_rate, 0.5 * gap_rate, max(0.0, initial_gap - gap)


def plate_span(config: dict) -> tuple[float, float, float, float]:
    center = np.array(config["object_center_m"], dtype=np.float64)
    height = float(config.get("plate_height_m", squeeze_diameter(config)))
    depth = float(config.get("plate_depth_m", squeeze_diameter(config)))
    return (
        float(center[1] - height * 0.5),
        float(center[1] + height * 0.5),
        float(center[2] - depth * 0.5),
        float(center[2] + depth * 0.5),
    )


def particle_geometry(points: np.ndarray) -> dict[str, float]:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    return {
        "width_m": float(maxs[0] - mins[0]),
        "height_m": float(maxs[1] - mins[1]),
        "depth_m": float(maxs[2] - mins[2]),
        "min_x_m": float(mins[0]),
        "max_x_m": float(maxs[0]),
        "min_y_m": float(mins[1]),
        "max_y_m": float(maxs[1]),
        "min_z_m": float(mins[2]),
        "max_z_m": float(maxs[2]),
    }


def build_lattice(config: dict) -> tuple[np.ndarray, float]:
    center = np.array(config["object_center_m"], dtype=np.float64)
    size = object_size(config)
    res = np.array(config["lattice_resolution"], dtype=int)
    axes = [np.linspace(center[i] - size[i] * 0.5, center[i] + size[i] * 0.5, res[i]) for i in range(3)]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    if config["shape"] == "sphere":
        radius = float(config["object_diameter_m"]) * 0.5
        mask = np.linalg.norm(grid - center, axis=1) <= radius + 1e-12
        grid = grid[mask]
    spacing = float(np.min(size / np.maximum(res - 1, 1)))
    return grid.astype(np.float64), spacing


def build_springs(points: np.ndarray, spacing: float) -> tuple[np.ndarray, np.ndarray]:
    quantized = np.round(points / spacing).astype(int)
    lookup = {tuple(idx): i for i, idx in enumerate(quantized)}
    offsets = []
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            for dz in range(-1, 2):
                if dx == dy == dz == 0:
                    continue
                if (dx, dy, dz) > (0, 0, 0):
                    offsets.append((dx, dy, dz))

    edges = []
    rest_lengths = []
    max_len = math.sqrt(3.0) * spacing * 1.01
    for i, idx in enumerate(quantized):
        for offset in offsets:
            j = lookup.get(tuple(idx + np.array(offset)))
            if j is None:
                continue
            rest = float(np.linalg.norm(points[j] - points[i]))
            if rest <= max_len:
                edges.append((i, j))
                rest_lengths.append(rest)
    return np.array(edges, dtype=np.int32), np.array(rest_lengths, dtype=np.float64)


def project_plates(
    points: np.ndarray,
    left: float,
    right: float,
    left_vel: float,
    right_vel: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    skin: float,
    masses: np.ndarray,
    dt: float,
    contact_force: float,
) -> float:
    in_plate = (points[:, 1] >= y0) & (points[:, 1] <= y1) & (points[:, 2] >= z0) & (points[:, 2] <= z1)
    left_limit = left + skin
    right_limit = right - skin
    left_mask = in_plate & (points[:, 0] < left_limit)
    right_mask = in_plate & (points[:, 0] > right_limit)
    if np.any(left_mask):
        correction = left_limit - points[left_mask, 0]
        points[left_mask, 0] = left_limit
        contact_force += float(np.sum(masses[left_mask] * correction / (dt * dt)))
    if np.any(right_mask):
        correction = points[right_mask, 0] - right_limit
        points[right_mask, 0] = right_limit
        contact_force += float(np.sum(masses[right_mask] * correction / (dt * dt)))
    return contact_force


def plate_penetration(points: np.ndarray, left: float, right: float, y0: float, y1: float, z0: float, z1: float) -> float:
    in_plate = (points[:, 1] >= y0) & (points[:, 1] <= y1) & (points[:, 2] >= z0) & (points[:, 2] <= z1)
    if not np.any(in_plate):
        return 0.0
    selected = points[in_plate]
    return float(max(np.maximum(0.0, left - selected[:, 0]).max(initial=0.0), np.maximum(0.0, selected[:, 0] - right).max(initial=0.0)))


def run_simulation(config: dict, config_path: Path, frame_override: int | None, no_render: bool) -> Path:
    output_dir = Path(config["output_dir"])
    frames_dir = output_dir / "frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_path, output_dir / "used_config.json")

    x, spacing = build_lattice(config)
    edges, rest = build_springs(x, spacing)
    edge_a = edges[:, 0]
    edge_b = edges[:, 1]
    v = np.zeros_like(x)
    x0 = x.copy()
    initial = particle_geometry(x)

    density = float(config["density_kg_m3"])
    total_mass = density * object_volume(config)
    masses = np.full(len(x), total_mass / len(x), dtype=np.float64)
    inv_masses = 1.0 / masses

    fps = int(config["fps"])
    max_frames = int(frame_override if frame_override is not None else config["max_frames"])
    substeps = int(config["substeps_per_frame"])
    dt = float(config["dt"])
    stiffness = float(config["constraint_stiffness"])
    iterations = int(config["pbd_iterations"])
    damping = float(config.get("velocity_damping", 0.0))
    gravity = np.array([0.0, float(config.get("gravity_m_s2", 0.0)), 0.0], dtype=np.float64)
    domain_size = float(config["domain_size_m"])
    plate_thickness = float(config["plate_thickness_m"])
    skin = float(config["contact_skin_m"])
    y0, y1, z0, z1 = plate_span(config)
    render_every = int(config.get("render_every", 1))

    rows = []
    rendered_frames: list[Path] = []

    for frame in range(max_frames):
        frame_start = time.perf_counter()
        frame_force = 0.0
        t = frame / fps
        left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, t)

        for substep_id in range(substeps):
            sub_t = t + substep_id * dt
            left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, sub_t)
            prev_x = x.copy()
            v += gravity * dt
            v *= max(0.0, 1.0 - damping * dt)
            x += v * dt

            frame_force = project_plates(x, left, right, left_vel, right_vel, y0, y1, z0, z1, skin, masses, dt, frame_force)
            for _ in range(iterations):
                delta = x[edge_b] - x[edge_a]
                dist = np.linalg.norm(delta, axis=1)
                safe_dist = np.maximum(dist, 1e-12)
                correction_mag = stiffness * (dist - rest) / (inv_masses[edge_a] + inv_masses[edge_b])
                correction = (correction_mag / safe_dist)[:, None] * delta
                np.add.at(x, edge_a, inv_masses[edge_a, None] * correction)
                np.add.at(x, edge_b, -inv_masses[edge_b, None] * correction)
                frame_force = project_plates(x, left, right, left_vel, right_vel, y0, y1, z0, z1, skin, masses, dt, frame_force)

            eps = 0.002
            x[:] = np.clip(x, eps, domain_size - eps)
            v = (x - prev_x) / dt
            in_left = (x[:, 0] <= left + skin + 1e-9) & (x[:, 1] >= y0) & (x[:, 1] <= y1) & (x[:, 2] >= z0) & (x[:, 2] <= z1)
            in_right = (x[:, 0] >= right - skin - 1e-9) & (x[:, 1] >= y0) & (x[:, 1] <= y1) & (x[:, 2] >= z0) & (x[:, 2] <= z1)
            v[in_left, 0] = np.maximum(v[in_left, 0], left_vel)
            v[in_right, 0] = np.minimum(v[in_right, 0], right_vel)

        stats = particle_geometry(x)
        displacement = x - x0
        kinetic = float(0.5 * np.sum(masses[:, None] * v * v))
        elastic = float(0.5 * density * object_volume(config) * np.mean(np.sum(displacement * displacement, axis=1)))
        
        try:
            hull = ConvexHull(x)
            current_volume = hull.volume
            initial_volume = object_volume(config)
            volume_ratio = current_volume / initial_volume if initial_volume > 0 else np.nan
        except Exception:
            volume_ratio = np.nan
        
        wall_ms = (time.perf_counter() - frame_start) * 1000.0

        rows.append(
            {
                "engine": "taichi",
                "solver": "pbd3d",
                "scene": config["scene"],
                "frame": frame,
                "t": f"{t:.6f}",
                "dt": f"{dt:.8f}",
                "substeps": substeps,
                "particles": len(x),
                "grid_res": "",
                "squeeze_disp_m": f"{squeeze_disp:.8f}",
                "plate_force_n": f"{frame_force / max(1, substeps):.8f}",
                "height_m": f"{stats['height_m']:.8f}",
                "width_m": f"{stats['width_m']:.8f}",
                "volume_ratio": f"{volume_ratio:.8f}" if not np.isnan(volume_ratio) else "",
                "residual_strain": f"{abs(stats['width_m'] - initial['width_m']) / initial['width_m']:.8f}",
                "max_penetration_m": f"{plate_penetration(x, left, right, y0, y1, z0, z1):.8f}",
                "kinetic_energy": f"{kinetic:.8f}",
                "elastic_energy": f"{elastic:.8f}",
                "wall_ms": f"{wall_ms:.4f}",
            }
        )

        if not no_render and frame % render_every == 0:
            frame_path = frames_dir / f"frame_{frame:04d}.png"
            render_frame_3d(
                x,
                left,
                right,
                plate_thickness,
                y0,
                y1,
                z0,
                z1,
                domain_size,
                frame_path,
                f"{config['scene']}  t={t:.2f}s",
            )
            rendered_frames.append(frame_path)

        if frame == 0 or (frame + 1) % 10 == 0 or frame + 1 == max_frames:
            print(f"[{config['scene']}] frame {frame + 1:03d}/{max_frames} force={frame_force / max(1, substeps):.3f}N width={stats['width_m']:.4f}m wall={wall_ms:.1f}ms")

    metrics_path = output_dir / "metrics.csv"
    write_metrics_csv(metrics_path, rows)
    if not no_render:
        write_preview_gif(rendered_frames, output_dir / "preview.gif", fps=max(1, fps // max(1, render_every)))
    print(f"Wrote {metrics_path}")
    return metrics_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a 3D PBD squeeze simulation.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--no-render", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_simulation(load_config(args.config), args.config, args.frames, args.no_render)


if __name__ == "__main__":
    main()
