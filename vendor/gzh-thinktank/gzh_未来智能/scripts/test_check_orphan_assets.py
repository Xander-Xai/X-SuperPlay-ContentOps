"""Regression test: editable sources declared by visual-contract are live assets."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from check_orphan_assets import _collect_index


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="orphan-contract-") as raw:
        article = Path(raw)
        source = article / "imgs" / "diagram-sources" / "body-02.svg"
        source.parent.mkdir(parents=True)
        source.write_text("<svg/>", encoding="utf-8")
        (article / "visual-contract.json").write_text(
            json.dumps({"units": [{"id": "body-02", "diagram_source": "imgs\\diagram-sources\\body-02.svg"}]}, ensure_ascii=False),
            encoding="utf-8",
        )
        assert "imgs/diagram-sources/body-02.svg" in _collect_index(article)
        plan_asset = article / "imgs" / "cover-agnes-background.png"
        plan_asset.write_bytes(b"png-placeholder")
        (article / "image-generation-plan.json").write_text(
            json.dumps({"cover_background": "imgs/cover-agnes-background.png"}, ensure_ascii=False),
            encoding="utf-8",
        )
        assert "imgs/cover-agnes-background.png" in _collect_index(article)
    print("ORPHAN CONTRACT TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
