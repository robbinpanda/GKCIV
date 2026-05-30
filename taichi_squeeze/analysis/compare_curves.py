from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


STYLE_BY_SOLVER = {
    "mpm": {"color": "#2563eb", "marker": "o"},
    "mpm3d": {"color": "#2563eb", "marker": "o"},
    "pbd3d": {"color": "#16a34a", "marker": "s"},
    "fem3d": {"color": "#dc2626", "marker": "^"},
}


def label_from_run_dir(run_dir: str) -> str:
    parts = run_dir.split("_")
    solver = parts[0].replace("3d", "").upper() if parts else run_dir
    shape = "cube" if "cube" in parts else "sphere" if "sphere" in parts else ""
    material = "soft" if "soft" in parts else "hard" if "hard" in parts else ""
    if "neo" in parts and "hookean" in parts:
        model = "NH"
    elif "corotated" in parts:
        model = "CR"
    else:
        model = ""
    return " ".join(part for part in [solver, shape, material, model] if part)


def linestyle_from_run_dir(run_dir: str) -> str:
    if "neo_hookean" in run_dir:
        return "--"
    if "corotated" in run_dir:
        return "-"
    return ":"


def find_metric_files(outputs: Path, contains: str | None = None) -> list[Path]:
    paths = sorted(path for path in outputs.glob("*/metrics.csv") if path.is_file())
    if contains:
        paths = [path for path in paths if contains.lower() in path.parent.name.lower()]
    return paths


