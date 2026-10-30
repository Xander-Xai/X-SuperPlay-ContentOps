"""The migration: what came over from the source repository, and what may not.

The X-Growth-OS repository was retired into this one. Its drafts, its post table
and two unmerged branches are now here, and the remote is gone. These tests are
the guarantee that the move did not quietly invent anything.

Four properties are checked, and they are the four ways a migration lies:

1. **A record says where it came from.** Every record names a provenance source
   that is really in this tree, so a reader can open the original text.
2. **The table and the records agree.** Every row is backed by a record, except
   the three rows that record a person's claim of publication with no draft and
   no URL -- those are counted separately and never as verified publications.
3. **Nothing is half-vetted.** A thesis is either absent or complete; a record
   never carries two of three candidates and pretends the third is missing.
4. **Nothing claims a publication it cannot show.** A record that says published
   has a real status URL, and a row that says published has one too.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish import post_verdict, valid_status_url  # noqa: E402
from contentops.publish import x_tables  # noqa: E402
from process_utils import hidden_run, python_executable  # noqa: E402

TESTS: List[Any] = []

PROJECT = ROOT / "projects" / "x-growth-en"
POSTS = PROJECT / "posts"
POSTS_CSV = PROJECT / "templates" / "posts.csv"
ACCOUNT_PATH = ROOT / "config" / "accounts" / "x-superplay-english.json"

#: The status the source table used for a post a person says went out, with no
#: URL and no draft behind it.
PENDING = x_tables.PENDING_STATUS


def test(fn):
    TESTS.append(fn)
    return fn


def _records() -> Dict[str, Dict[str, Any]]:
    return {path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(POSTS.glob("*.json"))}


def _rows() -> List[Dict[str, str]]:
    with POSTS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _account() -> Dict[str, Any]:
    return json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))


def _project(temp: str) -> Path:
    """A throwaway X project with the three tables the gate reads."""
    project = Path(temp) / "x-growth-en"
    (project / "posts").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "project.yaml").write_text(
        "slug: x-growth-en\naccount_slug: x-superplay-english\nplatform: x\n"
        "language: en\nformat: 1600x900\n", encoding="utf-8")
    for name, header in (
            ("posts.csv", ",".join(x_tables.POSTS_COLUMNS)),
            ("x-metric-snapshots.csv", ",".join(x_tables.METRIC_COLUMNS)),
            ("x-account-snapshots.csv", ",".join(x_tables.ACCOUNT_COLUMNS))):
        (project / "templates" / name).write_text(header + "\n", encoding="utf-8")
    return project


def _write_row(project: Path, values: Dict[str, str]) -> None:
    path = project / "templates" / "posts.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or x_tables.POSTS_COLUMNS)
        rows = list(reader)
    rows = [row for row in rows if row.get("content_id") != values["content_id"]]
    rows.append({field: values.get(field, "") for field in fields})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


# ------------------------------------------------------------------ the records


@test
def test_every_record_names_a_provenance_that_is_really_here():
    records = _records()
    assert records, "the X project has no records at all"
    for content_id, record in records.items():
        provenance = record.get("provenance")
        assert isinstance(provenance, dict), f"{content_id} has no provenance"
        source = str(provenance.get("source") or "").strip()
        assert source, f"{content_id} names no provenance source"
        if not source.lower().startswith(("http://", "https://")):
            assert (ROOT / source).exists(), \
                f"{content_id} points at {source!r}, which is not in this tree"
        assert str(record.get("source_category") or "").strip(), (
            f"{content_id} keeps no source_category, so the source's own "
            "classification was dropped")
        assert str(record.get("notes") or "").strip(), \
            f"{content_id} carries no note saying what was mapped"
    print(f"[ok] 1. all {len(records)} records name a provenance that exists")


@test
def test_the_post_table_and_the_records_agree():
    records = _records()
    rows = _rows()
    row_ids = [str(row.get("content_id") or "") for row in rows]
    assert len(row_ids) == len(set(row_ids)), "the post table has a duplicate row"
    pending = {str(row.get("content_id") or "") for row in rows
               if row.get("status") == PENDING}
    for content_id in row_ids:
        if content_id in pending:
            # A person's claim with no draft behind it: legal only without a record.
            assert content_id not in records, \
                f"{content_id} is still pending but a record claims it"
        else:
            assert content_id in records, \
                f"the post table has a row for {content_id} with no record"
    for content_id in records:
        assert content_id in row_ids, f"{content_id} has no row in the post table"
    print(f"[ok] 2. {len(rows)} rows and {len(records)} records agree, with "
          f"{len(pending)} unverified claim(s) apart")


@test
def test_no_record_carries_a_half_finished_thesis():
    for content_id, record in _records().items():
        theses = record.get("theses")
        assert isinstance(theses, list), f"{content_id} has no thesis list"
        if not theses:
            continue
        assert len(theses) == 3, (
            f"{content_id} carries {len(theses)} theses; a partial set looks "
            "complete and is not")
        for index, thesis in enumerate(theses, start=1):
            for field in ("thesis", "evidence", "counterexample", "reader_action"):
                assert str(thesis.get(field) or "").strip(), \
                    f"{content_id} thesis {index} has no {field}"
    print("[ok] 3. no record carries a partial thesis set")


@test
def test_nothing_claims_a_publication_it_cannot_show():
    for content_id, record in _records().items():
        if record.get("status") == "published":
            assert valid_status_url(record.get("status_url")), \
                f"{content_id} says published without a real status URL"
        assert record.get("review") is None or isinstance(record.get("review"), dict), \
            f"{content_id} has a review that is neither absent nor an object"
    for row in _rows():
        if row.get("status") == "published":
            assert valid_status_url(row.get("x_post_url")), \
                f"row {row.get('content_id')} says published without a URL"
    print("[ok] 4. nothing claims a publication it cannot show")


@test
def test_the_three_owner_reported_posts_stay_unverified():
    rows = _rows()
    pending = [row for row in rows if row.get("status") == PENDING]
    assert len(pending) == 3, (
        f"the post table holds {len(pending)} unverified claim(s); the source "
        "table recorded three")
    for row in pending:
        assert not str(row.get("x_post_url") or "").strip(), \
            f"row {row.get('content_id')} is pending but carries a URL"
    account = _account()
    records = _records()
    published = [content_id for content_id, record in records.items()
                 if record.get("status") == "published"]
    assert not published, f"{published} claim(s) are published without a review"
    issues = x_tables.verify_tables(PROJECT, list(records))
    assert not issues, [issue.as_dict() for issue in issues]
    print("[ok] 5. the three owner-reported posts stay unverified claims")


@test
def test_every_migrated_record_is_graded_and_none_is_ready():
    """A migrated draft is a draft. None of them may pass the gate by accident."""
    account = _account()
    for content_id, record in _records().items():
        verdict = post_verdict(record, account, root=PROJECT)
        assert verdict in ("DRAFT", "IMAGE_MISSING", "BLOCKED"), \
            f"{content_id} is {verdict}; a migrated draft has no human review"
        assert verdict != "READY", f"{content_id} is READY without a review"
    print("[ok] 6. every migrated record is graded and none is READY")


# --------------------------------------------------------------------- the tables


@test
def test_verify_tables_refuses_a_foreign_header():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        path = project / "templates" / "posts.csv"
        path.write_text("content_id,status\n20261025-002,draft\n", encoding="utf-8")
        issues = x_tables.verify_tables(project, [])
        codes = {issue.code for issue in issues}
        assert "TABLE_HEADER_DRIFT" in codes, [issue.as_dict() for issue in issues]
    print("[ok] 7. a foreign header is refused")


@test
def test_verify_tables_refuses_a_metric_that_is_not_a_number():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _write_row(project, {"content_id": "20261025-002", "status": "draft",
                             "impressions": "a few"})
        issues = x_tables.verify_tables(project, ["20261025-002"])
        codes = {issue.code for issue in issues}
        assert "METRIC_NOT_OBSERVED" in codes, [issue.as_dict() for issue in issues]
    print("[ok] 8. a metric that is a word is refused, not read as a number")


@test
def test_verify_tables_keeps_a_blank_metric_distinct_from_a_zero():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _write_row(project, {"content_id": "20261025-002", "status": "draft",
                             "impressions": "0"})
        assert not x_tables.verify_tables(project, ["20261025-002"])
        _write_row(project, {"content_id": "20261025-002", "status": "draft",
                             "impressions": ""})
        assert not x_tables.verify_tables(project, ["20261025-002"])
    print("[ok] 9. a zero and a blank are both allowed, and neither is invented")


@test
def test_verify_tables_refuses_a_pending_row_that_has_a_record():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _write_row(project, {"content_id": "20261026-001", "status": PENDING})
        assert not x_tables.verify_tables(project, [])
        # The same row is illegal once a record exists: a claim with a draft behind
        # it should have been graded, not left as a claim.
        issues = x_tables.verify_tables(project, ["20261026-001"])
        codes = {issue.code for issue in issues}
        assert "CSV_STATUS_INVALID" in codes, [issue.as_dict() for issue in issues]
    print("[ok] 10. a pending row is legal only while it has no record")


@test
def test_verify_tables_refuses_a_published_row_with_no_url():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _write_row(project, {"content_id": "20261026-001", "status": "published"})
        issues = x_tables.verify_tables(project, ["20261026-001"])
        codes = {issue.code for issue in issues}
        assert "CSV_PUBLISHED_WITHOUT_URL" in codes, \
            [issue.as_dict() for issue in issues]
    print("[ok] 11. a published row with no URL is refused")


# ---------------------------------------------------------------------- the prompt


@test
def test_new_records_the_prompt_reference_and_refuses_an_unknown_one():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        result = hidden_run(
            [python_executable(), str(ROOT / "scripts" / "x_post.py"), "--new",
             str(project), "--id", "20261030-002", "--topic", "a topic",
             "--prompt", "daily_post", "--json"],
            cwd=str(ROOT), timeout=120)
        assert result.returncode == 0, result.stdout + result.stderr
        record = json.loads((project / "posts" / "20261030-002.json")
                            .read_text(encoding="utf-8"))
        assert record["prompt_ref"] == "daily_post"
        payload = json.loads(result.stdout)
        assert payload["prompt_requirements"], \
            "the prompt's own requirements must be read back, not invented"
        receipt = json.loads((project / "receipts" / "x-new-20261030-002.json")
                             .read_text(encoding="utf-8"))
        assert receipt["prompt_ref"] == "daily_post"
        assert receipt["prompt_source"].endswith("DAILY-POST.md")

        unknown = hidden_run(
            [python_executable(), str(ROOT / "scripts" / "x_post.py"), "--new",
             str(project), "--id", "20261030-003", "--topic", "a topic",
             "--prompt", "not_a_prompt", "--json"],
            cwd=str(ROOT), timeout=120)
        assert unknown.returncode == 1, unknown.stdout + unknown.stderr
        blocked = json.loads(unknown.stdout)
        assert blocked["code"] == "PROMPT_REF_UNKNOWN", blocked
        assert not (project / "posts" / "20261030-003.json").exists(), \
            "a refused prompt must not leave a record behind"
    print("[ok] 12. --new keeps the prompt reference, reads its requirements back "
          "and refuses an unknown name")


@test
def test_the_gate_refuses_a_record_that_names_a_prompt_this_account_does_not_declare():
    from contentops.publish import validate_post
    account = _account()
    record = _records()["20261030-001"]
    broken = dict(record)
    broken["prompt_ref"] = "not_a_prompt"
    codes = {issue.code for issue in validate_post(broken, account, root=PROJECT)}
    assert "PROMPT_REF_UNKNOWN" in codes, codes

    missing = dict(record)
    missing["provenance"] = {"source": "vendor/x-growth-os/posts/nope.md"}
    codes = {issue.code for issue in validate_post(missing, account, root=PROJECT)}
    assert "PROVENANCE_SOURCE_ABSENT" in codes, codes
    print("[ok] 13. an undeclared prompt and a missing provenance are both refused")


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
    print(f"All {len(TESTS)} X migration tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
