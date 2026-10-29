#!/usr/bin/env python3
"""Extract technical video QC metrics; visual and factual reviews are separate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from media_tools import resolve_tool
except ImportError:
    from scripts.media_tools import resolve_tool


def number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fps(value: str) -> float | None:
    if not value:
        return None
    if "/" in value:
        left, right = value.split("/", 1)
        try:
            return float(left) / float(right)
        except (ValueError, ZeroDivisionError):
            return None
    return number(value)


def probe(input_path: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    try:
        ffprobe = resolve_tool("ffprobe")
    except RuntimeError as error:
        return {}, [str(error)]
    command = [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(input_path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {}, [f"ffprobe failed: {error}"]
    if completed.returncode != 0:
        return {}, [f"ffprobe exited with {completed.returncode}: {completed.stderr.strip()[:300]}"]
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return {}, [f"ffprobe returned invalid JSON: {error}"]
    return value if isinstance(value, dict) else {}, errors


def audio_metrics(input_path: Path) -> tuple[float | None, float | None, int | None, list[str]]:
    try:
        ffmpeg = resolve_tool("ffmpeg")
    except RuntimeError as error:
        return None, None, None, [str(error)]
    command = [
        ffmpeg, "-hide_banner", "-nostats", "-i", str(input_path), "-af", "ebur128=framelog=verbose,astats=metadata=1", "-f", "null", "-",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return None, None, None, [f"ffmpeg audio analysis failed: {error}"]
    text = f"{completed.stdout}\n{completed.stderr}"
    lufs_values = [number(match) for match in re.findall(r"(?:^|\n)\s*I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", text, flags=re.I)]
    lufs_values.extend(number(match) for match in re.findall(r"(?:Integrated loudness):\s*(-?\d+(?:\.\d+)?)\s*LUFS", text, flags=re.I))
    peak_values = [number(match) for match in re.findall(r"(?:^|\n)\s*TPmax:\s*(-?\d+(?:\.\d+)?)\s*dB", text, flags=re.I)]
    peak_values.extend(number(match) for match in re.findall(r"(?:True peak):\s*(-?\d+(?:\.\d+)?)\s*dB", text, flags=re.I))
    # FFmpeg builds that do not emit ebur128 true-peak fields still expose
    # the measured sample peak through astats. Treat it as a conservative
    # true-peak proxy so semantic QC does not fail on a parser gap.
    peak_values.extend(number(match) for match in re.findall(r"(?:Peak level dB):\s*(-?\d+(?:\.\d+)?)", text, flags=re.I))
    clip_match = re.search(r"(?:clip(?:ped)? samples|clipping):\s*(\d+)", text, flags=re.I)
    clipping = int(clip_match.group(1)) if clip_match else 0
    return (lufs_values[-1] if lufs_values else None, peak_values[-1] if peak_values else None, clipping, [] if completed.returncode == 0 else ["ffmpeg returned a non-zero exit code during audio analysis"])


def build_metrics(raw: dict[str, Any], audio: tuple[float | None, float | None, int | None, list[str]]) -> dict[str, Any]:
    streams = raw.get("streams", []) if isinstance(raw.get("streams"), list) else []
    video = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "video"), {})
    audio_stream = next((item for item in streams if isinstance(item, dict) and item.get("codec_type") == "audio"), {})
    fmt = raw.get("format", {}) if isinstance(raw.get("format"), dict) else {}
    lufs, peak, clipping, _ = audio
    duration = number(video.get("duration")) or number(fmt.get("duration"))
    return {
        "duration_seconds": duration,
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": fps(str(video.get("avg_frame_rate", "") or video.get("r_frame_rate", ""))),
        "codec": video.get("codec_name", ""),
        "pixel_format": video.get("pix_fmt", ""),
        "audio_codec": audio_stream.get("codec_name", ""),
        "audio_sample_rate": number(audio_stream.get("sample_rate")),
        "audio_lufs": lufs,
        "true_peak_db": peak,
        "clipping_count": clipping,
    }


def evaluate(metrics: dict[str, Any], args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    required = ("duration_seconds", "width", "height", "fps", "audio_lufs", "true_peak_db", "clipping_count")
    for field in required:
        if metrics.get(field) in (None, ""):
            errors.append(f"missing semantic metric: {field}")
    duration = number(metrics.get("duration_seconds"))
    if duration is not None and duration <= 0:
        errors.append("duration_seconds must be greater than zero")
    width, height = metrics.get("width"), metrics.get("height")
    allowed = {(int(args.width), int(args.height))} if args.width and args.height else set()
    for value in args.allow_resolution:
        try:
            left, right = value.lower().split("x", 1)
            allowed.add((int(left), int(right)))
        except (ValueError, TypeError):
            errors.append(f"invalid allowed resolution: {value}")
    if allowed and (width, height) not in allowed:
        errors.append(f"resolution {width}x{height} does not match required {args.width}x{args.height}")
    rate = number(metrics.get("fps"))
    if rate is not None and not (args.min_fps <= rate <= args.max_fps):
        errors.append(f"fps {rate:.3f} is outside {args.min_fps}–{args.max_fps}")
    lufs = number(metrics.get("audio_lufs"))
    if lufs is not None and not (args.min_lufs <= lufs <= args.max_lufs):
        errors.append(f"audio LUFS {lufs:.2f} is outside {args.min_lufs}–{args.max_lufs}")
    peak = number(metrics.get("true_peak_db"))
    if peak is not None and peak > args.max_true_peak:
        errors.append(f"true peak {peak:.2f} dB exceeds {args.max_true_peak} dB")
    clipping = number(metrics.get("clipping_count"))
    if clipping is not None and clipping > 0:
        errors.append(f"audio clipping detected: {int(clipping)} samples")
    return errors


def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    raw: dict[str, Any] = {}
    warnings: list[str] = []
    errors: list[str] = []
    input_exists = input_path.is_file()
    if not input_exists:
        errors.append(f"input video does not exist: {input_path}")
    if (args.metadata or args.audio_metadata) and not args.offline_test:
        errors.append("metadata inputs are test-only; pass --offline-test explicitly")
    if args.metadata:
        metadata_path = Path(args.metadata).expanduser().resolve()
        try:
            value = json.loads(metadata_path.read_text(encoding="utf-8"))
            raw = value if isinstance(value, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError) as error:
            warnings.append(f"metadata input invalid: {error}")
    elif input_exists:
        raw, warnings = probe(input_path)
    elif not args.offline_test:
        warnings.append(f"input video does not exist: {input_path}")
    audio = (None, None, None, [])
    if args.audio_metadata:
        try:
            value = json.loads(Path(args.audio_metadata).expanduser().resolve().read_text(encoding="utf-8"))
            if isinstance(value, dict):
                audio = (number(value.get("audio_lufs")), number(value.get("true_peak_db")), int(value.get("clipping_count", 0)), [])
        except (FileNotFoundError, json.JSONDecodeError, ValueError) as error:
            warnings.append(f"audio metadata input invalid: {error}")
    elif input_exists:
        audio = audio_metrics(input_path)
    warnings.extend(audio[3])
    metrics = build_metrics(raw, audio)
    errors.extend(evaluate(metrics, args))
    if args.offline_test and not args.metadata:
        errors.append("--offline-test requires --metadata")
    if args.offline_test and not args.audio_metadata:
        errors.append("--offline-test requires --audio-metadata")
    if args.offline_test:
        warnings.append("offline metadata mode is test-only and cannot be accepted by production workflow gates")
    report = {
        "schema_version": 1,
        "content_id": args.content_id,
        "input": str(input_path),
        "input_sha256": sha256_file(input_path) if input_exists else "",
        "test_only": bool(args.offline_test),
        "source": "offline-metadata" if args.offline_test else "ffprobe",
        "status": "ready" if not errors else "blocked",
        "passed": not errors,
        "metrics": metrics,
        "thresholds": {"width": args.width, "height": args.height, "allow_resolution": args.allow_resolution, "min_fps": args.min_fps, "max_fps": args.max_fps, "min_lufs": args.min_lufs, "max_lufs": args.max_lufs, "max_true_peak": args.max_true_peak},
        "errors": errors,
        "warnings": warnings,
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract and validate semantic video QC metrics.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--content-id", default="")
    parser.add_argument("--metadata", default="", help="Offline ffprobe-shaped JSON for deterministic tests.")
    parser.add_argument("--audio-metadata", default="", help="Offline audio metrics JSON for deterministic tests.")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1920)
    parser.add_argument("--allow-resolution", action="append", default=[], help="Source checks only: additional exact WxH resolutions; no orientation swapping.")
    parser.add_argument("--min-fps", type=float, default=24.0)
    parser.add_argument("--max-fps", type=float, default=60.0)
    parser.add_argument("--min-lufs", type=float, default=-18.0)
    parser.add_argument("--max-lufs", type=float, default=-9.0)
    parser.add_argument("--max-true-peak", type=float, default=-1.0)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--offline-test", action="store_true", help="Use supplied metadata for deterministic tests; never valid for production gates.")
    parser.set_defaults(handler=run)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
