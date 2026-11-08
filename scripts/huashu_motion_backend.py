#!/usr/bin/env python3
"""Render a project-local huashu-motion film as one M5 visual asset.

The upstream CLI/runtime is installed separately and is never copied into the
repository. This adapter only runs its local, non-paid renderer; publication
and source evidence remain governed by the existing M5 stages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT / "src", ROOT / "scripts"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from process_utils import hidden_run, python_executable  # noqa: E402


class BackendError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> Dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackendError(f"invalid JSON input {path.name}: {type(exc).__name__}") from None
    if not isinstance(value, dict):
        raise BackendError(f"expected JSON object in {path.name}")
    return value


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_motion_project(project: Path, value: str) -> Path:
    """Only use film projects stored under this ContentOps project's motion tree."""
    candidate = (project / value).resolve()
    allowed = (project / "motion" / "huashu-motion").resolve()
    try:
        candidate.relative_to(allowed)
    except ValueError:
        raise BackendError("Huashu Motion project must stay under motion/huashu-motion/") from None
    if not (candidate / "index.html").is_file():
        raise BackendError("Huashu Motion project has no index.html")
    for relative in ("vendor/gsap.min.js",):
        if not (candidate / relative).is_file():
            raise BackendError(f"Huashu Motion project is missing {relative}")
    return candidate


def resolve_runtime() -> Path:
    configured = (os.environ.get("CONTENTOPS_HUASHU_MOTION_RUNTIME")
                  or os.environ.get("HUASHU_MOTION_RUNTIME"))
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend([ROOT / ".runtime" / "huashu-motion", ROOT.parent / ".runtime" / "huashu-motion"])
    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / "cli" / "om.js").is_file() and (candidate / "package.json").is_file():
            return candidate
    raise BackendError("Huashu Motion runtime is not installed; set CONTENTOPS_HUASHU_MOTION_RUNTIME")


def _runtime_facts(runtime: Path) -> Dict[str, str]:
    package = _json(runtime / "package.json")
    node = hidden_run(["node", "--version"], cwd=str(runtime), timeout=30)
    if node.returncode != 0 or not re.fullmatch(r"v\d+\.\d+\.\d+\s*", node.stdout or ""):
        raise BackendError("Node.js is unavailable for Huashu Motion")
    major = int((node.stdout or "v0").strip()[1:].split(".", 1)[0])
    if major < 22:
        raise BackendError("Huashu Motion requires Node.js 22 or later")
    commit = hidden_run(["git", "rev-parse", "HEAD"], cwd=str(runtime), timeout=30)
    return {
        "version": str(package.get("version") or "unknown"),
        "node": (node.stdout or "").strip(),
        "commit": (commit.stdout or "").strip() if commit.returncode == 0 else "unversioned",
    }


def _film_hash(project_dir: Path) -> str:
    digest = hashlib.sha256()
    # The CLI appends render history under .om/ on every invocation; that log
    # is output metadata, not an input to the frames, so it must not defeat cache reuse.
    excluded = {"out", ".om", ".git", "node_modules", "cache", "tmp"}
    files = [p for p in project_dir.rglob("*") if p.is_file()
             and not any(part.casefold() in excluded for part in p.relative_to(project_dir).parts)]
    for path in sorted(files, key=lambda item: item.relative_to(project_dir).as_posix().casefold()):
        digest.update(path.relative_to(project_dir).as_posix().encode("utf-8"))
        digest.update(bytes.fromhex(_sha(path)))
    return digest.hexdigest()


