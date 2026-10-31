"""Positive and negative acceptance for the real X Post Gate.

The other suites mostly prove refusals. This one builds a synthetic record that
is complete on purpose -- evidence pointer, three theses, recovery fields, one
real 1600x900 PNG, ALT text and a *test* review -- and asserts the gate returns
an editorial package a person could publish by hand.

The review here is synthetic (``reviewer: "synthetic-fixture-reviewer"``). It is
not a real account approval and the suite never claims one.
"""

from __future__ import annotations

import copy
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish import (  # noqa: E402
    AWAITING,
    PackageBlocked,
    PublishMode,
    PublisherUnavailable,
    build_package,
    post_verdict,
    publish,
    valid_status_url,
    validate_post,
)

ACCOUNT_PATH = ROOT / "config" / "accounts" / "x-superplay-english.json"
CONTENT_ID = "20261101-001"
SYNTHETIC_REVIEWER = "synthetic-fixture-reviewer"

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


def _project(temp: str, image: bool = True) -> Path:
    project = Path(temp) / "x-growth-en"
    (project / "assets").mkdir(parents=True)
    (project / "posts").mkdir()
    if image:
        (project / "assets" / f"{CONTENT_ID}.png").write_bytes(_png(1600, 900))
    return project


def _record() -> Dict[str, Any]:
    return {
        "schema": "contentops.x-post/v1",
        "content_id": CONTENT_ID,
        "account_slug": "x-superplay-english",
        "mode": "source_analysis",
        "topic": "a synthetic acceptance topic",
        "sources": ["https://example.org/synthetic-source"],
        "audience_job": "decide whether an evidence pointer is enough to trust a claim",
        "proof_grade": "P0",
        "unique_artifact_ref": "https://example.org/synthetic-source",
        "experiment_variable": "evidence pointer placement",
        "label": "SOURCE_ANALYSIS",
        "theses": [
            {"thesis": "A pointer to a source is not the same as a verified result",
             "evidence": "the synthetic source is a document, not a run",
             "counterexample": "a repository-relative artifact with an exact version can be verified",
             "reader_action": "open the pointer before trusting the claim"},
            {"thesis": "A review score is a separate claim from the evidence grade",
             "evidence": "the fixture scores novelty and evidence independently",
             "counterexample": "a high evidence grade can still carry a weak comparison",
             "reader_action": "read the proof grade before the score"},
            {"thesis": "A manual package is not a publication",
             "evidence": "the package status remains AWAITING_MANUAL_PUBLISH",
             "counterexample": "a real status URL recorded by a person is a publication",
             "reader_action": "publish by hand and record the real link"},
        ],
        "red_team": [
            "A source pointer is obvious and needs no post.",
            "The score is arbitrary and should be removed.",
            "This fails when the pointer goes stale.",
        ],
        "post_copy": {"parts": [
            "A source pointer proves where a claim came from, not that its result "
            "was reproduced.\n\nOpen the artifact, check the grade, then decide.\n\n"
            "Artifact: https://example.org/synthetic-source",
        ]},
        "image_brief": "dark card, POINTER IS NOT PROOF, two rules",
        "image": {"path": f"assets/{CONTENT_ID}.png"},
        "image_status": "generated",
        "alt_text": "A dark card titled POINTER IS NOT PROOF. Two lines: open the "
                    "artifact, check the grade.",
        "review": {
            "reviewer": SYNTHETIC_REVIEWER,
            "reviewed_at": "2026-11-01",
            "dimensions": {"novelty": 4, "evidence": 4, "mechanism": 5,
                           "audience_decision": 5, "falsifiable": 4, "tension": 4},
            "score": 26,
            "opinion": "synthetic fixture review; not a real account approval",
        },
        "status": "draft",
        "status_url": None,
        "metrics": None,
        "notes": "synthetic acceptance fixture",
    }


def _codes(record: Dict[str, Any], project: Path) -> set:
    return {issue.code for issue in validate_post(record, _account(), root=project)}


@test
def test_a_complete_synthetic_record_is_ready():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = _record()
        assert validate_post(record, _account(), root=project) == []
        assert post_verdict(record, _account(), root=project) == "READY"
    print("[ok] 1. a complete synthetic record passes every gate")


