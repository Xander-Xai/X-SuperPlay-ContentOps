#!/usr/bin/env python3
"""Read-only lifecycle view of operator-linked content, not a new approval system."""
import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import editorial_ops as ops
import platform_learning_loop as learning

sys.path.insert(0, str(ops.ROOT / "src"))
from contentops.workflow import (WorkflowError, load_workflow, reconcile,
                                 current_stage, artifact_path, CONTRACT_ID,
                                 GRAPHIC_CONTRACT_ID)

FIELDS = ("candidate_id", "project_slug", "content_id", "post_url", "definition")
MAX_JSON = 2_000_000


def initialize(directory):
    directory = ops.init(directory)
    path = ops.safe_file(directory, "lifecycle-links.csv")
    if not path.exists():
        with path.open("x", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerow(FIELDS)


def links(directory, candidates):
    path = ops.safe_file(directory, "lifecycle-links.csv")
    if not path.exists():
        return {}
    if path.stat().st_size > 5_000_000:
        raise ValueError("lifecycle links too large")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("invalid lifecycle link columns")
        rows = list(reader)
    result, publications, projects = {}, set(), set()
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("malformed lifecycle link")
        ident = row["candidate_id"]
        if ident not in candidates or ident in result:
            raise ValueError("unknown or duplicate candidate link")
        slug = row["project_slug"]
        if slug:
            ops.slug(slug)
            if slug in projects:
                raise ValueError("project already linked; one candidate per project in pilot")
            projects.add(slug)
        key = (row["content_id"], row["post_url"])
        if any(key) or row["definition"]:
            if not all(key) or not learning._url(key[1]):
                raise ValueError("publication link needs content ID and HTTPS URL")
            ops.slug(row["definition"])
            if key in publications:
                raise ValueError("publication already linked")
            publications.add(key)
        if not slug and not any(key):
            raise ValueError("empty lifecycle link")
        result[ident] = row
    return result


def route(directory, ident):
    path = ops.safe_file(directory, "route-" + ident + ".json")
    if not path.exists():
        return "NOT_ROUTED"
    if path.stat().st_size > MAX_JSON:
        return "INVALID_ROUTE_RECEIPT"
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
        if (not isinstance(row, dict) or row.get("schema") != "contentops.editorial-route/v1"
                or row.get("candidate_id") != ident or row.get("production_ready") is not False
                or row.get("publish_authorized") is not False):
            return "INVALID_ROUTE_RECEIPT"
        state = row.get("status")
        if state == "ROUTED_FOR_HUMAN_REVIEW" and not row.get("router_run_id"):
            return "INVALID_ROUTE_RECEIPT"
        return state if state in {"ROUTED_FOR_HUMAN_REVIEW", "EXECUTION_PENDING",
                                  "ROUTE_BLOCKED", "RECONCILIATION_REQUIRED"} else "INVALID_ROUTE_RECEIPT"
    except (ValueError, OSError):
        return "INVALID_ROUTE_RECEIPT"


def project_status(root, slug, q):
    if not slug:
        return {"state": "NOT_LINKED"}
    root = Path(root).resolve()
    project = root / slug
    try:
        if project.is_symlink() or project.resolve().parent != root or not project.is_dir():
            return {"state": "PROJECT_UNAVAILABLE"}
        file = project / "workflow.json"
        if file.is_symlink() or not file.is_file() or file.stat().st_size > MAX_JSON:
            return {"state": "WORKFLOW_UNAVAILABLE"}
        doc = load_workflow(file)
        expected = CONTRACT_ID if q["format"] == "video" else GRAPHIC_CONTRACT_ID
        if (doc["slug"] != slug or doc["account"] != q["account"]
                or doc["contract"] != expected):
            return {"state": "WORKFLOW_SCOPE_MISMATCH"}
        # Reconcile in memory only. Existing gate fingerprints, not status
        # strings, decide whether a stage approval is still current.
        for stage in doc["stages"]:
            if stage["status"] == "approved":
                p = artifact_path(project, doc, stage["id"])
                if p.is_file() and p.stat().st_size > 100_000_000:
                    return {"state": "WORKFLOW_ARTIFACT_TOO_LARGE"}
        reconcile(project, doc)
        stage = current_stage(doc)
        return {"state": "WORKFLOW_REVIEW_REQUIRED" if stage else "WORKFLOW_RECORDED_COMPLETE",
                "current_stage": stage, "stages": [{"id": s["id"], "status": s["status"],
                                                    "stale": s["stale"]} for s in doc["stages"]]}
    except (WorkflowError, ValueError, OSError, KeyError, TypeError):
        return {"state": "WORKFLOW_INVALID"}


def publication(q, link, index, snapshots, as_of):
    key = (link["content_id"], link["post_url"])
    if not all(key):
        return {"state": "NOT_LINKED", "windows": {}}
    matching = [r for r in index if (r["content_id"], r["post_url"]) == key]
    if len(matching) != 1:
        return {"state": "INDEX_MISSING_OR_AMBIGUOUS", "windows": {}}
    p = matching[0]
    published = learning._date(p["published_at"])
    if ((p["account_alias"], p["platform"], p["content_format"], p["topic_cluster"]) !=
            (q["account"], q["platform"], q["format"], q["topic"]) or
            not published or published > as_of or p["publish_status"] not in learning.VALID_STATUS):
        return {"state": "INDEX_SCOPE_OR_STATUS_MISMATCH", "windows": {}}
    age = (as_of-published).total_seconds()/3600
    windows = {}
    for window, (low, high) in learning.WINDOW_HOURS.items():
        rows = [s for s in snapshots if (s["content_id"], s["post_url"], s["platform"],
                s["account_alias"], s["content_format"], s["experiment_id"], s["window"],
                s["metric_definition_version"]) ==
                (*key, p["platform"], p["account_alias"], p["content_format"],
                 p["experiment_id"], window, link["definition"])]
        if len(rows) > 1:
            state = "AMBIGUOUS_SNAPSHOT"
        elif rows:
            s = rows[0]
            stamp = learning._date(s["observed_at"])
            if (not stamp or stamp > as_of or learning._date(s["published_at"]) != published
                    or not low <= (stamp-published).total_seconds()/3600 <= high):
                state = "INVALID_SNAPSHOT"
            elif (s["data_access"] in {"available", "partial"}
                  and s["organic_paid"] == "organic"
                  and s["metric_source"] in {"native_manual", "native_export", "official_api"}
                  and any(learning._metric(s.get(m, "")) is not None for m in learning.METRICS)):
                state = "ORGANIC_OBSERVATION_RECORDED"
            elif s["data_access"] in {"available", "partial"}:
                state = "OBSERVATION_ONLY"
            else:
                state = "DATA_UNAVAILABLE"
        else:
            state = "NOT_DUE" if age < low else "DUE" if age <= high else "WINDOW_MISSED"
        windows[window] = state
    return {"state": "LOCAL_PUBLICATION_RECORDED", "post_url": key[1],
            "reported_status": p["publish_status"], "windows": windows}


def report(directory, plan, metrics, projects, as_of):
    stamp = learning._date(as_of)
    if stamp is None:
        raise ValueError("timezone-aware as-of required")
    candidates = {q["id"]: q for q in plan["queue"]}
    mapped = links(directory, candidates)
    metrics = ops.local_dir(metrics)
    ix = learning._load(ops.safe_file(metrics, "content-index.csv"), learning.INDEX_COLUMNS)
    ms = learning._load(ops.safe_file(metrics, "metric-snapshots.csv"), learning.SNAPSHOT_COLUMNS)
    result = []
    for ident, q in candidates.items():
        link = mapped.get(ident, dict(project_slug="", content_id="", post_url="", definition=""))
        result.append({"candidate_id": ident, "route": route(directory, ident),
                       "project": project_status(projects, link["project_slug"], q),
                       "publication": publication(q, link, ix, ms, stamp),
                       "link_origin": "OPERATOR_LOCAL_MAPPING" if ident in mapped else "NONE"})
    return {"schema": "contentops.editorial-lifecycle/v1", "as_of": stamp.isoformat(),
            "items": result, "publication_counts": dict(Counter(x["publication"]["state"] for x in result)),
            "limitations": "Operator links are not independent provenance. Workflow records are not media quality "
                           "or publish authorization. Local publication is not live platform verification. "
                           "Observation availability is not growth or causal evidence.",
            "production_ready": False, "publish_authorized": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("init", "status"))
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    p.add_argument("--projects-dir", type=Path, default=ops.ROOT / "projects")
    p.add_argument("--as-of")
    a = p.parse_args()
    try:
        if a.command == "init":
            initialize(a.data_dir)
            print("READY: lifecycle-links.csv")
        else:
            stamp = a.as_of or datetime.now(timezone.utc).isoformat()
            print(json.dumps(report(a.data_dir, ops.plan(a.data_dir), a.metrics_dir,
                                    a.projects_dir, stamp), ensure_ascii=True, indent=2))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        p.exit(4, "BLOCKED: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
