from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

CONFIGS_DIR = Path("taichi_squeeze/configs")

SOLVER_MODULES = {
    "mpm3d": "taichi_squeeze.src.simulate_mpm3d",
    "fem3d": "taichi_squeeze.src.simulate_fem3d",
    "pbd3d": "taichi_squeeze.src.simulate_pbd3d",
}


def run_one(config_path: Path, frames: int | None = None, no_render: bool = False) -> tuple[str, bool, float, str]:
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    solver = config.get("solver", "")
    module = SOLVER_MODULES.get(solver)
    if not module:
        return config_path.name, False, 0.0, f"Unknown solver: {solver}"

    cmd = [sys.executable, "-m", module, "--config", str(config_path)]
    if frames is not None:
        cmd.extend(["--frames", str(frames)])
    if no_render:
        cmd.append("--no-render")

    start = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        elapsed = time.perf_counter() - start
        if result.returncode == 0:
            return config_path.name, True, elapsed, result.stdout.strip()
        else:
            return config_path.name, False, elapsed, result.stderr[-500:]
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return config_path.name, False, elapsed, "Timeout after 3600s"
    except Exception as e:
        elapsed = time.perf_counter() - start
        return config_path.name, False, elapsed, str(e)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run all experiments from configs.")
    parser.add_argument("--frames", type=int, default=None, help="Override frame count for quick testing.")
    parser.add_argument("--no-render", action="store_true", help="Skip rendering.")
    parser.add_argument("--filter", type=str, default=None, help="Only run configs containing this string.")
    args = parser.parse_args()

    configs = sorted(CONFIGS_DIR.glob("*.json"))
    configs = [c for c in configs if c.name != "camera.json" and c.name != "color_scheme.json"]

    if args.filter:
        configs = [c for c in configs if args.filter in c.name]

    total = len(configs)
    print(f"Found {total} configs to run")
    print(f"{'='*60}")

    results = []
    total_start = time.perf_counter()
    success_count = 0
    fail_count = 0

    for i, config_path in enumerate(configs, 1):
        name = config_path.name
        solver = name.split("_")[0]

        elapsed_str = ""
        if results:
            avg_time = sum(r[2] for r in results) / len(results)
            remaining = avg_time * (total - i + 1)
            elapsed_str = f" | ETA: {remaining/60:.0f}min"

        bar_len = 30
        filled = int(bar_len * i / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        percent = i / total * 100

        print(f"\n[{bar}] {percent:5.1f}% ({i}/{total}){elapsed_str}")
        print(f"  Running: {name} ({solver})")

        name, success, elapsed, msg = run_one(config_path, args.frames, args.no_render)
        results.append((name, success, elapsed, msg))

        if success:
            success_count += 1
            print(f"  ✓ SUCCESS ({elapsed:.1f}s)")
        else:
            fail_count += 1
            print(f"  ✗ FAILED ({elapsed:.1f}s)")

    total_elapsed = time.perf_counter() - total_start

    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")

    for name, success, elapsed, _ in results:
        status = "✓" if success else "✗"
        print(f"  {status} {name} ({elapsed:.1f}s)")

    print(f"\nTotal: {len(results)} configs, {success_count} success, {fail_count} failed")
    print(f"Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)")

    summary_path = Path("outputs/run_summary.txt")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", encoding="utf-8") as f:
        f.write(f"Run Summary\n")
        f.write(f"Total: {len(results)} configs, {success_count} success, {fail_count} failed\n")
        f.write(f"Total time: {total_elapsed:.1f}s ({total_elapsed/60:.1f} min)\n\n")
        for name, success, elapsed, msg in results:
            status = "OK" if success else "FAIL"
            f.write(f"[{status}] {name} ({elapsed:.1f}s)\n")
            if not success:
                f.write(f"  Error: {msg}\n")
    print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    main()
