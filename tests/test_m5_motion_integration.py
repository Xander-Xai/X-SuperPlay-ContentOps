"""M5 must be able to place a video shot, and must never substitute a still or a
different voice when the declared one is unavailable.

The failure this prevents, twice over:

- M5 built its own storyboard with ``image`` and a literal ``"motion": "static"``,
  so a rendered clip in the manifest could not reach the composer at all;
- asking for a narration source the build could not reach returned a SAPI track
  that looked like a success.
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import tempfile
from types import SimpleNamespace
from unittest import mock
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import m5_production  # noqa: E402
import produce_video  # noqa: E402
import huashu_motion_adapter  # noqa: E402
import huashu_motion_backend  # noqa: E402
import raw_video_inputs  # noqa: E402
from contentops.media import storyboard_adapter as adapter  # noqa: E402
from contentops.media import local_assets, motion_planner, visual_gate  # noqa: E402


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assets(temp: Path, *, video: bool = True) -> dict:
    media = temp / "work" / "media"
    media.mkdir(parents=True, exist_ok=True)
    name = "beat-00.mp4" if video else "beat-00.png"
    (media / name).write_bytes(b"placeholder bytes")
    return {"A1": {"repo_path": f"work/media/{name}",
                   "type": "video" if video else "screenshot"}}


def _lines():
    return [{"asset_id": "A1", "caption": "第一句", "narration": "第一句", "claim": "C1"}]


def _timings(seconds=5.0):
    return [{"duration": seconds}]


def _huashu_project():
    temporary = tempfile.TemporaryDirectory(dir=ROOT / "projects",
                                             prefix="test-huashu-local-")
    project = Path(temporary.name)
    (project / "project.yaml").write_text(
        "id: local-motion-test\naccount_slug: x-superplay-future-intelligence\n",
        encoding="utf-8")
    for relative, payload in {
        "script/script.json": {"lines": [{"id": "P-01", "asset_id": "source-01",
                                             "claim": "C-01", "narration": "RAG 检索机制"}]},
        "script/claims.json": {"claims": [{"id": "C-01", "artifacts": ["E-01"]}]},
        "script/assets.json": {"assets": {}},
        "sources/source-refs.json": {"refs": [{"id": "E-01", "path": "README.md"}]},
        "sources/assets.json": {"assets": []},
        "motion/auto/shot.json": {"grammar": "y3_whiteboard", "duration": 3.0,
                                  "fps": 30, "width": 1080, "height": 1920,
                                  "cues": [{"at": 0.0, "kind": "draw", "text": "RAG"}]},
    }.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return temporary, project


def test_visual_gate_states_are_fail_closed_and_never_approve_publication():
    passed = visual_gate.evaluate_film_gate(
        {"gate_light": "green", "verdict": "green", "fast_ratio": 0.08}, 0)
    assert passed["state"] == "PASS"
    assert passed["metrics"]["fast_ratio"] == 0.08
    assert passed["production_ready"] is False
    assert passed["publish_authorized"] is False
    assert passed["human_review"] == "PENDING_FOUNDER_REVIEW"
    assert visual_gate.evaluate_film_gate(
        {"gate_light": "yellow", "verdict": "yellow"}, 0)["state"] == "WARN"
    assert visual_gate.evaluate_film_gate(
        {"gate_light": "red", "verdict": "red"}, 2)["state"] == "FAIL"
    assert visual_gate.evaluate_film_gate(
        {"gate_light": "green", "verdict": "green"}, 2)["state"] == "BLOCKED"
    assert visual_gate.evaluate_film_gate(
        {"gate_light": "green", "verdict": "yellow"}, 0)["state"] == "BLOCKED"


def test_huashu_preflight_auto_and_review_allow_local_preview_without_grant():
    temporary, project = _huashu_project()
    route = {"verdict": "RESOLVABLE", "reason": "RESOLVABLE",
             "execution_authorized": False,
             "capability": {"provider": {"path_permitted": True,
                                             "network": False, "paid": False,
                                             "cross_project_reuse": False}}}
    runtime = {"skill_id": "huashu-art-motion", "version": "1.2.0"}
    try:
        with mock.patch.object(huashu_motion_adapter.skill_route,
                               "resolve_capability", return_value=route), \
                mock.patch.object(huashu_motion_adapter, "_runtime", return_value=runtime):
            for mode in ("AUTO", "REVIEW"):
                capture = io.StringIO()
                with mock.patch("sys.stdout", capture):
                    code = huashu_motion_adapter.main([
                        str(project), "--preflight", "--mode", mode, "--json"])
                payload = json.loads(capture.getvalue())
                assert code == 0 and payload["state"] == "READY"
                assert payload["execution_policy"] == {
                    "state": "LOCAL_ONLY_PERMITTED", "project_grant_required": False,
                    "network": False, "paid": False, "publication": False,
                    "technical_preview_requires_copy_review": False}
                assert payload["copy_review"].get("state") != "APPROVED"
            capture = io.StringIO()
            with mock.patch("sys.stdout", capture):
                code = huashu_motion_adapter.main([
                    str(project), "--preflight", "--mode", "STRICT", "--json"])
            strict_payload = json.loads(capture.getvalue())
            assert code != 0 and strict_payload["state"] == "BLOCKED"
            assert any(item.startswith("COPY_REVIEW_")
                       for item in strict_payload["problems"])
    finally:
        temporary.cleanup()


def test_huashu_local_effect_policy_does_not_authorize_paid_or_publish_effects():
    registry = json.loads((ROOT / "runtime" / "skill-registry.json").read_text(
        encoding="utf-8"))
    entry = next(row for row in registry["skills"]
                 if row.get("id") == "x-superplay-huashu-motion")
    provider = entry["provider"]
    execution = entry["execution"]
    assert provider["path_permitted"] is True
    assert provider["network"] is False
    assert provider["paid"] is False
    assert provider["cross_project_reuse"] is False
    assert execution["authorizes_execution"] is False
    assert execution["project_grant_required"] is False
    assert "publication clearance" in entry["rights"]["scope"]


def test_huashu_auto_local_render_runs_repeated_shots_without_grant():
    temporary, project = _huashu_project()
    route = {"verdict": "RESOLVABLE", "reason": "RESOLVABLE",
             "execution_authorized": False, "capability": {}}
    runtime = {"skill_id": "huashu-art-motion", "version": "1.2.0"}
    try:
        with mock.patch.object(huashu_motion_adapter.skill_route,
                               "resolve_capability", return_value=route), \
                mock.patch.object(huashu_motion_adapter, "_runtime", return_value=runtime), \
                mock.patch.object(huashu_motion_adapter, "_render",
                                  side_effect=[{"asset_id": "huashu-P-01"},
                                               {"asset_id": "huashu-P-02"},
                                               {"asset_id": "huashu-P-03"}]) as render:
            results = []
            for index in range(1, 4):
                capture = io.StringIO()
                with mock.patch("sys.stdout", capture):
                    code = huashu_motion_adapter.main([
                        str(project), "--render", "--mode", "AUTO",
                        "--spec", "motion/auto/shot.json",
                        "--placement-id", f"P-0{index}",
                        "--asset-id", f"huashu-P-0{index}", "--json"])
                assert code == 0, capture.getvalue()
                results.append(json.loads(capture.getvalue()))
        assert render.call_count == 3
        assert [item["execution"]["state"] for item in results] == [
            "EXECUTED", "EXECUTED", "EXECUTED"]
        for item in results:
            assert item["decision"]["state"] == "NOT_REQUIRED_LOCAL_ONLY"
            assert item["decision"]["execution_authorized"] is False
            assert item["production_ready"] is False
            assert item["publish_authorized"] is False
        assert not (project / "receipts" / "skill-execution-approval.json").exists()
        assert not (project / "receipts" / "grants").exists()
    finally:
        temporary.cleanup()


def test_huashu_valid_cached_render_is_reused_without_renderer_call():
    temporary, project = _huashu_project()
    route = {"verdict": "RESOLVABLE", "reason": "RESOLVABLE",
             "execution_authorized": False, "capability": {}}
    runtime = {"skill_id": "huashu-art-motion", "version": "1.2.0"}
    cached_output = project / "assets" / "generated" / "huashu" / "huashu-P-01.mp4"
    cached_output.parent.mkdir(parents=True)
    cached = {"line": {"id": "P-01"}, "claim": {"id": "C-01"},
              "spec_path": project / "motion" / "auto" / "shot.json",
              "spec": {"duration": 3}, "output": cached_output,
              "technical": {"approved": True}}
    try:
        with mock.patch.object(huashu_motion_adapter.skill_route,
                               "resolve_capability", return_value=route), \
                mock.patch.object(huashu_motion_adapter, "_runtime", return_value=runtime), \
                mock.patch.object(huashu_motion_adapter, "_cached_render",
                                  return_value=cached), \
                mock.patch.object(huashu_motion_adapter, "_register",
                                  return_value={"asset_id": "huashu-P-01"}), \
                mock.patch.object(huashu_motion_adapter, "_render") as render:
            capture = io.StringIO()
            with mock.patch("sys.stdout", capture):
                code = huashu_motion_adapter.main([
                    str(project), "--render", "--mode", "AUTO",
                    "--spec", "motion/auto/shot.json",
                    "--placement-id", "P-01", "--asset-id", "huashu-P-01", "--json"])
        payload = json.loads(capture.getvalue())
        assert code == 0
        assert payload["execution"]["state"] == "REUSED"
        assert payload["execution"]["reused"] is True
        render.assert_not_called()
        assert not (project / "receipts" / "grants").exists()
    finally:
        temporary.cleanup()


def test_huashu_accepts_only_exact_nonfactual_editorial_transitions_without_claims():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        line = {"id": "P-01", "narration": "这期只看仓库源码。", "claim": None}
        (project / "script").mkdir()
        (project / "script" / "lines.json").write_text(json.dumps({"beats": [{
            "placement_id": "P-01", "claim_id": "C-01"}]}), encoding="utf-8")
        claim = {"claim_id": "C-01", "text": "这期只看仓库源码。",
                 "kind": "editorial_transition", "assertion_about": "none",
                 "evidence": []}
        map_path = project / "script" / "claim-map.json"
        map_path.write_text(json.dumps({"claims": [claim]}, ensure_ascii=False),
                            encoding="utf-8")
        editorial = huashu_motion_adapter._editorial_transition(project, line, "P-01")
        assert editorial == {"id": "C-01", "text": "这期只看仓库源码。",
                             "artifacts": [], "editorial_only": True}
        claim["kind"] = "source"
        map_path.write_text(json.dumps({"claims": [claim]}, ensure_ascii=False),
                            encoding="utf-8")
        assert huashu_motion_adapter._editorial_transition(project, line, "P-01") is None
        claim["kind"] = "editorial_transition"
        claim["evidence"] = [{"evidence_id": "E-01"}]
        map_path.write_text(json.dumps({"claims": [claim]}, ensure_ascii=False),
                            encoding="utf-8")
        assert huashu_motion_adapter._editorial_transition(project, line, "P-01") is None


def test_huashu_source_cta_requires_all_prior_claims_in_verified_inventory():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        (project / "script").mkdir()
        (project / "receipts").mkdir()
        line = {"id": "P-02", "narration": "以上内容都能在文末的来源里逐条核对。",
                "claim": None}
        beats = [{"placement_id": "P-01", "claim_id": "C-01"},
                 {"placement_id": "P-02", "claim_id": "C-02"}]
        claims = [
            {"claim_id": "C-01", "text": "源码功能", "kind": "source",
             "evidence": [{"evidence_id": "E-01", "sha256": "abc123"}]},
            {"claim_id": "C-02", "text": line["narration"], "kind": "cta",
             "assertion_about": "none", "evidence": []},
        ]
        (project / "script" / "lines.json").write_text(
            json.dumps({"beats": beats}, ensure_ascii=False), encoding="utf-8")
        (project / "script" / "claim-map.json").write_text(
            json.dumps({"claims": claims}, ensure_ascii=False), encoding="utf-8")
        inventory_path = project / "receipts" / "source-artifacts.json"
        inventory_path.write_text(json.dumps({"artifacts": [
            {"id": "E-01", "sha256": "abc123", "permission": "LICENSED"}]}),
            encoding="utf-8")
        result = huashu_motion_adapter._editorial_transition(project, line, "P-02")
        assert result == {"id": "C-02", "text": line["narration"],
                          "artifacts": ["E-01"], "editorial_only": False,
                          "claim_basis": "source_referential_cta"}
        inventory_path.write_text(json.dumps({"artifacts": []}), encoding="utf-8")
        assert huashu_motion_adapter._editorial_transition(project, line, "P-02") is None


def test_storyboard_preserves_each_narration_pause_inside_its_own_shot():
    shots = [{"duration": 2.0, "duration_s": 2.0} for _ in range(2)]
    timings = [{"start": 0.0, "duration": 1.8},
               {"start": 2.3, "duration": 1.7}]
    aligned = m5_production._align_shots_to_narration(shots, timings)
    assert [shot["duration_s"] for shot in aligned] == [2.3, 1.7]


def test_a_video_asset_reaches_the_storyboard_as_a_clip():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                    assets=_assets(project), repo_root=project)
        assert shots[0]["video"] == "work/media/beat-00.mp4"
        assert shots[0]["source_type"] == "video"


def test_a_still_asset_is_not_labelled_a_clip():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                    assets=_assets(project, video=False), repo_root=project)
        assert "video" not in shots[0]
        assert shots[0]["image"] == "work/media/beat-00.png"


def test_runtime_release_facts_use_the_source_image_motion_grammar():
    assert motion_planner._topic_kind("The verified runtime is pinned to v0.2.1") == "code"


def test_explicit_user_media_is_preview_only_and_hash_bound():
    # A valid 1x1 PNG, selected from a separate source folder.
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        repo = base / "repo"
        project = repo / "projects" / "preview-only"
        source = base / "selected-media"
        source.mkdir()
        (source / "provided.png").write_bytes(png)

        with mock.patch.object(produce_video, "ROOT", repo):
            digest_before_import = produce_video._input_digest(project, assets_dir=source)
        receipt = local_assets.import_local_assets(source, project, repo_root=repo)
        assert receipt["usage_scope"] == "LOCAL_PREVIEW_ONLY"
        assert receipt["distribution_authorized"] is False
        assert receipt["evidence_capable"] is False
        repeated = local_assets.import_local_assets(source, project, repo_root=repo)
        assert len(repeated["assets"]) == 1
        with mock.patch.object(produce_video, "ROOT", repo):
            assert produce_video._input_digest(project, assets_dir=source) == digest_before_import
        asset = json.loads((project / "sources" / "assets.json").read_text(
            encoding="utf-8"))["assets"][0]
        assert local_assets.is_valid_local_preview_asset(asset, project, repo)

        # The normal M5 asset stage may use the visual in a local preview, while
        # leaving its rights and claim-evidence status unchanged.
        stage_root = Path(str(repo).swapcase()) if sys.platform == "win32" else repo
        with mock.patch.object(m5_production, "ROOT", stage_root):
            verified = m5_production.stage_assets(project)
            assert verified[asset["id"]]["verified_sha256"] == asset["sha256"]
            imported_path = repo / asset["repo_path"]
            imported_path.write_bytes(png + b"tampered")
            try:
                local_assets.import_local_assets(source, project, repo_root=repo)
            except local_assets.LocalAssetError as exc:
                assert "changed" in str(exc)
            else:
                raise AssertionError("changed imported bytes must prevent stale-cache reuse")
            try:
                m5_production.stage_assets(project)
            except m5_production.M5Blocked as exc:
                assert "sha256" in str(exc)
            else:
                raise AssertionError("changed local media must fail the hash check")


def test_user_video_import_records_metadata_and_three_review_frames():
    from process_utils import hidden_run

    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        repo = base / "repo"
        project = repo / "projects" / "video-preview"
        source = base / "selected-media"
        source.mkdir()
        video = source / "sample.mp4"
        generated = hidden_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=96x160:rate=8:duration=2",
            "-pix_fmt", "yuv420p", str(video),
        ], timeout=60)
        assert generated.returncode == 0 and video.is_file()

        receipt = local_assets.import_local_assets(source, project, repo_root=repo)
        imported = {row["id"]: row for row in receipt["assets"]}
        parent = next(row for row in imported.values()
                      if row.get("type") == "USER_PROVIDED_VIDEO")
        summary = parent["video_summary"]
        assert summary["duration_s"] == 2.0
        assert summary["video_codec"] == "h264"
        assert summary["width"] == 96 and summary["height"] == 160
        samples = summary["sample_frames"]
        assert [row["timestamp_s"] for row in samples] == [0.1, 1.0, 1.75]
        assert all(row["id"] in imported for row in samples)
        assert receipt["contact_sheet"]["state"] == "READY"
        assert receipt["contact_sheet"]["items"] == 3
        assert "@" in receipt["contact_sheet"]["asset_cells"][0]["label"]
        assert receipt["distribution_authorized"] is False
        assert receipt["evidence_capable"] is False


def test_unified_producer_passes_selected_media_into_m5():
    with tempfile.TemporaryDirectory() as temp:
        assets_dir = Path(temp)
        expected = {"state": "QC_PASSED", "project": "projects/demo",
                    "video": "project://final/demo.mp4", "elapsed_seconds": 0,
                    "human_review": "PENDING_FOUNDER_REVIEW"}
        with (mock.patch.object(sys, "argv", [
                  "produce_video.py", "--project", "projects/demo", "--assets",
                  str(assets_dir), "--json"]),
              mock.patch.object(produce_video, "produce", return_value=expected) as run):
            assert produce_video.main() == 0
            assert run.call_args.kwargs["assets_dir"] == assets_dir.resolve()


def test_the_composer_key_and_the_receipt_key_agree():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(4.25),
                                    assets=_assets(project), repo_root=project)
        assert shots[0]["duration"] == shots[0]["duration_s"] == 4.25


def test_a_missing_asset_stops_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        assets = _assets(project)
        (project / "work" / "media" / "beat-00.mp4").unlink()
        try:
            adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                assets=assets, repo_root=project)
        except adapter.StoryboardContractError as exc:
            assert "missing on disk" in str(exc), exc
        else:
            raise AssertionError("a missing clip must not silently become a still")


def test_a_non_positive_duration_stops_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            adapter.build_shots(lines=_lines(), narration_lines=_timings(0),
                                assets=_assets(project), repo_root=project)
        except adapter.StoryboardContractError:
            pass
        else:
            raise AssertionError("a zero-length shot must be refused")


def test_misaligned_lines_and_timings_stop_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            adapter.build_shots(lines=_lines(), narration_lines=[],
                                assets=_assets(project), repo_root=project)
        except adapter.StoryboardContractError as exc:
            assert "not aligned" in str(exc), exc
        else:
            raise AssertionError("an unaligned timeline must be refused")


def test_the_same_asset_can_support_multiple_timeline_placements():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        lines = _lines() + _lines()
        shots = adapter.build_shots(lines=lines, narration_lines=_timings() + _timings(),
                                    assets=_assets(project), repo_root=project)
        assert len(shots) == 2
        assert [shot["asset_id"] for shot in shots] == ["A1", "A1"]
        assert shots[0]["source"] == shots[1]["source"]
        assert shots[0]["shot_id"] != shots[1]["shot_id"]


def _script():
    return {"lines": _lines()}


def test_minimax_narration_requires_an_explicit_voice_and_never_uses_sapi():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            m5_production.stage_narration(project, _script(), provider="minimax")
        except m5_production.M5Blocked as exc:
            assert "explicit --narration-voice" in str(exc), exc
        else:
            raise AssertionError("MiniMax must require an explicit voice; no SAPI fallback is allowed")


def test_motion_backend_selection_is_per_shot_and_fail_closed():
    assert m5_production._select_motion_backend({}, "huashu-art-motion") == "huashu-art-motion"
    assert m5_production._select_motion_backend(
        {"motion_backend": "huashu-motion"}, "huashu-art-motion") == "huashu-motion"
    assert m5_production._select_motion_backend(
        {"backend": "art-motion"}, "huashu-motion") == "huashu-art-motion"
    try:
        m5_production._select_motion_backend({"backend": "other"}, "huashu-art-motion")
    except m5_production.M5Blocked as exc:
        assert "unsupported motion backend" in str(exc)
    else:
        raise AssertionError("unknown motion backends must not be silently routed")


def test_video_account_dna_enables_h3_bookends_with_explicit_budget_policy():
    future = m5_production._load_digital_presenter_profile(
        {"account_slug": "x-superplay-future-intelligence"})
    account_1024 = m5_production._load_digital_presenter_profile(
        {"account_slug": "x-superplay-1024"})
    english = m5_production._load_digital_presenter_profile(
        {"account_slug": "x-superplay-english"})
    assert future["provider"] == account_1024["provider"] == "minimax-h3"
    assert future["asset_dir"] == account_1024["asset_dir"] == "assert"
    assert future["scope"] == account_1024["scope"] == "intro_and_outro_only"
    assert future["requires_explicit_quota_budget"] is True
    assert account_1024["requires_explicit_quota_budget"] is True
    assert english == {}, "the English account must keep its own existing format"


def test_m5_motion_stage_dispatches_explicit_huashu_motion_shots():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        for folder in ("script", "sources", "receipts"):
            (project / folder).mkdir(parents=True, exist_ok=True)
        (project / "script" / "assets.json").write_text(
            json.dumps({"schema": "contentops.m5-script-assets/v1", "assets": {}}),
            encoding="utf-8")
        plan_path = project / "motion" / "shot-plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_text(json.dumps({"shots": [{
            "placement_id": "P-01", "asset_id": "HM-PROBE-01",
            "source_asset_id": "SRC-01", "spec": "motion/huashu-motion/shot-01",
            "motion_backend": "huashu-motion", "duration_s": 5.166,
        }]}), encoding="utf-8")
        script = {"lines": [{"id": "P-01", "asset_id": "SRC-01",
                             "motion_asset_id": "HM-PROBE-01",
                             "narration": "逐步展示检索流程。"}]}
        response = {"execution": {"state": "EXECUTED", "reused": False,
                                   "adapter_receipt": {"engine": "huashu-motion"}},
                    "receipt": "project://receipts/huashu-motion-HM-PROBE-01.json"}
        fake = SimpleNamespace(returncode=0,
                               stdout=json.dumps(response, ensure_ascii=False), stderr="")
        with mock.patch.object(m5_production, "hidden_run", return_value=fake) as run:
            result = m5_production.stage_motion(
                project,
                {"id": "probe", "account_slug": "x-superplay-future-intelligence",
                 "motion": {"backend": "huashu-art-motion", "shot_plan": "motion/shot-plan.json"}},
                script, require_copy_review=False,
                narration={"lines": [{"line_id": "P-01", "duration": 5.166}]})
        assert result == {"state": "OK", "backend": "huashu-motion", "shots": 1}
        command = run.call_args.args[0]
        assert command[1].endswith("huashu_motion_backend.py")
        assert command[command.index("--film") + 1] == "motion/huashu-motion/shot-01"
        assert command[command.index("--expected-duration") + 1] == "5.166"
        saved = json.loads((project / "receipts" / "motion-stage.json").read_text(encoding="utf-8"))
        assert saved["shots"][0]["backend"] == "huashu-motion"


def test_huashu_motion_film_path_must_remain_project_local():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp) / "project"
        film = project / "motion" / "huashu-motion" / "shot-01"
        (film / "vendor").mkdir(parents=True)
        (film / "index.html").write_text("<html></html>", encoding="utf-8")
        (film / "vendor" / "gsap.min.js").write_text("", encoding="utf-8")
        assert huashu_motion_backend.resolve_motion_project(
            project, "motion/huashu-motion/shot-01") == film.resolve()
        try:
            huashu_motion_backend.resolve_motion_project(project, "../../outside")
        except huashu_motion_backend.BackendError as exc:
            assert "must stay under" in str(exc)
        else:
            raise AssertionError("a motion film outside the project must be refused")


def test_h3_avatar_bookends_reuse_only_hash_bound_subscription_outputs():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        root = Path(temp)
        project = root / "project"
        assets = root / "assert"
        project.mkdir()
        assets.mkdir()
        portrait, voice = assets / "portrait.png", assets / "voice.wav"
        portrait.write_bytes(b"registered portrait")
        voice.write_bytes(b"registered voice reference")
        manifest = {
            "local_only": True, "do_not_commit_media": True,
            "primary": {"presenter_reference": "portrait", "voice_reference": "voice"},
            "assets": [
                {"asset_id": "portrait", "relative_path": "renamed.png",
                 "sha256": m5_production._sha256(portrait)},
                {"asset_id": "voice", "relative_path": "moved.wav",
                 "sha256": m5_production._sha256(voice)},
            ],
        }
        (assets / "asset-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        references = [m5_production._sha256(portrait), m5_production._sha256(voice)]
        clips = []
        for role in ("intro", "outro"):
            clip = project / f"{role}.mp4"
            clip.write_bytes(f"{role} generated video".encode())
            payload = {
                "provider": "minimax_m_plan", "model": "MiniMax-H3",
                "credential_class": "SUBSCRIPTION", "payg_allowed": False,
                "output_sha256": m5_production._sha256(clip),
                "audio_stream_present": True,
                "reference_asset_sha256": references,
                "actual_duration_s": 4.4,
            }
            clip.with_name(clip.name + ".receipt.json").write_text(
                json.dumps(payload), encoding="utf-8")
            clips.append(clip)

        with mock.patch.object(m5_production, "_run_h3_avatar_clip") as generate:
            undersized_budget = m5_production.stage_avatar(
                project, "demo", asset_root=assets, quota_budget="7pp",
                intro_line="开场", outro_line="结尾")
        assert undersized_budget["state"] == "PARTIAL"
        assert "no H3 request was sent" in undersized_budget["blocked_reason"]
        generate.assert_not_called()

        result = m5_production.stage_avatar(
            project, "demo", asset_root=assets, quota_budget=None,
            intro_line="开场", outro_line="结尾",
            intro_video=clips[0], outro_video=clips[1])
        assert result["state"] == "READY"
        assert result["intro"]["reused"] and result["outro"]["reused"]
        saved = json.loads((project / "receipts" / "avatar-bookends.json").read_text())
        assert saved["intro"]["video"].endswith("intro.mp4")
        assert saved.get("production_ready") is not True

        partial_without_budget = m5_production.stage_avatar(
            project, "demo", asset_root=assets, quota_budget=None,
            intro_line="开场", outro_line="结尾", intro_video=clips[0])
        assert partial_without_budget["state"] == "PARTIAL"
        assert partial_without_budget["intro"]["reused"]
        assert partial_without_budget.get("outro") is None

        generated = project / "new-outro.mp4"
        generated.write_bytes(b"new H3 outro")
        with mock.patch.object(m5_production, "_run_h3_avatar_clip", return_value={
                "video": generated, "receipt": generated.with_name(generated.name + ".receipt.json"),
                "sha256": m5_production._sha256(generated), "reused": False,
                "duration_s": 4.4}) as generate:
            hybrid = m5_production.stage_avatar(
                project, "demo", asset_root=assets, quota_budget="7pp",
                intro_line="开场", outro_line="结尾", intro_video=clips[0])
        assert hybrid["state"] == "READY"
        assert hybrid["intro"]["reused"] and not hybrid["outro"]["reused"]
        generate.assert_called_once()
        assert generate.call_args.kwargs["role"] == "outro"

        receipt_path = clips[1].with_name(clips[1].name + ".receipt.json")
        receipt = json.loads(receipt_path.read_text())
        receipt["payg_allowed"] = True
        receipt_path.write_text(json.dumps(receipt))
        rejected = m5_production.stage_avatar(
            project, "demo", asset_root=assets, quota_budget=None,
            intro_line="开场", outro_line="结尾",
            intro_video=clips[0], outro_video=clips[1])
        assert rejected["state"] == "PARTIAL"
        assert "provider, audio, or hash" in rejected["blocked_reason"]


def test_avatar_bookend_composition_preserves_the_main_only_render():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        final = project / "final"
        final.mkdir()
        video = final / "demo.mp4"
        video.write_bytes(b"main-only")
        (final / "demo-main-only.mp4").write_bytes(b"stale-body-from-prior-run")
        intro, outro = project / "intro.mp4", project / "outro.mp4"
        intro.write_bytes(b"intro")
        outro.write_bytes(b"outro")
        avatar = {"state": "READY", "intro": {"video": intro, "duration_s": 4.4},
                  "outro": {"video": outro, "duration_s": 4.4}}
        calls = []

        def fake_ffmpeg(command, **_kwargs):
            calls.append(command)
            Path(command[-1]).write_bytes(b"combined")
            return SimpleNamespace(returncode=0, stderr="")

        with mock.patch.object(m5_production, "hidden_run", side_effect=fake_ffmpeg):
            result = m5_production._compose_avatar_bookends(project, "demo", avatar, video)
        assert video.read_bytes() == b"combined"
        assert (final / "demo-main-only.mp4").read_bytes() == b"main-only"
        assert result["state"] == "COMPOSED"
        filt = calls[0][calls[0].index("-filter_complex") + 1]
        assert "concat=n=3:v=1:a=1" in filt


def test_partial_avatar_preview_keeps_only_the_successful_clip_and_main_video():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        (project / "receipts").mkdir()
        final = project / "final"
        final.mkdir()
        main = final / "main.mp4"
        main.write_bytes(b"existing main video")
        intro = project / "intro.mp4"
        intro.write_bytes(b"successful H3 intro")
        output = final / "partial-preview.mp4"
        commands = []

        def fake_ffmpeg(command, **_kwargs):
            commands.append(command)
            Path(command[-1]).write_bytes(b"composed partial preview")
            return SimpleNamespace(returncode=0, stderr="")

        with mock.patch.object(m5_production, "hidden_run", side_effect=fake_ffmpeg):
            result = m5_production._compose_partial_avatar_preview(
                project, "demo", {"state": "PARTIAL", "intro": {"video": intro},
                                   "outro": None}, main, output)
        assert result["state"] == "PARTIAL_PREVIEW"
        assert result["segments"] == ["intro", "main"]
        assert result["production_ready"] is False
        assert main.read_bytes() == b"existing main video"
        assert output.read_bytes() == b"composed partial preview"
        filt = commands[0][commands[0].index("-filter_complex") + 1]
        assert "concat=n=2:v=1:a=1" in filt
        saved = json.loads((project / "receipts" / "avatar-bookends.json").read_text())
        assert saved["partial_preview"]["state"] == "PARTIAL_PREVIEW"


def test_existing_narration_without_a_receipt_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio)
        except m5_production.M5Blocked as exc:
            assert "narration-receipt" in str(exc), exc
        else:
            raise AssertionError("audio without provenance must be refused")


def test_existing_narration_bound_to_another_script_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({"text_sha256": _sha("other script"),
                                       "lines": _timings()}), encoding="utf-8")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio,
                                          narration_receipt=receipt)
        except m5_production.M5Blocked as exc:
            assert "not bound to the current script" in str(exc), exc
        else:
            raise AssertionError("audio that speaks another script must be refused")


def test_existing_narration_without_line_timings_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        text = "\n".join(line["narration"] for line in _lines())
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({"text_sha256": _sha(text)}), encoding="utf-8")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio,
                                          narration_receipt=receipt)
        except m5_production.M5Blocked as exc:
            assert "per-line timings" in str(exc), exc
        else:
            raise AssertionError("audio without timings cannot drive subtitles")


def test_existing_narration_that_matches_is_reused_without_a_provider_call():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 4000)  # 0.5 s of silence
        text = "\n".join(line["narration"] for line in _lines())
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({
            "engine": "speech-2.8-hd", "voice": "fixture",
            "text_sha256": _sha(text), "lines": _timings(0.5),
        }), encoding="utf-8")
        payload = m5_production.stage_narration(
            project, _script(), provider="existing",
            narration_audio=audio, narration_receipt=receipt)
        assert payload["voice_provider"] == "existing"
        assert payload["text_sha256"] == _sha(text)
        assert payload["network"] is False
        assert (project / "assets" / "voice" / "narration.wav").is_file()
        assert payload["duration_s"] > 0


def test_producer_reuses_current_qc_pass_without_rebuilding():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp).resolve()
        project = root / "projects" / "demo-project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        (project / "project.yaml").write_text("id: demo-project\nsource_refs: []\n", encoding="utf-8")
        (project / "script" / "script.json").write_text("{}", encoding="utf-8")
        (project / "script" / "claims.json").write_text("{}", encoding="utf-8")
        (project / "sources" / "assets.json").write_text(
            '{"schema":"contentops.m5-assets/v1","assets": []}', encoding="utf-8")
        assets_dir = root / "selected-media"
        assets_dir.mkdir()
        (assets_dir / "selected.png").write_bytes(bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
        ))
        old_root, old_build = produce_video.ROOT, produce_video.m5_production.build
        calls = []

        build_options = []

        def fake_build(target, **options):
            calls.append(target)
            build_options.append(options)
            local_assets.import_local_assets(options["assets_dir"], target, repo_root=root)
            (target / "final").mkdir(parents=True, exist_ok=True)
            (target / "final" / "demo-project.mp4").write_bytes(b"rendered bytes")
            report = {"overall": "PASS", "graded_target": "project://final/demo-project.mp4"}
            (target / "receipts").mkdir(exist_ok=True)
            (target / "receipts" / "qc-report-demo-project.json").write_text(
                json.dumps(report), encoding="utf-8")
            contact_sheet = target / "receipts" / "visual-contact-sheet.png"
            contact_sheet.write_bytes(b"contact sheet fixture")
            (target / "receipts" / "visual-gate.json").write_text(json.dumps({
                "state": "PASS", "video_sha256": produce_video._hash_file(
                    target / "final" / "demo-project.mp4"),
                "contact_sheet": "project://receipts/visual-contact-sheet.png",
            }), encoding="utf-8")
            return {"stages": {"compose": {"state": "OK"}, "qc": {"overall": "PASS"},
                               "visual_qc": {"state": "PASS"}},
                    "human_review": "PENDING_FOUNDER_REVIEW"}

        produce_video.ROOT = Path(str(root).swapcase()) if sys.platform == "win32" else root
        produce_video.m5_production.build = fake_build
        try:
            assert produce_video._relative_to_root(project) == Path("projects/demo-project")
            first = produce_video.produce(project, assets_dir=assets_dir)
            second = produce_video.produce(project, assets_dir=assets_dir)
            assert build_options == [{"require_copy_review": False,
                                      "assets_dir": assets_dir.resolve()}]
            assert first["state"] == "QC_PASSED" and first["reused"] is False
            assert second["state"] == "QC_PASSED" and second["reused"] is True
            assert second["resumed_from_run_id"] == first["run_id"]
            assert second["rendered"] is True and second["technical_qc"] == "PASS"
            assert second["visual_qc"] == "PASS"
            assert second["production_ready"] is False and second["published"] is False
            assert len(second["runs"]) == 2
            assert second["runs"][0]["run_id"] == first["run_id"]
            assert second["runs"][0]["elapsed_seconds"] == first["elapsed_seconds"]
            assert second["runs"][1]["reused"] is True
            assert len(calls) == 1
            assert second["human_review"] == "PENDING_FOUNDER_REVIEW"
        finally:
            produce_video.ROOT = old_root
            produce_video.m5_production.build = old_build


def test_producer_review_mode_renders_local_draft_for_review():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp).resolve()
        project = root / "projects" / "demo-project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        (project / "project.yaml").write_text("id: demo-project\nsource_refs: []\n", encoding="utf-8")
        (project / "script" / "script.json").write_text("{}", encoding="utf-8")
        (project / "script" / "claims.json").write_text("{}", encoding="utf-8")
        (project / "sources" / "assets.json").write_text('{"assets": []}', encoding="utf-8")
        old_root, old_check, old_build = (
            produce_video.ROOT,
            produce_video.m5_production.copy_review.require_approved,
            produce_video.m5_production.build,
        )
        calls = []

        def refuse_review(_project):
            raise produce_video.m5_production.copy_review.CopyReviewRequired(
                "NOT_REVIEWED", "approve copy")

        def local_build(target, **options):
            calls.append(options)
            video = target / "final" / f"{target.name}.mp4"
            video.parent.mkdir(parents=True, exist_ok=True)
            video.write_bytes(b"local draft video")
            report = target / "receipts" / f"qc-report-{target.name}.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps({
                "graded_target": f"project://final/{target.name}.mp4",
                "overall": "PASS"}), encoding="utf-8")
            return {"stages": {"visual_qc": {"state": "PASS"}},
                    "stage_timings_seconds": {"motion": 1.0},
                    "human_review": "PENDING_FOUNDER_REVIEW"}

        produce_video.ROOT = root
        produce_video.m5_production.copy_review.require_approved = refuse_review
        produce_video.m5_production.build = local_build
        try:
            result = produce_video.produce(project, mode="REVIEW")
            saved = json.loads((project / "receipts" / "produce-video.json").read_text(encoding="utf-8"))
            assert result["state"] == "QC_PASSED"
            assert saved["copy_review_required_for_render"] is False
            assert saved["human_review"] == "PENDING_FOUNDER_REVIEW"
            assert calls == [{"require_copy_review": False}]
        finally:
            produce_video.ROOT = old_root
            produce_video.m5_production.copy_review.require_approved = old_check
            produce_video.m5_production.build = old_build


def test_local_motion_runs_each_placement_and_accepts_cache_reuse():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        plan = {"shots": [
            {"id": "line-1", "asset_id": "motion-A1", "spec": "motion/one.json"},
            {"id": "line-2", "asset_id": "motion-A2", "spec": "motion/two.json"},
        ]}
        plan_path = project / "motion" / "plan.json"
        plan_path.parent.mkdir()
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        script_path = project / "script" / "script.json"
        script_path.parent.mkdir()
        original_script = {"lines": [{"id": "line-1", "asset_id": "A1"},
                                      {"id": "line-2", "asset_id": "A2"}]}
        script_path.write_text(json.dumps(original_script), encoding="utf-8")
        commands = []
        old_run = m5_production.hidden_run

        def fake_run(command, **_options):
            commands.append(command)
            payload = {"execution": {"state": "EXECUTED" if len(commands) == 1 else "REUSED",
                                     "reused": len(commands) > 1,
                                     "adapter_receipt": {"asset_id": "ok"}},
                       "receipt": "receipts/executions/test.json"}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

        m5_production.hidden_run = fake_run
        try:
            result = m5_production.stage_motion(
                project, {"motion": {"backend": "huashu-art-motion",
                                     "shot_plan": "motion/plan.json"}},
                {"lines": [{"id": "line-1", "asset_id": "A1"},
                           {"id": "line-2", "asset_id": "A2"}]},
                require_copy_review=False)
            assert result == {"state": "OK", "backend": "huashu-art-motion", "shots": 2}
            assert len(commands) == 2
            assert all("--mode" in command and command[command.index("--mode") + 1] == "AUTO"
                       for command in commands)
            receipt = json.loads((project / "receipts" / "motion-stage.json").read_text())
            assert [row["placement_id"] for row in receipt["shots"]] == ["line-1", "line-2"]
            assert [row["execution_state"] for row in receipt["shots"]] == [
                "EXECUTED", "REUSED"]
            assert [row["reused_render"] for row in receipt["shots"]] == [False, True]
            assert json.loads(script_path.read_text()) == original_script
            assert [command[command.index("--asset-id") + 1] for command in commands] == [
                "motion-A1", "motion-A2"]
        finally:
            m5_production.hidden_run = old_run


def test_motion_stage_refuses_an_unmapped_plan_before_rendering():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        plan_path = project / "plan.json"
        plan_path.write_text(json.dumps({"shots": [
            {"id": "other", "asset_id": "A1", "spec": "one.json"}]}),
            encoding="utf-8")
        try:
            m5_production.stage_motion(
                project, {"motion": {"backend": "huashu-art-motion",
                                     "shot_plan": "plan.json"}},
                {"lines": [{"id": "line-1", "asset_id": "A1"}]},
                require_copy_review=False)
        except m5_production.M5Blocked as exc:
            assert "does not map" in str(exc)
        else:
            raise AssertionError("an unmapped animation must not run")


def test_huashu_render_cache_requires_matching_inputs_and_output_hash():
    verify_root = ROOT / ".verify-tmp"
    verify_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=verify_root) as temp:
        project = Path(temp)
        for relative, payload in {
            "script/script.json": {"lines": [{"id": "P-01", "asset_id": "A1",
                                                "claim": "C-01"}]},
            "script/claims.json": {"claims": [{"id": "C-01", "artifacts": ["E-01"]}]},
            "sources/source-refs.json": {"refs": [{"id": "E-01"}]},
            "motion.json": {"duration": 4, "width": 1080, "height": 1920,
                             "fps": 30, "cues": [{"start": 0, "end": 4}]},
        }.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        output = project / "assets" / "generated" / "huashu" / "A1.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"verified motion output")
        spec_path = project / "motion.json"
        runtime = {"skill_id": "huashu-art-motion", "version": "1.2.0"}
        inputs = {
            "script": huashu_motion_adapter._sha(project / "script/script.json"),
            "claims": huashu_motion_adapter._sha(project / "script/claims.json"),
            "source_refs": huashu_motion_adapter._sha(project / "sources/source-refs.json"),
            "spec": huashu_motion_adapter._sha(spec_path),
        }
        digest = huashu_motion_adapter._sha(output)
        receipt = {
            "schema": "contentops.video-receipt/v1",
            "asset_id": "A1", "placement_id": "P-01",
            "runtime": runtime, "input_sha256": inputs,
            "fingerprint": huashu_motion_adapter._motion_fingerprint(
                inputs, runtime, "P-01"),
            "output": {"repo_path": output.relative_to(ROOT).as_posix(),
                       "output_sha256": digest},
            "technical_qc": {"approved": True, "black_frame_segments": []},
        }
        receipt_path = project / "receipts" / "huashu-A1.json"
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        cached = huashu_motion_adapter._cached_render(
            project, "A1", "P-01", "motion.json", runtime)
        assert cached is not None
        assert cached["output"] == output

        output.write_bytes(b"changed output")
        assert huashu_motion_adapter._cached_render(
            project, "A1", "P-01", "motion.json", runtime) is None


def test_future_intelligence_auto_plan_uses_account_palette_and_rag_grammar():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence",
            account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "claim": "C-01",
                               "narration": "混合检索并行找词项和语义候选。"}]},
            narration={"lines": [{"start": 0.0, "duration": 4.5}]},
            source_assets={},
        )
        shot = result["plan"]["shots"][0]
        spec = json.loads((project / shot["spec"]).read_text(encoding="utf-8"))
        assert shot["semantic_class"] == "retrieval"
        assert shot["motion_syntax"] == "t1_3b1b"
        assert shot["source_asset_id"] == "source-01"
        assert spec["duration"] == 4.5
        assert spec["theme"] == dna["visual"]["motion"]["motion_profile"]["palette"]
        assert spec["grammar"] == "t1_3b1b"
        assert [cue["kind"] for cue in spec["cues"]] == [
            "equation", "equation", "equation", "point", "highlight"]
        assert [cue.get("text") for cue in spec["cues"][:4]] == [
            "Query → 词项", "Query → 语义 候选",
            "词项 + 语义 → 融合候选", "两路候选完成融合"]
        assert spec["cues"][0]["at"] == 0
        assert result["plan"]["compiler"] == "contentops.motion_planner/v4"
        assert result["plan"]["compiler_sha256"] == motion_planner._file_sha(
            Path(motion_planner.__file__).resolve())
        assert max(cue["at"] for cue in spec["cues"]) < spec["duration"]

        revised = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence",
            account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "claim": "C-01",
                               "narration": "混合检索并行找词项和语义候选，再进行重排。"}]},
            narration={"lines": [{"start": 0.0, "duration": 4.5}]},
            source_assets={},
        )
        assert revised["path"] != result["path"]
        assert revised["path"].is_file() and result["path"].is_file()
        assert len(list((project / "motion" / "auto").glob("shot-plan-*.json"))) == 2


def test_huashu_motion_auto_film_keeps_a_local_source_screenshot():
    import huashu_motion_backend

    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "source.png"
        source.write_bytes(b"registered source image bytes")
        assets_path = project / "sources" / "assets.json"
        assets_path.parent.mkdir(parents=True)
        assets_path.write_text(json.dumps({"assets": [{
            "id": "source-01", "type": "CODE_SNAPSHOT",
            "repo_path": source.relative_to(ROOT).as_posix(),
            "source_document": "src/retriever.py",
        }]}), encoding="utf-8")
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        shot = {"placement_id": "P-01", "source_asset_id": "source-01",
                "content_point": "Query expansion", "semantic_class": "code"}
        line = {"id": "P-01", "caption": "Query expansion"}
        runtime = ROOT / ".verify-tmp" / "huashu-motion-runtime"
        with mock.patch.object(huashu_motion_backend, "resolve_runtime", return_value=runtime):
            film_rel = huashu_motion_backend.author_auto_film(project, shot, line, dna, 3.0)
        film = project / film_rel
        assert (film / "assets" / "source.png").read_bytes() == source.read_bytes()
        assert "assets/source.png" in (film / "index.html").read_text(encoding="utf-8")
        assert (film / "vendor" / "gsap.min.js").is_file()


def test_huashu_motion_auto_film_uses_readable_lines_from_registered_source():
    import huashu_motion_backend

    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "source.png"
        source.write_bytes(b"registered source image bytes")
        document = project / "sources" / "retriever.py"
        document.parent.mkdir(parents=True)
        document.write_text(
            "class Retriever:\n"
            "    def expand_query(self, query):\n"
            "        return QueryExpander.expand(query)\n"
            "    def retrieve(self, query):\n"
            "        bm25 = self.bm25_index.score(query)\n"
            "        dense = self.vector_index.search(query)\n"
            "        return reciprocal_rank_fusion(bm25, dense)\n",
            encoding="utf-8",
        )
        (project / "sources" / "assets.json").write_text(json.dumps({"assets": [{
            "id": "source-01", "type": "CODE_SNAPSHOT",
            "repo_path": source.relative_to(ROOT).as_posix(),
            "source_document": "sources/retriever.py",
        }]}), encoding="utf-8")
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        shot = {"placement_id": "P-02", "source_asset_id": "source-01",
                "content_point": "BM25 dense retrieval and RRF fusion", "semantic_class": "retrieval"}
        line = {"id": "P-02", "caption": "BM25 dense retrieval and RRF fusion"}
        runtime = ROOT / ".verify-tmp" / "huashu-motion-runtime"
        with mock.patch.object(huashu_motion_backend, "resolve_runtime", return_value=runtime):
            film_rel = huashu_motion_backend.author_auto_film(project, shot, line, dna, 3.0)
        html_path = project / film_rel / "index.html"
        html_text = html_path.read_text(encoding="utf-8")
        assert "bm25 = self.bm25_index.score(query)" in html_text
        assert "reciprocal_rank_fusion(bm25, dense)" in html_text
        assert "bm25 = self.bm25_index.score(query)" in html_text
        assert "MECHANISM SCHEMATIC · NOT A RUNTIME RESULT" in html_text
        assert "核心步骤" not in html_text


def test_future_intelligence_auto_plan_explains_rrf_with_rank_contributions():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence",
            account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "claim": "C-01",
                               "narration": "RRF 按各结果列表名次累加倒数分。"}]},
            narration={"lines": [{"start": 0.0, "duration": 4.5}]},
            source_assets={},
        )
        spec = json.loads((project / result["plan"]["shots"][0]["spec"])
                          .read_text(encoding="utf-8"))
        equations = [cue["text"] for cue in spec["cues"]
                     if cue["kind"] == "equation"]
        assert equations == [
            "rankᵢ(d)",
            "1 / (k + rankᵢ(d))",
            "score(d) = Σᵢ 1 / (k + rankᵢ(d))",
        ]
        assert spec["cues"][-1] == {
            "at": 3.85, "kind": "highlight", "data": {"target": "equation"}}


def test_future_intelligence_auto_plan_derives_agent_flow_from_named_terms():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence",
            account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "claim": "C-01",
                               "narration": "Agent 工具调用后，结果写入状态并支持任务恢复。"}]},
            narration={"lines": [{"start": 0.0, "duration": 5.0}]},
            source_assets={},
        )
        spec = json.loads((project / result["plan"]["shots"][0]["spec"])
                          .read_text(encoding="utf-8"))
        assert spec["grammar"] == "t1_3b1b"
        assert [cue.get("text") for cue in spec["cues"][:-1]] == [
            "Agent → 工具", "工具 → 结果", "结果 → 状态", "状态 → 恢复"]
        assert spec["cues"][-1]["kind"] == "highlight"
        assert max(cue["at"] for cue in spec["cues"]) < spec["duration"]


def test_future_intelligence_auto_plan_derives_protocol_flow_from_named_terms():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence",
            account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "claim": "C-01",
                               "narration": "MCP 协议中客户端向服务端发起工具调用，再接收结果。"}]},
            narration={"lines": [{"start": 0.0, "duration": 5.0}]},
            source_assets={},
        )
        spec = json.loads((project / result["plan"]["shots"][0]["spec"])
                          .read_text(encoding="utf-8"))
        assert spec["grammar"] == "t1_3b1b"
        assert [cue.get("text") for cue in spec["cues"][:-1]] == [
            "MCP → 协议", "协议 → Client", "Client → Server", "Server → 工具",
            "工具 → 结果"]
        assert spec["cues"][-1]["kind"] == "highlight"
        assert max(cue["at"] for cue in spec["cues"]) < spec["duration"]


def test_auto_plan_pads_sub_two_second_narration_with_a_visual_hold():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence",
            account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "narration": "RAG 短句。"}]},
            narration={"lines": [{"start": 0.0, "duration": 1.83}]},
            source_assets={},
        )
        shot = result["plan"]["shots"][0]
        spec = json.loads((project / shot["spec"]).read_text(encoding="utf-8"))
        assert shot["duration_s"] == 1.83
        assert spec["duration"] == 2.0
        assert spec["contentops_timing"] == {
            "narration_duration_s": 1.83, "visual_hold_padding_s": 0.17}


def test_future_intelligence_auto_plan_does_not_compare_raw_retrieval_scores():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence",
            account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "claim": "C-01",
                               "narration": "融合排名，避免直接比较不同原始分数。"}]},
            narration={"lines": [{"start": 0.0, "duration": 4.5}]},
            source_assets={},
        )
        spec = json.loads((project / result["plan"]["shots"][0]["spec"])
                          .read_text(encoding="utf-8"))
        equations = [cue["text"] for cue in spec["cues"]
                     if cue["kind"] == "equation"]
        assert equations == [
            "BM25 原始分",
            "向量相似度",
            "1/(k+rank₁(d)) + 1/(k+rank₂(d))",
        ]


def test_1024_auto_plan_requires_and_carries_real_source_stills():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "assets" / "terminal.png"
        source.parent.mkdir(parents=True)
        # The planner only localizes an existing source path; it does not claim
        # this minimal fixture passed visual or rights acceptance.
        source.write_bytes(b"test image placeholder")
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-1024.json").read_text(encoding="utf-8"))
        source_id = "evidence-01"
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-1024", account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": source_id,
                               "narration": "这段代码调用 MCP 工具接口。"}]},
            narration={"lines": [{"start": 0.0, "duration": 3.0}]},
            source_assets={source_id: {"id": source_id, "type": "REAL_SCREENSHOT",
                                       "repo_path": source.relative_to(ROOT).as_posix()}},
        )
        shot = result["plan"]["shots"][0]
        spec = json.loads((project / shot["spec"]).read_text(encoding="utf-8"))
        assert shot["source_asset_id"] == source_id
        assert shot["motion_syntax"] == "y3_whiteboard"
        assert spec["cues"][0]["kind"] == "image"
        assert spec["cues"][0]["image"]
        digest = huashu_motion_adapter._sha(source)
        assert spec["contentops_source"]["sha256"] == digest
        manifest = project / "sources" / "assets.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"assets": [{
            "id": source_id, "type": "REAL_SCREENSHOT", "repo_path": source.relative_to(ROOT).as_posix(),
            "sha256": digest, "permission": "CREATED_BY_OWNER", "usage_scope": "test fixture only"}]}),
            encoding="utf-8")
        validated_path, validated_spec = huashu_motion_adapter._validate_spec(project, shot["spec"])
        assert validated_path.is_file() and validated_spec["contentops_source"]["asset_id"] == source_id
        source.write_bytes(b"changed screenshot bytes")
        try:
            huashu_motion_adapter._validate_spec(project, shot["spec"])
        except ValueError as exc:
            assert "hash does not match" in str(exc)
        else:
            raise AssertionError("changed source image bytes must invalidate the motion spec")


def test_1024_uses_ocr_matched_screenshot_region_for_camera_motion():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "assets" / "terminal.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"registered screenshot bytes")
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-1024.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-1024", account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "evidence-01",
                               "narration": "MCP 工具调用完成后返回真实结果。"}]},
            narration={"lines": [{"start": 0.0, "duration": 3.5}]},
            source_assets={"evidence-01": {
                "id": "evidence-01", "type": "USER_PROVIDED_IMAGE",
                "repo_path": source.relative_to(ROOT).as_posix(),
                "ocr_regions": [{"text": "MCP 工具调用", "confidence": 0.94,
                                 "rect": [0.11, 0.22, 0.31, 0.06]}],
            }},
        )
        shot = result["plan"]["shots"][0]
        spec = json.loads((project / shot["spec"]).read_text(encoding="utf-8"))
        assert shot["motion_syntax"] == "t2_keynote_ui"
        assert shot["ocr_targets"] == [{"text": "MCP 工具调用", "confidence": 0.94,
                                        "rect": [0.11, 0.22, 0.31, 0.06],
                                        "matched_terms": ["mcp", "具调", "工具", "调用"]}]
        assert spec["grammar"] == "t2_keynote_ui"
        assert spec["cues"][0]["kind"] == "image" and spec["cues"][0]["image"]
        assert spec["cues"][1] == {
            "at": 0.8, "kind": "highlight",
            "data": {"rect": [0.11, 0.22, 0.31, 0.06]}}


def test_code_snapshot_uses_its_ocr_region_instead_of_a_generic_icon():
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "assets" / "source-anchor.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(png)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence", account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "narration": "Configuration settings for"}]},
            narration={"lines": [{"start": 0.0, "duration": 3.0}]},
            source_assets={"source-01": {
                "id": "source-01", "type": "CODE_SNAPSHOT",
                "repo_path": source.relative_to(ROOT).as_posix(),
                "ocr_regions": [
                    {"text": "Configuration settings for", "confidence": 0.96,
                     "rect": [0.1, 0.15, 0.7, 0.04]},
                    {"text": "Master configuration for", "confidence": 0.94,
                     "rect": [0.1, 0.28, 0.7, 0.04]},
                ],
            }},
        )
        shot = result["plan"]["shots"][0]
        spec = json.loads((project / shot["spec"]).read_text(encoding="utf-8"))
        assert shot["motion_syntax"] == "t2_keynote_ui"
        assert len(shot["ocr_targets"]) == 1
        assert shot["ocr_targets"][0]["rect"] == [0.1, 0.15, 0.7, 0.04]
        assert spec["cues"][0]["kind"] == "image"
        assert spec["cues"][1]["kind"] == "highlight"


def test_code_snapshot_without_ocr_uses_progressive_image_motion_without_highlight():
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "assets" / "source-anchor.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(png)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence", account_dna=dna,
            script={"lines": [{"id": "P-01", "asset_id": "source-01",
                               "narration": "A line with no source OCR match"}]},
            narration={"lines": [{"start": 0.0, "duration": 3.0}]},
            source_assets={"source-01": {
                "id": "source-01", "type": "CODE_SNAPSHOT",
                "repo_path": source.relative_to(ROOT).as_posix(),
            }},
        )
        shot = result["plan"]["shots"][0]
        spec = json.loads((project / shot["spec"]).read_text(encoding="utf-8"))
        assert shot["motion_syntax"] == "y3_whiteboard"
        assert spec["cues"][0]["kind"] == "image"
        assert any(cue["kind"] in {"draw", "point"} for cue in spec["cues"])
        assert not any(cue["kind"] == "highlight" for cue in spec["cues"])


def test_code_snapshot_uses_each_ocr_camera_target_only_once():
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "assets" / "source-anchor.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(png)
        dna = json.loads((ROOT / "config" / "accounts" /
                          "x-superplay-future-intelligence.json").read_text(encoding="utf-8"))
        lines = [
            {"id": f"P-{index:02d}", "asset_id": "source-01",
             "narration": "Configuration settings for"}
            for index in range(1, 4)
        ]
        result = motion_planner.build_auto_plan(
            project=project, account_id="x-superplay-future-intelligence", account_dna=dna,
            script={"lines": lines},
            narration={"lines": [{"start": i * 3.0, "duration": 2.8}
                                  for i in range(3)]},
            source_assets={"source-01": {
                "id": "source-01", "type": "CODE_SNAPSHOT",
                "repo_path": source.relative_to(ROOT).as_posix(),
                "ocr_regions": [
                    {"text": "Configuration settings", "confidence": 0.96,
                     "rect": [0.1, 0.15, 0.7, 0.04]},
                    {"text": "Configuration settings", "confidence": 0.95,
                     "rect": [0.1, 0.28, 0.7, 0.04]},
                ],
            }},
        )
        grammars = [shot["motion_syntax"] for shot in result["plan"]["shots"]]
        assert grammars == ["t2_keynote_ui", "t2_keynote_ui", "y3_whiteboard"]


def test_motion_plan_uses_the_code_snapshot_for_the_claimed_source_file():
    refs = [{"path": "projects/demo/sources/research-candidates/files/src/engine.py"}]
    assets = [
        {"id": "source-anchor-01", "type": "CODE_SNAPSHOT",
         "source_document": "sources/research-candidates/files/src/config.py"},
        {"id": "source-anchor-02", "type": "CODE_SNAPSHOT",
         "source_document": "sources/research-candidates/files/src/engine.py"},
        {"id": "generated-video", "type": "GENERATED_VIDEO",
         "source_document": "sources/research-candidates/files/src/engine.py"},
    ]
    assert m5_production._source_snapshot_for_refs(refs, assets) == "source-anchor-02"


def test_local_asset_ocr_boxes_are_normalized_and_clamped():
    regions = raw_video_inputs._normalized_ocr_regions(
        [[[ [110, 220], [420, 220], [420, 340], [110, 340]],
          "MCP 工具调用", "0.94"],
         [[[1070, 1900], [1120, 1900], [1120, 1940], [1070, 1940]],
          "edge", 0.8],
         [[], "bad score", "oops"]],
        1080, 1920)
    assert regions == [
        {"text": "MCP 工具调用", "confidence": 0.94,
         "rect": [0.101852, 0.114583, 0.287037, 0.0625]},
        {"text": "edge", "confidence": 0.8,
         "rect": [0.990741, 0.989583, 0.009259, 0.010417]},
    ]
    assert raw_video_inputs._normalized_ocr_regions([], 0, 1920) == []


def test_source_snapshot_selects_verbatim_claim_relevant_lines():
    shown = raw_video_inputs._topical_source_lines(
        ["header", "unrelated setup", "cache = None", "other", "def hybrid_retrieval():",
         "    bm25 = retrieve_terms()", "    vector = retrieve_semantic()", "return results"],
        ["hybrid retrieval combines bm25 and semantic vector candidates"], limit=5)
    assert [line for _, line in shown] == [
        "def hybrid_retrieval():", "    bm25 = retrieve_terms()",
        "    vector = retrieve_semantic()", "return results"]
    assert [number for number, _ in shown] == [5, 6, 7, 8]


def test_m5_auto_selects_future_profile_motion_after_measured_narration():
    import huashu_motion_backend

    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        for relative, payload in {
            "sources/assets.json": {"assets": [{"id": "source-01",
                                                    "repo_path": "projects/source.png",
                                                    "type": "SCREENSHOT"}]},
            "sources/source-refs.json": {"refs": [{"id": "E-01",
                                                      "url": "https://docs.example.test/rag"}]},
            "script/script.json": {"lines": [{"id": "P-01", "asset_id": "source-01",
                                                "claim": "C-01",
                                                "narration": "混合检索并行找词项和语义候选。"}]},
            "script/claims.json": {"claims": [{"id": "C-01", "artifacts": ["E-01"]}]},
        }.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        old_run = m5_production.hidden_run
        commands = []

        def fake_run(command, **_options):
            commands.append(command)
            payload = {"execution": {"state": "EXECUTED",
                                     "adapter_receipt": {"asset_id": "huashu-P-01"}},
                       "receipt": "receipts/executions/test.json"}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

        m5_production.hidden_run = fake_run
        film_mock = None
        try:
            film_mock = mock.patch.object(
                huashu_motion_backend, "author_auto_film",
                return_value="motion/huashu-motion/auto/P-01-test",
            )
            film_mock.start()
            result = m5_production.stage_motion(
                project,
                {"account_slug": "x-superplay-future-intelligence"},
                {"lines": [{"id": "P-01", "asset_id": "source-01", "claim": "C-01",
                            "narration": "混合检索并行找词项和语义候选。"}]},
                require_copy_review=False,
                narration={"lines": [{"start": 0.0, "duration": 4.5}]},
            )
        finally:
            m5_production.hidden_run = old_run
            if film_mock:
                film_mock.stop()
        plan_paths = list((project / "motion" / "auto").glob("huashu-motion-shot-plan-*.json"))
        assert len(plan_paths) == 1
        plan = json.loads(plan_paths[0].read_text(encoding="utf-8"))
        receipt = json.loads((project / "receipts" / "motion-stage.json")
                             .read_text(encoding="utf-8"))
        assert result["backend"] == "huashu-motion"
        assert plan["account_id"] == "x-superplay-future-intelligence"
        assert plan["shots"][0]["source_refs"] == ["https://docs.example.test/rag"]
        assert receipt["shots"][0]["content_point"] == "混合检索并行找词项和语义候选。"
        assert commands[0][commands[0].index("--asset-id") + 1] == "huashu-motion-P-01"


def test_auto_profile_motion_receipt_replaces_the_still_on_the_m5_timeline():
    with tempfile.TemporaryDirectory(dir=ROOT / ".verify-tmp") as temp:
        project = Path(temp)
        source = project / "assets" / "source.png"
        clip = project / "assets" / "generated" / "huashu" / "huashu-P-01.mp4"
        source.parent.mkdir(parents=True)
        clip.parent.mkdir(parents=True)
        source.write_bytes(b"registered user source still")
        clip.write_bytes(b"generated Huashu motion clip")
        script = {"schema": m5_production.SCRIPT_SCHEMA, "lines": [{
            "id": "P-01", "asset_id": "source-01", "claim": "C-01",
            "narration": "先召回，再融合候选。", "caption": "两路召回",
        }]}
        script_path = project / "script" / "script.json"
        script_path.parent.mkdir(parents=True)
        script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        motion_receipt = {
            "schema": "contentops.m5-motion-stage/v1", "backend": "huashu-art-motion",
            "state": "OK", "script_sha256": m5_production._payload_sha256(script),
            "shots": [{"placement_id": "P-01", "asset_id": "huashu-P-01"}],
        }
        (project / "receipts" / "motion-stage.json").parent.mkdir(parents=True)
        (project / "receipts" / "motion-stage.json").write_text(
            json.dumps(motion_receipt), encoding="utf-8")
        assets = {
            "source-01": {"id": "source-01", "type": "REAL_SCREENSHOT",
                          "repo_path": source.relative_to(ROOT).as_posix()},
            "huashu-P-01": {"id": "huashu-P-01", "type": "GENERATED_VIDEO",
                            "repo_path": clip.relative_to(ROOT).as_posix(),
                            "generated": True},
        }
        narration = {"lines": [{"start": 0.0, "duration": 4.0}],
                     "duration_s": 4.0, "voice_provider": "existing"}

        result = m5_production.stage_storyboard(
            project, {"target": {"resolution": "1080x1920"}}, script,
            narration, {}, assets)
        shot = result["storyboard"]["shots"][0]
        assert shot["video"] == clip.relative_to(ROOT).as_posix()
        assert result["storyboard"]["generated_visuals"]["asset_ids"] == ["huashu-P-01"]

        # A stale successful receipt is ignored in an automatic account profile,
        # and a specifically requested backend fails closed on the same mismatch.
        changed_script = json.loads(json.dumps(script))
        changed_script["lines"][0]["narration"] = "重排候选并输出结果。"
        script_path.write_text(json.dumps(changed_script, ensure_ascii=False), encoding="utf-8")
        fallback = m5_production.stage_storyboard(
            project, {"target": {"resolution": "1080x1920"}}, changed_script,
            narration, {}, assets)
        fallback_shot = fallback["storyboard"]["shots"][0]
        assert "video" not in fallback_shot
        assert fallback_shot["image"] == source.relative_to(ROOT).as_posix()
        try:
            m5_production.stage_storyboard(
                project, {"motion": {"backend": "huashu-art-motion"}},
                changed_script, narration, {}, assets)
        except m5_production.M5Blocked as exc:
            assert "does not match" in str(exc)
        else:
            raise AssertionError("an explicit backend must reject a stale motion receipt")


def main() -> int:
    tests = (test_visual_gate_states_are_fail_closed_and_never_approve_publication,
             test_huashu_preflight_auto_and_review_allow_local_preview_without_grant,
             test_huashu_local_effect_policy_does_not_authorize_paid_or_publish_effects,
             test_huashu_auto_local_render_runs_repeated_shots_without_grant,
             test_huashu_valid_cached_render_is_reused_without_renderer_call,
             test_huashu_accepts_only_exact_nonfactual_editorial_transitions_without_claims,
             test_huashu_source_cta_requires_all_prior_claims_in_verified_inventory,
             test_storyboard_preserves_each_narration_pause_inside_its_own_shot,
             test_a_video_asset_reaches_the_storyboard_as_a_clip,
             test_a_still_asset_is_not_labelled_a_clip,
             test_runtime_release_facts_use_the_source_image_motion_grammar,
             test_explicit_user_media_is_preview_only_and_hash_bound,
             test_user_video_import_records_metadata_and_three_review_frames,
             test_unified_producer_passes_selected_media_into_m5,
             test_the_composer_key_and_the_receipt_key_agree,
             test_a_missing_asset_stops_the_build,
             test_a_non_positive_duration_stops_the_build,
             test_misaligned_lines_and_timings_stop_the_build,
             test_the_same_asset_can_support_multiple_timeline_placements,
             test_minimax_narration_requires_an_explicit_voice_and_never_uses_sapi,
             test_video_account_dna_enables_h3_bookends_with_explicit_budget_policy,
             test_motion_backend_selection_is_per_shot_and_fail_closed,
             test_m5_motion_stage_dispatches_explicit_huashu_motion_shots,
             test_huashu_motion_film_path_must_remain_project_local,
             test_h3_avatar_bookends_reuse_only_hash_bound_subscription_outputs,
             test_avatar_bookend_composition_preserves_the_main_only_render,
             test_partial_avatar_preview_keeps_only_the_successful_clip_and_main_video,
             test_existing_narration_without_a_receipt_is_refused,
             test_existing_narration_bound_to_another_script_is_refused,
             test_existing_narration_without_line_timings_is_refused,
             test_existing_narration_that_matches_is_reused_without_a_provider_call,
             test_producer_reuses_current_qc_pass_without_rebuilding,
             test_producer_review_mode_renders_local_draft_for_review,
             test_local_motion_runs_each_placement_and_accepts_cache_reuse,
             test_motion_stage_refuses_an_unmapped_plan_before_rendering,
             test_huashu_render_cache_requires_matching_inputs_and_output_hash,
             test_future_intelligence_auto_plan_uses_account_palette_and_rag_grammar,
             test_future_intelligence_auto_plan_explains_rrf_with_rank_contributions,
             test_future_intelligence_auto_plan_does_not_compare_raw_retrieval_scores,
             test_auto_plan_pads_sub_two_second_narration_with_a_visual_hold,
             test_1024_auto_plan_requires_and_carries_real_source_stills,
             test_1024_uses_ocr_matched_screenshot_region_for_camera_motion,
             test_code_snapshot_uses_its_ocr_region_instead_of_a_generic_icon,
             test_code_snapshot_without_ocr_uses_progressive_image_motion_without_highlight,
             test_code_snapshot_uses_each_ocr_camera_target_only_once,
             test_motion_plan_uses_the_code_snapshot_for_the_claimed_source_file,
             test_local_asset_ocr_boxes_are_normalized_and_clamped,
             test_source_snapshot_selects_verbatim_claim_relevant_lines,
             test_m5_auto_selects_future_profile_motion_after_measured_narration,
             test_auto_profile_motion_receipt_replaces_the_still_on_the_m5_timeline)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} M5 motion-integration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
