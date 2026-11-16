#!/usr/bin/env python3
"""P3-A regression + fail-closed evidence.

1. Param change: copy math01 spec, alter one trusted term, render to a scratch
   asset id and assert a NEW sha (exact re-render), then clean up the scratch.
2. DNA colour: a spec carrying style_variants / palette overrides is BLOCKED.
3. Missing trusted source binding: a spec without definition_source is BLOCKED.
4. Installed-runtime cannot fake verification: capability_matrix('manim') stays
   IMPLEMENTED_NOT_VERIFIED without receipt-backed render_evidence.
5. Easel input validation writes its receipt (one manifest, one timeline).

All results are recorded under receipts/. Nothing here grants production or
publication, and no receipt is fabricated -- each is derived from a real call.
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
from contentops.media import animation_backend as ab  # noqa: E402


def sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wb(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def render(spec: str, asset: str) -> dict:
    proc = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "manim_render.py"), str(PROJECT),
         "--render", "--spec", spec, "--placement-id", asset, "--asset-id", asset,
         "--account", "x-superplay-future-intelligence", "--purpose", "test", "--json"],
        cwd=str(ROOT), timeout=900,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
    )
    try:
        return json.loads(proc.stdout or "{}")
    except ValueError:
        return {"execution": {"state": "FAILED", "error": (proc.stdout or "")[-500:]},
                "returncode": proc.returncode}


def param_change_regression() -> dict:
    """Render a changed spec in an isolated temp project so the accepted project
    manifest is never polluted by the scratch asset."""
    import shutil
    import tempfile

    base = json.loads((PROJECT / "specs" / "math01.json").read_text(encoding="utf-8"))
    original_sha = sha(PROJECT / "assets" / "generated" / "manim" / "math01.mp4")
    original_fp = json.loads((PROJECT / "receipts" / "manim-math01.json").read_text(encoding="utf-8")).get("fingerprint")

    with tempfile.TemporaryDirectory(prefix="p3-manim-regen-") as temp:
        tmp_project = Path(temp) / PROJECT.name
        # Copy only the inputs the render entry needs.
        for rel in ("project.yaml", "specs", "sources", "script"):
            src = PROJECT / rel
            dst = tmp_project / rel
            if src.is_dir():
                shutil.copytree(src, dst)
            elif src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        changed = json.loads(json.dumps(base))
        changed["props"]["terms"][0] = changed["props"]["terms"][0] + "*"
        wb(tmp_project / "specs" / "math01.json", changed)

        # The copied inventory already lists math01 at the real project's path;
        # in the temp project that path differs, so strip generated rows first.
        assets_path = tmp_project / "sources" / "assets.json"
        assets_doc = json.loads(assets_path.read_text(encoding="utf-8"))
        assets_doc["assets"] = [row for row in assets_doc.get("assets", [])
                                if not row.get("generated")]
        wb(assets_path, assets_doc)
        script_assets_path = tmp_project / "script" / "assets.json"
        script_doc = json.loads(script_assets_path.read_text(encoding="utf-8"))
        script_doc["assets"] = {}
        wb(script_assets_path, script_doc)

        proc = hidden_run(
            [python_executable(), str(ROOT / "scripts" / "manim_render.py"), str(tmp_project),
             "--render", "--spec", "specs/math01.json", "--placement-id", "math01",
             "--asset-id", "math01", "--account", "x-superplay-future-intelligence",
             "--purpose", "test", "--json"],
            cwd=str(ROOT), timeout=900,
            env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
        )
        try:
            result = json.loads(proc.stdout or "{}")
        except ValueError:
            result = {"execution": {"state": "FAILED"}, "error": (proc.stdout or "")[-400:]}

    new_sha = result.get("sha256")
    out = {
        "check": "parameter_change_exact_rerender",
        "isolated_project": True,
        "original_sha256": original_sha,
        "rerender_sha256": new_sha,
        "state": result.get("execution", {}).get("state"),
        "distinct_sha": bool(new_sha and new_sha != original_sha),
        "original_fingerprint": original_fp,
        "rerender_fingerprint": result.get("fingerprint"),
    }
    out["pass"] = (out["state"] == "EXECUTED" and out["distinct_sha"]
                   and out["original_fingerprint"] != out["rerender_fingerprint"])
    return out


def fail_closed_spec(name: str, mutate) -> dict:
    base = json.loads((PROJECT / "specs" / "math01.json").read_text(encoding="utf-8"))
    mutate(base)
    spec_path = PROJECT / "specs" / f"_{name}.json"
    wb(spec_path, base)
    asset = f"block_{name}"
    result = render(f"specs/_{name}.json", asset)
    decision = result.get("decision") or {}
    code = decision.get("code") or (result.get("execution") or {}).get("error")
    state = (result.get("execution") or {}).get("state")
    spec_path.unlink(missing_ok=True)
    return {"check": name, "state": state, "code": code,
            "blocked": state == "BLOCKED", "production_ready": False}


def main() -> int:
    evidence: dict = {"schema": "contentops.p3-manim-regression/v1"}

    evidence["param_change"] = param_change_regression()

    def dna_override(doc):
        doc["props"]["style_variants"] = {"accent": "#FF0000"}
    evidence["dna_override_blocked"] = fail_closed_spec("dna_override", dna_override)

    def no_source(doc):
        doc["props"].pop("definition_source", None)
    evidence["missing_source_blocked"] = fail_closed_spec("missing_source", no_source)

    matrix = ab.capability_matrix(ROOT)
    row = matrix["backends"]["manim"]
    evidence["capability_not_verified_by_install"] = {
        "check": "installed_runtime_does_not_promote_verify",
        "state": row["state"], "render_verified": row["render_verified"],
        "execution_authorized": row["execution_authorized"],
        "publish_authorized": row["publish_authorized"],
        "pass": (row["state"] == "IMPLEMENTED_NOT_VERIFIED"
                 and row["render_verified"] is False
                 and row["execution_authorized"] is False
                 and row["publish_authorized"] is False),
    }

    proc = hidden_run(
        [python_executable(), str(ROOT / "scripts" / "manim_render.py"), str(PROJECT),
         "--validate-easel", "--asset-id", "math01", "--json"],
        cwd=str(ROOT), timeout=60,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
    )
    try:
        evidence["easel_input_validation"] = json.loads(proc.stdout or "{}")
    except ValueError:
        evidence["easel_input_validation"] = {"state": "BLOCKED", "detail": (proc.stdout or "")[-300:]}

    checks = [
        evidence["param_change"]["pass"],
        evidence["dna_override_blocked"]["blocked"],
        evidence["missing_source_blocked"]["blocked"],
        evidence["capability_not_verified_by_install"]["pass"],
        evidence["easel_input_validation"].get("accepted_by_easel") is True,
    ]
    evidence["accepted"] = all(checks)
    wb(PROJECT / "receipts" / "regression-and-blocks.json", evidence)
    print("regression accepted:", evidence["accepted"])
    for key in ("param_change", "capability_not_verified_by_install"):
        print(key, "pass=", evidence[key]["pass"])
    return 0 if evidence["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
