#!/usr/bin/env python3
"""Offline editorial planner. No network, publishing or approval authority."""
import argparse
import csv
import hashlib
import io
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
    directory = local_dir(directory)
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


def _slugify_topic(topic):
    """An ascii identifier for a topic an operator typed in any script.

    Operators write Chinese topics; the CSV needs an ascii slug. An ascii topic
    is lowercased and dashed; a non-ascii topic gets a stable hashed slug so the
    same topic always maps to the same id. The readable text is kept in the
    angle/hook fields, never lost.
    """
    text = str(topic).strip()
    if text.isascii():
        raw = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]
        if raw and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", raw):
            return raw
    # A non-ascii topic's ascii fragment ("Easel 冻结" and "Easel 升级" both
    # reduce to "easel") is not unique, so hash the full text for a stable id.
    return "topic-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]


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
        raw_scores = {k: int(row[k]) for k in WEIGHTS}
        # -1 is the explicit "not scored yet" sentinel. A quick-created topic
        # carries it until a human fills the six judgements; the planner must
        # never invent those scores.
        unscored = any(v == -1 for v in raw_scores.values())
        if any(v not in (-1,) and not 0 <= v <= 10 for v in raw_scores.values()):
            raise ValueError("score outside 0..10")
        if unscored and any(v != -1 for v in raw_scores.values()):
            raise ValueError("score must be all six dimensions or all -1 (unscored)")
        cost = lane(int(row["minutes"]), row["risk"])
        refs = [v for (t, _), v in evidence.items() if t == topic]
        if unscored:
            scores = {k: 0 for k in WEIGHTS}
            breakdown = {k: 0 for k in WEIGHTS}
            score = None
            weakest = ""
            decision = "NEEDS_SCORING"
            next_gate = "待人工给六维评分：python scripts/editorial_ops.py score --candidate <id> ..."
        else:
            scores = raw_scores
            breakdown = {k: scores[k] * w for k, w in WEIGHTS.items()}
            score = sum(breakdown.values()) / 10
            decision = ("NEEDS_EVIDENCE" if not refs else "CANDIDATE" if score >= 80
                        else "LOW_COST_VALIDATION" if score >= 65 else "DEFER")
            if decision == "LOW_COST_VALIDATION" and cost == "L3":
                decision = "REPLAN_COST"
            # Explain the score instead of only stating it: which weighted
            # dimension is weakest and how far the next decision is. Advice for
            # the human planner; it never changes the decision itself.
            weakest = min(breakdown, key=lambda k: (breakdown[k], k))
            if decision == "NEEDS_EVIDENCE":
                next_gate = "还缺可核对来源：先补一条 source_url 再评分"
            elif decision == "REPLAN_COST":
                next_gate = f"分数够但成本高：降低 minutes/risk 或降低 {weakest} 的投入"
            elif score < 65:
                next_gate = f"再加 {65 - score:.0f} 分到 LOW_COST_VALIDATION；最弱维度 {weakest}"
            elif score < 80:
                next_gate = f"再加 {80 - score:.0f} 分到 CANDIDATE；最弱维度 {weakest}"
            else:
                next_gate = "已达 CANDIDATE"
        ident = hashlib.sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:16]
        queue.append({"id": ident, **row, "score": score, "cost_lane": cost,
                      "decision": decision, "evidence_ids": [v["signal_id"] for v in refs],
                      "source_urls": [v["source_url"] for v in refs],
                      "peer_case_ids": peer_ids.get(topic, []), "unique_source_urls": len(refs),
                      "score_breakdown": breakdown, "weakest_dimension": weakest,
                      "next_gate": next_gate,
                      "status": "PLANNED", "production_ready": False, "publish_authorized": False})
    def _rank(q):
        needs_human = q["decision"] in ("NEEDS_EVIDENCE", "NEEDS_SCORING")
        return (needs_human, -(q["score"] if q["score"] is not None else 0),
                q["planned_date"], q["id"])
    queue.sort(key=_rank)
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
                     "angle", "score", "cost_lane", "decision", "unique_source_urls",
                     "next_gate")) + "</tr>")
    headers = ("Date", "Account", "Platform", "Format", "Series", "Angle",
               "Score", "Lane", "Decision", "Source URLs", "Next")
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


