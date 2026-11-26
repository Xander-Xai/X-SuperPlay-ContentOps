"""The copy fingerprint must cover what the film shows and claims, not only what
it narrates.

The failure this prevents: a review is approved, then the clip behind a shot is
swapped, or the caption is rewritten, or a claim is rebound to different
evidence — and the fingerprint does not move, so a stale ``APPROVED`` still
passes. That was possible while ``video``, ``caption``, ``claim`` and ``source``
were absent from ``COPY_FIELDS``.
"""
from __future__ import annotations

import contextlib
import base64
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops import paths as contentops_paths  # noqa: E402
contentops_paths._env_loaded = True  # keep CLI tests offline; never consult repository .env
from contentops.workflow import canonical_copy, copy_review, preresearch, topic_package  # noqa: E402


def _seed_intent(project: Path, target_pipeline: str = "VIDEO") -> dict:
    """The router-shaped intent this fixture's research is done against."""
    intent = {
        "schema": preresearch.INTENT_SCHEMA,
        "account_id": "x-superplay-1024",
        "account_profile_version": "acc-x-superplay-1024@v3",
        "route_mode": "USER_TOPIC",
        "topic": "Regression fixture topic",
        "evidence_status": "verification_required",
        "approval_status": "pending",
        "target_pipeline": target_pipeline,
        "brief_status": "draft",
        "route_context": {"mode": "USER_TOPIC", "topic_origin": "USER_INPUT"},
        "created_at": "2026-11-12T09:00:00Z",
    }
    folder = project / preresearch.RESEARCH_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "content-intent.json").write_text(
        json.dumps(intent, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return intent


def _seed_preresearch(project: Path, target_pipeline: str = "VIDEO") -> None:
    """CLI fixtures need a signed research gate before a copy decision."""
    _seed_intent(project, target_pipeline=target_pipeline)
    folder = project / preresearch.RESEARCH_DIR
    (folder / "project-reading.md").write_text(
        "# Project read-through\n\n## Files read\n\n"
        "- `docs/RUNBOOK.md` records the stable entry commands.\n"
        "- `scripts/copy_review.py` records the copy decision.\n"
        "- `src/contentops/workflow/copy_review.py` computes the fingerprint.\n\n"
        "## Findings\n\n- A copy decision is bound to a fingerprint.\n",
        encoding="utf-8")
    (folder / "outline.md").write_text(
        "# Outline\n\n## Topic\n\n- Fingerprint regression fixture.\n\n"
        "## Video\n\n- One shot.\n\n## Graphic\n\n- One draft.\n\n"
        "## Evidence\n\n- Three sources.\n", encoding="utf-8")
    (folder / "evidence-list.json").write_text(json.dumps({
        "schema": "contentops.precopy-research-evidence/v1",
        "items": [
            {"id": "S1", "kind": "primary", "title": "LoRA paper",
             "url": "https://arxiv.org/abs/2106.09685"},
            {"id": "S2", "kind": "primary", "title": "QLoRA paper",
             "url": "https://arxiv.org/abs/2305.14314"},
            {"id": "S3", "kind": "official", "title": "Runbook",
             "url": "repo://docs/RUNBOOK.md"},
        ]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / "boundary.md").write_text(
        "# Boundary\n\nThis phase does not render or publish.\n"
        "- `production_ready: false`\n- `publish_authorized: false`\n"
        "- Research approval is not copy approval.\n", encoding="utf-8")
    preresearch.approve(project, reviewer="Fixture Reviewer",
                        opinion="research reviewed for the CLI fixture")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _project(temp: Path) -> Path:
    """A minimal but realistic project: script, captions, asset map, media."""
    script = temp / "script"
    script.mkdir()
    (script / "master.md").write_text("# script\nhook line\n", encoding="utf-8")
    (script / "cut.srt").write_text(
        "1\n00:00:00,000 --> 00:00:05,000\n第一句\n", encoding="utf-8")
    (script / "lines.json").write_text(
        json.dumps({"lines": [{"line": 0, "text": "第一句"}]}, ensure_ascii=False),
        encoding="utf-8")
    (script / "claim-map.json").write_text(
        json.dumps({"claims": [{"id": "C1", "source": "A-ONE"}]}, ensure_ascii=False),
        encoding="utf-8")
    (script / "cut-plan.json").write_text(
        json.dumps({"schema": "contentops.cut-plan/v1",
                    "placements": [{"id": "P-01", "asset_id": "A-ONE"}]},
                   ensure_ascii=False), encoding="utf-8")
    (script / "script.json").write_text(
        json.dumps({"schema": "contentops.m5-script/v1",
                    "lines": [{"id": "s1", "narration": "第一句"}]},
                   ensure_ascii=False), encoding="utf-8")
    # Generated text: the pipeline writes it, so it must not be bound.
    (script / "narration.txt").write_text("第一句\n", encoding="utf-8")
    (temp / "motion").mkdir()
    (temp / "motion" / "timeline.json").write_text(
        json.dumps({"segments": [{"clip": "p00", "duration": 5.0}]}, ensure_ascii=False),
        encoding="utf-8")
    (temp / "receipts").mkdir()
    # Generated per-line timings: derived from the narration, never hashed.
    (temp / "receipts" / "voice-lines.json").write_text(
        json.dumps({"lines": [{"line": 0, "duration_s": 5.0}]}, ensure_ascii=False),
        encoding="utf-8")
    media = temp / "work" / "motion"
    media.mkdir(parents=True)
    clip = media / "beat-00.mp4"
    clip.write_bytes(b"clip bytes v1")
    (script / "assets.json").write_text(json.dumps({
        "schema": "contentops.asset-map/v1",
        "assets": {
            "A-ONE": {"kind": "motion", "path": "project://work/motion/beat-00.mp4",
                      "sha256": _sha(clip.read_bytes()), "evidence_capable": False},
        },
    }, ensure_ascii=False), encoding="utf-8")
    shot = {"unit": "u1", "narration": "第一句", "caption": "第一句",
            "claim": "C1", "image": None, "video": "project://work/motion/beat-00.mp4",
            "source": "project://work/motion/beat-00.mp4", "source_type": "motion",
            "duration": 5.0, "function": "proof", "dna_role": "support"}
    (script / "storyboard.json").write_text(json.dumps({
        "size": "1080x1920", "narration": "project://work/narration.wav",
        "subtitle": "project://assets/captions/cut.srt", "runtime": {"release": "v0.2.1"},
        "shots": [shot],
    }, ensure_ascii=False), encoding="utf-8")
    return temp


def _board(project: Path) -> dict:
    return json.loads((project / "script" / "storyboard.json").read_text(encoding="utf-8"))


def _write_board(project: Path, document: dict) -> None:
    (project / "script" / "storyboard.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8")


def _approve(project: Path) -> dict:
    return copy_review.decide(project, status_value="APPROVED", reviewer="test-reviewer",
                              opinion="fixture approval for a fingerprint test",
                              reviewed_at="2026-11-01T00:00:00Z")


def test_swapping_the_video_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        assert copy_review.status(project)["state"] == "APPROVED"
        document = _board(project)
        document["shots"][0]["video"] = "project://work/motion/beat-01.mp4"
        _write_board(project, document)
        gate = copy_review.status(project)
        assert gate["state"] == "STALE", gate
        assert gate["ok"] is False


def test_changing_the_caption_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "script" / "cut.srt").write_text(
            "1\n00:00:00,000 --> 00:00:05,000\n换了一句\n", encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_changing_the_claim_binding_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        document = _board(project)
        document["shots"][0]["claim"] = "C2"
        _write_board(project, document)
        assert copy_review.status(project)["state"] == "STALE"


def test_adding_the_machine_verified_claim_ledger_does_not_stale_the_copy():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "script" / "claims.json").write_text(json.dumps({
            "schema": "contentops.claim-ledger/v1",
            "claims": [{"id": "C1", "text": "A sourced statement.",
                        "artifacts": ["E1"], "quotes": ["A verbatim quote"]}],
        }), encoding="utf-8")
        gate = copy_review.status(project)
        assert gate["state"] == "APPROVED", gate


def test_exact_m5_projection_keeps_review_but_script_drift_stales_it():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        (project / "script" / "master.md").write_text(
            "# script\nApproved narration\n", encoding="utf-8")
        (project / "script" / "script.json").unlink()
        derivative = {
            "schema": "contentops.topic-copy-derivative/v1",
            "format": "VIDEO",
            "segments": [{"source_segment_id": "S1", "text": "Approved narration",
                          "claim_refs": ["C1"]}],
        }
        (project / "00_brief").mkdir(exist_ok=True)
        (project / "00_brief" / "copy-derivative.json").write_text(
            json.dumps(derivative, ensure_ascii=False), encoding="utf-8")
        _approve(project)

        script = {"schema": "contentops.m5-script/v1", "lines": [{
            "id": "l1", "source_segment_id": "S1", "narration": "Approved narration",
            "caption": "Approved narration", "claim": "C1", "asset_id": "A-ONE",
        }]}
        script_path = project / "script" / "script.json"
        script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "APPROVED"

        script["lines"][0]["narration"] = "Changed narration"
        script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_m5_projection_accepts_every_derivative_claim_on_one_line():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        (project / "script" / "master.md").write_text(
            "# script\nApproved narration\n", encoding="utf-8")
        (project / "script" / "script.json").unlink()
        derivative = {
            "schema": "contentops.topic-copy-derivative/v1",
            "format": "VIDEO",
            "segments": [{"source_segment_id": "S1", "text": "Approved narration",
                          "claim_refs": ["C1", "C2"]}],
        }
        (project / "00_brief").mkdir(exist_ok=True)
        (project / "00_brief" / "copy-derivative.json").write_text(
            json.dumps(derivative, ensure_ascii=False), encoding="utf-8")
        _approve(project)
        script = {"schema": "contentops.m5-script/v1", "lines": [{
            "id": "l1", "source_segment_id": "S1", "narration": "Approved narration",
            "caption": "Approved narration", "claim": "C1", "claims": ["C1", "C2"],
            "asset_id": "A-ONE",
        }]}
        script_path = project / "script" / "script.json"
        script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "APPROVED"
        script["lines"][0]["claims"] = ["C1", "UNBOUND"]
        script_path.write_text(json.dumps(script, ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_changing_the_source_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        document = _board(project)
        document["shots"][0]["source"] = "project://sources/other.png"
        _write_board(project, document)
        assert copy_review.status(project)["state"] == "STALE"


def test_replacing_the_bytes_behind_an_unchanged_path_is_asset_drift():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        assert copy_review.status(project)["ok"] is True
        (project / "work" / "motion" / "beat-00.mp4").write_bytes(b"clip bytes v2")
        gate = copy_review.status(project)
        assert gate["state"] == "ASSET_DRIFT", gate
        assert gate["ok"] is False
        assert gate["asset_drift"][0]["asset_id"] == "A-ONE"


def test_missing_review_blocks():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        gate = copy_review.status(project)
        assert gate["state"] == "NOT_REVIEWED"
        assert gate["ok"] is False
        assert "--confirm" in gate["remedy"]
        try:
            copy_review.require_approved(project)
        except copy_review.CopyReviewRequired:
            pass
        else:
            raise AssertionError("a missing review must raise")


def test_a_stale_sha_blocks():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        record = _approve(project)
        record["copy_sha256"] = "0" * 64
        (project / "receipts" / "script-review.json").write_text(
            json.dumps(record), encoding="utf-8")
        gate = copy_review.status(project)
        assert gate["state"] == "STALE"
        assert gate["ok"] is False


def test_build_metadata_does_not_invalidate_the_review():
    """Rewriting paths the pipeline owns must not force a new review."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        document = _board(project)
        document["narration"] = "project://work/narration-110x.wav"
        document["subtitle"] = "project://assets/captions/cut-110x.srt"
        document["runtime"] = {"release": "v0.2.1", "commit": "deadbeef"}
        document["engine"] = "easel"
        _write_board(project, document)
        gate = copy_review.status(project)
        assert gate["state"] == "APPROVED", gate


def test_declared_assets_are_part_of_the_fingerprint():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        before = copy_review.copy_fingerprint(project)
        assets = json.loads((project / "script" / "assets.json").read_text(encoding="utf-8"))
        assets["assets"]["A-ONE"]["sha256"] = "1" * 64
        (project / "script" / "assets.json").write_text(
            json.dumps(assets, ensure_ascii=False), encoding="utf-8")
        assert copy_review.copy_fingerprint(project) != before


def test_editing_the_cut_plan_invalidates_the_review():
    """The cut plan decides shot order and placement; it is source, not output."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "script" / "cut-plan.json").write_text(
            json.dumps({"schema": "contentops.cut-plan/v1",
                        "placements": [{"id": "P-01", "asset_id": "A-ONE"},
                                       {"id": "P-02", "asset_id": "A-ONE"}]},
                       ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_editing_the_m5_script_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "script" / "script.json").write_text(
            json.dumps({"schema": "contentops.m5-script/v1",
                        "lines": [{"id": "s1", "narration": "换了台词"}]},
                       ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_editing_the_motion_timeline_invalidates_the_review():
    """Segment order and duration live outside script/, but change the film."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "motion" / "timeline.json").write_text(
            json.dumps({"segments": [{"clip": "p00", "duration": 7.5}]},
                       ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_editing_the_canonical_topic_copy_invalidates_the_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        canonical_dir = project / "00_brief"
        canonical_dir.mkdir()
        canonical = {
            "schema": canonical_copy.SCHEMA,
            "copy_id": "copy-001",
            "intent_sha256": "a" * 64,
            "research_sha256": "b" * 64,
            "account": "x-superplay-1024",
            "topic": "A verified topic",
            "segments": [{"id": "s1", "text": "A sourced statement.",
                          "claim_refs": ["C1"]}],
            "claims": {"C1": {"statement": "A sourced statement.",
                                "evidence_refs": ["E1"]}},
        }
        (canonical_dir / "canonical-copy.json").write_text(
            json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
        _approve(project)
        assert copy_review.status(project)["state"] == "APPROVED"
        canonical["segments"][0]["text"] = "A changed sourced statement."
        (canonical_dir / "canonical-copy.json").write_text(
            json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_generated_narration_text_does_not_invalidate_the_review():
    """The pipeline writes narration.txt; rewriting it must not expire a review."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "script" / "narration.txt").write_text("第一句\n（重写）\n", encoding="utf-8")
        gate = copy_review.status(project)
        assert gate["state"] == "APPROVED", gate


def test_generated_voice_timings_do_not_invalidate_the_review():
    """Per-line timings are derived from the narration, not an authored input."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _approve(project)
        (project / "receipts" / "voice-lines.json").write_text(
            json.dumps({"lines": [{"line": 0, "duration_s": 4.2}]},
                       ensure_ascii=False), encoding="utf-8")
        gate = copy_review.status(project)
        assert gate["state"] == "APPROVED", gate


def test_canonical_copy_validates_claim_and_evidence_bindings():
    document = {
        "schema": canonical_copy.SCHEMA,
        "copy_id": "copy-001",
        "intent_sha256": "a" * 64,
        "research_sha256": "b" * 64,
        "account": "x-superplay-1024",
        "topic": "A verified topic",
        "segments": [{"id": "s1", "text": "A sourced statement.",
                      "claim_refs": ["C1"]}],
        "claims": {"C1": {"statement": "A sourced statement.",
                            "evidence_refs": ["E1"]}},
    }
    assert canonical_copy.validate(document) == []


def test_canonical_copy_rejects_claims_without_evidence():
    document = {
        "schema": canonical_copy.SCHEMA,
        "copy_id": "copy-001",
        "intent_sha256": "a" * 64,
        "research_sha256": "b" * 64,
        "account": "x-superplay-1024",
        "topic": "A verified topic",
        "segments": [{"id": "s1", "text": "An unsupported statement.",
                      "claim_refs": ["C1"]}],
        "claims": {"C1": {"statement": "An unsupported statement.",
                            "evidence_refs": []}},
    }
    failures = canonical_copy.validate(document)
    assert any("evidence_refs" in failure for failure in failures), failures


def test_format_derivative_cannot_introduce_unbound_claims():
    canonical = {
        "schema": canonical_copy.SCHEMA,
        "copy_id": "copy-001",
        "intent_sha256": "a" * 64,
        "research_sha256": "b" * 64,
        "account": "x-superplay-1024",
        "topic": "A verified topic",
        "segments": [{"id": "s1", "text": "A sourced statement.",
                      "claim_refs": ["C1"]}],
        "claims": {"C1": {"statement": "A sourced statement.",
                            "evidence_refs": ["E1"]}},
    }
    derivative = {
        "schema": canonical_copy.DERIVATIVE_SCHEMA,
        "copy_id": "copy-001",
        "copy_sha256": canonical_copy.digest(canonical),
        "format": "VIDEO",
        "segments": [{"source_segment_id": "s1", "text": "A sourced statement.",
                      "claim_refs": ["C1", "C2"]}],
    }
    failures = canonical_copy.validate_derivative(canonical, derivative)
    assert any("claim set" in failure for failure in failures), failures


def test_format_derivative_binds_selected_canonical_source():
    canonical = {
        "schema": canonical_copy.SCHEMA,
        "copy_id": "copy-001",
        "intent_sha256": "a" * 64,
        "research_sha256": "b" * 64,
        "account": "x-superplay-1024",
        "topic": "A verified topic",
        "segments": [{"id": "s1", "text": "A sourced statement.",
                      "claim_refs": ["C1"]}],
        "claims": {"C1": {"statement": "A sourced statement.",
                            "evidence_refs": ["E1"]}},
    }
    derivative = canonical_copy.derive(canonical, "VIDEO", ["s1"])
    assert derivative["copy_id"] == "copy-001"
    assert derivative["copy_sha256"] == canonical_copy.digest(canonical)
    assert canonical_copy.validate_derivative(canonical, derivative) == []


def test_reworded_format_derivative_needs_its_own_current_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        _seed_preresearch(project)
        intent_path = project / preresearch.INTENT_FILE
        research = preresearch.check(project)
        canonical = {
            "schema": canonical_copy.SCHEMA,
            "copy_id": "copy-001",
            "intent_sha256": _sha(intent_path.read_bytes()),
            "research_sha256": research["artifacts_sha256"],
            "account": "x-superplay-1024",
            "topic": "Regression fixture topic",
            "segments": [{"id": "s1", "text": "Canonical statement.",
                          "claim_refs": ["C1"]}],
            "claims": {"C1": {"statement": "Canonical statement.",
                                "evidence_refs": ["S1"]}},
        }
        derivative = {
            "schema": canonical_copy.DERIVATIVE_SCHEMA,
            "copy_id": canonical["copy_id"],
            "copy_sha256": canonical_copy.digest(canonical),
            "format": "VIDEO",
            "segments": [{"source_segment_id": "s1", "text": "Video adaptation.",
                          "claim_refs": ["C1"]}],
        }
        (project / canonical_copy.CANONICAL_FILE).parent.mkdir(parents=True, exist_ok=True)
        (project / canonical_copy.CANONICAL_FILE).write_text(
            json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
        (project / canonical_copy.DERIVATIVE_FILE).write_text(
            json.dumps(derivative, ensure_ascii=False), encoding="utf-8")
        (project / "script" / "master.md").write_text(
            "# Video\n\nVideo adaptation.\n", encoding="utf-8")
        assert canonical_copy.status(project, "VIDEO")["ok"]
        _approve(project)
        assert copy_review.status(project)["ok"]
        derivative["segments"][0]["text"] = "A stronger video claim."
        (project / canonical_copy.DERIVATIVE_FILE).write_text(
            json.dumps(derivative, ensure_ascii=False), encoding="utf-8")
        (project / "script" / "master.md").write_text(
            "# Video\n\nA stronger video claim.\n", encoding="utf-8")
        assert copy_review.status(project)["state"] == "STALE"


def test_one_topic_package_feeds_video_and_graphic_projects_and_stales_together():
    with tempfile.TemporaryDirectory() as temp:
        projects_root = Path(temp) / "projects"
        package = projects_root / "same-topic"
        package.mkdir(parents=True)
        (package / "project.yaml").write_text(
            "id: same-topic\naccount_slug: x-superplay-1024\nstatus: initialized\n",
            encoding="utf-8")
        _seed_preresearch(package, target_pipeline="TOPIC")
        intent_path = package / preresearch.INTENT_FILE
        research = preresearch.check(package)
        canonical = {
            "schema": canonical_copy.SCHEMA,
            "copy_id": "shared-copy-001",
            "intent_sha256": _sha(intent_path.read_bytes()),
            "research_sha256": research["artifacts_sha256"],
            "account": "x-superplay-1024",
            "topic": "Regression fixture topic",
            "segments": [{"id": "s1", "text": "A shared sourced statement.",
                          "claim_refs": ["C1"]}],
            "claims": {"C1": {"statement": "A shared sourced statement.",
                                "evidence_refs": ["S1"]}},
        }
        (package / canonical_copy.CANONICAL_FILE).parent.mkdir(parents=True, exist_ok=True)
        (package / canonical_copy.CANONICAL_FILE).write_text(
            json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
        topic_package.initialize(package)
        copy_review.decide(package, status_value="APPROVED", reviewer="Founder",
                           opinion="Approved the shared topic copy",
                           reviewed_at="2026-11-19T00:00:00Z")

        children = {}
        for content_format, slug in (("VIDEO", "same-topic-video"),
                                     ("GRAPHIC_TEXT", "same-topic-graphic")):
            child = projects_root / slug
            (child / "receipts").mkdir(parents=True)
            (child / "00_brief").mkdir()
            (child / "project.yaml").write_text(
                f"id: {slug}\naccount_slug: x-superplay-1024\nstatus: initialized\n",
                encoding="utf-8")
            derivative = {
                "schema": canonical_copy.DERIVATIVE_SCHEMA,
                "copy_id": canonical["copy_id"],
                "copy_sha256": canonical_copy.digest(canonical),
                "format": content_format,
                "segments": [{"source_segment_id": "s1",
                              "text": f"{content_format} adaptation of shared fact.",
                              "claim_refs": ["C1"]}],
            }
            (child / canonical_copy.DERIVATIVE_FILE).write_text(
                json.dumps(derivative, ensure_ascii=False), encoding="utf-8")
            output = (child / "script" / "master.md" if content_format == "VIDEO"
                      else child / "draft.md")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(derivative["segments"][0]["text"] + "\n",
                              encoding="utf-8")
            topic_package.bind_child(package, child, content_format,
                                     projects_root=projects_root)
            copy_review.decide(child, status_value="APPROVED", reviewer="Founder",
                               opinion=f"Reviewed {content_format} adaptation",
                               reviewed_at="2026-11-19T00:00:00Z")
            children[content_format] = child

        states = [topic_package.status_child(child, projects_root=projects_root)
                  for child in children.values()]
        assert all(state["ok"] for state in states), states
        assert states[0]["package_sha256"] == states[1]["package_sha256"]
        assert all(copy_review.status(child, projects_root=projects_root)["state"] == "APPROVED"
                   for child in children.values())
        scripts_path = ROOT / "scripts"
        sys.path.insert(0, str(scripts_path))
        try:
            import production_gates
            import m5_production
            from contentops.graphic import package as graphic_package
            for content_format, child in children.items():
                gate = production_gates._canonical_copy_state(
                    child, content_format, projects_root=projects_root)
                assert gate["applicable"] and gate["ok"], gate
                if content_format == "VIDEO":
                    m5_production._require_shared_topic_copy(
                        child, projects_root=projects_root)
                else:
                    with mock.patch.object(graphic_package, "verify_bundle_unchanged"):
                        graphic_package.verify_package_current(
                            {"schema": graphic_package.PACKAGE_SCHEMA,
                             "draft": {"path": "draft.md", "scope": "project",
                                       "sha256": _sha((child / "draft.md").read_bytes())},
                             "images": []}, child, ROOT)
        finally:
            sys.path.remove(str(scripts_path))

        video_ref = children["VIDEO"] / topic_package.REFERENCE
        saved_ref = json.loads(video_ref.read_text(encoding="utf-8"))
        forged_ref = {**saved_ref, "package_slug": "../outside"}
        video_ref.write_text(json.dumps(forged_ref), encoding="utf-8")
        path_block = topic_package.status_child(children["VIDEO"],
                                                projects_root=projects_root)
        assert not path_block["ok"] and path_block["state"] == "TOPIC_PACKAGE_PATH_INVALID"
        video_ref.write_text(json.dumps(saved_ref), encoding="utf-8")
        video_ref.unlink()
        missing_block = topic_package.status_child(children["VIDEO"],
                                                   projects_root=projects_root)
        assert not missing_block["ok"] and missing_block["state"] == "TOPIC_PACKAGE_REFERENCE_MISSING"
        topic_package.bind_child(package, children["VIDEO"], "VIDEO",
                                 projects_root=projects_root)

        canonical["segments"][0]["text"] = "Changed canonical source text."
        (package / canonical_copy.CANONICAL_FILE).write_text(
            json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
        blocked = [topic_package.status_child(child, projects_root=projects_root)
                   for child in children.values()]
        assert all(not state["ok"] for state in blocked), blocked
        assert all(copy_review.status(child, projects_root=projects_root)["state"] != "APPROVED"
                   for child in children.values())
        try:
            m5_production._require_shared_topic_copy(
                children["VIDEO"], projects_root=projects_root)
        except m5_production.M5Blocked as exc:
            assert "TOPIC_PACKAGE_STALE" in str(exc)
        else:
            raise AssertionError("the direct M5 entry must block a changed shared source")
        try:
            with mock.patch.object(graphic_package, "verify_bundle_unchanged"):
                graphic_package.verify_package_current(
                    {"schema": graphic_package.PACKAGE_SCHEMA,
                     "draft": {"path": "draft.md", "scope": "project",
                               "sha256": _sha((children["GRAPHIC_TEXT"] / "draft.md").read_bytes())},
                     "images": []}, children["GRAPHIC_TEXT"], ROOT)
        except graphic_package.GraphicPackageError as exc:
            assert exc.code == "TOPIC_PACKAGE_STALE"
        else:
            raise AssertionError("graphic delivery must block a changed shared source")


def _copy_review_cli():
    path = ROOT / "scripts" / "copy_review.py"
    spec = importlib.util.spec_from_file_location("copy_review_cli", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"could not load CLI from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cli_project(root: Path) -> Path:
    project = root / "projects" / "copy-review-cli-test"
    project.mkdir(parents=True)
    (project / "script").mkdir()
    (project / "script" / "master.md").write_text("# Reviewed copy\n", encoding="utf-8")
    _seed_preresearch(project)
    return project


def test_video_copy_fingerprint_keeps_legacy_graphic_sidecar_bytes_opaque():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        script = project / "script"
        script.mkdir()
        (script / "script.json").write_text("{}", encoding="utf-8")
        (project / "graphic-input.json").write_text("legacy opaque bytes", encoding="utf-8")
        first = copy_review.copy_fingerprint(project)
        (project / "graphic-input.json").write_text("changed opaque bytes", encoding="utf-8")
        assert copy_review.copy_fingerprint(project) != first


def test_graphic_copy_fingerprint_tracks_selected_prose_not_image_plan():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        draft = project / "article.md"
        draft.write_text("# Draft\n\nBody.\n", encoding="utf-8")
        input_path = project / "graphic-input.json"
        input_path.write_text(json.dumps({
            "title": "Title", "draft": "article.md", "platform_id": "wechat_article",
            "account": "thinktank", "images": [{"asset_id": "one", "path": "a.png"}],
        }), encoding="utf-8")

        original = copy_review.copy_fingerprint(project)
        input_path.write_text(json.dumps({
            "title": "Title", "draft": "article.md", "platform_id": "wechat_article",
            "account": "thinktank", "images": [{"asset_id": "two", "path": "b.png"}],
        }), encoding="utf-8")
        assert copy_review.copy_fingerprint(project) == original

        draft.write_text("# Draft\n\nChanged body.\n", encoding="utf-8")
        assert copy_review.copy_fingerprint(project) != original


def test_graphic_review_binds_nondefault_input_and_its_selected_draft():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        draft = project / "alternate.md"
        draft.write_text("# Approved text\n", encoding="utf-8")
        selected_input = project / "alternate-input.json"
        selected_input.write_text(json.dumps({
            "title": "Alternate", "draft": "alternate.md",
            "platform_id": "wechat_article", "account": "thinktank",
            "images": [],
        }), encoding="utf-8")
        copy_review.decide(
            project, status_value="APPROVED", reviewer="Founder",
            opinion="Reviewed the working draft", reviewed_at="2026-11-23T00:00:00Z",
            graphic_input_path=selected_input)

        assert copy_review.status(project, graphic_input_path=selected_input)["ok"]
        assert copy_review.status(project)["state"] == "STALE"
        draft.write_text("# Changed after review\n", encoding="utf-8")
        assert copy_review.status(project, graphic_input_path=selected_input)["state"] == "STALE"


def test_graphic_package_uses_single_copy_review_and_checks_remaining_stages_automatically():
    from contentops.graphic import build_package, verify_graphic_review, write_package

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "article"
        project.mkdir()
        assets = project / "assets"
        assets.mkdir()
        image = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
            "YAAAAAYAAjCB0C8AAAAASUVORK5CYII=")
        (assets / "cover.png").write_bytes(image)
        rights = {
            "schema": "contentops.media-rights-review/v1",
            "license_id": "OWNED-BY-OPERATOR",
            "source_url": "repo://test#cover",
            "reviewed_by": "Founder", "reviewed_at": "2026-11-23",
            "attribution": "", "synthetic": False,
        }
        (assets / "cover.rights.json").write_text(json.dumps(rights), encoding="utf-8")
        (project / "draft.md").write_text("# Reviewed article\n\nBody.\n", encoding="utf-8")
        input_path = project / "graphic-input.json"
        input_path.write_text(json.dumps({
            "title": "Reviewed article", "platform_id": "wechat_article",
            "account": "thinktank", "draft": "draft.md",
            "images": [{
                "asset_id": "cover", "path": "assets/cover.png", "alt": "Cover",
                "rights": {**rights, "schema": "contentops.media-rights/v1",
                           "review_evidence": "assets/cover.rights.json"},
            }],
        }), encoding="utf-8")
        handoff = project / "handoff.json"
        handoff.write_text(json.dumps({
            "schema": "contentops.bundle-handoff/v1", "bundle_id": "CB-20261123-001",
            "bundle_sha256": "a" * 64, "content_format": "GRAPHIC_TEXT",
            "platform": {"platform_id": "wechat_article"}, "blockers": [],
            "publish_authorized": False, "human_review": "NOT_STARTED",
            "production_ready": False,
        }), encoding="utf-8")

        try:
            build_package(project, handoff, input_path, ROOT, ROOT,
                          require_copy_review=True)
        except Exception as exc:
            assert getattr(exc, "code", "") == "FORMAT_COPY_REVIEW_REQUIRED"
        else:
            raise AssertionError("unreviewed graphic draft must not enter production packaging")

        copy_review.decide(
            project, status_value="APPROVED", reviewer="Founder",
            opinion="Reviewed the working draft", reviewed_at="2026-11-23T00:00:00Z")
        package = build_package(project, handoff, input_path, ROOT, ROOT,
                                require_copy_review=True)
        package["blockers"] = []
        paths = write_package(project, package, ROOT)
        workflow = json.loads(paths["workflow"].read_text(encoding="utf-8"))
        assert all(stage["status"] == "checked" for stage in workflow["stages"])
        assert all(stage["approval"] is None for stage in workflow["stages"])
        reviewed = verify_graphic_review(project, package)
        assert reviewed["reviewer"] == "Founder"


def test_graphic_copy_review_cli_accepts_a_bound_nondefault_input():
    cli = _copy_review_cli()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = root / "projects" / "graphic-cli"
        project.mkdir(parents=True)
        (project / "article.md").write_text("# Draft\n", encoding="utf-8")
        selected_input = project / "alternate.json"
        selected_input.write_text(json.dumps({
            "title": "Draft", "draft": "article.md", "platform_id": "wechat_article",
            "account": "thinktank", "images": [],
        }), encoding="utf-8")
        cli.ROOT = root
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cli.main([str(project), "--graphic-input", "alternate.json",
                               "--approve", "--reviewer", "Founder", "--opinion",
                               "Reviewed", "--confirm", "--json"])
        payload = json.loads(out.getvalue())
        assert result == 0
        assert payload["gate"]["ok"] is True
        assert copy_review.load(project)["graphic_input_path"] == "alternate.json"


def test_copy_review_cli_check_is_read_only_and_fails_closed():
    cli = _copy_review_cli()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = _cli_project(root)
        cli.ROOT = root
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cli.main([str(project), "--check", "--json"])
        payload = json.loads(out.getvalue())
        assert result == 1
        assert payload["state"] == "NOT_REVIEWED"
        assert not (project / "receipts" / "script-review.json").exists()


def test_copy_review_cli_requires_explicit_confirmation_for_decisions():
    cli = _copy_review_cli()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = _cli_project(root)
        cli.ROOT = root
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                cli.main([str(project), "--approve", "--reviewer", "Founder",
                          "--opinion", "Reviewed copy"])
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("a decision without --confirm must be refused")
        assert not (project / "receipts" / "script-review.json").exists()


def test_copy_review_cli_records_a_confirmed_approval_bound_to_current_copy():
    cli = _copy_review_cli()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = _cli_project(root)
        cli.ROOT = root
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cli.main([str(project), "--approve", "--reviewer", "Founder",
                               "--opinion", "Reviewed final narration", "--confirm", "--json"])
        payload = json.loads(out.getvalue())
        record = json.loads((project / "receipts" / "script-review.json").read_text(
            encoding="utf-8"))
        assert result == 0
        assert payload["gate"]["state"] == "APPROVED"
        assert record["reviewer"] == "Founder"
        assert record["opinion"] == "Reviewed final narration"
        assert record["copy_sha256"] == copy_review.copy_fingerprint(project)


def test_copy_review_cli_records_changes_requested_without_approving():
    cli = _copy_review_cli()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = _cli_project(root)
        cli.ROOT = root
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = cli.main([str(project), "--request-changes", "--reviewer", "Founder",
                               "--opinion", "Add a source citation", "--confirm", "--json"])
        payload = json.loads(out.getvalue())
        record = json.loads((project / "receipts" / "script-review.json").read_text(
            encoding="utf-8"))
        assert result == 0
        assert record["status"] == "CHANGES_REQUESTED"
        assert payload["gate"]["state"] == "CHANGES_REQUESTED"
        assert payload["gate"]["ok"] is False


def test_copy_review_cli_refuses_projects_outside_the_repository_projects_root():
    cli = _copy_review_cli()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "repo"
        root.mkdir()
        project = Path(temp) / "outside"
        project.mkdir()
        cli.ROOT = root
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            result = cli.main([str(project), "--json"])
        payload = json.loads(out.getvalue())
        assert result == 1
        assert payload["state"] == "BLOCKED"
        assert payload["code"] == "PROJECT_OUTSIDE_REPO"


def test_copy_review_cli_refuses_nested_paths_inside_a_project():
    cli = _copy_review_cli()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / "repo"
        nested = root / "projects" / "group" / "nested"
        nested.mkdir(parents=True)
        cli.ROOT = root
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            result = cli.main([str(nested), "--json"])
        payload = json.loads(out.getvalue())
        assert result == 1
        assert payload["state"] == "BLOCKED"
        assert payload["code"] == "PROJECT_INVALID"


def main() -> int:
    tests = (test_swapping_the_video_invalidates_the_review,
             test_changing_the_caption_invalidates_the_review,
             test_changing_the_claim_binding_invalidates_the_review,
             test_adding_the_machine_verified_claim_ledger_does_not_stale_the_copy,
             test_exact_m5_projection_keeps_review_but_script_drift_stales_it,
             test_m5_projection_accepts_every_derivative_claim_on_one_line,
             test_changing_the_source_invalidates_the_review,
             test_replacing_the_bytes_behind_an_unchanged_path_is_asset_drift,
             test_missing_review_blocks,
             test_a_stale_sha_blocks,
             test_build_metadata_does_not_invalidate_the_review,
             test_declared_assets_are_part_of_the_fingerprint,
             test_editing_the_cut_plan_invalidates_the_review,
             test_editing_the_m5_script_invalidates_the_review,
             test_editing_the_motion_timeline_invalidates_the_review,
             test_editing_the_canonical_topic_copy_invalidates_the_review,
             test_generated_narration_text_does_not_invalidate_the_review,
             test_generated_voice_timings_do_not_invalidate_the_review,
             test_canonical_copy_validates_claim_and_evidence_bindings,
             test_canonical_copy_rejects_claims_without_evidence,
             test_format_derivative_cannot_introduce_unbound_claims,
             test_format_derivative_binds_selected_canonical_source,
             test_reworded_format_derivative_needs_its_own_current_review,
             test_one_topic_package_feeds_video_and_graphic_projects_and_stales_together,
             test_video_copy_fingerprint_keeps_legacy_graphic_sidecar_bytes_opaque,
             test_graphic_copy_fingerprint_tracks_selected_prose_not_image_plan,
             test_graphic_review_binds_nondefault_input_and_its_selected_draft,
             test_graphic_package_uses_single_copy_review_and_checks_remaining_stages_automatically,
             test_graphic_copy_review_cli_accepts_a_bound_nondefault_input,
             test_copy_review_cli_check_is_read_only_and_fails_closed,
             test_copy_review_cli_requires_explicit_confirmation_for_decisions,
             test_copy_review_cli_records_a_confirmed_approval_bound_to_current_copy,
             test_copy_review_cli_records_changes_requested_without_approving,
             test_copy_review_cli_refuses_projects_outside_the_repository_projects_root,
             test_copy_review_cli_refuses_nested_paths_inside_a_project)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} copy-review integrity tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
