"""M5 script validation and reviewer-copy output (Issue #140 slice).

The stage keeps its historical inputs, error type, receipt schema and Markdown
rendering. Dependencies are injected by the compatibility facade so this module
owns no CLI or second evidence model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from contentops.paths import relative_label


def stage_script(
    project: Path,
    ledger: Any,
    assets: Dict[str, Any],
    *,
    repo_root: Path,
    load_script: Callable[[Path], Dict[str, Any]],
    blocked_error: type[Exception],
    read_json_or_none: Callable[[Path], Any],
    write_json: Callable[[Path, Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Validate script references and write the legacy check/master outputs."""
    script = load_script(project)
    ids = [line["id"] for line in script["lines"]]
    if len(ids) != len(set(ids)):
        raise blocked_error("duplicate script line id")
    known = ledger.by_id()
    cited = {line.get("claim") for line in script["lines"] if line.get("claim")}
    unknown = sorted(cited - set(known))
    if unknown:
        raise blocked_error(f"script cites unknown claims: {unknown}")
    unused = ledger.require_used(cited)
    if unused:
        raise blocked_error(f"claims never appear in the script: {unused}")
    for line in script["lines"]:
        asset = assets.get(line.get("asset_id"))
        if asset is None:
            raise blocked_error(
                f"{line['id']}: asset_id {line.get('asset_id')!r} is not in sources/assets.json")
        if not (repo_root / asset["repo_path"]).is_file():
            raise blocked_error(f"{line['id']}: asset missing: {asset['repo_path']}")
        if not str(line.get("narration") or "").strip():
            raise blocked_error(f"{line['id']}: narration is empty")
    payload = {
        "schema": "contentops.m5-script-check/v1",
        "ok": True,
        "lines": len(script["lines"]),
        "claims_cited": sorted(cited),
        "claims_unused": [],
    }
    write_json(project / "receipts" / "script-check.json", payload)

    # Shared copy is reviewed before rendering; do not overwrite its fingerprinted master.
    master = (project / "receipts" / "m5-reviewed-copy.md"
              if (project / "receipts" / "shared-copy-video.json").exists()
              else project / "script" / "master.md")
    # Each beat includes a followable evidence link, not only a bare claim id.
    refs_doc = read_json_or_none(project / "sources" / "source-refs.json") or {}
    refs_by_id = {
        str(row.get("id")): row
        for row in (refs_doc.get("refs") or [])
        if isinstance(row, dict) and row.get("id")
    }
    rows = ["| # | 旁白 | 字幕 | 事实来源 | 素材 |", "|---|---|---|---|---|"]
    for line in script["lines"]:
        claim = known.get(line.get("claim") or "")
        citations = []
        for artifact_id in (claim.artifacts if claim else ()):
            ref = refs_by_id.get(str(artifact_id)) or {}
            target = str(ref.get("url") or ref.get("path") or "")
            if not target:
                continue
            title = str(ref.get("title") or artifact_id).replace("]", r"\]")
            citations.append(f"[{title}](<{target}>)")
        source_cell = " · ".join(citations) if citations else "—"
        rows.append(
            f"| {line['id']} | {line['narration']} | {line['caption']} | "
            f"{source_cell} | {assets[line['asset_id']]['repo_path']} |"
        )
    master.write_text(
        f"# {project.name} — 脚本文本\n\n"
        "由 `script/script.json` 生成；每条事实声明在 `script/claims.json` 中绑定到来源引文。\n\n"
        + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return {"script": script, "lines": len(script["lines"])}
