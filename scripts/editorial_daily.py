#!/usr/bin/env python3
"""Daily capacity and draft editorial review over the existing local planner."""
import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import editorial_ops as ops

RUBRIC = {
    "audience_value": "One identifiable audience and a specific useful outcome",
    "hook": "Opening immediately earns attention without exaggerating",
    "title_cover": "Title and cover (where applicable) accurately express the benefit",
    "structure": "Every section earns its place; no avoidable filler",
    "originality": "Adds a distinct perspective, example or useful explanation",
    "clarity": "Target reader can understand the result and limitations",
    "cta": "Next step is relevant, honest and proportionate",
}
SCHEMA = "contentops.editorial-draft-review/v1"
DEMAND_KINDS = {"search", "comment", "issue", "job", "buyer_request", "review"}


def capacity(directory, plan, signals, day, minutes):
    if type(minutes) is not int or not 1 <= minutes <= 1440:
        raise ValueError("daily minutes must be between 1 and 1440")
    day = date.fromisoformat(day)
    directory = ops.local_dir(directory)
    selected, deferred = [], []
    left = minutes
    for q in plan["queue"]:  # preserve planner rank; not an optimal-knapsack claim
        ident = q["id"]
        if len(ident) != 16 or any(c not in "0123456789abcdef" for c in ident):
            raise ValueError("invalid candidate identity")
        due = date.fromisoformat(q["planned_date"])
        estimate = int(q["minutes"])
        if estimate <= 0:
            raise ValueError("invalid planned minutes")
        if ops.safe_file(directory, "route-" + ident + ".json").exists():
            reason = "ALREADY_ROUTED"
        elif due > day:
            reason = "FUTURE"
        elif q["decision"] not in {"CANDIDATE", "LOW_COST_VALIDATION"}:
            reason = q["decision"]
        elif estimate > left:
            reason = "CAPACITY"
        else:
            refs = [s for s in signals if s["signal_id"] in q["evidence_ids"]]
            demand = {s["source_url"] for s in refs if s["kind"] in DEMAND_KINDS}
            buyer = {s["source_url"] for s in refs if s["kind"] == "buyer_request"}
            selected.append({
                "candidate_id": ident, "account": q["account"], "topic": q["topic"],
                "platform": q["platform"], "format": q["format"],
                "cost_lane": q["cost_lane"], "estimated_minutes": estimate,
                "score": q["score"], "overdue": due < day,
                "demand_signal_urls": len(demand), "reported_buyer_request_urls": len(buyer),
                "next_action": "HUMAN_SELECT_AND_EXISTING_ROUTER",
            })
            left -= estimate
            continue
        deferred.append({"candidate_id": ident, "reason": reason})
    return {"schema": "contentops.editorial-capacity/v1", "day": day.isoformat(),
            "budget_minutes": minutes, "allocated_minutes": minutes-left,
            "remaining_minutes": left, "selected": selected, "deferred": deferred,
            "limits": "Estimates only; URL counts are not independent demand or verified buyers.",
            "production_ready": False, "publish_authorized": False}


def candidate(plan, ident):
    found = [q for q in plan["queue"] if q["id"] == ident]
    if len(found) != 1:
        raise ValueError("candidate not found or ambiguous")
    return found[0]


def draft_binding(directory, plan, ident, draft):
    q = candidate(plan, ident)
    path = ops.safe_file(directory, draft)
    if path.suffix.lower() not in {".md", ".txt"} or not path.is_file():
        raise ValueError("provide a local draft .md or .txt file")
    if not 0 < path.stat().st_size <= 2_000_000:
        raise ValueError("empty or oversized draft")
    raw = path.read_bytes()
    if not raw.decode("utf-8").strip():
        raise ValueError("blank draft")
    if draft in ops.FIELDS:
        raise ValueError("invalid draft input")
    canonical = json.dumps(q, sort_keys=True, ensure_ascii=False).encode()
    return {"candidate_id": ident, "draft_file": path.name,
            "candidate_sha256": hashlib.sha256(canonical).hexdigest(),
            "draft_sha256": hashlib.sha256(raw).hexdigest()}


def template(directory, plan, ident, draft):
    return {"schema": SCHEMA, "binding": draft_binding(directory, plan, ident, draft),
            "reviewer": None, "checks": {k: {"question": v, "result": None, "note": ""}
                                         for k, v in RUBRIC.items()},
            "production_ready": False, "publish_authorized": False}


def review(directory, plan, ident, draft, record):
    current = template(directory, plan, ident, draft)
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ValueError("wrong review schema")
    if record.get("binding") != current["binding"]:
        raise ValueError("STALE: draft or candidate changed")
    if record.get("production_ready") is not False or record.get("publish_authorized") is not False:
        raise ValueError("editorial review cannot authorize")
    reviewer = record.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 100:
        raise ValueError("named human reviewer required")
    checks = record.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(RUBRIC):
        raise ValueError("review every rubric dimension")
    changes = []
    for key, value in checks.items():
        if not isinstance(value, dict) or value.get("question") != RUBRIC[key]:
            raise ValueError("invalid rubric dimension: " + key)
        if value.get("result") not in {"SATISFIED", "REVISE"}:
            raise ValueError("record an explicit result for " + key)
        note = value.get("note")
        if not isinstance(note, str) or not note.strip() or len(note) > 1000:
            raise ValueError("record a concrete review note for " + key)
        if value["result"] == "REVISE":
            changes.append(key)
    return {"schema": SCHEMA, "binding": current["binding"],
            "status": "REVISIONS_SUGGESTED" if changes else "REVIEW_RECORDED",
            "reviewer": reviewer, "revise_dimensions": changes,
            "review_origin": "LOCAL_SELF_ATTESTED",
            "production_ready": False, "publish_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--day", required=True)
    p.add_argument("--minutes", type=int, required=True)
    for cmd in ("rubric", "review"):
        p = sub.add_parser(cmd)
        p.add_argument("--candidate", required=True)
        p.add_argument("--draft", required=True)
        if cmd == "review":
            p.add_argument("--record", required=True)
            p.add_argument("--confirm", action="store_true")
    a = parser.parse_args()
    try:
        plan = ops.plan(a.data_dir)
        if a.command == "plan":
            result = capacity(a.data_dir, plan, ops.load(a.data_dir, "signals.csv"),
                              a.day, a.minutes)
        elif a.command == "rubric":
            result = template(a.data_dir, plan, a.candidate, a.draft)
        else:
            if not a.confirm:
                raise ValueError("explicit human confirmation required")
            path = ops.safe_file(a.data_dir, a.record)
            if path.suffix != ".json" or path.stat().st_size > 100_000:
                raise ValueError("invalid review record")
            result = review(a.data_dir, plan, a.candidate, a.draft,
                            json.loads(path.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (OSError, ValueError) as exc:
        parser.exit(1, "editorial daily refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
