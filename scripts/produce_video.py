#!/usr/bin/env python3
"""Run one M5 video project through source-bound preparation, compose and QC.

For a brief-driven AUTO project, missing script and M5 input contracts are
drafted from its collected evidence pack and bridged when the required source
permissions and placement-to-asset map are present. Existing M5 scripts are
left untouched. ``--assets`` imports an explicitly selected local image/video
folder for preview. Production delegates to the existing M5 pipeline and
pinned Easel renderer. It does not approve copy or publish. A matching QC-
passed run is reused by input digest.

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


def _input_digest(project: Path, *, assets_dir: Path | None = None) -> str:
    """Hash declared production inputs, including local files named by assets."""
    local_source_ids: set[str] = set()
    source_files: list[tuple[str, str]] = []
    normalized_assets_manifest: bytes | None = None
    assets_path = project / "sources" / "assets.json"
    if assets_dir is not None:
        for source in sorted(Path(assets_dir).expanduser().rglob("*"),
                             key=lambda p: p.as_posix().casefold()):
            if (not source.is_file() or source.is_symlink()
                    or source.suffix.casefold() not in {
                        ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov",
                        ".webm", ".mkv", ".m4v",
                    }):
                continue
            source_hash = _hash_file(source)
            source_relative = source.relative_to(assets_dir).as_posix()
            source_files.append((source_relative, source_hash))
            local_source_ids.add(f"user-{source_hash[:16]}")
        try:
            manifest = json.loads(assets_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            manifest = {
                "schema": "contentops.m5-assets/v1",
                "policy": "User-provided media is local-preview-only until separately rights-cleared.",
                "assets": [],
            }
        if not isinstance(manifest, dict):
            manifest = {
                "schema": "contentops.m5-assets/v1",
                "policy": "User-provided media is local-preview-only until separately rights-cleared.",
                "assets": [],
            }
        rows = manifest.get("assets") if isinstance(manifest, dict) else None
        if not isinstance(rows, list):
            rows = []
        manifest["assets"] = [
            row for row in rows
            if not (isinstance(row, dict)
                    and row.get("permission") == "USER_PROVIDED_LOCAL"
                    and (row.get("id") in local_source_ids
                         or row.get("derived_from_asset_id") in local_source_ids))
        ]
        normalized_assets_manifest = (
            json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n"
        ).encode("utf-8")
    candidates = [
        project / "project.yaml",
        project / "00_brief" / "brief.json",
        project / "00_brief" / "evidence-pack.json",
        project / "00_brief" / "source-permissions.json",
        project / "script" / "lines.json",
        project / "script" / "claim-map.json",
        project / "script" / "asset-map.json",
        project / "script" / "script.json",
        project / "script" / "claims.json",
        project / "sources" / "assets.json",
        project / "sources" / "source-refs.json",
        ROOT / "runtime" / "easel.lock.json",
    ]
    if assets_path.is_file():
        try:
            assets = json.loads(assets_path.read_text(encoding="utf-8")).get("assets", [])
        except (OSError, ValueError, TypeError):
            assets = []
        for asset in assets:
            if (assets_dir is not None and isinstance(asset, dict)
                    and asset.get("permission") == "USER_PROVIDED_LOCAL"
                    and (asset.get("id") in local_source_ids
                         or asset.get("derived_from_asset_id") in local_source_ids)):
                continue
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
            if path.resolve() == assets_path.resolve() and normalized_assets_manifest is not None:
                digest.update(hashlib.sha256(normalized_assets_manifest).hexdigest().encode("ascii"))
            else:
                digest.update(_hash_file(path).encode("ascii"))
        else:
            if path == assets_path and normalized_assets_manifest is not None:
                digest.update(hashlib.sha256(normalized_assets_manifest).hexdigest().encode("ascii"))
            else:
                digest.update(b"MISSING")
        digest.update(b"\n")
    for relative, source_hash in source_files:
        digest.update(b"USER_ASSET\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source_hash.encode("ascii"))
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
    visual_path = project / "receipts" / "visual-gate.json"
    if not video.is_file() or not report_path.is_file() or not visual_path.is_file():
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
        visual = json.loads(visual_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    contact_sheet_ref = visual.get("contact_sheet")
    contact_sheet = project / "receipts" / "visual-contact-sheet.png"
    if (report.get("overall") != "PASS"
            or report.get("graded_target") != f"project://final/{project.name}.mp4"
            or receipt.get("video_sha256") != _hash_file(video)
            or visual.get("video_sha256") != _hash_file(video)
            or visual.get("state") not in {"PASS", "WARN"}
            or contact_sheet_ref != "project://receipts/visual-contact-sheet.png"
            or not contact_sheet.is_file()):
        return None
    receipt["visual_qc"] = visual.get("state")
    return receipt


def _run_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: receipt.get(key) for key in (
        "run_id", "task_id", "state", "started_at", "finished_at",
        "elapsed_seconds", "reused", "video_sha256", "stage_timings_seconds",
    ) if key in receipt}


def _prepare_brief_inputs(project: Path, *, mode: str) -> dict[str, Any] | None:
    """Draft and bridge a brief-driven AUTO project when M5 input is absent.

    This only runs when the project has a brief and neither M5 contract file is
    present. Existing M5 scripts are never rewritten by this preparation path.
    Rights, source quotes and placement-to-asset mappings remain enforced by
    the existing draft and bridge validators.
    """
    brief = project / "00_brief" / "brief.json"
    if not brief.is_file():
        return None
    m5_script = project / "script" / "script.json"
    m5_claims = project / "script" / "claims.json"
    if m5_script.is_file() or m5_claims.is_file():
        if m5_script.is_file() and m5_claims.is_file():
            return {"state": "EXISTING_M5_INPUT", "written": []}
        raise m5_production.M5Blocked(
            "brief preparation: script/script.json and script/claims.json must either "
            "both exist or both be absent; existing partial M5 input was left untouched")

    from contentops.script import ScriptBlocked, build as build_draft, write as write_draft
    from contentops.script.m5_bridge import BridgeBlocked, build as build_bridge, write as write_bridge

    preview = mode == "AUTO"
    draft_lines = project / "script" / "lines.json"
    draft_claims = project / "script" / "claim-map.json"
    if draft_lines.is_file() != draft_claims.is_file():
        raise m5_production.M5Blocked(
            "brief preparation: script/lines.json and script/claim-map.json must either "
            "both exist or both be absent; existing partial draft was left untouched")
    written: list[str] = []
    try:
        if not draft_lines.is_file():
            draft = build_draft(project, root=ROOT,
                                allow_unapproved_preview=preview)
            written.extend(path.relative_to(project).as_posix()
                           for path in write_draft(draft).values())
        converted = build_bridge(project, repo_root=ROOT,
                                 allow_unapproved_preview=preview)
        written.extend(path.relative_to(project).as_posix()
                       for path in write_bridge(converted, project).values())
    except (ScriptBlocked, BridgeBlocked) as exc:
        code = getattr(exc, "code", type(exc).__name__)
        detail = getattr(exc, "detail", str(exc))
        blockers = getattr(exc, "blockers", [])
        suffix = "; ".join(str(item) for item in blockers[:6])
        raise m5_production.M5Blocked(
            f"brief preparation [{code}]: {detail}"
            + (f"; {suffix}" if suffix else "")) from None
    return {"state": "PREPARED_FOR_LOCAL_PREVIEW" if preview else "PREPARED",
            "preview_only": bool(converted.get("preview_only")),
            "written": written,
            "lines": converted.get("counts", {}).get("lines", 0),
            "claims": converted.get("counts", {}).get("claims", 0)}


def _record_brief_preparation_failure(project: Path, mode: str,
                                      error: m5_production.M5Blocked,
                                      started_at: str, started_clock: float) -> None:
    """Keep a failed AUTO preparation attempt in the normal run receipt."""
    receipt_path = project / "receipts" / RECEIPT
    previous: dict[str, Any] = {}
    if receipt_path.is_file():
        try:
            value = json.loads(receipt_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                previous = value
        except (OSError, ValueError):
            pass
    history = list(previous.get("runs") or [])
    prior_run_id = previous.get("run_id")
    if prior_run_id and not any(item.get("run_id") == prior_run_id for item in history
                                if isinstance(item, dict)):
        history.append(_run_summary(previous))
    finished = _now()
    elapsed = round(time.monotonic() - started_clock, 3)
    digest = _input_digest(project)
    failure = {
        "schema": "contentops.produce-video/v1",
        "run_id": str(uuid.uuid4()), "task_id": digest,
        "project": (_relative_to_root(project).as_posix()
                    if _relative_to_root(project) else str(project)),
        "input_sha256": digest, "runs": history, "mode": mode,
        "state": "BLOCKED", "started_at": started_at,
        "finished_at": finished, "elapsed_seconds": elapsed,
        "reused": False, "rendered": False, "technical_qc": "NOT_RUN",
        "production_ready": False, "external_provider_calls": 0,
        "external_cost": 0,
        "external_cost_reason": "brief preparation stopped before provider calls",
        "human_review": "PENDING_FOUNDER_REVIEW",
        "copy_review_required_for_render": mode != "AUTO",
        "brief_preparation": {"state": "BLOCKED",
                              "failure_reason": str(error)[:1000]},
        "failure_type": type(error).__name__,
        "failure_reason": str(error)[:1000], "published": False,
    }
    failure["runs"].append(_run_summary(failure))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")


def produce(project: Path, *, force: bool = False, mode: str = "AUTO",
            assets_dir: Path | None = None) -> dict[str, Any]:
    mode = mode.upper()
    if mode not in {"AUTO", "REVIEW", "STRICT"}:
        raise ValueError("mode must be AUTO, REVIEW, or STRICT")
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    project_relative = _relative_to_root(project)
    if not project.is_dir() or project_relative is None:
        raise ValueError("--project must be an existing project inside this repository")
    if assets_dir is not None:
        from contentops.media.local_assets import LocalAssetError, import_local_assets
        try:
            import_local_assets(assets_dir, project, repo_root=ROOT)
        except LocalAssetError as exc:
            raise m5_production.M5Blocked(f"user asset import: {exc}") from None
    prepare_started_at, prepare_started_clock = _now(), time.monotonic()
    try:
        brief_preparation = _prepare_brief_inputs(project, mode=mode)
    except m5_production.M5Blocked as exc:
        _record_brief_preparation_failure(project, mode, exc,
                                          prepare_started_at, prepare_started_clock)
        raise
    digest = _input_digest(project, assets_dir=assets_dir)
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
                      "visual_qc": prior.get("visual_qc"),
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
        # The receipt scanner permits a task identifier only when it is a
        # one-way content digest; short digest prefixes look like provider IDs.
        "task_id": digest,
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
        "brief_preparation": brief_preparation,
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
        build_options = {"require_copy_review": mode != "AUTO"}
        if assets_dir is not None:
            build_options["assets_dir"] = assets_dir
        m5_run = m5_production.build(project, **build_options)
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
                        "visual_qc": (m5_run.get("stages", {}).get("visual_qc", {})
                                      .get("state", "NOT_RUN")),
                        "production_ready": False})
    except m5_production.M5Blocked as exc:
        receipt.update({"state": "BLOCKED", "failure_type": type(exc).__name__,
                        "failure_reason": str(exc)[:1000]})
        video = project / "final" / f"{project.name}.mp4"
        visual_path = project / "receipts" / "visual-gate.json"
        if video.is_file():
            receipt["video_sha256"] = _hash_file(video)
            receipt["rendered"] = True
        if visual_path.is_file():
            try:
                visual = json.loads(visual_path.read_text(encoding="utf-8"))
                receipt["visual_qc"] = visual.get("state", "BLOCKED")
                receipt["visual_qc_receipt"] = visual_path.name
            except (OSError, ValueError):
                pass
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
    parser.add_argument("--project", required=True,
                        help="project under projects/; AUTO can prepare missing Brief-driven script/M5 inputs")
    parser.add_argument("--mode", default="AUTO", choices=("AUTO", "REVIEW", "STRICT"),
                        help="AUTO runs authorized M5 stages; REVIEW/STRICT also require a recorded copy approval")
    parser.add_argument("--force", action="store_true", help="rerun even when the same inputs already passed QC")
    parser.add_argument("--assets", default=None,
                        help="explicit local image/video folder; imported media is local-preview-only")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = produce(Path(args.project), force=args.force, mode=args.mode,
                         assets_dir=(Path(args.assets).expanduser().resolve()
                                     if args.assets else None))
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
