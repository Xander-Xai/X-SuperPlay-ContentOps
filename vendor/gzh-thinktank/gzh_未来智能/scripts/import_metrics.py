#!/usr/bin/env python3
"""Import measured T+1/T+7 metrics without fabricating an operations loop.

The importer accepts a user-supplied JSON or CSV export, records its SHA-256
and capture time, and never marks an unobserved window as complete.  It does
not call WeChat or infer missing values.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workflow_security import ensure_article_path  # noqa: E402
WINDOWS = {"t1", "t7"}
METRICS = {
    "views", "likes", "comments", "shares", "follows", "keyword_replies",
    "lead_magnet_claims", "consultation_requests", "qualified_leads",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _parse_input(path: Path) -> tuple[dict[str, Any], str | None]:
    if path.suffix.lower() == ".csv":
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, csv.Error) as exc:
            return {}, f"CSV 读取失败：{exc}"
        if len(rows) != 1:
            return {}, "CSV 必须恰好包含一行指标数据"
        raw: dict[str, Any] = dict(rows[0])
    else:
        raw = _read_json(path)
        if not isinstance(raw, dict):
            return {}, "JSON 必须是对象"
    values = raw.get("values") if isinstance(raw.get("values"), dict) else raw
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        key = str(key).strip()
        if key in METRICS:
            cleaned[key] = value
    return {"values": cleaned, "captured_at": raw.get("captured_at")}, None


def _validate_values(values: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not values:
        return ["没有可导入的指标字段"]
    for key, raw in values.items():
        try:
            number = int(raw)
        except (TypeError, ValueError):
            errors.append(f"指标 {key} 不是整数")
            continue
        if number < 0:
            errors.append(f"指标 {key} 不能为负数")
    return errors


def _archive_source(article: Path, window: str, input_path: Path) -> tuple[str, str]:
    """Preserve the exact external export inside the article workspace."""

    digest = _sha256(input_path)
    suffix = input_path.suffix.lower() if input_path.suffix else ".bin"
    target = article / "work" / "metrics" / f"{window}-{digest}{suffix}"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        if _sha256(target) != digest:
            raise OSError(f"metrics archive hash conflict: {target}")
    else:
        shutil.copyfile(input_path, target)
    return target.relative_to(article).as_posix(), digest


def import_window(article: Path, window: str, input_path: Path, source: str, captured_at: str | None, replace: bool) -> int:
    if window not in WINDOWS:
        print(f"METRICS IMPORT BLOCKED: window 必须是 t1/t7，当前 {window!r}")
        return 1
    payload, parse_error = _parse_input(input_path)
    if parse_error:
        print(f"METRICS IMPORT BLOCKED: {parse_error}")
        return 1
    values = payload.get("values") if isinstance(payload.get("values"), dict) else {}
    errors = _validate_values(values)
    effective_captured = str(captured_at or payload.get("captured_at") or "").strip()
    if not effective_captured:
        errors.append("必须提供 captured_at（原始数据采集时间），不能用导入时间冒充")
    if not str(source).strip():
        errors.append("必须提供 source")
    if errors:
        print("METRICS IMPORT BLOCKED:")
        for error in errors:
            print(f"- {error}")
        return 1
    metrics_path = article / "metrics.json"
    metrics = _read_json(metrics_path)
    if not isinstance(metrics, dict):
        metrics = {"schema_version": 2, "conversion": {}, "attribution": {}}
    old = metrics.get(window)
    if isinstance(old, dict) and old.get("status") == "observed" and not replace:
        print(f"METRICS IMPORT BLOCKED: {window} 已有 observed 数据；如确需更正请显式 --replace")
        return 1
    try:
        source_path, source_digest = _archive_source(article, window, input_path)
    except OSError as exc:
        print(f"METRICS IMPORT BLOCKED: 无法归档原始导出：{exc}")
        return 1
    imported_at = datetime.now(timezone.utc).isoformat()
    try:
        previous_schema = int(metrics.get("schema_version", 2) or 2)
    except (TypeError, ValueError):
        previous_schema = 2
    metrics["schema_version"] = max(previous_schema, 3)
    metrics[window] = {
        "status": "observed",
        "captured_at": effective_captured,
        "imported_at": imported_at,
        "source": str(source).strip(),
        "source_path": source_path,
        "source_sha256": source_digest,
        "values": {key: int(value) for key, value in values.items()},
    }
    metrics.setdefault("handoff_signals", [])
    metrics.setdefault("content_reuse", [])
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"METRICS IMPORT PASSED: {window}; {len(values)} fields; source_sha256={metrics[window]['source_sha256']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--window", required=True, choices=sorted(WINDOWS))
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--source", required=True, help="数据导出来源或人工回执编号")
    parser.add_argument("--captured-at", help="原始数据采集时间；也可放在 JSON 的 captured_at")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        article = ensure_article_path(args.article, allow_test_fixture=True)
    except ValueError as exc:
        print(f"METRICS IMPORT BLOCKED: {exc}")
        return 1
    input_path = args.input.expanduser()
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path
    return import_window(article, args.window, input_path.resolve(), args.source, args.captured_at, args.replace)


if __name__ == "__main__":
    raise SystemExit(main())