@test
def test_a_ready_record_builds_a_manual_publish_package():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        package = build_package(_record(), _account(), project)
        assert package["status"] == AWAITING
        assert package["publication_mode"] == PublishMode.MANUAL_ONLY.value
        assert package["status_url"] is None
        assert package["copy"]["parts"][0]["text"].startswith("A source pointer")
        assert package["alt_text"].startswith("A dark card titled POINTER IS NOT PROOF")
        assert package["image"]["sha256"], package["image"]
        assert package["image"]["width"] == 1600 and package["image"]["height"] == 900
        assert package["review"]["reviewer"] == SYNTHETIC_REVIEWER
        assert package["manual_steps"], package["manual_steps"]
        receipt = json.loads((project / package["receipt"]).read_text(encoding="utf-8"))
        assert receipt["status"] == AWAITING
        assert receipt["status_url"] is None
    print("[ok] 2. READY produces AWAITING_MANUAL_PUBLISH, never PUBLISHED")


@test
def test_api_publication_still_raises():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        try:
            publish(_record(), _account(), project, mode=PublishMode.API)
        except PublisherUnavailable:
            pass
        else:
            raise AssertionError("API publication was not refused")
    print("[ok] 3. the API seam still raises; MANUAL_ONLY is the only mode")


@test
def test_missing_evidence_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = copy.deepcopy(_record())
        record["unique_artifact_ref"] = ""
        codes = _codes(record, project)
        assert "RECOVERY_FIELD_MISSING" in codes, codes
        assert post_verdict(record, _account(), root=project) == "BLOCKED"
    print("[ok] 4. a record with no evidence pointer is refused")


@test
def test_missing_image_and_alt_are_refused_separately():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        no_image = copy.deepcopy(_record())
        no_image["image"] = {}
        codes = _codes(no_image, project)
        assert "IMAGE_ABSENT" in codes, codes

        no_alt = copy.deepcopy(_record())
        no_alt["alt_text"] = ""
        codes = _codes(no_alt, project)
        assert "ALT_MISSING" in codes, codes
    print("[ok] 5. a missing image and missing ALT are named refusals")


@test
def test_missing_human_review_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = copy.deepcopy(_record())
        record["review"] = None
        codes = _codes(record, project)
        assert "REVIEW_MISSING" in codes, codes
        assert post_verdict(record, _account(), root=project) != "READY"
        try:
            build_package(record, _account(), project)
        except PackageBlocked:
            pass
        else:
            raise AssertionError("an unreviewed record was packaged")
    print("[ok] 6. a record with no human review is refused")


@test
def test_a_review_status_string_cannot_replace_a_review():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = copy.deepcopy(_record())
        record["review"] = None
        record["review_status"] = "APPROVED"
        codes = _codes(record, project)
        assert "REVIEW_MISSING" in codes, codes
        assert post_verdict(record, _account(), root=project) != "READY"
        try:
            build_package(record, _account(), project)
        except PackageBlocked:
            pass
        else:
            raise AssertionError("review_status bypassed the review gate")
    print("[ok] 7. review_status='APPROVED' does not stand in for a review")


@test
def test_a_ready_flag_cannot_bypass_the_gate():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = copy.deepcopy(_record())
        record["review"] = None
        record["ready_for_publish"] = True
        codes = _codes(record, project)
        assert "REVIEW_MISSING" in codes, codes
        assert post_verdict(record, _account(), root=project) != "READY"
        try:
            build_package(record, _account(), project)
        except PackageBlocked:
            pass
        else:
            raise AssertionError("ready_for_publish bypassed the review gate")
    print("[ok] 8. ready_for_publish=true does not bypass the gate")


@test
def test_url_syntax_is_not_a_publication_proof():
    url = "https://x.com/someone/status/123456789"
    assert valid_status_url(url), "the fixture URL is syntactically valid"
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = copy.deepcopy(_record())
        record["status_url"] = url
        assert post_verdict(record, _account(), root=project) == "READY"
        package = build_package(record, _account(), project)
        assert package["status"] == AWAITING
        assert package["verdict"] == "READY"
    print("[ok] 9. a plausible URL alone does not make the post published")


@test
def test_another_accounts_record_cannot_borrow_this_gate():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = copy.deepcopy(_record())
        record["account_slug"] = "x-superplay-1024"
        codes = _codes(record, project)
        assert "ACCOUNT_MISMATCH" in codes, codes
        assert post_verdict(record, _account(), root=project) == "BLOCKED"
    print("[ok] 10. a record for another account is refused")


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
    print(f"All {len(TESTS)} positive X acceptance tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
