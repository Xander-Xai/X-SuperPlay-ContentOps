"""The CSV mirror: three tables, and what each row is allowed to say.

The vendored workflow keeps its history in three CSV tables under ``templates/``:
``posts.csv`` (one row per intended post), ``x-metric-snapshots.csv`` (observed
per-post metrics at a recorded age window) and ``x-account-snapshots.csv``
(observed account-level follower and impression counts).

Two rules from that workflow are mechanical and belong in a gate rather than in
prose:

1. **A blank metric is not a zero.** A blank cell means nobody observed it; a
   ``0`` means it was observed and it was zero. The two are never
   interchangeable, and a table that conflates them is worse than no table.
2. **A row that says "published" needs a real link.** A claim of publication
   without an ``x.com/<handle>/status/<id>`` URL is the same lie the record gate
   refuses, in a different file.

The tables are also how the vendored report script reads this project, so their
headers are the vendor's headers: a change here is a change to the vendored
contract and has to be a new import, not an edit.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from contentops.publish.x_post import Issue, POST_STATUSES

#: The repository root, for the vendored templates the headers come from.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where the vendored tables live. Their headers are the contract.
VENDOR_TEMPLATES = REPO_ROOT / "vendor" / "x-growth-os" / "templates"

#: The post table's columns, in the vendored order.
POSTS_COLUMNS = (
    "date_local", "timezone", "content_id", "mode", "topic", "source_url",
    "status", "x_post_url", "post_count", "image_status", "impressions", "likes",
    "reposts", "replies", "bookmarks", "profile_visits", "follower_delta", "notes",
    "account_handle", "icp", "proof_grade", "experiment_variable", "post_published_at",
)

#: The per-post metric table's columns, in the vendored order.
METRIC_COLUMNS = (
    "metric_snapshot_id", "content_id", "x_post_url", "post_published_at",
    "observed_at", "timezone", "age_window", "metric_source",
    "metric_definition_version", "data_access", "organic_paid", "impressions",
    "engagements", "likes", "reposts", "replies", "bookmarks", "profile_clicks",
    "link_clicks", "attributed_follows", "qualified_signal_count", "missing_reason",
    "notes",
)

#: The account table's columns, in the vendored order.
ACCOUNT_COLUMNS = (
    "snapshot_id", "account_handle", "observed_at", "timezone",
    "observation_source", "followers_count", "following_count",
    "account_profile_visits", "account_impressions", "platform_reported_net_follows",
    "account_notice_state", "data_access", "notes",
)

#: The post table's own metric columns. Blank means unobserved; `0` means zero.
POST_METRIC_COLUMNS = (
    "impressions", "likes", "reposts", "replies", "bookmarks", "profile_visits",
    "follower_delta",
)

#: The per-post metric table's counted columns.
SNAPSHOT_METRIC_COLUMNS = (
    "impressions", "engagements", "likes", "reposts", "replies", "bookmarks",
    "profile_clicks", "link_clicks", "attributed_follows", "qualified_signal_count",
)

#: The account table's counted columns.
ACCOUNT_COUNT_COLUMNS = (
    "followers_count", "following_count", "account_profile_visits",
    "account_impressions", "platform_reported_net_follows",
)

#: The ages a snapshot may claim, from the vendored recovery doc.
AGE_WINDOWS = ("T+2H", "T+24H", "T+72H", "T+7D")

#: A status the vendor recorded but a record cannot hold: a person said it was
#: published and no URL proves it. It is legal only on a row with no record.
PENDING_STATUS = "reported_published_url_pending"


def _read(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    if not path.is_file():
        return [], []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def _vendor_header(name: str) -> List[str]:
    """The header the vendored template itself carries."""
    fields, _rows = _read(VENDOR_TEMPLATES / name)
    return fields


def _header_issue(table: str, actual: Sequence[str],
                  expected: Sequence[str]) -> Optional[Issue]:
    if not actual:
        return Issue("TABLE_MISSING", f"{table} does not exist")
    if list(actual) != list(expected):
        missing = [name for name in expected if name not in actual]
        extra = [name for name in actual if name not in expected]
        return Issue("TABLE_HEADER_DRIFT",
                     f"{table} has columns {list(actual)}; the vendored contract is "
                     f"{list(expected)} (missing {missing}, unexpected {extra})")
    return None


def _number_issue(table: str, row_index: int, column: str, raw: str) -> Optional[Issue]:
    """A metric cell is blank (unobserved) or a non-negative integer (observed)."""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        return Issue("METRIC_NOT_OBSERVED",
                     f"{table} row {row_index} column {column!r} is {text!r}; a "
                     "metric is a non-negative integer or blank (unobserved), never "
                     "a word")
    if value < 0:
        return Issue("METRIC_NOT_OBSERVED",
                     f"{table} row {row_index} column {column!r} is {value}; a "
                     "counted metric is never negative")
    return None


def verify_posts_table(path: Path, records: Sequence[str]) -> List[Issue]:
    """Check the post table against the records it is supposed to mirror."""
    issues: List[Issue] = []
    fields, rows = _read(path)
    header = _header_issue(path.name, fields,
                            _vendor_header("posts.csv") or POSTS_COLUMNS)
    if header:
        return [header]
    for index, row in enumerate(rows, start=2):
        content_id = str(row.get("content_id") or "").strip()
        status = str(row.get("status") or "").strip()
        if not content_id:
            issues.append(Issue("CSV_CONTENT_ID_MISSING",
                                f"{path.name} row {index} names no content_id"))
            continue
        if status not in POST_STATUSES:
            if status == PENDING_STATUS and content_id not in records:
                # A recorded claim with no record behind it. Honest, but it is a
                # claim and nothing in this tree can verify it.
                pass
            else:
                issues.append(Issue("CSV_STATUS_INVALID",
                                    f"{path.name} row {index} has status {status!r}; "
                                    f"expected one of {list(POST_STATUSES)} or "
                                    f"{PENDING_STATUS!r} on a row with no record"))
        if status == "published":
            url = str(row.get("x_post_url") or "").strip()
            if not url:
                issues.append(Issue("CSV_PUBLISHED_WITHOUT_URL",
                                    f"{path.name} row {index} says published with no "
                                    "x_post_url; publication is a link, not a claim"))
        for column in POST_METRIC_COLUMNS:
            issue = _number_issue(path.name, index, column, row.get(column, ""))
            if issue:
                issues.append(issue)
    return issues


def verify_metric_table(path: Path) -> List[Issue]:
    """Check the per-post metric table: ages, counts and the missing_reason rule."""
    issues: List[Issue] = []
    fields, rows = _read(path)
    header = _header_issue(path.name, fields,
                            _vendor_header("x-metric-snapshots.csv") or METRIC_COLUMNS)
    if header:
        return [header]
    for index, row in enumerate(rows, start=2):
        age = str(row.get("age_window") or "").strip()
        if age and age not in AGE_WINDOWS:
            issues.append(Issue("CSV_AGE_WINDOW_INVALID",
                                f"{path.name} row {index} has age_window {age!r}; the "
                                f"vendored windows are {list(AGE_WINDOWS)}"))
        for column in ("metric_source", "data_access"):
            if not str(row.get(column) or "").strip():
                issues.append(Issue("CSV_SOURCE_MISSING",
                                    f"{path.name} row {index} has no {column}; a "
                                    "metric without its source and coverage is not "
                                    "evidence"))
        observed = any(str(row.get(column) or "").strip()
                       for column in SNAPSHOT_METRIC_COLUMNS)
        if not observed and not str(row.get("missing_reason") or "").strip():
            issues.append(Issue("CSV_MISSING_REASON_MISSING",
                                f"{path.name} row {index} observes no metric and gives "
                                "no missing_reason; blank is unobserved, and unobserved "
                                "needs a reason"))
        for column in SNAPSHOT_METRIC_COLUMNS:
            issue = _number_issue(path.name, index, column, row.get(column, ""))
            if issue:
                issues.append(issue)
    return issues


def verify_account_table(path: Path) -> List[Issue]:
    """Check the account table: an identity, a source and counted columns."""
    issues: List[Issue] = []
    fields, rows = _read(path)
    header = _header_issue(path.name, fields,
                            _vendor_header("x-account-snapshots.csv") or ACCOUNT_COLUMNS)
    if header:
        return [header]
    for index, row in enumerate(rows, start=2):
        for column in ("snapshot_id", "account_handle", "observed_at",
                       "observation_source", "data_access"):
            if not str(row.get(column) or "").strip():
                issues.append(Issue("CSV_SOURCE_MISSING",
                                    f"{path.name} row {index} has no {column}; an "
                                    "account snapshot must say whose account it is "
                                    "and where the numbers came from"))
        for column in ACCOUNT_COUNT_COLUMNS:
            issue = _number_issue(path.name, index, column, row.get(column, ""))
            if issue:
                issues.append(issue)
    return issues


def verify_tables(project: Path, records: Sequence[str]) -> List[Issue]:
    """Every table in the project, checked against the vendored contract."""
    project = Path(project)
    templates = project / "templates"
    issues: List[Issue] = []
    for name, constant in (("posts.csv", POSTS_COLUMNS),
                           ("x-metric-snapshots.csv", METRIC_COLUMNS),
                           ("x-account-snapshots.csv", ACCOUNT_COLUMNS)):
        vendor = VENDOR_TEMPLATES / name
        if not vendor.is_file():
            issues.append(Issue("VENDOR_TEMPLATE_MISSING",
                                f"{vendor} is not in this tree; the vendored headers "
                                "are the contract and a change needs a new import"))
            continue
        header = _vendor_header(name)
        if header and tuple(header) != tuple(constant):
            issues.append(Issue("VENDOR_CONTRACT_DRIFT",
                                f"the vendored {name} header is {header}; this module "
                                f"expects {list(constant)}"))
    if issues:
        return issues
    issues.extend(verify_posts_table(templates / "posts.csv", records))
    issues.extend(verify_metric_table(templates / "x-metric-snapshots.csv"))
    issues.extend(verify_account_table(templates / "x-account-snapshots.csv"))
    return issues
