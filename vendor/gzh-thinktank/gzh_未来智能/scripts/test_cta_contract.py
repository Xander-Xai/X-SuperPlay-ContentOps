from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cta_contract import build, validate


def _article(root: Path) -> Path:
    article = root / "article"
    article.mkdir()
    (article / "article.yaml").write_text("title: LangGraph 状态持久化\naccount: thinktank\n", encoding="utf-8")
    (article / "topic-contract.yaml").write_text("canonical_topic: LangGraph 状态持久化\n", encoding="utf-8")
    (article / "content-brief.yaml").write_text(
        "account: thinktank\nreply_keyword: 检查点\nlead_magnet: LangGraph 实战清单\n"
        "primary_cta: 关注并回复检查点领取 LangGraph 实战清单\n"
        "secondary_cta: 留言你的部署问题\n",
        encoding="utf-8",
    )
    return article


def test_cta_contract_round_trip() -> None:
    with tempfile.TemporaryDirectory() as raw:
        article = _article(Path(raw))
        (article / "cta-contract.json").write_text(
            json.dumps(build(article), ensure_ascii=False), encoding="utf-8"
        )
        assert validate(article) == []


def test_cta_contract_rejects_topic_drift() -> None:
    with tempfile.TemporaryDirectory() as raw:
        article = _article(Path(raw))
        contract = build(article)
        contract["topic_fingerprint"] = "0" * 64
        (article / "cta-contract.json").write_text(
            json.dumps(contract, ensure_ascii=False), encoding="utf-8"
        )
        assert any("topic_fingerprint" in error for error in validate(article))


if __name__ == "__main__":
    test_cta_contract_round_trip()
    test_cta_contract_rejects_topic_drift()
    print("CTA CONTRACT TESTS PASSED")
