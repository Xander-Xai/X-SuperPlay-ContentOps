#!/usr/bin/env python3
"""Run the M5 production chain for one project and write a receipt per stage.

The chain is deliberately narrow and refuses rather than improvises:

    sources → claims → script → narration → subtitles → storyboard → compose → QC → review

Facts come from `project.yaml` source refs and are verified against quotes in
`script/claims.json`. Narration is synthesized locally (Windows SAPI) only:
network TTS is not authorized, and a silent video is not accepted as narration.
Everything else reuses the existing pipeline — MediaManifest-era storyboard
contract, the pinned Easel composer, `qc_video.py` — so this adds an evidence
layer, not a second media engine.

Nothing here approves a video. The run always ends at
`PENDING_FOUNDER_REVIEW` with `production_ready: false`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
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

    return {
        "state": handoff["state"],
        "bundle_id": handoff["bundle_id"],
        "bundle_sha256": handoff["bundle_sha256"],
        "handoff": written.relative_to(project).as_posix(),
        "blockers": handoff["blockers"],
    }


def stage_sources(project: Path, config: Dict[str, Any]) -> Dict[str, Any]:
    artifacts = build_artifacts(config.get("source_refs") or [], repo_root=ROOT)
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
    for asset in declared + generated:
        path = (ROOT / asset["repo_path"]).resolve()
        try:
            path.relative_to(ROOT)
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
        if asset.get("permission") not in {"OWNED", "CREATED_BY_OWNER", "LICENSED"}:
            problems.append(f"{asset['id']}: permission {asset.get('permission')} is not usable")
            continue
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
    silence = work / "silence.wav"
    if not silence.is_file():
        proc = hidden_run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "anullsrc=r=24000:cl=mono", "-t", str(SILENCE_SECONDS),
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
                    narration_receipt: Optional[Path] = None) -> Dict[str, Any]:
    """Produce the voice track from an explicitly chosen source.

    ``sapi``     the offline Windows voice — a compatibility and diagnostic path;
    ``existing`` an audio file plus the receipt that binds it to this script;
    anything else is BLOCKED. A provider this build cannot reach must fail, not
    fall back to SAPI or edge-tts.
    """
    if provider not in ("sapi", "existing"):
        raise M5Blocked(
            f"narration provider {provider!r} is not reachable in this build; "
            f"refusing to fall back to the offline SAPI voice")

    text = "\n".join(line["narration"] for line in script["lines"])
    text_sha = _text_sha(text)
    target = project / "assets" / "voice" / "narration.wav"
    target.parent.mkdir(parents=True, exist_ok=True)

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
    """Make the visual timeline cover the spoken one, gaps included.

    Per-line durations alone omit the pauses between lines, so the rendered
    video ends before the audio does and the last words are cut. Extending the
    final shot by the uncovered remainder keeps the picture on screen for the
    whole narration without moving any earlier cut.
    """
    if not shots or not narration_lines:
        return shots
    timeline_end = max(
        float(line.get("start") or 0.0) + float(line.get("duration") or 0.0)
        for line in narration_lines
    )
    covered = sum(float(shot.get("duration") or 0.0) for shot in shots)
    if timeline_end > covered + 0.001:
        extended = round(float(shots[-1]["duration"]) + (timeline_end - covered), 3)
        shots[-1]["duration"] = extended
        shots[-1]["duration_s"] = extended
    return shots


def stage_storyboard(project: Path, config: Dict[str, Any], script: Dict[str, Any],
                     narration: Dict[str, Any], subtitles: Dict[str, Any],
                     assets: Dict[str, Any],
                     media_audio: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from contentops.media.storyboard_adapter import (
        StoryboardContractError, build_shots,
    )
    try:
        shots = build_shots(lines=script["lines"],
                            narration_lines=narration["lines"],
                            assets=assets, repo_root=ROOT)
    except StoryboardContractError as exc:
        raise M5Blocked(f"storyboard contract: {exc}")
    shots = _align_shots_to_narration(shots, narration["lines"])
    target = (config.get("target") or {}).get("resolution", "1080x1920")
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
        "generated_visuals": {"count": 0, "policy": "real_assets_only"},
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
          narration_receipt: Optional[Path] = None) -> Dict[str, Any]:
    if not project.is_dir():
        raise M5Blocked(f"project not found: {project}")
    config = _read_yaml(project / "project.yaml")
    slug = config.get("id") or project.name
    stages: Dict[str, Any] = {}

    bundle = stage_bundle(project, config)
    if bundle["state"] != "NOT_CONFIGURED":
        stages["bundle"] = bundle
    sources = stage_sources(project, config)
    stages["sources"] = {"count": sources["count"]}
    media = stage_media_use(project, config, adapter=media_adapter)
    stages["media_use"] = {
        "state": media["state"], "count": media["count"],
        "bgm": bool(media["audio"]["bgm"]), "sfx": len(media["audio"]["sfx"]),
    }
    assets = stage_assets(project, extra_assets=media["assets"])
    stages["assets"] = {"count": len(assets)}
    claims = stage_claims(project, sources["artifacts"])
    stages["claims"] = {"count": claims["count"]}
    script = stage_script(project, claims["ledger"], assets)
    stages["script"] = {"lines": script["lines"]}
    provider = (narration_provider
                or (config.get("narration") or {}).get("provider")
                or "sapi")
    narration = stage_narration(project, script["script"], provider=provider,
                                narration_audio=narration_audio,
                                narration_receipt=narration_receipt)
    stages["narration"] = {"duration_s": narration["duration_s"],
                           "engine": narration["engine"],
                           "provider": narration.get("voice_provider", provider)}
    subtitles = stage_subtitles(project, script["script"], narration)
    stages["subtitles"] = {"cues": subtitles["cues"]}
    storyboard = stage_storyboard(project, config, script["script"], narration, subtitles,
                                  assets, media_audio=media["audio"])
    stages["storyboard"] = {
        "shots": storyboard["shots"],
        "bgm": "bgm" in storyboard["storyboard"],
        "sfx": len(storyboard["storyboard"].get("sfx") or []),
    }

    if skip_compose:
        stages["compose"] = {"state": "NOT_RUN"}
        stages["qc"] = {"state": "NOT_RUN"}
        review = None
    else:
        compose = stage_compose(project, slug)
        stages["compose"] = {"state": "OK", "video": compose.get("video")}
        qc = stage_qc(project, slug)
        stages["qc"] = {"overall": qc["report"].get("overall"),
                        "audio": qc["report"]["m5_checks"]["audio_stream"]}
        review = stage_review(project, slug, qc, bundle=stages.get("bundle"))

    run = {
        "schema": RUN_SCHEMA,
        "project": project.relative_to(ROOT).as_posix() if project.is_relative_to(ROOT) else str(project),
        "stages": stages,
        "production_ready": False,
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
                        choices=("sapi", "existing"),
                        help="sapi = offline Windows voice (compatibility/diagnostic); "
                             "existing = reuse audio bound to this script by a receipt. "
                             "Any other provider is refused, never silently replaced")
    parser.add_argument("--narration-audio", default=None,
                        help="with --narration-provider existing: the audio file to reuse")
    parser.add_argument("--narration-receipt", default=None,
                        help="with --narration-provider existing: a prior narration.json "
                             "carrying text_sha256 and per-line timings")
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
                                       if args.narration_receipt else None))
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
