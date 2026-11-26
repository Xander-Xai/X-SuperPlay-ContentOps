#!/usr/bin/env python3
"""Loopback-only editable editorial workbench; no router or publishing actions."""
import argparse
import csv
import hashlib
import io
import json
import secrets
import shutil
import sys
import tempfile
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import editorial_ops as ops

EDITABLE = ("planned_date", "minutes", "risk", "hook", "cta", "reviewer")
MAX_BODY = 16_384


def revision(directory):
    directory = ops.local_dir(directory)
    digest = hashlib.sha256()
    for name in ops.FIELDS:
        path = ops.safe_file(directory, name)
        if path.stat().st_size > 5_000_000:
            raise ValueError("input too large")
        digest.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def snapshot(directory):
    before = revision(directory)
    report = ops.plan(directory)
    if before != revision(directory):
        raise ValueError("inputs changed; refresh")
    return before, report


def edit(directory, ident, expected, changes):
    directory = ops.local_dir(directory)
    if not changes or set(changes) - set(EDITABLE):
        raise ValueError("unsupported editorial edit")
    if any(not isinstance(v, str) or not v.strip() or len(v) > 500 for v in changes.values()):
        raise ValueError("blank or oversized edit")
    lock = ops.safe_file(directory, "workspace-edit.lock")
    with lock.open("x", encoding="utf-8"):
        pass
    try:
        before, report = snapshot(directory)
        if before != expected:
            raise ValueError("stale edit; refresh workbench")
        match = [q for q in report["queue"] if q["id"] == ident]
        if len(match) != 1:
            raise ValueError("candidate not found")
        if ops.safe_file(directory, "route-" + ident + ".json").exists():
            raise ValueError("routed candidate is locked; create a new variant")
        q = match[0]
        rows = ops.load(directory, "topics.csv")
        identity = ("topic", "account", "platform", "format", "angle")
        matching = [row for row in rows if all(row[k] == q[k] for k in identity)]
        if len(matching) != 1:
            raise ValueError("ambiguous candidate")
        matching[0].update(changes)
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=ops.FIELDS["topics.csv"])
        writer.writeheader()
        writer.writerows(rows)
        payload = stream.getvalue()
        # Reuse the existing full validation before modifying the real CSV.
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            staged = Path(temp)
            for name in ops.FIELDS:
                if name != "topics.csv":
                    shutil.copyfile(ops.safe_file(directory, name), staged / name)
            (staged / "topics.csv").write_text(payload, encoding="utf-8")
            ops.plan(staged)
        if revision(directory) != expected or ops.safe_file(directory, "route-" + ident + ".json").exists():
            raise ValueError("inputs or route changed; refresh")
        ops.write_atomic(directory, "topics.csv", payload)
        return snapshot(directory)
    finally:
        lock.unlink()


def daily_panel(directory, report, day, minutes):
    from editorial_daily import capacity
    result = capacity(directory, report, ops.load(directory, "signals.csv"), day, minutes)
    e = lambda v: escape(str(v), quote=True)
    candidates = {q["id"]: q for q in report["queue"]}
    rows = []
    for q in result["selected"]:
        ident = q["candidate_id"]
        rows.append("<li><a href='#candidate-" + e(ident) + "'>" +
                    e(candidates[ident]["angle"]) + "</a> — " +
                    e(q["cost_lane"]) + ", " + e(q["estimated_minutes"]) +
                    " min, demand URLs " + e(q["demand_signal_urls"]) + "</li>")
    deferred = {}
    for item in result["deferred"]:
        reason = item["reason"]
        deferred[reason] = deferred.get(reason, 0) + 1
    counts = ", ".join(e(reason) + ": " + e(n) for reason, n in sorted(deferred.items()))
    return ("<article><h2>Daily capacity / " + e(result["day"]) + "</h2><p>" +
            e(result["allocated_minutes"]) + " / " + e(result["budget_minutes"]) +
            " estimated minutes; " + e(result["remaining_minutes"]) + " remaining.</p>" +
            "<ol>" + "".join(rows) + "</ol><p>Deferred: " + (counts or "none") +
            "</p><p>Advisory selection only. No routing or production authorization. "
            "Demand URL counts are not verified buyers.</p></article>")


