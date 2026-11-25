#!/usr/bin/env python3
"""Offline editorial planner. No network, publishing or approval authority."""
import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / ".local" / "editorial-ops"
FIELDS = {
    "signals.csv": ("signal_id", "topic", "kind", "source_url", "observed_at", "observation"),
    "peers.csv": ("case_id", "topic", "platform", "source_url", "observed_at",
                  "hook", "format", "lesson", "metric_name", "metric_value"),
    "topics.csv": ("topic", "account", "platform", "format", "audience", "angle",
                   "series", "hook", "cta", "planned_date", "minutes", "risk",
                   "reviewer", "demand", "reach", "fit", "originality", "evidence", "commercial"),
}
WEIGHTS = dict(demand=25, reach=20, fit=15, originality=15, evidence=15, commercial=10)
KINDS = {"hotspot", "search", "comment", "issue", "job", "buyer_request", "review", "rss"}
FORMATS = {"text", "image", "article", "video"}


def local_dir(path):
    path = Path(path).resolve()
    try:
        rel = path.relative_to(ROOT.resolve())
    except ValueError:
        return path
    if not rel.parts or rel.parts[0] != ".local":
        raise ValueError("data inside checkout must be under ignored .local/")
    return path


def safe_file(directory, name):
    p = directory / name
    if p.is_symlink() or p.resolve().parent != directory:
        raise ValueError("unsafe file path")
    return p


