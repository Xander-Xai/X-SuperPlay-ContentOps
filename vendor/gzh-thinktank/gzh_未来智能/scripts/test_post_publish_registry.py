from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "skill-registry.yaml"
ADAPTERS = {
    "z5_review": "skills/z5-wechat-sop",
    "fallback_publisher": "skills/wechat-publisher",
    "cross_platform_repurpose": "skills/content-repurposer",
}


def _block(text: str, name: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\s*\n(.*?)(?=^  [A-Za-z0-9_-]+:\s*$|\Z)", text)
    return match.group(1) if match else ""


def test_registry_adapters() -> None:
    text = REGISTRY.read_text(encoding="utf-8")
    for name, path in ADAPTERS.items():
        body = _block(text, name)
        assert body, f"missing adapter {name}"
        assert f"path: {path}" in body
        assert "activation: opt-in" in body
        assert "requires: final_reviewed" in body
        assert "guard: media_guard" in body
        assert (ROOT / path).exists(), path


if __name__ == "__main__":
    test_registry_adapters()
    print("POST-PUBLISH REGISTRY TESTS PASSED")