def render(directory, token, day=None, minutes=None, metrics=None, projects=None):
    rev, report = snapshot(directory)
    def e(value):
        return escape(str(value), quote=True)
    blocks = []
    if day is not None and minutes is not None:
        blocks.append(daily_panel(directory, report, day, minutes))
        if rev != revision(directory):
            raise ValueError("inputs changed; refresh")
    elif day is not None or minutes is not None:
        raise ValueError("day and minutes must be specified together")
    lifecycle = {}
    if metrics is not None:
        from datetime import datetime, timezone
        import editorial_lifecycle
        view = editorial_lifecycle.report(directory, report, metrics,
                                          projects or ops.ROOT / "projects",
                                          datetime.now(timezone.utc).isoformat())
        lifecycle = {item["candidate_id"]: item for item in view["items"]}
    for q in report["queue"]:
        route_file = ops.safe_file(directory, "route-" + q["id"] + ".json")
        if route_file.exists():
            # This is execution bookkeeping, not content/publication status.
            status = json.loads(route_file.read_text(encoding="utf-8")).get("status", "UNKNOWN")
            form = "<p>Route receipt: " + e(status) + " — editing locked.</p>"
        else:
            inputs = "".join("<label>" + e(k) + "<input name='" + e(k) + "' value='" +
                             e(q[k]) + "' required maxlength='500'></label>" for k in EDITABLE)
            form = ("<form method='post' action='/edit'>" +
                    "".join("<input type='hidden' name='" + k + "' value='" + e(v) + "'>"
                            for k, v in (("token", token), ("revision", rev), ("id", q["id"]))) +
                    inputs + "<button>Save plan</button></form>")
        if q["id"] in lifecycle:
            item = lifecycle[q["id"]]
            pub = item["publication"]
            form += ("<p>Lifecycle (local records): " + e(item["route"]) + " | " +
                     e(item["project"]["state"]) + " | " + e(pub["state"]) + "</p>" +
                     "<p>Metrics: " + ", ".join(e(k) + " " + e(v) for k, v in pub["windows"].items()) +
                     "</p><p>Not a media or publication approval.</p>")
        blocks.append("<article id='candidate-" + e(q["id"]) + "'><h2>" + e(q["angle"]) + "</h2><p>" +
                      " | ".join(e(q[k]) for k in ("account", "platform", "series", "decision",
                                                    "score", "cost_lane")) + "</p>" + form + "</article>")
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>ContentOps Workbench</title>"
            "<style>body{font:16px system-ui;max-width:1050px;margin:2rem auto;padding:1rem;background:#f5f6fa}"
            "article{background:white;padding:1rem;margin:1rem 0;border:1px solid #ddd;border-radius:8px}"
            "form{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem}"
            "label{display:flex;flex-direction:column}input,button{font:inherit;padding:.45rem}</style>"
            "<h1>Editorial workbench</h1><p>Local planning only. No approval or publishing action.</p>"
            + "".join(blocks) + "</html>")


def handler(directory, token, day=None, minutes=None, metrics=None, projects=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def trusted(self):
            port = self.server.server_port
            return self.headers.get("Host") in {"127.0.0.1:" + str(port)}

        def reply(self, status, page):
            raw = page.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.trusted() or self.path != "/":
                self.reply(404, "Not found")
                return
            try:
                self.reply(200, render(directory, token, day, minutes, metrics, projects))
            except (ValueError, OSError):
                self.reply(409, "Local data invalid; inspect CSV files.")

        def do_POST(self):
            if not self.trusted() or self.path != "/edit":
                self.reply(404, "Not found")
                return
            if self.headers.get("Origin") != "http://127.0.0.1:" + str(self.server.server_port):
                self.reply(403, "Origin refused")
                return
            try:
                if self.headers.get_content_type() != "application/x-www-form-urlencoded":
                    raise ValueError("invalid content type")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError("invalid body length")
                data = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True,
                                strict_parsing=True, max_num_fields=20)
                if set(data) != {"token", "revision", "id", *EDITABLE} or any(len(v) != 1 for v in data.values()):
                    raise ValueError("invalid form")
                if not secrets.compare_digest(data["token"][0], token):
                    self.reply(403, "Token refused")
                    return
                edit(directory, data["id"][0], data["revision"][0], {k: data[k][0] for k in EDITABLE})
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
            except (ValueError, OSError, UnicodeError):
                self.reply(409, "Edit blocked; refresh and check the inputs.")
    return Handler


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-dir", type=Path, default=ops.DEFAULT)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--day", help="explicit planning day YYYY-MM-DD")
    p.add_argument("--minutes", type=int, help="daily advisory capacity")
    p.add_argument("--metrics-dir", type=Path, help="opt-in local lifecycle view")
    p.add_argument("--projects-dir", type=Path, default=ops.ROOT / "projects")
    a = p.parse_args(argv)
    try:
        if not 1024 <= a.port <= 65535:
            raise ValueError("port must be 1024..65535")
        if (a.day is None) != (a.minutes is None):
            raise ValueError("--day and --minutes must be specified together")
        if a.day is not None:
            from datetime import date
            date.fromisoformat(a.day)
            if not 1 <= a.minutes <= 1440:
                raise ValueError("--minutes must be 1..1440")
        directory = ops.init(a.data_dir)
        with HTTPServer(("127.0.0.1", a.port), handler(directory, secrets.token_urlsafe(32), a.day, a.minutes, a.metrics_dir, a.projects_dir)) as server:
            print("Local planning only: http://127.0.0.1:%d/" % a.port, flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        return 0
    except (ValueError, OSError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
