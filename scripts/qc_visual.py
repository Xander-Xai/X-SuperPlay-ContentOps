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
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from process_utils import hidden_run

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_FRACTIONS = [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65, 0.75, 0.85, 0.95]
THUMB_W = 320
THUMB_H = 569  # 9:16

# TECHNICAL_PASS means only "the media decodes and its A/V parameters are sane".
# Editorial checks (real_evidence_present, real_source_ratio, duration_range,
# voice_quality_declared ...) live in canonical QC's ``overall`` but must never
# downgrade or upgrade this technical verdict.
TECHNICAL_CHECK_IDS = (
    "file_size",
    "ffprobe_parse",
    "resolution",
    "aspect_ratio_9_16",
    "video_codec_h264",
    "audio_present",
    "audio_codec_aac",
    "voice_not_silence",
)


def file_sha256(path: Path) -> str | None:
    """Bind the QC receipt to the exact bytes it graded."""
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def technical_state(canonical_qc: dict) -> str:
    """Derive the technical layer from media checks, not from QC ``overall``.

    A content-evidence WARN (e.g. ``real_evidence_present``) leaves ``overall``
    at WARN even when every decodability check passed. Reporting that file as
    TECHNICAL_PENDING would be wrong; reporting it as editorial approval would
    be dishonest. Missing checks stay PENDING, never a silent pass.
    """
    rows = canonical_qc.get("checks") or []
    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    if not by_id:
        return "TECHNICAL_PENDING"
    failed = [cid for cid in TECHNICAL_CHECK_IDS
              if cid in by_id and by_id[cid].get("ok") is not True]
    missing = [cid for cid in TECHNICAL_CHECK_IDS if cid not in by_id]
    if failed:
        return "TECHNICAL_FAIL"
    if missing:
        return "TECHNICAL_PENDING"
    return "TECHNICAL_PASS"


def human_review_states(project: Path) -> tuple[str, str]:
    """CONTENT/PUBLICATION layers come only from a real, complete human review.

    An absent, unsigned, unscored or non-approving human-review.json can never
    become PUBLISH_APPROVED, no matter how many technical/visual checks passed.
    """
    path = project / "receipts" / "human-review.json"
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "CONTENT_REVIEW_PENDING", "PENDING_HUMAN_APPROVAL"
    approved = (
        isinstance(review, dict)
        and review.get("decision") == "APPROVED"
        and review.get("production_ready") is True
        and bool(review.get("reviewer"))
        and bool(review.get("reviewed_at"))
        and review.get("scores") is not None
    )
    if not approved:
        return "CONTENT_REVIEW_PENDING", "PENDING_HUMAN_APPROVAL"
    return "CONTENT_REVIEWED", "PUBLISH_APPROVED"


def ffprobe_duration(path: Path) -> float:
    r = hidden_run(
        ["ffprobe", "-v", "error", "-show_format", "-print_format", "json", str(path)],
        timeout=30,
    )
    try:
        return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def extract_frame(video: Path, timestamp: float, out_png: Path) -> bool:
    r = hidden_run(
        ["ffmpeg", "-y", "-ss", f"{timestamp:.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={THUMB_W}:{THUMB_H}",
         str(out_png)],
        timeout=60,
    )
    return r.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0


