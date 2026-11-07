"""Import user-selected media for local preview without claiming publication rights.

The import receipt binds each copied byte to the explicitly selected input
folder. Its permission is intentionally limited to local preview. User media is
never treated as claim evidence and the receipt never grants distribution.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

SCHEMA = "contentops.user-assets-import/v1"
MANIFEST_SCHEMA = "contentops.m5-assets/v1"
RECEIPT = Path("receipts") / "user-assets-import.json"
MANIFEST = Path("sources") / "assets.json"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


class LocalAssetError(ValueError):
    """A user-selected media folder or imported asset is invalid."""


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise LocalAssetError(f"cannot read {path.name}: {exc}") from None
    if not isinstance(value, dict):
        raise LocalAssetError(f"{path.name} must contain a JSON object")
    return value


def _safe_name(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip(".-_")
    return (stem or "media")[:64]


def _validate_image(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            header = stream.read(16)
    except OSError as exc:
        raise LocalAssetError(f"cannot read image {path.name}: {exc}") from None
    suffix = path.suffix.casefold()
    valid = ((suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"))
             or (suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"))
             or (suffix == ".webp" and header[:4] == b"RIFF"
                 and header[8:12] == b"WEBP"))
    if not valid:
        raise LocalAssetError(f"file extension does not match a supported image: {path.name}")


def _video_info(path: Path) -> Dict[str, Any]:
    # Imported lazily so a still-image folder needs no external media tools.
    from process_utils import hidden_run

    result = hidden_run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", str(path),
    ], timeout=60)
    try:
        probe = json.loads(result.stdout or "{}")
        duration = float((probe.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        probe, duration = {}, 0.0
    if result.returncode or duration <= 0:
        raise LocalAssetError(f"could not measure source video {path.name}")
    streams = probe.get("streams") or []
    video = next((row for row in streams
                  if isinstance(row, dict) and row.get("codec_type") == "video"), {})
    audio = next((row for row in streams
                  if isinstance(row, dict) and row.get("codec_type") == "audio"), None)
    rate = str(video.get("avg_frame_rate") or "")
    try:
        numerator, denominator = rate.split("/", 1)
        fps = round(float(numerator) / float(denominator), 3)
    except (ValueError, ZeroDivisionError):
        fps = None
    return {
        "duration_s": round(duration, 3),
        "video_codec": str(video.get("codec_name") or "unknown"),
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "frames_per_second": fps,
        "audio_present": audio is not None,
    }


def _video_duration(path: Path) -> float:
    """Compatibility helper for callers that only need the timeline length."""
    return float(_video_info(path)["duration_s"])


def _extract_frame(video: Path, timestamp: float, output: Path) -> None:
    from process_utils import hidden_run

    output.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss",
        f"{timestamp:.3f}", "-i", str(video), "-frames:v", "1",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease",
        str(output),
    ], timeout=180)
    if result.returncode or not output.is_file() or output.stat().st_size == 0:
        output.unlink(missing_ok=True)
        raise LocalAssetError(f"could not extract a frame from {video.name}")


def _contact_sheet(project: Path, repo_root: Path,
                   rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Make a local visual index of imported stills and extracted video frames."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {"state": "UNAVAILABLE", "reason": "Pillow is not installed"}
    candidates = [row for row in rows
                  if isinstance(row, dict)
                  and row.get("permission") == "USER_PROVIDED_LOCAL"
                  and row.get("type") == "USER_PROVIDED_IMAGE"
                  and row.get("repo_path")]
    if not candidates:
        return {"state": "NOT_NEEDED", "items": 0}
    candidates = candidates[:24]
    cell_w, cell_h, label_h, columns = 320, 220, 34, 3
    font = ImageFont.load_default()
    sheet = Image.new("RGB", (cell_w * columns,
                              (cell_h + label_h) * ((len(candidates) + columns - 1) // columns)),
                      (18, 22, 30))
    draw = ImageDraw.Draw(sheet)
    mapping = []
    for index, row in enumerate(candidates):
        source = (repo_root / str(row["repo_path"])).resolve()
        try:
            source.relative_to(project)
        except ValueError:
            continue
        try:
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((cell_w - 12, cell_h - 12))
                col, line = index % columns, index // columns
                x = col * cell_w + (cell_w - image.width) // 2
                y = line * (cell_h + label_h) + (cell_h - image.height) // 2
                sheet.paste(image, (x, y))
                label = str(row.get("id") or "")
                draw.text((col * cell_w + 6, line * (cell_h + label_h) + cell_h),
                          label[:54], font=font, fill=(230, 235, 242))
                mapping.append({"asset_id": row.get("id"), "cell": index + 1})
        except (OSError, ValueError):
            continue
    if not mapping:
        return {"state": "FAILED", "reason": "no imported preview image could be read"}
    target = project / "receipts" / "user-assets-contact-sheet.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.resolve(strict=False).relative_to(project)
    except ValueError:
        raise LocalAssetError("contact sheet destination resolves outside the project") from None
    if target.is_symlink():
        raise LocalAssetError("refusing symlinked contact sheet destination")
    sheet.save(target, format="JPEG", quality=88, optimize=True)
    return {"state": "READY", "path": target.relative_to(repo_root).as_posix(),
            "items": len(mapping), "asset_cells": mapping}


def import_local_assets(source_dir: Path, project_dir: Path, *, repo_root: Path) -> Dict[str, Any]:
    """Copy explicit user media into one project and record preview-only scope.

    Videos are retained and receive start, middle, and end representative
    frames plus format metadata. A local contact sheet indexes all selected
    stills and extracted frames. Unsupported files are ignored; directories
    with no supported media fail clearly.
    """
    source = Path(source_dir).expanduser().resolve()
    project = Path(project_dir).resolve()
    root = Path(repo_root).resolve()
    if not source.is_dir():
        raise LocalAssetError("--assets must name an existing directory")
    try:
        project.relative_to(root)
    except ValueError:
        raise LocalAssetError("project directory must stay inside the repository") from None

    candidates = sorted(
        (path for path in source.rglob("*")
         if path.is_file() and not path.is_symlink()
         and path.suffix.casefold() in IMAGE_SUFFIXES | VIDEO_SUFFIXES),
        key=lambda path: path.relative_to(source).as_posix().casefold(),
    )
    if not candidates:
        raise LocalAssetError("--assets contains no supported image or video files")

    target_dir = project / "assets" / "imported" / "user"
    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        target_dir.resolve().relative_to(project)
    except ValueError:
        raise LocalAssetError("user media destination resolves outside the project") from None
    manifest_path = project / MANIFEST
    if manifest_path.is_file():
        manifest = _load(manifest_path)
        if manifest.get("schema") != MANIFEST_SCHEMA or not isinstance(manifest.get("assets"), list):
            raise LocalAssetError("existing sources/assets.json has an unsupported schema")
    else:
        manifest = {"schema": MANIFEST_SCHEMA, "policy":
                    "User-provided media is local-preview-only until separately rights-cleared.",
                    "assets": []}
    rows = list(manifest["assets"])
    ids = {str(row.get("id")) for row in rows if isinstance(row, dict)}
    receipts: List[Dict[str, Any]] = []

    def copy_asset(path: Path, *, asset_id: str, asset_type: str,
                   origin_id: str | None = None) -> Dict[str, Any]:
        digest = _sha(path)
        name = f"{digest[:12]}-{_safe_name(path.name)}{path.suffix.casefold()}"
        target = target_dir / name
        try:
            target.resolve(strict=False).relative_to(project)
        except ValueError:
            raise LocalAssetError("user media destination resolves outside the project") from None
        if target.is_symlink():
            raise LocalAssetError(f"refusing symlinked import target {target.name}")
        if target.exists() and _sha(target) != digest:
            raise LocalAssetError(f"import target collision for {path.name}")
        if not target.exists():
            target.write_bytes(path.read_bytes())
        relative = target.relative_to(root).as_posix()
        row = {
            "id": asset_id,
            "sha256": digest,
            "type": asset_type,
            "origin": "USER_PROVIDED",
            "permission": "USER_PROVIDED_LOCAL",
            "usage_scope": "LOCAL_PREVIEW_ONLY",
            "distribution_authorized": False,
            "evidence_capable": False,
            "repo_path": relative,
            "source_name": path.name,
        }
        if origin_id:
            row["derived_from_asset_id"] = origin_id
        return row

    for path in candidates:
        if path.suffix.casefold() in IMAGE_SUFFIXES:
            _validate_image(path)
        digest = _sha(path)
        base_id = f"user-{digest[:16]}"
        if base_id in ids:
            existing = next(row for row in rows if str(row.get("id")) == base_id)
            if existing.get("sha256") != digest:
                raise LocalAssetError(f"asset id collision for {path.name}")
            continue
        asset_type = "USER_PROVIDED_IMAGE" if path.suffix.casefold() in IMAGE_SUFFIXES \
            else "USER_PROVIDED_VIDEO"
        copied = copy_asset(path, asset_id=base_id, asset_type=asset_type)
        rows.append(copied)
        ids.add(base_id)
        receipts.append({"id": base_id, "sha256": digest,
                         "repo_path": copied["repo_path"], "type": asset_type,
                         "source_name": path.name, "source_bytes": path.stat().st_size})
        if asset_type == "USER_PROVIDED_VIDEO":
            summary = _video_info(path)
            video_receipt = receipts[-1]
            video_receipt["video_summary"] = summary
            duration = float(summary["duration_s"])
            samples = []
            fps = float(summary.get("frames_per_second") or 0)
            end_limit = max(0.0, duration - (2.0 / fps if fps > 0 else 0.25))
            for label, fraction in (("start", 0.05), ("middle", 0.5), ("end", 0.95)):
                timestamp = round(max(0.0, min(duration * fraction, end_limit)), 3)
                frame_id = f"user-frame-{digest[:12]}-{label}"
                frame_path = target_dir / "frames" / f"{digest[:12]}-{label}.png"
                _extract_frame(path, timestamp, frame_path)
                frame_bytes = frame_path.stat().st_size
                frame_row = copy_asset(frame_path, asset_id=frame_id,
                                       asset_type="USER_PROVIDED_IMAGE", origin_id=base_id)
                frame_row["source_name"] = path.name
                rows.append(frame_row)
                ids.add(frame_id)
                samples.append({"id": frame_id, "timestamp_s": timestamp})
                receipts.append({"id": frame_id, "sha256": frame_row["sha256"],
                                 "repo_path": frame_row["repo_path"],
                                 "type": frame_row["type"], "derived_from_asset_id": base_id,
                                 "source_name": path.name, "source_bytes": frame_bytes,
                                 "extraction_timestamp_s": timestamp})
                frame_path.unlink(missing_ok=True)
            video_receipt["video_summary"]["sample_frames"] = samples

    manifest["assets"] = rows
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    prior_receipts: List[Dict[str, Any]] = []
    prior_path = project / RECEIPT
    if prior_path.is_file():
        previous = _load(prior_path)
        if previous.get("schema") != SCHEMA:
            raise LocalAssetError("existing user asset import receipt has an unsupported schema")
        prior_receipts = [row for row in previous.get("assets", [])
                          if isinstance(row, dict)]
    all_receipts = {str(row.get("id")): row for row in prior_receipts}
    all_receipts.update({str(row.get("id")): row for row in receipts})
    receipt = {
        "schema": SCHEMA,
        "state": "IMPORTED_LOCAL_PREVIEW_ONLY",
        "source_directory_name": source.name,
        "usage_scope": "LOCAL_PREVIEW_ONLY",
        "distribution_authorized": False,
        "evidence_capable": False,
        "assets": [all_receipts[key] for key in sorted(all_receipts)],
    }
    target = project / RECEIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    receipt["contact_sheet"] = _contact_sheet(project, root, rows)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    imported_rows = [row for row in rows
                     if isinstance(row, dict)
                     and row.get("permission") == "USER_PROVIDED_LOCAL"]
    for row in imported_rows:
        if not is_valid_local_preview_asset(row, project, root):
            raise LocalAssetError(
                f"imported asset {row.get('id')} is missing, changed, or lacks a valid receipt")
    return receipt


def is_valid_local_preview_asset(asset: Mapping[str, Any], project_dir: Path,
                                 repo_root: Path) -> bool:
    """Verify a local-only manifest entry against its import receipt and bytes."""
    if (asset.get("permission") != "USER_PROVIDED_LOCAL"
            or asset.get("usage_scope") != "LOCAL_PREVIEW_ONLY"
            or asset.get("distribution_authorized") is not False
            or asset.get("evidence_capable") is not False):
        return False
    project = Path(project_dir).resolve()
    root = Path(repo_root).resolve()
    try:
        receipt = _load(project / RECEIPT)
        relative = str(asset.get("repo_path") or "")
        path = (root / relative).resolve()
        path.relative_to(root)
        path.relative_to(project)
        listed = any(
            isinstance(row, dict)
            and row.get("id") == asset.get("id")
            and row.get("sha256") == asset.get("sha256")
            and row.get("repo_path") == relative
            for row in receipt.get("assets", [])
        )
        registered = _load(project / MANIFEST)
        manifest_row = next((row for row in registered.get("assets", [])
                             if isinstance(row, dict) and row.get("id") == asset.get("id")), None)
        return bool(
            receipt.get("schema") == SCHEMA
            and receipt.get("state") == "IMPORTED_LOCAL_PREVIEW_ONLY"
            and receipt.get("usage_scope") == "LOCAL_PREVIEW_ONLY"
            and receipt.get("distribution_authorized") is False
            and listed and manifest_row == dict(asset)
            and path.is_file() and _sha(path) == str(asset.get("sha256") or "")
        )
    except (LocalAssetError, OSError, ValueError):
        return False


__all__ = ["LocalAssetError", "import_local_assets", "is_valid_local_preview_asset"]
