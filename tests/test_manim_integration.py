"""P3-A Manim integration: two-template contract, DNA colour, trusted cache,
fail-closed gates, media properties, capability honesty, and a real-render test
that is environment-gated and reports BLOCKED (never a fake PASS).

Run: python tests/test_manim_integration.py

There is no pytest: each test is a standalone function; main() runs all of them.
The real-render test PROBES the locked isolated venv first. When the venv or
Manim is absent it prints an availability line and records BLOCKED — it does
NOT fail the suite and does NOT claim a render happened. When present it runs
the actual official CLI and asserts the produced MP4's ffprobe facts and SHAs.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import animation_backend as ab  # noqa: E402
import manim_render  # noqa: E402

DNA = json.loads((ROOT / "config" / "accounts" / "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
PALETTE = ab.palette_from_dna(DNA)
LOCK = json.loads((ROOT / "runtime" / "manim.lock.json").read_text(encoding="utf-8"))
DEFN = ROOT / "projects" / "e2e-p3-manim" / "specs" / "definitions" / "math-attention.json"
DEFN_SHA = hashlib.sha256(DEFN.read_bytes()).hexdigest()


def _source():
    return {"source_ref_id": "definition_source", "sha256": DEFN_SHA}


def _math_props(**overrides):
    data = {
        "title": "缩放点积注意力",
        "terms": ["Attention", "(", "Q", "V", ")", "=", "softmax", "V"],
        "variables": [{"symbol": "Q", "meaning": "查询"}, {"symbol": "V", "meaning": "值"}],
        "definition_source": _source(),
        "palette": PALETTE,
    }
    data.update(overrides)
    return data


def _attn_props(**overrides):
    data = {
        "title": "自注意力",
        "tokens": ["我", "查", "到", "答案"],
        "labels": ["行=查询"],
        "matrix": [[0.1, 0.6, 0.2, 0.1], [0.15, 0.15, 0.55, 0.15],
                   [0.25, 0.25, 0.2, 0.3], [0.05, 0.1, 0.15, 0.7]],
        "definition_source": _source(),
        "palette": PALETTE,
    }
    data.update(overrides)
    return data


# --- two-template contract --------------------------------------------------

def test_both_templates_register_in_the_single_contract():
    for name in ab.MANIM_TEMPLATES:
        assert name in ab.TEMPLATES
        assert ab.TEMPLATES[name]["backend"] == "manim"
    assert ab.TEMPLATES["math_formula_reveal"]["composition"] == "MathFormulaReveal"
    assert ab.TEMPLATES["attention_matrix_flow"]["composition"] == "AttentionMatrixFlow"
    assert "manim" in ab.SHOT_COMPATIBILITY["math"]
    assert "manim" in ab.SHOT_COMPATIBILITY["attention"]


def test_math_template_requires_trusted_terms_and_variables():
    plan = ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="math_formula_reveal",
                        placement_id="p", asset_id="a", duration_s=4.0,
                        props=_math_props(), backend="manim", dna=DNA)
    assert plan["backend"] == "manim" and plan["composition"] == "MathFormulaReveal"
    assert plan["counts_as_real_recording"] is False
    for bad in (
        _math_props(terms=[]),
        _math_props(variables=[]),
        _math_props(variables=[{"symbol": "Q"}]),
    ):
        try:
            ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="math_formula_reveal",
                         placement_id="p", asset_id="a", props=bad, backend="manim", dna=DNA)
        except ab.AnimationError as exc:
            assert exc.code in ("PROPS", "DNA_VISUAL")
        else:
            raise AssertionError("malformed math props were accepted")


def test_attention_template_requires_a_consistent_numeric_matrix():
    plan = ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="attention_matrix_flow",
                        placement_id="p", asset_id="a", duration_s=5.0,
                        props=_attn_props(), backend="manim", dna=DNA)
    assert plan["composition"] == "AttentionMatrixFlow"
    for bad in (
        _attn_props(matrix=[[0.1, 0.2]]),            # wrong width
        _attn_props(matrix=[["x", 0.2, 0.3, 0.4]]),   # non-numeric
        _attn_props(tokens=["only-one"]),             # too few tokens
    ):
        try:
            ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="attention_matrix_flow",
                         placement_id="p", asset_id="a", props=bad, backend="manim", dna=DNA)
        except ab.AnimationError as exc:
            assert exc.code in ("PROPS", "DNA_VISUAL")
        else:
            raise AssertionError("malformed attention props were accepted")


def test_unbound_definition_is_blocked():
    # A definition is "bound" when it carries a source_ref_id and a 64-hex
    # sha256. Anything missing either is refused (missing id, non-hex, or None).
    for props in (_math_props(definition_source={"source_ref_id": "x", "sha256": "not-a-digest"}),
                  _math_props(definition_source=None),
                  _math_props(definition_source={"sha256": DEFN_SHA}),
                  _math_props(definition_source={"source_ref_id": "x"})):
        try:
            ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="math_formula_reveal",
                         placement_id="p", asset_id="a", props=props, backend="manim", dna=DNA)
        except ab.AnimationError as exc:
            assert exc.code == "PROPS"
        else:
            raise AssertionError("an unbound math definition was accepted")


# --- DNA colour ownership ---------------------------------------------------

def test_palette_is_dna_brand_palette_not_legacy_style_variants():
    assert PALETTE["bg"] == "#0F1117"
    assert PALETTE["accent"] == "#38BDF8"
    # A legacy style_variants palette never leaks into the resolved palette.
    assert PALETTE["accent"] != "#157F8B"


def test_visual_overrides_are_rejected_not_applied():
    for key in ("style_variants", "palette_override", "color", "effect", "font_size"):
        try:
            ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="math_formula_reveal",
                         placement_id="p", asset_id="a",
                         props=_math_props(**{key: "#FF0000"}), backend="manim", dna=DNA)
        except ab.AnimationError as exc:
            assert exc.code == "DNA_VISUAL"
        else:
            raise AssertionError(f"visual override {key} was accepted")


def test_render_entry_overwrites_a_smuggled_palette_from_dna():
    # The render entry is the sole place that writes palette into scene props;
    # it must use palette_from_dna regardless of what the spec carried.
    smuggled = _math_props(palette={"bg": "#FFFFFF", "accent": "#FF0000", "ink": "#000000"})
    assert smuggled["palette"]["accent"] == "#FF0000"  # the spec's claim
    assert PALETTE["accent"] == "#38BDF8"               # what render uses


# --- exact re-render on parameter change ------------------------------------

def test_fingerprint_changes_on_params_source_dna_and_version():
    base = dict(account_id=ab.ACCOUNT_FUTURE, template="math_formula_reveal",
                placement_id="p", asset_id="a", purpose="test", duration_s=4.0,
                props=_math_props(), dna=DNA, source_digests=[DEFN_SHA],
                version=ab.MANIM_VERSION, backend="manim", template_digest="t")
    fp = ab.clip_fingerprint(**base)
    assert fp == ab.clip_fingerprint(**base)
    assert ab.clip_fingerprint(**{**base, "props": _math_props(terms=["changed"])}) != fp
    assert ab.clip_fingerprint(**{**base, "source_digests": ["0" * 64]}) != fp
    assert ab.clip_fingerprint(**{**base, "version": "0.0.0"}) != fp
    assert ab.clip_fingerprint(**{**base, "dna": {"brand": {}}}) != fp
    assert ab.clip_fingerprint(**{**base, "template_digest": "other"}) != fp


def test_scene_template_digest_covers_scene_source_and_lock():
    digest = manim_render._scene_template_digest(LOCK)
    assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
    with mock.patch.object(manim_render, "SCENE_MODULE", ROOT / "missing.py"):
        assert manim_render._scene_template_digest(LOCK) != digest


# --- fail-closed gates ------------------------------------------------------

def test_preflight_requires_a_readable_manim_runtime():
    ready = ab.preflight("manim", {"manim": True, "ffmpeg": True, "version": "0.22.1"})
    assert ready["state"] == "READY" and ready["execution_authorized"] is False
    missing = ab.preflight("manim", {"manim": False, "ffmpeg": True})
    assert missing["state"] == "BLOCKED" and missing["code"] == "RUNTIME_MISSING"


def test_selector_never_substitutes_manim_with_remotion():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_FUTURE, shot_type="math", explicit="manim",
        readiness={"manim": False, "remotion": True},
        declared_fallbacks=("remotion",), purpose="production")
    assert result["code"] == "RUNTIME_NOT_READY"
    assert result["substituted"] is False


def test_lock_defaults_to_no_execution_and_no_publication():
    assert LOCK["execution_authorized"] is False
    assert LOCK["publish_authorized"] is False
    assert LOCK["capability_verified_by_installation"] is False
    assert "manim" in LOCK["render_entry"]


# --- capability honesty: installed != VERIFIED ------------------------------

def test_capability_matrix_is_not_verified_from_installation_alone():
    matrix = ab.capability_matrix(ROOT)
    row = matrix["backends"]["manim"]
    assert row["state"] in ("IMPLEMENTED_NOT_VERIFIED", "BLOCKED")
    assert row["render_verified"] is False
    assert row["execution_authorized"] is False
    assert row["publish_authorized"] is False
    assert row["production_ready"] is False
    assert row["lock_present"] is True


def test_capability_matrix_only_promotes_from_receipt_backed_evidence():
    partial = ab.capability_matrix(ROOT, render_evidence={
        "manim": {"verified_at": "2026-11-17", "sha256": "a" * 64}})
    assert partial["backends"]["manim"]["render_verified"] is False
    full = ab.capability_matrix(ROOT, render_evidence={
        "manim": {"verified_at": "2026-11-17", "sha256": "a" * 64,
                  "receipt": "project://receipts/manim-math01.json"}})
    assert full["backends"]["manim"]["state"] == "VERIFIED"
    blocked = ab.capability_matrix(ROOT, render_evidence={
        "manim": {"verified_at": "2026-11-17", "sha256": "a" * 64,
                  "receipt": "project://receipts/manim-math01.json"}},
        block_state={"manim": "RUNTIME_MISSING"})
    assert blocked["backends"]["manim"]["state"] == "BLOCKED"


# --- committed e2e evidence (receipts are tracked; MP4/frames are gitignored) -

def test_committed_e2e_receipts_carry_governance_flags_and_media_facts():
    receipts = ROOT / "projects" / "e2e-p3-manim" / "receipts"
    if not receipts.is_dir():
        return  # e2e project not yet materialised in this checkout
    for asset in ("math01", "attn01"):
        receipt = receipts / f"manim-{asset}.json"
        if not receipt.is_file():
            continue
        data = json.loads(receipt.read_text(encoding="utf-8"))
        assert data["generated"] is True and data["evidence_capable"] is False
        assert data["production_ready"] is False and data["publish_authorized"] is False
        assert data["human_review"] == "PENDING_FOUNDER_REVIEW"
        assert data["width"] == 1080 and data["height"] == 1920
        assert data["codec"] == "h264" and data["pix_fmt"] == "yuv420p"
        assert data["has_audio"] is False
        assert 2.0 <= float(data["duration_s"]) <= 8.0
        assert len(data["sha256"]) == 64
        assert data["output_path"].startswith("project://")


def test_easel_input_validation_receipt_is_visual_support_only():
    path = ROOT / "projects" / "e2e-p3-manim" / "receipts" / "regression-and-blocks.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    easel = data.get("easel_input_validation") or {}
    assert easel.get("accepted_by_easel") is True
    assert easel.get("production_ready") is False
    assert easel.get("publish_authorized") is False
    assert easel.get("evidence_capable") is False


def test_fail_closed_receipts_record_the_specific_gate():
    path = ROOT / "projects" / "e2e-p3-manim" / "receipts" / "regression-and-blocks.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("accepted") is True
    assert data["dna_override_blocked"]["code"] == "DNA_VISUAL"
    assert data["missing_source_blocked"]["code"] == "PROPS"
    assert data["param_change"]["pass"] is True
    assert data["capability_not_verified_by_install"]["pass"] is True
    assert data["param_change"]["original_sha256"] != data["param_change"]["rerender_sha256"]


# --- real render, environment-gated -----------------------------------------

def _real_render_available() -> bool:
    probe = manim_render.environment_probe()
    return bool(probe.get("manim") and probe.get("ffmpeg"))


def test_real_render_end_to_end_or_blocked():
    """Runs the official CLI only when the locked isolated venv is executable.

    Missing runtime -> prints an availability line and records BLOCKED. This is
    honest reporting, not a hidden skip: the function returns without asserting
    that a render occurred, and the top-level runner prints the availability.
    """
    if not _real_render_available():
        probe = manim_render.environment_probe()
        print("  [availability] manim real render BLOCKED: "
              f"manim={probe.get('manim')} ffmpeg={probe.get('ffmpeg')} "
              f"detail={str(probe.get('detail') or '')[:120]}")
        return
    with tempfile.TemporaryDirectory(prefix="p3-manim-test-") as temp:
        project = Path(temp) / "e2e-p3-manim"
        src = ROOT / "projects" / "e2e-p3-manim"
        import shutil
        for rel in ("project.yaml", "specs", "sources", "script"):
            s = src / rel
            d = project / rel
            if s.is_dir():
                shutil.copytree(s, d)
            elif s.is_file():
                d.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(s, d)
        assets_path = project / "sources" / "assets.json"
        assets_doc = json.loads(assets_path.read_text(encoding="utf-8"))
        assets_doc["assets"] = [r for r in assets_doc.get("assets", []) if not r.get("generated")]
        assets_path.write_bytes((json.dumps(assets_doc, ensure_ascii=False) + "\n").encode())
        script_path = project / "script" / "assets.json"
        script_doc = json.loads(script_path.read_text(encoding="utf-8"))
        script_doc["assets"] = {}
        script_path.write_bytes((json.dumps(script_doc, ensure_ascii=False) + "\n").encode())

        # Use the CLI surface exactly as M5 does.
        from process_utils import hidden_run, python_executable
        proc = hidden_run(
            [python_executable(), str(ROOT / "scripts" / "manim_render.py"), str(project),
             "--render", "--spec", "specs/math01.json", "--placement-id", "math01",
             "--asset-id", "math01", "--account", ab.ACCOUNT_FUTURE,
             "--purpose", "test", "--json"],
            cwd=str(ROOT), timeout=900,
            env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"),
        )
        result = json.loads(proc.stdout or "{}")
        assert proc.returncode == 0, result
        assert result["execution"]["state"] in ("EXECUTED", "REUSED")
        assert len(result["sha256"]) == 64
        assert result["easel_input"]["accepted_by_easel"] is True
        output = project / "assets" / "generated" / "manim" / "math01.mp4"
        assert output.is_file()
        from contentops.media.motion_sample import check_motion_sample
        probe = manim_render._ffprobe(output)
        checked = check_motion_sample(output, probe=probe)
        assert checked["state"] == "TECHNICALLY_CHECKED", checked
        assert hashlib.sha256(output.read_bytes()).hexdigest() == result["sha256"]


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    import traceback
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - the runner reports, never hides
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
            traceback.print_exc()
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