def load_metrics(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        df = pd.read_csv(path)
        df["run_dir"] = path.parent.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No metrics.csv files found.")
    return pd.concat(frames, ignore_index=True)


def style_for_group(group: pd.DataFrame, fallback_label: str) -> dict:
    solver = str(group["solver"].iloc[0]).lower()
    style = STYLE_BY_SOLVER.get(solver, {})
    return {
        "label": label_from_run_dir(fallback_label),
        "color": style.get("color", None),
        "marker": style.get("marker", "o"),
        "linestyle": linestyle_from_run_dir(fallback_label),
    }


def plot_lines(df: pd.DataFrame, x: str, y: str, out: Path, xlabel: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(9.5, 5.6), dpi=160)
    plotted = 0
    for label, group in df.groupby("run_dir"):
        group = group.sort_values(x if x != "normalized_compression" else "frame")
        values = pd.to_numeric(group[y], errors="coerce")
        xs = pd.to_numeric(group[x], errors="coerce")
        mask = values.notna() & xs.notna()
        if not mask.any():
            continue
        style = style_for_group(group, label)
        ax.plot(
            xs[mask],
            values[mask],
            label=style["label"],
            color=style["color"],
            linestyle=style["linestyle"],
            linewidth=2.8,
            marker=style["marker"],
            markersize=4.0,
            markevery=max(1, len(group) // 8),
            alpha=0.95,
        )
        plotted += 1
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, color="#d6dde3", linewidth=0.8)
    ax.set_facecolor("#fbfdff")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if plotted:
        ax.legend(frameon=False, ncols=min(plotted, 3), loc="best")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_hysteresis(df: pd.DataFrame, out: Path) -> None:
    """绘制滞回曲线（加载-卸载围成面积）"""
    fig, ax = plt.subplots(figsize=(9.5, 5.6), dpi=160)
    plotted = 0
    for label, group in df.groupby("run_dir"):
        group = group.sort_values("frame")
        disp = pd.to_numeric(group["squeeze_disp_m"], errors="coerce").values
        force = pd.to_numeric(group["plate_force_n"], errors="coerce").values
        mask = ~np.isnan(disp) & ~np.isnan(force)
        if not mask.any():
            continue
        style = style_for_group(group, label)
        ax.plot(
            disp[mask],
            force[mask],
            label=style["label"],
            color=style["color"],
            linestyle=style["linestyle"],
            linewidth=2.0,
            alpha=0.85,
        )
        plotted += 1
    ax.set_xlabel("displacement (m)")
    ax.set_ylabel("plate force (N)")
    ax.set_title("Hysteresis Loop (Force-Displacement)")
    ax.grid(True, color="#d6dde3", linewidth=0.8)
    ax.set_facecolor("#fbfdff")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if plotted:
        ax.legend(frameon=False, ncols=min(plotted, 3), loc="best")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def plot_energy(df: pd.DataFrame, out: Path) -> None:
    """绘制能量曲线"""
    fig, ax = plt.subplots(figsize=(9.5, 5.6), dpi=160)
    plotted = 0
    for label, group in df.groupby("run_dir"):
        group = group.sort_values("frame")
        t = pd.to_numeric(group["t"], errors="coerce").values
        kinetic = pd.to_numeric(group["kinetic_energy"], errors="coerce").values
        elastic = pd.to_numeric(group["elastic_energy"], errors="coerce").values
        total = kinetic + elastic
        style = style_for_group(group, label)
        ax.plot(t, total, label=style["label"], color=style["color"], linestyle=style["linestyle"], linewidth=2.0, alpha=0.85)
        plotted += 1
    ax.set_xlabel("time (s)")
    ax.set_ylabel("total energy (J)")
    ax.set_title("Total Energy (Kinetic + Elastic)")
    ax.grid(True, color="#d6dde3", linewidth=0.8)
    ax.set_facecolor("#fbfdff")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if plotted:
        ax.legend(frameon=False, ncols=min(plotted, 3), loc="best")
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def compute_equivalent_stiffness(displacement: np.ndarray, force: np.ndarray) -> float:
    """等效刚度 k_eq: F-d 曲线前 20% 段线性拟合斜率"""
    if len(displacement) < 5 or len(force) < 5:
        return np.nan
    n = max(2, int(len(displacement) * 0.2))
    d = displacement[:n]
    f = force[:n]
    if d[-1] - d[0] < 1e-12:
        return np.nan
    coeffs = np.polyfit(d, f, 1)
    return float(coeffs[0])


def compute_hysteresis_area(displacement: np.ndarray, force: np.ndarray, compress_time: float, release_time: float, fps: int) -> float:
    """滞回面积 A_hys: 加载-卸载围成面积"""
    compress_end = int(compress_time * fps)
    hold_time = 0.5
    release_start = int((compress_time + hold_time) * fps)
    release_end = min(len(displacement), int((compress_time + hold_time + release_time) * fps))
    
    if compress_end < 2 or release_end - release_start < 2:
        return np.nan
    
    d_load = displacement[:compress_end]
    f_load = force[:compress_end]
    d_unload = displacement[release_start:release_end]
    f_unload = force[release_start:release_end]
    
    area_load = np.trapezoid(f_load, d_load)
    area_unload = np.trapezoid(f_unload, d_unload)
    return float(abs(area_load - area_unload))


def compute_recovery_time(width: np.ndarray, time: np.ndarray, release_start_s: float, fps: int) -> float:
    """恢复时间 T_95: 释放后挤压方向宽度回到 95% 初始宽度的时间"""
    release_start_idx = int(release_start_s * fps)
    if release_start_idx >= len(width):
        return np.nan
    
    initial_width = width[0]
    target_width = initial_width * 0.95
    
    release_width = width[release_start_idx:]
    release_t = time[release_start_idx:]
    
    for i, w in enumerate(release_width):
        if w >= target_width:
            return float(release_t[i] - release_start_s)
    return np.nan


def compute_energy_drift(kinetic: np.ndarray, elastic: np.ndarray) -> float:
    """能量漂移 ΔE: |(E_kin + E_elastic)_final - initial|"""
    if len(kinetic) < 2 or len(elastic) < 2:
        return np.nan
    initial_energy = kinetic[0] + elastic[0]
    final_energy = kinetic[-1] + elastic[-1]
    return float(abs(final_energy - initial_energy))


def compute_contact_force_jitter(force: np.ndarray, hold_start: float, hold_end: float, fps: int) -> float:
    """接触力抖动 σ_F: 保持阶段 plate_force_n 标准差"""
    start_idx = int(hold_start * fps)
    end_idx = int(hold_end * fps)
    if start_idx >= len(force) or end_idx > len(force):
        return np.nan
    hold_force = force[start_idx:end_idx]
    if len(hold_force) < 2:
        return np.nan
    return float(np.std(hold_force))


def compute_volume_ratio_stats(volume_ratio: np.ndarray) -> tuple[float, float]:
    """体积保持率统计: 均值和方差"""
    valid = volume_ratio[~np.isnan(volume_ratio)]
    if len(valid) < 2:
        return np.nan, np.nan
    return float(np.mean(valid)), float(np.var(valid))


def compute_advanced_metrics(group: pd.DataFrame) -> dict:
    """计算单个实验组的高级指标"""
    displacement = pd.to_numeric(group["squeeze_disp_m"], errors="coerce").values
    force = pd.to_numeric(group["plate_force_n"], errors="coerce").values
    width = pd.to_numeric(group["width_m"], errors="coerce").values
    time_vals = pd.to_numeric(group["t"], errors="coerce").values
    kinetic = pd.to_numeric(group["kinetic_energy"], errors="coerce").values
    elastic = pd.to_numeric(group["elastic_energy"], errors="coerce").values
    volume_ratio = pd.to_numeric(group["volume_ratio"], errors="coerce").values
    
    fps = 60
    compress_time = 1.0
    hold_time = 0.5
    release_time = 1.0
    
    k_eq = compute_equivalent_stiffness(displacement, force)
    a_hys = compute_hysteresis_area(displacement, force, compress_time, release_time, fps)
    t_95 = compute_recovery_time(width, time_vals, compress_time + hold_time, fps)
    delta_e = compute_energy_drift(kinetic, elastic)
    sigma_f = compute_contact_force_jitter(force, compress_time, compress_time + hold_time, fps)
    vol_mean, vol_var = compute_volume_ratio_stats(volume_ratio)
    
    return {
        "k_eq": k_eq,
        "a_hys": a_hys,
        "t_95": t_95,
        "delta_e": delta_e,
        "sigma_f": sigma_f,
        "volume_mean": vol_mean,
        "volume_var": vol_var,
    }


def write_stability_table(df: pd.DataFrame, out: Path) -> None:
    rows = []
    for label, group in df.groupby("run_dir"):
        final = group.iloc[-1]
        advanced = compute_advanced_metrics(group)
        min_det_f = ""
        max_inverted = ""
        if "min_det_f" in group:
            min_det_f = pd.to_numeric(group["min_det_f"], errors="coerce").min()
        if "inverted_tet_count" in group:
            max_inverted = pd.to_numeric(group["inverted_tet_count"], errors="coerce").max()
        rows.append(
            {
                "run": label,
                "frames": len(group),
                "max_force_n": group["plate_force_n"].max(),
                "max_penetration_m": group["max_penetration_m"].max(),
                "max_wall_ms": group["wall_ms"].max(),
                "final_residual_strain": final["residual_strain"],
                "min_volume_ratio": group["volume_ratio"].min(),
                "max_volume_ratio": group["volume_ratio"].max(),
                "k_eq": advanced["k_eq"],
                "a_hys": advanced["a_hys"],
                "t_95": advanced["t_95"],
                "delta_e": advanced["delta_e"],
                "sigma_f": advanced["sigma_f"],
                "volume_mean": advanced["volume_mean"],
                "volume_var": advanced["volume_var"],
                "min_det_f": min_det_f,
                "max_inverted_tets": max_inverted,
            }
        )
    table = pd.DataFrame(rows)
    columns = list(table.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in table.iterrows():
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, float):
                values.append(f"{value:.6g}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_analysis(outputs: Path, output_dir: Path | None = None, contains: str | None = None) -> Path:
    metric_files = find_metric_files(outputs, contains)
    df = load_metrics(metric_files)
    out_dir = output_dir or outputs / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    initial_width = df.groupby("run_dir")["width_m"].transform("first").replace(0, np.nan)
    df["normalized_compression"] = df["squeeze_disp_m"] / initial_width

    plot_lines(
        df,
        "normalized_compression",
        "plate_force_n",
        out_dir / "force_displacement.png",
        "normalized compression",
        "plate force (N)",
    )
    plot_lines(df, "t", "height_m", out_dir / "height_time.png", "time (s)", "height (m)")
    plot_lines(df, "t", "volume_ratio", out_dir / "volume_ratio_time.png", "time (s)", "volume ratio")
    plot_lines(df, "t", "residual_strain", out_dir / "recovery_error_time.png", "time (s)", "residual strain")
    plot_lines(df, "t", "wall_ms", out_dir / "performance_ms_step.png", "time (s)", "wall time per frame (ms)")
    plot_hysteresis(df, out_dir / "hysteresis.png")
    plot_energy(df, out_dir / "energy_time.png")
    write_stability_table(df, out_dir / "stability_table.md")
    df.to_csv(out_dir / "combined_metrics.csv", index=False)

    print(f"Analyzed {len(metric_files)} run(s). Wrote {out_dir}")
    return out_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate plots from MPM squeeze metrics.")
    parser.add_argument("--outputs", type=Path, default=Path("outputs"), help="Root outputs directory.")
    parser.add_argument("--out", type=Path, default=None, help="Optional analysis output directory.")
    parser.add_argument("--contains", type=str, default=None, help="Only include run directories containing this text.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_analysis(args.outputs, args.out, args.contains)


if __name__ == "__main__":
    main()