def search(directory, query):
    """Read-only keyword search across the three ledgers.

    Retrieval, not planning: a historical row is returned even if it would not
    pass today's ``plan`` validation, so past topics and peer cases stay
    findable. Matches any field, case-insensitively, and never writes a file.
    """
    directory = local_dir(directory)
    q = str(query or "").strip().lower()
    if not q:
        raise ValueError("--query required")
    hits = []
    for name in FIELDS:
        for line_no, row in enumerate(load(directory, name), start=2):
            if any(q in str(value).lower() for value in row.values()):
                hits.append({"table": name, "line": line_no, "row": row})
    return hits


def _write_rows(directory, name, rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIELDS[name])
    writer.writeheader()
    writer.writerows(rows)
    write_atomic(directory, name, stream.getvalue())


def quick_create(directory, *, topic, account, platform, format, source_url="",
                 angle="", hook="", reviewer="operator"):
    """Create an editable topic row from the minimum an operator knows.

    Required from the operator: the topic, the account, the platform and the
    format. Everything the system can derive is derived (audience from DNA,
    series from the topic, schedule and cost from defaults); the two prose
    fields get a clearly *suggested* value the operator can overwrite. The six
    subjective scores are written as -1 so ``plan`` reports NEEDS_SCORING —
    the tool never invents a demand, reach or commercial judgement.
    """
    directory = local_dir(directory)
    display_topic = str(topic).strip()
    topic_slug = _slugify_topic(display_topic)
    account_slug, platform_slug = slug(account), slug(platform)
    reviewer = str(reviewer or "operator").strip() or "operator"
    if format not in FORMATS:
        raise ValueError("invalid format")
    account_allows(account_slug, platform_slug)
    dna = json.loads((ROOT / "config" / "accounts" / (account_slug + ".json"))
                     .read_text(encoding="utf-8"))
    audience = str((dna.get("core_audience") or dna.get("audience") or ["general"])[0])
    derived = [
        "audience <- account DNA core_audience",
        "series <- topic slug",
        "planned_date <- today",
        "minutes/risk <- 30/low default",
        "six scores <- -1 (NEEDS_SCORING, human must fill)",
    ]
    row = {
        "topic": topic_slug, "account": account_slug, "platform": platform_slug,
        "format": format, "audience": audience[:80], "series": topic_slug,
        "planned_date": date.today().isoformat(), "minutes": "30", "risk": "low",
        "reviewer": reviewer,
        "demand": "-1", "reach": "-1", "fit": "-1",
        "originality": "-1", "evidence": "-1", "commercial": "-1",
    }
    if angle:
        row["angle"] = angle
    else:
        row["angle"] = f"从真实使用出发讲清「{display_topic}」"
        derived.append("angle <- SUGGESTED, overwrite it")
    if hook:
        row["hook"] = hook
    else:
        row["hook"] = f"先说清「{display_topic}」最容易踩的坑"
        derived.append("hook <- SUGGESTED, overwrite it")
    row["cta"] = "完整步骤和来源在文末"
    derived.append("cta <- SUGGESTED, overwrite it")
    required(row, FIELDS["topics.csv"])
    rows = load(directory, "topics.csv")
    key = (row["topic"], row["account"], row["platform"], row["format"], row["angle"])
    if any((r["topic"], r["account"], r["platform"], r["format"], r["angle"]) == key
           for r in rows):
        raise ValueError("duplicate editorial variant")
    rows.append(row)
    _write_rows(directory, "topics.csv", rows)

    signal_added = False
    if source_url:
        signal = {
            "signal_id": "sig-" + hashlib.sha256(
                json.dumps([topic_slug, source_url], ensure_ascii=False).encode()).hexdigest()[:12],
            "topic": topic_slug, "kind": "search", "source_url": source_url,
            "observed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "observation": f"operator-supplied source for {topic_slug}",
        }
        required(signal, FIELDS["signals.csv"])
        validate_source(signal)
        signals = load(directory, "signals.csv")
        if not any(r["signal_id"] == signal["signal_id"] for r in signals):
            signals.append(signal)
            _write_rows(directory, "signals.csv", signals)
            signal_added = True

    return {"schema": "contentops.editorial-quick-create/v1", "created": row,
            "derived": derived, "signal_added": signal_added,
            "fields_from_operator": ["topic", "account", "platform", "format"],
            "fields_total": len(FIELDS["topics.csv"]),
            "needs": ["six human scores", "copy review later"],
            "next": ("python scripts/editorial_ops.py score --candidate <id> "
                     "--demand N --reach N --fit N --originality N --evidence N --commercial N"),
            "external_action": "none", "publish_authorized": False}


