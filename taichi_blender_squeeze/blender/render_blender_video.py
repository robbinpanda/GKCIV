from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


DEFAULT_CONFIG = Path("taichi_blender_squeeze/configs/blender_config.example.json")
DEFAULT_BLEND = Path("taichi_blender_squeeze/outputs/blender/scene/squishy_mpm_cube.blend")
DEFAULT_FRAME_DIR = Path("taichi_blender_squeeze/outputs/blender/final_frames")
DEFAULT_VIDEO = Path("taichi_blender_squeeze/outputs/blender/squishy_mpm_cube.mp4")


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_blender_exe(config: dict, override: str | None) -> str:
    candidate = override or config.get("blender_exe") or "blender"
    if Path(candidate).exists():
        return candidate
    found = shutil.which(candidate)
    if found:
        return found
    raise FileNotFoundError(
        f"Blender executable not found: {candidate}. Install Blender or pass --blender-exe with blender.exe."
    )


def render_frames(blender_exe: str, blend: Path, frame_dir: Path, file_format: str) -> None:
    frame_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = str(frame_dir / "frame_####")
    cmd = [
        blender_exe,
        "-b",
        str(blend),
        "-o",
        output_pattern,
        "-F",
        file_format,
        "-a",
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def encode_video(frame_dir: Path, output: Path, fps: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found; frames were rendered but MP4 encoding was skipped.")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        str(frame_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        str(output),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the saved squishy Blender scene to frames and MP4.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--blender-exe", type=str, default=None)
    parser.add_argument("--blend", type=Path, default=DEFAULT_BLEND)
    parser.add_argument("--frame-dir", type=Path, default=DEFAULT_FRAME_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_VIDEO)
    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--format", type=str, default="PNG")
    parser.add_argument("--skip-video", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    blender_exe = resolve_blender_exe(config, args.blender_exe)
    fps = int(args.fps or config.get("fps", 30))

    render_frames(blender_exe, args.blend, args.frame_dir, args.format)
    if not args.skip_video:
        encode_video(args.frame_dir, args.output, fps)


if __name__ == "__main__":
    main()
