"""WeChat Official Account statistics, read through the official data cube.

Why this module exists
----------------------
The registry marks ``wechat_article`` ``metrics: NONE`` and the operator had
no in-repo way to read account numbers at all: the manual export path
(``contentops.manual_metrics``) expects a human to walk the admin UI, and the
browser bridge is a publishing channel, not a measurement one. WeChat ships an
official statistics API (the *data cube*) and the vendored ``wechatpy`` already
wraps it — this module is the repository-side half of that channel: date-range
rules, credential preflight and the receipt.

Transport-free by construction
------------------------------
This module never imports ``wechatpy``, never opens a socket, never reads a
credential *value*. ``scripts/wechat_metrics.py`` owns those, lazily, only
under ``--execute``.

The one thing this cannot settle offline
----------------------------------------
The data cube sits behind the same access_token gate as everything else on
the MP platform, and the token request is refused with ``40164`` when the
caller's IP is not on the account's whitelist. ``preflight`` therefore reports
``ip_whitelist: "UNKNOWN"`` and only a real token fetch can settle it — the
same honesty rule the draft channel already follows.

What a receipt may and may not claim
------------------------------------
A receipt records the counters the API returned for the requested range. A
day the API has not aggregated yet is missing, not zero. ``modifies_script``,
``modifies_qc`` and ``modifies_production_ready`` are always false:
post-publication evidence informs the next round, it never edits the artefact.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "CREDENTIAL_KEYS",
    "DATA_CUBE_ENDPOINTS",
    "MAX_USER_SUMMARY_DAYS",
    "RECEIPT_SCHEMA",
    "build_receipt",
    "normalise_metric_rows",
    "preflight",
    "validate_range",
]

RECEIPT_SCHEMA = "contentops.wechat-metrics/v1"

#: The slot naming this repository already uses for the first account — the
#: same keys the draft channel reads, because it is the same appid.
CREDENTIAL_KEYS = ("WECHAT_1_APPID", "WECHAT_1_APPSECRET")

#: Documented endpoints (basis: official MP docs) so a reviewer can see what
#: the transport will call without reading it.
DATA_CUBE_ENDPOINTS = {
    "token": "GET  /cgi-bin/token?grant_type=client_credential",
    "user_summary": "POST /datacube/getusersummary (max span 7 days)",
    "article_summary": "POST /datacube/getarticlesummary (max span 1 day)",
    "article_total": "POST /datacube/getarticletotal (single day)",
}

#: Official range ceilings, recorded as the contract they are.
MAX_USER_SUMMARY_DAYS = 7
MAX_ARTICLE_SUMMARY_DAYS = 1

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_PLACEHOLDER = re.compile(r"(your|xxx|changeme|placeholder|todo|<.*>)", re.IGNORECASE)


def _parse_day(value: str) -> Optional[date]:
    text = str(value or "").strip()
    if not _DATE.match(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def validate_range(begin: str, end: str, span_days: int) -> List[str]:
    """Every date-range problem at once, named — never just the first one."""
    problems: List[str] = []
    begin_day = _parse_day(begin)
    end_day = _parse_day(end)
    if begin_day is None:
        problems.append(f"begin_date is not YYYY-MM-DD: {begin!r}")
    if end_day is None:
        problems.append(f"end_date is not YYYY-MM-DD: {end!r}")
    if begin_day is None or end_day is None:
        return problems
    if begin_day > end_day:
        problems.append(f"begin_date {begin} is after end_date {end}")
        return problems
    span = (end_day - begin_day).days + 1
    if span > span_days:
        problems.append(
            f"span is {span} days, the official ceiling for this endpoint is {span_days}"
        )
    if end_day > date.today():
        problems.append(f"end_date {end} is in the future; the cube has not aggregated it")
    return problems


def preflight(env: Dict[str, str]) -> Dict[str, Any]:
    """Credential shape only. Lengths and digests, never values."""
    result: Dict[str, Any] = {
        "credentials": {},
        "ip_whitelist": "UNKNOWN",
        "ip_whitelist_note": "only a real token fetch settles 40164; no offline check exists",
    }
    for key in CREDENTIAL_KEYS:
        value = str(env.get(key) or "").strip()
        entry: Dict[str, Any] = {"present": bool(value)}
        if value:
            entry["length"] = len(value)
            entry["looks_like_placeholder"] = bool(_PLACEHOLDER.search(value)) or value.lower() in {
                "changeme",
                "your_appid",
                "your_appsecret",
            }
        result["credentials"][key] = entry
    missing = [key for key, entry in result["credentials"].items() if not entry["present"]]
    placeholder = [
        key for key, entry in result["credentials"].items() if entry.get("looks_like_placeholder")
    ]
    result["ok"] = not missing and not placeholder
    if missing:
        result["problems"] = [f"missing credential {key}" for key in missing]
    if placeholder:
        result.setdefault("problems", []).extend(
            [f"{key} looks like a placeholder" for key in placeholder]
        )
    return result


def normalise_metric_rows(rows: Any, day_fields: Tuple[str, ...] = ("int_page_read_count", "cumulate_user")) -> Dict[str, Any]:
    """Keep the counters the API actually returned; name the ones it did not.

    The cube returns per-day rows whose field names differ per endpoint. This
    helper sums the numeric fields that are present across rows and reports
    which of the expected ones never appeared — expected-but-absent stays a
    fact, never a zero.
    """
    problems: List[str] = []
    if not isinstance(rows, list):
        problems.append("cube response rows are not a list")
        return {"metrics": {}, "problems": problems}
    totals: Dict[str, int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            problems.append(f"row {index} is not an object")
            continue
        for key, value in row.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                continue
            totals[key] = totals.get(key, 0) + value
    missing_expected = [field for field in day_fields if field not in totals]
    return {"metrics": totals, "problems": problems, "fields_absent": missing_expected}


def build_receipt(
    account_slug: str,
    begin_date: str,
    end_date: str,
    endpoints: List[str],
    data: Dict[str, Any],
    fetched_at: str,
    problems: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """The receipt: which endpoint over which days, and what it must not touch."""
    receipt: Dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "platform": "wechat_article",
        "channel": "api_official",
        "account_slug": str(account_slug or ""),
        "begin_date": begin_date,
        "end_date": end_date,
        "endpoints": list(endpoints),
        "fetched_at": fetched_at,
        "data": data,
        "upstream": {
            "project": "wechatpy/wechatpy (vendored)",
            "license": "MIT",
            "note": "official data cube; no scraping, no login session replay",
        },
        "modifies_script": False,
        "modifies_qc": False,
        "modifies_production_ready": False,
    }
    if problems:
        receipt["issues"] = list(problems)
    return receipt
