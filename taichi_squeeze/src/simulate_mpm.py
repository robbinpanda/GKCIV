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

from taichi_squeeze.src.metrics import particle_geometry, write_metrics_csv
from taichi_squeeze.src.render import render_frame, write_preview_gif


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


def sample_circle(rng: np.random.Generator, n: int, center: np.ndarray, diameter: float) -> np.ndarray:
    radius = diameter * 0.5
    theta = rng.uniform(0.0, 2.0 * math.pi, n)
    r = radius * np.sqrt(rng.uniform(0.0, 1.0, n))
    points = np.column_stack((np.cos(theta) * r, np.sin(theta) * r))
    return points + center


def rounded_box_sdf(p: np.ndarray, half_size: float, radius: float) -> np.ndarray:
    q = np.abs(p) - (half_size - radius)
    outside = np.linalg.norm(np.maximum(q, 0.0), axis=1)
    inside = np.minimum(np.maximum(q[:, 0], q[:, 1]), 0.0)
    return outside + inside - radius


def sample_rounded_box(
    rng: np.random.Generator,
    n: int,
    center: np.ndarray,
    diameter: float,
    radius: float,
) -> np.ndarray:
    half = diameter * 0.5
    points: list[np.ndarray] = []
    while sum(len(chunk) for chunk in points) < n:
        candidates = rng.uniform(-half, half, size=(max(n, 2048), 2))
        accepted = candidates[rounded_box_sdf(candidates, half, radius) <= 0.0]
        if len(accepted):
            points.append(accepted)
    return np.vstack(points)[:n] + center


def sample_particles(config: dict) -> np.ndarray:
    rng = np.random.default_rng(int(config.get("seed", 0)))
    n = int(config["n_particles"])
    center = np.array(config["object_center_m"], dtype=np.float32)
    diameter = float(config["object_diameter_m"])
    shape = config["shape"]

    if shape == "circle":
        return sample_circle(rng, n, center, diameter).astype(np.float32)
    if shape == "rounded_box":
        radius = float(config.get("corner_radius_m", diameter * 0.15))
        return sample_rounded_box(rng, n, center, diameter, radius).astype(np.float32)
    raise ValueError(f"Unsupported shape: {shape}")


def estimate_area(config: dict) -> float:
    diameter = float(config["object_diameter_m"])
    if config["shape"] == "circle":
        return math.pi * (diameter * 0.5) ** 2
    if config["shape"] == "rounded_box":
        r = float(config.get("corner_radius_m", diameter * 0.15))
        return diameter * diameter - (4.0 - math.pi) * r * r
    raise ValueError(f"Unsupported shape: {config['shape']}")


def plate_motion(config: dict, t: float) -> tuple[float, float, float, float, float]:
    center_x = float(config["object_center_m"][0])
    diameter = float(config["object_diameter_m"])
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
    left_velocity = -0.5 * gap_rate
    right_velocity = 0.5 * gap_rate
    squeeze_disp = max(0.0, initial_gap - gap)
    return left, right, left_velocity, right_velocity, squeeze_disp


def plate_vertical_span(config: dict) -> tuple[float, float]:
    center_y = float(config["object_center_m"][1])
    height = float(config.get("plate_height_m", config["object_diameter_m"]))
    return center_y - height * 0.5, center_y + height * 0.5


def plate_penetration(points: np.ndarray, left_face: float, right_face: float, y_min: float, y_max: float) -> float:
    inside_height = (points[:, 1] >= y_min) & (points[:, 1] <= y_max)
    if not np.any(inside_height):
        return 0.0
    side_points = points[inside_height]
    left_depth = np.maximum(0.0, left_face - side_points[:, 0])
    right_depth = np.maximum(0.0, side_points[:, 0] - right_face)
    return float(max(left_depth.max(initial=0.0), right_depth.max(initial=0.0)))


