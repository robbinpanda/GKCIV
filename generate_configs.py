from __future__ import annotations

import json
from pathlib import Path

CONFIGS_DIR = Path("taichi_squeeze/configs")

SCENES = [
    {
        "scene_id": "sphere_40mm",
        "shape": "sphere",
        "object_diameter_m": 0.04,
        "object_center_m": [0.05, 0.05, 0.05],
    },
    {
        "scene_id": "cube_40mm",
        "shape": "box",
        "object_size_m": [0.04, 0.04, 0.04],
        "object_center_m": [0.05, 0.05, 0.05],
    },
]

STIFFNESS = [
    {"stiffness_id": "soft", "young_modulus_pa": 30000},
    {"stiffness_id": "hard", "young_modulus_pa": 80000},
]

MPM_CONFIGS = [
    {"solver": "mpm3d", "constitutive_model": "corotated"},
    {"solver": "mpm3d", "constitutive_model": "neo_hookean"},
]

FEM_CONFIGS = [
    {"solver": "fem3d", "constitutive_model": "corotated"},
    {"solver": "fem3d", "constitutive_model": "neo_hookean"},
]

PBD_CONFIG = {"solver": "pbd3d", "constitutive_model": "none"}
FPS = 60


def frame_dt(substeps: int) -> float:
    return round(1.0 / FPS / substeps, 10)


def make_mpm_config(scene: dict, stiff: dict, model: dict) -> dict:
    name = f"{model['solver']}_{scene['scene_id']}_{stiff['stiffness_id']}_{model['constitutive_model']}"
    mpm_substeps = 167
    cfg = {
        "solver": model["solver"],
        "constitutive_model": model["constitutive_model"],
        "scene": name,
        "shape": scene["shape"],
        "object_center_m": scene["object_center_m"],
        "density_kg_m3": 1000,
        "young_modulus_pa": stiff["young_modulus_pa"],
        "poisson_ratio": 0.35,
        "n_particles": 4000,
        "n_grid": 32,
        "domain_size_m": 0.1,
        "dt": frame_dt(mpm_substeps),
        "substeps_per_frame": mpm_substeps,
        "fps": FPS,
        "max_frames": 390,
        "initial_gap_ratio": 1.05,
        "min_gap_ratio": 0.50,
        "compress_time_s": 1.0,
        "hold_time_s": 0.5,
        "release_time_s": 1.0,
        "plate_thickness_m": 0.006,
        "contact_skin_m": 0.00025,
        "grid_contact_margin_cells": 0.5,
        "grid_velocity_damping": 0.0,
        "gravity_m_s2": 0.0,
        "arch": "cpu",
        "seed": 42,
        "output_dir": f"outputs/{name}",
        "render_every": 1,
        "render_backend": "matplotlib",
        "particle_radius_m": 0.0009,
    }
    if scene["shape"] == "sphere":
        cfg["object_diameter_m"] = scene["object_diameter_m"]
    else:
        cfg["object_size_m"] = scene["object_size_m"]
    return cfg


def make_fem_config(scene: dict, stiff: dict, model: dict) -> dict:
    name = f"{model['solver']}_{scene['scene_id']}_{stiff['stiffness_id']}_{model['constitutive_model']}"
    fem_substeps = 48
    cfg = {
        "solver": model["solver"],
        "constitutive_model": model["constitutive_model"],
        "scene": name,
        "shape": scene["shape"],
        "object_center_m": scene["object_center_m"],
        "density_kg_m3": 1000,
        "young_modulus_pa": stiff["young_modulus_pa"],
        "poisson_ratio": 0.35,
        "mesh_resolution": [9, 9, 9] if scene["shape"] == "sphere" else [8, 8, 8],
        "sphere_surface_points": 192,
        "domain_size_m": 0.1,
        "dt": frame_dt(fem_substeps),
        "substeps_per_frame": fem_substeps,
        "fps": FPS,
        "max_frames": 390,
        "initial_gap_ratio": 1.05,
        "min_gap_ratio": 0.50,
        "compress_time_s": 1.0,
        "hold_time_s": 0.5,
        "release_time_s": 1.0,
        "plate_thickness_m": 0.006,
        "contact_skin_m": 0.00025,
        "velocity_damping": 3.0,
        "max_velocity_m_s": 2.0,
        "max_tet_condition": 120.0,
        "lock_transverse_center": True,
        "center_lock_strength": 1.0,
        "gravity_m_s2": 0.0,
        "arch": "cpu",
        "seed": 42,
        "output_dir": f"outputs/{name}",
        "render_every": 1,
        "render_backend": "matplotlib",
        "particle_radius_m": 0.0010,
    }
    if scene["shape"] == "sphere":
        cfg["object_diameter_m"] = scene["object_diameter_m"]
    else:
        cfg["object_size_m"] = scene["object_size_m"]
    return cfg


def make_pbd_config(scene: dict, stiff: dict) -> dict:
    name = f"pbd3d_{scene['scene_id']}_{stiff['stiffness_id']}"
    pbd_substeps = 17
    cfg = {
        "solver": "pbd3d",
        "constitutive_model": "none",
        "scene": name,
        "shape": scene["shape"],
        "object_center_m": scene["object_center_m"],
        "density_kg_m3": 1000,
        "lattice_resolution": [13, 13, 13] if scene["shape"] == "sphere" else [12, 12, 12],
        "sphere_surface_points": 256,
        "constraint_stiffness": 0.8,
        "pbd_iterations": 5,
        "domain_size_m": 0.1,
        "dt": frame_dt(pbd_substeps),
        "substeps_per_frame": pbd_substeps,
        "fps": FPS,
        "max_frames": 390,
        "initial_gap_ratio": 1.05,
        "min_gap_ratio": 0.50,
        "compress_time_s": 1.0,
        "hold_time_s": 0.5,
        "release_time_s": 1.0,
        "plate_thickness_m": 0.006,
        "contact_skin_m": 0.00025,
        "velocity_damping": 0.0,
        "gravity_m_s2": 0.0,
        "arch": "cpu",
        "seed": 42,
        "output_dir": f"outputs/{name}",
        "render_every": 1,
        "render_backend": "matplotlib",
        "particle_radius_m": 0.0010,
    }
    if scene["shape"] == "sphere":
        cfg["object_diameter_m"] = scene["object_diameter_m"]
    else:
        cfg["object_size_m"] = scene["object_size_m"]
    return cfg


def main() -> None:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    for old_config in CONFIGS_DIR.glob("*.json"):
        if old_config.name not in {"camera.json", "color_scheme.json"}:
            old_config.unlink()

    count = 0
    for scene in SCENES:
        for stiff in STIFFNESS:
            for model in MPM_CONFIGS:
                cfg = make_mpm_config(scene, stiff, model)
                path = CONFIGS_DIR / f"{cfg['scene']}.json"
                path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
                count += 1
                print(f"Generated: {path.name}")

            for model in FEM_CONFIGS:
                cfg = make_fem_config(scene, stiff, model)
                path = CONFIGS_DIR / f"{cfg['scene']}.json"
                path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
                count += 1
                print(f"Generated: {path.name}")

            cfg = make_pbd_config(scene, stiff)
            path = CONFIGS_DIR / f"{cfg['scene']}.json"
            path.write_text(json.dumps(cfg, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
            count += 1
            print(f"Generated: {path.name}")

    print(f"\nTotal: {count} configs generated")


if __name__ == "__main__":
    main()
