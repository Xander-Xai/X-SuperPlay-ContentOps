from __future__ import annotations

import tempfile
from pathlib import Path

from validate_handoff import validate
from workflow_gate import _errors_for_topic


VALID = """---
schema_version: 1
contract: handoff-contract-v1
source_article_ref: drafts/source-article
source_article_sha256: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
signal_count: 3
required_signals:
  - repeated_deployment_questions
  - source_or_code_requests
  - above_baseline_engagement
target_topic: LangGraph 状态持久化
human_confirmed_by: editor
approved_at: 2026-08-10T12:00:00+08:00
---
# handoff
"""


def test_valid_handoff() -> None:
    with tempfile.TemporaryDirectory() as raw:
        card = Path(raw) / "handoff-card.md"
        card.write_text(VALID, encoding="utf-8")
        assert validate(card) == []


def test_missing_signal_is_blocked() -> None:
    with tempfile.TemporaryDirectory() as raw:
        card = Path(raw) / "handoff-card.md"
        card.write_text(VALID.replace("  - source_or_code_requests\n", ""), encoding="utf-8")
        assert any("required_signals" in error for error in validate(card))


def test_topic_gate_invokes_handoff_contract() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        card = root / "handoff-card.md"
        card.write_text(VALID.replace("source_or_code_requests", ""), encoding="utf-8")
        article = root / "article"
        article.mkdir()
        (article / "routing.yaml").write_text(
            "topic_route:\n  mode: user_material\n  reference: " + str(card).replace("\\", "/") + "\n",
            encoding="utf-8",
        )
        (article / "article.yaml").write_text("account: thinktank\n", encoding="utf-8")
        errors = _errors_for_topic(article)
        assert any("handoff 合同" in error for error in errors)


if __name__ == "__main__":
    test_valid_handoff()
    test_missing_signal_is_blocked()
    test_topic_gate_invokes_handoff_contract()
    print("HANDOFF CONTRACT TESTS PASSED")
