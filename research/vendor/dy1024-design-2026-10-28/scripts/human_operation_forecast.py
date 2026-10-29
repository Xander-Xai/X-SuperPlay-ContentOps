#!/usr/bin/env python3
"""Forecast and gate human operations before a topic enters production.

The forecast is intentionally a separate, reviewable artifact.  It predicts
what the operator must do, what must be visible on screen, and which local
preconditions can block the experiment.  It never claims that a model or
service has been successfully run.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ACCOUNT = "X•超玩1024"
SCHEMA_VERSION = 1


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_available(name: str) -> bool:
    return bool(shutil.which(name))


def gpu_receipt() -> dict[str, Any]:
    if not command_available("nvidia-smi"):
        return {"status": "unknown", "reason": "nvidia-smi is unavailable", "gpus": []}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "unknown", "reason": str(error), "gpus": []}
    if result.returncode != 0:
        return {"status": "unknown", "reason": (result.stderr or "nvidia-smi failed").strip(), "gpus": []}
    gpus = []
    for line in (result.stdout or "").splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            total = float(parts[1]) / 1024
            free = float(parts[2]) / 1024
        except ValueError:
            continue
        gpus.append({"name": parts[0], "memory_total_gb": round(total, 2), "memory_free_gb": round(free, 2)})
    return {"status": "ready" if gpus else "unknown", "reason": "", "gpus": gpus}


def path_check(value: Any) -> dict[str, Any]:
    raw = os.path.expandvars(str(value or "")).strip()
    if not raw:
        return {"path": "", "exists": False}
    path = Path(raw).expanduser()
    return {"path": str(path), "exists": path.exists(), "is_file": path.is_file(), "is_dir": path.is_dir()}


def local_runtime_receipt(root: Path) -> dict[str, Any]:
    runtime_path = root / "local-runtime.json"
    if not runtime_path.is_file() and (root / "dy_1024" / "local-runtime.json").is_file():
        runtime_path = root / "dy_1024" / "local-runtime.json"
    if not runtime_path.is_file():
        return {"status": "unknown", "path": str(runtime_path), "components": {}}
    try:
        payload = load(runtime_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"status": "blocked", "path": str(runtime_path), "components": {}, "reason": str(error)}
    components = {}
    for key in ("index_tts", "funasr", "minimax_h3", "openchatcut"):
        item = payload.get(key) if isinstance(payload.get(key), dict) else {}
        checks = {}
        for field in ("root", "python"):
            if item.get(field):
                checks[field] = path_check(item[field])
        components[key] = {"checks": checks, "configured": bool(item)}
    return {"status": "ready", "path": str(runtime_path), "components": components, "reason": ""}


def operation(
    operation_id: str,
    phase: str,
    title: str,
    human_required: bool,
    surface: list[str],
    preconditions: list[str],
    must_show: list[str],
    must_hide: list[str],
    acceptance: list[str],
    failure_modes: list[dict[str, Any]],
    actions: list[str] | None = None,
    minimum_seconds: float = 5,
) -> dict[str, Any]:
    return {
        "operation_id": operation_id,
        "phase": phase,
        "title": title,
        "human_required": human_required,
        "surface": surface,
        "preconditions": preconditions,
        "actions": actions or [
            "先展示输入条件和任务目标",
            "按一个可复现顺序执行主操作，不剪掉关键等待或错误",
            "停留在结果或原始错误画面，并记录来源/文件名",
        ],
        "screen_recording": {
            "required": human_required,
            "must_show": must_show,
            "must_hide": must_hide,
            "minimum_seconds": minimum_seconds,
        },
        "acceptance_criteria": acceptance,
        "failure_modes": failure_modes,
    }


def evaluate_resource_requirements(
    item: dict[str, Any], gpu: dict[str, Any], blocking: list[str], warnings: list[str]
) -> None:
    """Evaluate only explicitly declared, machine-checkable requirements.

    The forecast never infers a requirement from the topic title.  Unknown
    requirement kinds stay as human-review preconditions instead of becoming a
    guessed implementation branch.
    """
    requirements = item.get("resource_requirements")
    if not isinstance(requirements, list):
        return
    for requirement in requirements:
        if not isinstance(requirement, dict):
            warnings.append("resource_requirements contains a non-object item; it was ignored")
            continue
        kind = str(requirement.get("kind", "")).strip()
        if kind not in {"gpu_memory_gb", "gpu_total_memory_gb"}:
            continue
        try:
            minimum = float(requirement.get("minimum", 0))
        except (TypeError, ValueError):
            warnings.append(f"resource requirement {kind} has an invalid minimum")
            continue
        if minimum <= 0:
            warnings.append(f"resource requirement {kind} must have a positive minimum")
            continue
        available = [float(item.get("memory_total_gb", 0)) for item in gpu.get("gpus", [])]
        label = str(requirement.get("label", kind)).strip() or kind
        if not available:
            blocking.append(f"选题声明的资源要求“{label}”需要至少 {minimum:g} GB，但当前无法取得 GPU 容量回执")
        elif max(available) < minimum:
            blocking.append(
                f"选题声明的资源要求“{label}”需要至少 {minimum:g} GB，当前最高仅 {max(available):g} GB；"
                "必须调整资源、方案或改用已接受的替代路线"
            )


def build_forecast(route: dict[str, Any], root: Path, assessment_basis: str = "") -> dict[str, Any]:
    topic = str(route.get("topic", "")).strip()
    content_id = str(route.get("content_id", "")).strip() or "unallocated"
    content_type = str(route.get("content_type", "")).strip() or "tool_test"
    gpu = gpu_receipt()
    runtime = local_runtime_receipt(root)
    blocking: list[str] = []
    warnings: list[str] = []
    operations = [
        operation(
            "topic-evidence-review", "research", "核对热点来源和选题边界", True,
            ["PowerShell", "浏览器", "来源 JSON"],
            ["热点报告或用户提供的选题", "公开来源 URL", "无敏感凭据窗口"],
            ["查询词", "来源 URL", "标题/日期", "候选被保留或淘汰的理由"],
            ["Cookie", "Token", "私人文件", "未授权账号页面"],
            ["每条保留候选都有可访问来源", "选题能映射到一个账号支柱", "无来源候选被标记为淘汰"],
            [{"failure": "来源打不开", "action": "记录失败并换主信源", "blocks": False}],
        ),
        operation(
            "runtime-screen-recording", "evidence", "录制真实产品/终端操作", True,
            ["浏览器", "PowerShell", "目标产品 UI"],
            ["产品可访问", "操作账号/权限已确认", "录屏工具已准备"],
            ["输入条件", "关键操作", "结果", "错误或边界", "可复现的结束状态"],
            ["密码", "Token", "私人聊天", "系统通知", "无关桌面内容"],
            ["画面能证明实际操作而非静态截图", "结果与旁白 claim 一一对应", "失败样本没有被剪掉"],
            [{"failure": "登录/权限不足", "action": "改为公开演示或降级为研究线索", "blocks": True}],
            minimum_seconds=8,
        ),
        operation(
            "human-visual-review", "review", "人工检查证据画面和安全区", True,
            ["视频预览", "手机视口/编辑器"],
            ["录屏或素材已生成", "无敏感信息", "画面可读"],
            ["字幕", "关键数值", "操作结果", "错误提示", "CTA/安全区"],
            ["未授权素材", "私人数据", "调试叠层", "旧版本画面"],
            ["用户明确接受画面和录屏负担", "重要证据没有被生成卡片替代"],
            [{"failure": "画面无法证明 claim", "action": "退回重新录制或改写 claim", "blocks": True}],
        ),
    ]
    # Topic-specific operations are data, not workflow code.  The agent or
    # user may declare them in route.operation_requirements or an input JSON;
    # omitted requirements do not create model/GPU/MCP branches implicitly.
    declared = route.get("operation_requirements") if isinstance(route.get("operation_requirements"), list) else []
    for item in declared:
        if not isinstance(item, dict):
            warnings.append("operation_requirements contains a non-object item; it was ignored")
            continue
        required = bool(item.get("human_required", True))
        evaluate_resource_requirements(item, gpu, blocking, warnings)
        declared_operation = operation(
            str(item.get("operation_id", "declared-operation")).strip() or "declared-operation",
            str(item.get("phase", "topic-specific")).strip() or "topic-specific",
            str(item.get("title", "选题特定操作")).strip() or "选题特定操作",
            required,
            [str(value) for value in item.get("surface", [])] if isinstance(item.get("surface"), list) else ["用户指定界面"],
            [str(value) for value in item.get("preconditions", [])] if isinstance(item.get("preconditions"), list) else ["选题要求已明确"],
            [str(value) for value in item.get("must_show", [])] if isinstance(item.get("must_show"), list) else ["输入、操作、结果或原始错误"],
            [str(value) for value in item.get("must_hide", [])] if isinstance(item.get("must_hide"), list) else ["密码、Token、私人数据"],
            [str(value) for value in item.get("acceptance_criteria", [])] if isinstance(item.get("acceptance_criteria"), list) else ["操作可执行且结果可复核"],
            item.get("failure_modes", []) if isinstance(item.get("failure_modes"), list) else [{"failure": "操作失败", "action": "记录原因并回到选题判断", "blocks": True}],
            [str(value) for value in item.get("actions", [])] if isinstance(item.get("actions"), list) else None,
        )
        if isinstance(item.get("resource_requirements"), list):
            declared_operation["resource_requirements"] = item["resource_requirements"]
        operations.append(declared_operation)
    automatic = [
        "生成来源清单、去重和证据字段草稿",
        "根据选题类型生成初步脚本/音频/素材责任分配计划",
        "为每个人工 beat 生成录屏清单、命名和验收条件",
        "在收到录屏后执行来源、技术和画面 QC",
    ]
    basis = str(assessment_basis or route.get("operation_assessment_basis", "")).strip()
    meaningful_declared = [
        item for item in declared
        if isinstance(item, dict) and (str(item.get("operation_id", "")).strip() or str(item.get("title", "")).strip())
    ]
    assessment_status = "complete" if basis or meaningful_declared else "missing"
    if assessment_status == "missing":
        blocking.append("选题特定人工操作判断依据缺失；必须声明额外操作，或明确说明为什么不需要额外操作")
    human_count = sum(1 for item in operations if item["human_required"])
    level = "block" if blocking else ("warn" if warnings else "pass")
    status = "blocked" if blocking else "ready"
    return {
        "schema_version": SCHEMA_VERSION,
        "content_id": content_id,
        "account": str(route.get("account", ACCOUNT)),
        "route_id": str(route.get("route_id", "")),
        "topic_mode": str(route.get("topic_mode", "")),
        "content_type": content_type,
        "topic": topic,
        "generated_at": now(),
        "environment": {"platform": platform.platform(), "python": platform.python_version(), "gpu": gpu, "local_runtime": runtime},
        "risk_summary": {"level": level, "blocking_reasons": blocking, "warnings": warnings},
        "topic_specific_assessment": {"status": assessment_status, "basis": basis},
        "declared_operation_requirements": meaningful_declared,
        "human_operation_count": human_count,
        "operations": operations,
        "automatic_operations": automatic,
        "human_acceptance": {"status": "pending", "reviewer": "", "accepted_at": "", "note": ""},
        "status": status,
        "notes": ["这是可行性预判，不是模型成功回执；接受后仍需按人工操作手册录制并回传证据。"],
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# 人工操作可行性预判：{report.get('topic', '')}",
        "",
        f"- 状态：`{report.get('status', '')}`",
        f"- 风险：`{report.get('risk_summary', {}).get('level', '')}`",
        f"- 人工操作数：`{report.get('human_operation_count', 0)}`",
        f"- 选题特定判断：`{(report.get('topic_specific_assessment') or {}).get('status', '')}`",
        "",
        "## 先决结论",
        "",
        "这是操作预判，不是成功证明。只有用户接受后，选题才能进入 Brief；完成录屏并回传后，工作流才会继续使用真实证据。",
        "",
        "## 阻断与警告",
        "",
    ]
    summary = report.get("risk_summary", {}) if isinstance(report.get("risk_summary"), dict) else {}
    for item in summary.get("blocking_reasons", []):
        lines.append(f"- BLOCK：{item}")
    for item in summary.get("warnings", []):
        lines.append(f"- WARN：{item}")
    lines.extend(["", "## 人工操作清单", ""])
    for index, item in enumerate(report.get("operations", []), 1):
        screen = item.get("screen_recording", {})
        lines.extend([
            f"### {index}. {item.get('title', '')}",
            f"- operation_id：`{item.get('operation_id', '')}`",
            f"- 阶段：`{item.get('phase', '')}`；人工完成：`{item.get('human_required')}`",
            f"- 操作界面：{', '.join(item.get('surface', []))}",
            f"- 前置条件：{'；'.join(item.get('preconditions', []))}",
            "- 实操步骤：" + "；".join(item.get("actions", [])),
            f"- 录屏至少保留：{'；'.join(screen.get('must_show', []))}",
            f"- 必须隐藏：{'；'.join(screen.get('must_hide', []))}",
            f"- 验收条件：{'；'.join(item.get('acceptance_criteria', []))}",
            "- 失败处理：" + "；".join(f"{x.get('failure')} → {x.get('action')}" for x in item.get("failure_modes", [])),
            "",
        ])
    lines.extend(["## 自动完成项", "", *[f"- {item}" for item in report.get("automatic_operations", [])], ""])
    return "\n".join(lines)


def cmd_draft(args: argparse.Namespace) -> int:
    route = load(Path(args.route).expanduser().resolve())
    if args.requirements_json:
        requirements = json.loads(Path(args.requirements_json).expanduser().resolve().read_text(encoding="utf-8"))
        if isinstance(requirements, dict):
            requirements = requirements.get("operations", [])
        if not isinstance(requirements, list):
            raise SystemExit("--requirements-json must contain a JSON list or an object with an operations list")
        route["operation_requirements"] = requirements
    if args.assessment_basis:
        route["operation_assessment_basis"] = args.assessment_basis.strip()
    report = build_forecast(route, Path(args.workflow_root).expanduser().resolve(), args.assessment_basis)
    output = Path(args.output).expanduser().resolve()
    guide = Path(args.guide_output).expanduser().resolve() if args.guide_output else output.with_suffix(".md")
    write(output, report)
    guide.parent.mkdir(parents=True, exist_ok=True)
    guide.write_text(markdown(report).rstrip() + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "guide": str(guide), "status": report["status"], "risk": report["risk_summary"]}, ensure_ascii=False, indent=2))
    return 0 if report["status"] != "blocked" else 1


def cmd_check(args: argparse.Namespace) -> int:
    report = load(Path(args.input).expanduser().resolve())
    errors: list[str] = []
    for field in ("content_id", "account", "topic", "route_id", "topic_mode", "status", "risk_summary", "topic_specific_assessment", "operations", "human_acceptance"):
        if field not in report:
            errors.append(f"missing {field}")
    if report.get("account") != ACCOUNT:
        errors.append("account must be X•超玩1024")
    if not isinstance(report.get("operations"), list) or not report.get("operations"):
        errors.append("operations must be a non-empty list")
    if report.get("risk_summary", {}).get("level") == "block" and report.get("status") not in {"blocked", "rejected"}:
        errors.append("blocked risk cannot be marked ready")
    assessment = report.get("topic_specific_assessment") if isinstance(report.get("topic_specific_assessment"), dict) else {}
    if report.get("status") in {"ready", "accepted"} and assessment.get("status") != "complete":
        errors.append("topic_specific_assessment must be complete before acceptance")
    print(json.dumps({"input": str(Path(args.input).expanduser().resolve()), "passed": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


def cmd_decide(args: argparse.Namespace, status: str) -> int:
    path = Path(args.input).expanduser().resolve()
    report = load(path)
    if status == "accepted" and report.get("risk_summary", {}).get("level") == "block":
        raise SystemExit("blocked feasibility forecast cannot be accepted; resolve the blocking precondition first")
    assessment = report.get("topic_specific_assessment") if isinstance(report.get("topic_specific_assessment"), dict) else {}
    if status == "accepted" and assessment.get("status") != "complete":
        raise SystemExit("topic-specific assessment is incomplete; provide --assessment-basis or declared operations before acceptance")
    if not args.confirm:
        raise SystemExit("human decision requires --confirm")
    if not args.reviewer.strip():
        raise SystemExit("--reviewer is required")
    route_path = Path(args.route).expanduser().resolve() if args.route else None
    if route_path:
        route = load(route_path)
        identity_fields = ("content_id", "account", "topic", "route_id", "topic_mode")
        mismatches = [
            key for key in identity_fields
            if not str(report.get(key, "")).strip() or str(report.get(key)) != str(route.get(key, ""))
        ]
        if mismatches:
            raise SystemExit("forecast does not belong to the selected route: " + ", ".join(mismatches))
    report["status"] = status
    report["human_acceptance"] = {
        "status": status,
        "reviewer": args.reviewer.strip(),
        "accepted_at": now(),
        "note": str(args.note or "").strip(),
    }
    write(path, report)
    if route_path:
        route["operation_assessment_basis"] = str((report.get("topic_specific_assessment") or {}).get("basis", "")).strip()
        route["operation_requirements"] = report.get("declared_operation_requirements", route.get("operation_requirements", []))
        route["operation_forecast"] = {
            "status": status,
            "report": str(path),
            "guide": str(Path(args.guide or path.with_suffix(".md")).expanduser().resolve()),
            "reviewer": args.reviewer.strip(),
            "decided_at": report["human_acceptance"]["accepted_at"],
            "note": report["human_acceptance"]["note"],
        }
        write(route_path, route)
    print(json.dumps({"input": str(path), "status": status, "route_updated": bool(route_path)}, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Forecast and gate human operations before production.")
    sub = root.add_subparsers(dest="command", required=True)
    draft = sub.add_parser("draft")
    draft.add_argument("--route", required=True)
    draft.add_argument("--output", required=True)
    draft.add_argument("--guide-output", default="")
    draft.add_argument("--workflow-root", default=str(Path(__file__).resolve().parents[1]))
    draft.add_argument("--requirements-json", default="", help="optional JSON list/object declaring topic-specific operations")
    draft.add_argument("--assessment-basis", default="", help="why this topic does or does not need extra human operations")
    draft.set_defaults(handler=cmd_draft)
    check = sub.add_parser("check")
    check.add_argument("--input", required=True)
    check.set_defaults(handler=cmd_check)
    for name, status in (("accept", "accepted"), ("reject", "rejected")):
        decision = sub.add_parser(name)
        decision.add_argument("--input", required=True)
        decision.add_argument("--route", default="")
        decision.add_argument("--guide", default="")
        decision.add_argument("--reviewer", required=True)
        decision.add_argument("--note", default="")
        decision.add_argument("--confirm", action="store_true")
        decision.set_defaults(handler=lambda args, value=status: cmd_decide(args, value))
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
