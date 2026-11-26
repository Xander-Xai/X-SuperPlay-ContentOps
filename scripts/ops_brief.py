#!/usr/bin/env python3
"""One screen for the day's operations: what needs a decision, and what next.

The operator should not have to remember six CLIs and four paths to learn, on a
given morning, what to do. This reads only what already exists -- the editorial
plan, each project's receipts, the platform registry, the last hotspot capture --
and prints a single briefing with the next action per item. It never approves,
never publishes, never bills, and never invents a status.

Usage:
    python scripts/ops_brief.py                 # today, text
    python scripts/ops_brief.py --html out.html # also write a static page
    python scripts/ops_brief.py --data-dir <dir> --projects <dir>

Exit codes: 0 briefing printed; 2 a required input directory is unreadable.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

DEFAULT_DATA = ROOT / ".local" / "editorial-ops"
DEFAULT_PROJECTS = ROOT / "projects"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _editorial_queue(data_dir: Path) -> Dict[str, Any]:
    """Reuse the planner; never recompute its rules here."""
    plan_file = data_dir / "editorial-plan.json"
    report = _read_json(plan_file)
    if report is None:
        try:
            import editorial_ops as ops  # noqa: WPS433
            report = ops.plan(data_dir)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            return {"state": "UNAVAILABLE", "detail": str(exc), "queue": []}
    queue = report.get("queue") or []
    by_decision: Counter = Counter(item.get("decision") for item in queue)
    due = {}
    for item in queue:
        due.setdefault(item.get("planned_date"), 0)
        due[item["planned_date"]] += 1
    return {"state": "OK", "queue": queue, "by_decision": dict(by_decision),
            "calendar": dict(sorted(due.items()))}


def _project_stage(project: Path) -> Dict[str, Any]:
    """Classify a project by the receipts it actually wrote."""
    receipts = project / "receipts"
    final = project / "final"
    stage, next_action = "UNKNOWN", "check project layout"
    review = _read_json(receipts / "human-review.json")
    package = _read_json(receipts / "graphic-package.json")
    m5 = _read_json(receipts / "m5-run.json")
    metrics = _read_json(receipts / "metrics-review.json")
    has_mp4 = final.is_dir() and any(final.glob("*.mp4"))
    if metrics is not None:
        stage, next_action = "REVIEWED", "write the next brief from this review"
    elif review is not None and str(review.get("state")) == "PENDING_FOUNDER_REVIEW":
        stage, next_action = "AWAITING_REVIEW", "human watches the film and fills human-review.json"
    elif review is not None and review.get("decision") in {"APPROVE", "APPROVED"}:
        stage, next_action = "APPROVED", "pack with video_deliver.py, publish by hand"
    elif package is not None and str(package.get("status")) == "AWAITING_MANUAL_REVIEW":
        stage, next_action = "AWAITING_REVIEW", "review the graphic package"
    elif has_mp4:
        stage, next_action = "RENDERED", "run qc then write human-review.json"
    elif m5 is not None:
        stage, next_action = "IN_PRODUCTION", "resume make_content.py for this project"
    return {"project": project.name, "stage": stage, "next": next_action}


def _projects(root: Path, limit: int = 40) -> List[Dict[str, Any]]:
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith("_") and (child / "receipts").is_dir():
            out.append(_project_stage(child))
        if len(out) >= limit:
            break
    return out


def _platforms() -> Dict[str, int]:
    data = _read_json(ROOT / "config" / "registry" / "platforms.json") or {}
    return dict(Counter(str(p.get("status")) for p in (data.get("platforms") or [])))


def _latest_hotspots() -> Dict[str, Any]:
    log = ROOT / ".local" / "content-router" / "observation" / "daily.jsonl"
    if not log.is_file():
        return {"state": "NONE", "detail": "no local hotspot capture yet"}
    last = None
    try:
        for line in log.read_text(encoding="utf-8").splitlines():
            if line.strip():
                last = json.loads(line)
    except (OSError, ValueError):
        return {"state": "UNREADABLE", "detail": str(log)}
    if not last:
        return {"state": "EMPTY"}
    return {"state": "OK", "observed_at": last.get("observed_at") or last.get("date"),
            "fetched": last.get("fetched"), "source": last.get("adapter") or last.get("source")}


def build(data_dir: Path, projects_root: Path) -> Dict[str, Any]:
    return {
        "schema": "contentops.ops-brief/v1",
        "date": date.today().isoformat(),
        "editorial": _editorial_queue(data_dir),
        "projects": _projects(projects_root),
        "platforms": _platforms(),
        "hotspots": _latest_hotspots(),
        "external_action": "none",
        "publish_authorized": False,
    }


def _next_steps(brief: Dict[str, Any]) -> List[str]:
    steps = []
    ed = brief["editorial"]
    for decision, hint in (("NEEDS_SCORING", "score it: editorial_ops score --candidate <id> ..."),
                           ("NEEDS_EVIDENCE", "add a source_url, then score"),
                           ("CANDIDATE", "research + copy review, then make_content.py")):
        items = [q for q in ed.get("queue", []) if q.get("decision") == decision]
        for item in items[:3]:
            steps.append(f"[{decision}] {item.get('topic')} — {hint}")
    for project in brief["projects"]:
        if project["stage"] in ("AWAITING_REVIEW", "RENDERED", "APPROVED"):
            steps.append(f"[{project['stage']}] {project['project']} — {project['next']}")
    if brief["hotspots"].get("state") != "OK":
        steps.append(f"[HOTSPOTS] {brief['hotspots'].get('state')} — run router_schedule or content_route")
    if not steps:
        steps.append("nothing waiting: import hotspots or create a topic with editorial_ops quick-create")
    return steps


def render_text(brief: Dict[str, Any]) -> str:
    ed = brief["editorial"]
    lines = [f"=== ContentOps 今日运营简报 · {brief['date']} ===", ""]
    if ed.get("state") == "UNAVAILABLE":
        lines.append(f"[选题] 无法读取账本：{ed.get('detail')}")
    else:
        counts = ed.get("by_decision") or {}
        lines.append("[选题] " + (" · ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "空"))
        for item in ed.get("queue", [])[:5]:
            lines.append(f"  - {item.get('decision'):<16} {item.get('topic')}  ({item.get('next_gate')})")
        if ed.get("calendar"):
            lines.append("[排期] " + " · ".join(f"{d}:{n}" for d, n in ed["calendar"].items()))
    projects = brief["projects"]
    lines.append(f"[项目] {len(projects)} 个")
    for project in projects[:10]:
        lines.append(f"  - {project['project']:<34} {project['stage']:<16} next: {project['next']}")
    lines.append("[平台] " + " · ".join(f"{k}={v}" for k, v in sorted(brief["platforms"].items())))
    hot = brief["hotspots"]
    if hot.get("state") == "OK":
        lines.append(f"[热点] 最新采集 {hot.get('observed_at')} · {hot.get('fetched')} 条 · {hot.get('source')}")
    else:
        lines.append(f"[热点] {hot.get('state')} · {hot.get('detail', '')}")
    lines.append("")
    lines.append("[下一步]")
    for i, step in enumerate(_next_steps(brief), 1):
        lines.append(f"  {i}. {step}")
    lines.append("")
    lines.append("（只读简报：不审批、不发布、不产生付费调用）")
    return "\n".join(lines)


def render_html(brief: Dict[str, Any]) -> str:
    from html import escape
    rows = "".join(
        f"<tr><td>{escape(p['project'])}</td><td>{escape(p['stage'])}</td>"
        f"<td>{escape(p['next'])}</td></tr>" for p in brief["projects"])
    steps = "".join(f"<li>{escape(s)}</li>" for s in _next_steps(brief))
    qrows = "".join(
        f"<tr><td>{escape(str(q.get('topic')))}</td><td>{escape(str(q.get('decision')))}</td>"
        f"<td>{escape(str(q.get('next_gate')))}</td></tr>"
        for q in brief["editorial"].get("queue", []))
    return f"""<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8">
