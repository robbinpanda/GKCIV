from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

import numpy as np


DEFAULT_INPUT = Path("taichi_blender_squeeze/outputs/geometry/mpm3d_cube_40mm_soft_corotated")
DEFAULT_OUTPUT = Path("taichi_blender_squeeze/outputs/meshes/mpm3d_cube_40mm_soft_corotated")


def read_plate_rows(path: Path) -> list[dict[str, object]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return [
            {
                "frame": int(row["frame"]),
                "t": float(row["t"]),
                "left_plate": float(row["left_plate"]),
                "right_plate": float(row["right_plate"]),
                "plate_y_min": float(row["plate_y_min"]),
                "plate_y_max": float(row["plate_y_max"]),
                "plate_z_min": float(row["plate_z_min"]),
                "plate_z_max": float(row["plate_z_max"]),
                "plate_thickness": float(row["plate_thickness"]),
                "domain_size": float(row["domain_size"]),
            }
            for row in csv.DictReader(f)
        ]


def load_particle_files(input_dir: Path) -> list[tuple[int, Path, np.ndarray]]:
    files = sorted(input_dir.glob("particles_*.npz"))
    if not files:
        raise FileNotFoundError(f"No particle files found in {input_dir}")

    loaded: list[tuple[int, Path, np.ndarray]] = []
    for path in files:
        with np.load(path) as data:
            frame = int(data["frame"])
            points = np.asarray(data["positions"], dtype=np.float32)
        loaded.append((frame, path, points))
    return loaded


def estimate_kernel_radius(points: np.ndarray, radius_scale: float) -> float:
    extent = np.max(points, axis=0) - np.min(points, axis=0)
    particle_spacing = float(np.max(extent)) / max(2.0, np.cbrt(len(points)))
    return max(0.0015, particle_spacing * radius_scale)


def splat_density(points: np.ndarray, bounds_min: np.ndarray, bounds_max: np.ndarray, resolution: int, radius_scale: float) -> np.ndarray:
    grid = np.zeros((resolution, resolution, resolution), dtype=np.float32)
    cell = (bounds_max - bounds_min) / (resolution - 1)
    h = estimate_kernel_radius(points, radius_scale)
    radius_cells = int(np.ceil(2.5 * h / float(np.min(cell))))

    offsets = []
    for ox in range(-radius_cells, radius_cells + 1):
        for oy in range(-radius_cells, radius_cells + 1):
            for oz in range(-radius_cells, radius_cells + 1):
                offsets.append((ox, oy, oz))
    offsets_np = np.asarray(offsets, dtype=np.int32)

    grid_pos = (points - bounds_min) / cell
    centers = np.rint(grid_pos).astype(np.int32)
    inv_two_h2 = 1.0 / (2.0 * h * h)

    for point, center in zip(points, centers):
        idxs = center[None, :] + offsets_np
        mask = np.all((idxs >= 0) & (idxs < resolution), axis=1)
        idxs = idxs[mask]
        world = bounds_min + idxs * cell
        dist2 = np.sum((world - point) ** 2, axis=1)
        values = np.exp(-dist2 * inv_two_h2).astype(np.float32)
        grid[idxs[:, 0], idxs[:, 1], idxs[:, 2]] += values

    return grid


def write_ascii_ply(path: Path, vertices: np.ndarray, faces: np.ndarray) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write("ply\n")
        f.write("format ascii 1.0\n")
        f.write(f"element vertex {len(vertices)}\n")
        f.write("property float x\n")
        f.write("property float y\n")
        f.write("property float z\n")
        f.write(f"element face {len(faces)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for x, y, z in vertices:
            f.write(f"{x:.8f} {y:.8f} {z:.8f}\n")
        for a, b, c in faces:
            f.write(f"3 {int(a)} {int(b)} {int(c)}\n")


def build_vertex_neighbors(vertex_count: int, faces: np.ndarray) -> list[np.ndarray]:
    neighbors: list[set[int]] = [set() for _ in range(vertex_count)]
    for a, b, c in faces:
        ai, bi, ci = int(a), int(b), int(c)
        neighbors[ai].update((bi, ci))
        neighbors[bi].update((ai, ci))
        neighbors[ci].update((ai, bi))
    return [np.fromiter(items, dtype=np.int32) if items else np.empty(0, dtype=np.int32) for items in neighbors]


def taubin_smooth(vertices: np.ndarray, faces: np.ndarray, iterations: int, lambda_factor: float = 0.45, mu_factor: float = -0.48) -> np.ndarray:
    if iterations <= 0 or len(vertices) == 0 or len(faces) == 0:
        return vertices

    smoothed = vertices.astype(np.float64, copy=True)
    neighbors = build_vertex_neighbors(len(smoothed), faces)
    for _ in range(iterations):
        for factor in (lambda_factor, mu_factor):
            updated = smoothed.copy()
            for idx, adjacent in enumerate(neighbors):
                if len(adjacent) == 0:
                    continue
                centroid = smoothed[adjacent].mean(axis=0)
                updated[idx] = smoothed[idx] + factor * (centroid - smoothed[idx])
            smoothed = updated
    return smoothed.astype(vertices.dtype, copy=False)


def taichi_to_blender(points: np.ndarray) -> np.ndarray:
    return points[:, [0, 2, 1]]


def reconstruct_frame(
    frame: int,
    points: np.ndarray,
    output_dir: Path,
    bounds_min: np.ndarray,
    bounds_max: np.ndarray,
    resolution: int,
    radius_scale: float,
    threshold_ratio: float,
    smooth_iterations: int,
) -> Path:
    try:
        from skimage.measure import marching_cubes
    except ImportError as exc:
        raise RuntimeError("scikit-image is required for marching cubes: pip install scikit-image") from exc

    density = splat_density(points, bounds_min, bounds_max, resolution, radius_scale)
    level = max(1e-5, float(np.max(density)) * threshold_ratio)
    verts, faces, _normals, _values = marching_cubes(density, level=level)

    cell = (bounds_max - bounds_min) / (resolution - 1)
    verts_world = bounds_min + verts * cell
    verts_world = taichi_to_blender(verts_world)
    verts_world = taubin_smooth(verts_world, faces, smooth_iterations)
    mesh_path = output_dir / f"mesh_{frame:04d}.ply"
    write_ascii_ply(mesh_path, verts_world.astype(np.float32), faces.astype(np.int32))
    return mesh_path


def reconstruct_sequence(
    input_dir: Path,
    output_dir: Path,
    resolution: int,
    radius_scale: float,
    threshold_ratio: float,
    smooth_iterations: int,
    clean: bool,
) -> Path:
    loaded = load_particle_files(input_dir)
    if clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_points = np.vstack([points for _frame, _path, points in loaded])
    margin = max(0.006, estimate_kernel_radius(all_points, radius_scale) * 2.0)
    bounds_min = np.maximum(0.0, np.min(all_points, axis=0) - margin)
    bounds_max = np.minimum(0.1, np.max(all_points, axis=0) + margin)

    exported_meshes = []
    for frame, _path, points in loaded:
        mesh_path = reconstruct_frame(
            frame,
            points,
            output_dir,
            bounds_min,
            bounds_max,
            resolution,
            radius_scale,
            threshold_ratio,
            smooth_iterations,
        )
        exported_meshes.append(mesh_path.name)
        print(f"[mesh] frame {frame:04d} -> {mesh_path}")

    plates_path = input_dir / "plates.csv"
    if plates_path.exists():
        plates = read_plate_rows(plates_path)
        with (output_dir / "plates.json").open("w", encoding="utf-8") as f:
            json.dump(plates, f, indent=2)

    with (output_dir / "reconstruction_config.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "input_dir": str(input_dir),
                "resolution": resolution,
                "radius_scale": radius_scale,
                "threshold_ratio": threshold_ratio,
                "smooth_iterations": smooth_iterations,
                "bounds_min": bounds_min.tolist(),
                "bounds_max": bounds_max.tolist(),
                "meshes": exported_meshes,
            },
            f,
            indent=2,
        )

    print(f"Wrote mesh sequence to {output_dir}")
    return output_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstruct Blender-ready PLY meshes from MPM particle exports.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution", type=int, default=96)
    parser.add_argument("--radius-scale", type=float, default=2.0)
    parser.add_argument("--threshold-ratio", type=float, default=0.18)
    parser.add_argument("--smooth-iterations", type=int, default=8)
    parser.add_argument("--no-clean", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    reconstruct_sequence(
        input_dir=args.input,
        output_dir=args.output,
        resolution=args.resolution,
        radius_scale=args.radius_scale,
        threshold_ratio=args.threshold_ratio,
        smooth_iterations=args.smooth_iterations,
        clean=not args.no_clean,
    )


if __name__ == "__main__":
    main()
