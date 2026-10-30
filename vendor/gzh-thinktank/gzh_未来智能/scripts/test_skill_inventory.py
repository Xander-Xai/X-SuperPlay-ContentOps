from __future__ import annotations

import tempfile
from pathlib import Path

from audit_skill_inventory import scan


def test_inventory_is_parameterized_and_hashes_files() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        skill = root / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: demo\nversion: 1.0\n---\n# Demo\n", encoding="utf-8"
        )
        doc = scan(root)
        assert doc["skill_count"] == 1
        assert doc["skills"][0]["name"] == "demo"
        assert len(doc["skills"][0]["sha256"]) == 64


if __name__ == "__main__":
    test_inventory_is_parameterized_and_hashes_files()
    print("SKILL INVENTORY TESTS PASSED")
