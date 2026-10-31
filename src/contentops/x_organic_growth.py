"""Offline, advisory helpers for X organic-growth planning.

This module neither connects to X nor approves or executes a platform action.
"""
from __future__ import annotations

import math
import re
from statistics import mean
from urllib.parse import urlsplit

from contentops.x_growth_engagement import brief
from contentops.x_growth_contract import ContractError, map_draft_to_x_post
from contentops.x_growth_metrics import build_weekly_report

_DIMENSIONS = ("topic_relevance", "audience_fit", "incremental_value", "evidence_quality",
               "discussion_potential", "duplication_risk", "compliance_risk")
_EXPERIMENTS = {"ORIGINAL_VS_QUOTE", "MORNING_VS_EVENING", "HOOK_STYLE", "TOPIC_CLUSTER",
                "POST_FREQUENCY", "CONTENT_FORMAT", "ENGAGEMENT_QUALITY"}
_SENSITIVE = re.compile(r"(?i)(api[_-]?key|access[_-]?token|password|secret|cookie|private[_-]?message|bearer\s+|github_pat_|ghp_|\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b)")
_ACCOUNT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_INJECTION = re.compile(
    r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions"
    r"|disregard\s+(all\s+)?(previous|prior)\s+instructions"
    r"|system\s+prompt|<\|?system\|?>|忽略.{0,8}(指令|规则))"
)
_MAX_DEPTH = 32


def _injection(value, depth=0):
    if depth > _MAX_DEPTH:
        return True
    if isinstance(value, dict):
        return any(_injection(v, depth + 1) for v in value.values())
    if isinstance(value, list):
        return any(_injection(v, depth + 1) for v in value)
    return isinstance(value, str) and bool(_INJECTION.search(value))


def _unsafe(value, depth=0):
    if depth > _MAX_DEPTH:
        return True
    if isinstance(value, dict):
        return any(_SENSITIVE.search(str(k)) or _unsafe(v, depth + 1) for k, v in value.items())
    if isinstance(value, list):
        return any(_unsafe(v, depth + 1) for v in value)
    return isinstance(value, str) and bool(_SENSITIVE.search(value))


def _url(value):
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
        return parts.scheme == "https" and bool(parts.hostname) and not parts.username and not parts.password
    except ValueError:
        return False


def _result(status, *reasons, **data):
    return {"schema": "contentops.x-organic-growth/v1", "status": status,
            "reasons": list(reasons), "network_used": False, "external_action": "none",
            "execution_authorized": False, "requires_human_review": True, **data}


def _accounts_match(value, account):
    if isinstance(value, dict):
        for field in ("account_id", "account_handle"):
            if field in value and value[field] != account:
                return False
        return all(_accounts_match(v, account) for v in value.values())
    if isinstance(value, list):
        return all(_accounts_match(v, account) for v in value)
    return True


