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
    python scripts/produce_video.py --account x-superplay-future-intelligence \
        --topic "RAG 混合检索的工作原理" --mode AUTO
    python scripts/produce_video.py --account x-superplay-1024 \
        --source-url https://github.com/Xander-Xai/X-SuperPlay-ContentOps --mode AUTO
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
RAW_DRAFT_VERSION = "raw-draft-v7"


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


def _input_digest(project: Path, *, assets_dir: Path | None = None,
                  narration_provider: str | None = None,
                  narration_audio: Path | None = None,
                  narration_receipt: Path | None = None,
                  narration_voice: str | None = None,
                  narration_model: str | None = None,
                  temporary_narration_voice: bool = False,
                  cost_budget_cny: float = 0.0,
                  avatar_provider: str | None = None,
                  avatar_assets_dir: Path | None = None,
                  avatar_quota_budget: str | None = None,
                  avatar_intro_line: str | None = None,
                  avatar_outro_line: str | None = None,
                  avatar_intro_video: Path | None = None,
                  avatar_outro_video: Path | None = None) -> str:
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
    runtime_options = {
        "narration_provider": narration_provider,
        "narration_audio_sha256": _hash_file(narration_audio) if narration_audio and narration_audio.is_file() else None,
        "narration_receipt_sha256": _hash_file(narration_receipt) if narration_receipt and narration_receipt.is_file() else None,
        "narration_voice": narration_voice,
        "narration_model": narration_model,
        "temporary_narration_voice": bool(temporary_narration_voice),
        "cost_budget_cny": str(cost_budget_cny),
        "avatar_provider": avatar_provider,
        "avatar_quota_budget": avatar_quota_budget,
        "avatar_intro_line": avatar_intro_line,
        "avatar_outro_line": avatar_outro_line,
        "avatar_intro_video_sha256": _hash_file(avatar_intro_video) if avatar_intro_video and avatar_intro_video.is_file() else None,
        "avatar_outro_video_sha256": _hash_file(avatar_outro_video) if avatar_outro_video and avatar_outro_video.is_file() else None,
    }
    digest.update(b"PRODUCTION_OPTIONS\0")
    digest.update(json.dumps(runtime_options, sort_keys=True, separators=(",", ":"))
                  .encode("utf-8"))
    if avatar_assets_dir is not None:
        manifest_path = avatar_assets_dir.expanduser().resolve() / "asset-manifest.json"
        digest.update(b"AVATAR_ASSETS\0")
        digest.update(_hash_file(manifest_path).encode("ascii") if manifest_path.is_file() else b"MISSING")
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                asset_ids = {manifest.get("primary", {}).get("presenter_reference"),
                             manifest.get("primary", {}).get("voice_reference")}
                rows = [row for row in manifest.get("assets", [])
                        if isinstance(row, dict) and row.get("asset_id") in asset_ids]
                for row in rows:
                    expected = str(row.get("sha256") or "").casefold()
                    selected = None
                    declared = manifest_path.parent / str(row.get("relative_path") or "")
                    for candidate in ([declared] if declared.is_file() else
                                      manifest_path.parent.rglob("*")):
                        if candidate.is_file() and not candidate.is_symlink() and _hash_file(candidate).casefold() == expected:
                            selected = candidate
                            break
                    digest.update(str(row.get("asset_id")).encode("utf-8"))
                    digest.update(b"\0")
                    digest.update((_hash_file(selected).encode("ascii") if selected else b"MISSING"))
                    digest.update(b"\n")
            except (OSError, ValueError, TypeError):
                digest.update(b"AVATAR_REFERENCE_HASHES_UNREADABLE")
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


