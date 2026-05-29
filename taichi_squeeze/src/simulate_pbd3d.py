import argparse
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import taichi as ti
from scipy.spatial import ConvexHull, cKDTree

from taichi_squeeze.src.geometry3d import analytical_volume, object_size, squeeze_diameter, spherical_point_cloud
from taichi_squeeze.src.metrics import write_metrics_csv
from taichi_squeeze.src.render3d import render_frame_auto, write_preview_gif


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def arch_from_name(name: str):
    arch = name.lower()
    if arch == "cpu":
        return ti.cpu
    if arch == "cuda":
        return ti.cuda
    if arch == "vulkan":
        return ti.vulkan
    raise ValueError(f"Unsupported Taichi arch: {name}")


def object_volume(config: dict) -> float:
    return analytical_volume(config)


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
    if config["shape"] == "sphere":
        points, _ = spherical_point_cloud(
            config,
            resolution_key="lattice_resolution",
            surface_key="sphere_surface_points",
            default_surface_points=256,
        )
        spacing = float(config["object_diameter_m"]) / max(int(np.max(config["lattice_resolution"])) - 1, 1)
        return points.astype(np.float64), spacing

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
    tree = cKDTree(points)
    max_len = math.sqrt(3.0) * spacing * 1.05
    pairs = sorted(tree.query_pairs(max_len))
    edges = np.array(pairs, dtype=np.int32)
    if len(edges) == 0:
        raise ValueError("Generated PBD lattice has no springs. Increase lattice_resolution.")
    rest_lengths = np.linalg.norm(points[edges[:, 1]] - points[edges[:, 0]], axis=1)
    return np.array(edges, dtype=np.int32), np.array(rest_lengths, dtype=np.float64)


def plate_penetration(points: np.ndarray, left: float, right: float, y0: float, y1: float, z0: float, z1: float) -> float:
    in_plate = (points[:, 1] >= y0) & (points[:, 1] <= y1) & (points[:, 2] >= z0) & (points[:, 2] <= z1)
    if not np.any(in_plate):
        return 0.0
    selected = points[in_plate]
    return float(max(np.maximum(0.0, left - selected[:, 0]).max(initial=0.0), np.maximum(0.0, selected[:, 0] - right).max(initial=0.0)))


