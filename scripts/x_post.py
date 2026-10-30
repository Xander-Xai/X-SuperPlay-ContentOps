#!/usr/bin/env python3
"""The X post gate: scaffold a record, grade it, package it, and record a URL.

Why this exists
---------------
The vendored workflow at ``vendor/x-growth-os/`` states its delivery and editorial
gates in prose: a 280-weighted-character body, a real 1600x900 raster card, ALT
text, three distinct theses with counterexamples, a human review scored on six
dimensions, four recovery fields, a proof grade, and a real
``x.com/<handle>/status/<id>`` URL before anything is called published.

Prose does not refuse anything. This command does. It is the X track's one
enforced gate, and it never publishes: ``--package`` assembles what a person
pastes and attaches, and ``--mark-published`` only records a URL that person
already has.

``--prompt`` names the account prompt a record was written from. It is a
reference, not a generator: the command reads that prompt's own requirement
headings back as a checklist and refuses a name the account does not declare.

Usage
-----
    python scripts/x_post.py --new projects/x-growth-en --id 20261030-001 \
        --topic "verification before completion"
    python scripts/x_post.py --new projects/x-growth-en --id 20261030-002 \
        --topic "..." --prompt daily_post
    python scripts/x_post.py --check projects/x-growth-en --id 20261030-001
    python scripts/x_post.py --package projects/x-growth-en --id 20261030-001
    python scripts/x_post.py --mark-published projects/x-growth-en \
        --id 20261030-001 --url https://x.com/<handle>/status/<id>
    python scripts/x_post.py --verify-log projects/x-growth-en
    python scripts/x_post.py --verify-tables projects/x-growth-en

Every action writes a receipt under the project's ``receipts/`` directory:
``x-check-<id>.json`` for a grade, ``x-package-<id>.json`` for a package,
``x-publish-<id>.json`` for a recorded publication, ``x-tables-<date>.json``
for the CSV tables.

Exit codes: 0 pass, 1 refusal, 2 misuse.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import account_route as ar  # noqa: E402
from contentops.accounts import X_SCHEMA  # noqa: E402
from contentops.publish import (  # noqa: E402
    AWAITING,
    SCHEMA,
    Issue,
    PackageBlocked,
    PostFormatError,
    PublishMode,
    PublisherUnavailable,
    build_package,
    load_post,
    post_verdict,
    valid_status_url,
    validate_post,
)
from contentops.publish import x_prompts, x_tables  # noqa: E402
from contentops.publish.x_text import parts_lengths  # noqa: E402

#: What this command's receipts declare.
RECEIPT_SCHEMA = "contentops.x-post-gate/v1"

EXIT_PASS, EXIT_REFUSED, EXIT_MISUSE = 0, 1, 2

#: The vendored posts table, unchanged, so its own report script can read ours.
POSTS_CSV = Path("templates") / "posts.csv"
COLUMNS = x_tables.POSTS_COLUMNS

#: The metric columns. Blank means unobserved; `0` means observed and zero.
METRIC_COLUMNS = x_tables.POST_METRIC_COLUMNS


class Refusal(Exception):
    """A named refusal that is the caller's to fix."""

    def __init__(self, code: str, detail: str,
                 issues: Optional[List[Issue]] = None) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.issues = issues or []


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def account_for(project: Path) -> Dict[str, Any]:
    """The X account this project belongs to, or a refusal."""
    project = Path(project)
    if not project.is_dir():
        raise Refusal("PROJECT_MISSING", f"{project} is not a directory")
    slug = ar.declared_account_slug(project)
    if not slug:
        raise Refusal("ACCOUNT_SLUG_MISSING",
                      f"{project / 'project.yaml'} declares no account_slug")
    try:
        dna = ar.load_dna(slug)
    except ar.RouteBlocked as blocked:
        raise Refusal(blocked.code, blocked.detail) from blocked
    if dna.get("schema") != X_SCHEMA:
        raise Refusal(
            "ACCOUNT_NOT_X",
            f"{slug} is a {dna.get('schema')!r} account; the X gate owns "
            f"{X_SCHEMA!r}, and a film account has a different gate")
    return dna


