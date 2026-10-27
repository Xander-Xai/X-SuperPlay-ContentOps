"""The optimization layer: signals -> score -> decision -> experiment -> ship.

This module is deliberately small and stdlib-only. It does not produce video and
it is not a second production system. It turns three kinds of input into a ranked
backlog that ContentOps can execute:

- external signals: X posts, GitHub repositories
- human signals: Founder review, viewer feedback
- machine signals: production receipts, platform metrics

The policy enforces the repository's non-negotiables: no adoption without a
linkable source and evidence, no GPU-dependent capability in the main workflow,
and no second production system.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config" / "optimization"

POLICY_PATH = CONFIG / "policy.json"
SIGNALS_PATH = CONFIG / "signals.json"
BACKLOG_PATH = CONFIG / "backlog.json"
FLYWHEEL_PATH = CONFIG / "flywheel.json"
EVALUATED_PATH = CONFIG / "backlog-evaluated.json"

SOURCES = {"X", "GITHUB", "FOUNDER", "VIEWER", "PRODUCTION", "PLATFORM_METRIC"}
DECISION_ORDER = {"ADOPT": 0, "EXTEND": 1, "BUILD": 2, "DEFER": 3, "REJECT": 4}
#: Actionable decisions share one group and are ranked by priority; deferrals
#: and rejects follow. A BUILD with priority 8 must outrank an EXTEND with 6.
ACTION_GROUP = {"ADOPT": 0, "EXTEND": 0, "BUILD": 0, "DEFER": 1, "REJECT": 2}
SCORE_FIELDS = ("impact", "evidence", "effort", "risk")


class OptimizationError(RuntimeError):
    """A signal, candidate or cycle is malformed or violates policy."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise OptimizationError("FILE_MISSING", f"{path} does not exist")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OptimizationError("INVALID_JSON", f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise OptimizationError("INVALID_SHAPE", f"{path} must contain an object")
    return payload


def load_policy() -> Dict[str, Any]:
    return load_json(POLICY_PATH)


def load_signals() -> Dict[str, Any]:
    return load_json(SIGNALS_PATH)


def load_backlog() -> Dict[str, Any]:
    return load_json(BACKLOG_PATH)


def load_flywheel() -> Dict[str, Any]:
    return load_json(FLYWHEEL_PATH)


def _require(payload: Dict[str, Any], fields: Tuple[str, ...], kind: str) -> None:
    missing = [field for field in fields if field not in payload]
    if missing:
        raise OptimizationError(
            "MISSING_FIELD", f"{kind} {payload.get('id', '?')} lacks {missing}"
        )


def validate_signal(signal: Dict[str, Any]) -> None:
    _require(
        signal,
        ("id", "source", "captured_at", "title", "observation",
         "affected_stage", "evidence"),
        "signal",
    )
    if signal["source"] not in SOURCES:
        raise OptimizationError(
            "UNKNOWN_SOURCE", f"{signal['id']} source {signal['source']!r}"
        )
    if not isinstance(signal["evidence"], list) or not signal["evidence"]:
        raise OptimizationError(
            "NO_EVIDENCE", f"{signal['id']} must carry at least one evidence reference"
        )
    if not isinstance(signal.get("metrics", {}), dict):
        raise OptimizationError("BAD_METRICS", f"{signal['id']} metrics must be an object")


def validate_candidate(candidate: Dict[str, Any], policy: Dict[str, Any]) -> None:
    _require(
        candidate,
        ("id", "signal_ids", "capability", "affected_stage", "impact", "evidence",
         "effort", "risk", "gpu_required", "decision", "reason", "next_action"),
        "candidate",
    )
    decisions = policy.get("decisions") or list(DECISION_ORDER)
    if candidate["decision"] not in decisions:
        raise OptimizationError(
            "UNKNOWN_DECISION",
            f"{candidate['id']} decision {candidate['decision']!r} not in {decisions}",
        )
    for field in SCORE_FIELDS:
        value = candidate[field]
        if not isinstance(value, int) or not 1 <= value <= 5:
            raise OptimizationError(
                "BAD_SCORE", f"{candidate['id']} {field}={value!r} must be 1..5"
            )
    if not isinstance(candidate["gpu_required"], bool):
        raise OptimizationError(
            "BAD_GPU_FLAG", f"{candidate['id']} gpu_required must be boolean"
        )
    if not isinstance(candidate["signal_ids"], list) or not candidate["signal_ids"]:
        raise OptimizationError(
            "NO_SIGNAL", f"{candidate['id']} must reference at least one signal"
        )


