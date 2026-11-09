"""Read-only scene candidate adapter for locally supplied, rights-reviewable footage.

This is a narrow integration seam for Breakthrough/PySceneDetect. It does not
cut video, create factual evidence, alter a storyboard, spend credits, approve
rights, or authorize publishing. External dependency is loaded only on demand.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

SCHEMA = "contentops.scene-candidates/v1"
MAX_SCENES = 500
EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
Detector = Callable[[Path, float], Iterable[tuple[float, float]]]


class SceneAnalysisError(ValueError):
    """Source, detector, or output path failed validation."""


class SceneDetectorUnavailable(SceneAnalysisError):
    """The optional PySceneDetect dependency is absent."""


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _local_source(project: Path, relative_path: str) -> tuple[Path, str]:
    root = project.resolve(strict=True)
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise SceneAnalysisError("SOURCE_PATH_REQUIRED")
    candidate = (root / relative_path).resolve(strict=True)
    try:
        rel = candidate.relative_to(root)
    except ValueError as exc:
        raise SceneAnalysisError("SOURCE_OUTSIDE_PROJECT") from exc
    if not candidate.is_file() or candidate.suffix.lower() not in EXTENSIONS:
        raise SceneAnalysisError("UNSUPPORTED_SOURCE_VIDEO")
    if rel.parts and rel.parts[0] == "receipts":
        raise SceneAnalysisError("RECEIPT_NOT_SOURCE_MEDIA")
    return candidate, rel.as_posix()


def _detect_with_pyscenedetect(video: Path, threshold: float) -> Iterable[tuple[float, float]]:
    try:
        from scenedetect import ContentDetector, detect
    except ImportError as exc:
        raise SceneDetectorUnavailable("PYSCENEDETECT_NOT_INSTALLED") from exc
    scenes = detect(str(video), ContentDetector(threshold=threshold))
    return [(start.get_seconds(), end.get_seconds()) for start, end in scenes]


def _normalise(scenes: Iterable[tuple[float, float]], source: str) -> list[dict]:
    output: list[dict] = []
    previous_end = 0.0
    for start, end in scenes:
        if len(output) >= MAX_SCENES:
            raise SceneAnalysisError("TOO_MANY_SCENES")
        try:
            begin, finish = float(start), float(end)
        except (TypeError, ValueError) as exc:
            raise SceneAnalysisError("INVALID_SCENE_TIME") from exc
        if (not math.isfinite(begin) or not math.isfinite(finish)
                or begin < 0 or finish <= begin or begin < previous_end - 0.001):
            raise SceneAnalysisError("INVALID_SCENE_BOUNDARIES")
        output.append({
            "scene_id": f"SCENE-{len(output) + 1:03d}",
            "start_seconds": round(begin, 3),
            "end_seconds": round(finish, 3),
            "duration_seconds": round(finish - begin, 3),
            "source_ref": f"project://{source}",
            "visual_role": "REFERENCE_ONLY",
            "evidence_capable": False,
            "approved_for_use": False,
        })
        previous_end = finish
    return output


def analyze(project: Path, source: str, *, threshold: float = 27.0,
            detector: Detector | None = None) -> dict:
    """Produce a source-hash-bound, non-authoritative candidate manifest.

    Injecting detector enables completely offline contract tests. An actual
    execution uses PySceneDetect only when the caller opted into this command.
    """
    try:
        value = float(threshold)
    except (TypeError, ValueError) as exc:
        raise SceneAnalysisError("INVALID_THRESHOLD") from exc
    if not math.isfinite(value) or not (0 < value <= 255):
        raise SceneAnalysisError("INVALID_THRESHOLD")
    video, relative = _local_source(Path(project), source)
    chosen = detector if detector is not None else _detect_with_pyscenedetect
    scenes = _normalise(chosen(video, value), relative)
    try:
        version = importlib.metadata.version("scenedetect") if detector is None else "TEST_INJECTION"
    except importlib.metadata.PackageNotFoundError:
        version = "UNKNOWN"
    return {
        "schema": SCHEMA,
        "state": "CANDIDATES_READY" if scenes else "NO_SCENES_DETECTED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_ref": f"project://{relative}",
        "source_sha256": _sha256(video),
        "detector": {"repository": "Breakthrough/PySceneDetect",
                     "method": "ContentDetector", "threshold": value,
                     "installed_version": version},
        "scenes": scenes,
        "scene_count": len(scenes),
        "rights_review": "PENDING_HUMAN_REVIEW",
        "content_review": "PENDING_HUMAN_REVIEW",
        "production_ready": False,
        "publish_authorized": False,
        "external_network_calls": 0,
        "provider_spend": 0,
    }


def write_receipt(project: Path, payload: dict) -> Path:
    """Persist only inside the project receipts directory; refuse symlink escape."""
    root = Path(project).resolve(strict=True)
    folder = root / "receipts"
    folder.mkdir(parents=True, exist_ok=True)
    if not folder.resolve().is_relative_to(root):
        raise SceneAnalysisError("RECEIPTS_OUTSIDE_PROJECT")
    path = folder / "scene-candidates.json"
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise SceneAnalysisError("RECEIPT_PATH_UNSAFE")
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    temp = folder / ".scene-candidates.tmp"
    if temp.is_symlink() or not temp.resolve().is_relative_to(root):
        raise SceneAnalysisError("TEMP_RECEIPT_PATH_UNSAFE")
    temp.write_text(data, encoding="utf-8")
    temp.replace(path)
    return path
