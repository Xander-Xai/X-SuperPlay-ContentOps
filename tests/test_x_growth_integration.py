"""End-to-end: growth skill -> account DNA -> enrichment -> gate -> package.

The growth skill and the X Post Gate live on separate branches. This suite
proves they compose without either side being weakened:

- the growth record is still ``PARTIAL_CONTRACT`` when it enters the bridge;
- the bridge cannot invent evidence: every thesis cites an id from the caller's
  own evidence list;
- the review comes from a separate file, never from the draft;
- the real gate still decides READY, and the package still stops at
  ``AWAITING_MANUAL_PUBLISH``.

All data is synthetic. The review fixture is labelled synthetic and is not a
real account approval.
"""

from __future__ import annotations

import json
import struct
import sys
import tempfile
import zlib
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish.x_growth_pipeline import run  # noqa: E402

ACCOUNT_PATH = ROOT / "config" / "accounts" / "x-superplay-english.json"
WEEKLY_FIXTURE = ROOT / "tests" / "fixtures" / "x-organic-weekly.json"
CONTENT_ID = "20261101-900"

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


def _account() -> Dict[str, Any]:
    return json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))


def _png(width: int, height: int) -> bytes:
    row = b"\x00" + b"\x00" * (width * 3)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height))
            + chunk(b"IEND", b""))


def _project(temp: str) -> Path:
    project = Path(temp) / "x-growth-en"
    (project / "assets").mkdir(parents=True)
    (project / "sources").mkdir()
    (project / "assets" / f"{CONTENT_ID}.png").write_bytes(_png(1600, 900))
    (project / "sources" / "review.json").write_text(json.dumps({
        "account_slug": "x-superplay-english",
        "decision": "APPROVED",
        "reviewer": "synthetic-fixture-reviewer",
        "reviewed_at": "2026-11-01",
        "dimensions": {"novelty": 5, "evidence": 5, "mechanism": 5,
                       "audience_decision": 5, "falsifiable": 5, "tension": 5},
        "score": 30,
        "opinion": "synthetic fixture; not a real account approval",
        "synthetic": True,
    }, indent=2), encoding="utf-8")
    return project


def _growth_request() -> Dict[str, Any]:
    return {
        "account_id": "x-superplay-english",
        "language": "en",
        "privacy": "public",
        "fixture": True,
        "operation": "x_contract",
        "draft": {
            "account_id": "x-superplay-english",
            "draft": "A source pointer proves where a claim came from, not that it "
                     "was reproduced. Open the artifact, check the grade, then decide.",
            "source_url": "https://example.org/synthetic-source",
        },
    }


def _enrichment() -> Dict[str, Any]:
    artifact = "https://example.org/synthetic-source"
    return {
        "content_id": CONTENT_ID,
        "mode": "source_analysis",
        "audience_job": "decide whether an evidence pointer is enough to trust a claim",
        "proof_grade": "P0",
        "unique_artifact_ref": artifact,
        "experiment_variable": "evidence pointer placement",
        "label": "SOURCE_ANALYSIS",
        "evidence": [
            {"id": "E1", "artifact_ref": artifact,
             "observation": "the synthetic source is a document, not a run"},
            {"id": "E2", "artifact_ref": artifact,
             "observation": "the score and the grade are recorded separately"},
        ],
        "theses": [
            {"thesis": "A pointer to a source is not a verified result",
             "evidence_id": "E1",
             "counterexample": "a versioned artifact with a run log can be verified",
             "reader_action": "open the pointer before trusting the claim"},
            {"thesis": "A review score is a separate claim from the evidence grade",
             "evidence_id": "E2",
             "counterexample": "a high grade can still carry a weak comparison",
             "reader_action": "read the proof grade before the score"},
            {"thesis": "A manual package is not a publication",
             "evidence_id": "E1",
             "counterexample": "a real status URL recorded by a person is a publication",
             "reader_action": "publish by hand and record the real link"},
        ],
        "red_team": [
            "A source pointer is obvious and needs no post.",
            "The score is arbitrary and should be removed.",
            "This fails when the pointer goes stale.",
        ],
        "image_brief": "dark card, POINTER IS NOT PROOF, two rules",
        "image": {"path": f"assets/{CONTENT_ID}.png"},
        "image_status": "generated",
        "alt_text": "A dark card titled POINTER IS NOT PROOF. Two lines: open the "
                    "artifact, check the grade.",
        "review_source": "sources/review.json",
    }


def _run(project: Path, **overrides) -> Dict[str, Any]:
    enrichment = _enrichment()
    enrichment.update(overrides.pop("enrichment", {}))
    return run(project, overrides.pop("request", _growth_request()), enrichment,
               _account(), **overrides)