def score(directory, candidate, votes):
    """Fill the six human scores for a quick-created candidate, by plan id."""
    directory = local_dir(directory)
    report = plan(directory)
    target = next((q for q in report["queue"] if q["id"] == candidate), None)
    if not target:
        raise ValueError("unknown candidate id")
    for key, value in votes.items():
        if key not in WEIGHTS:
            raise ValueError(f"unknown score dimension {key}")
        if not 0 <= value <= 10:
            raise ValueError("score outside 0..10")
    rows = load(directory, "topics.csv")
    match = (target["topic"], target["account"], target["platform"],
             target["format"], target["angle"])
    for row in rows:
        if (row["topic"], row["account"], row["platform"],
                row["format"], row["angle"]) == match:
            for key, value in votes.items():
                row[key] = str(value)
            break
    else:
        raise ValueError("candidate row not found")
    required(rows[0], FIELDS["topics.csv"])
    _write_rows(directory, "topics.csv", rows)
    return {"schema": "contentops.editorial-score/v1", "candidate": candidate,
            "scored": votes, "external_action": "none", "publish_authorized": False}


def prepare_handoff(directory, report, ident, reviewer, confirmed):
    """Create an explicit router command; never execute it or approve research."""
    directory = local_dir(directory)
    if not confirmed or not reviewer.strip():
        raise ValueError("named human decision and --confirm required")
    matches = [q for q in report["queue"] if q["id"] == ident]
    if len(matches) != 1 or matches[0]["decision"] not in {"CANDIDATE", "LOW_COST_VALIDATION"}:
        raise ValueError("candidate is not eligible for handoff")
    q = matches[0]
    notes = json.dumps({k: q[k] for k in ("id", "topic", "platform", "format",
                                            "audience", "hook", "cta", "series", "cost_lane")},
                       ensure_ascii=False)
    argv = ["python", "scripts/content_route.py", "start", "--mode", "topic",
            "--account", q["account"], "--topic", q["angle"], "--by", reviewer,
            "--notes", notes]
    for url in q["source_urls"]:
        argv.extend(["--url", url])
    result = {"schema": "contentops.editorial-handoff/v1", "status": "READY_FOR_HUMAN_ROUTING",
              "reviewer": reviewer, "candidate_id": ident, "argv": argv,
              "plan_sha256": hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
              "production_ready": False, "publish_authorized": False}
    write_atomic(directory, "editorial-handoff.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result



def route(directory, report, ident, reviewer, confirmed, runner=None):
    """Explicitly create a topic-route run; never approve copy or production.

    A durable pending marker is created before execution. Ambiguous outcomes
    require human reconciliation rather than automatic retries.
    """
    from process_utils import hidden_run, python_executable
    directory = local_dir(directory)
    if not confirmed or not reviewer.strip() or not re.fullmatch(r"[0-9a-f]{16}", ident or ""):
        raise ValueError("candidate ID, named human and confirmation required")
    name = "route-" + ident + ".json"
    path = safe_file(directory, name)
    if path.exists():
        raise ValueError("route already attempted; reconcile its receipt before any retry")
    handoff = prepare_handoff(directory, report, ident, reviewer, confirmed)
    argv = [python_executable(), str(ROOT / "scripts/content_route.py"),
            *handoff["argv"][2:], "--json"]
    receipt = {"schema": "contentops.editorial-route/v1", "status": "EXECUTION_PENDING",
               "candidate_id": ident, "reviewer": reviewer, "plan_sha256": handoff["plan_sha256"],
               "production_ready": False, "publish_authorized": False}
    with path.open("x", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)
    try:
        result = (runner or hidden_run)(argv, cwd=str(ROOT), timeout=90)
        payload = json.loads(result.stdout)
        q = next(q for q in report["queue"] if q["id"] == ident)
        if not isinstance(payload, dict) or payload.get("account_id") != q["account"]:
            raise ValueError("router result account mismatch or invalid output")
        receipt.update(router_exit_code=result.returncode, router_run_id=payload.get("run_id"),
                       router_state=payload.get("state"),
                       status="ROUTED_FOR_HUMAN_REVIEW" if result.returncode == 0
                       and payload.get("run_id") else "ROUTE_BLOCKED")
    except Exception as exc:
        # No raw stdout/stderr or secrets in the receipt.
        receipt.update(status="RECONCILIATION_REQUIRED", error_type=type(exc).__name__)
    write_atomic(directory, name, json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("init", "plan", "import-hotspots", "dashboard",
                                            "handoff", "route", "search", "quick-create", "score"))
    parser.add_argument("--data-dir", type=Path, default=DEFAULT)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--topic")
    parser.add_argument("--query", default="")
    parser.add_argument("--account")
    parser.add_argument("--platform")
    parser.add_argument("--format")
    parser.add_argument("--source-url", default="")
    parser.add_argument("--angle", default="")
    parser.add_argument("--hook", default="")
    parser.add_argument("--candidate")
    parser.add_argument("--reviewer", default="")
    parser.add_argument("--confirm", action="store_true")
    for dim in ("demand", "reach", "fit", "originality", "evidence", "commercial"):
        parser.add_argument("--" + dim, type=int, default=None)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init(args.data_dir)
            print("READY: local CSV templates")
        elif args.command == "import-hotspots":
            if not args.input or not args.topic or not args.account:
                raise ValueError("--input, --topic and --account required")
            print(json.dumps(import_hotspots(args.data_dir, args.input, args.topic, args.account)))
        elif args.command == "search":
            hits = search(args.data_dir, args.query)
            print(json.dumps(hits, ensure_ascii=False, indent=2))
            print("SEARCH: %d match(es)" % len(hits), file=sys.stderr)
        elif args.command == "quick-create":
            if not (args.topic and args.account and args.platform and args.format):
                raise ValueError("--topic --account --platform --format required")
            result = quick_create(args.data_dir, topic=args.topic, account=args.account,
                                  platform=args.platform, format=args.format,
                                  source_url=args.source_url, angle=args.angle,
                                  hook=args.hook, reviewer=args.reviewer)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "score":
            votes = {dim: getattr(args, dim) for dim in WEIGHTS
                     if getattr(args, dim) is not None}
            if not args.candidate or not votes:
                raise ValueError("--candidate and at least one score required")
            print(json.dumps(score(args.data_dir, args.candidate, votes),
                             ensure_ascii=False))
        else:
            report = plan(args.data_dir)
            if args.command == "dashboard":
                dashboard(args.data_dir, report)
                print("READY: local editorial-workspace.html")
            elif args.command == "route":
                receipt = route(args.data_dir, report, args.candidate, args.reviewer, args.confirm)
                print(receipt["status"])
                return 0 if receipt["status"] == "ROUTED_FOR_HUMAN_REVIEW" else 1
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
