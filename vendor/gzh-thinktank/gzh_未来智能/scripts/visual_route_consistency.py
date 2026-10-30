#!/usr/bin/env python3
"""Fail closed when visual route/provenance ledgers disagree.

The visual workflow has several ledgers because planning, execution, and
publication are different lifecycle stages.  This checker makes that
distinction executable: requested, selected, and execution backends must agree
across the contract, router, generation plan, director plan, and source ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT = "visual-route-consistency.json"


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _by(items: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(items, list):
        return {}
    return {
        str(item.get(key)): item
        for item in items
        if isinstance(item, dict) and str(item.get(key) or "").strip()
    }


def _resolve(article: Path, raw: str) -> Path:
    path = Path(str(raw or ""))
    return path if path.is_absolute() else article / path


def _check_excalidraw(path: Path) -> list[str]:
    if not path.is_file():
        return [f"Excalidraw source missing: {path}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"Excalidraw source invalid JSON: {path}: {exc}"]
    errors: list[str] = []
    if value.get("type") != "excalidraw" or value.get("version") != 2:
        errors.append(f"Excalidraw envelope invalid: {path}")
    if not isinstance(value.get("elements"), list) or not value.get("elements"):
        errors.append(f"Excalidraw source has no elements: {path}")
    for element in value.get("elements", []):
        if not isinstance(element, dict):
            errors.append(f"Excalidraw element is not an object: {path}")
            continue
        if element.get("link"):
            errors.append(f"Excalidraw element link is not allowed: {path}#{element.get('id')}")
        if element.get("type") == "text" and not str(element.get("text") or "").strip():
            errors.append(f"Excalidraw text element is empty: {path}#{element.get('id')}")
    return errors


def check(article: Path) -> dict[str, Any]:
    article = article.resolve()
    contract = _json(article / "visual-contract.json")
    routing = _json(article / "visual-routing.json")
    plan = _json(article / "image-generation-plan.json")
    director = _json(article / "visual-director-plan.json")
    sources = _json(article / "image-sources.json")
    units = _by(contract.get("units"), "id")
    routes = _by(routing.get("routes"), "id")
    plans = _by(plan.get("prompt_files"), "id")
    directors = _by(director.get("records"), "id")
    source_assets = _by(sources.get("assets"), "path")
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    full_ledger = bool(routes or plans or directors or source_assets)
    if units and not full_ledger:
        report = {
            "schema_version": 1,
            "contract": "visual-route-consistency-v1",
            "status": "passed",
            "article": article.name,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "records": [],
            "errors": [],
            "note": "minimal contract fixture: cross-ledger route check deferred until planning/execution ledgers exist.",
        }
        (article / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return report
    manifest_path = article / "visual-run-manifest.jsonl"
    if plan.get("prompt_files"):
        if not manifest_path.is_file():
            errors.append("缺少 visual-run-manifest.jsonl：完整视觉执行必须留下命令与输入/输出哈希 provenance")
        else:
            runs: list[dict[str, Any]] = []
            for raw in manifest_path.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict) and row.get("stage") == "visual-render" and row.get("status") == "passed":
                    runs.append(row)
            if not runs:
                errors.append("visual-run-manifest.jsonl 缺少 status=passed 的 visual-render 记录")
            else:
                latest = runs[-1]
                for item in latest.get("outputs", []) if isinstance(latest.get("outputs"), list) else []:
                    if not isinstance(item, dict) or not item.get("exists"):
                        continue
                    if str(item.get("path") or "").replace("\\", "/") == "visual-run-manifest.jsonl":
                        continue
                    current = _resolve(article, str(item.get("path") or ""))
                    if current.is_file() and str(item.get("sha256") or "").lower() != _sha(current):
                        errors.append(f"visual-run-manifest 输出哈希已过期：{item.get('path')}")
    if plan.get("prompt_files") and not (article / "visual-run-manifest.jsonl").is_file():
        errors.append("缺少 visual-run-manifest.jsonl：完整视觉执行必须留下命令与输入/输出哈希 provenance")

    for unit_id, unit in units.items():
        if unit_id == "cover":
            continue
        requested = str(unit.get("requested_backend") or unit.get("render_backend") or "").strip().lower()
        selected = str(unit.get("render_backend") or "").strip().lower()
        execution = str(unit.get("execution_backend") or "").strip().lower()
        if not requested or not selected or not execution:
            errors.append(f"{unit_id}: contract 缺少 requested/selected/execution backend")
        if requested != selected or selected != execution:
            errors.append(f"{unit_id}: contract backend drift requested={requested} selected={selected} execution={execution}")

        route = routes.get(unit_id, {})
        route_backend = str(route.get("primary_backend") or "").strip().lower()
        if route_backend and route_backend != execution:
            errors.append(f"{unit_id}: visual-routing primary_backend={route_backend} != execution={execution}")

        plan_item = plans.get(unit_id, {})
        director_item = directors.get(unit_id, {})
        for label, item in (("generation-plan", plan_item), ("director-plan", director_item)):
            item_requested = str(item.get("requested_backend") or item.get("render_backend") or "").strip().lower()
            item_execution = str(item.get("execution_backend") or "").strip().lower()
            if item_requested and item_requested != requested:
                errors.append(f"{unit_id}: {label} requested_backend={item_requested} != {requested}")
            if item_execution and item_execution != execution:
                errors.append(f"{unit_id}: {label} execution_backend={item_execution} != {execution}")

        output = str(unit.get("output") or unit.get("asset") or "").replace("\\", "/")
        output_path = _resolve(article, output)
        if not output_path.is_file():
            errors.append(f"{unit_id}: raster output missing: {output}")

        source_raw = str(unit.get("diagram_source") or "").strip()
        source_path = _resolve(article, source_raw)
        if not source_path.is_file():
            errors.append(f"{unit_id}: diagram_source missing: {source_raw}")
        if execution == "excalidraw":
            native_raw = str(unit.get("excalidraw_source") or "").strip()
            native_path = _resolve(article, native_raw)
            errors.extend(f"{unit_id}: {issue}" for issue in _check_excalidraw(native_path))
            if plan_item:
                plan_native = str(plan_item.get("excalidraw_source") or "").strip()
                if plan_native and plan_native.replace("\\", "/") != native_raw.replace("\\", "/"):
                    errors.append(f"{unit_id}: generation-plan excalidraw_source drift")
            source_asset = source_assets.get(output, {})
            generation = source_asset.get("generation") if isinstance(source_asset.get("generation"), dict) else {}
            ledger_native = str(generation.get("excalidraw_source") or "").strip()
            if ledger_native and ledger_native.replace("\\", "/") != native_raw.replace("\\", "/"):
                errors.append(f"{unit_id}: image-sources excalidraw_source drift")

        source_asset = source_assets.get(output, {})
        generation = source_asset.get("generation") if isinstance(source_asset.get("generation"), dict) else {}
        ledger_requested = str(generation.get("requested_backend") or "").strip().lower()
        ledger_execution = str(generation.get("execution_backend") or "").strip().lower()
        if ledger_requested and ledger_requested != requested:
            errors.append(f"{unit_id}: image-sources requested_backend={ledger_requested} != {requested}")
        if ledger_execution and ledger_execution != execution:
            errors.append(f"{unit_id}: image-sources execution_backend={ledger_execution} != {execution}")

        records.append(
            {
                "id": unit_id,
                "requested_backend": requested,
                "selected_backend": selected,
                "execution_backend": execution,
                "output": output,
                "output_sha256": _sha(output_path),
                "status": "failed" if any(error.startswith(f"{unit_id}:") for error in errors) else "passed",
            }
        )

    report = {
        "schema_version": 1,
        "contract": "visual-route-consistency-v1",
        "status": "passed" if not errors else "failed",
        "article": article.name,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
        "errors": errors,
        "note": "route drift is blocking; a historical override must be represented by a superseded event, not stale free text.",
    }
    (article / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    report = check(args.article)
    print(json.dumps({"status": report["status"], "errors": len(report["errors"])}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
