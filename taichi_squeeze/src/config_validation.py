from __future__ import annotations

from pathlib import Path


def validate_frame_timestep(config: dict, config_path: Path | None = None, tolerance: float = 1e-8) -> None:
    """Ensure one rendered frame advances exactly one configured frame of physics."""
    fps = float(config["fps"])
    dt = float(config["dt"])
    substeps = int(config["substeps_per_frame"])
    expected = 1.0 / fps
    actual = dt * substeps
    if abs(actual - expected) <= tolerance:
        return

    label = str(config_path) if config_path else str(config.get("scene", "<config>"))
    raise ValueError(
        f"{label}: inconsistent timestep settings: dt * substeps_per_frame = {actual:.10f}s, "
        f"but 1 / fps = {expected:.10f}s. Fix dt or substeps_per_frame before running."
    )
