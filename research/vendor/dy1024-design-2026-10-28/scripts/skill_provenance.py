#!/usr/bin/env python3
"""Record and audit execution evidence for routed external skills.

Skill files are declarative instructions, so this tool records the concrete
invocation and artifacts produced by the agent or adapter that followed them.
It never stores credentials or raw prompt contents; only paths, hashes and
short operator notes are persisted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from console_encoding import configure_utf8_stdio
except ImportError:  # imported as scripts.skill_provenance
    from scripts.console_encoding import configure_utf8_stdio

configure_utf8_stdio()

try:
    from plugin_runtime import approved_skill_roots, plugin_metadata, skill_path as plugin_skill_path
except ModuleNotFoundError:  # pragma: no cover - package-style imports
    from scripts.plugin_runtime import approved_skill_roots, plugin_metadata, skill_path as plugin_skill_path


ROOT = Path(__file__).resolve().parents[1]
INTERNAL_ROUTES = {
    "account-router", "compile-short-video", "design-direction", "media-delivery",
    "runtime-media", "source-collector", "rights-audit", "delivery-package",
    "publish-feedback", "douyin-sidecar-publish", "douyin-creator-sidecar", "creator-ops-sidecar",
    "visual-route", "content-strategy",
    # Provider outputs are recorded by the durable generation receipt layer.
    "chatgpt-bridge", "bridge-xiaohei", "bridge-concept", "gflow-cli",
}
CORE_REAL_ROUTES = {
    "content-copy-orchestrator",
    "script-to-tts",
    "speech-to-text",
    "video-shotcraft",
    "remotion-captions",
    "index-tts",
    "openchatcut",
    # Visual routes are execution capabilities, not decorative suggestions.
    # If a scene selects one, the agent must record the real renderer command
    # and its output fingerprint before the assets/quality gates can pass.
    "beautiful-mermaid",
    "latex-formatting",
    "manim-video",
    "cs-board-whiteboard",
    "baoyu-infographic",
    "playwright",
    "media-use",
    "material-source-research",
    "broll-production",
    "hyperframes",
    "remotion",
    "ian-xiaohei-illustrations",
    "ian-xiaohei-scenes",
}
# Creative copywriting can be executed interactively by an agent rather than
# through a deterministic subprocess.  It still requires a skill file, a
# hashed output artifact, and an operator note; this is auditable manual
# evidence, not an unverified declaration.  Keep the exception explicit so
# rendering/model routes remain real-command-only.
MANUAL_PROOF_ROUTES = {"content-copy-orchestrator"}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def digest(path: Path) -> str:
    if not path.is_file():
        return "missing"
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def resolve_artifact(project: Path, value: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("artifact path is empty")
    path = Path(raw).expanduser()
    if path.is_absolute():
        resolved = path.resolve()
    else:
        resolved = (project.resolve() / path).resolve()
    try:
        resolved.relative_to(project.resolve())
    except ValueError as error:
        raise ValueError(f"provenance artifact path escapes project: {raw}") from error
    return resolved


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as error:
        raise SystemExit(f"invalid or missing {label}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit(f"{label} must be a JSON object")
    return value


def project_files(project: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    manifest = load_json(project / "content.json", "content.json")
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    output = resolve_artifact(project, str(paths.get("skill_provenance", "05_publish/skill-provenance.json")))
    report = load_json(output, "skill provenance report") if output.is_file() else {
        "schema_version": 1,
        "content_id": manifest.get("content_id", ""),
        "account": manifest.get("account", ""),
        "status": "pending",
        "passed": False,
        "required_routes": [],
        "records": [],
        "errors": [],
        "warnings": [],
    }
    return manifest, output, report


def collect_routes(value: Any, key: str = "") -> list[str]:
    if key == "no_text_routes":
        return []
    routes: list[str] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            routes.extend(collect_routes(child, str(child_key)))
    elif isinstance(value, list) and key.endswith("routes"):
        routes.extend(str(item).strip().lower() for item in value if str(item).strip())
    return routes


def route_available(route: str) -> bool:
    if route in INTERNAL_ROUTES:
        return True
    candidates = [route]
    if route == "remotion":
        candidates = ["remotion", "remotion-best-practices", "remotion-create", "remotion-render"]
    elif route == "hyperframes":
        candidates = ["hyperframes", "hyperframes-core", "hyperframes-animation"]
    if route in {"hyperframes", "remotion"} and plugin_skill_path(route):
        return True
    return any((ROOT / "skills" / candidate).is_dir() and any((ROOT / "skills" / candidate).rglob("SKILL.md")) for candidate in candidates)


def skill_candidates(route: str) -> set[str]:
    """Return local directory names allowed to prove a public route."""
    candidates = {route}
    if route == "remotion":
        candidates.update({"remotion-best-practices", "remotion-create", "remotion-render"})
    elif route == "hyperframes":
        candidates.update({"hyperframes", "hyperframes-core", "hyperframes-animation"})
    return {value.lower() for value in candidates}


def default_skill_path(route: str) -> Path | None:
    """Resolve the canonical local SKILL.md when the CLI omits it."""
    if route in {"hyperframes", "remotion"}:
        plugin_path = plugin_skill_path(route)
        if plugin_path is not None:
            return plugin_path
    root = (ROOT / "skills").resolve()
    for candidate in sorted(skill_candidates(route)):
        candidate_root = root / candidate
        if not candidate_root.is_dir():
            continue
        for path in sorted(candidate_root.rglob("SKILL.md")):
            if any(part.lower() in {".git", ".venv", "node_modules", "__pycache__"} for part in path.relative_to(root).parts):
                continue
            if path.parent.name.lower() not in skill_candidates(route):
                continue
            return path.resolve()
    return None


def valid_skill_binding(route: str, item: dict[str, Any]) -> tuple[bool, str]:
    """Require a current, local, route-matching skill file and hash."""
    if route in INTERNAL_ROUTES:
        return True, ""
    raw_path = str(item.get("skill_path", "")).strip()
    raw_hash = str(item.get("skill_sha256", "")).strip().lower()
    if not raw_path or not raw_hash or raw_hash == "missing":
        return False, f"{route}: skill_path and skill_sha256 are required"
    path = Path(raw_path).expanduser().resolve()
    skill_root = (ROOT / "skills").resolve()
    allowed_roots = [skill_root]
    if route in {"hyperframes", "remotion"}:
        allowed_roots.extend(approved_skill_roots(route))
    if not any(path == root or root in path.parents for root in allowed_roots):
        return False, f"{route}: skill_path escapes the isolated local skill root or approved plugin roots"
    if not path.is_file() or path.name.lower() != "skill.md":
        return False, f"{route}: skill_path is not a local SKILL.md"
    if route in {"hyperframes", "remotion"} and path == plugin_skill_path(route):
        return True, ""
    if path.parent.name.lower() not in skill_candidates(route):
        return False, f"{route}: skill_path does not match the routed skill"
    if digest(path) != raw_hash:
        return False, f"{route}: skill_sha256 does not match skill_path"
    return True, ""


def visual_route_replacements(project: Path) -> dict[str, str]:
    """Map unavailable preferred visual skills to an installed fallback."""
    path = project / "04_video" / "visual-route.json"
    if not path.is_file():
        return {}
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    replacements: dict[str, str] = {}
    for item in report.get("routes", []) if isinstance(report, dict) and isinstance(report.get("routes"), list) else []:
        if not isinstance(item, dict):
            continue
        fallbacks = [str(value).strip().lower() for value in item.get("fallback_routes", []) if str(value).strip() and str(value).strip() != "blocked-awaiting-real-capture"]
        fallback = next((value for value in fallbacks if route_available(value)), "")
        if not fallback:
            continue
        for primary in item.get("skill_routes", []) if isinstance(item.get("skill_routes"), list) else []:
            value = str(primary).strip().lower()
            if value and not route_available(value):
                replacements[value] = fallback
    return replacements


def _append_route_values(target: set[str], value: Any) -> None:
    """Add non-empty route values without treating declarations as execution."""
    if isinstance(value, (list, tuple, set)):
        target.update(str(item).strip().lower() for item in value if str(item).strip())
    elif isinstance(value, str) and value.strip():
        target.add(value.strip().lower())


def _active_routes(project: Path, plan: dict[str, Any]) -> set[str]:
    """Collect routes that this package can actually activate.

    Profile ``allowed_routes`` and top-level route inventories describe
    capability, not execution.  Only required execution stages and concrete
    package artifacts (selected visual scenes, ready material plans, or an
    enabled image plan) are provenance obligations.
    """
    routes: set[str] = set()
    stages = plan.get("required_execution_stages") if isinstance(plan.get("required_execution_stages"), dict) else {}
    for stage in stages.values():
        if not isinstance(stage, dict) or stage.get("required") is not True:
            continue
        _append_route_values(routes, stage.get("routes"))
    # Older/fixture execution plans may not yet have the normalized stage
    # map.  Preserve their explicit stage-owned route arrays, while still
    # ignoring profile capability inventories such as image_policy.allowed_routes.
    if not stages:
        video_plan = plan.get("video") if isinstance(plan.get("video"), dict) else {}
        for key in (
            "research_routes",
            "strategy_routes",
            "script_routes",
            "runtime_routes",
            "design_routes",
            "asset_routes",
            "visual_routes",
            "motion_routes",
            "delivery_routes",
            "image_routes",
        ):
            _append_route_values(routes, plan.get(key))
            _append_route_values(routes, video_plan.get(key))

    visual_path = project / "04_video" / "visual-route.json"
    if visual_path.is_file():
        try:
            visual = load_json(visual_path, "visual route")
        except (OSError, json.JSONDecodeError):
            visual = {}
        for item in visual.get("routes", []) if isinstance(visual.get("routes"), list) else []:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "")).strip().lower() not in {"ready", "executed"}:
                continue
            _append_route_values(routes, item.get("skill_routes"))
            _append_route_values(routes, item.get("fallback_routes"))

    image_path = project / "03_assets" / "image-prompt-plan.json"
    if image_path.is_file():
        try:
            image_plan = load_json(image_path, "image prompt plan")
        except (OSError, json.JSONDecodeError):
            image_plan = {}
        if image_plan.get("status") in {"ready", "executed", "blocked-awaiting-human-decision"}:
            for item in image_plan.get("items", []) if isinstance(image_plan.get("items"), list) else []:
                if not isinstance(item, dict):
                    continue
                _append_route_values(routes, item.get("skill_routes"))
                _append_route_values(routes, item.get("skill_route"))
                _append_route_values(routes, item.get("provider_skill"))

    for relative in ("04_video/broll-plan.json", "03_assets/source-candidates.json"):
        path = project / relative
        if not path.is_file():
            continue
        try:
            payload = load_json(path, relative)
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") not in {"ready", "approved", "selected", "acquired", "promoted"}:
            continue
        _append_route_values(routes, payload.get("route"))
        _append_route_values(routes, payload.get("automation_owner"))
        _append_route_values(routes, payload.get("routes"))
        # B-roll plans own beat-level automation routes under ``beats``;
        # source-candidate manifests use ``candidates`` and image/material
        # adapters may use ``items``. Treat all three as concrete artifact
        # route evidence once the plan is ready.
        item_values = payload.get("items", payload.get("candidates", payload.get("beats", [])))
        for item in item_values if isinstance(item_values, list) else []:
            if isinstance(item, dict):
                # In a B-roll plan, ``route`` is a visual delivery route such
                # as product-ui/concept-motion, not a skill provenance route.
                # Candidate manifests retain their route field as a source
                # adapter declaration.
                if relative != "04_video/broll-plan.json":
                    _append_route_values(routes, item.get("route"))
                _append_route_values(routes, item.get("automation_owner"))
    return routes


def required_routes(manifest: dict[str, Any]) -> list[str]:
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    project = Path(manifest.get("_project_path", "."))
    plan_path = resolve_artifact(project, str(paths.get("execution_plan", "00_brief/execution-plan.json")))
    if not plan_path.is_file():
        return []
    plan = load_json(plan_path, "execution plan")
    replacements = visual_route_replacements(project)
    routes = {route for route in _active_routes(project, plan) if route not in INTERNAL_ROUTES}
    resolved = {replacements.get(route, route) for route in routes}
    return sorted(resolved)


def write(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def audit(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest, output, report = project_files(project)
    manifest["_project_path"] = str(project)
    required = required_routes(manifest)
    report["required_routes"] = required
    report["content_id"] = manifest.get("content_id", "")
    report["account"] = manifest.get("account", "")
    records = report.get("records", []) if isinstance(report.get("records"), list) else []
    successful: set[str] = set()
    # A route can legitimately have several receipts (authoring, prepare,
    # render). Older receipts become stale when a later prepare rewrites the
    # same source files; that history must not invalidate a newer successful
    # receipt. Keep the diagnostic per route and only surface it if no valid
    # real record exists for that route at all.
    invalid_required_routes: set[str] = set()
    binding_errors: set[str] = set()
    blocked_tokens: set[str] = set()
    policy_path = ROOT / "local-media-policy.json"
    if policy_path.is_file():
        try:
            media_policy = json.loads(policy_path.read_text(encoding="utf-8"))
            blocked_tokens = {str(value).strip().lower() for value in media_policy.get("blocked_provider_tokens", []) if str(value).strip()}
        except (OSError, json.JSONDecodeError):
            binding_errors.add("local-media-policy.json is invalid or unreadable")
    for item in records:
        if not isinstance(item, dict) or item.get("status") != "success":
            continue
        route = str(item.get("route", "")).lower()
        command_text = str(item.get("command", "")).lower()
        for token in blocked_tokens:
            if token in command_text:
                binding_errors.add(f"{route}: command contains blocked provider token {token}")
        # A declarative skill declaration is not proof that the skill ran. A
        # real record needs the invoked command, a zero exit code, and at
        # least one output whose current fingerprint was captured. There are
        # no stage-name exceptions: a production route cannot be disguised as
        # a test record.
        execution_mode = str(item.get("execution_mode", "declarative"))
        outputs = item.get("outputs", []) if isinstance(item.get("outputs"), list) else []
        output_records = [output for output in outputs if isinstance(output, dict)]
        outputs_exist = bool(output_records) and all(
            str(output.get("sha256", "")) not in {"", "missing"}
            and Path(str(output.get("path", ""))).is_file()
            and digest(Path(str(output.get("path")))) == str(output.get("sha256"))
            for output in output_records
        )
        try:
            exit_code = int(item.get("exit_code", 1))
        except (TypeError, ValueError):
            exit_code = 1
        binding_ok, binding_error = valid_skill_binding(route, item)
        if not binding_ok:
            binding_errors.add(binding_error)
        manual_evidence = (
            execution_mode == "manual"
            and (route not in CORE_REAL_ROUTES or route in MANUAL_PROOF_ROUTES)
            and binding_ok
            and outputs_exist
            and bool(str(item.get("note", "")).strip())
        )
        valid_real = execution_mode == "real" and binding_ok and str(item.get("command", "")).strip() and exit_code == 0 and outputs_exist
        if valid_real or manual_evidence:
            successful.add(route)
        elif route in required:
            invalid_required_routes.add(route)
    errors = [f"skill route has no successful execution record: {route}" for route in required if route not in successful]
    errors.extend(f"skill route binding is invalid: {error}" for error in sorted(binding_errors))
    errors.extend(
        f"skill route execution lacks real evidence: {route}"
        for route in sorted(invalid_required_routes)
        if route not in successful
    )
    report["errors"] = errors
    report["binding_errors"] = sorted(binding_errors)
    report["warnings"] = []
    report["status"] = "ready" if not errors else "blocked"
    report["passed"] = not errors
    write(output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def init(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load_json(project / "content.json", "content.json")
    manifest["_project_path"] = str(project)
    _, output, report = project_files(project)
    report["required_routes"] = required_routes(manifest)
    report["content_id"] = manifest.get("content_id", "")
    report["account"] = manifest.get("account", "")
    write(output, report)
    print(json.dumps({"output": str(output), "required_routes": report["required_routes"]}, ensure_ascii=False, indent=2))
    return 0


def record(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest, output, report = project_files(project)
    manifest["_project_path"] = str(project)
    required = required_routes(manifest)
    route = args.route.strip().lower()
    if route not in required:
        raise SystemExit(f"route is not declared in the execution plan: {route}")
    if args.execution_mode == "manual" and route in CORE_REAL_ROUTES and route not in MANUAL_PROOF_ROUTES:
        raise SystemExit(f"core production route requires real execution evidence: {route}")
    if args.status == "failed" and not args.error.strip():
        raise SystemExit("--error is required for failed skill executions")
    if route not in INTERNAL_ROUTES and args.execution_mode in {"real", "manual"}:
        if not args.skill_path.strip():
            resolved_skill = default_skill_path(route)
            if resolved_skill is not None:
                args.skill_path = str(resolved_skill)
        binding_ok, binding_error = valid_skill_binding(
            route,
            {
                "skill_path": args.skill_path,
                "skill_sha256": digest(Path(args.skill_path).expanduser().resolve()) if args.skill_path.strip() else "",
            },
        )
        if not binding_ok:
            raise SystemExit(binding_error)
    record_value = {
        "route": route,
        "stage": args.stage.strip(),
        "status": args.status,
        "execution_mode": args.execution_mode,
        "command": args.command.strip(),
        "exit_code": args.exit_code,
        "actor": args.actor.strip() or "agent",
        "started_at": args.started_at.strip() or now(),
        "finished_at": args.finished_at.strip() or now(),
        "skill_path": args.skill_path.strip(),
        "skill_sha256": digest(Path(args.skill_path).expanduser().resolve()) if args.skill_path.strip() else "",
        "inputs": [{"path": str(resolve_artifact(project, item)), "sha256": digest(resolve_artifact(project, item))} for item in args.input],
        "outputs": [{"path": str(resolve_artifact(project, item)), "sha256": digest(resolve_artifact(project, item))} for item in args.output],
        "note": args.note.strip(),
        "error": args.error.strip(),
    }
    records = report.setdefault("records", [])
    if not isinstance(records, list):
        records = []
        report["records"] = records
    records.append(record_value)
    report["required_routes"] = required
    report["status"] = "pending"
    report["passed"] = False
    write(output, report)
    print(json.dumps(record_value, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record and audit routed external skill executions.")
    child = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("init", init), ("audit", audit)):
        command = child.add_parser(name)
        command.add_argument("--project", required=True)
        if name == "audit":
            command.add_argument("--strict", action="store_true")
        command.set_defaults(handler=handler)
    record_parser = child.add_parser("record")
    record_parser.add_argument("--project", required=True)
    record_parser.add_argument("--route", required=True)
    record_parser.add_argument("--stage", required=True)
    record_parser.add_argument("--status", choices=["success", "failed", "skipped"], default="success")
    record_parser.add_argument("--execution-mode", choices=["real", "manual", "declarative"], default="declarative")
    record_parser.add_argument("--command", default="", help="Exact command or API operation that was actually invoked")
    record_parser.add_argument("--exit-code", type=int, default=0)
    record_parser.add_argument("--actor", default="agent")
    record_parser.add_argument("--skill-path", default="")
    record_parser.add_argument("--input", action="append", default=[])
    record_parser.add_argument("--output", action="append", default=[])
    record_parser.add_argument("--started-at", default="")
    record_parser.add_argument("--finished-at", default="")
    record_parser.add_argument("--note", default="")
    record_parser.add_argument("--error", default="")
    record_parser.set_defaults(handler=record)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
