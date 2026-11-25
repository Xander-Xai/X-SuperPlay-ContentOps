#!/usr/bin/env python3
"""Bounded video editorial experiments; DNA stays immutable."""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import editorial_ops as ops
import editorial_feedback as feedback
import platform_learning_loop as learning

# Start with expression-only parameters. Rendering, cadence, duration, rights,
# account scope and all other production policies are deliberately not editable.
VARIABLES = {"hook", "title", "cta"}
SCHEMA = "contentops.bounded-editorial-experiment/v1"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def dna_hash(account, platform):
    ops.account_allows(account, platform)
    if platform not in {"bilibili", "douyin"}:
        raise ValueError("video pilot only; X retains its dedicated language-cohort workflow")
    path = ops.ROOT / "config" / "accounts" / (ops.slug(account) + ".json")
    raw = path.read_bytes()
    dna = json.loads(raw)
    if dna.get("schema") == "contentops.x-account/v1":
        raise ValueError("not a video account")
    return digest(raw)


def text(value, maximum):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum and not any(ord(c) < 32 for c in value)


def create(directory, *, experiment, account, platform, topic, variable,
           a, b, hypothesis, start, end, reviewer, confirmed,
           window="T+24H", definition="native_v1", primary="views_or_reads", interest="saves", today=None):
    if not confirmed or not feedback.named_reviewer(reviewer):
        raise ValueError("named planning reviewer and confirmation required")
    for v in (experiment, account, platform, topic, definition):
        ops.slug(v)
    if variable not in VARIABLES:
        raise ValueError("only expression variables hook/title/cta allowed")
    if not all(text(v, 500) for v in (a, b, hypothesis)) or a.strip() == b.strip():
        raise ValueError("two distinct expressions and hypothesis required")
    begin, finish = date.fromisoformat(start), date.fromisoformat(end)
    now = today or datetime.now(timezone.utc).date()
    if begin < now or not 1 <= (finish - begin).days + 1 <= 28:
        raise ValueError("preregister before start; maximum 28 calendar days (UTC)")
    if window not in learning.WINDOW_HOURS or primary not in learning.METRICS or interest not in learning.RATE_METRICS or primary == interest:
        raise ValueError("invalid predeclared metric cohort")
    fingerprint = dna_hash(account, platform)
    directory = ops.init(directory)
    record = {"schema": SCHEMA, "status": "PLANNED_NOT_AUTHORIZED", "experiment_id": experiment,
              "account": account, "platform": platform, "format": "video", "topic": topic, "variable": variable,
              "arms": {"a": a, "b": b}, "hypothesis": hypothesis, "start_utc": start, "end_utc": end,
              "window": window, "definition": definition, "primary": primary, "interest": interest,
              "reviewer": reviewer, "dna_sha256": fingerprint, "minimum_valid_per_arm": 5,
              "publish_authorized": False, "dna_changed": False}
    path = ops.safe_file(directory, "experiment-" + experiment + ".json")
    with path.open("x", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return record


def review(directory, metrics, *, experiment, reviewer, confirmed):
    if not confirmed or not feedback.named_reviewer(reviewer):
        raise ValueError("named review and confirmation required")
    directory, metrics = ops.local_dir(directory), ops.local_dir(metrics)
    ops.slug(experiment)
    raw, plan = feedback.read_local_json(ops.safe_file(directory, "experiment-" + experiment + ".json"))
    if (not isinstance(plan, dict) or plan.get("schema") != SCHEMA or plan.get("experiment_id") != experiment
            or plan.get("status") != "PLANNED_NOT_AUTHORIZED" or plan.get("publish_authorized") is not False
            or plan.get("dna_changed") is not False or plan.get("variable") not in VARIABLES or plan.get("format") != "video"):
        raise ValueError("invalid local experiment plan")
    if dna_hash(plan["account"], plan["platform"]) != plan["dna_sha256"]:
        raise ValueError("account DNA changed; plan stale")
    begin, end = date.fromisoformat(plan["start_utc"]), date.fromisoformat(plan["end_utc"])
    if not 1 <= (end - begin).days + 1 <= 28:
        raise ValueError("invalid plan period")
    mapping = feedback.read_links(directory, experiment, plan["variable"])
    index_path = ops.safe_file(metrics, "content-index.csv")
    snapshot_path = ops.safe_file(metrics, "metric-snapshots.csv")
    records = learning._load(index_path, learning.INDEX_COLUMNS)
    for key in mapping:
        matches = [r for r in records if (r["content_id"], r["post_url"]) == key]
        if len(matches) != 1:
            raise ValueError("assignment must match one actual publication record")
        row = matches[0]
        published = learning._date(row["published_at"])
        if (row["platform"], row["account_alias"], row["content_format"], row["topic_cluster"], row["experiment_id"]) != (plan["platform"], plan["account"], "video", plan["topic"], experiment):
            raise ValueError("assignment outside plan cohort")
        if (row["publish_status"] not in learning.VALID_STATUS or not published
                or not begin <= published.astimezone(timezone.utc).date() <= end):
            raise ValueError("assignment outside publication period")
    before = digest(index_path.read_bytes() + snapshot_path.read_bytes())
    result = feedback.review(directory, metrics, experiment=experiment, variable=plan["variable"],
                             platform=plan["platform"], account=plan["account"], content_format="video",
                             topic=plan["topic"], window=plan["window"], definition=plan["definition"],
                             primary=plan["primary"], interest=plan["interest"])
    if result["input_sha256"] != before or before != digest(index_path.read_bytes() + snapshot_path.read_bytes()):
        raise ValueError("metrics changed during review")
    if dna_hash(plan["account"], plan["platform"]) != plan["dna_sha256"] or ops.safe_file(directory, "experiment-" + experiment + ".json").read_bytes() != raw:
        raise ValueError("DNA or plan changed during review")
    groups = {g["variant"]: g for g in result["groups"]}
    eligible = result["status"] == "DESCRIPTIVE_ONLY" and set(groups) == {"a", "b"}
    priority = None
    if eligible:
        av, bv = (groups[k]["median_interest_per_1000_post"] for k in ("a", "b"))
        if av != bv:
            priority = "a" if av > bv else "b"
    report = {"schema": "contentops.bounded-experiment-review/v1", "experiment_id": experiment,
              "status": result["status"], "plan_sha256": digest(raw), "dna_sha256": plan["dna_sha256"],
              "input_sha256": before, "assignment_sha256": result["assignment_sha256"],
              "reviewer": reviewer, "observed_priority": priority, "groups": result["groups"],
              "next_action": "FOUNDER_STRATEGY_REVIEW_REQUIRED", "dna_changed": False,
              "publish_authorized": False, "finding": "Observational, not randomized or causal; no automatic policy update."}
    ops.write_atomic(directory, "experiment-" + experiment + "-review.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("plan", "review"))
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    p.add_argument("--experiment", required=True)
    for name in ("account", "platform", "topic", "variable", "a", "b", "hypothesis", "start", "end"):
        p.add_argument("--" + name)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--confirm", action="store_true")
    p.add_argument("--window", default="T+24H")
    p.add_argument("--definition", default="native_v1")
    p.add_argument("--primary", default="views_or_reads")
    p.add_argument("--interest", default="saves")
    args = p.parse_args(argv)
    try:
        if args.command == "plan":
            if not all(getattr(args, n) for n in ("account", "platform", "topic", "variable", "a", "b", "hypothesis", "start", "end")):
                raise ValueError("plan requires scope, two arms, hypothesis and UTC period")
            report = create(args.data_dir, **{n: getattr(args, n) for n in ("experiment", "account", "platform", "topic", "variable", "a", "b", "hypothesis", "start", "end", "reviewer", "window", "definition", "primary", "interest")}, confirmed=args.confirm)
        else:
            report = review(args.data_dir, args.metrics_dir, experiment=args.experiment, reviewer=args.reviewer, confirmed=args.confirm)
        print(report["status"])
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