@ti.data_oriented
class MPMSimulator:
    def __init__(self, config: dict, initial_positions: np.ndarray):
        self.n_particles = int(config["n_particles"])
        self.n_grid = int(config["n_grid"])
        self.domain_size = float(config["domain_size_m"])
        self.dx = self.domain_size / self.n_grid
        self.inv_dx = 1.0 / self.dx
        self.dt = float(config["dt"])
        self.gravity = float(config.get("gravity_m_s2", 0.0))
        self.grid_damping = float(config.get("grid_velocity_damping", 0.0))
        self.dim = 2

        area = estimate_area(config)
        depth = float(config["object_depth_m"])
        density = float(config["density_kg_m3"])
        self.p_vol = area * depth / self.n_particles
        self.p_mass = density * self.p_vol
        young = float(config["young_modulus_pa"])
        poisson = float(config["poisson_ratio"])
        self.mu = young / (2.0 * (1.0 + poisson))
        self.la = young * poisson / ((1.0 + poisson) * (1.0 - 2.0 * poisson))

        self.x = ti.Vector.field(2, dtype=ti.f32, shape=self.n_particles)
        self.v = ti.Vector.field(2, dtype=ti.f32, shape=self.n_particles)
        self.C = ti.Matrix.field(2, 2, dtype=ti.f32, shape=self.n_particles)
        self.F = ti.Matrix.field(2, 2, dtype=ti.f32, shape=self.n_particles)
        self.J = ti.field(dtype=ti.f32, shape=self.n_particles)
        self.grid_v = ti.Vector.field(2, dtype=ti.f32, shape=(self.n_grid, self.n_grid))
        self.grid_m = ti.field(dtype=ti.f32, shape=(self.n_grid, self.n_grid))
        self.contact_force = ti.field(dtype=ti.f32, shape=())
        self.kinetic_energy = ti.field(dtype=ti.f32, shape=())
        self.elastic_energy = ti.field(dtype=ti.f32, shape=())

        self.x.from_numpy(initial_positions.astype(np.float32))
        self.initialize_state()

    @ti.kernel
    def initialize_state(self):
        for p in range(self.n_particles):
            self.v[p] = ti.Vector([0.0, 0.0])
            self.C[p] = ti.Matrix([[0.0, 0.0], [0.0, 0.0]])
            self.F[p] = ti.Matrix([[1.0, 0.0], [0.0, 1.0]])
            self.J[p] = 1.0

    @ti.kernel
    def substep(
        self,
        left_plate: ti.f32,
        right_plate: ti.f32,
        left_vel: ti.f32,
        right_vel: ti.f32,
        plate_y_min: ti.f32,
        plate_y_max: ti.f32,
        contact_skin: ti.f32,
    ):
        for i, j in self.grid_m:
            self.grid_v[i, j] = ti.Vector([0.0, 0.0])
            self.grid_m[i, j] = 0.0
        self.contact_force[None] = 0.0

        for p in self.x:
            base = (self.x[p] * self.inv_dx - 0.5).cast(int)
            fx = self.x[p] * self.inv_dx - base.cast(float)
            w = [
                0.5 * (1.5 - fx) ** 2,
                0.75 - (fx - 1.0) ** 2,
                0.5 * (fx - 0.5) ** 2,
            ]

            self.F[p] = (ti.Matrix.identity(ti.f32, 2) + self.dt * self.C[p]) @ self.F[p]
            U, sig, V = ti.svd(self.F[p])
            J = sig[0, 0] * sig[1, 1]
            self.J[p] = J
            rotation = U @ V.transpose()
            stress = 2.0 * self.mu * (self.F[p] - rotation) @ self.F[p].transpose()
            stress += ti.Matrix.identity(ti.f32, 2) * self.la * J * (J - 1.0)
            stress = (-self.dt * self.p_vol * 4.0 * self.inv_dx * self.inv_dx) * stress
            affine = stress + self.p_mass * self.C[p]

            for i, j in ti.static(ti.ndrange(3, 3)):
                offset = ti.Vector([i, j])
                dpos = (offset.cast(float) - fx) * self.dx
                weight = w[i][0] * w[j][1]
                grid_idx = base + offset
                self.grid_v[grid_idx] += weight * (self.p_mass * self.v[p] + affine @ dpos)
                self.grid_m[grid_idx] += weight * self.p_mass

        for i, j in self.grid_m:
            mass = self.grid_m[i, j]
            if mass > 0.0:
                velocity = self.grid_v[i, j] / mass
                velocity[1] += self.dt * self.gravity
                velocity *= ti.max(0.0, 1.0 - self.grid_damping * self.dt)

                node_pos = ti.Vector([i, j]) * self.dx
                padding = 3.0 * self.dx
                if node_pos[0] < padding and velocity[0] < 0.0:
                    velocity[0] = 0.0
                if node_pos[0] > self.domain_size - padding and velocity[0] > 0.0:
                    velocity[0] = 0.0
                if node_pos[1] < padding and velocity[1] < 0.0:
                    velocity[1] = 0.0
                if node_pos[1] > self.domain_size - padding and velocity[1] > 0.0:
                    velocity[1] = 0.0

                in_plate_height = node_pos[1] >= plate_y_min and node_pos[1] <= plate_y_max
                if in_plate_height and node_pos[0] < left_plate and velocity[0] < left_vel:
                    impulse = mass * (left_vel - velocity[0])
                    velocity[0] = left_vel
                    ti.atomic_add(self.contact_force[None], ti.abs(impulse) / self.dt)
                if in_plate_height and node_pos[0] > right_plate and velocity[0] > right_vel:
                    impulse = mass * (right_vel - velocity[0])
                    velocity[0] = right_vel
                    ti.atomic_add(self.contact_force[None], ti.abs(impulse) / self.dt)

                self.grid_v[i, j] = velocity

        for p in self.x:
            base = (self.x[p] * self.inv_dx - 0.5).cast(int)
            fx = self.x[p] * self.inv_dx - base.cast(float)
            w = [
                0.5 * (1.5 - fx) ** 2,
                0.75 - (fx - 1.0) ** 2,
                0.5 * (fx - 0.5) ** 2,
            ]
            new_v = ti.Vector([0.0, 0.0])
            new_C = ti.Matrix([[0.0, 0.0], [0.0, 0.0]])

            for i, j in ti.static(ti.ndrange(3, 3)):
                offset = ti.Vector([i, j])
                dpos = (offset.cast(float) - fx) * self.dx
                weight = w[i][0] * w[j][1]
                grid_idx = base + offset
                g_v = self.grid_v[grid_idx]
                new_v += weight * g_v
                new_C += 4.0 * self.inv_dx * weight * g_v.outer_product(dpos)

            self.v[p] = new_v
            self.C[p] = new_C
            self.x[p] += self.dt * self.v[p]

            eps = 2.0 * self.dx
            if self.x[p][1] >= plate_y_min and self.x[p][1] <= plate_y_max:
                left_limit = left_plate + contact_skin
                right_limit = right_plate - contact_skin
                if self.x[p][0] < left_limit:
                    correction = left_limit - self.x[p][0]
                    self.x[p][0] = left_limit
                    self.v[p][0] = ti.max(self.v[p][0], left_vel)
                    ti.atomic_add(self.contact_force[None], self.p_mass * correction / (self.dt * self.dt))
                if self.x[p][0] > right_limit:
                    correction = self.x[p][0] - right_limit
                    self.x[p][0] = right_limit
                    self.v[p][0] = ti.min(self.v[p][0], right_vel)
                    ti.atomic_add(self.contact_force[None], self.p_mass * correction / (self.dt * self.dt))

            self.x[p][0] = ti.min(ti.max(self.x[p][0], eps), self.domain_size - eps)
            self.x[p][1] = ti.min(ti.max(self.x[p][1], eps), self.domain_size - eps)

    @ti.kernel
    def compute_energy(self):
        self.kinetic_energy[None] = 0.0
        self.elastic_energy[None] = 0.0
        for p in self.x:
            ti.atomic_add(self.kinetic_energy[None], 0.5 * self.p_mass * self.v[p].dot(self.v[p]))
            strain = self.J[p] - 1.0
            ti.atomic_add(self.elastic_energy[None], 0.5 * (self.la + 2.0 * self.mu) * strain * strain * self.p_vol)


