#!/usr/bin/env python3
"""Evaluate prospective editorial rankings using existing native video metrics."""
import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import editorial_ops as ops
import editorial_diagnostics as diag
import platform_learning_loop as learning

SCHEMA = "contentops.editorial-score-review/v1"
MIN_PAIRS = 10


def encoded(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False)


def digest(obj):
    return hashlib.sha256(encoded(obj).encode()).hexdigest()


def record_path(directory, kind, ident):
    ops.slug(ident)
    return ops.safe_file(directory, f"score-{kind}-{ident}.json")


def load(directory, kind, ident):
    path = record_path(directory, kind, ident)
    if path.stat().st_size > 100_000:
        raise ValueError("oversized score record")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("candidate_id") != ident:
        raise ValueError("invalid score record")
    checksum = value.pop("record_sha256", None)
    if digest(value) != checksum:
        raise ValueError("score record digest mismatch")
    return value


def write_once(directory, kind, ident, value):
    path = record_path(directory, kind, ident)
    if path.exists():
        if load(directory, kind, ident) != value:
            raise ValueError("immutable record already exists")
        return
    ops.write_atomic(directory, path.name, encoded({**value, "record_sha256": digest(value)}) + "\n")


def now():
    return datetime.now(timezone.utc).isoformat()


def freeze(directory, candidate_id, reviewer, confirmed):
    if not confirmed or not reviewer.strip():
        raise ValueError("explicit human confirmation required")
    directory = ops.local_dir(directory)
    path = record_path(directory, "freeze", candidate_id)
    if path.exists():
        return load(directory, "freeze", candidate_id)
    plan = ops.plan(directory)
    selected = [q for q in plan["queue"] if q["id"] == candidate_id]
    if len(selected) != 1:
        raise ValueError("select one existing candidate")
    q = selected[0]
    if q["format"] != "video" or q["decision"] not in {"CANDIDATE", "LOW_COST_VALIDATION"}:
        raise ValueError("only eligible video candidates in this initial scope")
    value = {"schema": SCHEMA, "candidate_id": candidate_id, "frozen_at": now(),
             "account": q["account"], "platform": q["platform"], "topic": q["topic"],
             "format": q["format"], "score": q["score"],
             "components": {k: int(q[k]) for k in ops.WEIGHTS},
             "weights": dict(plan["weights"]), "candidate_sha256": digest(q),
             "reviewer": reviewer, "publish_authorized": False}
    write_once(directory, "freeze", candidate_id, value)
    return value


def index_rows(metrics):
    metrics = Path(metrics)
    learning._local_guard(metrics)
    path = metrics / "content-index.csv"
    if path.is_symlink():
        raise ValueError("symlink index refused")
    return learning._load(path, learning.INDEX_COLUMNS)


def match_post(rows, frozen, content_id, url):
    matches = [r for r in rows if r["content_id"] == content_id or r["post_url"] == url]
    if len(matches) != 1:
        raise ValueError("missing or duplicate publication identity")
    p = matches[0]
    if (p["content_id"], p["post_url"]) != (content_id, url) or not learning._url(url):
        raise ValueError("publication identity mismatch")
    if (p["account_alias"], p["platform"], p["topic_cluster"], p["content_format"]) != (
            frozen["account"], frozen["platform"], frozen["topic"], frozen["format"]):
        raise ValueError("publication outside frozen scope")
    stamp, earlier = learning._date(p["published_at"]), learning._date(frozen["frozen_at"])
    if (p["publish_status"] not in learning.VALID_STATUS or not stamp or not earlier
            or not earlier < stamp or stamp > datetime.now(timezone.utc)):
        raise ValueError("requires prospective freeze and actual reported publication")
    return p


def all_records(directory, kind):
    directory = ops.local_dir(directory)
    for path in sorted(directory.glob(f"score-{kind}-*.json")):
        ident = path.stem[len(f"score-{kind}-"):]
        yield load(directory, kind, ident)


def link(directory, metrics, candidate_id, content_id, post_url, reviewer, confirmed):
    if not confirmed or not reviewer.strip() or not content_id.strip():
        raise ValueError("explicit human publication binding required")
    frozen = load(directory, "freeze", candidate_id)
    p = match_post(index_rows(metrics), frozen, content_id, post_url)
    for old in all_records(directory, "link"):
        if old["candidate_id"] == candidate_id:
            if (old["content_id"], old["post_url"], old["experiment"]) == (
                    content_id, post_url, p["experiment_id"]) and old["freeze_sha256"] == digest(frozen):
                return old
            raise ValueError("candidate already bound")
        if old["content_id"] == content_id or old["post_url"] == post_url:
            raise ValueError("publication already bound to another candidate")
    value = {"schema": SCHEMA, "candidate_id": candidate_id,
             "content_id": content_id, "post_url": post_url,
             "experiment": p["experiment_id"], "published_at": p["published_at"],
             "freeze_sha256": digest(frozen), "reviewer": reviewer,
             "linked_at": now(), "publish_authorized": False}
    write_once(directory, "link", candidate_id, value)
    return value