def post_path(project: Path, content_id: str) -> Path:
    return Path(project) / "posts" / f"{content_id}.json"


def _post_ids(project: Path) -> List[str]:
    directory = Path(project) / "posts"
    if not directory.is_dir():
        return []
    return sorted(path.stem for path in directory.glob("*.json"))


def _resolve_id(project: Path, content_id: Optional[str]) -> str:
    if content_id:
        return content_id
    ids = _post_ids(project)
    if len(ids) == 1:
        return ids[0]
    raise Refusal(
        "CONTENT_ID_REQUIRED",
        f"{Path(project) / 'posts'} holds {len(ids)} records; name one with --id")


# --------------------------------------------------------------------------- CSV


def _read_rows(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    if not path.is_file():
        return list(COLUMNS), []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or COLUMNS)
        return fields, list(reader)


def _write_rows(path: Path, fields: List[str], rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _upsert_row(project: Path, values: Dict[str, str]) -> Path:
    """Set the named columns on the row for this content id, creating it if new."""
    path = Path(project) / POSTS_CSV
    fields, rows = _read_rows(path)
    unknown = [key for key in values if key not in fields]
    if unknown:
        raise Refusal("CSV_COLUMN_MISSING",
                      f"{path.name} has no {unknown} column; the vendored template "
                      "is the contract")
    content_id = values["content_id"]
    for row in rows:
        if row.get("content_id") == content_id:
            row.update(values)
            break
    else:
        rows.append({field: "" for field in fields} | values)
    _write_rows(path, fields, rows)
    return path


def _row_for(project: Path, content_id: str) -> Optional[Dict[str, str]]:
    _fields, rows = _read_rows(Path(project) / POSTS_CSV)
    for row in rows:
        if row.get("content_id") == content_id:
            return row
    return None


# ----------------------------------------------------------------------- record


def _template(account: Dict[str, Any], content_id: str, topic: str,
              sources: List[str], mode: str,
              prompt_ref: str = "") -> Dict[str, Any]:
    """A draft record with the holes a person has to fill, and nothing invented."""
    pillars = [str(pillar.get("name")) for pillar in account.get("content_pillars") or []
               if isinstance(pillar, dict)]
    if mode not in pillars:
        raise Refusal("MODE_UNKNOWN",
                      f"mode {mode!r} is not one of the account's pillars {pillars}")
    return {
        "schema": SCHEMA,
        "content_id": content_id,
        "account_slug": account.get("slug"),
        "mode": mode,
        "topic": topic,
        "sources": list(sources),
        "audience_job": "",
        "proof_grade": "P0",
        "unique_artifact_ref": "",
        "experiment_variable": "",
        "label": "",
        "theses": [],
        "red_team": [],
        "post_copy": {"parts": []},
        "image_brief": "",
        "image": None,
        "image_status": "missing",
        "alt_text": "",
        "prompt_ref": prompt_ref,
        "provenance": None,
        "source_category": "",
        "source_angles": [],
        "review": None,
        "status": "draft",
        "status_url": None,
        "scheduled_for": None,
        "metrics": None,
        "notes": "created by scripts/x_post.py --new; every empty field is a refusal",
    }


def _write_post(path: Path, post: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(post, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")


def _receipt(project: Path, name: str, payload: Dict[str, Any]) -> Path:
    path = Path(project) / "receipts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return path


def _issues(issues: List[Issue]) -> List[Dict[str, str]]:
    return [issue.as_dict() for issue in issues]


# ---------------------------------------------------------------------- actions


def action_new(project: Path, content_id: str, topic: str, sources: List[str],
               mode: str, prompt: str = "") -> Dict[str, Any]:
    account = account_for(project)
    path = post_path(project, content_id)
    if path.exists():
        raise Refusal("POST_EXISTS",
                      f"{path} already exists; editing it is a different decision "
                      "from creating it")
    if not str(topic or "").strip():
        raise Refusal("TOPIC_MISSING", "--new needs --topic; a record with no subject "
                                       "gates nothing")
    prompt_ref = ""
    checklist: List[str] = []
    prompt_path: Optional[Path] = None
    if str(prompt or "").strip():
        prompt_ref, prompt_path, code = x_prompts.resolve(account, prompt.strip())
        if code == "PROMPT_REF_UNKNOWN":
            raise Refusal(
                code,
                f"prompt {prompt_ref!r} is not one of the account's prompts "
                f"{sorted(x_prompts.prompt_map(account))}")
        if code == "PROMPT_REF_ABSENT":
            raise Refusal(
                code,
                f"prompt {prompt_ref!r} points at a file that is not in this tree; "
                "a prompt reference must be real")
        checklist = x_prompts.prompt_checklist(prompt_path)
    post = _template(account, content_id, topic.strip(), sources, mode, prompt_ref)
    _write_post(path, post)

    publication = account.get("publication") or {}
    handle = publication.get("handle") if publication.get("handle_status") == "CONFIRMED" else ""
    csv_path = _upsert_row(project, {
        "date_local": date.today().isoformat(),
        "timezone": "UTC",
        "content_id": content_id,
        "mode": mode,
        "topic": topic.strip(),
        "source_url": sources[0] if sources else "",
        "status": "draft",
        "x_post_url": "",
        "post_count": "1",
        "image_status": "missing",
        "account_handle": str(handle or ""),
        "icp": str(account.get("core_audience") or "")[:120],
        "proof_grade": post["proof_grade"],
        "experiment_variable": "",
        "notes": "seeded by scripts/x_post.py --new; unobserved metrics stay blank",
    })
    verdict = post_verdict(post, account, root=project)
    issues = validate_post(post, account, root=project)
    receipt = _receipt(project, f"x-new-{content_id}.json", {
        "schema": RECEIPT_SCHEMA,
        "action": "new",
        "content_id": content_id,
        "created_at": _now(),
        "post": path.relative_to(project).as_posix(),
        "csv": Path(csv_path).relative_to(project).as_posix(),
        "verdict": verdict,
        "prompt_ref": prompt_ref or None,
        "prompt_source": (Path(x_prompts.prompt_map(account)[prompt_ref]).as_posix()
                          if prompt_ref else None),
        "prompt_requirements": checklist,
        "outstanding": _issues(issues),
        "cannot": ["nothing was posted, rendered or scored; every field below empty "
                   "is a person's to fill"],
    })
    return {"action": "new", "content_id": content_id, "verdict": verdict,
            "post": post, "issues": issues,
            "prompt_ref": prompt_ref or None,
            "prompt_requirements": checklist,
            "receipt": receipt.relative_to(project).as_posix()}


def action_check(project: Path, content_id: str) -> Dict[str, Any]:
    account = account_for(project)
    path = post_path(project, content_id)
    post = load_post(path)
    issues = validate_post(post, account, root=project)
    verdict = post_verdict(post, account, root=project)
    receipt = _receipt(project, f"x-check-{content_id}.json", {
        "schema": RECEIPT_SCHEMA,
        "action": "check",
        "content_id": content_id,
        "checked_at": _now(),
        "verdict": verdict,
        "issues": _issues(issues),
        "status": post.get("status"),
        "status_url": post.get("status_url"),
        "copy_lengths": [
            {"index": index, "weighted_length": issue}
            for index, issue in _lengths(post)],
    })
    return {"action": "check", "content_id": content_id, "verdict": verdict,
            "issues": issues, "receipt": receipt.relative_to(project).as_posix()}


def _lengths(post: Dict[str, Any]) -> List[Tuple[int, int]]:
    parts = []
    copy = post.get("post_copy")
    if isinstance(copy, dict):
        parts = [str(part) for part in copy.get("parts") or []]
    elif isinstance(copy, list):
        parts = [str(part) for part in copy]
    elif isinstance(copy, str):
        parts = [copy]
    return list(enumerate(parts_lengths(parts), start=1))


def action_package(project: Path, content_id: str) -> Dict[str, Any]:
    account = account_for(project)
    post = load_post(post_path(project, content_id))
    issues = validate_post(post, account, root=project)
    verdict = post_verdict(post, account, root=project)
    if verdict not in ("READY", "PUBLISHED"):
        raise Refusal("PACKAGE_REFUSED",
                      f"{content_id} is {verdict}; a package is built from a READY "
                      "post, not from an intention", issues)
    package = build_package(post, account, project)
    return {"action": "package", "content_id": content_id, "verdict": verdict,
            "package": package, "issues": issues}


def action_mark_published(project: Path, content_id: str, url: str,
                          reviewer: Optional[str], opinion: Optional[str]) -> Dict[str, Any]:
    account = account_for(project)
    path = post_path(project, content_id)
    post = load_post(path)
    verdict = post_verdict(post, account, root=project)
    if verdict != "READY":
        raise Refusal(
            "NOT_READY",
            f"{content_id} is {verdict}; publication is recorded for a post that "
            "passed every gate, and a URL does not make a draft ready",
            validate_post(post, account, root=project))
    if not valid_status_url(url):
        raise Refusal("PUBLISHED_URL_INVALID",
                      f"{url!r} is not an https://x.com/<handle>/status/<id> link")

    handle = url.strip().rstrip("/").split("/")[3]
    post["status"] = "published"
    post["status_url"] = url.strip()
    post["image_status"] = "generated"
    if reviewer:
        post.setdefault("review", {})
        if isinstance(post["review"], dict):
            post["review"]["confirmed_by"] = reviewer
    if opinion:
        post["notes"] = (str(post.get("notes") or "") + " | " if post.get("notes") else "") + \
            f"publish note from {reviewer or 'operator'}: {opinion}"
    _write_post(path, post)

    issues = validate_post(post, account, root=project)
    if issues:
        _write_post(path, {**post, "status": "draft", "status_url": None})
        raise Refusal("PUBLISHED_RECORD_INVALID",
                      "recording the URL left the record invalid, so the change was "
                      "reverted", issues)

    _upsert_row(project, {
        "content_id": content_id,
        "status": "published",
        "x_post_url": url.strip(),
        "image_status": "generated",
        "account_handle": handle,
        "notes": "status and URL recorded by scripts/x_post.py --mark-published; "
                 "post_published_at stays blank until it is observed",
    })
    receipt = _receipt(project, f"x-publish-{content_id}.json", {
        "schema": RECEIPT_SCHEMA,
        "action": "mark-published",
        "content_id": content_id,
        "recorded_at": _now(),
        "status_url": url.strip(),
        "handle": handle,
        "handle_status": "CONFIRMED_BY_STATUS_URL",
        "reviewer": reviewer,
        "opinion": opinion,
        "publication_mode": PublishMode.MANUAL_ONLY.value,
        "cannot": ["this repository did not post; a person did, and this record only "
                   "stores what they observed"],
    })
    return {"action": "mark-published", "content_id": content_id, "verdict": "PUBLISHED",
            "status_url": url.strip(), "handle": handle,
            "receipt": receipt.relative_to(project).as_posix()}


def action_verify_log(project: Path) -> Dict[str, Any]:
    account = account_for(project)
    drift: List[Dict[str, str]] = []
    ids = _post_ids(project)
    published = set()
    for content_id in ids:
        post = load_post(post_path(project, content_id))
        row = _row_for(project, content_id)
        if post.get("status") == "published":
            published.add(content_id)
            if not valid_status_url(post.get("status_url")):
                drift.append({"content_id": content_id, "kind": "JSON_URL_INVALID",
                              "detail": f"status_url {post.get('status_url')!r}"})
            if row is None:
                drift.append({"content_id": content_id, "kind": "CSV_ROW_MISSING",
                              "detail": f"published record has no row in {POSTS_CSV}"})
                continue
            if row.get("status") != "published":
                drift.append({"content_id": content_id, "kind": "CSV_STATUS_STALE",
                              "detail": f"row status is {row.get('status')!r}"})
            if str(row.get("x_post_url") or "").strip() != str(post.get("status_url") or "").strip():
                drift.append({"content_id": content_id, "kind": "CSV_URL_DRIFT",
                              "detail": f"row {row.get('x_post_url')!r} != "
                                        f"record {post.get('status_url')!r}"})
        elif row is not None and row.get("status") == "published":
            drift.append({"content_id": content_id, "kind": "CSV_PUBLISHED_JSON_DRAFT",
                          "detail": "the row says published and the record does not"})
    for row in _read_rows(Path(project) / POSTS_CSV)[1]:
        content_id = str(row.get("content_id") or "")
        if row.get("status") == "published" and content_id not in ids:
            drift.append({"content_id": content_id, "kind": "CSV_ROW_ORPHANED",
                          "detail": "a published row with no post record"})
    return {"action": "verify-log", "published": sorted(published),
            "posts": len(ids), "drift": drift, "verdict": "PASS" if not drift else "BLOCKED"}


def action_verify_tables(project: Path) -> Dict[str, Any]:
    """Check the three CSV tables against the vendored contract and the records."""
    account = account_for(project)
    ids = _post_ids(project)
    issues = x_tables.verify_tables(project, ids)
    pending = [
        row.get("content_id")
        for row in _read_rows(Path(project) / POSTS_CSV)[1]
        if row.get("status") == x_tables.PENDING_STATUS
    ]
    receipt = _receipt(project, f"x-tables-{date.today().isoformat()}.json", {
        "schema": RECEIPT_SCHEMA,
        "action": "verify-tables",
        "checked_at": _now(),
        "records": len(ids),
        "tables": ["templates/posts.csv", "templates/x-metric-snapshots.csv",
                   "templates/x-account-snapshots.csv"],
        "unverified_reported_publications": sorted(str(item) for item in pending),
        "issues": _issues(issues),
        "verdict": "PASS" if not issues else "BLOCKED",
        "cannot": ["a pending row is a person's claim that a post went out; nothing "
                   "in this tree can verify it until the real URL is recorded"],
    })
    return {"action": "verify-tables", "records": len(ids), "issues": issues,
            "unverified_reported_publications": sorted(str(item) for item in pending),
            "verdict": "PASS" if not issues else "BLOCKED",
            "receipt": receipt.relative_to(project).as_posix()}


# ---------------------------------------------------------------------- printing


def _print_issues(issues: List[Issue]) -> None:
    for issue in issues:
        print(f"  {issue}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold, grade, package and record an X post. Never publishes.")
    parser.add_argument("project", help="X project directory, e.g. projects/x-growth-en")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--new", action="store_true",
                         help="write a draft record for --id")
    actions.add_argument("--check", action="store_true",
                         help="grade the record and refuse it by name")
    actions.add_argument("--package", action="store_true",
                         help="assemble the manual publish package")
    actions.add_argument("--mark-published", action="store_true",
                         help="record a real status URL for a READY post")
    actions.add_argument("--verify-log", action="store_true",
                         help="cross-check published records against posts.csv")
    actions.add_argument("--verify-tables", action="store_true",
                         help="check the CSV tables against the vendored contract")
    parser.add_argument("--id", dest="content_id", help="content id, e.g. 20261030-001")
    parser.add_argument("--topic", help="the post's subject, for --new")
    parser.add_argument("--source", action="append", default=[],
                        help="a source URL, repeatable")
    parser.add_argument("--mode", default="workflow_artifact",
                        help="one of the account's content pillars")
    parser.add_argument("--prompt", default="",
                        help="the account prompt this record is written from, e.g. "
                             "daily_post")
    parser.add_argument("--url", help="the real x.com/<handle>/status/<id> URL")
    parser.add_argument("--reviewer", help="who confirmed the publication")
    parser.add_argument("--opinion", help="their note, recorded verbatim")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    project = Path(args.project)

    def emit(payload: Dict[str, Any]) -> None:
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2,
                             default=lambda value: value.as_dict()
                             if isinstance(value, Issue) else str(value)))

    try:
        if args.verify_log:
            result = action_verify_log(project)
            emit(result)
            if not args.json:
                print(f"{result['posts']} record(s), {len(result['published'])} published")
                for item in result["drift"]:
                    print(f"  DRIFT {item['content_id']} {item['kind']}: {item['detail']}")
                print(result["verdict"])
            return EXIT_PASS if result["verdict"] == "PASS" else EXIT_REFUSED

        if args.verify_tables:
            result = action_verify_tables(project)
            emit(result)
            if not args.json:
                print(f"{result['records']} record(s), {len(result['issues'])} issue(s)")
                for item in result["issues"]:
                    print(f"  {item.code}: {item.detail}")
                for content_id in result["unverified_reported_publications"]:
                    print(f"  UNVERIFIED {content_id}: reported published, no URL")
                print(result["verdict"])
            return EXIT_PASS if result["verdict"] == "PASS" else EXIT_REFUSED

        content_id = _resolve_id(project, args.content_id)

        if args.new:
            result = action_new(project, content_id, args.topic or "", args.source,
                                args.mode, args.prompt)
        elif args.check:
            result = action_check(project, content_id)
        elif args.package:
            result = action_package(project, content_id)
        else:
            if not args.url:
                raise Refusal("URL_MISSING", "--mark-published needs --url; a record "
                                             "without a link is not evidence")
            result = action_mark_published(project, content_id, args.url,
                                           args.reviewer, args.opinion)

        emit({key: value for key, value in result.items() if key != "post"})
        if not args.json:
            if result["action"] == "new":
                print(f"{result['content_id']}: created, {len(result['issues'])} "
                      "field(s) outstanding before the gate can pass")
                if result.get("prompt_ref"):
                    print(f"  prompt {result['prompt_ref']} asks for:")
                    for item in result.get("prompt_requirements") or []:
                        print(f"    - {item}")
                _print_issues(result["issues"])
            else:
                print(f"{result['content_id']}: {result['verdict']}")
            if result["action"] == "package":
                package = result["package"]
                print(f"  receipt {package['receipt']} ({package['status']})")
                for part in package["copy"]["parts"]:
                    print(f"  part {part['index']} [{part['weighted_length']}"
                          f"/{package['copy']['budget']}]")
                    print("    " + part["text"].replace("\n", "\n    "))
                print(f"  image {package['image']['path']} "
                      f"({package['image']['width']}x{package['image']['height']}, "
                      f"{package['image']['format']})")
                print(f"  alt   {package['alt_text']}")
                print("  a person posts this; nothing here did")
            elif result.get("issues"):
                _print_issues(result["issues"])
            if result.get("receipt"):
                print(f"  receipt {result['receipt']}")
        if result["action"] in ("new", "package", "mark-published"):
            # A scaffold, a package and a recorded URL are writes that succeeded;
            # what they produced is graded by the next `--check`.
            return EXIT_PASS
        return EXIT_PASS if result["verdict"] in ("READY", "PUBLISHED") else EXIT_REFUSED

    except Refusal as refusal:
        payload = {"status": "BLOCKED", "code": refusal.code,
                   "reason": refusal.detail, "issues": _issues(refusal.issues)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"REFUSED {refusal.code}: {refusal.detail}", file=sys.stderr)
            _print_issues(refusal.issues)
        return EXIT_REFUSED
    except (PostFormatError, PackageBlocked, PublisherUnavailable) as refused:
        if args.json:
            print(json.dumps({"status": "BLOCKED", "reason": str(refused)},
                             ensure_ascii=False, indent=2))
        else:
            print(f"REFUSED: {refused}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(EXIT_MISUSE)