@test
def test_a_complete_synthetic_chain_reaches_a_manual_package():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = _run(project)
        assert result["status"] == "AWAITING_MANUAL_PUBLISH", result
        assert result["verdict"] == "READY"
        assert result["external_action"] == "none"
        assert result["execution_authorized"] is False
        assert result["review_provenance"] == "EXTERNAL_REVIEW_FILE_UNVERIFIED"

        record = json.loads((project / result["record_path"]).read_text(encoding="utf-8"))
        assert record["status"] == "draft"
        assert record["status_url"] is None
        assert record["contract_completeness"] == "PARTIAL_CONTRACT"
        assert record["review"]["synthetic"] is True
        assert record["enrichment"]["evidence_ids"] == ["E1", "E2"]

        package = json.loads((project / result["package_path"]).read_text(encoding="utf-8"))
        assert package["status"] == "AWAITING_MANUAL_PUBLISH"
        assert package["status_url"] is None
        assert package["publication_mode"] == "MANUAL_ONLY"
    print("[ok] 1. growth -> enrichment -> gate -> package ends at AWAITING_MANUAL_PUBLISH")


@test
def test_the_growth_request_cannot_name_a_different_account():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        request = _growth_request()
        request["account_id"] = "x-superplay-1024"
        result = _run(project, request=request)
        assert result["status"] == "GROWTH_BLOCKED", result
        assert "project resolves" in " ".join(result["reasons"])
    print("[ok] 2. a growth request for another account is refused")


@test
def test_an_automated_growth_operation_never_enters_the_chain():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        request = _growth_request()
        request["operation"] = "auto_publish"
        result = _run(project, request=request)
        assert result["status"] == "GROWTH_BLOCKED", result
    print("[ok] 3. auto_publish is refused before enrichment")


@test
def test_missing_evidence_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        enrichment = _enrichment()
        enrichment["evidence"] = []
        result = _run(project, enrichment=enrichment)
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("evidence list" in reason for reason in result["reasons"])
    print("[ok] 4. a thesis with no evidence cannot be enriched")


@test
def test_a_thesis_cannot_cite_evidence_that_was_not_supplied():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        enrichment = _enrichment()
        enrichment["theses"][1]["evidence_id"] = "E9"
        result = _run(project, enrichment=enrichment)
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("E9" in reason for reason in result["reasons"])
    print("[ok] 5. a thesis citing an unknown evidence id is refused")


@test
def test_the_review_must_be_a_separate_file():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = _run(project, enrichment={"review_source": ""})
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("review_source" in reason for reason in result["reasons"])
    print("[ok] 6. an inline review cannot stand in for the review file")


@test
def test_a_rejected_review_cannot_reach_the_gate():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        path = project / "sources" / "review.json"
        review = json.loads(path.read_text(encoding="utf-8"))
        review["decision"] = "REJECTED"
        path.write_text(json.dumps(review), encoding="utf-8")
        result = _run(project)
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("only APPROVED" in reason for reason in result["reasons"])
    print("[ok] 7. a rejected review stops the chain")


@test
def test_a_review_scoped_to_another_account_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        path = project / "sources" / "review.json"
        review = json.loads(path.read_text(encoding="utf-8"))
        review["account_slug"] = "x-superplay-1024"
        path.write_text(json.dumps(review), encoding="utf-8")
        result = _run(project)
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("scoped to" in reason for reason in result["reasons"])
    print("[ok] 8. another account's review cannot approve this record")


@test
def test_a_missing_image_or_alt_is_refused_before_packaging():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        (project / "assets" / f"{CONTENT_ID}.png").unlink()
        result = _run(project)
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("not a regular file" in reason for reason in result["reasons"])

    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = _run(project, enrichment={"alt_text": ""})
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("alt_text" in reason for reason in result["reasons"])
    print("[ok] 9. a missing image and missing ALT stop before packaging")


@test
def test_a_path_that_escapes_the_project_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = _run(project, enrichment={"image": {"path": "../outside.png"}})
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("project-relative" in reason for reason in result["reasons"])
    print("[ok] 10. an escaping image path is refused")


@test
def test_the_gate_is_not_weakened_by_this_pipeline():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        enrichment = _enrichment()
        enrichment["theses"] = enrichment["theses"][:2]
        result = _run(project, enrichment=enrichment)
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert not (project / "posts" / f"{CONTENT_ID}.json").exists()
    print("[ok] 11. an incomplete record never reaches the gate or the posts directory")


@test
def test_weekly_metrics_are_attached_or_reported_unavailable():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        weekly = json.loads(WEEKLY_FIXTURE.read_text(encoding="utf-8"))
        result = _run(project, weekly_request=weekly)
        assert result["status"] == "AWAITING_MANUAL_PUBLISH", result
        assert result["metrics"]["status"] in ("INSUFFICIENT_DATA", "REVIEW_REQUIRED")
        assert result["metrics"]["network_used"] is False

    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = _run(project)
        assert result["metrics"]["status"] == "DATA_UNAVAILABLE"
        assert result["metrics"]["external_action"] == "none"
    print("[ok] 12. metrics are attached when supplied, otherwise DATA_UNAVAILABLE")


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
    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} X growth-integration tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