def check_black_frame(png_path: Path) -> dict:
    """Check if a frame is mostly black (all pixels very dark)."""
    r = hidden_run(
        ["ffmpeg", "-i", str(png_path), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        timeout=30, text=False,
    )
    data = r.stdout
    if not data:
        return {"is_black": None, "reason": "could not read pixels"}
    dark = sum(1 for b in data if b < 16)
    ratio = dark / len(data)
    return {"is_black": ratio > 0.95, "dark_ratio": round(ratio, 4)}


def difference_hash(png_path: Path) -> str | None:
    """Return a 64-bit difference hash for repeat-frame screening."""
    try:
        from PIL import Image
        with Image.open(png_path) as source:
            pixels = list(source.convert("L").resize((9, 8)).getdata())
    except (OSError, ImportError):
        return None
    bits = []
    for row in range(8):
        offset = row * 9
        bits.extend(1 if pixels[offset + column] > pixels[offset + column + 1] else 0
                    for column in range(8))
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return f"{value:016x}"


def hamming_distance(left: str | None, right: str | None) -> int | None:
    if not left or not right:
        return None
    try:
        return (int(left, 16) ^ int(right, 16)).bit_count()
    except ValueError:
        return None


def _shot_reuse_issues(rows: list[dict]) -> list[dict]:
    """Flag adjacent repeated assets/frames unless each use has a distinct purpose."""
    issues = []
    for previous, current in zip(rows, rows[1:]):
        same_source = bool(
            (previous.get("asset_id") and previous.get("asset_id") == current.get("asset_id"))
            or (previous.get("source_sha256")
                and previous.get("source_sha256") == current.get("source_sha256"))
        )
        distance = hamming_distance(previous.get("frame_dhash"), current.get("frame_dhash"))
        similar_frame = distance is not None and distance <= 3
        if not (same_source or similar_frame):
            continue
        previous_variation = str(previous.get("variation") or "").strip()
        current_variation = str(current.get("variation") or "").strip()
        has_distinct_purpose = bool(previous_variation and current_variation
                                    and previous_variation != current_variation)
        issue = {
            "type": "REPEATED_SOURCE_WITHOUT_PURPOSE" if same_source else "NEAR_DUPLICATE_FRAME",
            "start_s": current.get("start_s"),
            "end_s": current.get("end_s"),
            "shot_id": current.get("shot_id"),
            "previous_shot_id": previous.get("shot_id"),
            "asset_id": current.get("asset_id"),
            "previous_asset_id": previous.get("asset_id"),
            "frame_hamming_distance": distance,
            "state": "ALLOWED_WITH_DISTINCT_PURPOSE" if has_distinct_purpose else "FAIL",
            "variation": current_variation or None,
        }
        issues.append(issue)
    return issues


def _shot_contact(project: Path, video: Path, storyboard_path: Path,
                  receipts: Path) -> dict:
    """Sample one frame per storyboard placement and diagnose adjacent reuse."""
    try:
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "UNAVAILABLE", "reason": "storyboard is unreadable", "shots": []}
    shots = storyboard.get("shots")
    if not isinstance(shots, list) or not shots:
        return {"state": "UNAVAILABLE", "reason": "storyboard has no shots", "shots": []}
    rows = []
    frames = []
    cursor = 0.0
    receipts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        for index, shot in enumerate(shots):
            if not isinstance(shot, dict):
                continue
            try:
                duration = float(shot.get("duration_s") or shot.get("duration") or 0)
            except (TypeError, ValueError):
                duration = 0.0
            try:
                start = float(shot.get("start", cursor))
            except (TypeError, ValueError):
                start = cursor
            try:
                end = float(shot.get("end", start + duration))
            except (TypeError, ValueError):
                end = start + duration
            if end <= start:
                end = start + duration
            sample_at = start + max(0.01, end - start) / 2
            frame = temp_path / f"shot-{index:03d}.png"
            extracted = extract_frame(video, sample_at, frame)
            source_ref = str(shot.get("source") or shot.get("image") or shot.get("video") or "")
            if source_ref.startswith("project://"):
                source_path = project / source_ref[len("project://"):]
            else:
                source_path = ROOT / source_ref
            source_digest = None
            if source_path.is_file():
                digest = hashlib.sha256()
                with source_path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(block)
                source_digest = digest.hexdigest()
            row = {
                "shot_id": shot.get("shot_id") or f"shot-{index + 1:03d}",
                "segment_id": shot.get("segment_id"),
                "start_s": round(start, 3), "end_s": round(end, 3),
                "asset_id": shot.get("asset_id"),
                "visual_role": shot.get("visual_role"),
                "evidence_ref": shot.get("evidence_ref"),
                "variation": shot.get("variation"),
                "source_sha256": source_digest,
                "frame_dhash": difference_hash(frame) if extracted else None,
                "frame_extracted": bool(extracted),
            }
            rows.append(row)
            if extracted:
                named = receipts / f"shot-contact-{index + 1:03d}.png"
                named.write_bytes(frame.read_bytes())
                frames.append(named)
            cursor = end
    issues = _shot_reuse_issues(rows)
    unresolved = [issue for issue in issues if issue["state"] == "FAIL"]
    missing_metadata = [row for row in rows if not row.get("visual_role")
                        or (row.get("visual_role") == "proof" and not row.get("evidence_ref"))]
    contact = receipts / "visual-shot-contact-sheet.png"
    sheet_written = build_contact_sheet(frames, contact) if frames else False
    return {
        "state": "VISUAL_FAIL" if unresolved or missing_metadata else "VISUAL_PASS",
        "shot_count": len(rows),
        "sampled_frames": len(frames),
        "contact_sheet": contact.relative_to(project).as_posix() if sheet_written else None,
        "issues": issues,
        "missing_role_or_evidence_metadata": [row["shot_id"] for row in missing_metadata],
        "shots": rows,
    }


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
    r = hidden_run(
        ["ffmpeg", "-y"] + inputs + ["-filter_complex", filter_chain, "-map", "[v]",
         str(out_png)],
        timeout=120,
    )
    if r.returncode == 0 and out_png.exists() and out_png.stat().st_size > 0:
        return True

    # Some Windows ffmpeg builds reject the xstack filter's `|` layout
    # separators when passed through CreateProcess. PIL keeps the same sampled
    # frames and dimensions without making contact-sheet production a gate.
    try:
        from PIL import Image
        sheet = Image.new("RGB", (sheet_w, sheet_h), (15, 17, 23))
        for index, frame in enumerate(frames):
            with Image.open(frame) as source:
                thumb = source.convert("RGB").resize((THUMB_W, THUMB_H))
            sheet.paste(thumb, ((index % cols) * THUMB_W,
                                (index // cols) * THUMB_H))
        sheet.save(out_png, format="PNG", optimize=True)
        return out_png.is_file() and out_png.stat().st_size > 0
    except (OSError, ImportError):
        return False


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
        "video_sha256": file_sha256(video),
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

    storyboard_path = project / "script" / "storyboard.json"
    shot_content = (_shot_contact(project, video, storyboard_path, receipts)
                    if storyboard_path.is_file()
                    else {"state": "UNAVAILABLE", "reason": "storyboard not found"})
    result["shot_content_qc"] = shot_content
    if black_count > 2 or extract_fail > 3:
        result["status"] = "WARN"
    elif shot_content.get("state") == "VISUAL_FAIL":
        result["status"] = "FAIL"
    else:
        result["status"] = "PASS"

    canonical_qc = receipts / f"qc-report-{project.name}.json"
    try:
        canonical = json.loads(canonical_qc.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        canonical = {}
    technical = technical_state(canonical)
    content, publication = human_review_states(project)
    result["quality_states"] = {
        "technical": technical,
        "visual": shot_content.get("state", "VISUAL_PENDING"),
        "content": content,
        "publication": publication,
    }
    result["quality_state_basis"] = {
        "technical_check_ids": list(TECHNICAL_CHECK_IDS),
        "technical_source": "canonical qc-report checks (media decodability only; not overall)",
        "publication_source": "receipts/human-review.json (real reviewer, timestamp, scores and APPROVED required)",
        "canonical_qc_overall": canonical.get("overall"),
    }

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
