#!/usr/bin/env python3
"""Offline audit / draft contract / descriptive performance review for the X copywriting Skill.

No model invocation, network, automatic publication, or platform measurement.
This is intentionally a thin deterministic helper, not a second X post gate.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "skills" / "x-high-engagement-copywriter" / "references" / "sample-ledger.json"
SCHEMA = "contentops.x-copywriter-draft/v1"
EXPECTED_IDS = {f"S{i:02d}" for i in range(1, 12)}
VALID_MODES = {"ORIGINAL_POST", "REPLY_DRAFT", "QUOTE_POST", "THREAD"}
VALID_LANGUAGES = {"en", "zh", "zh-CN"}
VALID_RISK = {"PASS", "REVISE", "HOLD"}
VALID_CLAIM = {"VERIFIED", "OPINION_ONLY", "UNVERIFIED"}
HOOK_KINDS = {"contrast", "story", "question", "sensory", "technical", "fact_check", "punchline", "reflection"}
STATUS_URL = re.compile(r"^https://(?:www\.)?(?:x\.com|twitter\.com)/[^/\s]+/status/\d+(?:\?.*)?$")
CW_EXPERIMENT = re.compile(r"^cw:(P\d{2}):([A-Za-z0-9_-]{1,60})$")


def load_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        raise ValueError("input must be a real JSON file <=1 MiB, not a symlink")
    return json.loads(path.read_text(encoding="utf-8"))


def ledger_errors(data: Any) -> list[str]:
    if not isinstance(data, dict) or data.get("schema") != "contentops.x-copywriter-corpus/v1":
        return ["BAD_CORPUS_SCHEMA"]
    records = data.get("samples")
    patterns = data.get("patterns")
    if not isinstance(records, list) or not isinstance(patterns, dict):
        return ["INVALID_CORPUS_STRUCTURE"]
    ids = [r.get("id") for r in records if isinstance(r, dict)]
    errors = []
    if len(records) != len(EXPECTED_IDS) or set(ids) != EXPECTED_IDS or len(ids) != len(set(ids)):
        errors.append("SOURCE_COVERAGE_MISMATCH")
    if sum(r.get("source_scope") == "current_thread_user_turn" for r in records if isinstance(r, dict)) != 10:
        errors.append("VISIBLE_SOURCE_COUNT_MISMATCH")
    for r in records:
        if not isinstance(r, dict):
            errors.append("INVALID_SAMPLE")
            continue
        sid = r.get("id", "?")
        if (r.get("source_scope") == "prior_turn_summary_only") != (sid == "S11"):
            errors.append(f"{sid}:SUMMARY_SCOPE_MISMATCH")
        if r.get("source_kind") != "USER_PASTED_X_POST" or not r.get("paraphrase"):
            errors.append(f"{sid}:SOURCE_NOT_TRACEABLE")
        if not r.get("pattern_ids") or not all(p in patterns for p in r["pattern_ids"]):
            errors.append(f"{sid}:INVALID_PATTERN")
        if r.get("primary_pattern") not in r.get("pattern_ids", []):
            errors.append(f"{sid}:PRIMARY_PATTERN_MISSING")
        if r.get("observed_metrics") is not None or r.get("verified_performance") is not False:
            errors.append(f"{sid}:UNVERIFIED_METRICS_PRESENT")
        if r.get("x_post_url") is not None:
            errors.append(f"{sid}:UNVERIFIED_URL_PRESENT")
    return errors


def draft_errors(draft: Any, ledger: dict[str, Any]) -> list[str]:
    if not isinstance(draft, dict) or draft.get("schema") != SCHEMA:
        return ["BAD_DRAFT_SCHEMA"]
    errors = []
    def bad(message: str) -> None:
        errors.append(message)

    if draft.get("mode") not in VALID_MODES:
        bad("BAD_MODE")
    lang = draft.get("language")
    if lang not in VALID_LANGUAGES:
        bad("BAD_LANGUAGE")
    account = draft.get("account_slug")
    if not isinstance(account, str) or not account:
        bad("MISSING_ACCOUNT")
    else:
        account_path = ROOT / "config" / "accounts" / (account + ".json")
        if account != "UNCONFIRMED" and account_path.is_file():
            account_info = load_json(account_path)
            allowed = account_info.get("allowed_languages") or [account_info.get("language")]
            normalized = "zh" if lang == "zh-CN" else lang
            if normalized not in allowed:
                bad("ACCOUNT_LANGUAGE_MISMATCH")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", account):
            bad("UNSAFE_ACCOUNT_NAME")
    if draft.get("status") != "DRAFT_REVIEW_REQUIRED":
        bad("NO_MANUAL_REVIEW_BOUNDARY")
    if draft.get("platform_metrics") is not None:
        bad("FABRICATED_PLATFORM_METRICS")
    if any(k in draft for k in ("auto_publish", "publish_url", "guaranteed_views", "execution_authorized")):
        bad("FORBIDDEN_PUBLISH_OR_GUARANTEE_FIELD")
    if not isinstance(draft.get("audience"), str) or not draft["audience"].strip():
        bad("MISSING_AUDIENCE")
    exp = draft.get("experiment")
    if not isinstance(exp, dict) or not exp.get("primary_variable") or not exp.get("age_window"):
        bad("NO_TESTABLE_EXPERIMENT")
    candidates = draft.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 15:
        return errors + ["INVALID_CANDIDATE_COUNT"]
    patterns = ledger["patterns"]
    samples = {r["id"]: r for r in ledger["samples"]}
    copies: set[str] = set()
    hooks: set[str] = set()
    for ix, c in enumerate(candidates, 1):
        prefix = f"C{ix}"
        if not isinstance(c, dict):
            bad(prefix + ":NOT_OBJECT")
            continue
        copy = c.get("copy", "")
        if not isinstance(copy, str) or not copy.strip():
            bad(prefix + ":EMPTY_COPY")
            continue
        normalized = re.sub(r"\s+", "", copy).lower()
        if normalized in copies:
            bad(prefix + ":DUPLICATE_COPY")
        copies.add(normalized)
        if c.get("pattern_id") not in patterns:
            bad(prefix + ":UNKNOWN_PATTERN")
        hook = c.get("hook_kind")
        if hook not in HOOK_KINDS:
            bad(prefix + ":UNKNOWN_HOOK")
        else:
            hooks.add(hook)
        ids = c.get("inspiration_ids")
        if not isinstance(ids, list) or any(sid not in samples for sid in ids):
            bad(prefix + ":UNKNOWN_SOURCE_ID")
        # The negative example must never be the PRIMARY transfer recipe.
        if c.get("pattern_id") == "P03":
            bad(prefix + ":FOLLOW_BAIT_PATTERN")
        claim_state, risk = c.get("claim_state"), c.get("risk")
        if claim_state not in VALID_CLAIM or risk not in VALID_RISK:
            bad(prefix + ":BAD_CLAIM_OR_RISK")
        if claim_state == "UNVERIFIED" and risk == "PASS":
            bad(prefix + ":UNVERIFIED_CLAIM_PASSED")
        if claim_state == "VERIFIED" and not c.get("evidence_refs"):
            bad(prefix + ":VERIFICATION_WITHOUT_EVIDENCE")
        if not isinstance(c.get("novel_angle"), str) or len(c["novel_angle"].strip()) < 8:
            bad(prefix + ":MISSING_NOVEL_ANGLE")
        score = c.get("editorial_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
            bad(prefix + ":INVALID_EDITORIAL_SCORE")
        # This is only a warning heuristic; substantive fact checking is human work.
        if re.search(r"(?i)(follow\s*me.*follow\s*back|回复.{0,8}(保送|必得)\d+粉|guaranteed \d+k followers)", copy):
            bad(prefix + ":TRANSACTIONAL_FOLLOW_BAIT")
    if len(candidates) >= 5 and len(hooks) < 3:
        bad("BATCH_REPEATS_HOOK_SHAPE")
    return errors


def _project_root(raw: str) -> Path:
    p = Path(raw).resolve()
    base = (ROOT / "projects").resolve()
    if p.parent != base or not p.is_dir():
        raise ValueError("review accepts only a direct projects/<slug> directory")
    return p


def _int_metric(raw: str) -> int | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        result = int(raw)
    except ValueError:
        return None
    return result if result >= 0 else None


def review(project: Path, age_window: str) -> dict[str, Any]:
    """Use ONLY the existing posts and metric snapshot CSVs; never mutate them."""
    posts_path = project / "templates" / "posts.csv"
    metrics_path = project / "templates" / "x-metric-snapshots.csv"
    if any(not p.is_file() or p.is_symlink() for p in (posts_path, metrics_path)):
        raise ValueError("existing X post/metric CSV tables are required")
    with posts_path.open(encoding="utf-8-sig", newline="") as f:
        posts = list(csv.DictReader(f))
    with metrics_path.open(encoding="utf-8-sig", newline="") as f:
        metrics = list(csv.DictReader(f))
    cohorts: dict[str, list[dict[str, Any]]] = {}
    missing: dict[str, int] = {}
    for p in posts:
        match = CW_EXPERIMENT.fullmatch(p.get("experiment_variable") or "")
        if not match:
            continue
        pattern, variant = match.groups()
        key = f"{pattern}:{variant}"
        url = p.get("x_post_url") or ""
        post_id = p.get("content_id") or ""
        if not STATUS_URL.fullmatch(url):
            missing[key] = missing.get(key, 0) + 1
            continue
        rows = [m for m in metrics if m.get("content_id") == post_id
                and m.get("x_post_url") == url and m.get("age_window") == age_window
                and m.get("metric_source") and m.get("observed_at")]
        rows.sort(key=lambda m: m.get("observed_at") or "")
        if not rows:
            missing[key] = missing.get(key, 0) + 1
            continue
        last = rows[-1]
        impressions, replies = _int_metric(last.get("impressions")), _int_metric(last.get("replies"))
        if impressions is None or impressions == 0 or replies is None:
            missing[key] = missing.get(key, 0) + 1
            continue
        cohorts.setdefault(key, []).append({
            "post_id": post_id, "impressions": impressions,
            "replies": replies, "reply_rate": replies / impressions,
            "metric_source": last["metric_source"],
        })
    results = []
    for key in sorted(set(cohorts) | set(missing)):
        items = cohorts.get(key, [])
        results.append({
            "pattern_variant": key, "measured_posts": len(items),
            "missing_or_invalid": missing.get(key, 0),
            "median_impressions": statistics.median([x["impressions"] for x in items]) if items else None,
            "median_reply_rate": statistics.median([x["reply_rate"] for x in items]) if items else None,
            "verdict": "DESCRIPTIVE_ONLY" if len(items) >= 3 else "INSUFFICIENT_DATA",
        })
    return {
        "schema": "contentops.x-copywriter-review/v1", "age_window": age_window,
        "status": "NO_OBSERVED_POSTS" if not results else "DESCRIPTIVE_ONLY",
        "groups": results, "causal_inference": False, "recommends_auto_publish": False,
        "note": "No correlation or algorithm proof. Same-age comparisons only; actual source accuracy must be audited by the operator. Zero views is not a missing observation.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--corpus", action="store_true", help="check source ledger coverage and provenance")
    group.add_argument("--check", metavar="DRAFT_JSON", help="validate an agent-produced draft contract")
    group.add_argument("--review", metavar="PROJECT", help="read existing X CSV metrics, descriptively")
    ap.add_argument("--age-window", default="T+24h", help="exact existing metric age_window key")
    args = ap.parse_args()
    try:
        ledger = load_json(LEDGER)
        errors = ledger_errors(ledger)
        payload: dict[str, Any] = {"status": "PASS" if not errors else "FAIL", "errors": errors}
        if args.check and not errors:
            path = Path(args.check).resolve()
            if not (path.is_relative_to(ROOT / "tests" / "fixtures")
                    or path.is_relative_to(ROOT / "projects")):
                raise ValueError("draft JSON must be under tests/fixtures or projects")
            errors = draft_errors(load_json(path), ledger)
            payload = {"status": "PASS" if not errors else "FAIL",
                       "errors": errors, "editorial_approval": False,
                       "publication_authorized": False}
        if args.review and not errors:
            payload = review(_project_root(args.review), args.age_window)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        payload = {"status": "FAIL", "errors": [f"INVALID_INPUT: {exc}"]}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if payload.get("status") == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