def init(directory):
    directory = local_dir(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, fields in FIELDS.items():
        p = safe_file(directory, name)
        if not p.exists():
            with p.open("x", encoding="utf-8", newline="") as f:
                csv.writer(f).writerow(fields)
    return directory


def load(directory, name):
    p = safe_file(directory, name)
    if p.stat().st_size > 5_000_000:
        raise ValueError("input too large")
    with p.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(FIELDS[name]):
            raise ValueError("invalid CSV columns: " + name)
        rows = list(reader)
    for row in rows:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("malformed CSV")
    return rows


def slug(s):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", s):
        raise ValueError("invalid slug")
    return s


def required(row, fields):
    if any(not row[k].strip() for k in fields):
        raise ValueError("missing required field")


def validate_source(row):
    u = urlsplit(row["source_url"])
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.fragment:
        raise ValueError("source must be HTTPS without credentials or fragment")
    if datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00")).utcoffset() is None:
        raise ValueError("observation requires timezone")
    slug(row["topic"])


def unique(rows, field):
    ids = [slug(r[field]) for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate " + field)


def account_allows(account, platform):
    dna = json.loads((ROOT / "config/accounts" / (slug(account) + ".json")).read_text(encoding="utf-8"))
    if dna.get("slug") != account or platform not in dna.get("platforms", []):
        raise ValueError("platform not in account DNA")


def lane(minutes, risk):
    if risk not in {"low", "standard", "high"} or not 1 <= minutes <= 480:
        raise ValueError("invalid risk or time budget")
    return "L3" if risk == "high" or minutes > 60 else "L2" if risk == "standard" or minutes > 15 else "L1"


def plan(directory, check_account=account_allows):
    directory = local_dir(directory)
    signals, peers, topics = (load(directory, n) for n in FIELDS)
    unique(signals, "signal_id")
    unique(peers, "case_id")
    evidence = {}
    peer_ids = {}
    for row in signals:
        required(row, FIELDS["signals.csv"])
        validate_source(row)
        if row["kind"] not in KINDS:
            raise ValueError("invalid signal kind")
        evidence.setdefault((row["topic"], row["source_url"]), row)
    for row in peers:
        required(row, FIELDS["peers.csv"][:-2])
        validate_source(row)
        if row["format"] not in FORMATS:
            raise ValueError("invalid peer format")
        if bool(row["metric_name"]) != bool(row["metric_value"]):
            raise ValueError("metric name/value must be paired")
        if row["metric_value"]:
            v = float(row["metric_value"])
            if not math.isfinite(v) or v < 0:
                raise ValueError("invalid observed metric")
        peer_ids.setdefault(row["topic"], []).append(row["case_id"])
    queue, seen = [], set()
    for row in topics:
        required(row, FIELDS["topics.csv"])
        topic, account, platform = (slug(row[k]) for k in ("topic", "account", "platform"))
        slug(row["series"])
        check_account(account, platform)
        if row["format"] not in FORMATS:
            raise ValueError("invalid format")
        date.fromisoformat(row["planned_date"])
        key = (topic, account, platform, row["format"], row["angle"])
        if key in seen:
            raise ValueError("duplicate editorial variant")
        seen.add(key)
        scores = {k: int(row[k]) for k in WEIGHTS}
        if any(not 0 <= v <= 10 for v in scores.values()):
            raise ValueError("score outside 0..10")
        score = sum(scores[k] * w for k, w in WEIGHTS.items()) / 10
        cost = lane(int(row["minutes"]), row["risk"])
        refs = [v for (t, _), v in evidence.items() if t == topic]
        decision = ("NEEDS_EVIDENCE" if not refs else "CANDIDATE" if score >= 80
                    else "LOW_COST_VALIDATION" if score >= 65 else "DEFER")
        if decision == "LOW_COST_VALIDATION" and cost == "L3":
            decision = "REPLAN_COST"
        ident = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:16]
        queue.append({"id": ident, **row, "score": score, "cost_lane": cost,
                      "decision": decision, "evidence_ids": [v["signal_id"] for v in refs],
                      "source_urls": [v["source_url"] for v in refs],
                      "peer_case_ids": peer_ids.get(topic, []), "unique_source_urls": len(refs),
                      "status": "PLANNED", "production_ready": False, "publish_authorized": False})
    queue.sort(key=lambda q: (q["decision"] == "NEEDS_EVIDENCE", -q["score"], q["planned_date"], q["id"]))
    return {"schema": "contentops.editorial-plan/v1", "status": "ADVISORY_ONLY",
            "weights": WEIGHTS, "unique_signals": len(evidence), "peer_cases": len(peers),
            "queue": queue, "calendar": dict(sorted(Counter(q["planned_date"] for q in queue).items())),
            "series": dict(sorted(Counter(q["series"] for q in queue).items())),
            "external_action": "none", "publish_authorized": False}


def save(directory, report):
    directory = local_dir(directory)
    p = safe_file(directory, "editorial-plan.json")
    tmp = safe_file(directory, "editorial-plan.tmp")
    with tmp.open("x", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    tmp.replace(p)



def write_atomic(directory, name, content):
    p = safe_file(directory, name)
    tmp = safe_file(directory, name + ".tmp")
    with tmp.open("x", encoding="utf-8", newline="") as f:
        f.write(content)
    tmp.replace(p)


def hotspot_identity(account, record):
    from types import SimpleNamespace
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from contentops.routing.hotspot_route import candidate_id_for
    return candidate_id_for(SimpleNamespace(account_id=account), record)


def import_hotspots(directory, input_file, topic, account):
    """Import a user-selected, account-scoped content_route candidates JSON export."""
    import io
    directory = local_dir(directory)
    input_file = Path(input_file)
    if input_file.is_symlink():
        raise ValueError("unsafe candidate export path")
    local_dir(input_file.resolve().parent)
    if input_file.stat().st_size > 5_000_000:
        raise ValueError("candidate export too large")
    slug(topic)
    # Account DNA must exist, but collection is not a platform action.
    dna = json.loads((ROOT / "config/accounts" / (slug(account) + ".json")).read_text(encoding="utf-8"))
    if dna.get("slug") != account:
        raise ValueError("unknown account")
    data = json.loads(input_file.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or any(not isinstance(c, dict) for c in data):
        raise ValueError("expected candidates JSON array")
    rows = load(directory, "signals.csv")
    unique(rows, "signal_id")
    urls = {(r["topic"], r["source_url"]) for r in rows}
    ids = {r["signal_id"] for r in rows}
    added = 0
    skipped = 0
    for c in data:
        if (c.get("candidate_id") != hotspot_identity(account, c) or
                not isinstance(c.get("relevance"), dict) or
                c["relevance"].get("accepted") is not True or
                (isinstance(c.get("quality"), dict) and c["quality"].get("verdict") == "REJECT")):
            skipped += 1
            continue
        u = c.get("url")
        title = c.get("title")
        stamp = c.get("collected_at")
        if not all(isinstance(v, str) and v.strip() for v in (u, title, stamp)):
            skipped += 1
            continue
        ident = "hot-" + hashlib.sha256((topic + "\n" + u).encode()).hexdigest()[:20]
        row = dict(signal_id=ident, topic=topic, kind="hotspot",
                   source_url=u, observed_at=stamp, observation=title)
        try:
            validate_source(row)
        except ValueError:
            skipped += 1
            continue
        if (topic, u) in urls:
            skipped += 1
            continue
        if ident in ids:
            raise ValueError("signal ID conflict")
        rows.append(row)
        ids.add(ident)
        urls.add((topic, u))
        added += 1
    if added:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=FIELDS["signals.csv"])
        writer.writeheader()
        writer.writerows(rows)
        write_atomic(directory, "signals.csv", stream.getvalue())
    return {"added": added, "skipped": skipped, "kind": "hotspot",
            "external_action": "none"}


def dashboard(directory, report):
    """Static, escaped local view; never loads third-party content."""
    from html import escape
    directory = local_dir(directory)
    def e(value):
        return escape(str(value), quote=True)
    rows = []
    for q in report["queue"]:
        rows.append("<tr>" + "".join("<td>" + e(q[k]) + "</td>" for k in
                    ("planned_date", "account", "platform", "format", "series",
                     "angle", "score", "cost_lane", "decision", "unique_source_urls")) + "</tr>")
    headers = ("Date", "Account", "Platform", "Format", "Series", "Angle",
               "Score", "Lane", "Decision", "Source URLs")
    calendar = "".join("<li>" + e(k) + ": " + e(v) + "</li>" for k, v in report["calendar"].items())
    series = "".join("<li>" + e(k) + ": " + e(v) + "</li>" for k, v in report["series"].items())
    page = ("<!doctype html><html lang='en'><meta charset='utf-8'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>ContentOps editorial workspace</title>"
            "<style>body{font:15px system-ui;margin:2rem;color:#202b31;background:#f7f9fc}"
            "table{border-collapse:collapse;width:100%;background:white}td,th{padding:.65rem;border:1px solid #ddd;text-align:left}"
            "th{background:#e8edf3}h1{font-size:24px}section{overflow:auto}</style>"
            "<h1>ContentOps editorial workspace</h1><p>ADVISORY ONLY — planned, not published.</p>"
            "<h2>Editorial queue</h2><section><table><thead><tr>" +
            "".join("<th>" + e(h) + "</th>" for h in headers) +
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>"
            "<h2>Calendar</h2><ul>" + calendar + "</ul><h2>Series</h2><ul>" + series + "</ul></html>")
    write_atomic(directory, "editorial-workspace.html", page)


def prepare_handoff(directory, report, ident, reviewer, confirmed):
    """Create an explicit router command; never execute it or approve research."""
    directory = local_dir(directory)
    if not confirmed or not reviewer.strip():
        raise ValueError("named human decision and --confirm required")
    matches = [q for q in report["queue"] if q["id"] == ident]
    if len(matches) != 1 or matches[0]["decision"] not in {"CANDIDATE", "LOW_COST_VALIDATION"}:
        raise ValueError("candidate is not eligible for handoff")
    q = matches[0]
    argv = ["python", "scripts/content_route.py", "start", "--mode", "topic",
            "--account", q["account"], "--topic", q["angle"], "--by", reviewer,
            "--notes", "Editorial plan " + q["id"]]
    for url in q["source_urls"]:
        argv.extend(["--url", url])
    result = {"schema": "contentops.editorial-handoff/v1", "status": "READY_FOR_HUMAN_ROUTING",
              "reviewer": reviewer, "candidate_id": ident, "argv": argv,
              "plan_sha256": hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
              "production_ready": False, "publish_authorized": False}
    write_atomic(directory, "editorial-handoff.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "plan", "import-hotspots", "dashboard", "handoff"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--topic")
    parser.add_argument("--account")
    parser.add_argument("--candidate")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init(args.data_dir)
            print("READY: local CSV templates")
        elif args.command == "import-hotspots":
            if not args.input or not args.topic or not args.account:
                raise ValueError("--input, --topic and --account required")
            print(json.dumps(import_hotspots(args.data_dir, args.input, args.topic, args.account)))
        else:
            report = plan(args.data_dir)
            if args.command == "dashboard":
                dashboard(args.data_dir, report)
                print("READY: local editorial-workspace.html")
            elif args.command == "handoff":
                prepare_handoff(args.data_dir, report, args.candidate, args.reviewer, args.confirm)
                print("READY_FOR_HUMAN_ROUTING: local editorial-handoff.json")
            else:
                save(args.data_dir, report)
                print("ADVISORY_ONLY: %d variants" % len(report["queue"]))
        return 0
    except (ValueError, OSError, TypeError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
