#!/usr/bin/env python3
"""Run the M5 production chain for one project and write a receipt per stage.

The chain is deliberately narrow and refuses rather than improvises:

    sources → claims → script → narration → subtitles → storyboard → compose → QC → visual QC → review

Facts come from `project.yaml` source refs and are verified against quotes in
`script/claims.json`. Narration can use the existing MiniMax M Plan Speech
Provider, receipt-bound audio, or explicitly selected offline SAPI diagnostics.
MiniMax is never replaced by SAPI after a failure. Everything else reuses the
existing MediaManifest-era storyboard contract, pinned Easel composer and QC.

Nothing here approves a video. The run always ends at
`PENDING_FOUNDER_REVIEW` with `production_ready: false`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run, python_executable  # noqa: E402

from contentops.evidence import ClaimLedger, build_artifacts  # noqa: E402
from contentops.content_kernel.handoff import (  # noqa: E402
    VIDEO,
    HandoffError,
    build_handoff,
    load_bundle_for_handoff,
    write_handoff,
)
from contentops.media.rights_gate import (  # noqa: E402
    RightsError,
    validate_declared_asset,
    validate_request_rights,
)
from contentops.workflow import copy_review  # noqa: E402

RUN_SCHEMA = "contentops.m5-run/v1"
SCRIPT_SCHEMA = "contentops.m5-script/v1"
SILENCE_SECONDS = 0.28


class M5Blocked(RuntimeError):
    """A stage refused to continue; the run records the reason."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _select_motion_backend(shot: Dict[str, Any], default: Optional[str]) -> Optional[str]:
    """Resolve per-shot MotionBackend without silently changing an explicit request."""
    selected = shot.get("motion_backend") or shot.get("backend") or default
    if selected is None:
        return None
    selected = str(selected).strip().lower()
    aliases = {"art-motion": "huashu-art-motion", "motion": "huashu-motion"}
    selected = aliases.get(selected, selected)
    if selected not in {"huashu-art-motion", "huashu-motion"}:
        raise M5Blocked(f"unsupported motion backend {selected!r}")
    return selected


def _payload_sha256(value: Dict[str, Any]) -> str:
    """Stable digest for the in-memory script passed between M5 stages."""
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


#: Where a media-use import receipt is mirrored so a clone can read it.
TRACKED_RECEIPT_DIR = Path("receipts") / "media-use"


def _mirror_import_receipt(project: Path, imported: Any) -> str:
    """Copy an adapter import receipt to a repository-tracked path.

    The adapter writes each receipt beside the asset it describes. For audio the
    skill resolves from the pinned runtime, that is ``.media/``, which this
    repository ignores — so the receipt carrying the licence and attribution could
    not be checked from a clone. The mirror keeps the same bytes (the adapter
    redacts them before writing) under ``receipts/media-use/``. The original stays
    where it is, so ``.media/manifest.jsonl`` and the adapter's own lookup are not
    disturbed, and nothing here is a second registry: these are the same receipts
    at a path this repository tracks.
    """
    source = getattr(imported, "receipt_path", None)
    reference = str(getattr(imported, "receipt_ref", "") or "")
    if not source:
        return reference
    source = Path(str(source))
    if not source.is_file():
        return reference
    directory = Path(project) / TRACKED_RECEIPT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    (directory / source.name).write_bytes(source.read_bytes())
    return (TRACKED_RECEIPT_DIR / source.name).as_posix()


