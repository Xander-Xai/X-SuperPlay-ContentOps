"""Check one short motion sample: 4-8 s, silent, 1080x1920, H.264/yuv420p, CFR 30.

The CLI only runs ffprobe and hands the facts to
``contentops.media.motion_sample``. It has no approval, publish or force flag.
An unavailable ffprobe is a BLOCKED result, never a pass.

Usage:
    python scripts/check_motion_sample.py <sample.mp4> [--sha256 <hex>] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.motion_sample import check_motion_sample  # noqa: E402
from process_utils import hidden_run  # noqa: E402


def _probe(path: Path) -> Dict[str, Any]:
    try:
        meta = hidden_run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            timeout=30,
        )
    except FileNotFoundError:
        return {"error": "FFPROBE_UNAVAILABLE", "detail": "ffprobe is not on PATH"}
    if meta.returncode != 0:
        return {"error": "FFPROBE_FAILED", "detail": (meta.stderr or "").strip()[:300]}
    try:
        payload = json.loads(meta.stdout or "{}")
    except ValueError as exc:
        return {"error": "FFPROBE_PARSE", "detail": str(exc)}

    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        return {"error": "SAMPLE_NO_VIDEO", "detail": "ffprobe found no video stream"}
    try:
        duration = float((payload.get("format") or {}).get("duration") or video.get("duration"))
    except (TypeError, ValueError):
        duration = None

    frames = hidden_run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(path)],
        timeout=60,
    )
    timestamps = []
    if frames.returncode == 0:
        for line in (frames.stdout or "").splitlines():
            text = line.strip().rstrip(",")
            if not text:
                continue
            try:
                timestamps.append(float(text))
            except ValueError:
                continue

    frame_rate = video.get("avg_frame_rate") or ""
    return {
        "duration_s": duration,
        "width": video.get("width"),
        "height": video.get("height"),
        "codec_name": video.get("codec_name"),
        "pix_fmt": video.get("pix_fmt"),
        "avg_frame_rate": frame_rate,
        "r_frame_rate": video.get("r_frame_rate"),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "frame_timestamps": timestamps,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Technical check for a short motion sample.")
    parser.add_argument("sample")
    parser.add_argument("--sha256", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.sample)
    result = check_motion_sample(path, probe=_probe(path), expected_sha256=args.sha256 or None)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("state") == "TECHNICALLY_CHECKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
