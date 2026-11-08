#!/usr/bin/env python3
"""Account-scoped Huashu Art Motion adapter for visual-support clips.

Rendering is guarded by the ContentOps skill grant and current Copy Review.
The output is registered as GENERATED_VIDEO / VISUAL_SUPPORT only; the clip can
never support or replace a factual claim. This adapter does not run M5 or Easel.
After the new asset is fingerprinted, a human must review the updated copy/map
before the normal M5 -> Easel entry point can continue.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from process_utils import hidden_run, python_executable  # noqa: E402
import skill_route  # noqa: E402
from contentops.media.image_contract import AssetKind, AssetRegistry, EvidenceUse  # noqa: E402
from contentops.media.media_envelope import (  # noqa: E402
    HUMAN_REVIEW_PENDING,
    TECHNICAL_PASS,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.motion_sample import check_motion_sample  # noqa: E402
from contentops.media.huashu_runtime import find_runtime  # noqa: E402
from contentops.media.quality_gate import AssetQualityGate, build_manifest  # noqa: E402
from contentops.skills.authorization import ExecutionRequest, evaluate  # noqa: E402
from contentops.skills.execution_gate import execute  # noqa: E402
from contentops.skills.grant_source import GrantSourceError, load_grant  # noqa: E402
from contentops.workflow import copy_review  # noqa: E402

SKILL_ID = "x-superplay-huashu-motion"
SKILL_VERSION = "0.1.0"
UPSTREAM_SKILL = "huashu-art-motion"
UPSTREAM_VERSION = "1.2.0"
ACCOUNTS = ("x-superplay-1024", "x-superplay-future-intelligence")
OWNER_ENV = "CONTENTOPS_OWNER_IDENTITIES"
SUBJECT_ENV = "CONTENTOPS_EXECUTION_SUBJECT"
SCHEMA = "contentops.huashu-motion-receipt/v1"
ASSET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _project_path(value: str) -> Path:
    candidate = Path(value)
    project = (candidate if candidate.is_absolute() else ROOT / candidate).resolve()
    projects_root = (ROOT / "projects").resolve()
    try:
        relative = project.relative_to(projects_root)
    except ValueError:
        raise ValueError("PROJECT_OUTSIDE_REPO: expected projects/<slug>") from None
    if len(relative.parts) != 1:
        raise ValueError("PROJECT_INVALID: expected one project directory under projects/")
    if not project.is_dir():
        raise ValueError("PROJECT_MISSING: project directory does not exist")
    return project


def _project_account(project: Path) -> str:
    config = project / "project.yaml"
    if not config.is_file():
        raise ValueError("ACCOUNT_SLUG_MISSING: project.yaml is missing; refusing to infer account from directory name")
    text = config.read_text(encoding="utf-8")
    match = re.search(r"^account_slug:\s*[\"']?([A-Za-z0-9_-]+)", text, re.M)
    if not match:
        raise ValueError("ACCOUNT_SLUG_MISSING: project.yaml declares no account_slug")
    account = match.group(1)
    if account not in ACCOUNTS:
        raise ValueError(f"ACCOUNT_OUT_OF_SCOPE: {account} is not in {', '.join(ACCOUNTS)}")
    return account


def _runtime() -> Dict[str, Any]:
    try:
        skill_root = find_runtime(ROOT)
    except FileNotFoundError as exc:
        raise ValueError(f"RUNTIME_MISSING: {exc}") from None
    skill_md = skill_root / "SKILL.md"
    renderer = skill_root / "scripts" / "engine" / "render.py"
    if not skill_md.is_file() or not renderer.is_file():
        raise ValueError(f"RUNTIME_MISSING: expected {skill_md} and {renderer}")
    text = skill_md.read_text(encoding="utf-8")
    version_match = re.search(r"^\s*version:\s*[\"']?([^\"'\s]+)", text, re.M)
    version = version_match.group(1) if version_match else ""
    if version != UPSTREAM_VERSION:
        raise ValueError(f"RUNTIME_VERSION_MISMATCH: installed {version!r}, expected {UPSTREAM_VERSION}")
    return {"skill_id": UPSTREAM_SKILL, "version": version,
            "skill_md_sha256": _sha(skill_md), "renderer_sha256": _sha(renderer),
            "renderer": "shared-skill/scripts/engine/render.py",
            "wrapper": "scripts/huashu_render.py"}


def _preflight(project: Path, *, require_copy_review: bool = True,
              check_execution: bool = True) -> Dict[str, Any]:
    problems: List[str] = []
    account: Optional[str] = None
    try:
        account = _project_account(project)
    except ValueError as exc:
        problems.append(str(exc))
    required = (
        "script/script.json", "script/claims.json", "script/assets.json",
        "sources/source-refs.json", "sources/assets.json",
    )
    for relative in required:
        if not (project / relative).is_file():
            problems.append(f"INPUT_MISSING:{relative}")

    review = copy_review.status(project)
    if require_copy_review and review.get("state") != "APPROVED":
        problems.append(f"COPY_REVIEW_{review.get('state', 'UNKNOWN')}")

    route: Dict[str, Any] = {"verdict": "BLOCKED", "reason": "ACCOUNT_SLUG_MISSING"}
    if account:
        route = skill_route.resolve_capability(
            SKILL_ID, account=account, pipeline="M5", stage="motion")
        if check_execution and route.get("verdict") != "RESOLVABLE":
            problems.append(f"SKILL_ROUTE_{route.get('reason', 'BLOCKED')}")
    runtime = _runtime()
    if account and check_execution:
        entry = next((item for item in skill_route.registry_entries()
                      if item.get("id") == SKILL_ID), None)
        request = ExecutionRequest(
            request_id=f"{project.name}-huashu-preflight", skill_id=SKILL_ID,
            skill_version=SKILL_VERSION, account=account, pipeline="M5",
            stage="motion", operations=("render",), subject=_subject())
        try:
            grant = load_grant(project, owner_identities=_owners())
        except GrantSourceError as exc:
            problems.append(f"EXECUTION_{exc.code}: {exc.detail}")
        else:
            decision = evaluate(request, verdict=route, registry_entry=entry, grant=grant)
            if decision.state != "AUTHORIZED":
                problems.append(f"EXECUTION_{decision.reason}: {decision.detail}")
    return {"account_id": account, "state": "BLOCKED" if problems else "READY",
            "problems": problems, "copy_review": review,
            "skill_route": route, "runtime": runtime}


def _read_json(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"INVALID_JSON_OBJECT:{path.relative_to(ROOT).as_posix()}")
    return payload


def _validate_spec(project: Path, value: str) -> tuple[Path, Dict[str, Any]]:
    candidate = (project / value).resolve()
    try:
        candidate.relative_to(project.resolve())
    except ValueError:
        raise ValueError("SPEC_PATH_ESCAPE: spec must stay inside the project") from None
    if not candidate.is_file():
        raise ValueError(f"SPEC_MISSING:{candidate.relative_to(project).as_posix()}")
    spec = _read_json(candidate)
    if not (2.0 <= float(spec.get("duration") or 0.0) <= 8.0):
        raise ValueError("SPEC_DURATION: motion clips must be 2-8 seconds")
    if (spec.get("width"), spec.get("height"), spec.get("fps")) != (1080, 1920, 30):
        raise ValueError("SPEC_FORMAT: expected 1080x1920 at 30 fps")
    if not isinstance(spec.get("cues"), list) or not spec["cues"]:
        raise ValueError("SPEC_CUES: at least one animation cue is required")
    # Permit one registered still image as evidence-led visual support. The
    # image must resolve to the exact asset path and bytes recorded in the M5
    # manifest; frame sequences, remote URLs, data URLs and character packs
    # remain outside this adapter's approved source-media contract.
    source = spec.get("contentops_source")
    images = [cue.get("image") for cue in spec.get("cues", [])
              if isinstance(cue, dict) and cue.get("image")]
    if images:
        if len(images) != 1 or not isinstance(source, dict):
            raise ValueError("SPEC_SOURCE_MEDIA: one image requires a registered contentops_source anchor")
        asset_id = str(source.get("asset_id") or "")
        expected_sha = str(source.get("sha256") or "")
        if not asset_id or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
            raise ValueError("SPEC_SOURCE_MEDIA: asset_id and sha256 are required")
        manifest_path = project / "sources" / "assets.json"
        if not manifest_path.is_file():
            raise ValueError("SPEC_SOURCE_MEDIA: sources/assets.json is missing")
        manifest = _read_json(manifest_path)
        row = next((item for item in manifest.get("assets", [])
                    if str(item.get("id")) == asset_id), None)
        from contentops.media.local_assets import is_valid_local_preview_asset
        local_preview = bool(row and str(row.get("type") or "").upper()
                             == "USER_PROVIDED_IMAGE"
                             and is_valid_local_preview_asset(row, project, ROOT))
        if not row:
            raise ValueError("SPEC_SOURCE_MEDIA: anchor is not a registered real screenshot or imported user image")
        if (str(row.get("type") or "").upper() not in
                ("REAL_SCREENSHOT", "SCREENSHOT", "CODE_SNAPSHOT")
                and not local_preview):
            raise ValueError("SPEC_SOURCE_MEDIA: anchor is not a registered source screenshot, "
                             "code snapshot, or imported user image")
        if (str(row.get("permission") or "").upper() not in ("CREATED_BY_OWNER", "USER_PROVIDED")
                and not local_preview):
            raise ValueError("SPEC_SOURCE_MEDIA: screenshot permission is not recorded")
        if not str(row.get("usage_scope") or "").strip():
            raise ValueError("SPEC_SOURCE_MEDIA: screenshot usage_scope is missing")
        repo_path = str(row.get("repo_path") or "")
        if not repo_path:
            raise ValueError("SPEC_SOURCE_MEDIA: screenshot repo_path is missing")
        registered = (ROOT / repo_path).resolve()
        image_path = (candidate.parent / str(images[0])).resolve()
        try:
            image_path.relative_to(ROOT.resolve())
        except ValueError:
            raise ValueError("SPEC_SOURCE_MEDIA: image path escapes the repository") from None
        if image_path != registered:
            raise ValueError("SPEC_SOURCE_MEDIA: cue image does not match the registered asset path")
        if not image_path.is_file():
            raise ValueError("SPEC_SOURCE_MEDIA: registered screenshot is missing")
        actual_sha = _sha(image_path)
        if actual_sha != expected_sha or actual_sha != str(row.get("sha256") or ""):
            raise ValueError("SPEC_SOURCE_MEDIA: screenshot hash does not match its manifest and spec")

    def check_unsupported_media(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "image" and child:
                    # Only cue.image was accepted above. Any other image key
                    # (e.g. grammar data.image) needs a distinct rights contract.
                    if value not in spec.get("cues", []):
                        raise ValueError("SPEC_EXTERNAL_MEDIA: image requires a separate rights-reviewed asset handoff")
                elif key in ("frames", "character") and child:
                    raise ValueError(f"SPEC_EXTERNAL_MEDIA: {key} requires a separate rights-reviewed asset handoff")
                check_unsupported_media(child)
        elif isinstance(value, list):
            for child in value:
                check_unsupported_media(child)
    check_unsupported_media(spec)
    return candidate, spec


def _ffprobe(path: Path) -> Dict[str, Any]:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_frames", "-show_streams", "-show_format",
        "-select_streams", "v:0", "-show_entries",
        "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,r_frame_rate:" \
        "format=duration:frame=best_effort_timestamp_time",
        "-of", "json", str(path)], timeout=180)
    if proc.returncode != 0:
        return {"error": (proc.stderr or "ffprobe failed")[-800:]}
    try:
        raw = json.loads(proc.stdout or "{}")
    except ValueError:
        return {"error": "ffprobe returned invalid JSON"}
    stream = next((row for row in raw.get("streams", [])
                   if row.get("codec_type") == "video"), {})
    audio = any(row.get("codec_type") == "audio" for row in raw.get("streams", []))
    return {"codec_name": stream.get("codec_name"), "width": stream.get("width"),
            "height": stream.get("height"), "pix_fmt": stream.get("pix_fmt"),
            "avg_frame_rate": stream.get("avg_frame_rate"),
            "r_frame_rate": stream.get("r_frame_rate"),
            "duration_s": float((raw.get("format") or {}).get("duration") or 0.0),
            "has_audio": audio,
            "frame_timestamps": [row.get("best_effort_timestamp_time")
                                 for row in raw.get("frames", [])]}


def _technical_check(path: Path) -> Dict[str, Any]:
    probe = _ffprobe(path)
    check = check_motion_sample(path, probe=probe)
    if check.get("state") != "TECHNICALLY_CHECKED":
        raise ValueError(f"MOTION_SAMPLE_BLOCKED:{check.get('reason')}")
    decode = hidden_run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], timeout=600)
    if decode.returncode != 0 or (decode.stderr or "").strip():
        raise ValueError(f"FULL_DECODE_FAILED:{(decode.stderr or '')[-800:]}")
    black = hidden_run(["ffmpeg", "-hide_banner", "-i", str(path), "-vf",
                        "blackdetect=d=0.033:pix_th=0.10", "-an", "-f", "null", "-"],
                       timeout=600)
    segments = [line.strip() for line in (black.stderr or "").splitlines()
                if "black_start:" in line]
    if black.returncode != 0 or segments:
        raise ValueError("BLACK_FRAME_CHECK_FAILED: " + "; ".join(segments[:6]))
    return {"sample_check": check, "probe": probe, "full_decode": "PASS",
            "black_frame_segments": []}


def _register(project: Path, account: str, asset_id: str, placement_id: str,
              line: Dict[str, Any], claim: Dict[str, Any], spec_path: Path,
              spec: Dict[str, Any], output: Path, runtime: Dict[str, Any],
              technical: Dict[str, Any]) -> Dict[str, Any]:
    digest = _sha(output)
    inputs = {
        "script": _sha(project / "script" / "script.json"),
        "claims": _sha(project / "script" / "claims.json"),
        "source_refs": _sha(project / "sources" / "source-refs.json"),
        "spec": _sha(spec_path),
    }
    fingerprint = _motion_fingerprint(inputs, runtime, placement_id)
    rel_output = output.relative_to(ROOT).as_posix()
    receipt_path = project / "receipts" / f"huashu-{asset_id}.json"
    sidecar = output.with_suffix(output.suffix + ".receipt.json")
    receipt: Dict[str, Any] = {
        "schema": "contentops.video-receipt/v1",
        "adapter_schema": SCHEMA,
        "run_id": f"{project.name}-{asset_id}-{fingerprint[:12]}",
        "created_at": _now(),
        "status": "TECHNICALLY_CHECKED",
        "engine": UPSTREAM_SKILL,
        "skill_version": runtime["version"],
        "adapter_version": SKILL_VERSION,
        "account_id": account,
        "placement_id": placement_id,
        "asset_id": asset_id,
        "claim_id": line.get("claim"),
        "claim_text_sha256": hashlib.sha256(
            str(claim.get("text") or "").encode("utf-8")).hexdigest(),
        "input_sha256": inputs,
        "fingerprint": fingerprint,
        "command": [python_executable(), "scripts/huashu_render.py", "--spec",
                    spec_path.relative_to(project).as_posix(), "--out",
                    output.relative_to(project).as_posix()],
        "output": {"path": f"project://{output.relative_to(project).as_posix()}",
                   "repo_path": rel_output, "output_sha256": digest},
        "generated": True,
        "evidence_capable": False,
        "evidence_use": "VISUAL_SUPPORT",
        "source_lineage": {"script": "project://script/script.json",
                           "claims": "project://script/claims.json",
                           "source_refs": "project://sources/source-refs.json",
                           "source_claims_remain_separate": True},
        "runtime": runtime,
        "render_exit_code": 0,
        "technical_qc": {"approved": True, "reasons": [], **technical},
        "human_review": HUMAN_REVIEW_PENDING,
        "production_ready": False,
        "publish_authorized": False,
        "note": "Huashu output is explanatory visual support; it does not establish or replace any source claim.",
    }
    _write_json(receipt_path, receipt)
    _write_json(sidecar, receipt)

    registry = AssetRegistry()
    registry.register(asset_id=asset_id, kind=AssetKind.GENERATED_VIDEO,
                      path=f"project://{output.relative_to(project).as_posix()}",
                      evidence_use=EvidenceUse.VISUAL_SUPPORT,
                      receipt_ref=f"{output.name}.receipt.json", sha256=digest,
                      notes={"adapter": SKILL_ID, "placement_id": placement_id})
    registry.assert_evidence_boundary()

    # M4.5 uses its existing envelope, quality gate and manifest. Technical
    # success remains pending human review, and one explicit placement is active.
    envelope = MediaAssetEnvelope(
        asset_id=asset_id, modality=MediaModality.VIDEO,
        path=f"project://{output.relative_to(project).as_posix()}",
        sha256=digest, receipt_ref=sidecar.name,
        fingerprint=fingerprint, asset_kind=AssetKind.GENERATED_VIDEO,
        generated=True, evidence_capable=False,
        evidence_use=EvidenceUse.VISUAL_SUPPORT, claim_refs=[],
        technical_status=TECHNICAL_PASS, human_review=HUMAN_REVIEW_PENDING,
        production_ready=False, placement_id=placement_id)
    gate = AssetQualityGate().evaluate(envelope, repo_root=ROOT, project_root=project)
    if gate.blocked:
        raise ValueError("M45_ASSET_GATE_BLOCKED: " + "; ".join(gate.reasons))
    manifest = build_manifest(
        [envelope], [gate],
        notes={"source": "Huashu Art Motion local code render",
               "production_ready": False, "human_review": HUMAN_REVIEW_PENDING})
    manifest_path = project / "work" / "m45" / "huashu-media-manifest.json"
    manifest.write(manifest_path)
    receipt["m45"] = {"manifest": f"project://{manifest_path.relative_to(project).as_posix()}",
                      "fingerprint": manifest.fingerprint(),
                      "gate_state": gate.state}

    # M5's source inventory receives the generated file as visual support only.
    sources_path = project / "sources" / "assets.json"
    sources = _read_json(sources_path)
    assets = list(sources.get("assets") or [])
    entry = {"id": asset_id, "type": "GENERATED_VIDEO", "repo_path": rel_output,
             "sha256": digest, "permission": "CREATED_BY_OWNER",
             "usage_scope": "VISUAL_SUPPORT only",
             "origin": "huashu-art-motion local code render",
             "notes": "Generated visual; not source evidence. Claim source remains separately registered."}
    replaced = False
    for index, old in enumerate(assets):
        if old.get("id") == asset_id:
            if old.get("repo_path") != rel_output:
                raise ValueError(f"ASSET_ID_COLLISION:{asset_id} points to another path")
            assets[index] = {**old, **entry}
            replaced = True
            break
    if not replaced:
        assets.append(entry)
    sources["assets"] = assets
    _write_json(sources_path, sources)

    script_assets_path = project / "script" / "assets.json"
    script_assets = _read_json(script_assets_path)
    mapped = script_assets.get("assets")
    if not isinstance(mapped, dict):
        raise ValueError("SCRIPT_ASSET_MAP_INVALID: expected script/assets.json assets object")
    mapped[asset_id] = {"path": f"project://{output.relative_to(project).as_posix()}",
                        "sha256": digest, "evidence_use": "VISUAL_SUPPORT",
                        "generated": True}
    script_assets["assets"] = mapped
    _write_json(script_assets_path, script_assets)
    receipt["asset_registry"] = {"type": "GENERATED_VIDEO",
                                 "evidence_use": "VISUAL_SUPPORT",
                                 "evidence_capable": False}
    receipt["copy_review_after_asset_map"] = copy_review.status(project)
    _write_json(receipt_path, receipt)
    _write_json(sidecar, receipt)
    return receipt


def _motion_fingerprint(inputs: Dict[str, str], runtime: Dict[str, Any],
                        placement_id: str) -> str:
    payload = {"inputs": inputs, "runtime": runtime,
               "placement_id": placement_id}
    return hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def _cached_render(project: Path, asset_id: str, placement_id: str,
                   spec_arg: str, runtime: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a prior motion receipt only when its exact inputs and output match.

    This is called inside the managed execution callback, after the usual grant
    check. Reuse therefore avoids an unnecessary render without bypassing the
    account-scoped execution authorization.
    """
    spec_path, _spec = _validate_spec(project, spec_arg)
    script = _read_json(project / "script" / "script.json")
    claims = _read_json(project / "script" / "claims.json")
    line = next((row for row in script.get("lines", [])
                 if row.get("id") == placement_id), None)
    if not line or (line.get("motion_asset_id")
                    and line.get("motion_asset_id") != asset_id):
        return None
    claim = next((row for row in claims.get("claims", [])
                  if row.get("id") == line.get("claim")), None)
    if not claim or not claim.get("artifacts"):
        return None
    refs_path = project / "sources" / "source-refs.json"
    if not refs_path.is_file():
        return None
    inputs = {
        "script": _sha(project / "script" / "script.json"),
        "claims": _sha(project / "script" / "claims.json"),
        "source_refs": _sha(refs_path),
        "spec": _sha(spec_path),
    }
    fingerprint = _motion_fingerprint(inputs, runtime, placement_id)
    receipt_path = project / "receipts" / f"huashu-{asset_id}.json"
    if not receipt_path.is_file():
        return None
    try:
        receipt = _read_json(receipt_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    output = project / "assets" / "generated" / "huashu" / f"{asset_id}.mp4"
    technical = receipt.get("technical_qc") or {}
    expected_repo_path = output.relative_to(ROOT).as_posix()
    if (receipt.get("schema") != "contentops.video-receipt/v1"
            or receipt.get("fingerprint") != fingerprint
            or receipt.get("input_sha256") != inputs
            or receipt.get("runtime") != runtime
            or receipt.get("placement_id") != placement_id
            or receipt.get("asset_id") != asset_id
            or receipt.get("output", {}).get("repo_path") != expected_repo_path
            or not output.is_file()
            or receipt.get("output", {}).get("output_sha256") != _sha(output)
            or technical.get("approved") is not True):
        return None
    return {"receipt": receipt, "spec_path": spec_path, "spec": _spec,
            "output": output, "line": line, "claim": claim,
            "technical": technical}


def _render(project: Path, account: str, spec_arg: str, placement_id: str,
            asset_id: str, runtime: Dict[str, Any]) -> Dict[str, Any]:
    if not ASSET_ID_RE.fullmatch(asset_id):
        raise ValueError("ASSET_ID_INVALID: use a short filename-safe asset id")
    spec_path, spec = _validate_spec(project, spec_arg)
    script_doc = _read_json(project / "script" / "script.json")
    claim_doc = _read_json(project / "script" / "claims.json")
    lines = script_doc.get("lines") or []
    line = next((row for row in lines if row.get("id") == placement_id), None)
    if line is None:
        raise ValueError(f"PLACEMENT_MISSING:{placement_id}")
    if line.get("motion_asset_id") and line.get("motion_asset_id") != asset_id:
        raise ValueError("ASSET_ID_MISMATCH: script line declares another motion asset_id")
    claims = claim_doc.get("claims") or []
    claim = next((row for row in claims if row.get("id") == line.get("claim")), None)
    if not claim:
        raise ValueError("CLAIM_MISSING: placement has no matching claim ledger entry")
    if not claim.get("artifacts"):
        raise ValueError("SOURCE_LINEAGE_MISSING: claim has no source artifact references")
    project_assets = _read_json(project / "sources" / "assets.json")
    target = next((row for row in project_assets.get("assets", [])
                   if row.get("id") == asset_id), None)
    if target and str(target.get("type") or "").upper() not in ("GENERATED_VIDEO",):
        raise ValueError("ASSET_TYPE_MISMATCH: asset id is registered as a non-video asset")

    output = project / "assets" / "generated" / "huashu" / f"{asset_id}.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    proc = hidden_run([python_executable(), str(ROOT / "scripts" / "huashu_render.py"),
                       "--spec", str(spec_path), "--out", str(output)],
                      timeout=3600, cwd=str(ROOT), env=dict(os.environ, PYTHONUTF8="1",
                                                            PYTHONIOENCODING="utf-8"))
    if proc.returncode != 0 or not output.is_file():
        raise ValueError(f"RENDER_FAILED: exit={proc.returncode}; "
                         f"stdout={(proc.stdout or '')[-600:]}; stderr={(proc.stderr or '')[-600:]}")
    technical = _technical_check(output)
    receipt = _register(project, account, asset_id, placement_id, line, claim,
                        spec_path, spec, output, runtime, technical)
    manifest_path = project / "sources" / "assets.json"
    manifest = _read_json(manifest_path)
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        raise ValueError("M5_ASSET_MANIFEST_INVALID: assets must be a list")
    candidate = {"id": asset_id, "type": "generated_video",
                 "repo_path": output.relative_to(ROOT).as_posix(),
                 "sha256": _sha(output), "permission": "CREATED_BY_OWNER",
                 "evidence_capable": False, "evidence_use": "VISUAL_SUPPORT",
                 "receipt_ref": f"project://receipts/huashu-{asset_id}.json"}
    existing_index = next((index for index, row in enumerate(assets)
                           if str(row.get("id")) == asset_id), None)
    if existing_index is None:
        assets.append(candidate)
    else:
        assets[existing_index] = {**assets[existing_index], **candidate}
    _write_json(manifest_path, manifest)
    return receipt


