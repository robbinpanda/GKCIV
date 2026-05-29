from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np
from scipy.spatial import Delaunay

from taichi_squeeze.src.constitutive import corotated_pk1_and_energy, neo_hookean_pk1_and_energy
from taichi_squeeze.src.geometry3d import object_size, squeeze_diameter, spherical_point_cloud
from taichi_squeeze.src.metrics import write_metrics_csv
from taichi_squeeze.src.render3d import render_frame_auto, write_preview_gif


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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
    }


def build_vertices(config: dict) -> tuple[np.ndarray, dict[tuple[int, int, int], int], np.ndarray]:
    if config["shape"] == "sphere":
        vertices, _ = spherical_point_cloud(
            config,
            resolution_key="mesh_resolution",
            surface_key="sphere_surface_points",
            default_surface_points=192,
        )
        return vertices, {}, np.array(config["mesh_resolution"], dtype=int)

    center = np.array(config["object_center_m"], dtype=np.float64)
    size = object_size(config)
    res = np.array(config["mesh_resolution"], dtype=int)
    axes = [np.linspace(center[i] - size[i] * 0.5, center[i] + size[i] * 0.5, res[i]) for i in range(3)]

    vertices = []
    lookup: dict[tuple[int, int, int], int] = {}
    for i, x in enumerate(axes[0]):
        for j, y in enumerate(axes[1]):
            for k, z in enumerate(axes[2]):
                p = np.array([x, y, z], dtype=np.float64)
                keep = True
                if config["shape"] == "sphere":
                    keep = np.linalg.norm(p - center) <= float(config["object_diameter_m"]) * 0.5 + 1e-12
                if keep:
                    lookup[(i, j, k)] = len(vertices)
                    vertices.append(p)
    return np.array(vertices, dtype=np.float64), lookup, res


def build_sphere_tets(config: dict, vertices: np.ndarray) -> np.ndarray:
    center = np.array(config["object_center_m"], dtype=np.float64)
    radius = float(config["object_diameter_m"]) * 0.5
    delaunay = Delaunay(vertices)
    simplices = delaunay.simplices.astype(np.int32)
    centroids = vertices[simplices].mean(axis=1)
    inside = np.linalg.norm(centroids - center, axis=1) <= radius * 1.001
    tets = simplices[inside]
    if len(tets) == 0:
        raise ValueError("Generated FEM sphere mesh has no tetrahedra. Increase mesh_resolution or sphere_surface_points.")
    return tets


def build_tets(config: dict, lookup: dict[tuple[int, int, int], int], res: np.ndarray) -> np.ndarray:
    local_tets = [
        (0, 1, 3, 7),
        (0, 3, 2, 7),
        (0, 2, 6, 7),
        (0, 6, 4, 7),
        (0, 4, 5, 7),
        (0, 5, 1, 7),
    ]
    corner_offsets = [
        (0, 0, 0),
        (1, 0, 0),
        (0, 1, 0),
        (1, 1, 0),
        (0, 0, 1),
        (1, 0, 1),
        (0, 1, 1),
        (1, 1, 1),
    ]
    tets = []
    for i in range(res[0] - 1):
        for j in range(res[1] - 1):
            for k in range(res[2] - 1):
                corners = []
                valid = True
                for offset in corner_offsets:
                    key = (i + offset[0], j + offset[1], k + offset[2])
                    if key not in lookup:
                        valid = False
                        break
                    corners.append(lookup[key])
                if not valid:
                    continue
                for tet in local_tets:
                    tets.append([corners[tet[0]], corners[tet[1]], corners[tet[2]], corners[tet[3]]])
    if not tets:
        raise ValueError("Generated FEM mesh has no tetrahedra. Increase mesh_resolution.")
    return np.array(tets, dtype=np.int32)


