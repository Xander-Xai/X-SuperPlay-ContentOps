#!/usr/bin/env python3
"""Visual QC: sample frames and generate contact sheet.

Extracts frames at fixed intervals from a video, arranges them into
a contact sheet image for quick visual review. Also checks for
black frames and blank frames.

Output:
  projects/<slug>/receipts/visual-qc.json
  projects/<slug>/receipts/visual-contact-sheet.png (gitignored)

Usage:
  python scripts/qc_visual.py projects/easel-review
  python scripts/qc_visual.py projects/easel-review --video easel.mp4
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_FRACTIONS = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
THUMB_W = 320
THUMB_H = 569  # 9:16


def ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-print_format", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def extract_frame(video: Path, timestamp: float, out_png: Path) -> bool:
    r = subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{timestamp:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={THUMB_W}:{THUMB_H}",
         str(out_png)],
        capture_output=True, text=True, timeout=60,
    )
    return r.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0


def check_black_frame(png_path: Path) -> dict:
    """Check if a frame is mostly black (all pixels very dark)."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(png_path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, timeout=30,
    )
    data = r.stdout
    if not data:
        return {"is_black": None, "reason": "could not read pixels"}
    dark = sum(1 for b in data if b < 16)
    ratio = dark / len(data)
    return {"is_black": ratio > 0.95, "dark_ratio": round(ratio, 4)}


def build_contact_sheet(frames: list[Path], out_png: Path) -> bool:
    """Arrange frames into a grid contact sheet using ffmpeg."""
    if not frames:
        return False
    cols = min(5, len(frames))
    rows = (len(frames) + cols - 1) // cols
    sheet_w = THUMB_W * cols
    sheet_h = THUMB_H * rows

    # Build using ffmpeg xstack filter
    inputs = []
    for f in frames:
        inputs.extend(["-i", str(f)])
    n = len(frames)
    labels = []
    layout_parts = []
    for i in range(n):
        col = i % cols
        row = i // cols
        x = col * THUMB_W
        y = row * THUMB_H
        labels.append(f"[{i}:v]scale={THUMB_W}:{THUMB_H}[v{i}]")
        layout_parts.append(f"v{i}={x}_{y}")
    filter_chain = ";".join(labels) + f";xstack=inputs={'|'.join(f'v{i}' for i in range(n))}:layout={':'.join(layout_parts)}[v]"
    r = subprocess.run(
        ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_chain, "-map", "[v]",
         str(out_png)],
        capture_output=True, text=True, timeout=120,
    )
    return r.returncode == 0 and out_png.exists()


def qc_visual(project: Path, target: str = "") -> dict:
    project = project.resolve()
    if target:
        video = project / "final" / target
    else:
        easel = project / "final" / "easel.mp4"
        video = easel if easel.exists() else project / "final" / "final.mp4"

    receipts = project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)

    result = {
        "project": str(project),
        "video": str(video),
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frames": [],
    }

    if not video.exists():
        result["status"] = "FAIL"
        result["reason"] = f"video not found: {video}"
        print(json.dumps(result, indent=2))
        return result

    duration = ffprobe_duration(video)
    result["duration_sec"] = round(duration, 2)

    if duration < 1:
        result["status"] = "FAIL"
        result["reason"] = "video too short to sample"
        print(json.dumps(result, indent=2))
        return result

    frames_data = []
    extracted = []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for i, frac in enumerate(SAMPLE_FRACTIONS):
            ts = duration * frac
            frame_png = td_path / f"frame_{i:02d}.png"
            ok = extract_frame(video, ts, frame_png)
            if ok:
                extracted.append(frame_png)
                black = check_black_frame(frame_png)
                frames_data.append({
                    "index": i,
                    "timestamp_sec": round(ts, 2),
                    "fraction": frac,
                    "black_frame": black.get("is_black"),
                    "dark_ratio": black.get("dark_ratio"),
                })
            else:
                frames_data.append({
                    "index": i,
                    "timestamp_sec": round(ts, 2),
                    "fraction": frac,
                    "error": "extraction failed",
                })

        result["frames"] = frames_data

        # Build contact sheet
        sheet_path = receipts / "visual-contact-sheet.png"
        if extracted:
            sheet_ok = build_contact_sheet(extracted, sheet_path)
            result["contact_sheet"] = str(sheet_path) if sheet_ok else None

    # Summary
    black_count = sum(1 for f in frames_data if f.get("black_frame") is True)
    extract_fail = sum(1 for f in frames_data if "error" in f)
    result["summary"] = {
        "total_samples": len(SAMPLE_FRACTIONS),
        "extracted": len(SAMPLE_FRACTIONS) - extract_fail,
        "black_frames": black_count,
        "extraction_failures": extract_fail,
    }

    if black_count > 2 or extract_fail > 3:
        result["status"] = "WARN"
    else:
        result["status"] = "PASS"

    # Write JSON receipt
    out_json = receipts / "visual-qc.json"
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return result


def main():
    p = argparse.ArgumentParser(description="Visual QC: frame sampling and contact sheet")
    p.add_argument("project", help="project dir, e.g. projects/easel-review")
    p.add_argument("--video", default="", help="which render: easel.mp4 | fallback.mp4 | <file>")
    args = p.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()
    result = qc_visual(project, target=args.video)
    return 0 if result.get("status") in ("PASS", "WARN") else 1


if __name__ == "__main__":
    sys.exit(main())