def _read_yaml(path: Path) -> Dict[str, Any]:
    """Read the small subset of YAML these projects use, without a dependency."""
    try:
        import yaml  # type: ignore
    except ImportError:
        raise M5Blocked("PyYAML is required to read project.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _load_digital_presenter_profile(project_config: Dict[str, Any]) -> Dict[str, Any]:
    """Load the enabled account avatar defaults without reading private media."""
    account_slug = str(project_config.get("account_slug") or project_config.get("account_id") or "")
    if not account_slug:
        return {}
    path = ROOT / "config" / "accounts" / f"{account_slug}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    audio = payload.get("audio") if isinstance(payload, dict) else None
    profile = audio.get("digital_presenter") if isinstance(audio, dict) else None
    return profile if isinstance(profile, dict) and profile.get("enabled") is True else {}


def _load_narration_profile(project_config: Dict[str, Any]) -> Dict[str, Any]:
    """Read the account's declared voice route and alias for M5 defaults."""
    account_slug = str(project_config.get("account_slug") or project_config.get("account_id") or "")
    if not account_slug:
        return {}
    path = ROOT / "config" / "accounts" / f"{account_slug}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    audio = payload.get("audio") if isinstance(payload, dict) else None
    voice = audio.get("voice") if isinstance(audio, dict) else None
    return voice if isinstance(voice, dict) else {}


def _resolve_narration_defaults(project_config: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Translate account DNA provider hints into the normal M5 provider contract."""
    voice = _load_narration_profile(project_config)
    hint = str(voice.get("provider_hint") or "").strip()
    if not hint:
        return {"provider": None, "voice": None, "model": None}
    provider, _, model = hint.partition("/")
    provider = provider.strip().casefold()
    if provider in {"minimax_m_plan", "minimax", "minimax-speech"}:
        return {
            "provider": "minimax",
            "voice": str(voice.get("voice_alias") or "founder_primary_v1"),
            "model": model.strip() or "speech-2.8-hd",
        }
    return {"provider": provider, "voice": None, "model": model.strip() or None}


def _duration(path: Path) -> float:
    proc = hidden_run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        timeout=60,
    )
    try:
        return float((proc.stdout or "").strip())
    except ValueError:
        raise M5Blocked(f"cannot measure duration of {path}")


def _audio_sample_rate(path: Path) -> int:
    proc = hidden_run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate", "-of", "default=nw=1:nk=1", str(path)],
        timeout=60,
    )
    try:
        rate = int((proc.stdout or "").strip())
    except ValueError:
        rate = 0
    if rate <= 0:
        raise M5Blocked(f"cannot read audio sample rate of {path}")
    return rate


# --- stages -----------------------------------------------------------------


def stage_bundle(project: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    """Bind this project to a Strategy Content Bundle before any media work.

    Optional: a project without ``content_bundle`` keeps the historical path.
    When configured, an invalid Bundle or source mapping blocks the run rather
    than producing media that cannot be traced back to the Bundle.
    """
    declared = config.get("content_bundle")
    if declared is None:
        return {"state": "NOT_CONFIGURED"}
    if not isinstance(declared, dict):
        raise M5Blocked("content_bundle must be a mapping")
    path = declared.get("path")
    account = declared.get("account")
    source_map = declared.get("source_map")
    if not path or not account or not isinstance(source_map, dict) or not source_map:
        raise M5Blocked("content_bundle requires path, account and source_map")

    bundle_path = Path(str(path))
    if not bundle_path.is_absolute():
        local = (project / bundle_path).resolve()
        bundle_path = local if local.is_file() else (ROOT / bundle_path).resolve()
    try:
        bundle = load_bundle_for_handoff(bundle_path)
        handoff = build_handoff(
            bundle, str(account), VIDEO,
            project_slug=project.name,
            source_map={str(key): str(value) for key, value in source_map.items()},
            bundle_path=bundle_path,
            repo_root=ROOT,
            project_dir=project,
            platform_id=declared.get("platform"),
            registry_root=ROOT,
            host_capability=str(declared.get("host_capability") or "UNVERIFIED"),
        )
        written = write_handoff(project, handoff)
    except HandoffError as exc:
        raise M5Blocked(f"{exc.code}: {exc.detail}") from None

    # write_handoff resolves the project dir, and on Windows an 8.3 alias
    # (C:\Users\RUNNER~1\...) expands there while the caller's `project` keeps
    # the short spelling; a raw relative_to raises ValueError. os.path.normpath
    # does not expand such aliases (it is lexical only), so both sides are
    # resolved before comparing — the same policy contentops.media_paths
    # documents for runner temp directories.
    handoff_receipt = written.resolve().relative_to(
        Path(project).resolve()).as_posix()
    return {
        "state": handoff["state"],
        "bundle_id": handoff["bundle_id"],
        "bundle_sha256": handoff["bundle_sha256"],
        "handoff": handoff_receipt,
        "blockers": handoff["blockers"],
    }


SOURCE_REFS_SCHEMA = "contentops.m5-source-refs/v1"


def _declared_source_refs(project: Path, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``project.yaml`` refs plus the refs the brief bridge wrote.

    The bridge cannot edit YAML safely, so it writes the evidence it converted
    to ``sources/source-refs.json``. Both lists are one contract: the ids must
    still be unique, which ``build_artifacts`` enforces.
    """
    refs = list(config.get("source_refs") or [])
    sidecar = project / "sources" / "source-refs.json"
    if sidecar.is_file():
        document = json.loads(sidecar.read_text(encoding="utf-8"))
        if document.get("schema") != SOURCE_REFS_SCHEMA:
            raise M5Blocked(
                f"sources/source-refs.json schema is not {SOURCE_REFS_SCHEMA}")
        extra = document.get("refs")
        if not isinstance(extra, list):
            raise M5Blocked("sources/source-refs.json refs must be a list")
        refs.extend(extra)
    return refs


def stage_sources(project: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = build_artifacts(_declared_source_refs(project, config), repo_root=ROOT)
    payload = {
        "schema": "contentops.m5-sources/v1",
        "artifacts": [a.as_dict() for a in artifacts.values()],
    }
    _write_json(project / "receipts" / "source-artifacts.json", payload)
    return {"artifacts": artifacts, "count": len(artifacts)}



VISUAL_MEDIA_KINDS = {"image", "icon", "logo"}
AUDIO_MEDIA_KINDS = {"bgm", "sfx"}


def _media_volume(request: Dict[str, Any], asset_id: str, default: float) -> float:
    raw = request.get("volume", default)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise M5Blocked(f"{asset_id}: volume must be a number between 0 and 1")
    value = float(raw)
    if not 0.0 < value <= 1.0:
        raise M5Blocked(f"{asset_id}: volume must be greater than 0 and at most 1")
    return value


def _media_sfx_at(request: Dict[str, Any], asset_id: str) -> float:
    raw = request.get("at")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise M5Blocked(f"{asset_id}: an sfx request needs a numeric 'at' placement in seconds")
    value = float(raw)
    if value < 0.0:
        raise M5Blocked(f"{asset_id}: 'at' cannot be negative")
    return value


def stage_media_use(project: Path, config: Dict[str, Any], *, adapter: Any = None) -> Dict[str, Any]:
    """Resolve configured local media-use needs automatically before M5 asset validation.

    This is an optional material-source stage, NOT a second catalog or renderer.
    Already-declared M5 assets take precedence. Missing licensed visuals and
    audio beds/effects are resolved by the approved MediaUseAdapter, imported
    with their sidecars, verified, then offered to the existing M5 asset and
    storyboard path. Visual imports stay ``evidence_capable=false``; audio is a
    support track and never enters ``sources/assets.json``.
    """
    disabled = {"state": "DISABLED", "assets": {}, "audio": {"bgm": None, "sfx": []}, "count": 0}
    settings = config.get("media_use")
    if settings is None or settings is False:
        return disabled
    if not isinstance(settings, dict):
        raise M5Blocked("media_use must be a mapping")
    if settings.get("enabled") is not True:
        return disabled
    if settings.get("mode", "local-only") != "local-only":
        raise M5Blocked("media_use only supports local-only mode; network/paid use is not authorized")
    if any(settings.get(key) for key in ("allow_network", "allow_paid", "allow_cross_project_reuse")):
        raise M5Blocked("media_use cannot enable network, paid, or cross-project reuse")
    requests = settings.get("requests")
    if not isinstance(requests, list) or not requests:
        raise M5Blocked("media_use enabled requires nonempty requests")

    declared_path = project / "sources" / "assets.json"
    if not declared_path.is_file():
        raise M5Blocked("sources/assets.json is required before media_use resolution")
    declared = json.loads(declared_path.read_text(encoding="utf-8"))
    declared_assets = {str(item.get("id")): item for item in declared.get("assets", [])}
    existing = set(declared_assets)
    seen = set()
    todo = []
    results: List[Dict[str, Any]] = []
    for request in requests:
        if not isinstance(request, dict):
            raise M5Blocked("media_use request must be a mapping")
        asset_id = str(request.get("id") or "").strip()
        if not asset_id or asset_id in seen:
            raise M5Blocked("media_use request ids must be nonempty and unique")
        seen.add(asset_id)
        if asset_id in existing:
            if str(request.get("kind") or "").strip() in AUDIO_MEDIA_KINDS:
                raise M5Blocked(
                    f"{asset_id}: audio requests cannot be declared in "
                    f"sources/assets.json; declare them under media_use.requests"
                )
            try:
                validate_declared_asset(declared_assets[asset_id], project)
            except RightsError as exc:
                raise M5Blocked(f"{asset_id}: {exc}") from exc
            results.append({"id": asset_id, "state": "REUSED_DECLARED", "provider_call": False})
            continue
        kind = str(request.get("kind") or "").strip()
        intent = str(request.get("intent") or "").strip()
        if kind not in VISUAL_MEDIA_KINDS | AUDIO_MEDIA_KINDS:
            raise M5Blocked(
                f"{asset_id}: media_use in M5 accepts image/icon/logo/bgm/sfx only"
            )
        if not intent:
            raise M5Blocked(f"{asset_id}: intent is required")
        try:
            rights_info = validate_request_rights(request, project)
        except RightsError as exc:
            raise M5Blocked(f"{asset_id}: {exc}") from exc
        license_name = rights_info["license_id"]
        attribution = rights_info["attribution"]
        if kind == "bgm":
            if any(item[1] == "bgm" for item in todo):
                raise M5Blocked("a project can declare at most one bgm request")
            volume = _media_volume(request, asset_id, 0.25)
            todo.append((asset_id, kind, intent, rights_info, volume, None))
        elif kind == "sfx":
            volume = _media_volume(request, asset_id, 0.9)
            todo.append((asset_id, kind, intent, rights_info, volume,
                         _media_sfx_at(request, asset_id)))
        else:
            todo.append((asset_id, kind, intent, rights_info, None, None))

    if todo and adapter is None:
        try:
            from contentops.media.media_use_adapter import MediaUseAdapter
        except ImportError as exc:
            raise M5Blocked(
                "media-use adapter is not installed; PR #64 must be integrated before "
                "an enabled M5 media_use stage can run"
            ) from exc
        adapter = MediaUseAdapter()

    # Index existing project-local files before choosing candidates. The same
    # reviewed adapter does this offline; no manual media-use CLI pre-step needed.
    if todo:
        try:
            adapter.adopt(project_dir=project)
        except Exception as exc:
            code = getattr(exc, "code", type(exc).__name__)
            raise M5Blocked(f"media-use local adopt failed ({code}): {exc}") from exc

    discovered: Dict[str, Dict[str, Any]] = {}
    audio: Dict[str, Any] = {"bgm": None, "sfx": []}
    imported_ids: Dict[str, str] = {}
    for asset_id, kind, intent, rights_info, volume, at in todo:
        license_name = rights_info["license_id"]
        attribution = rights_info["attribution"]
        try:
            resolved = adapter.resolve(kind, intent, project_dir=project)
            if not resolved.importable:
                raise M5Blocked(f"{asset_id}: media-use returned an unimportable asset")
            imported = adapter.import_record(
                resolved.record, project_dir=project, kind=kind,
                license=license_name, attribution=attribution,
            )
            if imported.asset_id in imported_ids:
                raise M5Blocked(
                    f"{asset_id}: the same media-use asset was already imported as "
                    f"{imported_ids[imported.asset_id]}; declare one request and "
                    f"reuse its id"
                )
            imported_ids[imported.asset_id] = asset_id
            if not imported.logical_path.startswith("project://"):
                raise M5Blocked(f"{asset_id}: media-use returned a non-project asset path")
            relative = imported.logical_path[len("project://"):]
            verification = adapter.verify(
                project_dir=project, relative_path=relative,
                expected_sha256=imported.sha256,
            )
            if not verification.ok:
                raise M5Blocked(f"{asset_id}: media-use import receipt/hash verification failed")
            receipt_ref = _mirror_import_receipt(project, imported)
        except Exception as exc:
            if isinstance(exc, M5Blocked):
                raise
            code = getattr(exc, "code", None)
            if code:
                raise M5Blocked(f"{asset_id}: media-use {code}: {exc}") from exc
            raise

        resolved_path = (project / relative).resolve()
        try:
            repo_path = resolved_path.relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise M5Blocked(f"{asset_id}: imported asset lies outside this repository") from exc
        if kind in VISUAL_MEDIA_KINDS:
            discovered[asset_id] = {
                "id": asset_id, "type": "LICENSED_EXTERNAL",
                "repo_path": repo_path, "sha256": imported.sha256,
                "permission": "LICENSED", "evidence_capable": False,
                "license": license_name, "attribution": attribution,
                "rights": rights_info,
                "media_use_asset_id": imported.asset_id,
                "receipt_ref": receipt_ref,
            }
        elif kind == "bgm":
            audio["bgm"] = {
                "id": asset_id, "repo_path": repo_path,
                "sha256": imported.sha256, "volume": volume,
                "license": license_name, "attribution": attribution,
                "rights": rights_info,
                "media_use_asset_id": imported.asset_id,
                "receipt_ref": receipt_ref,
            }
        else:
            audio["sfx"].append({
                "id": asset_id, "repo_path": repo_path,
                "sha256": imported.sha256, "volume": volume, "at": at,
                "license": license_name, "attribution": attribution,
                "rights": rights_info,
                "media_use_asset_id": imported.asset_id,
                "receipt_ref": receipt_ref,
            })
        results.append({
            "id": asset_id, "state": "IMPORTED", "kind": kind,
            "source": resolved.source, "sha256": imported.sha256,
            "path": "project://" + relative, "receipt_ref": receipt_ref,
            "license": license_name, "attribution": attribution,
            "rights": rights_info,
            "evidence_capable": False, "provider_call": False,
            **({"volume": volume} if volume is not None else {}),
            **({"at": at} if at is not None else {}),
        })
    _write_json(project / "receipts" / "media-use-stage.json", {
        "schema": "contentops.m5-media-use/v1", "mode": "local-only",
        "network": False, "paid": False, "cross_project": False,
        "results": results,
    })
    return {"state": "OK", "assets": discovered, "audio": audio,
            "count": len(discovered) + len(audio["sfx"]) + (1 if audio["bgm"] else 0)}

def stage_assets(project: Path, extra_assets: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Check every declared visual against its recorded hash before it is used."""
    from contentops.media.local_assets import is_valid_local_preview_asset

    manifest_path = project / "sources" / "assets.json"
    if not manifest_path.is_file():
        raise M5Blocked("sources/assets.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = {}
    problems = []
    generated = list((extra_assets or {}).values())
    declared = list(manifest.get("assets") or [])
    all_ids = [str(asset.get("id")) for asset in declared + generated]
    if len(all_ids) != len(set(all_ids)):
        raise M5Blocked("duplicate declared/media-use asset id")
    root = ROOT.resolve()
    for asset in declared + generated:
        path = (root / asset["repo_path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            problems.append(f"{asset['id']}: path escapes the repository: {asset['repo_path']}")
            continue
        if not path.is_file():
            problems.append(f"{asset['id']}: file missing: {asset['repo_path']}")
            continue
        actual = _sha256(path)
        if actual != asset.get("sha256"):
            problems.append(f"{asset['id']}: sha256 {actual[:12]} != recorded {str(asset.get('sha256'))[:12]}")
            continue
        local_preview = is_valid_local_preview_asset(asset, project, ROOT)
        if (asset.get("permission") not in {"OWNED", "CREATED_BY_OWNER", "LICENSED"}
                and not local_preview):
            problems.append(f"{asset['id']}: permission {asset.get('permission')} is not usable")
            continue
        if not local_preview:
            try:
                validate_declared_asset(asset, project)
            except RightsError as exc:
                problems.append(f"{asset['id']}: {exc}")
                continue
        verified[asset["id"]] = {**asset, "verified_sha256": actual}
    payload = {
        "schema": "contentops.m5-assets-check/v1",
        "ok": not problems,
        "problems": problems,
        "assets": len(verified),
    }
    _write_json(project / "receipts" / "asset-manifest.json", payload)
    if problems:
        raise M5Blocked("; ".join(problems[:4]))
    return verified


def stage_claims(project: Path, artifacts: Dict[str, Any]) -> Dict[str, Any]:
    ledger_path = project / "script" / "claims.json"
    if not ledger_path.is_file():
        raise M5Blocked("script/claims.json is missing")
    ledger = ClaimLedger.load(ledger_path)
    problems = ledger.verify(artifacts, ROOT)
    payload = {
        "schema": "contentops.claim-verification/v1",
        "ok": not problems,
        "problems": problems,
        "claims": len(ledger.claims),
    }
    _write_json(project / "receipts" / "claim-verification.json", payload)
    if problems:
        raise M5Blocked("claims are not supported: " + "; ".join(problems[:4]))
    return {"ledger": ledger, "count": len(ledger.claims)}


def _source_snapshot_for_refs(refs: List[Dict[str, Any]],
                             source_assets: List[Dict[str, Any]]) -> Optional[str]:
    """Return the source snapshot whose exact source document backs a claim."""
    snapshots = [item for item in source_assets
                 if str(item.get("type") or "").upper() == "CODE_SNAPSHOT"]
    for ref in refs:
        ref_path = str(ref.get("path") or "").replace("\\", "/")
        marker = "/sources/"
        source_suffix = ref_path.split(marker, 1)[1] if marker in ref_path else ""
        if not source_suffix:
            continue
        matching = next((item for item in snapshots
                         if str(item.get("source_document") or "")
                         .replace("\\", "/").endswith(source_suffix)), None)
        if matching and matching.get("id"):
            return str(matching["id"])
    return None


def stage_motion(project: Path, config: Dict[str, Any], script: Dict[str, Any], *,
                 require_copy_review: bool,
                 narration: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Render account-profile or explicitly planned local Huashua clips.

    An M5 video account with a Huashua profile receives an automatic plan when
    no hand-authored plan is present. Unsupported content or missing source
    anchors stop before execution. The managed adapter remains the only render
    path; this local, non-paid action does not use a project execution grant.
    """
    motion = config.get("motion") or {}
    if not isinstance(motion, dict):
        motion = {}
    account_id = str(config.get("account_slug") or config.get("account_id") or "")
    dna_path = ROOT / "config" / "accounts" / f"{account_id}.json" if account_id else None
    account_dna = None
    if dna_path and dna_path.is_file():
        try:
            account_dna = json.loads(dna_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise M5Blocked(f"account DNA is invalid: {account_id}") from None
    if not motion.get("backend") and account_dna:
        visual = account_dna.get("visual") or {}
        profile = visual.get("motion", {}).get("motion_profile") or visual.get("motion_profile")
        if ((account_dna.get("pipeline") or "M5") == "M5"
                and isinstance(profile, dict)
                and profile.get("backend") in {"huashu-art-motion", "huashu-motion"}):
            motion = {**motion, "backend": profile["backend"], "auto_profile": True}
    default_backend = motion.get("backend")
    if default_backend not in (None, "huashu-art-motion", "huashu-motion", "art-motion", "motion"):
        raise M5Blocked(f"unsupported motion backend {default_backend!r}")
    if default_backend in ("art-motion", "motion"):
        default_backend = {"art-motion": "huashu-art-motion", "motion": "huashu-motion"}[default_backend]
    if not default_backend:
        default_backend = None
    if default_backend is None:
        _write_json(project / "receipts" / "motion-stage.json", {
            "schema": "contentops.m5-motion-stage/v1",
            "backend": None,
            "state": "NOT_CONFIGURED",
            "script_sha256": _payload_sha256(script),
            "shots": [],
            "production_ready": False,
        })
        return {"state": "NOT_CONFIGURED", "shots": 0}
    plan_arg = str(motion.get("shot_plan") or "").strip()
    if not plan_arg:
        if not account_id or not account_dna or not narration:
            raise M5Blocked("automatic Huashua motion needs account DNA and measured narration")
        from contentops.media.motion_planner import MotionPlanError, build_auto_plan
        try:
            claim_doc = json.loads((project / "script" / "claims.json")
                                   .read_text(encoding="utf-8"))
            refs_doc = json.loads((project / "sources" / "source-refs.json")
                                  .read_text(encoding="utf-8"))
            source_doc = json.loads((project / "sources" / "assets.json")
                                    .read_text(encoding="utf-8"))
            claims_by_id = {str(row.get("id")): row
                            for row in (claim_doc.get("claims") or [])}
            refs_by_id = {str(row.get("id")): row
                          for row in (refs_doc.get("refs") or [])}
            source_assets = source_doc.get("assets") or []
            plan_script = {**script, "lines": []}
            for original in script.get("lines") or []:
                line = dict(original)
                claim = claims_by_id.get(str(line.get("claim"))) or {}
                artifacts = [refs_by_id.get(str(ref), {})
                             for ref in (claim.get("artifacts") or [])]
                line["source_refs"] = [str(item.get("url") or item.get("path") or "")
                                       for item in artifacts
                                       if item.get("url") or item.get("path")]
                # Legacy script lines often all point to anchor-01, which
                # repeats the wrong file for engine/retriever claims.
                snapshot_id = _source_snapshot_for_refs(artifacts, source_assets)
                if snapshot_id:
                    line["asset_id"] = snapshot_id
                plan_script["lines"].append(line)
            generated = build_auto_plan(
                project=project, account_id=account_id, account_dna=account_dna,
                script=plan_script, narration=narration,
                source_assets={str(item.get("id")): item for item in source_assets},
            )
            if default_backend == "huashu-motion":
                from huashu_motion_backend import BackendError, author_auto_film
                lines_by_id = {str(row.get("id")): row for row in plan_script.get("lines") or []}
                narration_lines = narration.get("lines") or []
                timings_by_id = {str(row.get("line_id")): row
                                 for row in narration_lines if row.get("line_id")}
                timings_by_placement = {
                    str(line_row.get("id")): narration_lines[index]
                    for index, line_row in enumerate(plan_script.get("lines") or [])
                    if index < len(narration_lines)
                }
                auto_plan = dict(generated["plan"])
                auto_plan["backend"] = "huashu-motion"
                for shot in auto_plan.get("shots") or []:
                    placement = str(shot.get("placement_id") or "")
                    line = lines_by_id.get(placement)
                    timing = timings_by_id.get(placement) or timings_by_placement.get(placement) or {}
                    if not line or not timing.get("duration"):
                        raise M5Blocked(
                            f"{placement}: Huashu Motion needs a measured narration duration"
                        )
                    shot["asset_id"] = f"huashu-motion-{placement}"
                    shot["backend"] = "huashu-motion"
                    render_duration = float(shot.get("duration_s") or timing["duration"])
                    shot["spec"] = author_auto_film(
                        project, shot, line, account_dna, render_duration
                    )
                auto_path = project / "motion" / "auto" / (
                    f"huashu-motion-shot-plan-{generated['input_sha256'][:12]}.json"
                )
                auto_path.write_text(
                    json.dumps(auto_plan, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                generated = {**generated, "path": auto_path, "plan": auto_plan}
        except (OSError, ValueError, RuntimeError, MotionPlanError) as exc:
            raise M5Blocked(f"automatic Huashua shot plan: {exc}") from None
        plan_arg = generated["path"].relative_to(project).as_posix()
        motion = {**motion, "shot_plan": plan_arg,
                  "plan_sha256": generated["input_sha256"], "auto_profile": True}
    plan_path = (project / plan_arg).resolve()
    try:
        plan_path.relative_to(project.resolve())
    except ValueError:
        raise M5Blocked("motion.shot_plan must stay inside the project") from None
    if not plan_path.is_file():
        raise M5Blocked(f"motion shot plan is missing: {plan_arg}")
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise M5Blocked(f"motion shot plan is invalid: {exc}") from None
    shots = plan.get("shots") if isinstance(plan, dict) else None
    if not isinstance(shots, list) or not shots:
        raise M5Blocked("motion shot plan must contain a non-empty shots list")
    script_assets = project / "script" / "assets.json"
    if not script_assets.exists():
        # This is an adapter-maintained output map, not an approval record.
        # M5 owns its empty initialization so callers need not hand-author it.
        _write_json(script_assets, {"schema": "contentops.m5-script-assets/v1",
                                    "assets": {}})
    else:
        try:
            mapped = json.loads(script_assets.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise M5Blocked(f"script asset map is invalid: {exc}") from None
        if not isinstance(mapped, dict) or not isinstance(mapped.get("assets"), dict):
            raise M5Blocked("script/assets.json must contain an assets object")
    lines = script.get("lines") or []
    line_by_id = {str(row.get("id")): row for row in lines}
    if len(shots) != len(lines):
        raise M5Blocked("motion shot count must match M5 script line count")
    seen_placements = set()
    adapter = ROOT / "scripts" / "huashu_motion_adapter.py"
    motion_adapter = ROOT / "scripts" / "huashu_motion_backend.py"
    results = []
    mode = "REVIEW" if require_copy_review else "AUTO"
    narration_timings = {
        str(row.get("line_id")): row
        for row in (narration or {}).get("lines", [])
        if row.get("line_id") is not None
    }
    for shot in shots:
        if not isinstance(shot, dict):
            raise M5Blocked("motion shot entries must be objects")
        placement_id = str(shot.get("placement_id") or shot.get("id") or "")
        asset_id = str(shot.get("asset_id") or placement_id)
        spec = str(shot.get("spec") or "").strip()
        if not placement_id or placement_id not in line_by_id:
            raise M5Blocked(f"motion placement does not map to an M5 line: {placement_id!r}")
        if placement_id in seen_placements:
            raise M5Blocked(f"duplicate motion placement: {placement_id}")
        seen_placements.add(placement_id)
        line = line_by_id[placement_id]
        shot_backend = _select_motion_backend(shot, default_backend)
        source_asset_id = str(line.get("asset_id") or "")
        if not source_asset_id or (line.get("motion_asset_id")
                                   and line.get("motion_asset_id") != asset_id):
            raise M5Blocked(f"{placement_id}: motion asset_id must map to its script line")
        if not spec:
            raise M5Blocked(f"{placement_id}: motion shot plan has no spec path")
        if shot_backend == "huashu-motion":
            command = [python_executable(), str(motion_adapter), str(project),
                       "--film", spec, "--placement-id", placement_id,
                       "--asset-id", asset_id, "--account-id", account_id]
            timing = narration_timings.get(placement_id) or {}
            expected_duration = timing.get("duration")
            if expected_duration:
                command.extend(["--expected-duration", str(expected_duration)])
        else:
            command = [python_executable(), str(adapter), str(project), "--render",
                       "--mode", mode, "--spec", spec, "--placement-id", placement_id,
                       "--asset-id", asset_id, "--json"]
        proc = hidden_run(command, timeout=3600, cwd=str(ROOT),
                          env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
        try:
            result = json.loads(proc.stdout or "{}")
        except ValueError:
            result = {}
        execution = result.get("execution") or {}
        if proc.returncode != 0 or execution.get("state") not in ("EXECUTED", "REUSED"):
            detail = (execution.get("error") or
                      (result.get("decision") or {}).get("detail") or
                      (proc.stderr or proc.stdout or "adapter returned no execution receipt"))
            raise M5Blocked(f"Huashua motion blocked for {placement_id}: {str(detail)[-700:]}")
        results.append({"placement_id": placement_id, "asset_id": asset_id,
                        "source_asset_id": shot.get("source_asset_id", line.get("asset_id")),
                        "content_point": shot.get("content_point", line.get("narration")),
                        "backend": shot_backend,
                        "motion_syntax": shot.get("motion_syntax", "explicit-shot-plan"),
                        "execution_state": execution.get("state"),
                        "reused_render": execution.get("reused") is True,
                        "duration_s": shot.get("duration_s"),
                        "source_refs": shot.get("source_refs", []),
                        "visual_match": shot.get("visual_match", "PENDING_FRAME_REVIEW"),
                        "execution_receipt": result.get("receipt"),
                        "adapter_receipt": execution.get("adapter_receipt")})
    backends = sorted({str(row.get("backend")) for row in results})
    payload = {"schema": "contentops.m5-motion-stage/v1",
               "backend": backends[0] if len(backends) == 1 else "hybrid",
               "mode": mode, "state": "OK",
               "script_sha256": _payload_sha256(script), "shots": results,
               "production_ready": False}
    _write_json(project / "receipts" / "motion-stage.json", payload)
    return {"state": "OK", "backend": payload["backend"], "shots": len(results)}


def _load_script(project: Path) -> Dict[str, Any]:
    path = project / "script" / "script.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != SCRIPT_SCHEMA:
        raise M5Blocked(f"script schema is not {SCRIPT_SCHEMA}")
    return payload


def stage_script(project: Path, ledger: ClaimLedger, assets: Dict[str, Any]) -> Dict[str, Any]:
    script = _load_script(project)
    ids = [line["id"] for line in script["lines"]]
    if len(ids) != len(set(ids)):
        raise M5Blocked("duplicate script line id")
    known = ledger.by_id()
    cited = {line.get("claim") for line in script["lines"] if line.get("claim")}
    unknown = sorted(cited - set(known))
    if unknown:
        raise M5Blocked(f"script cites unknown claims: {unknown}")
    unused = ledger.require_used(cited)
    if unused:
        raise M5Blocked(f"claims never appear in the script: {unused}")
    for line in script["lines"]:
        asset = assets.get(line.get("asset_id"))
        if asset is None:
            raise M5Blocked(f"{line['id']}: asset_id {line.get('asset_id')!r} is not in sources/assets.json")
        if not (ROOT / asset["repo_path"]).is_file():
            raise M5Blocked(f"{line['id']}: asset missing: {asset['repo_path']}")
        if not str(line.get("narration") or "").strip():
            raise M5Blocked(f"{line['id']}: narration is empty")
    payload = {
        "schema": "contentops.m5-script-check/v1",
        "ok": True,
        "lines": len(script["lines"]),
        "claims_cited": sorted(cited),
        "claims_unused": [],
    }
    _write_json(project / "receipts" / "script-check.json", payload)

    master = project / "script" / "master.md"
    rows = ["| # | 旁白 | 字幕 | 事实来源 | 素材 |", "|---|---|---|---|---|"]
    for line in script["lines"]:
        rows.append(
            f"| {line['id']} | {line['narration']} | {line['caption']} | "
            f"{line.get('claim') or '—'} | {assets[line['asset_id']]['repo_path']} |"
        )
    master.write_text(
        f"# {project.name} — 脚本文本\n\n"
        "由 `script/script.json` 生成；每条事实声明在 `script/claims.json` 中绑定到来源引文。\n\n"
        + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return {"script": script, "lines": len(script["lines"])}


def _synthesize_windows(lines: List[Dict[str, Any]], out_dir: Path) -> List[Path]:
    """Synthesize one WAV per line with the local SAPI voice. No network."""
    if os.name != "nt":
        raise M5Blocked(
            "offline narration requires the Windows SAPI voice; no network TTS is authorized"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = out_dir / "lines.json"
    _write_json(manifest, [{"id": line["id"], "text": line["narration"]} for line in lines])
    ps = out_dir / "synthesize.ps1"
    ps.write_text(
        "\n".join([
            "param([string]$Manifest, [string]$OutDir)",
            "Add-Type -AssemblyName System.Speech",
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer",
            "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)",
            "$items = Get-Content -Raw -Encoding UTF8 $Manifest | ConvertFrom-Json",
            "foreach ($item in $items) {",
            "  $path = Join-Path $OutDir ($item.id + '.wav')",
            "  $synth.SetOutputToWaveFile($path, $fmt)",
            "  $synth.Speak($item.text)",
            "}",
            "$synth.Dispose()",
        ]) + "\n",
        encoding="utf-8",
    )
    proc = hidden_run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps),
         "-Manifest", str(manifest), "-OutDir", str(out_dir)],
        timeout=600,
    )
    if proc.returncode != 0:
        raise M5Blocked(f"SAPI synthesis failed: {(proc.stderr or proc.stdout)[-400:]}")
    wavs = [out_dir / f"{line['id']}.wav" for line in lines]
    missing = [p.name for p in wavs if not p.is_file()]
    if missing:
        raise M5Blocked(f"SAPI produced no audio for {missing}")
    return wavs


def _concat_with_pauses(wavs: List[Path], out_path: Path, work: Path) -> List[Dict[str, float]]:
    """Join the lines with short pauses and return each line's start/duration."""
    if not wavs:
        raise M5Blocked("narration produced no line audio")
    sample_rate = _audio_sample_rate(wavs[0])
    silence = work / "silence.wav"
    if not silence.is_file():
        proc = hidden_run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"anullsrc=r={sample_rate}:cl=mono", "-t", str(SILENCE_SECONDS),
             "-c:a", "pcm_s16le", str(silence)],
            timeout=120,
        )
        if proc.returncode != 0:
            raise M5Blocked("cannot generate silence")
    listing = work / "concat.txt"
    timings: List[Dict[str, float]] = []
    cursor = 0.0
    parts: List[str] = []
    for index, wav in enumerate(wavs):
        if index:
            parts.append(f"file '{silence.as_posix()}'")
            cursor += SILENCE_SECONDS
        parts.append(f"file '{wav.as_posix()}'")
        seconds = _duration(wav)
        timings.append({"start": round(cursor, 3), "duration": round(seconds, 3)})
        cursor += seconds
    listing.write_text("\n".join(parts) + "\n", encoding="utf-8")
    proc = hidden_run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c:a", "pcm_s16le", str(out_path)],
        timeout=300,
    )
    if proc.returncode != 0 or not out_path.is_file():
        raise M5Blocked(f"concat failed: {(proc.stderr or '')[-400:]}")
    return timings


def _text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stage_narration(project: Path, script: Dict[str, Any], *, provider: str = "sapi",
                    narration_audio: Optional[Path] = None,
                    narration_receipt: Optional[Path] = None,
                    narration_voice: Optional[str] = None,
                    narration_model: Optional[str] = None,
                    temporary_voice: bool = False,
                    cost_budget_cny: float = 0.0) -> Dict[str, Any]:
    """Produce the voice track from an explicitly chosen source.

    ``sapi``     the offline Windows voice — a compatibility and diagnostic path;
    ``existing`` an audio file plus the receipt that binds it to this script;
    ``minimax`` uses the existing M Plan Speech Provider once per line. The
    ordinary system voice path is accepted only when explicitly marked as a
    temporary audition; it is never labelled as a clone or final voice.
    Anything else is BLOCKED, never silently replaced with SAPI.
    """
    if provider not in ("sapi", "existing", "minimax"):
        raise M5Blocked(
            f"narration provider {provider!r} is not reachable in this build; "
            f"refusing to fall back to the offline SAPI voice")

    text = "\n".join(line["narration"] for line in script["lines"])
    text_sha = _text_sha(text)
    target = project / "assets" / "voice" / "narration.wav"
    target.parent.mkdir(parents=True, exist_ok=True)

    if provider == "minimax":
        from decimal import Decimal, InvalidOperation
        from datetime import datetime, timezone
        from contentops.media.contract import SpeechRequest
        from contentops.media.credentials import resolve_credential
        from contentops.media.minimax_speech import (
            MiniMaxMPlanProvider, receipt_to_dict, resolve_cli,
        )
        from synthesize_narration import build_guard

        if not isinstance(script.get("lines"), list) or not script["lines"]:
            raise M5Blocked("MiniMax narration needs at least one script line")
        try:
            budget = Decimal(str(cost_budget_cny))
        except (InvalidOperation, ValueError):
            raise M5Blocked("cost budget must be a non-negative CNY amount") from None
        if budget < 0:
            raise M5Blocked("cost budget must be a non-negative CNY amount")
        voice = (narration_voice or "").strip()
        if not voice:
            raise M5Blocked(
                "MiniMax requires an explicit --narration-voice; choose the verified "
                "clone ID or opt into a named temporary system voice"
            )
        if voice == "founder_primary_v1" and temporary_voice:
            raise M5Blocked("founder_primary_v1 cannot be labelled as a temporary system voice")
        if not temporary_voice and voice != "founder_primary_v1":
            raise M5Blocked(
                "a non-clone MiniMax voice requires --temporary-narration-voice; "
                "ordinary voices are auditions, not production clones"
            )
        resolved = resolve_credential()
        guard = build_guard(resolved)
        clone_inventory = None
        if voice == "founder_primary_v1":
            from contentops.media.minimax_voice_clone import MiniMaxVoiceCloneProvider
            from synthesize_narration import resolve_base_url
            try:
                clone_provider = MiniMaxVoiceCloneProvider(
                    credential=resolved, base_url=resolve_base_url())
                entries = clone_provider.list_cloned_voices()
            except Exception as exc:  # noqa: BLE001
                raise M5Blocked(
                    f"could not verify current founder_primary_v1 clone inventory "
                    f"({type(exc).__name__}); no synthesis was attempted"
                ) from None
            entry = next((item for item in entries
                          if str(item.get("voice_id") or item.get("id") or "") == voice), None)
            if entry is None:
                raise M5Blocked(
                    "founder_primary_v1 is absent from the current MiniMax clone inventory; "
                    "no historical clone receipt is treated as current"
                )
            created = entry.get("created_time")
            try:
                numeric = float(created)
                if numeric > 10_000_000_000:
                    numeric /= 1000
                created_at = datetime.fromtimestamp(numeric, tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                try:
                    created_at = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    raise M5Blocked(
                        "MiniMax clone inventory has no readable creation time for "
                        "founder_primary_v1; refusing a potentially expired voice"
                    ) from None
            age_seconds = (datetime.now(timezone.utc) - created_at).total_seconds()
            if age_seconds > 7 * 24 * 3600:
                raise M5Blocked(
                    "founder_primary_v1 is older than the documented 7-day active-use window; "
                    "no synthesis was attempted"
                )
            state = str(entry.get("status") or entry.get("state") or "").casefold()
            if state in {"inactive", "expired", "deleted", "disabled", "failed"}:
                raise M5Blocked(
                    f"founder_primary_v1 inventory status is {state}; no synthesis was attempted"
                )
            clone_inventory = {
                "voice": voice, "created_time": created_at.isoformat(),
                "age_seconds": int(max(0, age_seconds)),
                "inventory_status": state or "listed",
                "callability": "not_proven_until_a_real_tts_call",
            }
        work = project / "work" / "minimax-narration"
        work.mkdir(parents=True, exist_ok=True)
        speech = MiniMaxMPlanProvider(
            guard=guard,
            work_dir=work,
            cli=resolve_cli(),
            model=narration_model or "speech-2.8-hd",
            transport_credential=resolved,
        )
        wavs: List[Path] = []
        line_receipts: List[Dict[str, Any]] = []
        reused_count = 0
        billing_verdicts: List[str] = []
        for index, line in enumerate(script["lines"], start=1):
            request = SpeechRequest(
                display_text=str(line["narration"]),
                voice=voice,
                language="en" if any(ord(c) < 128 for c in str(line["narration"]))
                and not any("\u4e00" <= c <= "\u9fff" for c in str(line["narration"]))
                else "zh",
                model=narration_model or "speech-2.8-hd",
            )
            try:
                outcome = speech.synthesize_speech(request)
            except Exception as exc:  # noqa: BLE001
                raise M5Blocked(
                    f"MiniMax narration line {index} failed ({type(exc).__name__}): "
                    f"{str(exc)[:320]}"
                ) from None
            if not outcome.asset.normalized_path:
                raise M5Blocked(f"MiniMax narration line {index} has no normalized WAV")
            audio = Path(outcome.asset.normalized_path)
            if not audio.is_file() or _duration(audio) <= 0:
                raise M5Blocked(f"MiniMax narration line {index} is not playable audio")
            wavs.append(audio)
            reused_count += int(outcome.reused)
            line_receipts.append({
                "line_id": line.get("id"),
                "audio_sha256": outcome.asset.normalized_sha256,
                "audio_duration_s": round(float(outcome.asset.duration_s or _duration(audio)), 3),
                "voice": outcome.asset.voice,
                "model": outcome.asset.model,
                "reused": outcome.reused,
                "provider_receipt": receipt_to_dict(outcome.receipt),
            })
            billing_verdicts.append(str(outcome.receipt.billing_guard_verdict))
        timings = _concat_with_pauses(wavs, target, work)
        text_sha = _text_sha(text)
        payload = {
            "schema": "contentops.m5-narration/v1",
            "engine": "minimax_speech",
            "voice_provider": "minimax_temporary_system_voice" if temporary_voice
            else "minimax_cloned_voice",
            "voice": voice,
            "voice_alias": "founder_primary_v1" if voice == "founder_primary_v1" else None,
            "temporary_audition_only": bool(temporary_voice),
            "model": narration_model or "speech-2.8-hd",
            "network": True,
            "cost": 0,
            "cost_currency": "CNY",
            "cost_budget_cny": str(budget),
            "billing_guard_verdict": (
                "CACHE_ONLY_NO_NEW_AUTHORIZATION" if reused_count == len(wavs)
                else "SAFE_INCLUDED_PLAN" if all(v == "SAFE_INCLUDED_PLAN" for v in billing_verdicts)
                else "MIXED_CACHED_AND_GENERATED"),
            "credential_class": resolved.credential_class,
            "credential_source": resolved.source,
            "audio": target.relative_to(project).as_posix(),
            "sha256": _sha256(target),
            "text_sha256": text_sha,
            "duration_s": round(_duration(target), 3),
            "lines": [
                {**timing, **{"line_id": script["lines"][i].get("id")}}
                for i, timing in enumerate(timings)
            ],
            "line_receipts": line_receipts,
            "cache": {"line_count": len(wavs), "reused_line_count": reused_count},
            "clone_inventory": clone_inventory,
            "production_ready": False,
            "quality_note": "ordinary voice audition only; no clone identity or production quality is claimed"
            if temporary_voice else "cloned voice receipt bound per narration line",
        }
        _write_json(project / "receipts" / "minimax-speech.json", {
            "schema": "contentops.m5-minimax-speech/v1",
            "voice": voice, "model": payload["model"],
            "temporary_audition_only": bool(temporary_voice),
            "credential_class": resolved.credential_class,
            "billing_guard_verdict": payload["billing_guard_verdict"],
            "line_receipts": line_receipts,
            "cache": payload["cache"],
            "audio_sha256": payload["sha256"],
            "text_sha256": text_sha,
            "cost_cny": 0,
            "cost_budget_cny": str(budget),
        })
        _write_json(project / "receipts" / "narration.json", payload)
        return payload

    if provider == "existing":
        audio = Path(narration_audio) if narration_audio else None
        if audio is None or not audio.is_file():
            raise M5Blocked("provider 'existing' needs --narration-audio <file>")
        receipt_path = Path(narration_receipt) if narration_receipt else None
        if receipt_path is None or not receipt_path.is_file():
            raise M5Blocked(
                "provider 'existing' needs --narration-receipt: a path alone does not "
                "prove which text was spoken")
        try:
            previous = json.loads(receipt_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise M5Blocked(f"narration receipt is not readable JSON: {exc}")
        if previous.get("text_sha256") != text_sha:
            raise M5Blocked(
                "the narration receipt is not bound to the current script text — the "
                "audio speaks a different script")
        lines = previous.get("lines")
        if not isinstance(lines, list) or len(lines) != len(script["lines"]):
            raise M5Blocked(
                "the narration receipt carries no usable per-line timings; subtitles "
                "cannot be aligned to this audio")
        if audio.resolve() != target.resolve():
            shutil.copyfile(audio, target)
        payload = {
            "schema": "contentops.m5-narration/v1",
            "engine": previous.get("engine", "existing"),
            "voice_provider": "existing",
            "voice": previous.get("voice"),
            "network": False,
            "cost": 0,
            "audio": target.relative_to(project).as_posix(),
            "sha256": _sha256(target),
            "text_sha256": text_sha,
            "duration_s": round(_duration(target), 3),
            "lines": lines,
            "quality_note": "reused narration bound to this script by its receipt",
            "source_receipt": receipt_path.as_posix(),
        }
        _write_json(project / "receipts" / "narration.json", payload)
        return payload

    work = project / "work" / "narration"
    if work.is_dir():
        shutil.rmtree(work)
    wavs = _synthesize_windows(script["lines"], work)
    timings = _concat_with_pauses(wavs, target, work)
    payload = {
        "schema": "contentops.m5-narration/v1",
        "engine": "windows_sapi",
        "voice_provider": "sapi",
        "voice": "Microsoft Huihui Desktop (zh-CN)",
        "network": False,
        "cost": 0,
        "audio": target.relative_to(project).as_posix(),
        "sha256": _sha256(target),
        "text_sha256": text_sha,
        "duration_s": round(_duration(target), 3),
        "lines": timings,
        "quality_note": "local SAPI voice; robotic, not a production-grade voice track",
    }
    _write_json(project / "receipts" / "narration.json", payload)
    return payload


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def stage_subtitles(project: Path, script: Dict[str, Any], narration: Dict[str, Any]) -> Dict[str, Any]:
    lines = script["lines"]
    cues = []
    for line, timing in zip(lines, narration["lines"]):
        start = timing["start"]
        end = start + timing["duration"]
        cues.append(f"{len(cues) + 1}\n{_srt_time(start)} --> {_srt_time(end)}\n{line['caption']}\n")
    srt = project / "assets" / "captions" / "default.srt"
    srt.parent.mkdir(parents=True, exist_ok=True)
    srt.write_text("\n".join(cues), encoding="utf-8")
    covered = sum(t["duration"] for t in narration["lines"])
    ratio = covered / narration["duration_s"] if narration["duration_s"] else 0.0
    payload = {
        "schema": "contentops.m5-subtitles/v1",
        "path": srt.relative_to(project).as_posix(),
        "cues": len(cues),
        "coverage_ratio": round(ratio, 3),
        "audio_duration_s": narration["duration_s"],
    }
    _write_json(project / "receipts" / "subtitles.json", payload)
    if ratio < 0.8:
        raise M5Blocked(f"subtitle coverage {ratio:.2f} is below 0.8")
    return payload


def _align_shots_to_narration(shots: List[Dict[str, Any]],
                              narration_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Align each cut to measured speech starts, keeping natural pauses local.

    Adding all inter-line pauses to the final clip can make a real motion clip
    much shorter than its requested duration. Each shot now carries only the
    pause immediately following its own line; the last shot ends at the final
    measured speech boundary.
    """
    if not shots or not narration_lines:
        return shots
    if len(shots) != len(narration_lines):
        raise M5Blocked("storyboard shots do not match measured narration lines")
    for index, (shot, line) in enumerate(zip(shots, narration_lines)):
        start = float(line.get("start") or 0.0)
        if index + 1 < len(narration_lines):
            duration = float(narration_lines[index + 1].get("start") or 0.0) - start
        else:
            duration = float(line.get("duration") or 0.0)
        if duration <= 0:
            raise M5Blocked(f"narration line {index + 1} has a non-positive timeline span")
        shot["duration"] = round(duration, 3)
        shot["duration_s"] = round(duration, 3)
    return shots


def stage_storyboard(project: Path, config: Dict[str, Any], script: Dict[str, Any],
                     narration: Dict[str, Any], subtitles: Dict[str, Any],
                     assets: Dict[str, Any],
                     media_audio: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from contentops.media.storyboard_adapter import (
        StoryboardContractError, build_shots,
    )
    motion_assets = {}
    motion_receipt = project / "receipts" / "motion-stage.json"
    motion_configured = (config.get("motion") or {}).get("backend") in {
        "huashu-art-motion", "huashu-motion", "art-motion", "motion",
    }
    if motion_configured and not motion_receipt.is_file():
        raise M5Blocked("motion backend was requested but no motion-stage receipt was written")
    if motion_receipt.is_file():
        try:
            motion_data = json.loads(motion_receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise M5Blocked(f"motion stage receipt is invalid: {exc}") from None
        if motion_data.get("state") == "OK":
            expected_script_sha = _payload_sha256(script)
            if motion_data.get("script_sha256") != expected_script_sha:
                if motion_configured:
                    raise M5Blocked("motion-stage receipt does not match the current M5 script")
            else:
                motion_assets = {
                    str(row.get("placement_id")): str(row.get("asset_id"))
                    for row in motion_data.get("shots", [])
                    if row.get("placement_id") and row.get("asset_id")
                }
    storyboard_lines = []
    for original in script["lines"]:
        line = dict(original)
        motion_id = str(motion_assets.get(str(line.get("id")))
                        or line.get("motion_asset_id") or "")
        if motion_id:
            motion_asset = assets.get(motion_id)
            if not motion_asset:
                raise M5Blocked(
                    f"{line.get('id')}: motion asset {motion_id!r} is not registered")
            if not (motion_asset.get("generated")
                    or str(motion_asset.get("type") or "").lower().startswith("generated_")):
                raise M5Blocked(
                    f"{line.get('id')}: motion asset {motion_id!r} is not generated visual support")
            line["asset_id"] = motion_id
        storyboard_lines.append(line)
    try:
        shots = build_shots(lines=storyboard_lines,
                            narration_lines=narration["lines"],
                            assets=assets, repo_root=ROOT)
    except StoryboardContractError as exc:
        raise M5Blocked(f"storyboard contract: {exc}")
    shots = _align_shots_to_narration(shots, narration["lines"])
    target = (config.get("target") or {}).get("resolution", "1080x1920")
    generated_visual_ids = sorted({
        str(line.get("asset_id"))
        for line in storyboard_lines
        if line.get("asset_id")
        and line.get("asset_id") in assets
        and (
            bool(assets[line["asset_id"]].get("generated"))
            or str(assets[line["asset_id"]].get("type") or "").lower().startswith("generated_")
        )
    })
    storyboard = {
        "size": target,
        "image_motion": "static",
        "pad_mode": "trim",
        "shots": shots,
        "narration": f"{project.relative_to(ROOT).as_posix()}/assets/voice/narration.wav",
        "subtitle": f"{project.relative_to(ROOT).as_posix()}/assets/captions/default.srt",
        "engine": "easel",
        "voice_provider": (f"{narration.get('voice_provider', narration.get('engine', 'unknown'))}"
                           f"/{narration.get('voice') or 'unspecified'}"),
        "generated_visuals": {
            "count": len(generated_visual_ids),
            "asset_ids": generated_visual_ids,
            "policy": ("visual_support_not_claim_evidence" if generated_visual_ids
                       else "real_assets_only"),
        },
    }

    # Audio supplied by the media_use stage is a support track mixed underneath
    # the narration by the pinned Easel assembler. It is never a claim source and
    # never replaces the voice track.
    if media_audio:
        bgm = media_audio.get("bgm")
        if bgm:
            if not (ROOT / bgm["repo_path"]).is_file():
                raise M5Blocked(f"bgm file missing: {bgm['repo_path']}")
            storyboard["bgm"] = bgm["repo_path"]
            storyboard["bgm_volume"] = bgm["volume"]
        total = float(narration.get("duration_s") or 0.0)
        placements = []
        for sfx in media_audio.get("sfx") or []:
            if not (ROOT / sfx["repo_path"]).is_file():
                raise M5Blocked(f"sfx file missing: {sfx['repo_path']}")
            at = float(sfx["at"])
            if total and at >= total:
                raise M5Blocked(
                    f"{sfx['id']}: sfx placement {at:.3f}s is at or beyond the "
                    f"{total:.3f}s narration timeline"
                )
            entry = {"file": sfx["repo_path"], "at": at, "volume": sfx["volume"]}
            if any(old["file"] == entry["file"] and old["at"] == entry["at"]
                   for old in placements):
                raise M5Blocked(f"{sfx['id']}: duplicate sfx placement")
            placements.append(entry)
        if placements:
            storyboard["sfx"] = placements

    path = project / "script" / "storyboard.json"
    _write_json(path, storyboard)
    return {"storyboard": storyboard, "shots": len(shots), "path": path}


def _logical_path(path: Any, project: Path) -> Optional[str]:
    """Repo- or project-relative spelling for a receipt; never an absolute path."""
    if not path:
        return None
    resolved = Path(str(path)).resolve()
    for root, prefix in ((project.resolve(), "project://"), (ROOT.resolve(), "")):
        try:
            return prefix + resolved.relative_to(root).as_posix()
        except ValueError:
            continue
    return None


def stage_compose(project: Path, slug: str) -> Dict[str, Any]:
    import assemble_easel

    previous_video = project / "final" / f"{slug}.mp4"
    preserved_previous = project / "final" / f"{slug}-before-avatar-refresh.mp4"
    if previous_video.is_file() and not preserved_previous.exists():
        shutil.copy2(previous_video, preserved_previous)
    result = assemble_easel.run(project, out_name=slug)
    try:
        pin = json.loads((ROOT / "runtime" / "easel.lock.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pin = {}
    stamp = pin.get("tag") or pin.get("commit") or "unrecorded"
    receipt = {
        "status": result.get("status"),
        "video": _logical_path(result.get("video"), project),
        "subtitles_burned": result.get("subtitles_burned"),
        "upstream": f"easel@{stamp}:skills/openclaw/auto-short-video/scripts/assemble.py",
        "reason": result.get("reason"),
    }
    receipt = {key: value for key, value in receipt.items() if value is not None}
    _write_json(project / "receipts" / "compose.json", receipt)
    if result.get("status") != "OK":
        raise M5Blocked(f"compose: {result.get('reason')}")
    return receipt


def _registered_asset_path(asset_root: Path, manifest: Dict[str, Any], asset_id: str) -> Path:
    """Resolve a local-only asset by its registered hash, tolerating renamed files."""
    row = next((item for item in manifest.get("assets", [])
                if isinstance(item, dict) and item.get("asset_id") == asset_id), None)
    if row is None or not row.get("sha256"):
        raise M5Blocked(f"digital avatar asset {asset_id!r} is not registered")
    expected = str(row["sha256"]).casefold()
    declared = asset_root / str(row.get("relative_path") or "")
    candidates = [declared] if declared.is_file() else []
    if not candidates:
        candidates = [p for p in asset_root.rglob("*")
                      if p.is_file() and not p.is_symlink()]
    for candidate in candidates:
        if _sha256(candidate).casefold() == expected:
            return candidate.resolve()
    raise M5Blocked(f"digital avatar asset {asset_id!r} is missing or its hash changed")


def _run_h3_avatar_clip(project: Path, *, shot_id: str, line: str, role: str,
                        image: Path, voice_reference: Path, quota_budget: str) -> Dict[str, Any]:
    """Call the existing H3 provider CLI and require a real generated receipt."""
    shot = {
        "shot_id": shot_id,
        "purpose": f"Digital presenter {role} for a local video preview",
        "duration": 4,
        "aspect_ratio": "9:16",
        "mode": "Ref2VA",
        "subject": ("The same male presenter shown in reference image 1, maintaining his "
                    "facial identity, proportions, hair and clothing. He speaks one exact "
                    f"short Mandarin line: {line}"),
        "environment": "A restrained technology creator studio with warm practical lighting and a softly blurred bookshelf background.",
        "action": ("He looks into the camera, blinks naturally, gives one subtle "
                   f"{('concluding' if role == 'outro' else 'welcoming')} nod while speaking "
                   "the exact line in clear Mandarin. No on-screen text, subtitles, logos "
                   "or extra people."),
        "camera": "Static Shot",
        "sound": "Natural clean Mandarin speech matching the provided voice reference, synchronized to the visible speaker. No music or other voices.",
        "visual_style": "Natural live-action presenter, realistic skin and eye movement, editorial technology channel, soft cinematic key light",
        "reference_assets": ["the authorized male presenter portrait", "the authorized Mandarin voice sample"],
    }
    work_dir = project / "h3-avatar"
    work_dir.mkdir(parents=True, exist_ok=True)
    shot_file = work_dir / f"{shot_id}.json"
    _write_json(shot_file, shot)
    proc = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "generate_h3_shot.py"),
         "--shot-file", str(shot_file), "--out-dir", str(work_dir),
         "--shot-id", shot_id, "--mode", "Ref2VA", "--duration", "4",
         "--ratio", "9:16", "--reference-image", str(image),
         "--reference-audio", str(voice_reference), "--quota-budget", quota_budget,
         "--test-objective", f"Generate {role} avatar with registered local references for this production."],
        cwd=str(ROOT), timeout=1800,
    )
    try:
        payload = json.loads(proc.stdout or "{}")
    except ValueError:
        payload = {}
    if proc.returncode != 0 or payload.get("status") != "OK":
        reasons = payload.get("reasons") or payload.get("billing_reasons") or []
        detail = "; ".join(str(item) for item in reasons) or (proc.stderr or proc.stdout or "H3 generation failed")
        raise M5Blocked(f"MiniMax H3 {role} failed: {detail[-600:]}")
    video = Path(str(payload.get("canonical_path") or ""))
    if not video.is_absolute():
        video = ROOT / video
    receipt_path = video.with_name(video.name + ".receipt.json")
    if not video.is_file() or not receipt_path.is_file() or not payload.get("task_created"):
        raise M5Blocked(f"MiniMax H3 {role} returned without a generated video and provider receipt")
    return {"video": video, "receipt": receipt_path, "sha256": _sha256(video),
            "reused": bool(payload.get("reused")),
            "duration_s": payload.get("actual_duration_s"),
            "weekly_before": (payload.get("quota_before") or {}).get("weekly_remaining_percent"),
            "weekly_after": (payload.get("quota_after") or {}).get("weekly_remaining_percent")}


def stage_avatar(project: Path, slug: str, *, asset_root: Path,
                 quota_budget: Optional[str], intro_line: str, outro_line: str,
                 intro_video: Optional[Path] = None,
                 outro_video: Optional[Path] = None) -> Dict[str, Any]:
    """Generate/cache H3 bookends from registered local assets; leave a preview on partial failure."""
    manifest_path = asset_root / "asset-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise M5Blocked(f"digital avatar asset manifest unavailable: {exc}") from None
    if manifest.get("local_only") is not True or manifest.get("do_not_commit_media") is not True:
        raise M5Blocked("digital avatar assets must be explicitly registered as local-only")
    image = _registered_asset_path(asset_root, manifest, manifest.get("primary", {}).get("presenter_reference", ""))
    voice = _registered_asset_path(asset_root, manifest, manifest.get("primary", {}).get("voice_reference", ""))
    outputs: Dict[str, Any] = {"state": "GENERATING", "provider": "minimax-h3",
                               "asset_root": _logical_path(asset_root, project),
                               "image_sha256": _sha256(image), "voice_reference_sha256": _sha256(voice),
                               "audio_mode": "H3 native audio generated from a registered voice reference; not external TTS audio-driven lipsync"}
    _write_json(project / "receipts" / "avatar-bookends.json", outputs)

    def save_receipt() -> None:
        payload = dict(outputs)
        for name in ("intro", "outro"):
            clip = payload.get(name)
            if isinstance(clip, dict):
                clip = dict(clip)
                clip["video"] = _logical_path(clip.get("video"), project)
                clip["receipt"] = _logical_path(clip.get("receipt"), project)
                payload[name] = clip
        _write_json(project / "receipts" / "avatar-bookends.json", payload)

    try:
        expected_refs = {_sha256(image), _sha256(voice)}
        reused_any = False
        for role, candidate in (("intro", intro_video), ("outro", outro_video)):
            if candidate is None:
                continue
            receipt_path = candidate.with_name(candidate.name + ".receipt.json")
            try:
                receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise M5Blocked(f"H3 {role} reuse requires its provider receipt") from None
            if (not candidate.is_file() or receipt.get("provider") != "minimax_m_plan"
                    or receipt.get("model") != "MiniMax-H3"
                    or receipt.get("credential_class") != "SUBSCRIPTION"
                    or receipt.get("payg_allowed") is not False
                    or receipt.get("output_sha256") != _sha256(candidate)
                    or not receipt.get("audio_stream_present")):
                raise M5Blocked(f"H3 {role} reuse failed provider, audio, or hash validation")
            if not expected_refs.issubset(set(receipt.get("reference_asset_sha256") or [])):
                raise M5Blocked(f"H3 {role} receipt does not match the registered avatar and voice reference")
            outputs[role] = {
                "video": candidate.resolve(), "receipt": receipt_path.resolve(),
                "sha256": receipt["output_sha256"], "reused": True,
                "duration_s": receipt.get("actual_duration_s"),
                "weekly_before": (receipt.get("quota_before") or {}).get("weekly_remaining_percent"),
                "weekly_after": (receipt.get("quota_after") or {}).get("weekly_remaining_percent"),
            }
            reused_any = True

        missing = [role for role in ("intro", "outro") if role not in outputs]
        task_budget_pp: Optional[float] = None
        if missing:
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*pp\s*", quota_budget or "", re.IGNORECASE)
            if match is None:
                raise M5Blocked(
                    "MiniMax H3 requires a task-level weekly quota budget in percentage points, "
                    "for example 14pp for two clips"
                )
            task_budget_pp = float(match.group(1))
            required_pp = 7.0 * len(missing)
            if task_budget_pp + 1e-9 < required_pp:
                raise M5Blocked(
                    f"H3 task budget {task_budget_pp:g}pp is below the estimated "
                    f"{required_pp:g}pp needed for {len(missing)} missing clip(s); "
                    "no H3 request was sent"
                )
            outputs["task_quota_budget_pp"] = task_budget_pp
            outputs["estimated_quota_required_pp"] = required_pp
        quota_used_pp = 0.0
        for role in missing:
            remaining_pp = (task_budget_pp - quota_used_pp
                            if task_budget_pp is not None else 0.0)
            if remaining_pp + 1e-9 < 7.0:
                raise M5Blocked(
                    "observed H3 quota use left less than the 7pp clip estimate; "
                    "remaining bookend generation was stopped"
                )
            outputs[role] = _run_h3_avatar_clip(
                project, shot_id=f"{slug}-avatar-{role}",
                line=intro_line if role == "intro" else outro_line, role=role,
                image=image, voice_reference=voice,
                quota_budget=(f"7pp maximum for this H3 clip; task total "
                              f"{task_budget_pp:g}pp, remaining before this clip "
                              f"{remaining_pp:g}pp; included subscription only"))
            clip = outputs[role]
            before, after = clip.get("weekly_before"), clip.get("weekly_after")
            if isinstance(before, (int, float)) and isinstance(after, (int, float)):
                observed_pp = max(0.0, float(before) - float(after))
                quota_used_pp += observed_pp
                if observed_pp > remaining_pp + 1e-9:
                    raise M5Blocked(
                        f"H3 provider reported {observed_pp:g}pp use above the "
                        f"remaining task budget {remaining_pp:g}pp; no further clip was requested"
                    )
            else:
                # Without provider quota receipts the next billable clip cannot
                # be safely bounded against the task total.
                quota_used_pp += 7.0
                outputs["quota_usage_estimated"] = True
        if reused_any:
            outputs["reused_provider_outputs"] = True
        outputs["state"] = "READY"
    except M5Blocked as exc:
        outputs["state"] = "PARTIAL"
        outputs["blocked_reason"] = str(exc)
        outputs["production_ready"] = False
        save_receipt()
        return outputs
    save_receipt()
    return outputs


def _compose_avatar_bookends(project: Path, slug: str, avatar: Dict[str, Any],
                             video: Path) -> Dict[str, Any]:
    """Place H3's native-audio intro/outro around the M5 render."""
    if avatar.get("state") != "READY":
        return {"state": avatar.get("state", "NOT_CONFIGURED")}
    intro, outro = avatar["intro"]["video"], avatar["outro"]["video"]
    if not intro.is_file() or not outro.is_file() or not video.is_file():
        raise M5Blocked("avatar bookend or composed M5 video disappeared before assembly")
    base_copy = video.with_name(f"{slug}-main-only.mp4")
    # M5 has just rendered a fresh body, which may contain repaired shots.
    # Reusing an older main-only file here silently discarded those changes
    # when bookends were concatenated around a stale body.
    staged_base = base_copy.with_name(f"{base_copy.stem}.tmp{base_copy.suffix}")
    shutil.copy2(video, staged_base)
    staged_base.replace(base_copy)
    staged = video.with_name(f"{slug}.avatar.tmp.mp4")
    filter_complex = (
        "[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v0];"
        "[1:v]fps=30,scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v1];"
        "[2:v]fps=30,scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v2];"
        "[0:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a0];"
        "[1:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a1];"
        "[2:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a2];"
        "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[outv][outa]"
    )
    proc = hidden_run(
        ["ffmpeg", "-y", "-i", str(intro), "-i", str(base_copy), "-i", str(outro),
         "-filter_complex", filter_complex, "-map", "[outv]", "-map", "[outa]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(staged)],
        cwd=str(ROOT), timeout=900,
    )
    if proc.returncode != 0 or not staged.is_file():
        raise M5Blocked(f"avatar bookend concat failed: {(proc.stderr or '')[-500:]}")
    staged.replace(video)
    result = {"state": "COMPOSED", "video": _logical_path(video, project),
              "main_only": _logical_path(base_copy, project),
              "intro_duration_s": avatar["intro"].get("duration_s"),
              "outro_duration_s": avatar["outro"].get("duration_s"),
              "video_sha256": _sha256(video), "audio": "H3 native intro and outro audio; M5 audio in the middle",
              "production_ready": False, "publish_authorized": False}
    avatar_receipt_path = project / "receipts" / "avatar-bookends.json"
    avatar_receipt = _read_json_or_none(avatar_receipt_path) or {}
    avatar_receipt["composite"] = result
    _write_json(avatar_receipt_path, avatar_receipt)
    return result


def _compose_partial_avatar_preview(project: Path, slug: str, avatar: Dict[str, Any],
                                   main_video: Path, output_video: Path) -> Dict[str, Any]:
    """Keep an available H3 bookend reviewable without presenting it as complete."""
    if not main_video.is_file() or output_video.resolve() == main_video.resolve():
        raise M5Blocked("partial avatar preview needs a distinct output path and a main video")
    segments = []
    for name in ("intro", "outro"):
        row = avatar.get(name)
        candidate = row.get("video") if isinstance(row, dict) else None
        if candidate is not None:
            candidate = Path(candidate)
            if not candidate.is_file():
                raise M5Blocked(f"partial avatar preview {name} clip is missing")
            segments.append((name, candidate))
    if not segments:
        raise M5Blocked("partial avatar preview has no generated H3 clip to review")

    ordered = []
    if any(name == "intro" for name, _ in segments):
        ordered.extend([("intro", dict(segments)["intro"]), ("main", main_video)])
    else:
        ordered.append(("main", main_video))
    if any(name == "outro" for name, _ in segments):
        ordered.append(("outro", dict(segments)["outro"]))
    output_video.parent.mkdir(parents=True, exist_ok=True)
    staged = output_video.with_name(output_video.stem + ".partial.tmp.mp4")
    inputs = []
    filters = []
    concat_labels = []
    for idx, (name, path) in enumerate(ordered):
        inputs.extend(["-i", str(path)])
        filters.extend([
            f"[{idx}:v]fps=30,scale=1080:1920:force_original_aspect_ratio=decrease,"
            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{idx}];",
            f"[{idx}:a]aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[a{idx}];",
        ])
        concat_labels.extend([f"[v{idx}]", f"[a{idx}]"])
    filters.append(
        "".join(concat_labels) + f"concat=n={len(ordered)}:v=1:a=1[outv][outa]"
    )
    proc = hidden_run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", "".join(filters),
         "-map", "[outv]", "-map", "[outa]", "-c:v", "libx264", "-preset", "medium",
         "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(staged)], cwd=str(ROOT), timeout=900,
    )
    if proc.returncode != 0 or not staged.is_file():
        raise M5Blocked(f"partial avatar preview concat failed: {(proc.stderr or '')[-500:]}")
    staged.replace(output_video)
    result = {
        "state": "PARTIAL_PREVIEW", "video": _logical_path(output_video, project),
        "segments": [name for name, _ in ordered],
        "video_sha256": _sha256(output_video), "production_ready": False,
        "publish_authorized": False,
    }
    receipt_path = project / "receipts" / "avatar-bookends.json"
    receipt = _read_json_or_none(receipt_path) or {}
    receipt["partial_preview"] = result
    _write_json(receipt_path, receipt)
    return result


def stage_qc(project: Path, slug: str) -> Dict[str, Any]:
    from contentops.media.qc_canonical import (
        CURRENCY_CURRENT,
        canonical_qc_report,
        render_canonical_qc_markdown,
    )

    proc = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "qc_video.py"), str(project),
         "--video", f"{slug}.mp4"],
        cwd=str(ROOT), timeout=900,
    )
    report_path = project / "receipts" / f"qc-report-{slug}.json"
    legacy_path = project / "receipts" / "qc-report.json"
    if not report_path.is_file() and legacy_path.is_file():
        report_path = legacy_path
    if not report_path.is_file():
        raise M5Blocked(f"qc produced no report: {(proc.stderr or proc.stdout)[-300:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    video = project / "final" / f"{slug}.mp4"
    has_audio = _has_audio(video)
    extra = {
        "audio_stream": has_audio,
        "overall_after_m5": "PASS" if report.get("overall") != "FAIL" and has_audio else "FAIL",
    }
    canonical = canonical_qc_report(
        report, repo_root=ROOT, project_root=project,
        graded_target=f"project://final/{slug}.mp4", currency=CURRENCY_CURRENT,
    )
    canonical["project"] = (
        project.relative_to(ROOT).as_posix() if project.is_relative_to(ROOT) else "project://"
    )
    canonical["m5_checks"] = extra
    _write_json(report_path, canonical)
    (project / "receipts" / f"qc-report-{slug}.md").write_text(
        render_canonical_qc_markdown(canonical, project_name=project.name), encoding="utf-8"
    )
    if extra["overall_after_m5"] == "FAIL":
        raise M5Blocked("QC failed: " + json.dumps(extra))
    return {"report": canonical, "video": str(video)}


def stage_visual_qc(project: Path, slug: str) -> Dict[str, Any]:
    """Run frame sampling plus Huashu's calibrated motion/blank-frame gate.

    This remains an automated screen: it never grants production readiness or
    founder approval. Missing tools, malformed output, and uncertain verdicts
    fail closed. The source video and its hash bind both receipts.
    """
    from contentops.media.huashu_runtime import find_runtime
    from contentops.media.visual_gate import evaluate_film_gate

    video = project / "final" / f"{slug}.mp4"
    if not video.is_file():
        raise M5Blocked("visual QC requires the composed final video")
    video_sha = _file_sha256(video)
    receipts = project / "receipts"
    visual_receipt_path = receipts / "visual-gate.json"
    contact_sheet = receipts / "visual-contact-sheet.png"
    visual_qc_path = receipts / "visual-qc.json"

    # Fixed-interval samples make a contact sheet for required human playback.
    sample = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "qc_visual.py"), str(project),
         "--video", f"{slug}.mp4"], cwd=str(ROOT), timeout=300,
    )
    visual_qc = _read_json_or_none(visual_qc_path)
    if visual_qc is not None:
        recorded_video = visual_qc.get("video")
        try:
            same_video = bool(recorded_video) and Path(recorded_video).resolve() == video.resolve()
        except (OSError, RuntimeError):
            same_video = False
        if not same_video:
            visual_qc = None
    if visual_qc is not None:
        if visual_qc.get("contact_sheet") and contact_sheet.is_file():
            visual_qc["contact_sheet"] = "project://receipts/visual-contact-sheet.png"
        visual_qc.pop("project", None)
        visual_qc.pop("video", None)
        visual_qc["video_sha256"] = video_sha
        _write_json(visual_qc_path, visual_qc)
    frame_summary = (visual_qc or {}).get("summary") or {}
    frame_sampling_valid = (
        sample.returncode == 0
        and visual_qc is not None
        and visual_qc.get("status") in {"PASS", "WARN"}
        and contact_sheet.is_file()
        and frame_summary.get("extraction_failures", 10) <= 3
    )

    try:
        runtime = find_runtime(ROOT)
    except (OSError, RuntimeError):
        result = {
            "schema": "contentops.visual-gate/v1", "state": "BLOCKED",
            "reason": "no supported local Huashu Art Motion installation was found",
            "video_sha256": video_sha,
            "contact_sheet": "project://receipts/visual-contact-sheet.png"
            if contact_sheet.is_file() else None,
            "frame_sampling": visual_qc.get("status") if visual_qc else "BLOCKED",
            "production_ready": False, "publish_authorized": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
        }
        _write_json(visual_receipt_path, result)
        raise M5Blocked("visual motion gate blocked: Huashu film_gate.py unavailable") from None

    gate_script = runtime / "scripts" / "film_gate.py"
    if not gate_script.is_file():
        result = {
            "schema": "contentops.visual-gate/v1", "state": "BLOCKED",
            "reason": "Huashu installation has no scripts/film_gate.py",
            "video_sha256": video_sha,
            "contact_sheet": "project://receipts/visual-contact-sheet.png"
            if contact_sheet.is_file() else None,
            "production_ready": False, "publish_authorized": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
        }
        _write_json(visual_receipt_path, result)
        raise M5Blocked("visual motion gate blocked: film_gate.py missing")

    proc = hidden_run(
        [python_executable(), str(gate_script), str(video), "--json",
         "--vertical", "yes", "--no-template"], cwd=str(ROOT), timeout=900,
    )
    try:
        payload = json.loads(proc.stdout or "")
    except (TypeError, ValueError):
        payload = {}
    result = evaluate_film_gate(payload, proc.returncode)
    sampling_block_reason = None
    if not frame_sampling_valid and result["state"] not in {"FAIL", "BLOCKED"}:
        result["state"] = "BLOCKED"
        sampling_block_reason = "fixed-interval frame sampling or contact sheet is incomplete"
    result.update({
        "video_sha256": video_sha,
        "frame_sampling": visual_qc.get("status") if visual_qc else "BLOCKED",
        "frame_sampling_failures": (visual_qc.get("summary") or {}).get("extraction_failures")
        if visual_qc else None,
        "contact_sheet": "project://receipts/visual-contact-sheet.png"
        if contact_sheet.is_file() else None,
        "reason": sampling_block_reason or (
            None if result["state"] in {"PASS", "WARN"}
            else ((payload.get("summary") if isinstance(payload, dict) else None)
                  or (result.get("metrics") or {}).get("explain")
                  or "Huashu film gate returned an unrecognized result")
        ),
    })
    _write_json(visual_receipt_path, result)
    if result["state"] in {"BLOCKED", "FAIL"}:
        raise M5Blocked(f"visual motion gate {result['state']}: {result.get('reason') or result.get('gate_light')}")
    return result


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _has_audio(video: Path) -> bool:
    proc = hidden_run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=codec_type", "-of", "csv=p=0", str(video)],
        timeout=60,
    )
    return "audio" in (proc.stdout or "")


def _read_json_or_none(path: Path) -> Optional[Dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def stage_review(project: Path, slug: str, qc: Dict[str, Any],
                 bundle: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    report = qc["report"]
    fails = [c["id"] for c in report.get("checks", []) if c.get("severity") == "FAIL"]
    warns = [c["id"] for c in report.get("checks", []) if c.get("severity") == "WARN"]
    bundle_id = (bundle or {}).get("bundle_id")
    bundle_sha = (bundle or {}).get("bundle_sha256")

    # A review is bound to the Bundle bytes it saw. If those bytes moved, the
    # old review is revoked rather than left standing next to fresh evidence.
    previous = _read_json_or_none(project / "receipts" / "human-review.json")
    revoked = None
    if previous and bundle_sha is not None:
        reviewed = previous.get("reviewer") or previous.get("decision")
        if reviewed and previous.get("bundle_sha256") != bundle_sha:
            revoked = previous

    payload = {
        "project": project.relative_to(ROOT).as_posix(),
        "video": f"{project.relative_to(ROOT).as_posix()}/final/{slug}.mp4",
        "engine": "easel",
        "voice_quality": "windows_sapi_offline",
        "bundle_id": bundle_id,
        "bundle_sha256": bundle_sha,
        "production_ready": False,
        "state": "PENDING_FOUNDER_REVIEW",
        "auto_qc_result": report.get("overall"),
        "auto_qc_checks": len(report.get("checks", [])),
        "auto_qc_fails": fails,
        "auto_qc_warns": warns,
        "reviewer": None,
        "reviewed_at": None,
        "scores": None,
        "decision": None,
        "note": "scores are null until a human fills them; this file is not an approval",
    }
    if revoked:
        payload["review_revoked_reason"] = "BUNDLE_CHANGED"
        payload["revoked_review"] = {
            key: revoked.get(key)
            for key in ("reviewer", "reviewed_at", "decision", "bundle_sha256")
        }
    _write_json(project / "receipts" / "human-review.json", payload)
    return payload


def build(project: Path, *, skip_compose: bool = False, media_adapter: Any = None,
          narration_provider: Optional[str] = None,
          narration_audio: Optional[Path] = None,
          narration_receipt: Optional[Path] = None,
          narration_voice: Optional[str] = None,
          narration_model: Optional[str] = None,
          temporary_voice: bool = False,
          cost_budget_cny: float = 0.0,
          assets_dir: Optional[Path] = None,
          avatar_provider: Optional[str] = None,
          avatar_assets_dir: Optional[Path] = None,
          avatar_quota_budget: Optional[str] = None,
          avatar_intro_line: Optional[str] = None,
          avatar_outro_line: Optional[str] = None,
          avatar_intro_video: Optional[Path] = None,
          avatar_outro_video: Optional[Path] = None,
           require_copy_review: bool = True) -> Dict[str, Any]:
    if not project.is_dir():
        raise M5Blocked(f"project not found: {project}")
    stages: Dict[str, Any] = {}
    timings: Dict[str, float] = {}

    def run_stage(name: str, function, *args, **kwargs):
        started = time.monotonic()
        try:
            return function(*args, **kwargs)
        finally:
            timings[name] = round(time.monotonic() - started, 3)

    if assets_dir is not None:
        from contentops.media.local_assets import LocalAssetError, import_local_assets
        try:
            imported = run_stage("user_assets", import_local_assets, assets_dir,
                                 project, repo_root=ROOT)
        except LocalAssetError as exc:
            raise M5Blocked(f"user asset import: {exc}") from None
        stages["user_assets"] = {
            "state": "IMPORTED_LOCAL_PREVIEW_ONLY",
            "count": len(imported["assets"]),
            "receipt": "receipts/user-assets-import.json",
            "distribution_authorized": False,
            "evidence_capable": False,
        }

    config = _read_yaml(project / "project.yaml")
    slug = config.get("id") or project.name
    avatar_profile = _load_digital_presenter_profile(config)
    if avatar_profile:
        avatar_provider = avatar_provider or avatar_profile.get("provider")
        avatar_assets_dir = avatar_assets_dir or (
            ROOT / str(avatar_profile.get("asset_dir") or "assert")
        ).resolve()

    # A router project's copy is final only after the brief bridge writes
    # script.json and claims.json, so its review has to cover those files.
    # The gate therefore sits before narration, not at the draft. A project
    # with no 00_brief/brief.json is a legacy sample and is not retroactively
    # blocked; see copy_review.require_if_brief_driven.
    # In AUTO, draft video rendering can proceed without a separate manual
    # copy sign-off. Source/claim/asset checks still run; final publishing
    # remains separately subject to human review.
    if require_copy_review:
        try:
            copy_review.require_if_brief_driven(project)
        except copy_review.CopyReviewRequired as exc:
            raise M5Blocked(f"copy review: {exc}") from None

    bundle = run_stage("bundle", stage_bundle, project, config)
    if bundle["state"] != "NOT_CONFIGURED":
        stages["bundle"] = bundle
    sources = run_stage("sources", stage_sources, project, config)
    stages["sources"] = {"count": sources["count"]}
    media = run_stage("media_use", stage_media_use, project, config, adapter=media_adapter)
    stages["media_use"] = {
        "state": media["state"], "count": media["count"],
        "bgm": bool(media["audio"]["bgm"]), "sfx": len(media["audio"]["sfx"]),
    }
    claims = run_stage("claims", stage_claims, project, sources["artifacts"])
    stages["claims"] = {"count": claims["count"]}
    script_payload = _load_script(project)
    assets = run_stage("assets", stage_assets, project, extra_assets=media["assets"])
    stages["assets"] = {"count": len(assets)}
    script = run_stage("script", stage_script, project, claims["ledger"], assets)
    stages["script"] = {"lines": script["lines"]}
    narration_defaults = _resolve_narration_defaults(config)
    provider = (narration_provider
                or (config.get("narration") or {}).get("provider")
                or narration_defaults.get("provider")
                or "sapi")
    narration_voice = narration_voice or narration_defaults.get("voice")
    narration_model = narration_model or narration_defaults.get("model") or "speech-2.8-hd"
    narration = run_stage("narration", stage_narration, project, script["script"],
                          provider=provider, narration_audio=narration_audio,
                          narration_receipt=narration_receipt,
                          narration_voice=narration_voice,
                          narration_model=narration_model,
                          temporary_voice=temporary_voice,
                          cost_budget_cny=cost_budget_cny)
    stages["narration"] = {"duration_s": narration["duration_s"],
                           "engine": narration["engine"],
                           "provider": narration.get("voice_provider", provider)}
    motion = run_stage("motion", stage_motion, project, config, script["script"],
                       require_copy_review=require_copy_review, narration=narration)
    if motion["state"] != "NOT_CONFIGURED":
        stages["motion"] = motion
        assets = run_stage("motion_assets", stage_assets, project,
                           extra_assets=media["assets"])
        stages["assets"] = {"count": len(assets)}
    subtitles = run_stage("subtitles", stage_subtitles, project, script["script"], narration)
    stages["subtitles"] = {"cues": subtitles["cues"]}
    storyboard = run_stage("storyboard", stage_storyboard, project, config,
                            script["script"], narration, subtitles, assets,
                            media_audio=media["audio"])
    stages["storyboard"] = {
        "shots": storyboard["shots"],
        "bgm": "bgm" in storyboard["storyboard"],
        "sfx": len(storyboard["storyboard"].get("sfx") or []),
    }

    avatar = None
    if avatar_provider:
        if avatar_provider != "minimax-h3":
            stages["avatar"] = {"state": "BLOCKED", "reason": f"unsupported avatar provider {avatar_provider!r}"}
        elif not avatar_quota_budget and not (avatar_intro_video or avatar_outro_video):
            reason = "MiniMax H3 requires an explicit subscription quota budget"
            avatar = {
                "state": "BLOCKED", "provider": "minimax-h3",
                "asset_root": _logical_path(avatar_assets_dir or (ROOT / "assert"), project),
                "blocked_reason": reason, "production_ready": False,
                "publish_authorized": False,
            }
            _write_json(project / "receipts" / "avatar-bookends.json", avatar)
            stages["avatar"] = {
                "state": "BLOCKED", "provider": "minimax-h3",
                "reason": reason, "receipt": "receipts/avatar-bookends.json",
            }
        else:
            asset_root = (avatar_assets_dir or (ROOT / "assert")).resolve()
            intro_line = avatar_intro_line or str(
                avatar_profile.get("intro_line") or "本期我们来拆解一个关键问题。"
            )
            outro_line = avatar_outro_line or str(
                avatar_profile.get("outro_line") or "关注我，继续拆解 AI 技术。"
            )
            try:
                avatar = run_stage("avatar", stage_avatar, project, slug,
                                   asset_root=asset_root,
                                   quota_budget=avatar_quota_budget,
                                   intro_line=intro_line, outro_line=outro_line,
                                   intro_video=avatar_intro_video,
                                   outro_video=avatar_outro_video)
            except M5Blocked as exc:
                avatar = {"state": "BLOCKED", "blocked_reason": str(exc),
                          "production_ready": False}
                _write_json(project / "receipts" / "avatar-bookends.json", avatar)
            stages["avatar"] = {
                "state": avatar.get("state"), "provider": avatar.get("provider", avatar_provider),
                "receipt": "receipts/avatar-bookends.json",
                "audio_mode": avatar.get("audio_mode"),
                "blocked_reason": avatar.get("blocked_reason"),
            }

    if skip_compose:
        stages["compose"] = {"state": "NOT_RUN"}
        stages["qc"] = {"state": "NOT_RUN"}
        review = None
    else:
        compose = run_stage("compose", stage_compose, project, slug)
        if avatar is not None and avatar.get("state") == "READY":
            try:
                composed_avatar = run_stage(_compose_avatar_bookends.__name__,
                                            _compose_avatar_bookends, project, slug, avatar,
                                            project / "final" / f"{slug}.mp4")
                stages["avatar_compose"] = composed_avatar
            except M5Blocked as exc:
                stages["avatar_compose"] = {"state": "BLOCKED", "reason": str(exc),
                                             "production_ready": False}
                avatar_receipt = _read_json_or_none(project / "receipts" / "avatar-bookends.json") or {}
                avatar_receipt["compose_blocked_reason"] = str(exc)
                _write_json(project / "receipts" / "avatar-bookends.json", avatar_receipt)
        elif avatar is not None and avatar.get("state") == "PARTIAL":
            available_clips = any(
                isinstance(avatar.get(name), dict) and avatar[name].get("video")
                for name in ("intro", "outro")
            )
            if available_clips:
                try:
                    preview = run_stage(
                        _compose_partial_avatar_preview.__name__,
                        _compose_partial_avatar_preview, project, slug, avatar,
                        project / "final" / f"{slug}.mp4",
                        project / "final" / f"{slug}-avatar-preview.mp4",
                    )
                    stages["avatar_preview"] = preview
                except M5Blocked as exc:
                    stages["avatar_preview"] = {
                        "state": "BLOCKED", "reason": str(exc),
                        "production_ready": False,
                    }
        stages["compose"] = {"state": "OK", "video": compose.get("video")}
        qc = run_stage("qc", stage_qc, project, slug)
        stages["qc"] = {"overall": qc["report"].get("overall"),
                        "audio": qc["report"]["m5_checks"]["audio_stream"]}
        visual = run_stage("visual_qc", stage_visual_qc, project, slug)
        stages["visual_qc"] = {
            "state": visual["state"], "gate_light": visual.get("gate_light"),
            "receipt": "receipts/visual-gate.json",
            "contact_sheet": visual.get("contact_sheet"),
        }
        review = run_stage("human_review_package", stage_review, project, slug, qc,
                           bundle=stages.get("bundle"))

    run = {
        "schema": RUN_SCHEMA,
        "project": project.relative_to(ROOT).as_posix() if project.is_relative_to(ROOT) else str(project),
        "stages": stages,
        "stage_timings_seconds": timings,
        "production_ready": False,
        "copy_review_required_for_render": require_copy_review,
        "human_review": "PENDING_FOUNDER_REVIEW" if review else "NOT_RUN",
    }
    _write_json(project / "receipts" / "m5-run.json", run)
    return run


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", help="project directory, e.g. projects/m5-easel-pin")
    parser.add_argument("--skip-compose", action="store_true")
    parser.add_argument("--narration-provider", default=None,
                        choices=("sapi", "existing", "minimax"),
                        help="sapi = offline Windows voice (compatibility/diagnostic); "
                             "existing = reuse audio bound to this script by a receipt; "
                             "minimax = official M Plan Speech Provider, with an explicit voice ID. "
                             "Any other provider is refused, never silently replaced")
    parser.add_argument("--narration-audio", default=None,
                        help="with --narration-provider existing: the audio file to reuse")
    parser.add_argument("--narration-receipt", default=None,
                        help="with --narration-provider existing: a prior narration.json "
                             "carrying text_sha256 and per-line timings")
    parser.add_argument("--narration-voice", default=None,
                        help="MiniMax voice ID; use founder_primary_v1 only after current availability is verified")
    parser.add_argument("--narration-model", default="speech-2.8-hd")
    parser.add_argument("--temporary-narration-voice", action="store_true",
                        help="label a named ordinary MiniMax system voice as an audition, never as the clone")
    parser.add_argument("--cost-budget-cny", type=float, default=0.0,
                        help="task-level CNY ceiling; current M5 MiniMax path allows included-plan-only calls")
    parser.add_argument("--avatar-provider", choices=("minimax-h3",), default=None,
                        help="optional registered-asset MiniMax H3 intro/outro generation")
    parser.add_argument("--avatar-assets-dir", default=None,
                        help="local-only asset root containing asset-manifest.json; defaults to ./assert")
    parser.add_argument("--avatar-quota-budget", default=None,
                        help="explicit included-subscription weekly quota budget for H3 tasks")
    parser.add_argument("--avatar-intro-line", default=None,
                        help="short Mandarin digital presenter intro line")
    parser.add_argument("--avatar-outro-line", default=None,
                        help="short Mandarin digital presenter outro line")
    parser.add_argument("--avatar-intro-video", default=None,
                        help="reuse a real H3 intro MP4 only with its adjacent provider receipt")
    parser.add_argument("--avatar-outro-video", default=None,
                        help="reuse a real H3 outro MP4 only with its adjacent provider receipt")
    parser.add_argument("--assets", default=None,
                        help="explicit user-selected image/video folder; imported files are "
                             "local-preview-only and do not grant distribution or evidence rights")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()
    try:
        run = build(project, skip_compose=args.skip_compose,
                    narration_provider=args.narration_provider,
                    narration_audio=(Path(args.narration_audio)
                                     if args.narration_audio else None),
                    narration_receipt=(Path(args.narration_receipt)
                                       if args.narration_receipt else None),
                    narration_voice=args.narration_voice,
                    narration_model=args.narration_model,
                    temporary_voice=args.temporary_narration_voice,
                    cost_budget_cny=args.cost_budget_cny,
                    assets_dir=(Path(args.assets).expanduser().resolve()
                                if args.assets else None),
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
    except M5Blocked as exc:
        result = {"ok": False, "state": "BLOCKED", "reason": str(exc)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 4
    if args.json:
        print(json.dumps(run, ensure_ascii=False, indent=2))
    else:
        print(f"project          {run['project']}")
        for name, stage in run["stages"].items():
            print(f"  {name:12} {json.dumps(stage, ensure_ascii=False)[:90]}")
        print(f"  production_ready {run['production_ready']}  ({run['human_review']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
