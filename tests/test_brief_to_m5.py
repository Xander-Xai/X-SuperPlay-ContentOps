"""The brief bridge: an approved draft only becomes M5 input when it can be checked.

The tests pin four refusals that matter:

1. an unapproved brief never becomes a script;
2. an unreviewed copy never becomes a script;
3. a factual line with no evidence is not silently given a claim id;
4. a quote that is not in the saved document is not a quote.

One happy path proves the conversion: the line keeps its narration, the claim
keeps its artifact and quote, and the source ref is repository-relative.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.routing.brief import BRIEF_DIR, BRIEF_FILE, content_digest  # noqa: E402
from contentops.script.m5_bridge import (  # noqa: E402
    ASSET_MAP_FILE,
    PERMISSIONS_FILE,
    BridgeBlocked,
    build,
    check,
    write,
)
from contentops.workflow import copy_review  # noqa: E402

TESTS = []
QUOTE = "Checkpointers save graph state between steps."
BEAT_TEXT = QUOTE


def test(fn):
    TESTS.append(fn)
    return fn


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, document) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(document, str):
        path.write_text(document, encoding="utf-8")
    else:
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def _forecast() -> dict:
    return {
        "schema": "contentops.evidence-feasibility/v1",
        "topic_id": "T-1",
        "assessment_basis": "the official persistence document is public and saved",
        "evidence": [{
            "kind": "real_document", "required": True, "owner": "human",
            "available": True,
        }],
        "failure_plan": "stop",
    }


def _package(approved: bool = True) -> dict:
    package = {
        "schema": "contentops.brief/v1",
        "intent": {
            "topic": "LangGraph 持久化",
            "route_mode": "USER_TOPIC",
            "account_id": "x-superplay-1024",
            "account_profile_version": "test",
            "approval_status": "approved" if approved else "pending",
            "route_context": {"detail": {}},
        },
        "candidate": {"candidate_id": "CAND-1", "title": "Persistence"},
        "forecast": _forecast(),
        "forecast_verdict": "FEASIBLE",
    }
    if approved:
        package["intent"]["route_context"]["detail"]["approval"] = {
            "content_digest": content_digest(package),
            "actor_kind": "person",
            "actor": "Founder",
            "approved_at": "2026-11-04T00:00:00Z",
        }
    return package


def _project(temp: str, *, approved: bool = True, reviewed: bool = True) -> tuple:
    root = Path(temp) / "repo"
    project = root / "projects" / "e2e"
    doc = project / "evidence" / "persistence.md"
    _write(doc, "# Persistence\n\n" + QUOTE + "\n")
    visual = project / "assets" / "support.png"
    _write(visual, "png-bytes")
    _write(project / BRIEF_DIR / BRIEF_FILE, _package(approved))
    _write(project / "script" / "lines.json", {
        "schema": "contentops.audio-first-lines/v1",
        "beats": [
            {"placement_id": "P-01", "claim_id": "C-01", "text": BEAT_TEXT},
            {"placement_id": "P-02", "claim_id": "C-02",
             "text": "以上内容都能在文末的来源里逐条核对。"},
        ],
    })
    _write(project / "script" / "claim-map.json", {
        "schema": "contentops.claim-map/v1",
        "claims": [
            {"claim_id": "C-01", "text": BEAT_TEXT, "kind": "source",
             "support_status": "SUPPORTED",
             "evidence": [{"evidence_id": "E-01", "kind": "document",
                           "sha256": _sha(doc.read_bytes()),
                           "logical_path": "project://evidence/persistence.md",
                           "permission_scope": "publishable"}]},
            {"claim_id": "C-02", "text": "以上内容都能在文末的来源里逐条核对。",
             "kind": "cta", "support_status": "SUPPORTED", "evidence": []},
        ],
    })
    _write(project / "script" / "storyboard.json", {
        "schema": "contentops.storyboard/v1",
        "size": {"width": 1080, "height": 1920},
        "shots": [
            {"shot_id": "S-01", "placement": "P-01", "narration": BEAT_TEXT},
            {"shot_id": "S-02", "placement": "P-02",
             "narration": "以上内容都能在文末的来源里逐条核对。"},
        ],
    })
    _write(project / PERMISSIONS_FILE, {
        "schema": "contentops.source-permissions/v1",
        "permissions": {"E-01": {"permission": "LICENSED",
                                 "title": "LangGraph persistence",
                                 "note": "official documentation, cited"}},
    })
    _write(project / "sources" / "assets.json", {
        "schema": "contentops.m5-assets/v1",
        "assets": [{"id": "support-01", "repo_path": "projects/e2e/assets/support.png",
                    "sha256": _sha(visual.read_bytes()), "permission": "CREATED_BY_OWNER"}],
    })
    _write(project / ASSET_MAP_FILE, {
        "schema": "contentops.asset-map/v1",
        "mapping": {"P-01": "support-01", "P-02": "support-01"},
    })
    if reviewed:
        fingerprint = copy_review.copy_fingerprint(project)
        _write(project / "receipts" / "script-review.json", {
            "schema": "contentops.copy-review/v1",
            "status": "APPROVED",
            "copy_sha256": fingerprint,
            "reviewer": "Founder",
            "opinion": "ok",
            "reviewed_at": "2026-11-04T00:00:00Z",
        })
    return root, project


def _blocked(project: Path, root: Path, code: str) -> BridgeBlocked:
    try:
        build(project, repo_root=root)
    except BridgeBlocked as blocked:
        assert blocked.code == code, f"expected {code}, got {blocked.code}: {blocked.detail}"
        return blocked
    raise AssertionError(f"expected BridgeBlocked({code})")


@test
def test_an_approved_reviewed_draft_converts_to_the_m5_contract():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp)
        result = build(project, repo_root=root)
        lines = result["script"]["lines"]
        assert [line["id"] for line in lines] == ["P-01", "P-02"]
        assert lines[0]["claim"] == "C-01"
        assert lines[1]["claim"] is None, "a CTA must not carry a claim id"
        assert lines[0]["asset_id"] == "support-01"
        claims = result["claims"]["claims"]
        assert len(claims) == 1, claims
        assert claims[0]["quotes"] == [BEAT_TEXT]
        assert claims[0]["artifacts"] == ["E-01"]
        refs = result["source_refs"]["refs"]
        assert refs[0]["path"] == "projects/e2e/evidence/persistence.md", refs
        assert refs[0]["permission"] == "LICENSED"
        written = write(result, project)
        assert set(written) == {"script/script.json", "script/claims.json",
                                "sources/source-refs.json", "receipts/brief-to-m5.json"}
        assert check(project, repo_root=root)["ok"]
        print("[ok] an approved, reviewed draft becomes M5 input")


@test
def test_an_unapproved_brief_is_refused_before_anything_is_written():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp, approved=False)
        _blocked(project, root, "NOT_APPROVED")
        assert not (project / "script" / "script.json").exists()
        print("[ok] an unapproved brief is refused")


@test
def test_unapproved_preview_conversion_is_explicit_and_does_not_claim_approval():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp, approved=False, reviewed=False)
        result = build(project, repo_root=root, allow_unapproved_preview=True)
        assert result["preview_only"] is True
        receipt_path = write(result, project)["receipts/brief-to-m5.json"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        assert receipt["preview_only"] is True
        assert "unapproved" in receipt["note"]
        try:
            copy_review.require_if_brief_driven(project)
        except copy_review.CopyReviewRequired as blocked:
            assert "NOT_REVIEWED" in str(blocked), blocked
        else:
            raise AssertionError("preview conversion must not approve the copy")
        print("[ok] an unapproved brief converts only for local preview")


@test
def test_an_unreviewed_copy_is_refused_at_the_m5_gate():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp, reviewed=False)
        try:
            copy_review.require_if_brief_driven(project)
        except copy_review.CopyReviewRequired as blocked:
            assert "NOT_REVIEWED" in str(blocked), blocked
        else:
            raise AssertionError("an unreviewed router copy reached the gate")
        # Convert first, then review the final copy: that is the pipeline order.
        result = build(project, repo_root=root)
        write(result, project)
        _write(project / "receipts" / "script-review.json", {
            "schema": "contentops.copy-review/v1",
            "status": "APPROVED",
            "copy_sha256": copy_review.copy_fingerprint(project),
            "reviewer": "Founder",
            "opinion": "ok",
            "reviewed_at": "2026-11-04T00:00:00Z",
        })
        assert copy_review.require_if_brief_driven(project)["ok"]
        print("[ok] the copy review gate covers the converted copy")


@test
def test_a_legacy_project_without_a_brief_is_not_gated():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp, reviewed=False)
        (project / "00_brief" / "brief.json").unlink()
        assert copy_review.require_if_brief_driven(project) is None
        print("[ok] a legacy sample is not retroactively blocked")


@test
def test_a_factual_line_with_no_evidence_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp)
        document = json.loads((project / "script" / "claim-map.json").read_text("utf-8"))
        document["claims"][0]["evidence"] = []
        _write(project / "script" / "claim-map.json", document)
        blocked = _blocked(project, root, "BRIDGE_BLOCKED")
        assert any("without SUPPORTED evidence" in item for item in blocked.blockers)
        print("[ok] a spoken fact without evidence is refused")


@test
def test_a_quote_that_is_not_in_the_document_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp)
        document = json.loads((project / "script" / "claim-map.json").read_text("utf-8"))
        document["claims"][0]["text"] = "A sentence the source never wrote."
        _write(project / "script" / "claim-map.json", document)
        blocked = _blocked(project, root, "BRIDGE_BLOCKED")
        assert any("does not occur verbatim" in item for item in blocked.blockers), blocked.blockers
        print("[ok] an unverifiable quote is refused")


@test
def test_a_missing_source_permission_is_named_not_defaulted():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp)
        (project / PERMISSIONS_FILE).unlink()
        _blocked(project, root, "SOURCE_PERMISSIONS_MISSING")
        _write(project / PERMISSIONS_FILE, {"schema": "contentops.source-permissions/v1",
                                            "permissions": {}})
        blocked = _blocked(project, root, "BRIDGE_BLOCKED")
        assert any("source permissions are missing for: E-01" in item
                   for item in blocked.blockers), blocked.blockers
        print("[ok] a missing permission is named, never guessed")


@test
def test_a_placement_with_no_asset_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp)
        _write(project / ASSET_MAP_FILE, {"schema": "contentops.asset-map/v1",
                                          "mapping": {"P-01": "support-01"}})
        blocked = _blocked(project, root, "BRIDGE_BLOCKED")
        assert any("P-02" in item for item in blocked.blockers), blocked.blockers
        print("[ok] a picture nobody registered is a blocker")


@test
def test_an_asset_whose_digest_changed_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp)
        (project / "assets" / "support.png").write_bytes(b"different")
        blocked = _blocked(project, root, "BRIDGE_BLOCKED")
        assert any("sha256 differs" in item for item in blocked.blockers), blocked.blockers
        print("[ok] an asset that changed after registration is refused")


@test
def test_the_conversion_grants_no_approval_and_publishes_nothing():
    with tempfile.TemporaryDirectory() as temp:
        root, project = _project(temp)
        result = build(project, repo_root=root)
        receipt = write(result, project)["receipts/brief-to-m5.json"]
        text = receipt.read_text(encoding="utf-8")
        assert "PENDING_FOUNDER_REVIEW" in text
        assert "publishes nothing" in text
        print("[ok] the bridge records no approval")


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} brief-bridge tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
