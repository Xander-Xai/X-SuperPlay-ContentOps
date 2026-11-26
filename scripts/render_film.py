#!/usr/bin/env python3
"""Stitch sampled Huashu film stills into a playable animatic MP4.

Why this exists
---------------
ContentOps fed Huashu one hand-built HTML template and took only its mp4, so
every shot came back a black text card -- it bypassed Huashu's own director and
quality toolchain. The slow render paths are not reliable on this machine:
``om render`` drives Chrome CDP and its screenshot call fails, and driving
Playwright frame-by-frame runs at ~2s/frame for 1080x1920. The path that works
and stays honest is: ``om still`` samples the film's real timeline into
``index-<t>s.png`` (deterministic, uses Huashu's own layout), then this script
lays those frames on their true durations with FFmpeg. The result is an
*animatic preview*, not a frame-accurate final render, and it says so.

Usage
-----
    om still <film-dir> --at 0,2,5,8,11
    python scripts/render_film.py --film <film-dir> --out out.mp4 [--fps 24]

Exit codes
----------
0  an animatic was written
2  no stills found, or ffmpeg failed (nothing written)
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_utils import hidden_run  # noqa: E402

WIDTH, HEIGHT = 1080, 1920


def _collect(film: Path) -> list[tuple[float, Path]]:
    frames = []
    for path in glob.glob(str(film / "index-*s.png")):
        m = re.search(r"index-([0-9.]+)s\.png", os.path.basename(path))
        if m:
            frames.append((float(m.group(1)), Path(path)))
    frames.sort(key=lambda item: item[0])
    return frames


def _build(frames: list[tuple[float, Path]], out: Path, fps: int) -> None:
    if len(frames) < 2:
        raise SystemExit("need at least two stills; run `om still <film> --at ...` first")
    times = [t for t, _ in frames]
    lines: list[str] = []
    for i, (t, path) in enumerate(frames):
        dur = (times[i + 1] - t) if i + 1 < len(times) else 0.5
        lines.append(f"file '{path.as_posix()}'")
        lines.append(f"duration {dur:.2f}")
    lines.append(f"file '{frames[-1][1].as_posix()}'")
    lst = out.with_suffix(".concat.txt")
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
        "-vf", f"scale={WIDTH}:{HEIGHT}:flags=lanczos,fps={fps},format=yuv420p",
        "-c:v", "libx264", "-crf", "20", "-movflags", "+faststart", str(out),
    ]
    proc = hidden_run(cmd, capture_output=True, text=True, errors="replace", timeout=300)
    lst.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise SystemExit("ffmpeg failed:/n" + (proc.stderr or "")[-600:])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stills -> animatic MP4")
    parser.add_argument("--film", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args(argv)

    film = args.film.resolve()
    if not (film / "index.html").exists():
        raise SystemExit(f"not a film dir (no index.html): {film}")
    frames = _collect(film)
    if not frames:
        raise SystemExit(
            f"no index-<t>s.png stills in {film}; sample them first:/n"
            f"  om still {film} --at 0,2,5,8,11")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _build(frames, args.out, args.fps)
    print(f"ANIMATIC: {args.out} ({args.out.stat().st_size} bytes, "
          f"{len(frames)} frames, {args.fps}fps)")
    print("note: animatic from sampled stills, not a frame-accurate final render",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
