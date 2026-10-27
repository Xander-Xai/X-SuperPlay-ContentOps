#!/usr/bin/env python3
"""Produce a redacted derivative of a capture, and provenance-bound crops.

Two rules drive everything here:

1. **The raw file is never modified.** A redaction reads the raw bytes, writes a
   new file, and the receipt links the two hashes.
2. **A crop cannot be the first time a result is seen.** An enlarged crop must
   name an earlier crop of the same redacted source whose rectangle contains it,
   so the viewer always sees the evidence in context before seeing it enlarged.

The redaction plan also declares ``protected_regions``: parts of the frame whose
meaning changes the conclusion (a warning line, a failure summary, a unit). A
mask that overlaps one of them is refused, because at that point the derivative
no longer supports the claim the raw file supported.

Usage::

    python scripts/redact_terminal_evidence.py redact PLAN.json --project P
    python scripts/redact_terminal_evidence.py crop --project P --receipt R \\
        --crop-id CR-1 --rect 0,0,600,200 --time 1.2 --out work/crops/CR-1.png
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run  # noqa: E402
from contentops.evidence._common import (  # noqa: E402
    ContractError,
    parse_time_range,
    require,
    require_text,
    sha256_file,
)
from contentops.evidence.capture import CaptureProof  # noqa: E402
from contentops.evidence.redaction import (  # noqa: E402
    AUDIO_REMOVED,
    REVIEW_APPROVED,
    RedactionReceipt,
)
from contentops.media.media_paths import resolve_media_path  # noqa: E402

PLAN_SCHEMA = "contentops.redaction-plan/v1"
CROP_SCHEMA = "contentops.crop-receipt/v1"


class RedactionRefused(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _refuse(condition: bool, code: str, detail: str) -> None:
    if not condition:
        raise RedactionRefused(code, detail)


def _local(project: Path, logical: str) -> Path:
    return resolve_media_path(logical, repo_root=ROOT, project_root=project)


def _rect(value: Any, field_name: str) -> Dict[str, int]:
    require(isinstance(value, dict), "INVALID_RECT", f"{field_name} must be an object")
    out = {}
    for key in ("x", "y", "width", "height"):
        item = value.get(key)
        require(isinstance(item, int) and not isinstance(item, bool) and item >= 0,
                "INVALID_RECT", f"{field_name}.{key} must be a non-negative int")
        out[key] = item
    require(out["width"] > 0 and out["height"] > 0, "INVALID_RECT",
            f"{field_name} has zero area")
    return out


def _rects_intersect(a: Dict[str, int], b: Dict[str, int]) -> bool:
    return not (
        a["x"] + a["width"] <= b["x"]
        or b["x"] + b["width"] <= a["x"]
        or a["y"] + a["height"] <= b["y"]
        or b["y"] + b["height"] <= a["y"]
    )


def _ranges_intersect(a: Tuple[int, int], b: Tuple[int, int]) -> bool:
    return not (a[1] <= b[0] or b[1] <= a[0])


def validate_plan(document: Dict[str, Any], project: Path) -> Dict[str, Any]:
    require(isinstance(document, dict), "MALFORMED_PLAN", "plan must be an object")
    require(document.get("schema") == PLAN_SCHEMA, "UNSUPPORTED_SCHEMA",
            f"expected {PLAN_SCHEMA!r}")
    require_text(document.get("redaction_id"), "redaction_id")
    require_text(document.get("capture_receipt"), "capture_receipt")
    raw_ref = require_text(document.get("raw"), "raw")
    out_ref = require_text(document.get("output"), "output")
    _refuse(raw_ref != out_ref, "RAW_OVERWRITTEN",
            "the derivative must have its own path")

    capture_path = _local(project, document["capture_receipt"])
    _refuse(capture_path.is_file(), "CAPTURE_RECEIPT_MISSING",
            f"{capture_path} does not exist")
    proof = CaptureProof.from_dict(
        json.loads(capture_path.read_text(encoding="utf-8")))
    _refuse(proof.recording["logical_path"] == raw_ref, "RAW_NOT_THE_CAPTURE",
            f"the raw reference {raw_ref!r} is not the recording this capture "
            f"proof names ({proof.recording['logical_path']!r})")

    raw_path = _local(project, raw_ref)
    _refuse(raw_path.is_file(), "RAW_MISSING", f"{raw_path} does not exist")
    proof.verify_recording(raw_path)

    dimensions = document.get("source_dimensions") or {}
    for axis in ("width", "height"):
        size = dimensions.get(axis)
        require(isinstance(size, int) and not isinstance(size, bool) and size > 0,
                "INVALID_DIMENSIONS", f"source_dimensions.{axis} must be positive")

    masks = document.get("masks") or []
    require(isinstance(masks, list), "INVALID_MASKS", "masks must be a list")
    normalized_masks = []
    for index, mask in enumerate(masks):
        require(isinstance(mask, dict), "INVALID_MASKS", f"masks[{index}] must be an object")
        require_text(mask.get("mask_id"), f"masks[{index}].mask_id")
        require_text(mask.get("reason"), f"masks[{index}].reason")
        parse_time_range(mask.get("time_range"), f"masks[{index}].time_range")
        rect = _rect(mask.get("rect"), f"masks[{index}].rect")
        require(rect["x"] + rect["width"] <= dimensions["width"], "MASK_OUT_OF_BOUNDS",
                f"masks[{index}] extends past the source width")
        require(rect["y"] + rect["height"] <= dimensions["height"], "MASK_OUT_OF_BOUNDS",
                f"masks[{index}] extends past the source height")
        normalized_masks.append({
            "mask_id": mask["mask_id"], "reason": mask["reason"],
            "time_range": mask["time_range"], "rect": rect,
            "start_ms": parse_time_range(mask["time_range"], "mask")[0],
            "end_ms": parse_time_range(mask["time_range"], "mask")[1],
        })

    protected = document.get("protected_regions") or []
    require(isinstance(protected, list), "INVALID_PROTECTED",
            "protected_regions must be a list")
    for index, region in enumerate(protected):
        require(isinstance(region, dict), "INVALID_PROTECTED",
                f"protected_regions[{index}] must be an object")
        require_text(region.get("name"), f"protected_regions[{index}].name")
        require_text(region.get("why"), f"protected_regions[{index}].why")
        rect = _rect(region.get("rect"), f"protected_regions[{index}].rect")
        start, end = parse_time_range(region.get("time_range"),
                                      f"protected_regions[{index}].time_range")
        for mask in normalized_masks:
            if _rects_intersect(mask["rect"], rect) and _ranges_intersect(
                    (mask["start_ms"], mask["end_ms"]), (start, end)):
                raise RedactionRefused(
                    "MASK_HIDES_PROTECTED_CONTEXT",
                    f"mask {mask['mask_id']!r} overlaps protected region "
                    f"{region['name']!r} ({region['why']}); a derivative that hides "
                    f"it no longer supports the same claim")

    document["_proof"] = proof
    document["_raw_path"] = raw_path
    document["_masks"] = normalized_masks
    return document


def build_filter(masks: Sequence[Dict[str, Any]]) -> str:
    parts = []
    for mask in masks:
        rect = mask["rect"]
        start = mask["start_ms"] / 1000.0
        end = mask["end_ms"] / 1000.0
        parts.append(
            f"drawbox=x={rect['x']}:y={rect['y']}:w={rect['width']}:"
            f"h={rect['height']}:color=black@1.0:t=fill:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
    return ",".join(parts)


def _tool_version() -> Dict[str, str]:
    proc = hidden_run(["ffmpeg", "-version"], timeout=30)
    first = (proc.stdout or "").splitlines()[0] if proc.stdout else "ffmpeg"
    version = first.split("version")[-1].strip().split()[0] if "version" in first else "unknown"
    return {"name": "ffmpeg", "version": version}


def _has_audio(path: Path) -> bool:
    from contentops.media.transport import ffprobe_json

    payload = ffprobe_json(path)
    return any(stream.get("codec_type") == "audio"
               for stream in payload.get("streams") or [])


def redact(plan_path: Path, project: Path) -> Dict[str, Any]:
    project = project.resolve()
    document = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    document = validate_plan(document, project)

    raw_path: Path = document["_raw_path"]
    output_path = _local(project, document["output"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _refuse(output_path != raw_path, "RAW_OVERWRITTEN",
            "the derivative path resolves to the raw file")

    audio_policy = document.get("audio_policy", AUDIO_REMOVED)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
               "-i", str(raw_path)]
    filter_text = build_filter(document["_masks"])
    if filter_text:
        command += ["-vf", filter_text]
    if audio_policy == AUDIO_REMOVED:
        command += ["-an"]
    command += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
                str(output_path)]

    proc = hidden_run(command, timeout=900)
    _refuse(proc.returncode == 0 and output_path.is_file(),
            "FFMPEG_FAILED", (proc.stderr or "")[-600:])
    if audio_policy == AUDIO_REMOVED:
        _refuse(not _has_audio(output_path), "AUDIO_RETAINED",
                "the derivative still carries an audio stream")

    receipt = RedactionReceipt(
        redaction_id=document["redaction_id"],
        raw_source={"logical_path": document["raw"],
                    "sha256": sha256_file(raw_path)},
        output={"logical_path": document["output"],
                "sha256": sha256_file(output_path)},
        source_dimensions=document["source_dimensions"],
        masks=[{"mask_id": m["mask_id"], "reason": m["reason"],
                "time_range": m["time_range"], "rect": m["rect"]}
               for m in document["_masks"]],
        audio_policy=audio_policy,
        tool=_tool_version(),
        review_status=document.get("review_status", "PENDING"),
        reviewer=document.get("reviewer") or None,
        reviewed_at=document.get("reviewed_at") or None,
        publishable_scope=bool(document.get("publishable_scope")),
        notes=list(document.get("notes") or []),
    ).validate()

    receipts = project / "receipts" / "redactions"
    receipts.mkdir(parents=True, exist_ok=True)
    path = receipts / f"{receipt.redaction_id}.json"
    path.write_text(json.dumps(receipt.to_dict(), indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return {
        "status": "OK",
        "redaction_id": receipt.redaction_id,
        "output": receipt.output,
        "receipt": f"project://receipts/redactions/{receipt.redaction_id}.json",
        "masks": len(receipt.masks),
        "audio_removed": receipt.audio_removed,
        "review_status": receipt.review_status,
    }


def _load_receipt(project: Path, receipt_ref: str) -> Tuple[Path, RedactionReceipt]:
    path = _local(project, receipt_ref)
    _refuse(path.is_file(), "REDACTION_RECEIPT_MISSING",
            f"{path} does not exist; a crop must be bound to a redaction receipt")
    receipt = RedactionReceipt.from_dict(
        json.loads(path.read_text(encoding="utf-8")))
    return path, receipt


def _crops_path(project: Path, redaction_id: str) -> Path:
    return project / "receipts" / "redactions" / f"{redaction_id}-crops.json"


def crop(project: Path, receipt_ref: str, crop_id: str, rect_text: str,
         time_s: float, out_ref: str,
         context_crop_id: Optional[str] = None) -> Dict[str, Any]:
    project = project.resolve()
    _, receipt = _load_receipt(project, receipt_ref)

    # The source is the receipt's output, and a receipt cannot name the raw path
    # as its output, so a crop structurally cannot start from the raw capture.
    source_path = _local(project, receipt.output["logical_path"])
    _refuse(source_path.is_file(), "REDACTED_MISSING",
            f"{source_path} does not exist")
    _refuse(sha256_file(source_path) == receipt.output["sha256"],
            "EVIDENCE_SHA_MISMATCH",
            "the derivative changed after its receipt was written")

    try:
        x, y, width, height = (int(part) for part in rect_text.split(","))
    except (ValueError, TypeError):
        raise RedactionRefused("INVALID_RECT",
                               "rect must be x,y,width,height") from None
    rect = {"x": x, "y": y, "width": width, "height": height}
    dims = receipt.source_dimensions
    _refuse(width > 0 and height > 0, "INVALID_RECT", "crop rect has zero area")
    _refuse(x + width <= dims["width"] and y + height <= dims["height"],
            "CROP_OUT_OF_BOUNDS", "crop extends past the source frame")

    registry_path = _crops_path(project, receipt.redaction_id)
    registry = {"schema": CROP_SCHEMA, "redaction_id": receipt.redaction_id,
                "source_sha256": receipt.output["sha256"], "crops": []}
    if registry_path.exists():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        _refuse(registry.get("source_sha256") == receipt.output["sha256"],
                "STALE_CROP_REGISTRY",
                "the crop registry was built from a different derivative")

    _refuse(crop_id not in {c["crop_id"] for c in registry["crops"]},
            "DUPLICATE_CROP_ID", f"crop {crop_id!r} already exists")

    if context_crop_id:
        context = next((c for c in registry["crops"]
                        if c["crop_id"] == context_crop_id), None)
        _refuse(context is not None, "UNKNOWN_CONTEXT_CROP",
                f"context crop {context_crop_id!r} does not exist")
        _refuse(context["rect"]["x"] <= x
                and context["rect"]["y"] <= y
                and context["rect"]["x"] + context["rect"]["width"] >= x + width
                and context["rect"]["y"] + context["rect"]["height"] >= y + height,
                "CROP_NOT_CONTAINED_BY_CONTEXT",
                "the enlarged crop is not inside its context crop, so it does not "
                "show the same evidence with more detail")

    out_path = _local(project, out_ref)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", f"{max(time_s, 0):.3f}", "-i", str(source_path),
        "-frames:v", "1",
        "-vf", f"crop={width}:{height}:{x}:{y}",
        str(out_path),
    ], timeout=120)
    _refuse(proc.returncode == 0 and out_path.is_file(), "FFMPEG_FAILED",
            (proc.stderr or "")[-400:])

    record = {
        "schema": CROP_SCHEMA,
        "crop_id": crop_id,
        "redaction_id": receipt.redaction_id,
        "source_sha256": receipt.output["sha256"],
        "source_logical_path": receipt.output["logical_path"],
        "output_logical_path": out_ref,
        "output_sha256": sha256_file(out_path),
        "rect": rect,
        "source_dimensions": dict(dims),
        "time_s": round(time_s, 3),
        "context_crop_id": context_crop_id,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    registry["crops"].append(record)
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False),
                             encoding="utf-8")
    return {"status": "OK", **record}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    redact_p = sub.add_parser("redact")
    redact_p.add_argument("plan")
    redact_p.add_argument("--project", default="projects/easel-evidence-capture")

    crop_p = sub.add_parser("crop")
    crop_p.add_argument("--project", default="projects/easel-evidence-capture")
    crop_p.add_argument("--receipt", required=True)
    crop_p.add_argument("--crop-id", required=True)
    crop_p.add_argument("--rect", required=True, help="x,y,width,height")
    crop_p.add_argument("--time", type=float, required=True)
    crop_p.add_argument("--out", required=True)
    crop_p.add_argument("--context-crop-id", default=None)

    args = parser.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()
    try:
        if args.command == "redact":
            result = redact(Path(args.plan), project)
        else:
            result = crop(project, args.receipt, args.crop_id, args.rect,
                          args.time, args.out, args.context_crop_id)
    except (RedactionRefused, ContractError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)},
                         indent=2, ensure_ascii=False))
        return 4
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