def score_candidate(candidate: Dict[str, Any], policy: Dict[str, Any]) -> int:
    weights = policy["weights"]
    return int(sum(weights[field] * candidate[field] for field in SCORE_FIELDS))


def evaluate_candidate(candidate: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    """Return the declared decision plus the policy-effective decision.

    A declared ADOPT is downgraded to DEFER when it lacks a GitHub source, has
    evidence below the floor, or requires a GPU. The downgrade is recorded rather
    than hidden: the backlog must show what was proposed and what policy allows.
    """
    validate_candidate(candidate, policy)
    decision = candidate["decision"]
    reasons: List[str] = []
    if decision == "ADOPT":
        if policy.get("require_github_for_adopt", True) and not candidate.get("repo"):
            reasons.append("ADOPT requires a linkable GitHub repository")
        if candidate["evidence"] < policy.get("min_evidence_score", 2):
            reasons.append(
                f"evidence {candidate['evidence']} is below the floor "
                f"{policy.get('min_evidence_score', 2)}"
            )
        if policy.get("forbid_gpu_adopt", True) and candidate["gpu_required"]:
            reasons.append("ADOPT forbids GPU-dependent capability in the main workflow")
        if reasons:
            decision = "DEFER"
    evaluated = dict(candidate)
    evaluated["priority"] = score_candidate(candidate, policy)
    evaluated["effective_decision"] = decision
    evaluated["downgraded"] = decision != candidate["decision"]
    evaluated["downgrade_reasons"] = reasons
    return evaluated


def rank_backlog(backlog: Dict[str, Any], policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates = backlog.get("candidates") or []
    if not candidates:
        raise OptimizationError("EMPTY_BACKLOG", "backlog has no candidates")
    evaluated = [evaluate_candidate(candidate, policy) for candidate in candidates]
    evaluated.sort(
        key=lambda item: (
            ACTION_GROUP[item["effective_decision"]],
            -item["priority"],
            DECISION_ORDER[item["effective_decision"]],
            item["id"],
        )
    )
    return evaluated


def build_report(
    policy: Dict[str, Any],
    signals: Dict[str, Any],
    backlog: Dict[str, Any],
    flywheel: Dict[str, Any],
) -> Dict[str, Any]:
    for signal in signals.get("signals") or []:
        validate_signal(signal)
    signal_ids = {signal["id"] for signal in signals.get("signals") or []}
    for candidate in backlog.get("candidates") or []:
        missing = [sid for sid in candidate.get("signal_ids", []) if sid not in signal_ids]
        if missing:
            raise OptimizationError(
                "UNKNOWN_SIGNAL", f"{candidate.get('id')} references {missing}"
            )
    ranked = rank_backlog(backlog, policy)
    counts: Dict[str, int] = {}
    for item in ranked:
        counts[item["effective_decision"]] = counts.get(item["effective_decision"], 0) + 1
    blocked = [
        entry for entry in flywheel.get("entries") or []
        if entry.get("status") == "BLOCKED"
    ]
    return {
        "schema": "contentops.optimization-report/v1",
        "cycle": backlog.get("cycle"),
        "signal_count": len(signals.get("signals") or []),
        "candidate_count": len(ranked),
        "decision_counts": counts,
        "flywheel_stage": flywheel.get("stage"),
        "blocked_stages": [
            {"stage": entry.get("stage"), "reason": entry.get("reason")}
            for entry in blocked
        ],
        "ranked": ranked,
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        f"# Optimization cycle {report['cycle']}",
        "",
        f"- signals: {report['signal_count']}",
        f"- candidates: {report['candidate_count']}",
        f"- decisions: {report['decision_counts']}",
        f"- flywheel stage: {report['flywheel_stage']}",
        "",
        "| # | id | capability | repo | priority | declared | effective | next action |",
        "|---:|---|---|---|---:|---|---|---|",
    ]
    for index, item in enumerate(report["ranked"], 1):
        effective = item["effective_decision"]
        if item.get("downgraded"):
            effective += " ↓"
        lines.append(
            f"| {index} | {item['id']} | {item['capability']} | "
            f"{item.get('repo') or '—'} | {item['priority']} | "
            f"{item['decision']} | {effective} | {item['next_action']} |"
        )
    if report["blocked_stages"]:
        lines += ["", "## Blocked", ""]
        for entry in report["blocked_stages"]:
            lines.append(f"- **{entry['stage']}**: {entry['reason']}")
    return "\n".join(lines) + "\n"
