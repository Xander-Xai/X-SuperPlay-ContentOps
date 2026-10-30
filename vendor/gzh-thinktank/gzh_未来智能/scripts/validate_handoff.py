#!/usr/bin/env python3
"""Validate an approved handoff card without reading external workflows.

Cards are copied into ``inbox/handoff/<handoff_id>/`` by a human.  The card
must carry enough provenance to explain why a topic was promoted; this does
not make the split workflow depend on a running sentinel account.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SIGNALS = {
    "repeated_deployment_questions",
    "source_or_code_requests",
    "above_baseline_engagement",
}


def _frontmatter(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.lstrip().startswith("---"):
        return {}
    lines = text.lstrip().splitlines()
    end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
    if end is None:
        return {}
    try:
        import yaml  # type: ignore
        value = yaml.safe_load("\n".join(lines[1:end])) or {}
        return value if isinstance(value, dict) else {}
    except (ImportError, ValueError):
        return {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(card: Path) -> list[str]:
    errors: list[str] = []
    if not card.is_file():
        return [f"handoff card 不存在：{card}"]
    data = _frontmatter(card)
    if data.get("schema_version") != 1:
        errors.append("handoff card frontmatter 必须包含 schema_version: 1")
    if str(data.get("contract") or "").strip() != "handoff-contract-v1":
        errors.append("handoff card contract 必须是 handoff-contract-v1")
    if not str(data.get("source_article_ref") or "").strip():
        errors.append("handoff card 缺少 source_article_ref")
    source_sha = str(data.get("source_article_sha256") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        errors.append("handoff card source_article_sha256 必须是 64 位 SHA-256")
    try:
        count = int(data.get("signal_count"))
    except (TypeError, ValueError):
        count = 0
    if count < 3:
        errors.append("handoff card signal_count 至少为 3")
    raw_signals = data.get("required_signals")
    signals = {str(item).strip() for item in raw_signals} if isinstance(raw_signals, list) else set()
    missing = sorted(REQUIRED_SIGNALS - signals)
    if missing:
        errors.append("handoff card 缺少 required_signals：" + ", ".join(missing))
    if not str(data.get("human_confirmed_by") or "").strip():
        errors.append("handoff card 缺少 human_confirmed_by")
    if not str(data.get("approved_at") or "").strip():
        errors.append("handoff card 缺少 approved_at")
    if not str(data.get("target_topic") or "").strip():
        errors.append("handoff card 缺少 target_topic")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--card", required=True, type=Path)
    args = parser.parse_args()
    card = args.card.expanduser()
    if not card.is_absolute():
        card = ROOT / card
    card = card.resolve()
    errors = validate(card)
    if errors:
        print("HANDOFF CONTRACT BLOCKED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"HANDOFF CONTRACT PASSED: {card}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
