# GKCIV Taichi 3D Soft-Body Squeeze Experiments

This project runs a standardized 3D squeeze benchmark for Taichi soft-body simulation methods.
The current experiment matrix contains 20 runs:

- MPM Neo-Hookean / Corotated, sphere and cube, soft and hard materials
- FEM Neo-Hookean / Corotated, sphere and cube, soft and hard materials
- PBD sphere and cube, soft and hard constraint settings

The timestep cores for MPM, FEM, and PBD are implemented with Taichi kernels. Python is used for
configuration, mesh/point-cloud setup, metrics export, and rendering orchestration.

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

Full metrics plus PNG/GIF rendering:

```powershell
python run_all.py
```

Useful filters:

```powershell
python run_all.py --frames 10 --no-render
python run_all.py --filter fem3d --frames 10 --no-render
python run_all.py --filter sphere_40mm_soft
```

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
