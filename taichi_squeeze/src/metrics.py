from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


METRIC_COLUMNS = [
    "engine",
    "solver",
    "scene",
    "frame",
    "t",
    "dt",
    "substeps",
    "particles",
    "grid_res",
    "squeeze_disp_m",
    "plate_force_n",
    "height_m",
    "width_m",
    "volume_ratio",
    "residual_strain",
    "max_penetration_m",
    "kinetic_energy",
    "elastic_energy",
    "wall_ms",
]


@dataclass(frozen=True)
class GeometryStats:
    height_m: float
    width_m: float
    min_x_m: float
    max_x_m: float
    min_y_m: float
    max_y_m: float


def particle_geometry(points: np.ndarray) -> GeometryStats:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    return GeometryStats(
        height_m=float(maxs[1] - mins[1]),
        width_m=float(maxs[0] - mins[0]),
        min_x_m=float(mins[0]),
        max_x_m=float(maxs[0]),
        min_y_m=float(mins[1]),
        max_y_m=float(maxs[1]),
    )


def write_metrics_csv(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=METRIC_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in METRIC_COLUMNS})

