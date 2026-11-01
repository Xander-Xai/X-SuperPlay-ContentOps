"""The decoupled X project: account resolution and the CSV contract.

This slice ships the gate, the account DNA and the project templates, without
the vendor bundle and without the Content Router. These tests prove the two
boundaries the split creates:

1. A project resolves its account from ``project.yaml`` alone, and a slug can
   never be a path.
2. The three CSV tables are checked against the repository's own headers; the
   vendored templates are cross-checked only when a checkout carries them.

Run: python tests/test_x_project.py
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

import x_post  # noqa: E402
from contentops.accounts import X_SCHEMA  # noqa: E402
from contentops.publish import post_verdict, validate_post, x_tables  # noqa: E402
from process_utils import hidden_run, python_executable  # noqa: E402

TESTS: List[Any] = []

PROJECT = ROOT / "projects" / "x-growth-en"
ACCOUNT_PATH = ROOT / "config" / "accounts" / "x-superplay-english.json"

#: The status a person's claim uses when a post went out but no URL was recorded.
PENDING = x_tables.PENDING_STATUS


def test(fn):
    TESTS.append(fn)
    return fn


def _account() -> Dict[str, Any]:
    return json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))


def _project(temp: str, account_slug: str = "x-superplay-english") -> Path:
    """A throwaway X project with the three tables the gate reads."""
    project = Path(temp) / "x-growth-en"
    (project / "posts").mkdir(parents=True)
    (project / "templates").mkdir()
    (project / "project.yaml").write_text(
        f"slug: x-growth-en\naccount_slug: {account_slug}\nplatform: x\n"
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


# ------------------------------------------------------------------- the account


@test
def test_the_shipped_project_resolves_its_account():
    dna = x_post.account_for(PROJECT)
    assert dna.get("schema") == X_SCHEMA, dna.get("schema")
    assert dna.get("slug") == "x-superplay-english", dna.get("slug")
    print("[ok] 1. the shipped project resolves its X account from project.yaml")


@test
def test_a_project_without_an_account_slug_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "bare"
        project.mkdir()
        (project / "project.yaml").write_text("slug: bare\n", encoding="utf-8")
        try:
            x_post.account_for(project)
        except x_post.Refusal as refusal:
            assert refusal.code == "ACCOUNT_SLUG_MISSING", refusal.code
        else:
            raise AssertionError("a project with no account_slug resolved")
    print("[ok] 2. a project with no account_slug is refused by name")


@test
def test_an_unknown_or_path_like_slug_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        unknown = _project(temp, account_slug="no-such-account")
        try:
            x_post.account_for(unknown)
        except x_post.Refusal as refusal:
            assert refusal.code == "ACCOUNT_DNA_MISSING", refusal.code
        else:
            raise AssertionError("an unknown account resolved")

    with tempfile.TemporaryDirectory() as temp:
        traversal = _project(temp, account_slug="../accounts/x-superplay-english")
        try:
            x_post.account_for(traversal)
        except x_post.Refusal as refusal:
            assert refusal.code == "ACCOUNT_SLUG_INVALID", refusal.code
        else:
            raise AssertionError("a path-like account slug resolved")
    print("[ok] 3. an unknown slug and a path-like slug are both refused")


# -------------------------------------------------------------------- the tables


@test
def test_the_shipped_tables_match_the_contract():
    assert not x_tables.verify_tables(PROJECT, [])
    print("[ok] 4. the shipped project's three tables match the contract")


@test
def test_a_missing_vendor_bundle_is_not_an_issue():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        codes = {issue.code for issue in x_tables.verify_tables(project, [])}
        assert "VENDOR_TEMPLATE_MISSING" not in codes, codes
    print("[ok] 5. a checkout without vendor/ is a valid project tree")


@test
def test_verify_tables_refuses_a_foreign_header():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        (project / "templates" / "posts.csv").write_text(
            "content_id,status\n20261025-002,draft\n", encoding="utf-8")
        codes = {issue.code for issue in x_tables.verify_tables(project, [])}
        assert "TABLE_HEADER_DRIFT" in codes, codes
    print("[ok] 6. a foreign header is refused")


@test
def test_verify_tables_refuses_a_metric_that_is_not_a_number():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _write_row(project, {"content_id": "20261025-002", "status": "draft",
                             "impressions": "a few"})
        codes = {issue.code for issue in x_tables.verify_tables(
            project, ["20261025-002"])}
        assert "METRIC_NOT_OBSERVED" in codes, codes
    print("[ok] 7. a metric that is a word is refused, not read as a number")


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
    print("[ok] 8. a zero and a blank are both allowed, and neither is invented")


@test
def test_verify_tables_refuses_a_pending_row_that_has_a_record():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _write_row(project, {"content_id": "20261026-001", "status": PENDING})
        assert not x_tables.verify_tables(project, [])
        codes = {issue.code for issue in x_tables.verify_tables(
            project, ["20261026-001"])}
        assert "CSV_STATUS_INVALID" in codes, codes
    print("[ok] 9. a pending row is legal only while it has no record")


@test
def test_verify_tables_refuses_a_published_row_with_no_url():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _write_row(project, {"content_id": "20261026-001", "status": "published"})
        codes = {issue.code for issue in x_tables.verify_tables(
            project, ["20261026-001"])}
        assert "CSV_PUBLISHED_WITHOUT_URL" in codes, codes
    print("[ok] 10. a published row with no URL is refused")


# --------------------------------------------------------------------- the gate


def _new_record(project: Path, content_id: str, prompt: str = "") -> Dict[str, Any]:
    args = [python_executable(), str(ROOT / "scripts" / "x_post.py"), "--new",
            str(project), "--id", content_id, "--topic", "a topic"]
    if prompt:
        args += ["--prompt", prompt]
    args.append("--json")
    result = hidden_run(args, cwd=str(ROOT), timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


def test_new_records_the_repo_owned_prompt_and_refuses_an_unknown_one():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        payload = _new_record(project, "20261030-002", prompt="post_brief")
        record = json.loads((project / "posts" / "20261030-002.json")
                            .read_text(encoding="utf-8"))
        assert record["prompt_ref"] == "post_brief"
        receipt = json.loads((project / "receipts" / "x-new-20261030-002.json")
                             .read_text(encoding="utf-8"))
        assert receipt["prompt_ref"] == "post_brief"
        assert receipt["prompt_source"].endswith(
            "config/accounts/prompts/x-superplay-english.prompt.md")
        assert payload["prompt_ref"] == "post_brief"

        unknown = hidden_run(
            [python_executable(), str(ROOT / "scripts" / "x_post.py"), "--new",
             str(project), "--id", "20261030-003", "--topic", "a topic",
             "--prompt", "not_a_prompt", "--json"],
            cwd=str(ROOT), timeout=120)
        assert unknown.returncode == 1, unknown.stdout + unknown.stderr
        blocked = json.loads(unknown.stdout)
        assert blocked["code"] == "PROMPT_REF_UNKNOWN", blocked
        assert not (project / "posts" / "20261030-003.json").exists()
    print("[ok] 11. --new resolves the repo-owned prompt and refuses an unknown name")


@test
def test_a_new_record_is_a_draft_and_never_ready():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _new_record(project, "20261030-002")
        record = json.loads((project / "posts" / "20261030-002.json")
                            .read_text(encoding="utf-8"))
        verdict = post_verdict(record, _account(), root=project)
        assert verdict != "READY", verdict
    print("[ok] 12. a scaffolded record is a draft, not a ready post")


@test
def test_the_gate_refuses_an_undeclared_prompt_and_a_missing_provenance():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        _new_record(project, "20261030-002")
        record = json.loads((project / "posts" / "20261030-002.json")
                            .read_text(encoding="utf-8"))

        broken = dict(record)
        broken["prompt_ref"] = "not_a_prompt"
        codes = {issue.code for issue in validate_post(
            broken, _account(), root=project)}
        assert "PROMPT_REF_UNKNOWN" in codes, codes

        missing = dict(record)
        missing["provenance"] = {"source": "vendor/x-growth-os/posts/nope.md"}
        codes = {issue.code for issue in validate_post(
            missing, _account(), root=project)}
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
    print(f"All {len(TESTS)} X project tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