def process(request):
    """Process untrusted local data; never treat a reference as verified evidence."""
    if not isinstance(request, dict):
        return _result("BLOCKED", "INVALID_REQUEST")
    if _unsafe(request):
        return _result("BLOCKED", "SENSITIVE_INPUT")
    if _injection(request):
        return _result("BLOCKED", "UNTRUSTED_INSTRUCTION")
    if request.get("privacy") != "public":
        return _result("BLOCKED", "PUBLIC_INPUT_CONFIRMATION_REQUIRED")
    if request.get("fixture") is True and request.get("data_origin") == "observed":
        return _result("BLOCKED", "FIXTURE_ORIGIN_MISMATCH")
    account = request.get("account_id")
    if not isinstance(account, str) or not _ACCOUNT.fullmatch(account) or not request.get("language"):
        return _result("BLOCKED", "ACCOUNT_CONTEXT_REQUIRED")
    if not _accounts_match(request, account):
        return _result("BLOCKED", "ACCOUNT_MISMATCH")
    operation = request.get("operation")
    if not isinstance(operation, str):
        return _result("BLOCKED", "UNKNOWN_OPERATION")
    if operation in {"auto_publish", "auto_reply", "auto_like", "auto_follow", "auto_dm"}:
        return _result("BLOCKED", "AUTOMATED_ACTION_NOT_AVAILABLE")
    if operation == "publication":
        return _result("BLOCKED", "PUBLICATION_UNVERIFIED")
    if operation == "reply_check":
        drafts = request.get("drafts", [])
        if not isinstance(drafts, list) or not all(isinstance(d, str) and d.strip() for d in drafts):
            return _result("BLOCKED", "INVALID_DRAFTS")
        normalized = [" ".join(d.casefold().split()) for d in drafts]
        if len(set(normalized)) != len(normalized):
            return _result("BLOCKED", "DUPLICATE_REPLY")
        return _result("REVIEW_REQUIRED", drafts=drafts)
    if operation == "x_contract":
        try:
            draft = map_draft_to_x_post(request.get("draft"))
        except ContractError:
            return _result("BLOCKED", "INVALID_X_CONTRACT")
        return _result("REVIEW_REQUIRED", draft=draft, integration="BLOCKED_UPSTREAM",
                       contract_completeness="PARTIAL_CONTRACT")
    if operation == "engagement":
        candidate = request.get("candidate", {})
        if not isinstance(candidate, dict) or not _url(candidate.get("source_url")):
            return _result("BLOCKED", "MISSING_SOURCE_URL")
        writing_brief = brief(candidate)
        return _result(writing_brief["status"], *([writing_brief["reason"]] if "reason" in writing_brief else []), brief=writing_brief)
    if operation == "discover":
        candidates = request.get("candidates", [])
        if not isinstance(candidates, list):
            return _result("BLOCKED", "INVALID_CANDIDATES")
        if not candidates:
            return _result("DATA_UNAVAILABLE", "NO_CANDIDATES")
        if any(not isinstance(c, dict) or not _url(c.get("source_url")) for c in candidates):
            return _result("BLOCKED", "MISSING_SOURCE_URL")
        if any(c.get("source_access") == "NOT_FOUND" for c in candidates):
            return _result("BLOCKED", "SOURCE_NOT_FOUND")
        ranked = []
        for item in candidates:
            scores = item.get("scores", {})
            if not isinstance(scores, dict) or any(
                    isinstance(scores.get(k), bool) or type(scores.get(k)) not in (int, float)
                    or not math.isfinite(scores[k]) or not 0 <= scores[k] <= 5 for k in _DIMENSIONS):
                return _result("BLOCKED", "MISSING_OR_INVALID_SCORES")
            score = sum(scores[k] for k in _DIMENSIONS[:5]) - sum(scores[k] for k in _DIMENSIONS[5:])
            ranked.append({"candidate": item, "score": score, "source_verification": "UNVERIFIED_REFERENCE"})
        ranked.sort(key=lambda x: -x["score"])
        return _result("REVIEW_REQUIRED", candidates=ranked, scoring="user-supplied subjective judgments")
    if operation == "plan":
        if not _url(request.get("source_url")):
            return _result("BLOCKED", "MISSING_SOURCE_URL")
        return _result("REVIEW_REQUIRED", content=request.get("content", {}),
                       source_url=request["source_url"], source_verification="UNVERIFIED_REFERENCE",
                       editorial_gate="NOT_AVAILABLE_ON_MAIN")
    if operation == "metrics":
        records = request.get("records", [])
        if not isinstance(records, list):
            return _result("BLOCKED", "INVALID_RECORDS")
        if any(not isinstance(r, dict) or not r.get("observed_at") or not (r.get("metric_source") or r.get("observation_source")) for r in records):
            return _result("BLOCKED", "INVALID_OBSERVATION")
        return _result("REVIEW_REQUIRED" if records else "INSUFFICIENT_DATA", records=records,
                       note="Missing values are unknown; account changes are not attributed to individual posts.")
    if operation == "weekly":
        if not request.get("week_start"):
            return _result("INSUFFICIENT_DATA", "NO_OBSERVATIONS")
        return build_weekly_report(request)
    if operation == "experiment":
        records = request.get("records", [])
        if not records:
            return _result("INSUFFICIENT_DATA", "NO_OBSERVATIONS")
        if request.get("experiment_type") not in _EXPERIMENTS:
            return _result("BLOCKED", "INVALID_EXPERIMENT_TYPE")
        if not isinstance(records, list) or any(not isinstance(r, dict) for r in records):
            return _result("BLOCKED", "INVALID_RECORDS")
        groups = {}
        metrics = set()
        for r in records:
            value = r.get("value")
            if value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or not r.get("group") or not r.get("metric") or not r.get("age_window") or not r.get("observed_at") or not r.get("source"):
                return _result("BLOCKED", "INVALID_OBSERVATION")
            metrics.add(r["metric"])
            groups.setdefault((r["group"], r["age_window"]), []).append(value)
        if len(metrics) > 1:
            return _result("BLOCKED", "INCOMPARABLE_METRICS")
        windows = {window for _, window in groups}
        if len(groups) != 2 or len(windows) != 1 or any(len(v) < 2 for v in groups.values()):
            return _result("INSUFFICIENT_DATA", "COMPARABLE_OBSERVATIONS_REQUIRED")
        summary = [{"group": group, "age_window": window, "n": len(values), "mean": mean(values)}
                   for (group, window), values in sorted(groups.items())]
        if any(len(values) < 5 for values in groups.values()):
            return _result("INSUFFICIENT_DATA", "SMALL_SAMPLE", groups=summary,
                           note="Five observations per group is an operational minimum, not a statistical guarantee.")
        return _result("REVIEW_REQUIRED", groups=summary,
                       note="Descriptive comparison only; small samples and confounding prevent causal claims.")
    return _result("BLOCKED", "UNKNOWN_OPERATION")
