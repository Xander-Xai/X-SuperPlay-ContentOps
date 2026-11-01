"""Path safety for the growth integration: ids, reviews, images and sources.

Every value audited here is data a caller supplies. The suite proves three
things for each path:

1. traversal is refused on every spelling, including the Windows backslash form
   that is a plain file name on Linux;
2. a refusal happens before the file is opened, so an outside review is never
   read even when it is valid JSON;
3. a normal record still reaches ``AWAITING_MANUAL_PUBLISH``.

Symlink cases skip explicitly when the host cannot create a link.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts", ROOT / "tests"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish import validate_post  # noqa: E402
from contentops.publish.x_growth_pipeline import _write_record  # noqa: E402
from contentops.publish.x_paths import (  # noqa: E402
    ensure_inside,
    is_single_component,
    resolve_inside,
    safe_relative,
)
from test_x_growth_integration import (  # noqa: E402
    _account,
    _enrichment,
    _growth_request,
    _project,
    _run,
)

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


def _try_symlink(link: Path, target: Path) -> bool:
    try:
        os.symlink(target, link, target_is_directory=target.is_dir())
        return True
    except (OSError, NotImplementedError):
        return False


@test
def test_the_shared_helpers_reject_every_traversal_spelling():
    for value in ("../x", "..\\x", "/etc/passwd", "C:\\x", "\\\\server\\share",
                  "a/../../x", "a\\..\\..\\x", ".", "..", "", "a\x00b"):
        assert safe_relative(value) is None, value
    for value in ("assets/a.png", "sources/review.json", "a-b_c/d.json"):
        assert safe_relative(value) is not None, value
    for value in ("../../x", "a/b", "x.json", "", "..", "C:\\x"):
        assert not is_single_component(value), value
    for value in ("20261101-001", "x_1", "A" * 64):
        assert is_single_component(value), value
    print("[ok] 1. one path contract rejects absolute, drive, UNC, backslash and dot-dot")


@test
def test_content_id_cannot_become_a_path():
    malicious = ("../escaped", "..\\escaped", "a/b", "/abs", "C:\\evil",
                 "..", "a\x00b")
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = _project(temp)
        for content_id in malicious:
            with tempfile.TemporaryDirectory() as inner:
                project = _project(inner)
                result = _run(project, enrichment={"content_id": content_id})
                assert result["status"] == "ENRICHMENT_BLOCKED", (content_id, result)
                assert any("content_id" in reason for reason in result["reasons"]), \
                    (content_id, result["reasons"])
                assert not (Path(inner) / "escaped.json").exists(), content_id
                assert not (Path(inner) / "escaped").exists(), content_id
        assert not (root / "escaped.json").exists()
    print("[ok] 2. a malicious content_id is refused before posts/ is touched")


@test
def test_write_record_refuses_a_path_id_directly():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        for content_id in ("../escaped", "..\\escaped", "a/b"):
            try:
                _write_record(project, {"content_id": content_id})
            except ValueError:
                pass
            else:
                raise AssertionError(f"{content_id!r} was written")
        assert not (Path(temp) / "escaped.json").exists()
        assert not (project / "posts").exists() or not any((project / "posts").iterdir())
    print("[ok] 3. the writer refuses a path id even without the bridge")


@test
def test_a_linked_posts_directory_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        outside = Path(temp) / "outside-posts"
        outside.mkdir()
        if not _try_symlink(project / "posts", outside):
            print("[skip] 4. this host cannot create symlinks")
            return
        result = _run(project)
        assert result["status"] == "EDITORIAL_BLOCKED", result
        assert any("outside the project" in reason or "posts/" in reason
                   for reason in result["reasons"]), result["reasons"]
        assert list(outside.iterdir()) == []
    print("[ok] 4. a posts/ symlink pointing outside the project writes nothing")


@test
def test_review_paths_fail_closed_before_reading():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        outside = Path(temp) / "outside-review.json"
        outside.write_text("{ this is not json", encoding="utf-8")
        for source in ("../outside-review.json", "..\\outside-review.json",
                       str(outside), "C:\\outside-review.json",
                       "sources/../../../outside-review.json"):
            result = _run(project, enrichment={"review_source": source})
            assert result["status"] == "ENRICHMENT_BLOCKED", (source, result)
            reasons = " ".join(result["reasons"])
            assert "review_source" in reasons, (source, reasons)
            assert "not readable JSON" not in reasons, \
                (source, "the outside file was opened")
    print("[ok] 5. an escaping review path is refused, never parsed")


@test
def test_a_review_symlink_to_outside_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        outside = Path(temp) / "outside-review.json"
        outside.write_text('{"decision": "APPROVED", "reviewer": "x"}', encoding="utf-8")
        link = project / "sources" / "review-link.json"
        if not _try_symlink(link, outside):
            print("[skip] 6. this host cannot create symlinks")
            return
        result = _run(project, enrichment={"review_source": "sources/review-link.json"})
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("regular file" in reason or "link" in reason
                   for reason in result["reasons"]), result["reasons"]
    print("[ok] 6. a review symlink is refused even when the target is valid JSON")


@test
def test_a_review_over_the_size_limit_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        (project / "sources" / "big.json").write_text(
            "{" + " " * (1_048_576 + 1) + "}", encoding="utf-8")
        result = _run(project, enrichment={"review_source": "sources/big.json"})
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("1 MiB" in reason for reason in result["reasons"]), result["reasons"]
    print("[ok] 7. an oversized review file is refused")


@test
def test_image_symlink_and_backslash_paths_are_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        outside = Path(temp) / "outside.png"
        outside.write_bytes((project / "assets" / "20261101-900.png").read_bytes())
        link = project / "assets" / "linked.png"
        if _try_symlink(link, outside):
            result = _run(project, enrichment={"image": {"path": "assets/linked.png"}})
            assert result["status"] == "ENRICHMENT_BLOCKED", result
        result = _run(project, enrichment={"image": {"path": "assets\\x.png"}})
        assert result["status"] == "ENRICHMENT_BLOCKED", result
        assert any("project-relative" in reason for reason in result["reasons"])
    print("[ok] 8. image links and backslash paths are refused")


@test
def test_the_gate_refuses_image_and_provenance_escapes_with_the_shared_helper():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        record = json.loads((ROOT / "tests" / "fixtures" /
                             "x-post-partial-contract.json").read_text(encoding="utf-8"))
        record.update({
            "content_id": "20261101-900",
            "mode": "source_analysis",
            "audience_job": "decide",
            "proof_grade": "P0",
            "unique_artifact_ref": "https://example.org/s",
            "experiment_variable": "one",
            "label": "SOURCE_ANALYSIS",
            "theses": [{"thesis": "a", "evidence": "b", "counterexample": "c",
                        "reader_action": "d"}] * 3,
            "red_team": ["a", "b", "c"],
            "image_brief": "x",
            "image": {"path": "assets/../../outside.png"},
            "alt_text": "A card.",
            "review": {"reviewer": "r", "reviewed_at": "2026-11-01",
                       "dimensions": {}, "score": 0},
            "provenance": {"source": "..\\outside.md"},
        })
        codes = {issue.code for issue in validate_post(record, _account(), root=project)}
        assert "IMAGE_PATH_ESCAPE" in codes, codes
        assert "PROVENANCE_PATH_ESCAPE" in codes, codes
    print("[ok] 9. the gate reuses the same containment rule")


@test
def test_relative_containment_helpers_agree():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "inside.json").write_text("{}", encoding="utf-8")
        assert resolve_inside(root, "inside.json", must_be_file=True) is not None
        assert resolve_inside(root, "../outside.json") is None
        assert ensure_inside(root, root / "inside.json")
        assert not ensure_inside(root, root / ".." / "outside.json")
    print("[ok] 10. resolve_inside and ensure_inside reach the same verdict")


@test
def test_a_normal_record_still_reaches_the_manual_package():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = _run(project)
        assert result["status"] == "AWAITING_MANUAL_PUBLISH", result
        record = json.loads((project / result["record_path"]).read_text(encoding="utf-8"))
        assert record["review"]["synthetic"] is True
        assert record["enrichment"]["review_provenance"] == \
            "EXTERNAL_REVIEW_FILE_UNVERIFIED"
        assert record["enrichment"]["review_trust"] == "NOT_VERIFIED"
        assert result["review_trust"] == "NOT_VERIFIED"
        assert record["status"] == "draft" and record["status_url"] is None
    print("[ok] 11. the hardened pipeline still produces a manual package")


@test
def test_a_synthetic_review_is_never_reported_as_trusted():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = _run(project)
        rendered = json.dumps(result).lower()
        assert "approved" not in rendered or "external_review_file_unverified" in rendered
        assert "production" not in rendered
        assert result["review_trust"] == "NOT_VERIFIED"
        assert result["execution_authorized"] is False
        assert result["external_action"] == "none"
    print("[ok] 12. synthetic review and unverified provenance are not production trust")


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
    print(f"All {len(TESTS)} X path-safety tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