<title>ContentOps 今日运营简报 {escape(brief['date'])}</title>
<style>body{{font:15px system-ui;margin:2rem;color:#202b31;background:#f7f9fc}}
h1{{font-size:22px}}table{{border-collapse:collapse;width:100%;background:#fff;margin:.6rem 0}}
td,th{{padding:.55rem;border:1px solid #dde3ea;text-align:left}}th{{background:#eef2f7}}</style>
<h1>ContentOps 今日运营简报 · {escape(brief['date'])}</h1>
<p>只读总览：不审批、不发布、不产生付费调用。</p>
<h2>选题队列</h2><table><tr><th>Topic</th><th>Decision</th><th>Next</th></tr>{qrows}</table>
<h2>项目阶段</h2><table><tr><th>项目</th><th>阶段</th><th>下一步</th></tr>{rows}</table>
<h2>下一步</h2><ol>{steps}</ol></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only daily operations briefing")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--projects", type=Path, default=DEFAULT_PROJECTS)
    parser.add_argument("--html", default="", help="also write a static html page")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    brief = build(args.data_dir, args.projects)
    if args.json:
        print(json.dumps(brief, ensure_ascii=False, indent=2))
    else:
        print(render_text(brief))
    if args.html:
        Path(args.html).write_text(render_html(brief), encoding="utf-8")
        print(f"\nHTML: {args.html}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
