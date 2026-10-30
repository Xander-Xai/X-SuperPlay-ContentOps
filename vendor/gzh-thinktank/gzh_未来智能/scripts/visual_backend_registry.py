#!/usr/bin/env python3
"""Shared contracts for deterministic and illustrative visual backends."""

from __future__ import annotations

from typing import Any


BACKENDS: dict[str, dict[str, Any]] = {
    "katex-html-composite": {
        "owner": "diagram",
        "mode": "deterministic",
        "editable_suffix": ".html",
        "technical": True,
        "fallback": "deterministic-math-html",
    },
    "deterministic-svg": {
        "owner": "diagram",
        "mode": "deterministic",
        "editable_suffix": ".svg",
        "technical": False,
        "fallback": "deterministic-svg",
    },
    "beautiful-mermaid": {
        "owner": "diagram",
        "mode": "deterministic",
        "editable_suffix": ".svg",
        "technical": False,
        "fallback": "deterministic-svg",
    },
    "deterministic-infographic": {
        "owner": "evidence",
        "mode": "deterministic",
        "editable_suffix": ".html",
        "technical": False,
        "fallback": "deterministic-infographic",
    },
    "excalidraw": {
        "owner": "diagram",
        "mode": "deterministic",
        "editable_suffix": ".excalidraw.json",
        "technical": False,
        "fallback": "deterministic-svg",
    },
    "excalidraw-style": {
        "owner": "diagram",
        "mode": "deterministic",
        "editable_suffix": ".svg",
        "technical": False,
        "fallback": "deterministic-svg",
    },
    "agnes": {
        "owner": "illustration",
        "mode": "agnes",
        "editable_suffix": "",
        "technical": False,
        "fallback": "brand-cover-or-local-illustration",
    },
    "agnes-or-brand-cover": {
        "owner": "illustration",
        "mode": "agnes",
        "editable_suffix": "",
        "technical": False,
        "fallback": "brand-cover",
    },
    "code-block": {
        "owner": "diagram",
        "mode": "deterministic",
        "editable_suffix": ".html",
        "technical": True,
        "fallback": "deterministic-svg",
    },
    "formula-code-map": {
        "owner": "diagram",
        "mode": "deterministic",
        "editable_suffix": ".html",
        "technical": True,
        "fallback": "katex-html-composite",
    },
    "interactive-card-deck": {
        "owner": "illustration",
        "mode": "deterministic",
        "editable_suffix": ".svg",
        "technical": False,
        "fallback": "deterministic-svg",
    },
}


def backend_spec(name: str) -> dict[str, Any]:
    value = str(name or "").strip().lower()
    return dict(BACKENDS.get(value, {}))


def validate_record(record: dict[str, Any]) -> list[str]:
    """Return blocking contract errors for one visual plan record."""
    errors: list[str] = []
    backend = str(record.get("render_backend") or record.get("requested_backend") or "").strip().lower()
    spec = backend_spec(backend)
    identity = str(record.get("id") or "unknown")
    if not spec:
        errors.append(f"未知视觉后端：{identity} -> {backend or '(empty)'}")
        return errors
    if not str(record.get("content_signal") or "").strip():
        errors.append(f"视觉记录缺少 content_signal：{identity}")
    if not str(record.get("viewer_job") or "").strip():
        errors.append(f"视觉记录缺少 viewer_job：{identity}")
    if not str(record.get("fallback") or "").strip():
        errors.append(f"视觉记录缺少 fallback：{identity}")
    actual = str(record.get("execution_backend") or "").strip().lower()
    if actual and actual != backend:
        # A deterministic local renderer may be the explicit fallback for an
        # unavailable Mermaid/Excalidraw backend, but the reason is mandatory.
        if not str(record.get("fallback_reason") or "").strip():
            errors.append(f"视觉后端发生降级但缺少 fallback_reason：{identity}")
    if spec.get("technical") and str(record.get("generation_mode") or "").lower() == "agnes":
        errors.append(f"精确技术图不得使用 Agnes：{identity}")
    return errors


def route_backend(content_signal: str, visual_type: str = "") -> str:
    signal = str(content_signal or "").strip().lower()
    kind = str(visual_type or "").strip().lower()
    if kind in {"excalidraw", "whiteboard"}:
        return "excalidraw"
    if kind == "excalidraw-style":
        return "excalidraw-style"
    # Timelines and multi-branch relationships are clearer as editable SVG;
    # formulas remain in the article/KaTeX assets beside the visual anchor.
    if signal == "timeline" or kind == "kv-cache":
        return "deterministic-svg"
    if kind == "multihead" and signal in {"relationship", "comparison", "math"}:
        return "beautiful-mermaid"
    if signal == "math" or kind in {"qkv", "shape", "attention", "numeric"}:
        return "katex-html-composite"
    if signal == "relationship" or kind in {"architecture", "flow", "diagram"}:
        return "deterministic-svg"
    if signal in {"comparison", "checklist"} or kind in {"comparison", "evidence-strip", "checklist"}:
        return "deterministic-infographic"
    if signal == "formula-code-map" or kind == "formula-code-map":
        return "formula-code-map"
    if signal in {"code", "pseudocode"} or kind in {"code", "pseudocode"}:
        return "code-block"
    if kind == "excalidraw-style":
        return "excalidraw-style"
    return "agnes"