def prepare_tets(rest_x: np.ndarray, tets: np.ndarray, density: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    dm_inv = []
    volumes = []
    masses = np.zeros(len(rest_x), dtype=np.float64)
    valid_tets = []
    for tet in tets:
        x0, x1, x2, x3 = rest_x[tet]
        dm = np.column_stack((x1 - x0, x2 - x0, x3 - x0))
        det = float(np.linalg.det(dm))
        volume = abs(det) / 6.0
        if volume <= 1e-12:
            continue
        valid_tets.append(tet)
        dm_inv.append(np.linalg.inv(dm))
        volumes.append(volume)
        for idx in tet:
            masses[idx] += density * volume / 4.0
    masses[masses <= 0.0] = density * np.mean(volumes) / 4.0
    return np.array(valid_tets, dtype=np.int32), np.array(dm_inv), np.array(volumes), masses


def compute_forces(x: np.ndarray, tets: np.ndarray, dm_inv: np.ndarray, volumes: np.ndarray, mu: float, la: float, constitutive_model: str = "corotated") -> tuple[np.ndarray, float, float]:
    forces = np.zeros_like(x)
    elastic_energy = 0.0
    mean_j = 0.0
    for tet_id, tet in enumerate(tets):
        x0, x1, x2, x3 = x[tet]
        ds = np.column_stack((x1 - x0, x2 - x0, x3 - x0))
        F = ds @ dm_inv[tet_id]
        try:
            if constitutive_model == "neo_hookean":
                P, w = neo_hookean_pk1_and_energy(F, mu, la)
            else:
                P, w = corotated_pk1_and_energy(F, mu, la)
            J = float(np.linalg.det(F))
        except (np.linalg.LinAlgError, ValueError):
            P = np.zeros((3, 3), dtype=np.float64)
            w = 0.0
            J = 1.0
        H = -volumes[tet_id] * P @ dm_inv[tet_id].T
        f1, f2, f3 = H[:, 0], H[:, 1], H[:, 2]
        f0 = -f1 - f2 - f3
        forces[tet[0]] += f0
        forces[tet[1]] += f1
        forces[tet[2]] += f2
        forces[tet[3]] += f3
        elastic_energy += volumes[tet_id] * w
        mean_j += J
    return forces, elastic_energy, mean_j / max(1, len(tets))


def project_plates(
    points: np.ndarray,
    velocities: np.ndarray,
    masses: np.ndarray,
    left: float,
    right: float,
    left_vel: float,
    right_vel: float,
    y0: float,
    y1: float,
    z0: float,
    z1: float,
    skin: float,
    dt: float,
) -> float:
    contact_force = 0.0
    in_plate = (points[:, 1] >= y0) & (points[:, 1] <= y1) & (points[:, 2] >= z0) & (points[:, 2] <= z1)
    left_limit = left + skin
    right_limit = right - skin
    left_mask = in_plate & (points[:, 0] < left_limit)
    right_mask = in_plate & (points[:, 0] > right_limit)
    if np.any(left_mask):
        correction = left_limit - points[left_mask, 0]
        points[left_mask, 0] = left_limit
        velocities[left_mask, 0] = np.maximum(velocities[left_mask, 0], left_vel)
        contact_force += float(np.sum(masses[left_mask] * correction / (dt * dt)))
    if np.any(right_mask):
        correction = points[right_mask, 0] - right_limit
        points[right_mask, 0] = right_limit
        velocities[right_mask, 0] = np.minimum(velocities[right_mask, 0], right_vel)
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

    x, lookup, res = build_vertices(config)
    if config["shape"] == "sphere":
        tets = build_sphere_tets(config, x)
    else:
        tets = build_tets(config, lookup, res)
    density = float(config["density_kg_m3"])
    tets, dm_inv, volumes, masses = prepare_tets(x, tets, density)
    rest_x = x.copy()
    v = np.zeros_like(x)
    initial = particle_geometry(x)

    young = float(config["young_modulus_pa"])
    poisson = float(config["poisson_ratio"])
    mu = young / (2.0 * (1.0 + poisson))
    la = young * poisson / ((1.0 + poisson) * (1.0 - 2.0 * poisson))
    constitutive_model = config.get("constitutive_model", "corotated").lower()

    fps = int(config["fps"])
    max_frames = int(frame_override if frame_override is not None else config["max_frames"])
    substeps = int(config["substeps_per_frame"])
    dt = float(config["dt"])
    damping = float(config.get("velocity_damping", 0.0))
    gravity = np.array([0.0, float(config.get("gravity_m_s2", 0.0)), 0.0], dtype=np.float64)
    domain_size = float(config["domain_size_m"])
    plate_thickness = float(config["plate_thickness_m"])
    skin = float(config["contact_skin_m"])
    y0, y1, z0, z1 = plate_span(config)
    render_every = int(config.get("render_every", 1))
    render_backend = str(config.get("render_backend", "pyvista"))
    particle_radius = float(config.get("particle_radius_m", 0.0010))

    rows = []
    rendered_frames: list[Path] = []

    for frame in range(max_frames):
        frame_start = time.perf_counter()
        frame_force = 0.0
        elastic = 0.0
        mean_j = 1.0
        t = frame / fps
        left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, t)

        for substep_id in range(substeps):
            sub_t = t + substep_id * dt
            left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, sub_t)
            forces, elastic, mean_j = compute_forces(x, tets, dm_inv, volumes, mu, la, constitutive_model)
            v += (forces / masses[:, None] + gravity) * dt
            v *= max(0.0, 1.0 - damping * dt)
            x += v * dt
            eps = 0.002
            x[:] = np.clip(x, eps, domain_size - eps)
            frame_force += project_plates(x, v, masses, left, right, left_vel, right_vel, y0, y1, z0, z1, skin, dt)

        stats = particle_geometry(x)
        kinetic = float(0.5 * np.sum(masses[:, None] * v * v))
        wall_ms = (time.perf_counter() - frame_start) * 1000.0
        rows.append(
            {
                "engine": "taichi",
                "solver": "fem3d",
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
                "volume_ratio": f"{mean_j:.8f}",
                "residual_strain": f"{abs(stats['width_m'] - initial['width_m']) / initial['width_m']:.8f}",
                "max_penetration_m": f"{plate_penetration(x, left, right, y0, y1, z0, z1):.8f}",
                "kinetic_energy": f"{kinetic:.8f}",
                "elastic_energy": f"{elastic:.8f}",
                "wall_ms": f"{wall_ms:.4f}",
            }
        )

        if not no_render and frame % render_every == 0:
            frame_path = frames_dir / f"frame_{frame:04d}.png"
            render_backend = render_frame_auto(
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
                render_backend=render_backend,
                particle_radius_m=particle_radius,
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
    parser = argparse.ArgumentParser(description="Run a 3D tetrahedral FEM squeeze simulation.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--no-render", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_simulation(load_config(args.config), args.config, args.frames, args.no_render)


if __name__ == "__main__":
    main()