@ti.data_oriented
class TaichiPBD3DSimulator:
    def __init__(
        self,
        points: np.ndarray,
        edges: np.ndarray,
        rest_lengths: np.ndarray,
        masses: np.ndarray,
        inv_masses: np.ndarray,
        degree: np.ndarray,
        density: float,
        reference_volume: float,
        domain_size: float,
    ):
        self.n_particles = int(len(points))
        self.n_edges = int(len(edges))
        self.density = float(density)
        self.reference_volume = float(reference_volume)
        self.domain_size = float(domain_size)

        self.x = ti.Vector.field(3, dtype=ti.f32, shape=self.n_particles)
        self.rest_x = ti.Vector.field(3, dtype=ti.f32, shape=self.n_particles)
        self.prev_x = ti.Vector.field(3, dtype=ti.f32, shape=self.n_particles)
        self.v = ti.Vector.field(3, dtype=ti.f32, shape=self.n_particles)
        self.delta = ti.Vector.field(3, dtype=ti.f32, shape=self.n_particles)
        self.mass = ti.field(dtype=ti.f32, shape=self.n_particles)
        self.inv_mass = ti.field(dtype=ti.f32, shape=self.n_particles)
        self.degree = ti.field(dtype=ti.f32, shape=self.n_particles)
        self.edges = ti.Vector.field(2, dtype=ti.i32, shape=self.n_edges)
        self.rest = ti.field(dtype=ti.f32, shape=self.n_edges)
        self.contact_force = ti.field(dtype=ti.f32, shape=())
        self.kinetic_energy = ti.field(dtype=ti.f32, shape=())
        self.elastic_energy = ti.field(dtype=ti.f32, shape=())

        points32 = points.astype(np.float32)
        self.x.from_numpy(points32)
        self.rest_x.from_numpy(points32)
        self.mass.from_numpy(masses.astype(np.float32))
        self.inv_mass.from_numpy(inv_masses.astype(np.float32))
        self.degree.from_numpy(degree.astype(np.float32))
        self.edges.from_numpy(edges.astype(np.int32))
        self.rest.from_numpy(rest_lengths.astype(np.float32))
        self.initialize()

    @ti.kernel
    def initialize(self):
        for i in range(self.n_particles):
            self.prev_x[i] = self.x[i]
            self.v[i] = ti.Vector([0.0, 0.0, 0.0])
            self.delta[i] = ti.Vector([0.0, 0.0, 0.0])
        self.contact_force[None] = 0.0
        self.kinetic_energy[None] = 0.0
        self.elastic_energy[None] = 0.0

    @ti.kernel
    def reset_frame_stats(self):
        self.contact_force[None] = 0.0

    @ti.kernel
    def predict(self, dt: ti.f32, damping: ti.f32, gravity_y: ti.f32):
        damp = ti.max(0.0, 1.0 - damping * dt)
        for i in range(self.n_particles):
            self.prev_x[i] = self.x[i]
            self.v[i] = (self.v[i] + ti.Vector([0.0, gravity_y, 0.0]) * dt) * damp
            self.x[i] += self.v[i] * dt

    @ti.kernel
    def project_plates(
        self,
        left: ti.f32,
        right: ti.f32,
        y0: ti.f32,
        y1: ti.f32,
        z0: ti.f32,
        z1: ti.f32,
        skin: ti.f32,
        dt: ti.f32,
    ):
        left_limit = left + skin
        right_limit = right - skin
        for i in range(self.n_particles):
            pos = self.x[i]
            in_plate = pos[1] >= y0 and pos[1] <= y1 and pos[2] >= z0 and pos[2] <= z1
            if in_plate and pos[0] < left_limit:
                correction = left_limit - pos[0]
                pos[0] = left_limit
                ti.atomic_add(self.contact_force[None], self.mass[i] * correction / (dt * dt))
            if in_plate and pos[0] > right_limit:
                correction = pos[0] - right_limit
                pos[0] = right_limit
                ti.atomic_add(self.contact_force[None], self.mass[i] * correction / (dt * dt))
            self.x[i] = pos

    @ti.kernel
    def solve_springs_once(self, stiffness: ti.f32):
        for i in range(self.n_particles):
            self.delta[i] = ti.Vector([0.0, 0.0, 0.0])

        for e in range(self.n_edges):
            a = self.edges[e][0]
            b = self.edges[e][1]
            diff = self.x[b] - self.x[a]
            dist = diff.norm()
            if dist > 1e-12:
                correction_mag = stiffness * (dist - self.rest[e]) / (self.inv_mass[a] + self.inv_mass[b])
                correction = correction_mag / dist * diff
                wa = self.inv_mass[a] / self.degree[a]
                wb = self.inv_mass[b] / self.degree[b]
                for d in ti.static(range(3)):
                    ti.atomic_add(self.delta[a][d], wa * correction[d])
                    ti.atomic_add(self.delta[b][d], -wb * correction[d])

        for i in range(self.n_particles):
            self.x[i] += self.delta[i]

    @ti.kernel
    def finalize_velocity(
        self,
        dt: ti.f32,
        left: ti.f32,
        right: ti.f32,
        left_vel: ti.f32,
        right_vel: ti.f32,
        y0: ti.f32,
        y1: ti.f32,
        z0: ti.f32,
        z1: ti.f32,
        skin: ti.f32,
    ):
        self.kinetic_energy[None] = 0.0
        self.elastic_energy[None] = 0.0
        eps = 0.002
        left_limit = left + skin
        right_limit = right - skin
        for i in range(self.n_particles):
            pos = self.x[i]
            pos[0] = ti.min(ti.max(pos[0], eps), self.domain_size - eps)
            pos[1] = ti.min(ti.max(pos[1], eps), self.domain_size - eps)
            pos[2] = ti.min(ti.max(pos[2], eps), self.domain_size - eps)

            vel = (pos - self.prev_x[i]) / dt
            in_plate = pos[1] >= y0 and pos[1] <= y1 and pos[2] >= z0 and pos[2] <= z1
            if in_plate and pos[0] <= left_limit + 1e-9:
                vel[0] = ti.max(vel[0], left_vel)
            if in_plate and pos[0] >= right_limit - 1e-9:
                vel[0] = ti.min(vel[0], right_vel)

            self.x[i] = pos
            self.v[i] = vel
            disp = pos - self.rest_x[i]
            ti.atomic_add(self.kinetic_energy[None], 0.5 * self.mass[i] * vel.dot(vel))
            ti.atomic_add(self.elastic_energy[None], 0.5 * self.density * self.reference_volume * disp.dot(disp) / self.n_particles)


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
    degree = np.maximum(np.bincount(edges.reshape(-1), minlength=len(x)), 1).astype(np.float64)
    x0 = x.copy()
    initial = particle_geometry(x)
    try:
        initial_volume = float(ConvexHull(x0).volume)
    except Exception:
        initial_volume = object_volume(config)

    density = float(config["density_kg_m3"])
    total_mass = density * object_volume(config)
    masses = np.full(len(x), total_mass / len(x), dtype=np.float64)
    inv_masses = 1.0 / masses

    ti.init(
        arch=arch_from_name(config.get("arch", "cpu")),
        default_fp=ti.f32,
        random_seed=int(config.get("seed", 0)),
        offline_cache=False,
    )
    sim = TaichiPBD3DSimulator(
        x,
        edges,
        rest,
        masses,
        inv_masses,
        degree,
        density,
        object_volume(config),
        float(config["domain_size_m"]),
    )

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
    render_backend = str(config.get("render_backend", "pyvista"))
    particle_radius = float(config.get("particle_radius_m", max(spacing * 0.32, 0.0008)))

    rows = []
    rendered_frames: list[Path] = []

    for frame in range(max_frames):
        frame_start = time.perf_counter()
        frame_force = 0.0
        t = frame / fps
        left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, t)
        sim.reset_frame_stats()

        for substep_id in range(substeps):
            sub_t = t + substep_id * dt
            left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, sub_t)
            sim.predict(dt, damping, float(gravity[1]))
            sim.project_plates(left, right, y0, y1, z0, z1, skin, dt)
            for _ in range(iterations):
                sim.solve_springs_once(stiffness)
                sim.project_plates(left, right, y0, y1, z0, z1, skin, dt)
            sim.finalize_velocity(dt, left, right, left_vel, right_vel, y0, y1, z0, z1, skin)

        x = sim.x.to_numpy()
        stats = particle_geometry(x)
        frame_force = float(sim.contact_force[None])
        kinetic = float(sim.kinetic_energy[None])
        elastic = float(sim.elastic_energy[None])
        
        try:
            hull = ConvexHull(x)
            current_volume = hull.volume
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
