"""M5 Easel composition handoff (Issue #140 slice)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Optional


def stage_compose(
    project: Path,
    slug: str,
    *,
    compose: Callable[[], Dict[str, Any]],
    logical_path: Callable[[Any], Optional[str]],
    write_json: Callable[[Path, Dict[str, Any]], None],
    blocked_error: type[Exception],
) -> Dict[str, Any]:
    """Run the existing Easel adapter and write its canonical M5 receipt."""
    previous_video = project / "final" / f"{slug}.mp4"
    preserved_previous = project / "final" / f"{slug}-before-avatar-refresh.mp4"
    if previous_video.is_file() and not preserved_previous.exists():
        shutil.copy2(previous_video, preserved_previous)
    result = compose()
    # Resolve engine identity from the registry only when the adapter omitted it.
    engine_block = result.get("easel") or {}
    if not engine_block:
        try:
            from contentops.easel import pins as easel_pins

            engine = easel_pins.active()
            engine_block = {"engine_id": engine.engine_id, "tag": engine.tag,
                            "commit": engine.commit, "tree_sha256": engine.tree_sha256,
                            "layout": engine.layout}
        except Exception:  # noqa: BLE001 - a receipt must not invent an engine
            engine_block = {}
    stamp = engine_block.get("tag") or "unrecorded"
    upstream_path = Path(result.get(
        "upstream", "skills/openclaw/auto-short-video/scripts/assemble.py"
    )).as_posix()
    upstream_suffix = (upstream_path.split("/skills/", 1)[-1]
                       if "/skills/" in upstream_path else
                       upstream_path.removeprefix("skills/"))
    receipt = {
        "status": result.get("status"),
        "video": logical_path(result.get("video")),
        "subtitles_burned": result.get("subtitles_burned"),
        "upstream": f"easel@{stamp}:skills/{upstream_suffix}",
        "easel": engine_block or None,
        "reason": result.get("reason"),
    }
    receipt = {key: value for key, value in receipt.items() if value is not None}
    write_json(project / "receipts" / "compose.json", receipt)
    if result.get("status") != "OK":
        raise blocked_error(f"compose: {result.get('reason')}")
    return receipt
