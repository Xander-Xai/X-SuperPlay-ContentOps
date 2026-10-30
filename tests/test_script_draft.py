"""The script stage: an approved brief becomes copy, and nothing is invented.

What these tests pin:

- a draft is built only from an approved, unchanged brief;
- a degraded evidence forecast stops the stage at EVIDENCE_REQUIRED;
- every spoken line is a SUPPORTED claim or a transition, because the claim
  contract does not allow anything else on narration;
- the one factual line quotes the source's own title and binds a document whose
  digest matches the file on disk;
- a paraphrase of a claim is caught, because a different wording is a
  different claim;
- drafting never writes a copy-review approval.

Run: python tests/test_script_draft.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.hotspots.adapters import FixtureAdapter  # noqa: E402
from contentops.hotspots.storage import RouterStore  # noqa: E402
from contentops.routing.router import ContentRouter  # noqa: E402
from contentops.routing.user_topic_route import UserTopicInput  # noqa: E402
from contentops.script import ScriptBlocked, build, check, write  # noqa: E402

ACCOUNT_BUILD = "x-superplay-future-intelligence"
ACCOUNT_EXPLORE = "x-superplay-1024"
FIXTURES = ROOT / "tests" / "fixtures" / "hotspots" / "sample-pool.json"


class _Adapters(dict):
    """A source-id map whose misses fall back to one adapter."""

    def __init__(self, adapter):
        super().__init__()
        self._default = adapter

    def get(self, key, default=None):
        return self._default


class _Quality:
    """Evidence that never touches the network."""

    def fetch(self, full_name):
        from contentops.hotspots.quality import RepoEvidence
        return RepoEvidence(full_name=full_name, description="a real project",
                            size_kb=2048, stars=100, has_readme=True,
                            created_at="2025-01-01T00:00:00Z", fetched=True)


def _sandbox(tmp: str) -> Path:
    root = Path(tmp) / "repo"
    accounts = root / "config" / "accounts"
    accounts.mkdir(parents=True)
    for slug in (ACCOUNT_EXPLORE, ACCOUNT_BUILD):
        shutil.copy(ROOT / "config" / "accounts" / f"{slug}.json",
                    accounts / f"{slug}.json")
    return root


def _fixture_adapter() -> FixtureAdapter:
    return FixtureAdapter(json.loads(FIXTURES.read_text(encoding="utf-8")))


def _router(root: Path) -> ContentRouter:
    return ContentRouter(root, store=RouterStore(root, home=root / "state"),
                         adapters=_Adapters(_fixture_adapter()),
                         quality_fetcher=_Quality())


def _approved_topic(root: Path) -> tuple[ContentRouter, str, Path]:
    router = _router(root)
    run = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                       UserTopicInput(topic="LangGraph 的状态管理怎么设计",
                                      urls=["https://github.com/langchain-ai/langgraph"]))
    router.approve(ACCOUNT_BUILD, run.run_id, reviewer="Founder", confirmed=True,
                   project_slug="script-topic")
    return router, run.run_id, root / "projects" / "script-topic"


def test_an_approved_brief_becomes_a_draft():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, _, project = _approved_topic(root)
        draft = build(project, root=root)
        assert draft.lines["schema"] == "contentops.audio-first-lines/v1"
        assert draft.claim_map["schema"] == "contentops.claim-map/v1"
        assert len(draft.lines["beats"]) == 5
        assert draft.storyboard["shots"]
        assert draft.master.startswith("# ")
        assert draft.evidence_files


def test_every_spoken_line_is_supported():
    """The claim contract only lets SUPPORTED claims be narrated."""
    from contentops.evidence.claim_map import ClaimMap
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, _, project = _approved_topic(root)
        draft = build(project, root=root)
        claim_map = ClaimMap.from_dict(draft.claim_map).validate()
        spoken = {beat["claim_id"] for beat in draft.lines["beats"]}
        for claim in claim_map.claims:
            if claim.claim_id in spoken:
                assert claim.support_status == "SUPPORTED", claim.claim_id


def test_the_fact_line_quotes_the_source_and_binds_its_document():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, _, project = _approved_topic(root)
        draft = build(project, root=root)
        source_claim = next(claim for claim in draft.claim_map["claims"]
                            if claim["kind"] == "source")
        assert "原标题是" in source_claim["text"]
        evidence = source_claim["evidence"][0]
        content = draft.evidence_files["C-02-source.txt"]
        assert hashlib.sha256(content).hexdigest() == evidence["sha256"]
        assert evidence["logical_path"].startswith("project://script/evidence/")
        assert b"not a run, a test or an independent verification" in content


def test_a_degraded_forecast_stops_at_evidence_required():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root)
        run = router.start(ACCOUNT_EXPLORE, "HOTSPOT_DISCOVERY")
        candidate = run.detail["candidates"][0]["candidate_id"]
        router.select(ACCOUNT_EXPLORE, run.run_id, candidate, selected_by="Founder")
        router.approve(ACCOUNT_EXPLORE, run.run_id, reviewer="Founder",
                       confirmed=True, project_slug="script-hotspot")
        project = root / "projects" / "script-hotspot"
        package = json.loads((project / "00_brief" / "brief.json")
                             .read_text(encoding="utf-8"))
        if package.get("forecast_verdict") != "DEGRADED":
            raise AssertionError("fixture expected a DEGRADED forecast")
        try:
            build(project, root=root)
        except ScriptBlocked as exc:
            assert exc.code == "EVIDENCE_REQUIRED"
        else:
            raise AssertionError("a degraded forecast must not become a script")


def test_an_unapproved_brief_cannot_become_a_script():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        router = _router(root)
        run = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                           UserTopicInput(topic="Agent 的记忆机制怎么设计"))
        router.approve(ACCOUNT_BUILD, run.run_id, reviewer="Founder", confirmed=True,
                       project_slug="script-unapproved")
        project = root / "projects" / "script-unapproved"
        package = json.loads((project / "00_brief" / "brief.json")
                             .read_text(encoding="utf-8"))
        package["intent"]["topic"] = "被改过的主题"
        (project / "00_brief" / "brief.json").write_text(
            json.dumps(package, ensure_ascii=False), encoding="utf-8")
        try:
            build(project, root=root)
        except ScriptBlocked as exc:
            assert exc.code == "APPROVAL_STALE"
        else:
            raise AssertionError("a changed brief must not become a script")


def test_the_written_draft_passes_its_own_check_and_leaves_copy_unreviewed():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, _, project = _approved_topic(root)
        draft = build(project, root=root)
        written = write(draft)
        assert (project / "script" / "lines.json").is_file()
        assert (project / "script" / "claim-map.json").is_file()
        assert (project / "script" / "storyboard.json").is_file()
        assert (project / "script" / "master.md").is_file()
        assert (project / "00_brief" / "script-report.json").is_file()
        assert any(key.startswith("evidence/") for key in written)
        verdict = check(project)
        assert verdict["ok"] is True, verdict["failures"]
        assert verdict["copy_review"]["state"] == "NOT_REVIEWED"
        assert verdict["copy_review"]["ok"] is False


def test_a_paraphrased_narration_is_caught():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, _, project = _approved_topic(root)
        write(build(project, root=root))
        lines_path = project / "script" / "lines.json"
        document = json.loads(lines_path.read_text(encoding="utf-8"))
        document["beats"][1]["text"] = "换个说法就行了吧"
        lines_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        verdict = check(project)
        assert verdict["ok"] is False
        assert any("not the text of its claim" in failure
                   for failure in verdict["failures"])


def test_the_storyboard_carries_what_a_capture_step_needs():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, _, project = _approved_topic(root)
        draft = build(project, root=root)
        for shot in draft.storyboard["shots"]:
            for key in ("shot_id", "duration", "narration", "source_type",
                        "function", "dna_role", "needs_capture", "claim_id"):
                assert key in shot, key
            assert shot["duration"] > 0


def test_the_source_shot_is_the_source_and_needs_a_capture():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        _, _, project = _approved_topic(root)
        draft = build(project, root=root)
        source_shot = next(shot for shot in draft.storyboard["shots"]
                           if shot["claim_id"] == "C-02")
        assert source_shot["source_type"] in ("code_snapshot",
                                              "screen_recording_evidence",
                                              "ui_screenshot", "terminal_capture")
        assert source_shot["needs_capture"] is True
        assert source_shot["evidence_source"].startswith("https://")


def test_the_two_accounts_get_different_visual_plans():
    from contentops.routing.account_profile import load_profile
    explore = load_profile(ROOT, ACCOUNT_EXPLORE)
    build_profile = load_profile(ROOT, ACCOUNT_BUILD)
    assert explore.evidence_mode != build_profile.evidence_mode
    explore_roles = {(explore.dna.get("visual") or {}).get("composition", {})
                     .get("segments", [{}])[0].get("role")}
    build_roles = {(build_profile.dna.get("visual") or {}).get("composition", {})
                   .get("segments", [{}])[0].get("role")}
    assert explore_roles != build_roles


def main() -> int:
    tests = tuple(value for name, value in sorted(globals().items())
                  if name.startswith("test_") and callable(value))
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} script draft tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
