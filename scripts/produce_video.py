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
                if candidate.is_relative_to(ROOT.resolve()):
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
            if candidate.is_relative_to(ROOT.resolve()):
                candidates.append(candidate)
    digest = hashlib.sha256()
    for path in sorted(set(candidates), key=lambda p: p.as_posix()):
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
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


def produce(project: Path, *, force: bool = False, mode: str = "AUTO") -> dict[str, Any]:
    mode = mode.upper()
    if mode not in {"AUTO", "REVIEW", "STRICT"}:
        raise ValueError("mode must be AUTO, REVIEW, or STRICT")
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    if not project.is_dir() or not project.is_relative_to(ROOT.resolve()):
        raise ValueError("--project must be an existing project inside this repository")
    digest = _input_digest(project)
    if not force and mode == "AUTO":
        prior = _reusable(project, digest)
        if prior:
            reused = {**prior, "state": "QC_PASSED", "reused": True,
                      "resumed_from_run_id": prior.get("run_id"),
                      "run_id": str(uuid.uuid4()), "started_at": _now(),
                      "finished_at": _now(), "elapsed_seconds": 0.0,
                      "rendered": True, "technical_qc": "PASS",
                      "production_ready": False, "published": False}
            (project / "receipts" / RECEIPT).write_text(
                json.dumps(reused, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return reused

    run_id, started, start = str(uuid.uuid4()), _now(), time.monotonic()
    receipt: dict[str, Any] = {
        "schema": "contentops.produce-video/v1",
        "run_id": run_id,
        "task_id": digest[:16],
        "project": project.relative_to(ROOT).as_posix(),
        "input_sha256": digest,
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
        m5_run = m5_production.build(project)
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
