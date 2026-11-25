#!/usr/bin/env python3
"""Local editorial experiments and consented, review-only OPC signal export."""
import argparse
import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import editorial_ops as ops
import platform_learning_loop as learning

VARIABLES = {"hook", "title", "cover", "cta", "duration", "visual_style", "posting_time"}
LINKS = ("content_id", "post_url", "experiment_id", "variable", "variant")


def init_links(directory):
    directory = ops.init(directory)
    p = ops.safe_file(directory, "experiment-links.csv")
    if not p.exists():
        with p.open("x", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(LINKS)


def read_links(directory, experiment, variable):
    p = ops.safe_file(ops.local_dir(directory), "experiment-links.csv")
    if p.stat().st_size > 5_000_000:
        raise ValueError("link file too large")
    mapping = {}
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(LINKS):
            raise ValueError("unexpected experiment link columns")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError("malformed experiment links")
            if row["experiment_id"] != experiment:
                continue
            ops.required(row, LINKS)
            if row["variable"] != variable or row["variant"] not in {"a", "b"}:
                raise ValueError("one experiment must use one variable and arms a/b")
            if not learning._url(row["post_url"]):
                raise ValueError("invalid publication URL")
            key = (row["content_id"], row["post_url"])
            if key in mapping:
                raise ValueError("duplicate experiment assignment")
            mapping[key] = row["variant"]
    if not mapping:
        raise ValueError("no links for selected experiment")
    return mapping


def review(directory, metrics, *, experiment, variable, platform, account,
           content_format, topic, window, definition, primary, interest):
    ops.slug(experiment)
    if variable not in VARIABLES:
        raise ValueError("unsupported variable")
    mapping = read_links(directory, experiment, variable)
    result = learning.analyze(Path(metrics), platform=platform, account=account,
                              content_format=content_format, topic_cluster=topic, window=window,
                              metric_name=primary, definition=definition, interest_metric=interest,
                              experiment_id=experiment, variant_labels=mapping)
    result.update(experiment_id=experiment, variable=variable, platform=platform,
                  account=account, content_format=content_format, topic=topic,
                  window=window, definition=definition, primary=primary, interest=interest,
                  assignments=len(mapping), assignment_sha256=hashlib.sha256(
                      json.dumps(sorted((k[0], k[1], v) for k, v in mapping.items())).encode()).hexdigest(),
                  next_decision="HUMAN_REVIEW_REQUIRED")
    ops.write_atomic(ops.local_dir(directory), "variant-review.json",
                     json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


RECEIPT_FIELDS = {"schema", "status", "source_id", "source_sha256", "receiver",
                  "reviewer", "received_at", "evidence_status", "business_progress",
                  "payment_verified", "operating_ledger_written"}


def canonical_post_url(value):
    if not learning._url(value) or len(value) > 2048 or any(c.isspace() or c == "|" for c in value):
        return False
    u = urlsplit(value)
    return not u.query and u.port in (None, 443)


def named_reviewer(value):
    return isinstance(value, str) and 0 < len(value) <= 100 and value == value.strip() and not any(ord(c) < 32 for c in value)


def read_local_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("invalid or oversized local JSON")
    ops.local_dir(path.resolve().parent)
    raw = path.read_bytes()
    if len(raw) > 65536:
        raise ValueError("oversized local JSON")
    return raw, json.loads(raw.decode("utf-8"))


def acknowledge(directory, receipt_path, *, reviewer, confirmed):
    """Bind a manually returned OPC queue receipt to the exact original local bytes."""
    if not confirmed or not named_reviewer(reviewer):
        raise ValueError("named local reviewer and confirmation required")
    directory = ops.local_dir(directory)
    raw_receipt, receipt = read_local_json(receipt_path)
    if not isinstance(receipt, dict) or set(receipt) != RECEIPT_FIELDS:
        raise ValueError("unexpected receipt fields")
    ident = receipt["source_id"]
    if not isinstance(ident, str) or not re.fullmatch(r"lead-[0-9a-f]{16}", ident):
        raise ValueError("invalid source ID")
    if (receipt["schema"] != "opc.contentops-review-receipt/v1"
            or receipt["status"] != "RECEIVED_FOR_REVIEW"
            or receipt["receiver"] != "Xander-Xai/X-SuperPlay-OPC-Blueprint"
            or receipt["evidence_status"] != "UNVERIFIED_REFERENCE_ONLY"
            or receipt["business_progress"] is not False or receipt["payment_verified"] is not False
            or receipt["operating_ledger_written"] is not False or not named_reviewer(receipt["reviewer"])):
        raise ValueError("receipt exceeds review-only scope")
    stamp = receipt["received_at"]
    if not isinstance(stamp, str) or datetime.fromisoformat(stamp.replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("receipt timestamp requires timezone")
    source_bytes, source = read_local_json(ops.safe_file(directory, ident + ".json"))
    if (not isinstance(source, dict) or source.get("schema") != "contentops.opc-demand-signal/v1"
            or source.get("status") != "REVIEW_REQUIRED" or source.get("consent_attested") is not True
            or source.get("paid_demand_verified") is not False or source.get("payment_verified") is not False
            or hashlib.sha256(source_bytes).hexdigest() != receipt["source_sha256"]):
        raise ValueError("source changed or receipt does not match")
    result = {"schema": "contentops.opc-ack/v1", "status": "LOCAL_RECEIPT_MATCHED",
              "source_id": ident, "source_sha256": receipt["source_sha256"],
              "receipt_sha256": hashlib.sha256(raw_receipt).hexdigest(), "reviewer": reviewer,
              "receiver": receipt["receiver"], "remote_identity_independently_verified": False,
              "business_progress": False, "publish_authorized": False}
    name = ident + "-ack.json"
    out = ops.safe_file(directory, name)
    if out.exists():
        previous = json.loads(out.read_text(encoding="utf-8"))
        if previous.get("receipt_sha256") != result["receipt_sha256"]:
            raise ValueError("conflicting acknowledgement")
        return previous
    ops.write_atomic(directory, name, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def lead(directory, metrics, *, content_id, post_url, category, evidence_ref,
         reviewer, consent, confirmed):
    """An anonymized signal for manual OPC review, never a payment or customer claim."""
    if not (consent and confirmed and named_reviewer(reviewer)):
        raise ValueError("consent, named reviewer and confirmation required")
    if not canonical_post_url(post_url) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", content_id):
        raise ValueError("publication reference required")
    ops.slug(category)
    ops.slug(evidence_ref)
    metrics = ops.local_dir(metrics)
    rows = learning._load(ops.safe_file(metrics, "content-index.csv"), learning.INDEX_COLUMNS)
    matches = [r for r in rows if r["content_id"] == content_id and r["post_url"] == post_url
               and r["publish_status"] in learning.VALID_STATUS and learning._date(r["published_at"])]
    if len(matches) != 1:
        raise ValueError("unique published item not found in existing content index")
    item = matches[0]
    ops.account_allows(item["account_alias"], item["platform"])
    result = {"schema": "contentops.opc-demand-signal/v1", "status": "REVIEW_REQUIRED",
              "content_id": content_id, "post_url": post_url, "platform": item["platform"],
              "account_alias": item["account_alias"], "category": category,
              "local_evidence_ref": evidence_ref, "reviewer": reviewer, "consent_attested": True,
              "recorded_at": datetime.now(timezone.utc).isoformat(), "paid_demand_verified": False,
              "payment_verified": False, "external_action": "none"}
    directory = ops.local_dir(directory)
    name = "lead-" + hashlib.sha256((content_id + "|" + post_url + "|" + evidence_ref).encode()).hexdigest()[:16] + ".json"
    if ops.safe_file(directory, name).exists():
        raise ValueError("handoff already exists; inspect existing record")
    ops.write_atomic(directory, name, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("init", "review", "lead", "ack"))
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    for name in ("experiment", "platform", "account", "format", "topic",
                 "content-id", "post-url", "category", "evidence-ref"):
        p.add_argument("--" + name)
    p.add_argument("--variable", choices=sorted(VARIABLES))
    p.add_argument("--window", default="T+24H", choices=learning.WINDOW_HOURS)
    p.add_argument("--definition", default="native_v1")
    p.add_argument("--primary", default="views_or_reads", choices=learning.METRICS)
    p.add_argument("--interest", default="saves", choices=learning.RATE_METRICS)
    p.add_argument("--reviewer", default="")
    p.add_argument("--receipt", type=Path)
    p.add_argument("--consent", action="store_true")
    p.add_argument("--confirm", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.command == "init":
            init_links(a.data_dir)
            print("READY: local experiment-links.csv")
        elif a.command == "review":
            if not all((a.experiment, a.variable, a.platform, a.account, a.format, a.topic)):
                raise ValueError("experiment, variable, platform, account, format and topic required")
            report = review(a.data_dir, a.metrics_dir, experiment=a.experiment, variable=a.variable,
                            platform=a.platform, account=a.account, content_format=a.format, topic=a.topic,
                            window=a.window, definition=a.definition, primary=a.primary, interest=a.interest)
            print(report["status"])
        elif a.command == "ack":
            if a.receipt is None:
                raise ValueError("--receipt required")
            print(acknowledge(a.data_dir, a.receipt, reviewer=a.reviewer, confirmed=a.confirm)["status"])
        else:
            if not all((a.content_id, a.post_url, a.category, a.evidence_ref)):
                raise ValueError("content-id, post-url, category and evidence-ref required")
            lead(a.data_dir, a.metrics_dir, content_id=a.content_id, post_url=a.post_url,
                 category=a.category, evidence_ref=a.evidence_ref, reviewer=a.reviewer,
                 consent=a.consent, confirmed=a.confirm)
            print("REVIEW_REQUIRED: local OPC signal")
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