def _prepare_brief_inputs(project: Path, *, mode: str,
                          refresh_local_assets: bool = False) -> dict[str, Any] | None:
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
    raw_receipt = project / "receipts" / "raw-inputs.json"
    draft_marker = project / "script" / "source-pack.sha256"
    current_pack = project / "00_brief" / "evidence-pack.json"
    expected_marker = (hashlib.sha256(current_pack.read_bytes()).hexdigest()
                       + " " + RAW_DRAFT_VERSION) if current_pack.is_file() else ""
    raw_draft_stale = bool(raw_receipt.is_file() and expected_marker and (
        not draft_marker.is_file()
        or draft_marker.read_text(encoding="utf-8").strip() != expected_marker
        or refresh_local_assets))
    if m5_script.is_file() or m5_claims.is_file():
        if m5_script.is_file() and m5_claims.is_file() and not raw_draft_stale:
            return {"state": "EXISTING_M5_INPUT", "written": []}
        if not (m5_script.is_file() and m5_claims.is_file() and raw_draft_stale):
            raise m5_production.M5Blocked(
                "brief preparation: script/script.json and script/claims.json must either "
                "both exist or both be absent; existing partial M5 input was left untouched")
        review_path = project / "receipts" / "script-review.json"
        if review_path.is_file():
            try:
                review = json.loads(review_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                review = {}
            if review.get("status") == "APPROVED":
                raise m5_production.M5Blocked(
                    "brief preparation: the existing raw draft has an approval receipt; "
                    "create a new run to revise it")

    from contentops.script import ScriptBlocked, build as build_draft, write as write_draft
    from contentops.script.m5_bridge import BridgeBlocked, build as build_bridge, write as write_bridge

    # REVIEW is a request to inspect a locally rendered draft. It therefore
    # must allow the draft to be assembled; STRICT remains the explicit
    # pre-render copy approval mode. Publication always stays separate.
    preview = mode in {"AUTO", "REVIEW"}
    raw_receipt = project / "receipts" / "raw-inputs.json"
    if raw_receipt.is_file():
        import raw_video_inputs
        raw_video_inputs.bind_existing_source_scope(project)
    draft_lines = project / "script" / "lines.json"
    draft_claims = project / "script" / "claim-map.json"
    raw_receipt = project / "receipts" / "raw-inputs.json"
    draft_pack_marker = project / "script" / "source-pack.sha256"
    current_pack = project / "00_brief" / "evidence-pack.json"
    refresh_raw_draft = bool(
        raw_receipt.is_file() and current_pack.is_file()
        and (not draft_pack_marker.is_file()
             or draft_pack_marker.read_text(encoding="utf-8").strip()
             != (hashlib.sha256(current_pack.read_bytes()).hexdigest()
                 + " " + RAW_DRAFT_VERSION)
             or refresh_local_assets)
    )
    if draft_lines.is_file() != draft_claims.is_file():
        raise m5_production.M5Blocked(
            "brief preparation: script/lines.json and script/claim-map.json must either "
            "both exist or both be absent; existing partial draft was left untouched")
    written: list[str] = []
    try:
        if not draft_lines.is_file() or refresh_raw_draft:
            draft = build_draft(project, root=ROOT,
                                allow_unapproved_preview=preview)
            written.extend(path.relative_to(project).as_posix()
                           for path in write_draft(draft).values())
            if raw_receipt.is_file() and current_pack.is_file():
                draft_pack_marker.write_text(
                    hashlib.sha256(current_pack.read_bytes()).hexdigest()
                    + " " + RAW_DRAFT_VERSION + "\n",
                    encoding="utf-8")
        if raw_receipt.is_file() and (refresh_raw_draft
                                      or not (project / "script" / "asset-map.json").is_file()):
            import raw_video_inputs
            raw_video_inputs.prepare_m5_contracts(project)
            written.extend(("00_brief/source-permissions.json", "sources/assets.json",
                            "script/asset-map.json"))
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
        "copy_review_required_for_render": mode == "STRICT",
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
            assets_dir: Path | None = None,
            narration_provider: str | None = None,
            narration_audio: Path | None = None,
            narration_receipt: Path | None = None,
            narration_voice: str | None = None,
            narration_model: str = "speech-2.8-hd",
            temporary_narration_voice: bool = False,
            cost_budget_cny: float = 0.0,
            avatar_provider: str | None = None,
            avatar_assets_dir: Path | None = None,
            avatar_quota_budget: str | None = None,
            avatar_intro_line: str | None = None,
            avatar_outro_line: str | None = None,
            avatar_intro_video: Path | None = None,
            avatar_outro_video: Path | None = None) -> dict[str, Any]:
    mode = mode.upper()
    if mode not in {"AUTO", "REVIEW", "STRICT"}:
        raise ValueError("mode must be AUTO, REVIEW, or STRICT")
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    project_relative = _relative_to_root(project)
    if not project.is_dir() or project_relative is None:
        raise ValueError("--project must be an existing project inside this repository")
    try:
        project_config = m5_production._read_yaml(project / "project.yaml")
    except Exception:
        project_config = {}
    narration_profile = m5_production._resolve_narration_defaults(project_config)
    narration_provider = narration_provider or narration_profile.get("provider")
    narration_voice = narration_voice or narration_profile.get("voice")
    narration_model = narration_profile.get("model") or narration_model
    avatar_profile = m5_production._load_digital_presenter_profile(project_config)
    if avatar_profile:
        avatar_provider = avatar_provider or avatar_profile.get("provider")
        avatar_assets_dir = avatar_assets_dir or (
            ROOT / str(avatar_profile.get("asset_dir") or "assert")
        ).resolve()
        avatar_intro_line = avatar_intro_line or avatar_profile.get("intro_line")
        avatar_outro_line = avatar_outro_line or avatar_profile.get("outro_line")
    if assets_dir is not None:
        from contentops.media.local_assets import LocalAssetError, import_local_assets
        try:
            import_local_assets(assets_dir, project, repo_root=ROOT)
        except LocalAssetError as exc:
            raise m5_production.M5Blocked(f"user asset import: {exc}") from None
    if (avatar_provider or avatar_intro_video or avatar_outro_video) and avatar_assets_dir is None:
        avatar_assets_dir = ROOT / "assert"
    prepare_started_at, prepare_started_clock = _now(), time.monotonic()
    try:
        brief_preparation = _prepare_brief_inputs(
            project, mode=mode, refresh_local_assets=assets_dir is not None)
    except m5_production.M5Blocked as exc:
        _record_brief_preparation_failure(project, mode, exc,
                                          prepare_started_at, prepare_started_clock)
        raise
    digest = _input_digest(
        project, assets_dir=assets_dir,
        narration_provider=narration_provider,
        narration_audio=narration_audio,
        narration_receipt=narration_receipt,
        narration_voice=narration_voice,
        narration_model=narration_model,
        temporary_narration_voice=temporary_narration_voice,
        cost_budget_cny=cost_budget_cny,
        avatar_provider=avatar_provider,
        avatar_assets_dir=avatar_assets_dir,
        avatar_quota_budget=avatar_quota_budget,
        avatar_intro_line=avatar_intro_line,
        avatar_outro_line=avatar_outro_line,
        avatar_intro_video=avatar_intro_video,
        avatar_outro_video=avatar_outro_video,
    )
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
        "copy_review_required_for_render": mode == "STRICT",
        "brief_preparation": brief_preparation,
        "published": False,
    }
    output = project / "receipts" / RECEIPT
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        if mode == "STRICT":
            try:
                m5_production.copy_review.require_approved(project)
            except m5_production.copy_review.CopyReviewRequired as exc:
                raise m5_production.M5Blocked(f"copy review: {exc}") from None
        build_options = {"require_copy_review": mode == "STRICT"}
        if (narration_provider is not None or narration_voice is not None
                or narration_audio is not None or narration_receipt is not None
                or temporary_narration_voice or cost_budget_cny != 0.0):
            build_options.update({
                "narration_provider": narration_provider,
                "narration_audio": narration_audio,
                "narration_receipt": narration_receipt,
                "narration_voice": narration_voice,
                "narration_model": narration_model,
                "temporary_voice": temporary_narration_voice,
                "cost_budget_cny": cost_budget_cny,
            })
        if (avatar_provider is not None or avatar_intro_video is not None
                or avatar_outro_video is not None):
            build_options.update({
                "avatar_provider": avatar_provider or "minimax-h3",
                "avatar_assets_dir": avatar_assets_dir,
                "avatar_quota_budget": avatar_quota_budget,
                "avatar_intro_line": avatar_intro_line,
                "avatar_outro_line": avatar_outro_line,
                "avatar_intro_video": avatar_intro_video,
                "avatar_outro_video": avatar_outro_video,
            })
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
    parser.add_argument("--project", default="",
                        help="existing project under projects/; AUTO can prepare missing Brief-driven script/M5 inputs")
    parser.add_argument("--account", default="",
                        help="account DNA for a raw --topic/--source-url production")
    parser.add_argument("--topic", default="",
                        help="new topic; AUTO searches account-allowlisted sources when --source-url is absent")
    parser.add_argument("--source-url", action="append", default=[],
                        help="licensed public GitHub repository to pin as source evidence")
    parser.add_argument("--mode", default="AUTO", choices=("AUTO", "REVIEW", "STRICT"),
                        help="AUTO renders automatically; REVIEW renders a draft for review; STRICT requires copy approval first")
    parser.add_argument("--force", action="store_true", help="rerun even when the same inputs already passed QC")
    parser.add_argument("--assets", default=None,
                        help="explicit local image/video folder; imported media is local-preview-only")
    parser.add_argument("--narration-provider", choices=("sapi", "existing", "minimax"),
                        default=None, help="M5 narration provider; MiniMax never silently falls back")
    parser.add_argument("--narration-audio", default=None,
                        help="audio file for receipt-bound existing narration")
    parser.add_argument("--narration-receipt", default=None,
                        help="narration receipt binding an existing audio file to the current script")
    parser.add_argument("--narration-voice", default=None,
                        help="MiniMax voice ID; ordinary system voices require the temporary flag")
    parser.add_argument("--narration-model", default="speech-2.8-hd")
    parser.add_argument("--temporary-narration-voice", action="store_true",
                        help="mark a normal MiniMax voice as an audition only, not a clone")
    parser.add_argument("--cost-budget-cny", type=float, default=0.0,
                        help="task-level CNY cost ceiling; MiniMax M5 currently allows included-plan calls only")
    parser.add_argument("--avatar-provider", choices=("minimax-h3",), default=None,
                        help="generate and place MiniMax H3 presenter intro and outro")
    parser.add_argument("--avatar-assets-dir", default=None,
                        help="local-only directory with registered portrait and voice reference; defaults to assert/")
    parser.add_argument("--avatar-quota-budget", default=None,
                        help="explicit included-subscription weekly quota budget for H3 tasks")
    parser.add_argument("--avatar-intro-line", default=None)
    parser.add_argument("--avatar-outro-line", default=None)
    parser.add_argument("--avatar-intro-video", default=None,
                        help="reuse an H3 intro MP4 with its provider receipt")
    parser.add_argument("--avatar-outro-video", default=None,
                        help="reuse an H3 outro MP4 with its provider receipt")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.project:
            if args.topic or args.source_url or args.account:
                parser.error("--project cannot be combined with --account, --topic, or --source-url")
            project_path = Path(args.project)
        else:
            if not args.account or (not args.topic and not args.source_url):
                parser.error("raw production needs --account and at least one of --topic or --source-url")
            import raw_video_inputs
            try:
                project_path = raw_video_inputs.prepare_raw_project(
                    account=args.account, topic=args.topic, source_urls=args.source_url)
            except raw_video_inputs.RoutingError as exc:
                raise ValueError(str(exc)) from None
        result = produce(project_path, force=args.force, mode=args.mode,
                         assets_dir=(Path(args.assets).expanduser().resolve()
                                     if args.assets else None),
                         narration_provider=args.narration_provider,
                         narration_audio=(Path(args.narration_audio).expanduser().resolve()
                                          if args.narration_audio else None),
                         narration_receipt=(Path(args.narration_receipt).expanduser().resolve()
                                            if args.narration_receipt else None),
                         narration_voice=args.narration_voice,
                         narration_model=args.narration_model,
                         temporary_narration_voice=args.temporary_narration_voice,
                         cost_budget_cny=args.cost_budget_cny,
                         avatar_provider=args.avatar_provider,
                         avatar_assets_dir=(Path(args.avatar_assets_dir).expanduser().resolve()
                                            if args.avatar_assets_dir else None),
                         avatar_quota_budget=args.avatar_quota_budget,
                         avatar_intro_line=args.avatar_intro_line,
                         avatar_outro_line=args.avatar_outro_line,
                         avatar_intro_video=(Path(args.avatar_intro_video).expanduser().resolve()
                                             if args.avatar_intro_video else None),
                         avatar_outro_video=(Path(args.avatar_outro_video).expanduser().resolve()
                                             if args.avatar_outro_video else None))
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
