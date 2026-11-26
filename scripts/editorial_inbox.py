#!/usr/bin/env python3
"""Local single-operator feedback intake and human-confirmed topic promotion."""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit
import editorial_ops as ops
import editorial_feedback as feedback
import platform_learning_loop as learning

NAME = "audience-inbox.csv"
FIELDS = ("feedback_id", "account", "platform", "topic", "category",
          "source_url", "observed_at", "observation", "reviewer")
ACTIONABLE = {"question", "pain", "request", "criticism"}
CATEGORIES = ACTIONABLE | {"praise", "other"}


def identity(row):
    return "fb-" + hashlib.sha256(json.dumps(
        [row[k] for k in ("account", "platform", "topic", "source_url")],
        ensure_ascii=False).encode()).hexdigest()[:24]


def validate(row):
    ops.required(row, FIELDS)
    for key in ("feedback_id", "account", "platform", "topic"):
        ops.slug(row[key])
    ops.account_allows(row["account"], row["platform"])
    ops.validate_source(row)
    if urlsplit(row["source_url"]).query or any(c.isspace() for c in row["source_url"]):
        raise ValueError("public HTTPS URL without query or whitespace required")
    if row["category"] not in CATEGORIES or row["feedback_id"] != identity(row):
        raise ValueError("invalid category or feedback identity")
    if len(row["observation"]) > 500 or len(row["reviewer"]) > 80:
        raise ValueError("use short sanitized notes and reviewer alias")


