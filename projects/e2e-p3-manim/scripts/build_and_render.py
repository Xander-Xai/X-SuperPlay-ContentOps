#!/usr/bin/env python3
"""P3-A acceptance harness: render both Manim shots through the real adapter.

Runs from anywhere:
    python projects/e2e-p3-manim/scripts/build_and_render.py

Rebuilds the trusted source + specs with exact SHA binding, renders each shot
through scripts/manim_render.py (official Manim CLI from the isolated venv),
then writes a run summary. A second invocation must REUSE both shots with
identical SHAs. No clip is production-ready or publishable.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from process_utils import hidden_run, python_executable  # noqa: E402


def sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def render(spec: str, asset: str, purpose: str = "test") -> dict:
    proc = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "manim_render.py"), str(PROJECT),
         "--render", "--spec", spec, "--placement-id", asset, "--asset-id", asset,
         "--account", "x-superplay-future-intelligence", "--purpose", purpose, "--json"],
        cwd=str(ROOT), timeout=900,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
    )
    try:
        return json.loads(proc.stdout or "{}")
    except ValueError:
        return {"execution": {"state": "FAILED", "error": (proc.stdout or proc.stderr or "")[-600:]},
                "returncode": proc.returncode}


SHOTS = [("math01.json", "math01"), ("attn01.json", "attn01")]


def main() -> int:
    results = []
    for spec, asset in SHOTS:
        result = render("specs/" + spec, asset)
        execution = result.get("execution") or {}
        row = {
            "asset_id": asset,
            "spec": spec,
            "spec_sha256": sha(PROJECT / "specs" / spec),
            "state": execution.get("state"),
            "reused": execution.get("reused"),
            "sha256": result.get("sha256"),
            "fingerprint": result.get("fingerprint"),
            "easel_input": result.get("easel_input", {}).get("state"),
            "governance": {
                "generated": True, "evidence_capable": False,
                "production_ready": False, "publish_authorized": False,
            },
        }
        if execution.get("state") not in ("EXECUTED", "REUSED"):
            row["error"] = execution.get("error")
        write_json(PROJECT / "receipts" / f"run-{asset}.json", row)
        results.append(row)
        print(f"[{asset}] {execution.get('state')} sha={(result.get('sha256') or '')[:12]}")

    summary = {
        "schema": "contentops.p3-manim-run/v1",
        "backend": "manim",
        "backend_version": "0.22.1",
        "account_id": "x-superplay-future-intelligence",
        "render_entry": "scripts/manim_render.py",
        "scene_module": "scripts/manim_scenes.py",
        "runtime": "isolated venv via runtime/manim.lock.json",
        "generated": True, "evidence_capable": False, "evidence_use": "VISUAL_SUPPORT",
        "counts_as_real_recording": False, "production_ready": False,
        "publish_authorized": False, "human_review": "PENDING_FOUNDER_REVIEW",
        "easel_is_compositor": True,
        "shots": results,
        "accepted": all(r["state"] in ("EXECUTED", "REUSED") and r.get("sha256")
                        and r.get("easel_input") == "ACCEPTED_AS_VISUAL_SUPPORT"
                        for r in results),
    }
    write_json(PROJECT / "receipts" / "run-summary.json", summary)
    print("accepted:", summary["accepted"])
    return 0 if summary["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
