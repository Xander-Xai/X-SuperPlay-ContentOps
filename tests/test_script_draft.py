"""The script stage: provenance, substance and honest duration.

What these tests pin, one per defect this round fixed:

- a topic the user supplied is never presented as a source's own title;
- a brief with a link but no collected material does **not** become a script —
  it stops at DRAFT_CONTENT_INSUFFICIENT and says what is missing;
- with real material, every spoken fact is bound to a collected, hashed
  document, and the old "transitions only" script is gone;
- a shot lasts as long as its line takes to say, not as long as the account's
  window wants it to;
- one capture per source, because an operator captures a page once;
- drafting writes no copy-review approval.

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
from contentops.script.draft import line_seconds, topic_provenance  # noqa: E402
from contentops.script.evidence import PACK_SCHEMA  # noqa: E402

ACCOUNT_BUILD = "x-superplay-future-intelligence"
ACCOUNT_EXPLORE = "x-superplay-1024"
FIXTURES = ROOT / "tests" / "fixtures" / "hotspots" / "sample-pool.json"
TOPIC = "LangGraph 的状态管理怎么设计"


class _Adapters(dict):
    def __init__(self, adapter):
        super().__init__()
        self._default = adapter

    def get(self, key, default=None):
        return self._default


class _Quality:
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


def _router(root: Path) -> ContentRouter:
    return ContentRouter(root, store=RouterStore(root, home=root / "state"),
                         adapters=_Adapters(FixtureAdapter(
                             json.loads(FIXTURES.read_text(encoding="utf-8")))),
                         quality_fetcher=_Quality())


def _approved_topic(root: Path, slug: str = "script-topic") -> Path:
    router = _router(root)
    run = router.start(ACCOUNT_BUILD, "USER_TOPIC",
                       UserTopicInput(topic=TOPIC,
                                      urls=["https://github.com/langchain-ai/langgraph"]))
    router.approve(ACCOUNT_BUILD, run.run_id, reviewer="Founder", confirmed=True,
                   project_slug=slug)
    return root / "projects" / slug


def _pack(project: Path, items: int = 4, chars: int = 180,
          same_url: bool = False) -> Path:
    """A real-shaped pack: documents on disk, digests that match."""
    documents = project / "script" / "evidence"
    documents.mkdir(parents=True, exist_ok=True)
    entries = []
    for index in range(1, items + 1):
        sentence = ("LangGraph 用 checkpointer 保存每一步的图状态，因此一次长任务可以从"
                    "中断处继续，而不是从头再来。") * (1 + chars // 60)
        sentence = sentence[:chars]
        payload = (f"source: https://docs.example.test/page-{index}\n"
                   f"note: the page's own text as fetched\n\n{sentence}\n").encode("utf-8")
        path = documents / f"EV-{index:02d}.txt"
        path.write_bytes(payload)
        entries.append({
            "evidence_id": f"EV-{index:02d}", "kind": "documentation",
            "title": f"docs page {index}",
            "url": ("https://docs.example.test/page-1" if same_url
                    else f"https://docs.example.test/page-{index}"),
            "excerpt": sentence,
            "document": f"script/evidence/EV-{index:02d}.txt",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "retrieved_at": "2026-10-30T00:00:00Z",
        })
    pack = {"schema": PACK_SCHEMA, "topic": TOPIC, "items": entries}
    path = project / "00_brief" / "evidence-pack.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_a_user_topic_is_never_a_sources_title():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        brief = json.loads((project / "00_brief" / "brief.json").read_text(encoding="utf-8"))
        assert topic_provenance(brief) == "user_supplied_topic"
        _pack(project)
        draft = build(project, root=root)
        provenances = {claim["provenance"] for claim in draft.report["claims"]}
        assert "source_original_title" not in provenances
        opening = draft.master.split("## P-01")[1].split("## P-02")[0]
        assert "你提的问题" in opening
        assert "原标题" not in opening


def test_a_link_without_material_does_not_become_a_script():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        try:
            build(project, root=root)
        except ScriptBlocked as exc:
            assert exc.code == "DRAFT_CONTENT_INSUFFICIENT"
            assert "证据包" in exc.detail
        else:
            raise AssertionError("a brief with no collected material must not draft")


def test_a_thin_pack_is_refused_with_the_gap_named():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project, items=2, chars=60)
        try:
            build(project, root=root)
        except ScriptBlocked as exc:
            assert exc.code == "DRAFT_CONTENT_INSUFFICIENT"
            assert "可引用材料" in exc.detail
        else:
            raise AssertionError("two short items are not an episode")


def test_real_material_becomes_substantive_spoken_lines():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project)
        draft = build(project, root=root)
        spoken = [beat["text"] for beat in draft.lines["beats"]]
        assert len(spoken) >= 6
        factual = [claim for claim in draft.report["claims"] if claim["kind"] == "source"]
        assert len(factual) >= 4
        for claim in factual:
            assert claim["support_status"] == "SUPPORTED"
            assert claim["source_refs"][0].startswith("https://")
        assert any("checkpointer" in line for line in spoken)


def test_every_fact_is_bound_to_a_document_that_matches_its_digest():
    from contentops.evidence.claim_map import ClaimMap
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project)
        write(build(project, root=root))
        document = json.loads((project / "script" / "claim-map.json")
                              .read_text(encoding="utf-8"))
        claim_map = ClaimMap.from_dict(document).validate()
        for claim in claim_map.claims:
            for item in claim.evidence:
                relative = item["logical_path"].replace("project://", "")
                path = project / relative
                assert path.is_file(), relative
                assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_a_changed_evidence_file_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project)
        document = project / "script" / "evidence" / "EV-01.txt"
        document.write_bytes(document.read_bytes() + b"tampered")
        try:
            build(project, root=root)
        except ScriptBlocked as exc:
            assert exc.code == "EVIDENCE_PACK_INVALID"
            assert "摘要" in exc.detail
        else:
            raise AssertionError("a doctored document must not be quoted")


def test_duration_comes_from_the_words_not_from_the_window():
    assert line_seconds("") == 0.0
    short = line_seconds("很短的一句。")
    long = line_seconds("这一句明显更长，因为它在解释一张图里每一层分别在做什么事情。")
    assert short < long
    assert 0.5 < short < 3.0
    assert long > short

    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project)
        draft = build(project, root=root)
        total = 0.0
        for shot in draft.storyboard["shots"]:
            spoken = line_seconds(shot["narration"])
            assert shot["duration"] >= spoken - 0.001, shot["shot_id"]
            total += shot["duration"]
        assert abs(total - draft.report["storyboard"]["duration_s"]) < 0.2


def test_too_little_material_for_the_window_is_refused_not_stretched():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project, items=3, chars=150)
        try:
            build(project, root=root)
        except ScriptBlocked as exc:
            assert exc.code == "DRAFT_CONTENT_INSUFFICIENT"
            assert "窗口" in exc.detail
        else:
            raise AssertionError("a short script must not be stretched to fit")


def test_one_capture_per_source_not_one_per_sentence():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project, items=3, chars=600, same_url=True)
        draft = build(project, root=root)
        captures = [shot for shot in draft.storyboard["shots"] if shot["needs_capture"]]
        assert len(captures) == 1
        assert captures[0]["capture_task"]


def test_a_source_title_claim_in_a_user_topic_run_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project)
        write(build(project, root=root))
        report_path = project / "00_brief" / "script-report.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["claims"][0]["provenance"] = "source_original_title"
        report_path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        verdict = check(project)
        assert verdict["ok"] is False
        assert any("USER_TOPIC" in failure for failure in verdict["failures"])


def test_editing_the_script_invalidates_the_copy_fingerprint():
    """A review is bound to what the copy says; changing it makes the review stale."""
    from contentops.workflow import copy_review
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project)
        write(build(project, root=root))
        before = copy_review.copy_fingerprint(project)
        master = project / "script" / "master.md"
        master.write_text(master.read_text(encoding="utf-8") + "\n改一个字\n",
                          encoding="utf-8")
        after = copy_review.copy_fingerprint(project)
        assert before != after


def test_the_draft_leaves_the_copy_unreviewed():
    with tempfile.TemporaryDirectory() as tmp:
        root = _sandbox(tmp)
        project = _approved_topic(root)
        _pack(project)
        write(build(project, root=root))
        verdict = check(project)
        assert verdict["ok"] is True, verdict["failures"]
        assert verdict["copy_review"]["state"] == "NOT_REVIEWED"
        assert not (project / "receipts" / "script-review.json").exists()


def test_the_pack_fetcher_reads_prose_and_skips_scripts():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "evidence_pack_script", ROOT / "scripts" / "evidence_pack.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    markup = ("<html><head><title>Persistence</title><style>.x{color:red}</style></head>"
              "<body><script>var leak = 1;</script><h1>Persistence</h1>"
              "<p>Checkpointers save graph state.</p></body></html>")
    text = module._text_of(markup)
    assert "Checkpointers save graph state." in text
    assert "var leak" not in text
    assert "color:red" not in text
    assert module._title_of(markup) == "Persistence"


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