def init(directory):
    directory = ops.init(directory)
    path = ops.safe_file(directory, NAME)
    if not path.exists():
        with path.open("x", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(FIELDS)
    return directory


def read(directory):
    path = ops.safe_file(directory, NAME)
    if path.stat().st_size > 5_000_000:
        raise ValueError("inbox too large")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(FIELDS):
            raise ValueError("invalid inbox columns")
        rows = list(reader)
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("malformed inbox")
        validate(row)
    ops.unique(rows, "feedback_id")
    return rows


def write(directory, name, fields, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    ops.write_atomic(directory, name, stream.getvalue())


def receipt(status, **kwargs):
    return {"schema": "contentops.audience-inbox/v1", "status": status,
            **kwargs, "buyer_verified": False, "production_ready": False,
            "publish_authorized": False}


def add(directory, confirmed, **row):
    if not confirmed:
        raise ValueError("confirm public source and sanitized observation")
    if set(row) != set(FIELDS) - {"feedback_id"}:
        raise ValueError("invalid input fields")
    row["feedback_id"] = identity(row)
    validate(row)
    directory = init(directory)
    rows = read(directory)
    for old in rows:
        if old["feedback_id"] == row["feedback_id"]:
            if old != row:
                raise ValueError("conflicting replay; reconcile manually")
            return receipt("DUPLICATE", feedback_id=row["feedback_id"])
    write(directory, NAME, FIELDS, rows + [row])
    return receipt("RECORDED", feedback_id=row["feedback_id"])


def signals(directory):
    rows = ops.load(directory, "signals.csv")
    ops.unique(rows, "signal_id")
    for row in rows:
        ops.required(row, ops.FIELDS["signals.csv"])
        ops.validate_source(row)
        if row["kind"] not in ops.KINDS:
            raise ValueError("invalid signal kind")
    return rows


def matches(a, b):
    return (a["topic"], a["source_url"]) == (b["topic"], b["source_url"])


def report(directory):
    existing = signals(directory)
    groups = defaultdict(list)
    for row in read(directory):
        state = ("LINKED" if any(matches(row, s) for s in existing)
                 else "READY_FOR_REVIEW" if row["category"] in ACTIONABLE else "OBSERVE_ONLY")
        groups[(row["account"], row["platform"], row["topic"])].append({**row, "state": state})
    return receipt("ADVISORY_ONLY", groups=[
        {"account": a, "platform": p, "topic": t,
         "unique_source_urls": len({r["source_url"] for r in items}),
         "states": dict(Counter(r["state"] for r in items)),
         "categories": dict(Counter(r["category"] for r in items)), "items": items}
        for (a, p, t), items in sorted(groups.items())],
        limits="URL counts do not prove unique users, independent demand or buyers.")


def promote(directory, feedback_id, reviewer, confirmed):
    if not confirmed or not reviewer.strip() or len(reviewer) > 80:
        raise ValueError("named human confirmation required")
    row = next((r for r in read(directory) if r["feedback_id"] == feedback_id), None)
    if row is None or row["category"] not in ACTIONABLE:
        raise ValueError("select actionable feedback")
    existing = signals(directory)
    linked = [s["signal_id"] for s in existing if matches(row, s)]
    if linked:
        return receipt("ALREADY_LINKED", feedback_id=feedback_id, signal_ids=linked, reviewer=reviewer)
    ident = "feedback-" + hashlib.sha256(json.dumps(
        [row["topic"], row["source_url"]], ensure_ascii=False).encode()).hexdigest()[:24]
    if any(s["signal_id"] == ident for s in existing):
        raise ValueError("signal identity conflict")
    signal = dict(signal_id=ident, kind="comment", **{
        k: row[k] for k in ("topic", "source_url", "observed_at", "observation")})
    write(directory, "signals.csv", ops.FIELDS["signals.csv"], existing + [signal])
    return receipt("LINKED", feedback_id=feedback_id, signal_ids=[ident], reviewer=reviewer)



def feedback_row(directory, ident):
    ops.slug(ident)
    rows = [r for r in read(directory) if r["feedback_id"] == ident]
    if len(rows) != 1:
        raise ValueError("select exactly one existing feedback")
    return rows[0]


def feedback_digest(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def publication(metrics, row, content_id, post_url):
    if not content_id.strip() or not feedback.canonical_post_url(post_url):
        raise ValueError("canonical published identity required")
    metrics = ops.local_dir(metrics)
    records = learning._load(ops.safe_file(metrics, "content-index.csv"), learning.INDEX_COLUMNS)
    matches = [p for p in records if p["content_id"] == content_id or p["post_url"] == post_url]
    if len(matches) != 1:
        raise ValueError("missing or duplicate publication identity")
    p = matches[0]
    if (p["content_id"], p["post_url"], p["account_alias"], p["platform"], p["topic_cluster"]) != (
            content_id, post_url, row["account"], row["platform"], row["topic"]):
        raise ValueError("publication identity or account/platform/topic mismatch")
    published, observed = learning._date(p["published_at"]), learning._date(row["observed_at"])
    if (p["publish_status"] not in learning.VALID_STATUS or not published or not observed
            or published > observed or observed > datetime.now(timezone.utc)):
        raise ValueError("feedback must follow actual reported publication")
    return p


def publication_binding(directory, metrics, feedback_id, content_id, post_url, reviewer, confirmed):
    if not confirmed or not feedback.named_reviewer(reviewer):
        raise ValueError("named human attestation of feedback provenance required")
    row = feedback_row(directory, feedback_id)
    p = publication(metrics, row, content_id, post_url)
    result = receipt("PUBLICATION_LINKED", feedback_id=feedback_id, content_id=content_id,
                     post_url=post_url, published_at=p["published_at"],
                     feedback_sha256=feedback_digest(row), reviewer=reviewer,
                     attribution="operator_attested_not_independently_verified")
    name = "feedback-publication-" + feedback_id + ".json"
    path = ops.safe_file(directory, name)
    if path.exists():
        if path.stat().st_size > 100_000 or json.loads(path.read_text(encoding="utf-8")) != result:
            raise ValueError("conflicting feedback publication binding")
        return result
    ops.write_atomic(directory, name, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def handoff_lead(directory, metrics, feedback_id, reviewer, consent, confirmed):
    if not (consent and confirmed and feedback.named_reviewer(reviewer)):
        raise ValueError("explicit consent and named human confirmation required")
    row = feedback_row(directory, feedback_id)
    if row["category"] not in {"pain", "request"}:
        raise ValueError("only selected pain/request observations eligible for review")
    path = ops.safe_file(directory, "feedback-publication-" + feedback_id + ".json")
    if path.stat().st_size > 100_000:
        raise ValueError("invalid publication binding")
    binding = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(binding, dict) or binding.get("schema") != "contentops.audience-inbox/v1"
            or binding.get("status") != "PUBLICATION_LINKED"
            or binding.get("feedback_id") != feedback_id
            or binding.get("feedback_sha256") != feedback_digest(row)):
        raise ValueError("missing or stale feedback binding")
    p = publication(metrics, row, binding["content_id"], binding["post_url"])
    if binding.get("published_at") != p["published_at"]:
        raise ValueError("publication changed since binding")
    # Reuse existing anonymous OPC handoff; never export comment text or identity.
    return feedback.lead(directory, metrics, content_id=p["content_id"], post_url=p["post_url"],
                         category=row["topic"], evidence_ref=feedback_id, reviewer=reviewer,
                         consent=consent, confirmed=confirmed)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--metrics-dir", type=Path, default=learning.DEFAULT_DATA)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("report")
    a = sub.add_parser("add")
    for key in FIELDS[1:]:
        a.add_argument("--" + key.replace("_", "-"), required=True)
    a.add_argument("--confirm", action="store_true")
    a = sub.add_parser("promote")
    a.add_argument("--feedback-id", required=True)
    a.add_argument("--reviewer", required=True)
    a.add_argument("--confirm", action="store_true")
    for cmd in ("bind-publication", "lead"):
        a = sub.add_parser(cmd)
        a.add_argument("--feedback-id", required=True)
        a.add_argument("--reviewer", required=True)
        a.add_argument("--confirm", action="store_true")
        if cmd == "bind-publication":
            a.add_argument("--content-id", required=True)
            a.add_argument("--post-url", required=True)
        else:
            a.add_argument("--consent", action="store_true")
    args = vars(p.parse_args())
    directory, metrics, command = args.pop("data_dir"), args.pop("metrics_dir"), args.pop("command")
    try:
        if command == "init":
            result = receipt("INITIALIZED", directory=str(init(directory)))
        elif command == "report":
            result = report(directory)
        else:
            args["confirmed"] = args.pop("confirm")
            if command == "bind-publication":
                result = publication_binding(directory, metrics, **args)
            elif command == "lead":
                result = handoff_lead(directory, metrics, **args)
            else:
                result = (add if command == "add" else promote)(directory, **args)
        print(json.dumps(result, ensure_ascii=True, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        p.exit(1, "inbox refused: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
