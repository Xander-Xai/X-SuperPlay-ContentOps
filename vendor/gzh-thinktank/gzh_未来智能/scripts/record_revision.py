#!/usr/bin/env python3
"""Record content freshness and explicit reuse approval for an article workspace.

The workflow cannot infer whether a draft is genuinely new or intentionally
reused.  This small, deterministic command records that decision and binds it
to the current draft/final SHA-256 digests so later edits invalidate the
evidence instead of silently reusing an old review receipt.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from article_integrity import is_text_evidence_path, stable_sha256_file  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_article(raw: str) -> Path:
    article = Path(raw).expanduser()
    if not article.is_absolute():
        article = ROOT / article
    return article.resolve()


def _resolve_source(article: Path, raw: str) -> Path:
    source = Path(raw).expanduser()
    if not source.is_absolute():
        candidates = (article / source, ROOT / source)
        source = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    return source.resolve()


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _fail(message: str) -> int:
    print(f"REVISION BLOCKED: {message}", file=sys.stderr)
    return 1


def record(args: argparse.Namespace) -> int:
    article = _resolve_article(args.article)
    if not article.is_dir():
        return _fail(f"文章目录不存在：{article}")
    draft = article / "draft.md"
    if not draft.is_file() or not draft.read_text(encoding="utf-8", errors="replace").strip():
        return _fail("缺少 draft.md；必须先完成初稿")
    if not str(args.change_summary or "").strip():
        return _fail("必须填写 --change-summary，说明本次内容变化")

    mode = str(args.mode).strip().lower()
    if mode not in {"new", "reused"}:
        return _fail("--mode 只能是 new 或 reused")

    source: dict[str, Any]
    if mode == "reused":
        if not args.source:
            return _fail("复用稿必须通过 --source 指定原稿或用户材料")
        if not args.approve_reuse:
            return _fail("复用稿必须显式传 --approve-reuse，不能隐式沿用旧稿")
        source_path = _resolve_source(article, args.source)
        if not source_path.is_file():
            return _fail(f"复用来源不存在：{source_path}")
        source = {
            "kind": "local_material",
            "path": _display_path(source_path),
            "sha256": stable_sha256_file(source_path),
            "hash_mode": "canonical-text" if is_text_evidence_path(source_path) else "raw",
        }
    else:
        source = {
            "kind": "fresh_draft",
            "note": str(args.source_note or "本次基于当前选题和调研重新生成").strip(),
        }

    payload: dict[str, Any] = {
        "schema_version": 1,
        "status": "passed",
        "mode": mode,
        "operator": str(args.operator or "operator").strip(),
        "created_at": _now(),
        "change_summary": str(args.change_summary).strip(),
        "reuse_approved": bool(args.approve_reuse) if mode == "reused" else False,
        "source": source,
        "draft_digest": stable_sha256_file(draft),
        "final_digest": "",
        "finalized_at": "",
    }
    _write(article / "content-revision.json", payload)
    print(f"REVISION RECORDED: {article / 'content-revision.json'}")
    print(f"MODE: {mode}")
    return 0


def finalize(args: argparse.Namespace) -> int:
    article = _resolve_article(args.article)
    manifest_path = article / "content-revision.json"
    manifest = _load(manifest_path)
    if not manifest:
        return _fail("缺少 content-revision.json；先记录 new/reused 决策")
    draft = article / "draft.md"
    final = article / "article.md"
    if not draft.is_file() or not final.is_file():
        return _fail("--finalize 需要同时存在 draft.md 和 article.md")
    if manifest.get("draft_digest") != stable_sha256_file(draft):
        return _fail("draft.md 已变化；请重新记录 revision 再 finalize")
    text = final.read_text(encoding="utf-8", errors="replace").strip()
    if not text or "占位文件" in text:
        return _fail("article.md 仍为空或是占位文件")
    manifest["final_digest"] = stable_sha256_file(final)
    manifest["finalized_at"] = _now()
    manifest["status"] = "passed"
    _write(manifest_path, manifest)
    print(f"REVISION FINALIZED: {manifest_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, help="文章工作区目录")
    parser.add_argument("--mode", choices=("new", "reused"), help="新稿或显式复用稿")
    parser.add_argument("--source", help="复用稿的本地来源文件")
    parser.add_argument("--source-note", help="新稿来源说明")
    parser.add_argument("--change-summary", help="本次正文的实际变化说明")
    parser.add_argument("--operator", default="operator")
    parser.add_argument("--approve-reuse", action="store_true", help="明确批准复用来源")
    parser.add_argument("--finalize", action="store_true", help="将当前 article.md 绑定为最终稿")
    args = parser.parse_args()
    if args.finalize:
        return finalize(args)
    if not args.mode:
        parser.error("记录 revision 时必须提供 --mode；或使用 --finalize")
    return record(args)


if __name__ == "__main__":
    raise SystemExit(main())
