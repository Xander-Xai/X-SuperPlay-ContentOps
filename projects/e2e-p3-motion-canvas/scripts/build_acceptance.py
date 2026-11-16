#!/usr/bin/env python3
"""Build honest TEST_ONLY acceptance receipts for the Motion Canvas extension.

This never renders a video and never fabricates media evidence. It proves:
template contracts, DNA palette, compile capability, cache/parameter identity,
failure blocking, and the exact EDITOR_EXPORT_REQUIRED boundary. Media facts
(MP4/frames/ffprobe/SHA) stay null until a human editor export is imported.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from process_utils import hidden_run  # noqa: E402
from contentops.media import animation_backend as ab  # noqa: E402
import motion_canvas_adapter as adapter  # noqa: E402

EXTENSION = ROOT / "extensions" / "motion-canvas"
RECEIPTS = PROJECT / "receipts"
JOBS = (
    {"asset_id": "mc-arch01", "placement_id": "mc-arch01",
     "spec": "motion/specs/animated-system-graph.json"},
    {"asset_id": "mc-state01", "placement_id": "mc-state01",
     "spec": "motion/specs/agent-state-machine.json"},
)


def _write(name: str, payload: dict) -> None:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    (RECEIPTS / name).write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def _call_adapter(args: list[str]) -> tuple[int, dict]:
    capture = io.StringIO()
    with contextlib.redirect_stdout(capture):
        code = adapter.main([str(PROJECT), *args])
    try:
        payload = json.loads(capture.getvalue())
    except ValueError:
        payload = {"stdout": capture.getvalue()[-500:]}
    return code, payload


def _compile_evidence() -> dict:
    entrypoints = {
        "tsc": ["node", str(EXTENSION / "node_modules" / "typescript" / "bin" / "tsc"),
                "--noEmit"],
        "vite_build": ["node", str(EXTENSION / "node_modules" / "vite" / "bin" / "vite.js"),
                       "build"],
    }
    results = {}
    for name, command in entrypoints.items():
        node_modules = (EXTENSION / "node_modules" / "@motion-canvas" / "core"
                        / "package.json").is_file()
        if not node_modules:
            results[name] = {"state": "NOT_RUN", "reason": "node_modules is absent; "
                             "npm install has not been run in this checkout"}
            continue
        proc = hidden_run(command, cwd=str(EXTENSION), timeout=300)
        results[name] = {
            "command": ["node", "node_modules/typescript/bin/tsc --noEmit"
                        if name == "tsc" else "node_modules/vite/bin/vite.js build"],
            "exit_code": proc.returncode,
            "stdout_tail": (proc.stdout or "").strip()[-400:],
            "stderr_tail": (proc.stderr or "").strip()[-400:],
            "state": "COMPILE_PASS" if proc.returncode == 0 else "COMPILE_FAILED",
        }
    # vite build writes dist/; remove the generated artifact before committing.
    dist = EXTENSION / "dist"
    if dist.is_dir():
        import shutil
        shutil.rmtree(dist)
    return {
        "schema": "contentops.motion-canvas-compile-evidence/v1",
        "created_at": adapter._now(),
        "meaning": ("A successful tsc/vite build proves the pinned project and "
                    "the two scenes compile. It is NOT a render, NOT an MP4, and "
                    "never promotes the backend to VERIFIED."),
        "render_verified": False,
        "commands": results,
    }


def _parameter_regression(runtime: dict) -> dict:
    dna = adapter._load_dna("x-superplay-future-intelligence")
    palette = ab.palette_from_dna(dna)
    rows = []
    for job in JOBS:
        spec_path, spec = adapter._validate_spec(PROJECT, job["spec"])
        props = {**(spec.get("props") or {}), "palette": palette}
        base = adapter._fingerprint(PROJECT, spec_path, spec, dna, palette,
                                    job["placement_id"], job["asset_id"],
                                    "production", runtime)
        changed = json.loads(json.dumps(spec, ensure_ascii=False))
        if spec["template"] == "animated_system_graph":
            changed["props"]["steps"][0]["caption"] = "参数变更后的说明"
        else:
            changed["props"]["state_steps"][0]["caption"] = "参数变更后的说明"
        altered = adapter._fingerprint(PROJECT, spec_path, changed, dna, palette,
                                       job["placement_id"], job["asset_id"],
                                       "production", runtime)
        purpose_changed = adapter._fingerprint(PROJECT, spec_path, spec, dna, palette,
                                               job["placement_id"], job["asset_id"],
                                               "test", runtime)
        rows.append({
            "asset_id": job["asset_id"],
            "baseline_fingerprint": base,
            "parameter_changed_fingerprint": altered,
            "purpose_changed_fingerprint": purpose_changed,
            "parameters_change_identity": base != altered,
            "purpose_changes_identity": base != purpose_changed,
        })
    return {
        "schema": "contentops.motion-canvas-cache-regression/v1",
        "created_at": adapter._now(),
        "meaning": ("A parameter or purpose change must produce a different "
                    "fingerprint, so a stale MP4 can never be replayed under a "
                    "new identity. No render cache was created by this check."),
        "rows": rows,
        "pass": all(row["parameters_change_identity"] and row["purpose_changes_identity"]
                    for row in rows),
    }


def main() -> int:
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    runtime = adapter._runtime()

    preflight_code, preflight = _call_adapter(["--preflight"])
    _write("motion-canvas-preflight.json", preflight)

    prepared = []
    for job in JOBS:
        code, receipt = _call_adapter([
            "--prepare", "--spec", job["spec"], "--placement-id", job["placement_id"],
            "--asset-id", job["asset_id"], "--purpose", "test"])
        prepared.append({"asset_id": job["asset_id"], "exit_code": code,
                         "code": receipt.get("code"),
                         "render_verified": receipt.get("render_verified")})
        if code != 1 or receipt.get("code") != "EDITOR_EXPORT_REQUIRED":
            raise SystemExit("prepare must block with EDITOR_EXPORT_REQUIRED")

    invalid_spec = PROJECT / "work" / "motion-canvas" / "invalid-spec.json"
    invalid_spec.parent.mkdir(parents=True, exist_ok=True)
    invalid_spec.write_bytes((json.dumps({
        "template": "animated_system_graph", "duration_s": 9.0,
        "width": 1080, "height": 1920, "fps": 30, "title": "bad",
        "props": {"title": "bad"},
    }, ensure_ascii=False) + "\n").encode("utf-8"))
    failure_code, failure = _call_adapter([
        "--prepare", "--spec", "work/motion-canvas/invalid-spec.json",
        "--placement-id", "mc-invalid", "--asset-id", "mc-invalid"])
    failure_receipt = RECEIPTS / "motion-canvas-mc-invalid-block.json"
    failure_receipt.write_bytes(
        (json.dumps({**failure, "prepare_exit_code": failure_code},
                    ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    invalid_spec.unlink()

    compile_evidence = _compile_evidence()
    _write("compile-evidence.json", compile_evidence)
    regression = _parameter_regression(runtime)
    _write("cache-regression.json", regression)

    matrix = ab.capability_matrix(
        ROOT, block_state={"motion-canvas": "EDITOR_EXPORT_REQUIRED"})
    _write("capability-matrix.json", {
        "schema": ab.CAPABILITY_SCHEMA,
        "created_at": adapter._now(),
        "motion_canvas": matrix["backends"]["motion-canvas"],
        "note": ("Lock file and compile capability do not promote a backend. "
                 "Only a receipt-backed render_evidence entry can do that, and "
                 "no such MP4 exists in this TEST_ONLY project."),
    })

    # Media facts stay explicitly absent. Never write a fabricated SHA, ffprobe
    # reading, or first/mid/last frame for an MP4 that does not exist.
    pending = []
    for job in JOBS:
        pending.append({
            "asset_id": job["asset_id"],
            "expected_output": f"project://assets/generated/motion-canvas/{job['asset_id']}.mp4",
            "first_frame": None, "mid_frame": None, "last_frame": None,
            "ffprobe": None, "sha256": None,
            "state": "EDITOR_EXPORT_REQUIRED",
            "reason": ("No editor-exported MP4 exists. Frames, ffprobe and SHA-256 "
                       "will be filled only by --import-editor-export from a real "
                       "editor export; null here is an honest absence, not a failure "
                       "of the template."),
        })
    _write("pending-media-evidence.json", {
        "schema": "contentops.motion-canvas-pending-media/v1",
        "created_at": adapter._now(),
        "clips": pending,
        "render_verified": False,
    })

    summary = {
        "schema": "contentops.motion-canvas-acceptance/v1",
        "created_at": adapter._now(),
        "project": PROJECT.relative_to(ROOT).as_posix(),
        "backend_version": ab.MOTION_CANVAS_VERSION,
        "preflight": {"exit_code": preflight_code, "code": preflight.get("code"),
                      "render_verified": preflight.get("render_verified")},
        "prepared_jobs": prepared,
        "failure_block": {"exit_code": failure_code, "code": failure.get("code")},
        "compile": {name: result.get("state") for name, result
                    in compile_evidence["commands"].items()},
        "parameter_regression_pass": regression["pass"],
        "media_state": "EDITOR_EXPORT_REQUIRED",
        "render_verified": False,
        "generated": True,
        "evidence_capable": False,
        "counts_as_real_recording": False,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    _write("run-summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
