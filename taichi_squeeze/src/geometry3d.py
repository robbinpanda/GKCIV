from __future__ import annotations

import math

import numpy as np


def object_size(config: dict) -> np.ndarray:
    if config["shape"] == "sphere":
        diameter = float(config["object_diameter_m"])
        return np.array([diameter, diameter, diameter], dtype=np.float64)
    return np.array(config["object_size_m"], dtype=np.float64)


def squeeze_diameter(config: dict) -> float:
    if "object_diameter_m" in config:
        return float(config["object_diameter_m"])
    return float(config["object_size_m"][0])


def analytical_volume(config: dict) -> float:
    if config["shape"] == "sphere":
        radius = float(config["object_diameter_m"]) * 0.5
        return 4.0 / 3.0 * math.pi * radius**3
    sx, sy, sz = config["object_size_m"]
    return float(sx) * float(sy) * float(sz)


def fibonacci_sphere_points(center: np.ndarray, radius: float, count: int) -> np.ndarray:
    if count <= 0:
        return np.empty((0, 3), dtype=np.float64)

    indices = np.arange(count, dtype=np.float64) + 0.5
    z = 1.0 - 2.0 * indices / count
    theta = math.pi * (1.0 + 5.0**0.5) * indices
    xy = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    points = np.column_stack((np.cos(theta) * xy, np.sin(theta) * xy, z))

    axis_points = np.array(
        [
            [1.0, 0.0, 0.0],
            [-1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, -1.0, 0.0],
            [0.0, 0.0, 1.0],
            [0.0, 0.0, -1.0],
        ],
        dtype=np.float64,
    )
    return np.vstack((points, axis_points)) * radius + center


def sphere_interior_grid_points(center: np.ndarray, radius: float, resolution: np.ndarray, surface_margin: float = 0.92) -> np.ndarray:
    axes = [
        np.linspace(center[i] - radius, center[i] + radius, max(2, int(resolution[i])))
        for i in range(3)
    ]
    grid = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1, 3)
    distance = np.linalg.norm(grid - center, axis=1)
    points = grid[distance <= radius * surface_margin]
    if not np.any(np.linalg.norm(points - center, axis=1) < 1e-12):
        points = np.vstack((points, center))
    return points.astype(np.float64)


def unique_points(points: np.ndarray, decimals: int = 10) -> np.ndarray:
    rounded = np.round(points, decimals=decimals)
    _, unique_idx = np.unique(rounded, axis=0, return_index=True)
    return points[np.sort(unique_idx)]


def spherical_point_cloud(config: dict, resolution_key: str, surface_key: str, default_surface_points: int) -> tuple[np.ndarray, float]:
    center = np.array(config["object_center_m"], dtype=np.float64)
    radius = float(config["object_diameter_m"]) * 0.5
    resolution = np.array(config[resolution_key], dtype=int)
    surface_count = int(config.get(surface_key, default_surface_points))

    interior = sphere_interior_grid_points(center, radius, resolution)
    surface = fibonacci_sphere_points(center, radius, surface_count)
    return unique_points(np.vstack((interior, surface))), radius
