"""P3-B Motion Canvas contract tests.

Offline by design: no npm install, no browser, no editor, no render. A green run
proves the contract, the DNA palette, cache/parameter identity, failure blocking
and the media-attribute gate. It never proves a real video was rendered.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import animation_backend as ab  # noqa: E402
from contentops.media.motion_sample import check_motion_sample  # noqa: E402
import motion_canvas_adapter as adapter  # noqa: E402
import m5_production  # noqa: E402

DNA = json.loads((ROOT / "config" / "accounts"
                  / "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
PALETTE = ab.palette_from_dna(DNA)
E2E = ROOT / "projects" / "e2e-p3-motion-canvas"


def _props(template: str) -> dict:
    if template == "animated_system_graph":
        return {
            "title": "RAG 组件链路",
            "nodes": [{"id": "a", "label": "查询"}, {"id": "b", "label": "召回"}],
            "edges": [{"from": "a", "to": "b"}],
            "steps": [{"caption": "步骤一", "show_nodes": ["a"], "show_edges": []},
                      {"caption": "步骤二", "show_nodes": ["a", "b"],
                       "show_edges": [{"from": "a", "to": "b"}]}],
        }
    return {
        "title": "Agent 状态机",
        "states": [{"id": "idle", "label": "待命"}, {"id": "done", "label": "完成"}],
        "transitions": [{"from": "idle", "to": "done", "label": "完成"}],
        "state_steps": [{"caption": "待命", "active_state": "idle"},
                        {"caption": "完成", "active_state": "done",
                         "active_transition": {"from": "idle", "to": "done"}}],
    }


def test_templates_and_capability_entry_extend_existing_contract():
    for template in adapter.TEMPLATES:
        assert template in ab.TEMPLATES
        assert ab.TEMPLATES[template]["backend"] == "motion-canvas"
        assert template in ab.CAPABILITY_TEMPLATES["motion-canvas"]
    matrix = ab.capability_matrix(ROOT)
    row = matrix["backends"]["motion-canvas"]
    assert row["render_entry"] == "scripts/motion_canvas_adapter.py"
    assert row["export_mode"] == "EDITOR_EXPORT_REQUIRED"
    assert row["state"] != "VERIFIED"
    assert row["render_verified"] is False
    assert row["is_compositor"] is False


def test_plan_clip_accepts_both_templates_without_claim_fields():
    for template in adapter.TEMPLATES:
        plan = ab.plan_clip(
            account_id=ab.ACCOUNT_FUTURE, template=template,
            placement_id="p1", asset_id="a1", duration_s=5.0,
            backend="motion-canvas", dna=DNA,
            props={**_props(template), "palette": PALETTE,
                   "claim": "C-01", "source_refs": ["repo://x.md"],
                   "effect": "bounce", "color": "#FFFFFF"},
        )
        assert plan["backend"] == "motion-canvas"
        assert plan["composition"] == template
        assert plan["width"] == 1080 and plan["height"] == 1920 and plan["fps"] == 30
        assert plan["counts_as_real_recording"] is False
        assert plan["generated"] is True and plan["evidence_capable"] is False
        for key in ("claim", "source_refs", "effect", "color"):
            assert key not in plan["props"], (template, key)


def test_plan_clip_rejects_bad_graphs_failure_tail_and_path_asset_ids():
    bad_graph = _props("animated_system_graph")
    bad_graph["nodes"] = [{"id": "a", "label": "A"}]
    for payload, code in (
        ({**bad_graph, "palette": PALETTE}, "PROPS"),
        ({**_props("agent_state_machine"), "state_steps": [
            {"caption": "完成", "active_state": "done"},
            {"caption": "失败", "active_state": "idle", "failure": True}],
          "palette": PALETTE}, "DNA_VISUAL"),
    ):
        template = ("animated_system_graph" if code == "PROPS" else "agent_state_machine")
        try:
            ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template=template,
                         placement_id="p", asset_id="a", duration_s=4,
                         backend="motion-canvas", dna=DNA, props=payload)
        except ab.AnimationError as exc:
            assert exc.code == code
        else:
            raise AssertionError(f"{template} accepted an invalid spec")
    for asset_id in ("../escape", "nested/name", "/absolute"):
        try:
            ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="animated_system_graph",
                         placement_id="p", asset_id=asset_id, duration_s=4,
                         backend="motion-canvas", dna=DNA,
                         props={**_props("animated_system_graph"), "palette": PALETTE})
        except ab.AnimationError:
            pass
        else:
            raise AssertionError(f"path-like asset id accepted: {asset_id}")


def test_colours_come_from_brand_palette_not_scene_literals():
    assert PALETTE["bg"] == "#0F1117"
    assert PALETTE["accent"] == "#38BDF8"
    assert PALETTE["ink"] == "#202B31"
    source = (ROOT / "extensions" / "motion-canvas" / "src" / "scenes")
    for path in sorted(source.glob("*.tsx")):
        text = path.read_text(encoding="utf-8")
        for token in ("#0F1117", "#38BDF8", "#202B31", "#BD5149"):
            assert token not in text, f"{path.name} hardcodes DNA colour {token}"
        assert "spec.palette" in text
    assert DNA["brand"]["palette"]["problem"] == "#BD5149"


def test_fingerprint_changes_on_parameters_purpose_and_backend_version():
    runtime = {"template_digest": "a" * 64}
    spec_path = E2E / "motion" / "specs" / "animated-system-graph.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    base = adapter._fingerprint(E2E, spec_path, spec, DNA, PALETTE, "p", "a",
                                "production", runtime)
    changed = json.loads(json.dumps(spec, ensure_ascii=False))
    changed["props"]["steps"][0]["caption"] = "不同参数"
    assert adapter._fingerprint(E2E, spec_path, changed, DNA, PALETTE, "p", "a",
                                "production", runtime) != base
    assert adapter._fingerprint(E2E, spec_path, spec, DNA, PALETTE, "p", "a",
                                "test", runtime) != base
    assert adapter._fingerprint(E2E, spec_path, spec, DNA, PALETTE, "p", "a",
                                "production", {"template_digest": "b" * 64}) != base


def test_preflight_blocks_with_editor_export_required_not_headless():
    probe = adapter.environment_probe()
    assert probe["headless_export"] is False
    assert probe["export_mode"] == "EDITOR_EXPORT_REQUIRED"
    decision = ab.preflight("motion-canvas", probe)
    assert decision["code"] == "NO_HEADLESS_EXPORT"
    assert "EDITOR_EXPORT_REQUIRED" in decision["detail"]
    matrix = ab.capability_matrix(ROOT, block_state={"motion-canvas": "EDITOR_EXPORT_REQUIRED"})
    assert matrix["backends"]["motion-canvas"]["state"] == "BLOCKED"


def test_installing_and_compiling_never_promotes_verification():
    matrix = ab.capability_matrix(ROOT)
    row = matrix["backends"]["motion-canvas"]
    assert row["lock_present"] is True
    assert row["runtime_version"] == ab.MOTION_CANVAS_VERSION
    assert row["render_verified"] is False
    assert row["state"] in {"IMPLEMENTED_NOT_VERIFIED", "BLOCKED"}
    compile_evidence = json.loads((E2E / "receipts" / "compile-evidence.json").read_text(
        encoding="utf-8"))
    assert compile_evidence["render_verified"] is False
    assert all(result.get("state") in ("COMPILE_PASS", "COMPILE_FAILED", "NOT_RUN")
               for result in compile_evidence["commands"].values())


def test_render_evidence_requires_a_hash_matching_real_mp4():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        output = project / "assets" / "generated" / "motion-canvas" / "a.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"real editor-exported bytes")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        receipt = {"technical_qc": "TECHNICALLY_CHECKED", "created_at": "2026-11-17T00:00:00Z",
                   "output_path": f"project://{output.relative_to(project).as_posix()}",
                   "sha256": digest}
        (project / "receipts").mkdir()
        (project / "receipts" / "motion-canvas-a.json").write_text(
            json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
        proof = adapter.render_evidence(project, "a")
        assert proof and proof["sha256"] == digest and proof["receipt"]
        output.write_bytes(b"tampered")
        assert adapter.render_evidence(project, "a") is None


def test_media_attribute_gate_is_fail_closed():
    with tempfile.TemporaryDirectory() as temp:
        clip = Path(temp) / "clip.mp4"
        clip.write_bytes(b"bytes")
        valid = {"codec_name": "h264", "width": 1080, "height": 1920,
                 "pix_fmt": "yuv420p", "avg_frame_rate": "30/1", "r_frame_rate": "30/1",
                 "duration_s": 5.0, "has_audio": False,
                 "frame_timestamps": [i / 30 for i in range(150)]}
        assert check_motion_sample(clip, probe=valid)["state"] == "TECHNICALLY_CHECKED"
        for key, value in (("width", 1920), ("codec_name", "mpeg4"),
                           ("pix_fmt", "yuv444p"), ("has_audio", True),
                           ("duration_s", 9.0), ("avg_frame_rate", "60/1")):
            probe = dict(valid, **{key: value})
            assert check_motion_sample(clip, probe=probe)["state"] == "BLOCKED", key
        assert check_motion_sample(clip, probe={"error": "FFPROBE_FAILED"})["state"] == "BLOCKED"


def test_failure_block_writes_governance_flags_without_a_render():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "e2e-invalid"
        (project / "motion").mkdir(parents=True)
        (project / "project.yaml").write_text(
            "id: e2e-invalid\naccount_slug: x-superplay-future-intelligence\n",
            encoding="utf-8")
        invalid = project / "motion" / "bad.json"
        invalid.write_text(json.dumps({
            "template": "animated_system_graph", "duration_s": 9.0,
            "width": 1080, "height": 1920, "fps": 30, "title": "x",
            "props": {"title": "x"},
        }, ensure_ascii=False), encoding="utf-8")
        with mock.patch.object(adapter, "_project_path", return_value=project), \
                mock.patch("sys.stdout", new_callable=__import__("io").StringIO):
            code = adapter.main([str(project), "--prepare", "--spec", "motion/bad.json",
                                 "--placement-id", "p", "--asset-id", "bad-asset"])
        assert code == 1
        payload = json.loads((project / "receipts"
                              / "motion-canvas-bad-asset-block.json").read_text(
                                  encoding="utf-8"))
        assert payload["code"] == "SPEC_DURATION"
        assert payload["render_verified"] is False
        assert payload["production_ready"] is False and payload["publish_authorized"] is False
        assert payload["human_review"] == "PENDING_FOUNDER_REVIEW"


def test_easel_input_contract_is_reused_not_replaced():
    evidence = json.loads((E2E / "receipts" / "easel-input-validation.json").read_text(
        encoding="utf-8"))
    assert evidence["pass"] is True
    assert evidence["source_refs_schema"] == m5_production.SOURCE_REFS_SCHEMA
    assert evidence["declared_source_refs"] == ["E-mc-doc"]
    assert evidence["account_slug"] == "x-superplay-future-intelligence"
    assert all(row["shape_ok"] for row in evidence["project_shapes"].values())
    assert len(evidence["specs"]) == 2


def test_e2e_receipts_do_not_claim_a_render_or_fabricate_media():
    summary = json.loads((E2E / "receipts" / "run-summary.json").read_text(encoding="utf-8"))
    assert summary["media_state"] == "EDITOR_EXPORT_REQUIRED"
    assert summary["render_verified"] is False
    assert summary["parameter_regression_pass"] is True
    pending = json.loads((E2E / "receipts" / "pending-media-evidence.json").read_text(
        encoding="utf-8"))
    for clip in pending["clips"]:
        assert clip["first_frame"] is None and clip["mid_frame"] is None
        assert clip["last_frame"] is None and clip["ffprobe"] is None
        assert clip["sha256"] is None and clip["state"] == "EDITOR_EXPORT_REQUIRED"
    for receipt in (E2E / "receipts").glob("motion-canvas-*.json"):
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        assert payload.get("render_verified") is False, receipt.name
        assert payload.get("production_ready") is False, receipt.name
        assert payload.get("publish_authorized") is False, receipt.name


def test_adapter_reuses_the_existing_registration_not_a_second_system():
    source = (ROOT / "scripts" / "motion_canvas_adapter.py").read_text(encoding="utf-8")
    assert "register_generated_clip(" in source
    assert "build_manifest" not in source
    assert "MANIFEST_SCHEMA" not in source
    for job in (("mc-arch01", "mc-arch01", "motion/specs/animated-system-graph.json"),
                ("mc-state01", "mc-state01", "motion/specs/agent-state-machine.json")):
        asset_id, placement, spec_rel = job
        spec = json.loads((E2E / spec_rel).read_text(encoding="utf-8"))
        plan = ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template=spec["template"],
                            placement_id=placement, asset_id=asset_id,
                            duration_s=float(spec["duration_s"]), backend="motion-canvas",
                            dna=DNA, props={**spec["props"], "palette": PALETTE})
        assert plan["composition"] == spec["template"]


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - runner reports, never hides
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} P3 Motion Canvas tests passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