def _probe(path: Path) -> Dict[str, Any]:
    proc = hidden_run([
        "ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path),
    ], timeout=60)
    if proc.returncode != 0:
        raise BackendError("ffprobe could not read Huashu Motion output")
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError:
        raise BackendError("ffprobe returned invalid JSON") from None
    stream = next((row for row in data.get("streams", []) if row.get("codec_type") == "video"), None)
    if not stream:
        raise BackendError("Huashu Motion output has no video stream")
    result = {
        "codec": stream.get("codec_name"),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": stream.get("avg_frame_rate"),
        "duration_s": float((data.get("format") or {}).get("duration") or stream.get("duration") or 0),
        "has_audio": any(row.get("codec_type") == "audio" for row in data.get("streams", [])),
        "bytes": path.stat().st_size,
    }
    if result["codec"] != "h264" or (result["width"], result["height"]) != (1080, 1920):
        raise BackendError(
            f"Huashu Motion must render 1080x1920 H.264; got {result['width']}x{result['height']} {result['codec']}"
        )
    if result["duration_s"] <= 0 or result["bytes"] < 100_000:
        raise BackendError("Huashu Motion output is empty or has no duration")
    return result


def render(project: Path, film_arg: str, asset_id: str, placement_id: str,
           account_id: str = "", expected_duration_s: Optional[float] = None) -> Dict[str, Any]:
    project = project.resolve()
    if not project.is_relative_to((ROOT / "projects").resolve()):
        raise BackendError("M5 project must be inside projects/")
    film = resolve_motion_project(project, film_arg)
    runtime = resolve_runtime()
    facts = _runtime_facts(runtime)
    script = _json(project / "script" / "script.json")
    claims = _json(project / "script" / "claims.json")
    sources = _json(project / "sources" / "source-refs.json")
    line = next((row for row in script.get("lines", []) if str(row.get("id")) == placement_id), None)
    if not line:
        raise BackendError(f"placement {placement_id!r} is not present in script.json")
    inputs = {
        "script_sha256": _sha(project / "script" / "script.json"),
        "claims_sha256": _sha(project / "script" / "claims.json"),
        "source_refs_sha256": _sha(project / "sources" / "source-refs.json"),
        "film_sha256": _film_hash(film),
        "runtime_commit": facts["commit"],
    }
    fingerprint = hashlib.sha256(json.dumps(
        {"inputs": inputs, "asset_id": asset_id, "placement_id": placement_id},
        sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    output = project / "assets" / "generated" / "huashu-motion" / f"{asset_id}.mp4"
    receipt_path = project / "receipts" / f"huashu-motion-{asset_id}.json"
    previous = None
    if output.is_file() and receipt_path.is_file():
        try:
            prior = _json(receipt_path)
            if (prior.get("fingerprint") == fingerprint
                    and prior.get("output_sha256") == _sha(output)):
                probe = _probe(output)
                if expected_duration_s is None or abs(probe["duration_s"] - expected_duration_s) <= 0.15:
                    previous = prior
        except (BackendError, OSError, ValueError):
            previous = None
    if previous:
        return {"state": "REUSED", "reused": True, "output": output,
                "receipt": receipt_path, "technical_qc": previous["technical_qc"],
                "fingerprint": fingerprint, "runtime": facts}

    check = hidden_run(["node", str(runtime / "cli" / "om.js"), "check", str(film), "--source", "--json"],
                       cwd=str(runtime), timeout=600)
    if check.returncode != 0:
        raise BackendError(f"Huashu Motion source/structure check failed: {(check.stderr or check.stdout)[-700:]}")
    started = time.monotonic()
    proc = hidden_run(["node", str(runtime / "cli" / "om.js"), "render", str(film),
                       "--format", "mp4", "--fps", "30", "--workers", "1", "--silent"],
                      cwd=str(runtime), timeout=3600)
    elapsed = round(time.monotonic() - started, 3)
    if proc.returncode != 0:
        raise BackendError(f"Huashu Motion render failed: {(proc.stderr or proc.stdout)[-900:]}")
    matches = re.findall(r"(?:[A-Za-z]:[\\/]|/)[^\r\n]*?\.mp4", proc.stdout or "", re.IGNORECASE)
    rendered = Path(matches[-1].strip().strip('"')) if matches else None
    if rendered is None or not rendered.is_file():
        raise BackendError("Huashu Motion CLI exited successfully but did not report an MP4 path")
    technical = _probe(rendered)
    if expected_duration_s is not None and abs(technical["duration_s"] - expected_duration_s) > 0.15:
        raise BackendError(
            f"render duration {technical['duration_s']:.3f}s does not match narration {expected_duration_s:.3f}s"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    staged = output.with_suffix(".tmp.mp4")
    shutil.copy2(rendered, staged)
    staged.replace(output)
    digest = _sha(output)
    repo_path = output.relative_to(ROOT).as_posix()
    receipt = {
        "schema": "contentops.video-receipt/v1",
        "adapter": "contentops.huashu-motion-backend/v1",
        "created_at": _now(), "account_id": account_id,
        "engine": "huashu-motion", "runtime": facts,
        "placement_id": placement_id, "asset_id": asset_id,
        "script_sha256": inputs["script_sha256"],
        "claims_sha256": inputs["claims_sha256"],
        "source_refs_sha256": inputs["source_refs_sha256"],
        "film_sha256": inputs["film_sha256"],
        "fingerprint": fingerprint, "output_sha256": digest,
        "output": {"path": f"project://{output.relative_to(project).as_posix()}", "repo_path": repo_path},
        "technical_qc": technical, "elapsed_s": elapsed,
        "generated": True, "evidence_capable": False,
        "evidence_use": "VISUAL_SUPPORT", "human_review": "PENDING_FOUNDER_REVIEW",
        "production_ready": False, "publish_authorized": False,
        "note": "Huashu Motion visuals are explanatory support, not execution evidence.",
    }
    _write_json(receipt_path, receipt)
    _write_json(output.with_suffix(".mp4.receipt.json"), receipt)

    assets_path = project / "sources" / "assets.json"
    asset_doc = _json(assets_path)
    entries = list(asset_doc.get("assets") or [])
    item = {"id": asset_id, "type": "GENERATED_VIDEO", "repo_path": repo_path,
            "sha256": digest, "permission": "CREATED_BY_OWNER",
            "usage_scope": "VISUAL_SUPPORT only", "origin": "huashu-motion local code render",
            "notes": "Generated visual; source claims remain separately registered."}
    old = next((row for row in entries if row.get("id") == asset_id), None)
    if old and old.get("repo_path") not in (repo_path, None):
        raise BackendError(f"asset id {asset_id} already points to a different file")
    if old:
        entries[entries.index(old)] = {**old, **item}
    else:
        entries.append(item)
    asset_doc["assets"] = entries
    _write_json(assets_path, asset_doc)
    script_assets_path = project / "script" / "assets.json"
    script_assets = _json(script_assets_path) if script_assets_path.is_file() else {"assets": {}}
    mapped = script_assets.get("assets")
    if not isinstance(mapped, dict):
        raise BackendError("script/assets.json does not contain an assets object")
    mapped[asset_id] = {"path": f"project://{output.relative_to(project).as_posix()}",
                        "sha256": digest, "evidence_use": "VISUAL_SUPPORT", "generated": True}
    script_assets["assets"] = mapped
    _write_json(script_assets_path, script_assets)
    return {"state": "EXECUTED", "reused": False, "output": output,
            "receipt": receipt_path, "technical_qc": technical,
            "fingerprint": fingerprint, "runtime": facts, "elapsed_s": elapsed}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--film", required=True, help="project-relative Huashu Motion film directory")
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--placement-id", required=True)
    parser.add_argument("--account-id", default="")
    parser.add_argument("--expected-duration", type=float)
    args = parser.parse_args(argv)
    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    try:
        result = render(project, args.film, args.asset_id, args.placement_id,
                        args.account_id, args.expected_duration)
        public_result = {**result, "output": str(result["output"]),
                         "receipt": str(result["receipt"])}
        print(json.dumps({"execution": {"state": result["state"],
                                         "operation": "render", "reused": result["reused"],
                                         "adapter_receipt": public_result},
                          "receipt": f"project://{result['receipt'].relative_to(project).as_posix()}",
                          "production_ready": False, "publish_authorized": False},
                         ensure_ascii=False))
        return 0
    except (BackendError, OSError, ValueError, KeyError) as exc:
        print(json.dumps({"execution": {"state": "FAILED", "operation": "render",
                                         "external_effect": False, "error": str(exc)},
                          "production_ready": False, "publish_authorized": False},
                         ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