def _owners() -> List[str]:
    return [part.strip() for part in os.environ.get(OWNER_ENV, "").split(",")
            if part.strip()]


def _subject() -> str:
    return os.environ.get(SUBJECT_ENV, "").strip()


def main(argv: Optional[Sequence[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", help="project directory under projects/<slug>")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--render", action="store_true")
    parser.add_argument("--spec", help="project-relative JSON clip spec")
    parser.add_argument("--placement-id", help="M5 script line id for this animation")
    parser.add_argument("--asset-id", help="asset id already used by the M5 script line")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--mode", choices=("AUTO", "REVIEW", "STRICT"), default="AUTO",
                        help="AUTO renders a draft with review pending; REVIEW/STRICT require copy approval")
    args = parser.parse_args(argv)

    project = _project_path(args.project)
    receipt_path = project / "receipts" / "huashu-motion-preflight.json"
    try:
        status = _preflight(
            project, require_copy_review=(args.mode != "AUTO"),
            # The managed execution gate below is the sole grant evaluation for
            # a render. Preflight still resolves the registered skill route.
            check_execution=args.preflight)
    except (OSError, ValueError) as exc:
        status = {"state": "BLOCKED", "problems": [str(exc)], "account_id": None,
                  "runtime": None}
    if args.preflight or status["state"] != "READY":
        payload = {"schema": SCHEMA, "project": project.relative_to(ROOT).as_posix(),
                   "created_at": _now(), **status, "production_ready": False,
                   "publish_authorized": False}
        _write_json(receipt_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if status["state"] == "READY" else 1

    if not (args.spec and args.placement_id and args.asset_id):
        parser.error("--render requires --spec, --placement-id and --asset-id")
    account = status["account_id"]
    entry = next((item for item in skill_route.registry_entries()
                  if item.get("id") == SKILL_ID), None)
    verdict = status["skill_route"]

    def run(operation: str, _request: ExecutionRequest) -> Dict[str, Any]:
        try:
            cached = _cached_render(project, args.asset_id, args.placement_id,
                                    args.spec, status["runtime"])
            if cached:
                rendered = _register(
                    project, account, args.asset_id, args.placement_id,
                    cached["line"], cached["claim"], cached["spec_path"],
                    cached["spec"], cached["output"], status["runtime"],
                    cached["technical"])
                rendered["reused_render"] = True
                _write_json(project / "receipts" / f"huashu-{args.asset_id}.json",
                            rendered)
                _write_json(cached["output"].with_suffix(
                    cached["output"].suffix + ".receipt.json"), rendered)
                return {"ok": True, "state": "EXECUTED", "reused": True,
                        "receipt": rendered}
            rendered = _render(project, account, args.spec, args.placement_id,
                               args.asset_id, status["runtime"])
            return {"ok": True, "state": "EXECUTED", "receipt": rendered}
        except (OSError, ValueError, KeyError) as exc:
            return {"ok": False, "state": "BLOCKED", "error": str(exc)}

    result = execute(
        ExecutionRequest(
            request_id=f"{project.name}-huashu-{args.asset_id}",
            skill_id=SKILL_ID, skill_version=SKILL_VERSION, account=account,
            pipeline="M5", stage="motion", operations=("render",), subject=_subject()),
        verdict=verdict, registry_entry=entry, project_dir=project,
        owner_identities=_owners(), executor=run)
    payload = result.as_dict()
    payload["production_ready"] = False
    payload["publish_authorized"] = False
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.executed else 1


if __name__ == "__main__":
    raise SystemExit(main())
