# GKCIV Taichi 3D Soft-Body Squeeze Experiments

This project runs a standardized 3D squeeze benchmark for Taichi soft-body simulation methods.
The current experiment matrix contains 20 runs:

- MPM Neo-Hookean / Corotated, sphere and cube, soft and hard materials
- FEM Neo-Hookean / Corotated, sphere and cube, soft and hard materials
- PBD sphere and cube, soft and hard constraint settings

The timestep cores for MPM, FEM, and PBD are implemented with Taichi kernels. Python is used for
configuration, mesh/point-cloud setup, metrics export, and rendering orchestration.

## Project Layout

```text
taichi_squeeze/              # Phase 1: Taichi 3D squeeze simulation, rendering, metrics
taichi_blender_squeeze/      # Phase 2: MPM geometry export, surface reconstruction, Blender scripts
outputs/                     # Phase 1 generated results, ignored by git
docs/phase1/                 # Phase 1 report and improvement plan
docs/phase2/                 # Blender rendering plan
docs/reviews/                # Repository review notes
run_all.py                   # Batch runner for the 20 Phase 1 configurations
generate_configs.py          # Recreate the 20 experiment configs
```

Key documents:

- `docs/phase1/EXPERIMENT_REPORT.md`
- `docs/phase1/IMPROVEMENT_PLAN.md`
- `docs/phase2/TAICHI_BLENDER_RENDER_PLAN.md`
- `docs/reviews/REPOSITORY_REVIEW_2026-05-31.md`

## Environment

```powershell
conda env create -f environment.yml
conda activate GKCIV
```

If the environment already exists:

```powershell
conda activate GKCIV
```

## Generate Configs

```powershell
python generate_configs.py
```

This recreates the 20 experiment JSON files in `taichi_squeeze/configs/` while preserving
`camera.json` and `color_scheme.json`.

## Run All Experiments

Metrics-only run:

```powershell
python run_all.py --no-render
```

Full metrics plus PNG/GIF rendering. The default renderer is the original Matplotlib 3D view because
it preserves the coordinate axes and plate/object spatial relationship most clearly:

```powershell
python run_all.py
```

Useful filters:

```powershell
python run_all.py --frames 10 --no-render
python run_all.py --filter fem3d --frames 10 --no-render
python run_all.py --filter sphere_40mm_soft
```

PyVista rendering remains available by setting `"render_backend": "pyvista"` in selected configs,
but it is not the default for report-quality batch output.

## Single Solver Runs

```powershell
python -m taichi_squeeze.src.simulate_mpm3d --config taichi_squeeze/configs/mpm3d_sphere_40mm_soft_corotated.json --frames 10 --no-render
python -m taichi_squeeze.src.simulate_fem3d --config taichi_squeeze/configs/fem3d_sphere_40mm_soft_corotated.json --frames 10 --no-render
python -m taichi_squeeze.src.simulate_pbd3d --config taichi_squeeze/configs/pbd3d_sphere_40mm_soft.json --frames 10 --no-render
```

## Analysis

```powershell
python -m taichi_squeeze.analysis.compare_curves --outputs outputs --out outputs/analysis
```

Each run writes `metrics.csv`, `used_config.json`, optional PNG frames, and `preview.gif` into its
own directory under `outputs/`.

## Blender Pipeline

The Blender stage is intentionally isolated under `taichi_blender_squeeze/`. It exports MPM
particles, reconstructs PLY meshes, and uses Blender scripts for scene setup and rendering. Blender
is not required for Phase 1, but must be installed and available on `PATH` or passed as an explicit
`blender.exe` path before Phase 2 can be rendered.
