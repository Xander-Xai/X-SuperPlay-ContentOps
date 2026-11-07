#!/usr/bin/env python3
"""Run one prepared M5 video project through compose and technical QC.

This is the single execution entry for a project whose account, evidence,
script, claims and licensed assets are already present. It delegates all
production work to the existing M5 pipeline and pinned Easel renderer. It does
not approve copy or publish. A matching QC-passed run is reused by input digest.

Usage:
    python scripts/produce_video.py --project projects/my-project
    python scripts/produce_video.py --project projects/my-project --mode REVIEW
    python scripts/produce_video.py --project projects/my-project --force
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT / "scripts"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import m5_production  # noqa: E402

RECEIPT = "produce-video.json"


def _relative_to_root(path: Path) -> Path | None:
    """Return a root-relative path with Windows case normalization."""
    try:
        relative = Path(os.path.relpath(path, ROOT.resolve()))
    except ValueError:
        return None
    if relative.is_absolute() or relative == Path("..") or relative.parts[:1] == ("..",):
        return None
    return relative


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _input_digest(project: Path) -> str:
    """Hash declared production inputs, including local files named by assets."""
    candidates = [
        project / "project.yaml",
        project / "script" / "script.json",
        project / "script" / "claims.json",
        project / "sources" / "assets.json",
        project / "sources" / "source-refs.json",
        ROOT / "runtime" / "easel.lock.json",
    ]
    assets_path = project / "sources" / "assets.json"
    if assets_path.is_file():
        try:
            assets = json.loads(assets_path.read_text(encoding="utf-8")).get("assets", [])
        except (OSError, ValueError, TypeError):
            assets = []
        for asset in assets:
            reference = asset.get("repo_path") if isinstance(asset, dict) else None
            if reference:
                candidate = (ROOT / str(reference)).resolve()
                if _relative_to_root(candidate) is not None:
                    candidates.append(candidate)
    project_yaml = project / "project.yaml"
    if project_yaml.is_file():
        try:
            config = m5_production._read_yaml(project_yaml)
        except Exception:
            config = {}
        refs = list(config.get("source_refs") or [])
        sidecar = project / "sources" / "source-refs.json"
        if sidecar.is_file():
            try:
                refs.extend(json.loads(sidecar.read_text(encoding="utf-8")).get("refs", []))
            except (OSError, ValueError, TypeError):
                pass
        for ref in refs:
            if not isinstance(ref, dict) or not ref.get("path"):
                continue
            candidate = (ROOT / str(ref["path"])).resolve()
            if _relative_to_root(candidate) is not None:
                candidates.append(candidate)
    digest = hashlib.sha256()
    for path in sorted(set(candidates), key=lambda p: p.as_posix()):
        root_relative = _relative_to_root(path.resolve())
        if root_relative is None:
            continue
        relative = root_relative.as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_file():
            digest.update(_hash_file(path).encode("ascii"))
        else:
            digest.update(b"MISSING")
        digest.update(b"\n")
    return digest.hexdigest()


def _reusable(project: Path, digest: str) -> dict[str, Any] | None:
    receipt_path = project / "receipts" / RECEIPT
    if not receipt_path.is_file():
        return None
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if receipt.get("input_sha256") != digest or receipt.get("state") != "QC_PASSED":
        return None
    video = project / "final" / f"{project.name}.mp4"
    report_path = project / "receipts" / f"qc-report-{project.name}.json"
    if not video.is_file() or not report_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if (report.get("overall") != "PASS"
            or report.get("graded_target") != f"project://final/{project.name}.mp4"
            or receipt.get("video_sha256") != _hash_file(video)):
        return None
    return receipt


def _run_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: receipt.get(key) for key in (
        "run_id", "task_id", "state", "started_at", "finished_at",
        "elapsed_seconds", "reused", "video_sha256", "stage_timings_seconds",
    ) if key in receipt}


def produce(project: Path, *, force: bool = False, mode: str = "AUTO") -> dict[str, Any]:
    mode = mode.upper()
    if mode not in {"AUTO", "REVIEW", "STRICT"}:
        raise ValueError("mode must be AUTO, REVIEW, or STRICT")
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    project_relative = _relative_to_root(project)
    if not project.is_dir() or project_relative is None:
        raise ValueError("--project must be an existing project inside this repository")
    digest = _input_digest(project)
    receipt_path = project / "receipts" / RECEIPT
    previous: dict[str, Any] = {}
    if receipt_path.is_file():
        try:
            loaded = json.loads(receipt_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                previous = loaded
        except (OSError, ValueError):
            pass
    history = list(previous.get("runs") or [])
    previous_run_id = previous.get("run_id")
    if previous_run_id and not any(item.get("run_id") == previous_run_id for item in history
                                   if isinstance(item, dict)):
        history.append(_run_summary(previous))
    if not force and mode == "AUTO":
        prior = _reusable(project, digest)
        if prior:
            reused = {**prior, "state": "QC_PASSED", "reused": True,
                      "resumed_from_run_id": prior.get("run_id"),
                      "run_id": str(uuid.uuid4()), "started_at": _now(),
                      "finished_at": _now(), "elapsed_seconds": 0.0,
                      "rendered": True, "technical_qc": "PASS",
                      "production_ready": False, "published": False}
            history.append(_run_summary(reused))
            reused["runs"] = history
            receipt_path.write_text(json.dumps(reused, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
            return reused

    run_id, started, start = str(uuid.uuid4()), _now(), time.monotonic()
    receipt: dict[str, Any] = {
        "schema": "contentops.produce-video/v1",
        "run_id": run_id,
        "task_id": digest[:16],
        "project": project_relative.as_posix(),
        "input_sha256": digest,
        "runs": history,
        "mode": mode,
        "state": "RUNNING",
        "started_at": started,
        "reused": False,
        "rendered": False,
        "technical_qc": "NOT_RUN",
        "production_ready": False,
        "external_provider_calls": 0,
        "external_cost": 0,
        "external_cost_reason": "M5 accepts only local SAPI or receipt-bound existing narration in this entry; no paid provider is called",
        "human_review": "PENDING_FOUNDER_REVIEW",
        "copy_review_required_for_render": mode != "AUTO",
        "published": False,
    }
    output = project / "receipts" / RECEIPT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        if mode in {"REVIEW", "STRICT"}:
            try:
                m5_production.copy_review.require_approved(project)
            except m5_production.copy_review.CopyReviewRequired as exc:
                raise m5_production.M5Blocked(f"copy review: {exc}") from None
        m5_run = m5_production.build(project, require_copy_review=(mode != "AUTO"))
        receipt["m5_stages"] = m5_run.get("stages", {})
        receipt["stage_timings_seconds"] = m5_run.get("stage_timings_seconds", {})
        receipt["human_review"] = m5_run.get("human_review", "PENDING_FOUNDER_REVIEW")
        video = project / "final" / f"{project.name}.mp4"
        report_path = project / "receipts" / f"qc-report-{project.name}.json"
        if not video.is_file() or not report_path.is_file():
            raise m5_production.M5Blocked("M5 returned without a final video and QC receipt")
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("graded_target") != f"project://final/{project.name}.mp4":
            raise m5_production.M5Blocked("QC receipt does not grade the produced render")
        if report.get("overall") != "PASS":
            raise m5_production.M5Blocked(f"technical QC did not pass ({report.get('overall')})")
        receipt.update({"state": "QC_PASSED", "video": f"project://final/{project.name}.mp4",
                        "video_sha256": _hash_file(video), "qc_receipt": report_path.name,
                        "rendered": True, "technical_qc": "PASS",
                        "production_ready": False})
    except m5_production.M5Blocked as exc:
        receipt.update({"state": "BLOCKED", "failure_type": type(exc).__name__,
                        "failure_reason": str(exc)[:1000]})
        raise
    except Exception as exc:
        receipt.update({"state": "FAILED", "failure_type": type(exc).__name__,
                        "failure_reason": str(exc)[:1000]})
        raise
    finally:
        receipt["finished_at"] = _now()
        receipt["elapsed_seconds"] = round(time.monotonic() - start, 3)
        receipt["runs"].append(_run_summary(receipt))
        output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, help="prepared project directory under projects/")
    parser.add_argument("--mode", default="AUTO", choices=("AUTO", "REVIEW", "STRICT"),
                        help="AUTO runs authorized M5 stages; REVIEW/STRICT also require a recorded copy approval")
    parser.add_argument("--force", action="store_true", help="rerun even when the same inputs already passed QC")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = produce(Path(args.project), force=args.force, mode=args.mode)
    except (ValueError, m5_production.M5Blocked) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 4
    except Exception as exc:
        print(json.dumps({"state": "FAILED", "failure_type": type(exc).__name__,
                          "reason": str(exc)[:1000]}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
          f"{result['state']} · {result['project']} · {result.get('video', 'reused')} · "
          f"{result.get('elapsed_seconds', 0)}s · review={result.get('human_review')}")
    return 0 if result.get("state") == "QC_PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