def run_simulation(config: dict, config_path: Path, frame_override: int | None, no_render: bool) -> Path:
    output_dir = Path(config["output_dir"])
    frames_dir = output_dir / "frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(config_path, output_dir / "used_config.json")

    positions = sample_particles(config)
    initial_stats = particle_geometry(positions)

    ti.init(
        arch=arch_from_name(config.get("arch", "cpu")),
        default_fp=ti.f32,
        random_seed=int(config.get("seed", 0)),
        offline_cache=False,
    )
    sim = MPMSimulator(config, positions)

    max_frames = int(frame_override if frame_override is not None else config["max_frames"])
    fps = int(config["fps"])
    substeps = int(config["substeps_per_frame"])
    dt = float(config["dt"])
    domain_size = float(config["domain_size_m"])
    render_every = int(config.get("render_every", 1))
    plate_thickness = float(config.get("plate_thickness_m", 0.006))
    plate_y_min, plate_y_max = plate_vertical_span(config)
    contact_skin = float(config.get("contact_skin_m", sim.dx * 0.5))

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
            sim.substep(left, right, left_vel, right_vel, plate_y_min, plate_y_max, contact_skin)
            frame_force += float(sim.contact_force[None])

        sim.compute_energy()
        points = sim.x.to_numpy()
        stats = particle_geometry(points)
        mean_j = float(np.mean(sim.J.to_numpy()))
        penetration = plate_penetration(points, left, right, plate_y_min, plate_y_max)
        wall_ms = (time.perf_counter() - frame_start) * 1000.0

        rows.append(
            {
                "engine": "taichi",
                "solver": "mpm",
                "scene": config["scene"],
                "frame": frame,
                "t": f"{t:.6f}",
                "dt": f"{dt:.8f}",
                "substeps": substeps,
                "particles": config["n_particles"],
                "grid_res": config["n_grid"],
                "squeeze_disp_m": f"{squeeze_disp:.8f}",
                "plate_force_n": f"{frame_force / max(1, substeps):.8f}",
                "height_m": f"{stats.height_m:.8f}",
                "width_m": f"{stats.width_m:.8f}",
                "volume_ratio": f"{mean_j:.8f}",
                "residual_strain": f"{abs(stats.height_m - initial_stats.height_m) / initial_stats.height_m:.8f}",
                "max_penetration_m": f"{penetration:.8f}",
                "kinetic_energy": f"{float(sim.kinetic_energy[None]):.8f}",
                "elastic_energy": f"{float(sim.elastic_energy[None]):.8f}",
                "wall_ms": f"{wall_ms:.4f}",
            }
        )

        if not no_render and frame % render_every == 0:
            frame_path = frames_dir / f"frame_{frame:04d}.png"
            title = f"{config['scene']}  t={t:.2f}s"
            render_frame(
                points,
                left,
                right,
                plate_thickness,
                plate_y_min,
                plate_y_max,
                domain_size,
                frame_path,
                title,
            )
            rendered_frames.append(frame_path)

        if frame == 0 or (frame + 1) % 10 == 0 or frame + 1 == max_frames:
            print(
                f"[{config['scene']}] frame {frame + 1:03d}/{max_frames} "
                f"force={frame_force / max(1, substeps):.3f}N "
                f"height={stats.height_m:.4f}m wall={wall_ms:.1f}ms"
            )

    metrics_path = output_dir / "metrics.csv"
    write_metrics_csv(metrics_path, rows)
    if not no_render:
        write_preview_gif(rendered_frames, output_dir / "preview.gif", fps=max(1, fps // max(1, render_every)))
    print(f"Wrote {metrics_path}")
    return metrics_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a 2D Taichi MLS-MPM squeeze simulation.")
    parser.add_argument("--config", type=Path, required=True, help="Path to a scene JSON config.")
    parser.add_argument("--frames", type=int, default=None, help="Override the configured frame count.")
    parser.add_argument("--no-render", action="store_true", help="Skip PNG/GIF rendering and only write metrics.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    run_simulation(config, args.config, args.frames, args.no_render)
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":
        # Avoid a Taichi 1.7 shutdown UnicodeDecodeError in non-ASCII Windows paths.
        os._exit(0)


if __name__ == "__main__":
    main()