def ranks(values):
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(order)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        for k in order[i:j]:
            result[k] = (i + 1 + j) / 2
        i = j
    return result


def spearman(xs, ys):
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x, y = ranks(xs), ranks(ys)
    mean = (len(x) + 1) / 2
    dx, dy = [v - mean for v in x], [v - mean for v in y]
    denom = math.sqrt(sum(v*v for v in dx) * sum(v*v for v in dy))
    return max(-1.0, min(1.0, sum(a*b for a,b in zip(dx,dy)) / denom)) if denom else None


def review(directory, metrics, *, platform, account, topic, experiment, window, definition, metric):
    if metric not in diag.METRICS:
        raise ValueError("choose one native diagnostic metric")
    result = diag.diagnostics(metrics, platform=platform, account=account,
                              content_format="video", topic=topic, window=window,
                              definition=definition, experiment=experiment)
    observations = {(w["content_id"], w["post_url"]): w for w in result["works"]}
    posts = index_rows(metrics)
    frozen = {f["candidate_id"]: f for f in all_records(directory, "freeze")
              if (f["account"], f["platform"], f["topic"], f["format"]) ==
                 (account, platform, topic, "video")}
    links = list(all_records(directory, "link"))
    ids = Counter(l["content_id"] for l in links)
    urls = Counter(l["post_url"] for l in links)
    skipped = Counter()
    pairs = []
    for ident, f in frozen.items():
        linked = [l for l in links if l["candidate_id"] == ident]
        if len(linked) != 1:
            skipped["no_publication_binding"] += 1
            continue
        l = linked[0]
        if l["experiment"] != experiment:
            skipped["other_experiment"] += 1
            continue
        if ids[l["content_id"]] != 1 or urls[l["post_url"]] != 1 or l["freeze_sha256"] != digest(f):
            raise ValueError("duplicate or changed score linkage")
        p = match_post(posts, f, l["content_id"], l["post_url"])
        if (p["experiment_id"], p["published_at"]) != (experiment, l["published_at"]):
            raise ValueError("publication index changed since binding")
        # Weight changes make historical scores incomparable: never recompute them.
        if f["weights"] != ops.WEIGHTS:
            skipped["different_score_weights"] += 1
            continue
        w = observations.get((l["content_id"], l["post_url"]))
        outcome = w["metrics"].get(metric) if w else None
        if outcome is None:
            skipped["missing_or_ineligible_metric"] += 1
            continue
        pairs.append({"candidate_id": ident, "content_id": l["content_id"],
                      "score": f["score"], "outcome": outcome})
    rho = spearman([p["score"] for p in pairs], [p["outcome"] for p in pairs]) if len(pairs) >= MIN_PAIRS else None
    status = ("INSUFFICIENT_DATA" if len(pairs) < MIN_PAIRS else
              "NO_VARIATION" if rho is None else "DESCRIPTIVE_ONLY")
    return {"schema": SCHEMA, "status": status, "scope": result["scope"],
            "metric": metric, "sample_count": len(pairs), "frozen_count": len(frozen),
            "minimum_pairs": MIN_PAIRS, "spearman": rho, "skipped": dict(skipped),
            "native_skipped": result["skipped"], "metrics_sha256": result["input_sha256"],
            "records_sha256": digest({"frozen": frozen, "links": links}),
            "pairs": pairs, "weights_updated": False, "publish_authorized": False,
            "limits": ["Only published linked candidates; selection bias remains.",
                       "Ten pairs are a pilot threshold, not statistical significance.",
                       "Local operator timestamps and native exports are not independent verification.",
                       "Ordinal scores are not predicted probabilities. Association is not causal."]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ("freeze", "link"):
        q = sub.add_parser(cmd)
        q.add_argument("--candidate-id", required=True)
        q.add_argument("--reviewer", required=True)
        q.add_argument("--confirm", action="store_true")
        if cmd == "link":
            q.add_argument("--content-id", required=True)
            q.add_argument("--post-url", required=True)
    q = sub.add_parser("review")
    for name in ("platform", "account", "topic", "experiment", "window", "definition"):
        q.add_argument("--" + name, required=True)
    q.add_argument("--metric", choices=sorted(diag.METRICS), required=True)
    a = vars(p.parse_args())
    directory, metrics, cmd = a.pop("data_dir"), a.pop("metrics_dir"), a.pop("command")
    try:
        if cmd == "review":
            value = review(directory, metrics, **a)
        else:
            a["confirmed"] = a.pop("confirm")
            value = freeze(directory, **a) if cmd == "freeze" else link(directory, metrics, **a)
        print(json.dumps(value, ensure_ascii=True, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(1, "score review refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
