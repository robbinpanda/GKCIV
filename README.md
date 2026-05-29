# GKCIV Taichi MPM Squeeze Experiment

This project implements the Taichi part of the GKCIV soft-body squeeze comparison. The current code path uses only a 2D MLS-MPM solver and exports both simulation metrics and analysis plots.

The squeeze fixture is modeled as two finite-thickness kinematic rigid plates. They move by a prescribed displacement path, collide with the MPM material through grid velocity constraints, and project escaped particles back outside the plate volume to prevent visible penetration.

## 1. Environment

```powershell
conda activate GKCIV
```

If the environment has not been created yet:

```powershell
conda env create -f environment.yml
conda activate GKCIV
```

## 2. Run A Simulation

Sphere scene:

```powershell
python -m taichi_squeeze.src.simulate_mpm --config taichi_squeeze/configs/sphere_50mm_soft.json
```

Rounded cube scene:

```powershell
python -m taichi_squeeze.src.simulate_mpm --config taichi_squeeze/configs/cube_50mm_soft.json
```

Each run writes:

- `metrics.csv`
- rendered PNG frames
- `preview.gif`
- `used_config.json`

## 3. Generate Analysis Plots

```powershell
python -m taichi_squeeze.analysis.compare_curves --outputs outputs
```

The analysis script scans all `outputs/*/metrics.csv` files and writes plots into `outputs/analysis/`.

## 4. Useful Quick Test

For a shorter smoke test:

```powershell
python -m taichi_squeeze.src.simulate_mpm --config taichi_squeeze/configs/sphere_50mm_soft.json --frames 20 --no-render
python -m taichi_squeeze.analysis.compare_curves --outputs outputs
```

## 5. Run 3D MPM Experiments

The 3D solver is separate from the 2D solver:

```powershell
python -m taichi_squeeze.src.simulate_mpm3d --config taichi_squeeze/configs/sphere_3d_40mm_soft.json
python -m taichi_squeeze.src.simulate_mpm3d --config taichi_squeeze/configs/box_3d_45x35x35_soft.json
python -m taichi_squeeze.analysis.compare_curves --outputs outputs
```

For a faster 3D smoke test:

```powershell
python -m taichi_squeeze.src.simulate_mpm3d --config taichi_squeeze/configs/sphere_3d_40mm_soft.json --frames 10 --no-render
```
