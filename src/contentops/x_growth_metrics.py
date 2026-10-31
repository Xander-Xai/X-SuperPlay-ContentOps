"""Offline X metrics and weekly review; all observations remain advisory."""
from __future__ import annotations

import csv
import io
import math
import re
from datetime import date, datetime, timezone
from urllib.parse import urlsplit

_SCHEMA = "contentops.x-growth-metrics/v1"
_STATUS_URL = re.compile(r"^https://(?:x|twitter)\.com/[^/\s]+/status/\d+(?:[?#].*)?$")


def _status_url(value):
    """Syntax only. A matching URL is not proof of publication or ownership."""
    if not isinstance(value, str) or not _STATUS_URL.fullmatch(value):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return not parts.username and not parts.password


def _result(status, *reasons, **values):
    return {"schema": _SCHEMA, "status": status, "reasons": list(reasons),
            "network_used": False, "external_action": "none",
            "execution_authorized": False, "requires_human_review": True, **values}


def _rows(value, field):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        try:
            reader = csv.DictReader(io.StringIO(value))
            required = {
                "posts_csv": {"content_id", "mode", "status", "account_handle", "x_post_url", "post_published_at"},
                "metric_snapshots_csv": {"content_id", "observed_at", "metric_source", "age_window", "impressions", "engagements", "qualified_signal_count"},
                "account_snapshots_csv": {"account_handle", "observed_at", "observation_source", "followers_count"},
            }[field]
            if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
                raise ValueError("INVALID_CSV")
            return list(reader)
        except (csv.Error, UnicodeError):
            raise ValueError("INVALID_CSV") from None
    if isinstance(value, list) and all(isinstance(row, dict) for row in value):
        return value
    raise ValueError("INVALID_CSV")


