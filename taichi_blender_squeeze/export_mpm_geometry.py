from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
from pathlib import Path

import numpy as np
import taichi as ti

from taichi_squeeze.src.metrics import write_metrics_csv
from taichi_squeeze.src.simulate_mpm3d import (
    MPM3DSimulator,
    arch_from_name,
    load_config,
    particle_geometry_3d,
    plate_motion,
    plate_penetration,
    plate_span,
    sample_particles,
)


DEFAULT_CONFIG = Path("taichi_squeeze/configs/mpm3d_cube_40mm_soft_corotated.json")
DEFAULT_OUTPUT_ROOT = Path("taichi_blender_squeeze/outputs/geometry")


def parse_frame_list(raw: str | None) -> set[int] | None:
    if raw is None or raw.strip() == "":
        return None
    frames: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        frames.add(int(part))
    return frames


def should_export_frame(frame: int, keyframes: set[int] | None, frame_stride: int) -> bool:
    if keyframes is not None:
        return frame in keyframes
    return frame % max(1, frame_stride) == 0


def write_plate_rows(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "frame",
        "t",
        "left_plate",
        "right_plate",
        "plate_y_min",
        "plate_y_max",
        "plate_z_min",
        "plate_z_max",
        "plate_thickness",
        "domain_size",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_geometry(
    config_path: Path,
    output_root: Path,
    frame_override: int | None,
    frame_stride: int,
    keyframes: set[int] | None,
    arch_override: str | None,
    clean: bool,
) -> Path:
    config = load_config(config_path)
    if arch_override:
        config["arch"] = arch_override

    scene = str(config["scene"])
    output_dir = output_root / scene
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    positions = sample_particles(config)
    initial_stats = particle_geometry_3d(positions)

    ti.init(
        arch=arch_from_name(config.get("arch", "cpu")),
        default_fp=ti.f32,
        random_seed=int(config.get("seed", 0)),
        offline_cache=False,
    )
    sim = MPM3DSimulator(config, positions)

    max_frames = int(frame_override if frame_override is not None else config["max_frames"])
    if keyframes:
        max_frames = max(max_frames, max(keyframes) + 1)

    fps = int(config["fps"])
    substeps = int(config["substeps_per_frame"])
    dt = float(config["dt"])
    domain_size = float(config["domain_size_m"])
    plate_thickness = float(config.get("plate_thickness_m", 0.006))
    plate_y_min, plate_y_max, plate_z_min, plate_z_max = plate_span(config)
    contact_skin = float(config.get("contact_skin_m", sim.dx * 0.5))
    grid_contact_margin = max(contact_skin, float(config.get("grid_contact_margin_cells", 0.5)) * sim.dx)

    metrics_rows: list[dict[str, object]] = []
    plate_rows: list[dict[str, object]] = []
    exported_frames: list[int] = []

    for frame in range(max_frames):
        frame_start = time.perf_counter()
        frame_force = 0.0
        t = frame / fps
        left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, t)

        for substep_id in range(substeps):
            sub_t = t + substep_id * dt
            left, right, left_vel, right_vel, squeeze_disp = plate_motion(config, sub_t)
            sim.substep(
                left,
                right,
                left_vel,
                right_vel,
                plate_y_min,
                plate_y_max,
                plate_z_min,
                plate_z_max,
                contact_skin,
                grid_contact_margin,
            )
            frame_force += float(sim.contact_force[None])

        sim.compute_energy()
        points = sim.x.to_numpy().astype(np.float32)
        stats = particle_geometry_3d(points)
        mean_j = float(np.mean(sim.J.to_numpy()))
        penetration = plate_penetration(points, left, right, plate_y_min, plate_y_max, plate_z_min, plate_z_max)
        wall_ms = (time.perf_counter() - frame_start) * 1000.0

        if should_export_frame(frame, keyframes, frame_stride):
            np.savez_compressed(
                output_dir / f"particles_{frame:04d}.npz",
                positions=points,
                frame=np.array(frame, dtype=np.int32),
                t=np.array(t, dtype=np.float32),
                left_plate=np.array(left, dtype=np.float32),
                right_plate=np.array(right, dtype=np.float32),
                domain_size=np.array(domain_size, dtype=np.float32),
            )
            plate_rows.append(
                {
                    "frame": frame,
                    "t": f"{t:.8f}",
                    "left_plate": f"{left:.8f}",
                    "right_plate": f"{right:.8f}",
                    "plate_y_min": f"{plate_y_min:.8f}",
                    "plate_y_max": f"{plate_y_max:.8f}",
                    "plate_z_min": f"{plate_z_min:.8f}",
                    "plate_z_max": f"{plate_z_max:.8f}",
                    "plate_thickness": f"{plate_thickness:.8f}",
                    "domain_size": f"{domain_size:.8f}",
                }
            )
            exported_frames.append(frame)

        metrics_rows.append(
            {
                "engine": "taichi",
                "solver": "mpm3d",
                "scene": scene,
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
                "residual_strain": f"{abs(stats.width_m - initial_stats.width_m) / initial_stats.width_m:.8f}",
                "max_penetration_m": f"{penetration:.8f}",
                "kinetic_energy": f"{float(sim.kinetic_energy[None]):.8f}",
                "elastic_energy": f"{float(sim.elastic_energy[None]):.8f}",
                "wall_ms": f"{wall_ms:.4f}",
            }
        )

        if frame == 0 or (frame + 1) % 10 == 0 or frame + 1 == max_frames:
            print(
                f"[{scene}] frame {frame + 1:03d}/{max_frames} "
                f"exported={len(exported_frames)} force={frame_force / max(1, substeps):.3f}N"
            )

    write_metrics_csv(output_dir / "metrics.csv", metrics_rows)
    write_plate_rows(output_dir / "plates.csv", plate_rows)
    shutil.copyfile(config_path, output_dir / "used_config.json")
    with (output_dir / "export_config.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "config": str(config_path),
                "scene": scene,
                "frames_simulated": max_frames,
                "exported_frames": exported_frames,
                "frame_stride": frame_stride,
                "keyframes": sorted(keyframes) if keyframes else None,
            },
            f,
            indent=2,
        )

    print(f"Wrote geometry export to {output_dir}")
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Taichi MPM squeeze particles for Blender reconstruction.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--frames", type=int, default=None, help="Override simulation frame count.")
    parser.add_argument("--frame-stride", type=int, default=2, help="Export every Nth frame when --keyframes is not set.")
    parser.add_argument("--keyframes", type=str, default=None, help="Comma-separated frames to export, e.g. 0,60,90,150,389.")
    parser.add_argument("--arch", type=str, default=None, help="Override Taichi arch: cpu, cuda, or vulkan.")
    parser.add_argument("--no-clean", action="store_true", help="Keep existing files in the output scene folder.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    export_geometry(
        config_path=args.config,
        output_root=args.output_root,
        frame_override=args.frames,
        frame_stride=args.frame_stride,
        keyframes=parse_frame_list(args.keyframes),
        arch_override=args.arch,
        clean=not args.no_clean,
    )


if __name__ == "__main__":
    main()
