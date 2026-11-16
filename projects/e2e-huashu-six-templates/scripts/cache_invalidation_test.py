#!/usr/bin/env python3
"""P1.3: parameter edit invalidates only the affected shot's Huashu cache.

Uses the real adapter CLI (huashu_motion_adapter.py) end to end. It renders two
shots, edits one shot's node label in its spec, re-renders both, and asserts the
edited shot EXECUTED with a new SHA while the untouched shot REUSED with an
identical SHA. All receipts stay TEST_ONLY with governance flags unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

import huashu_motion_adapter as adapter  # noqa: E402
from process_utils import hidden_run, python_executable  # noqa: E402


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(spec: Path, placement: str, asset: str) -> dict:
    proc = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "huashu_motion_adapter.py"),
         str(PROJECT), "--render",
         "--spec", spec.relative_to(PROJECT).as_posix(),
         "--placement-id", placement, "--asset-id", asset, "--json"],
        cwd=str(ROOT), timeout=1800, env=dict(os.environ, PYTHONUTF8="1",
                                              PYTHONIOENCODING="utf-8"))
    out = proc.stdout or "{}"
    try:
        return json.loads(out)
    except ValueError:
        return {"execution": {"state": "FAILED", "error": out[-800:]}}


def state_of(result: dict) -> str:
    return str(result.get("execution", {}).get("state") or "UNKNOWN")


def sha_of(result: dict) -> str:
    return str(result.get("execution", {}).get("adapter_receipt", {})
               .get("output", {}).get("output_sha256") or "")


def fp_of(result: dict) -> str:
    return str(result.get("execution", {}).get("adapter_receipt", {})
               .get("fingerprint") or "")


def main() -> int:
    specs = sorted((PROJECT / "motion" / "auto" / "specs").glob("arch01-*.json"))
    specs2 = sorted((PROJECT / "motion" / "auto" / "specs").glob("state01-*.json"))
    assert specs and specs2, "specs missing; run build_and_render.py first"
    arch_spec, state_spec = specs[0], specs2[0]

    # Remove canonical receipts so this test starts from a clean cache.
    for asset in ("huashu-arch01", "huashu-state01"):
        receipt = PROJECT / "receipts" / f"huashu-{asset}.json"
        if receipt.exists():
            receipt.unlink()

    a1 = render(arch_spec, "arch01", "huashu-arch01")
    s1 = render(state_spec, "state01", "huashu-state01")
    a1_sha, s1_sha = sha_of(a1), sha_of(s1)
    assert state_of(a1) == "EXECUTED", state_of(a1)
    assert state_of(s1) == "EXECUTED", state_of(s1)

    # Cache replay: both REUSED, same SHA.
    a2 = render(arch_spec, "arch01", "huashu-arch01")
    s2 = render(state_spec, "state01", "huashu-state01")
    assert state_of(a2) == "REUSED", state_of(a2)
    assert state_of(s2) == "REUSED", state_of(s2)
    assert sha_of(a2) == a1_sha and sha_of(s2) == s1_sha

    # Edit ONE parameter (a node label) in the architecture spec only.
    original = json.loads(arch_spec.read_text(encoding="utf-8"))
    sha_before_edit = sha(arch_spec)
    changed = json.loads(json.dumps(original))
    edited = False
    for cue in changed.get("cues", []):
        if cue.get("kind") == "draw" and cue.get("text") == "Query":
            cue["text"] = "Question"
            edited = True
            break
    assert edited, "no editable node label found"
    arch_spec.write_text(json.dumps(changed, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    assert sha(arch_spec) != sha_before_edit, "spec edit did not change its hash"

    a3 = render(arch_spec, "arch01", "huashu-arch01")
    s3 = render(state_spec, "state01", "huashu-state01")
    result = {
        "schema": "contentops.animation-cache-regression/v1",
        "account_id": "x-superplay-future-intelligence",
        "edited_shot": {"placement": "arch01", "parameter": "nodes[Query]->Question",
                        "before_state": state_of(a2), "after_state": state_of(a3),
                        "before_sha": a1_sha, "after_sha": sha_of(a3),
                        "before_fp": fp_of(a2), "after_fp": fp_of(a3)},
        "untouched_shot": {"placement": "state01", "state": state_of(s3),
                           "before_sha": s1_sha, "after_sha": sha_of(s3),
                           "fp_stable": fp_of(s2) == fp_of(s3)},
        "pass": (state_of(a3) == "EXECUTED" and sha_of(a3) != a1_sha
                 and fp_of(a3) != fp_of(a2)
                 and state_of(s3) == "REUSED" and sha_of(s3) == s1_sha
                 and fp_of(s2) == fp_of(s3)),
        "generated": True, "evidence_capable": False,
        "production_ready": False, "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    (PROJECT / "receipts" / "cache-invalidation-test.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    # Restore the spec so the acceptance project remains reproducible.
    arch_spec.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
