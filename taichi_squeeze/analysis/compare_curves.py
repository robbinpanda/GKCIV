from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


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


def plot_lines(df: pd.DataFrame, x: str, y: str, out: Path, xlabel: str, ylabel: str) -> None:
    fig, ax = plt.subplots(figsize=(8, 5), dpi=140)
    for label, group in df.groupby("run_dir"):
        ax.plot(group[x], group[y], label=label, linewidth=1.8)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, color="#dfe6e9", linewidth=0.7)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def write_stability_table(df: pd.DataFrame, out: Path) -> None:
    rows = []
    for label, group in df.groupby("run_dir"):
        final = group.iloc[-1]
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

    df["normalized_compression"] = df["squeeze_disp_m"] / df.groupby("run_dir")["width_m"].transform("max")

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