def _timestamp(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("INVALID_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        raise ValueError("INVALID_TIMESTAMP") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("INVALID_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def _number(value, *, integer=False):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("INVALID_METRIC")
    try:
        number = int(value) if integer else float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("INVALID_METRIC") from None
    if isinstance(number, bool) or not math.isfinite(number) or number < 0 or (integer and str(number) != str(value).strip()):
        raise ValueError("INVALID_METRIC")
    return number


def _in_week(value, start, end):
    parsed = _timestamp(value)
    if not (start <= parsed.date() <= end):
        raise ValueError("TIMESTAMP_OUT_OF_RANGE")
    return parsed


def _validate_account(rows, account, *, required=True):
    for row in rows:
        row_account = row.get("account_id") or row.get("account_handle")
        if (required and not row_account) or (row_account is not None and row_account != account):
            raise ValueError("ACCOUNT_MISMATCH")


def _comparison(records, start, end):
    if records is None:
        return None
    if not isinstance(records, list) or any(not isinstance(row, dict) for row in records):
        raise ValueError("INVALID_COMPARISON")
    groups = {}
    metrics, windows = set(), set()
    for row in records:
        value = _number(row.get("value"))
        if value is None or not row.get("source"):
            raise ValueError("INVALID_OBSERVATION")
        _in_week(row.get("observed_at"), start, end)
        group, metric, window = row.get("group"), row.get("metric"), row.get("age_window")
        if not group or not metric or not window:
            raise ValueError("INVALID_OBSERVATION")
        groups.setdefault(group, []).append(value)
        metrics.add(metric)
        windows.add(window)
    if not records:
        return {"status": "INSUFFICIENT_DATA", "interpretation": "No comparison observations; no conclusion."}
    if len(groups) != 2 or len(metrics) != 1 or len(windows) != 1:
        raise ValueError("INCOMPARABLE_OBSERVATIONS")
    summaries = {group: {"n": len(values), "mean": sum(values) / len(values)} for group, values in sorted(groups.items())}
    sufficient = all(len(values) >= 5 for values in groups.values())
    return {"status": "REVIEW_REQUIRED" if sufficient else "INSUFFICIENT_DATA", "groups": summaries,
            "metric": next(iter(metrics)), "age_window": next(iter(windows)),
            "interpretation": "Descriptive observational comparison only; association is not causation. Five per group is an operational minimum, not statistical proof."}


def build_weekly_report(request):
    """Build a sourced, account-scoped weekly review from PR #50 CSV-shaped data.

    CSV arguments are `posts_csv`, `metric_snapshots_csv`, and
    `account_snapshots_csv`; each also accepts a list of row dictionaries.
    Manual interaction and work records require account_id, timestamp/date, and
    source. `fixture` must explicitly be True or False. This is an internal
    helper: the caller must classify privacy and filter secrets/private content
    before calling it. This function does not independently validate privacy or
    filter private content.
    """
    if not isinstance(request, dict):
        return _result("BLOCKED", "INVALID_REQUEST")
    if type(request.get("fixture")) is not bool:
        return _result("BLOCKED", "FIXTURE_FLAG_REQUIRED")
    if request["fixture"] is True and str(request.get("data_origin", "")).strip().casefold() == "observed":
        return _result("BLOCKED", "FIXTURE_OBSERVED_CONFLICT")
    account = request.get("account_id")
    try:
        start = date.fromisoformat(request.get("week_start", ""))
        end = date.fromisoformat(request.get("week_end", ""))
        if end < start:
            raise ValueError("INVALID_DATE_RANGE")
        posts = _rows(request.get("posts_csv"), "posts_csv")
        metrics = _rows(request.get("metric_snapshots_csv"), "metric_snapshots_csv")
        accounts = _rows(request.get("account_snapshots_csv"), "account_snapshots_csv")
        _validate_account(posts, account)
        # PR #50 metric snapshots lack an account column; they are scoped by content_id
        # and checked against the account-bound posts table before inclusion.
        _validate_account(metrics, account, required=False)
        _validate_account(accounts, account)
        if not isinstance(account, str) or not account.strip():
            raise ValueError("ACCOUNT_CONTEXT_REQUIRED")
        if not isinstance(request.get("next_experiment"), str) or not request["next_experiment"].strip() or not isinstance(request.get("stop_condition"), str) or not request["stop_condition"].strip():
            raise ValueError("WEEKLY_DECISION_REQUIRED")
        for row in posts:
            if row.get("status") == "published":
                published = row.get("post_published_at") or row.get("date_local")
                _in_week(published, start, end)
                if not _status_url(row.get("x_post_url")):
                    raise ValueError("INVALID_POST_SOURCE")
        seen_ids = [post.get("content_id") for post in posts]
        if len(seen_ids) != len(set(seen_ids)):
            raise ValueError("INVALID_POST_SOURCE")
        post_by_id = {post.get("content_id"): post for post in posts if post.get("account_handle") == account}
        all_post_ids = {post.get("content_id") for post in posts}
        for row in metrics:
            if not row.get("metric_source"):
                raise ValueError("INVALID_OBSERVATION")
            post = post_by_id.get(row.get("content_id"))
            if post is None:
                if row.get("content_id") in all_post_ids:
                    raise ValueError("ACCOUNT_MISMATCH")
                raise ValueError("INVALID_POST_SOURCE")
            if not row.get("x_post_url") or row.get("x_post_url") != post.get("x_post_url"):
                raise ValueError("INVALID_POST_SOURCE")
            published = _timestamp(row.get("post_published_at"))
            observed = _in_week(row.get("observed_at"), start, end)
            if observed < published:
                raise ValueError("INVALID_TIMESTAMP")
        for row in accounts:
            if not row.get("observation_source"):
                raise ValueError("INVALID_OBSERVATION")
            _in_week(row.get("observed_at"), start, end)
        interactions = request.get("manual_interactions", [])
        work = request.get("work_minutes", [])
        if not isinstance(interactions, list) or not isinstance(work, list):
            raise ValueError("INVALID_MANUAL_RECORD")
        for row in interactions:
            if not isinstance(row, dict) or row.get("account_id") != account or not row.get("source") or not row.get("kind"):
                raise ValueError("INVALID_MANUAL_RECORD")
            _in_week(row.get("occurred_at"), start, end)
        minutes = 0
        for row in work:
            if not isinstance(row, dict) or row.get("account_id") != account or not row.get("source"):
                raise ValueError("INVALID_MANUAL_RECORD")
            try:
                day = date.fromisoformat(row.get("date", ""))
            except ValueError:
                raise ValueError("INVALID_MANUAL_RECORD") from None
            if not start <= day <= end:
                raise ValueError("TIMESTAMP_OUT_OF_RANGE")
            value = _number(row.get("minutes"), integer=True)
            if value is None:
                raise ValueError("INVALID_MANUAL_RECORD")
            minutes += value
        comparison = _comparison(request.get("comparison"), start, end)
        originals = [row for row in posts if row.get("status") == "published" and row.get("mode", "").casefold() not in {"reply", "reply_draft"}]
        post_by_id = {row.get("content_id"): row for row in originals}
        # Keep every metric and age window in its own bucket; snapshots are cumulative.
        performance = {}
        latest_qualified = {}
        for row in metrics:
            content_id = row.get("content_id")
            if content_id not in post_by_id:
                continue
            age_window = row.get("age_window")
            observed = _timestamp(row.get("observed_at"))
            key = (content_id, age_window)
            qualified = _number(row.get("qualified_signal_count"), integer=True)
            previous = latest_qualified.get(key)
            if qualified is not None and (previous is None or observed > previous[0]):
                latest_qualified[key] = (observed, qualified)
            values = {"engagements": _number(row.get("engagements")),
                      "impressions": _number(row.get("impressions")),
                      "likes": _number(row.get("likes")),
                      "reposts": _number(row.get("reposts")),
                      "replies": _number(row.get("replies")),
                      "bookmarks": _number(row.get("bookmarks"))}
            for metric_name, value in values.items():
                if value is None:
                    continue
                metric_key = (age_window, metric_name)
                bucket = performance.setdefault(metric_key, {})
                prior = bucket.get(content_id)
                if prior is None or observed > prior[0]:
                    bucket[content_id] = (observed, value)
        top_content = None
        if performance:
            top_content = {}
            for (age_window, metric_name), observations in sorted(performance.items()):
                ranked = sorted(({"content_id": cid, "value": record[1], "source": "x-metric-snapshots.csv"}
                                 for cid, record in observations.items()), key=lambda item: (-item["value"], item["content_id"]))
                top_content.setdefault(age_window, {"metrics": {}})["metrics"][metric_name] = ranked[:3]
        inbound_qualified = None
        if latest_qualified:
            inbound_qualified = {}
            for (content_id, age_window), (_, value) in latest_qualified.items():
                inbound_qualified[age_window] = inbound_qualified.get(age_window, 0) + value
        followers = sorted(accounts, key=lambda row: _timestamp(row["observed_at"]))
        follower_net = None
        if len(followers) >= 2:
            before, after = _number(followers[0].get("followers_count"), integer=True), _number(followers[-1].get("followers_count"), integer=True)
            if before is not None and after is not None:
                follower_net = after - before
        outbound_manual_replies = sum(1 for row in interactions if row.get("kind", "").casefold() == "reply")
        qualified_manual_replies = sum(1 for row in interactions if row.get("kind", "").casefold() == "reply" and row.get("qualified") is True)
        if not originals and request.get("posts_coverage_complete") is not True:
            original_post_count = None
        else:
            original_post_count = len(originals)
        if not interactions and request.get("interactions_coverage_complete") is not True:
            manual_reply_count = None
            outbound_manual_replies = None
        else:
            manual_reply_count = outbound_manual_replies
        limitations = []
        if not metrics:
            limitations.append("METRICS_UNAVAILABLE")
        if len(followers) < 2 or follower_net is None:
            limitations.append("FOLLOWER_SNAPSHOTS_INSUFFICIENT")
        if not interactions and request.get("interactions_coverage_complete") is not True:
            limitations.append("MANUAL_INTERACTIONS_UNRECORDED")
        if not work:
            limitations.append("WORK_MINUTES_UNRECORDED")
        if original_post_count is None:
            limitations.append("POST_COVERAGE_UNCONFIRMED")
        if comparison and comparison.get("status") == "INSUFFICIENT_DATA":
            limitations.append("COMPARISON_INSUFFICIENT")
        report = {
            "account_id": account, "week_start": start.isoformat(), "week_end": end.isoformat(),
            "data_kind": "FIXTURE" if request["fixture"] else "USER_SUPPLIED_UNVERIFIED",
            "original_post_count": original_post_count, "publication_evidence": "USER_REPORTED_UNVERIFIED" if originals else None,
            "manual_reply_count": manual_reply_count, "outbound_manual_reply_count": outbound_manual_replies,
            "qualified_manual_reply_count": qualified_manual_replies if interactions else None,
            "inbound_qualified_responses": inbound_qualified, "follower_net": follower_net,
            "follower_net_source": "x-account-snapshots.csv" if follower_net is not None else None,
            "work_hours": round(minutes / 60, 2) if work else None,
            "feedback": request.get("feedback") if request.get("feedback") else None,
            "top_content": top_content, "failures": request.get("failures") or [],
            "comparison": comparison, "next_experiment": request.get("next_experiment") or None,
            "stop_condition": request.get("stop_condition") or None, "limitations": limitations,
        }
        return _result("REVIEW_REQUIRED" if not limitations else "INSUFFICIENT_DATA", report=report,
                       note="Descriptive records only. Account follower changes are not attributed to individual posts; review sources and next steps manually.")
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        known = {"ACCOUNT_MISMATCH", "INVALID_TIMESTAMP", "TIMESTAMP_OUT_OF_RANGE", "INVALID_METRIC", "INVALID_POST_SOURCE", "INVALID_OBSERVATION", "INVALID_MANUAL_RECORD", "INVALID_DATE_RANGE", "INCOMPARABLE_OBSERVATIONS", "INVALID_COMPARISON", "ACCOUNT_CONTEXT_REQUIRED", "INVALID_CSV", "WEEKLY_DECISION_REQUIRED"}
        return _result("BLOCKED", str(exc) if isinstance(exc, ValueError) and str(exc) in known else "INVALID_DATA")
