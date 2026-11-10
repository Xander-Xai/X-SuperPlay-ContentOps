"""Per-platform graphic delivery specifications.

Loads ``config/platforms/graphic-platforms.yaml`` and turns it into deterministic
shaping rules. Everything here is offline: no network, no credential, no host
startup. The module is deliberately separate from ``multichannel.py`` so that
"which platforms exist" and "what shape each platform wants" have one owner.

Accounting model
----------------
Two limit tiers per platform:

* ``*_hard`` - exceeding it is a **blocker**. The platform will truncate or the
  editor will refuse the body.
* ``*_soft`` - exceeding it is a **warning**. The draft is still valid, it is
  just off this project's editorial convention.

Collapsing those two into a single number is what made the previous
``PLATFORM_RULES`` tuple misleading: it reported a 50000-character WeChat body
limit against a project convention of a 25-character title, as if both had the
same authority. They do not.

Length counting
---------------
``weighted_len`` implements the one platform where plain ``len()`` is wrong: X
charges 2 for a CJK code point and 1 for a Latin code point inside its 280
budget. Every other platform here counts characters.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

SPEC_RELATIVE = Path("config") / "platforms" / "graphic-platforms.yaml"
SCHEMA = "contentops.graphic-platforms/v1"

# Fields a platform record must carry. Missing ones are a spec bug, not a
# runtime surprise, so they are checked once at load time.
REQUIRED_FIELDS = (
    "platform_id",
    "display_name",
    "registry_row",
    "strategy_platform",
    "pipeline",
    "native_format",
    "title_max_hard",
    "body_max_hard",
    "needs_cover",
    "channels",
)


class SpecError(RuntimeError):
    """The platform spec file is missing, malformed or internally inconsistent."""


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "registry" / "platforms.json").is_file():
            return parent
    return here.parents[3]


def spec_path() -> Path:
    return _project_root() / SPEC_RELATIVE


@lru_cache(maxsize=1)
def load_specs() -> dict[str, Any]:
    """Read and sanity-check the platform spec once per process."""
    try:
        import yaml  # noqa: PLC0415 - optional at import time, required at load
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise SpecError(
            "PyYAML 未安装，无法读取平台规格表。请使用项目 venv 运行"
            "（.runtime/gzh-wf-venv/Scripts/python.exe）。"
        ) from exc

    path = spec_path()
    if not path.is_file():
        raise SpecError(f"平台规格表缺失：{path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SpecError("平台规格表根节点必须是映射")
    if raw.get("schema") != SCHEMA:
        raise SpecError(f"平台规格表 schema 必须是 {SCHEMA}，实际 {raw.get('schema')!r}")

    rows = raw.get("platforms")
    if not isinstance(rows, list) or not rows:
        raise SpecError("平台规格表 platforms 必须是非空列表")

    seen: set[str] = set()
    platforms: dict[str, dict[str, Any]] = {}
    for row in rows:
        for field in REQUIRED_FIELDS:
            if field not in row:
                raise SpecError(f"平台记录缺少字段 {field}：{row.get('platform_id')!r}")
        pid = str(row["platform_id"])
        if pid in seen:
            raise SpecError(f"平台记录重复：{pid}")
        seen.add(pid)
        channels = row.get("channels") or []
        if not isinstance(channels, list) or not channels:
            raise SpecError(f"{pid} 没有任何投递通道")
        for ch in channels:
            if not ch.get("id") or not ch.get("kind"):
                raise SpecError(f"{pid} 的通道缺少 id/kind")
            if ch["kind"] not in ("api", "browser_bridge"):
                raise SpecError(f"{pid} 的通道 kind 只能是 api / browser_bridge")
        platforms[pid] = row

    return {
        "schema": raw["schema"],
        "limits_policy": raw.get("limits_policy") or {},
        "platforms": platforms,
        "excluded": raw.get("excluded") or [],
    }


def platform_ids(*, registry_rows_only: bool = False) -> tuple[str, ...]:
    rows = load_specs()["platforms"]
    if registry_rows_only:
        return tuple(pid for pid, row in rows.items() if row["registry_row"])
    return tuple(rows)


def spec(platform_id: str) -> dict[str, Any]:
    rows = load_specs()["platforms"]
    if platform_id not in rows:
        raise KeyError(platform_id)
    return rows[platform_id]


def is_registry_row(platform_id: str) -> bool:
    return bool(spec(platform_id)["registry_row"])


def channels(platform_id: str) -> list[dict[str, Any]]:
    return list(spec(platform_id)["channels"])


def primary_channel(platform_id: str) -> str:
    """The channel shown in a receipt: the API path first, else the bridge.

    Receipts record the *intended* channel, never a claim that it was used. The
    dispatch result carries the truth about whether it worked.
    """
    chans = channels(platform_id)
    for ch in chans:
        if ch["kind"] == "api":
            return str(ch["id"])
    return str(chans[0]["id"])


def requirements(platform_id: str) -> list[str]:
    """Union of everything any channel of this platform needs, deduplicated."""
    out: list[str] = []
    for ch in channels(platform_id):
        for item in ch.get("requires") or []:
            if item not in out:
                out.append(str(item))
    return out


def can_publish_via_api(platform_id: str) -> bool:
    return any(ch["kind"] == "api" for ch in channels(platform_id))


def weighted_len(text: str, platform_id: str) -> int:
    """Length as the platform's own counter would see it.

    Only X is weighted here. Every other platform in the spec counts code
    points, so ``len`` is correct and inventing a weight would be noise.
    """
    if platform_id != "x":
        return len(text)
    total = 0
    for ch in text:
        total += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return total


def rules(platform_id: str) -> dict[str, Any]:
    """Normalised shaping rules, with defaults filled in."""
    row = spec(platform_id)
    return {
        "native_format": row["native_format"],
        "title_max_hard": int(row.get("title_max_hard") or 0),
        "title_max_soft": int(row.get("title_max_soft") or 0),
        "body_max_hard": int(row.get("body_max_hard") or 0),
        "body_max_soft": int(row.get("body_max_soft") or 0),
        "summary_max": int(row.get("summary_max") or 0),
        "needs_cover": bool(row.get("needs_cover")),
        "cover_ratio": str(row.get("cover_ratio") or "none"),
        "recommended_tags": int(row.get("recommended_tags") or 0),
    }


def shape(platform_id: str, title: str, body: str) -> dict[str, Any]:
    """Shape one article into a platform's native form.

    Three conversions happen here, all deterministic and offline:

    1. **Format.** A ``markdown`` source is rendered to ``html`` for the
       platforms whose editor expects HTML, and flattened to plain text for the
       short-post platforms. Shipping raw Markdown to a platform declared as
       ``html`` was the old behaviour and it was simply wrong: the editor would
       show ``## heading`` as literal characters.
    2. **Title folding.** Short-post platforms have no title field, so the title
       is folded into the body head instead of being dropped.
    3. **Budget.** Over the hard limit the body is *condensed by sentence*, not
       cut mid-character. A post that ends in the middle of a sentence is a
       delivered defect, so the method used is reported back.

    Blocks are never silently swallowed: every rewording lands in ``blockers``
    or ``warnings`` so a human can see why the delivered text differs from the
    reviewed text.
    """
    r = rules(platform_id)
    fmt = r["native_format"]
    blockers: list[str] = []
    warnings: list[str] = []

    title = (title or "").strip()
    body = (body or "").strip()
    source_format = _detect_format(body)

    if fmt == "text":
        # Short-post platforms have no title field at all. Fold the title into
        # the body head so the meaning survives, then drop the title.
        body = _to_plain_text(body)
        if title and not body.startswith(title):
            body = f"{title} {body}".strip() if body else title
        title = ""
    elif fmt == "html" and source_format == "markdown":
        body = _markdown_to_html(body)
    elif fmt == "markdown" and source_format == "html":
        warnings.append("HTML_SOURCE_FOR_MARKDOWN_TARGET:未做反向转换，保留原文")

    title_len = weighted_len(title, platform_id)
    if r["title_max_hard"] and title_len > r["title_max_hard"]:
        blockers.append(f"TITLE_OVER_HARD:{title_len}>{r['title_max_hard']}")
    elif r["title_max_soft"] and title_len > r["title_max_soft"]:
        warnings.append(f"TITLE_OVER_SOFT:{title_len}>{r['title_max_soft']}")

    method = "as_is"
    body_len = weighted_len(body, platform_id)
    if r["body_max_hard"] and body_len > r["body_max_hard"]:
        condensed, method = _condense(body, r["body_max_hard"], platform_id)
        blockers.append(
            f"BODY_OVER_HARD:{body_len}>{r['body_max_hard']}"
        )
        blockers.append(f"BODY_REWRITTEN:{method}:{body_len}->{weighted_len(condensed, platform_id)}")
        body = condensed
        body_len = weighted_len(body, platform_id)
    elif r["body_max_soft"] and body_len > r["body_max_soft"]:
        warnings.append(f"BODY_OVER_SOFT:{body_len}>{r['body_max_soft']}")

    return {
        "platform_id": platform_id,
        "native_format": fmt,
        "source_format": source_format,
        "title": title,
        "body": body,
        "title_len": title_len,
        "body_len": body_len,
        "budget_method": method,
        "blockers": blockers,
        "warnings": warnings,
    }


_SENTENCE_END = "。！？!?；;…\n"


def _split_sentences(text: str) -> list[str]:
    """Split on sentence terminators, keeping the terminator with its sentence."""
    out: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in _SENTENCE_END:
            sentence = "".join(buf).strip()
            if sentence:
                out.append(sentence)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def _condense(body: str, budget: int, platform_id: str) -> tuple[str, str]:
    """Fit ``body`` into ``budget`` by whole sentences, then hard-cut as a last resort.

    Whole-sentence condensation is the difference between an X post that reads
    like a summary and one that stops mid-word. If not even the first sentence
    fits, there is nothing to condense and a character cut is the only honest
    option, so that is reported as its own method.
    """
    sentences = _split_sentences(body)
    if not sentences:
        return "", "empty"

    kept: list[str] = []
    used = 0
    for sentence in sentences:
        cost = weighted_len(sentence, platform_id)
        separator = 1 if kept else 0
        if used + separator + cost > budget:
            break
        kept.append(sentence)
        used += separator + cost

    if kept:
        out = " ".join(kept)
        if len(kept) < len(sentences):
            ellipsis = "…"
            if weighted_len(out, platform_id) + weighted_len(ellipsis, platform_id) <= budget:
                out += ellipsis
        return out, "sentence_condense"

    return _truncate(body, budget, platform_id), "char_truncate"


def _truncate(body: str, budget: int, platform_id: str) -> str:
    out: list[str] = []
    used = 0
    for ch in body:
        cost = weighted_len(ch, platform_id)
        if used + cost > budget:
            break
        out.append(ch)
        used += cost
    return "".join(out)


# re.M is required: these patterns are used both with .match() per line and with
# .sub() over the whole body. Without it, .sub() only rewrote the first line, so
# a flattened Weibo post still carried literal "## " markers and repeated its
# own title. Found by running the real bundle, not by reading the code.
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$", re.M)
_MD_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$", re.M)
_MD_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$", re.M)
_MD_CODE_FENCE = re.compile(r"^```(.*)$")
_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _detect_format(body: str) -> str:
    if re.search(r"^#{1,6}\s", body, re.M) or re.search(r"^```", body, re.M):
        return "markdown"
    if re.search(r"<(p|div|h[1-6]|ul|ol|li|br)\b", body, re.I):
        return "html"
    return "text"


def _escape_html(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _inline(text: str) -> str:
    out = _escape_html(text)
    out = _MD_INLINE_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _MD_BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    return out


def _markdown_to_html(body: str) -> str:
    """Minimal, deterministic Markdown → HTML for platform editors.

    Deliberately narrow: headings, bullet/ordered lists, fenced code, inline
    code, bold, paragraphs. Anything outside this subset is passed through as
    escaped text rather than guessed at, because a wrong guess in a delivered
    article is worse than plain text.
    """
    lines = body.splitlines()
    out: list[str] = []
    list_kind: str | None = None
    in_code = False

    def close_list() -> None:
        nonlocal list_kind
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = None

    for raw in lines:
        fence = _MD_CODE_FENCE.match(raw.strip())
        if fence:
            if in_code:
                out.append("</code></pre>")
                in_code = False
            else:
                close_list()
                lang = fence.group(1).strip()
                cls = f' class="language-{lang}"' if lang else ""
                out.append(f"<pre><code{cls}>")
                in_code = True
            continue
        if in_code:
            out.append(_escape_html(raw))
            continue

        if not raw.strip():
            close_list()
            continue

        heading = _MD_HEADING.match(raw)
        if heading:
            close_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            continue

        bullet = _MD_BULLET.match(raw)
        ordered = _MD_ORDERED.match(raw)
        if bullet or ordered:
            want = "ul" if bullet else "ol"
            if list_kind != want:
                close_list()
                out.append(f"<{want}>")
                list_kind = want
            text = (bullet or ordered).group(1).strip()
            out.append(f"<li>{_inline(text)}</li>")
            continue

        close_list()
        out.append(f"<p>{_inline(raw.strip())}</p>")

    close_list()
    if in_code:
        out.append("</code></pre>")
    return "\n".join(out)


def _to_plain_text(body: str) -> str:
    """Flatten Markdown/HTML to plain text, keeping line breaks meaningful."""
    text = body
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = _MD_HEADING.sub(lambda m: m.group(2).strip(), text)
    text = _MD_BULLET.sub(lambda m: m.group(1).strip(), text)
    text = _MD_ORDERED.sub(lambda m: m.group(1).strip(), text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _MD_INLINE_CODE.sub(lambda m: m.group(1), text)
    text = _MD_BOLD.sub(lambda m: m.group(1), text)
    text = text.replace("**", "").replace("`", "")
    parts = [p.strip() for p in re.split(r"\s{2,}|\n+", text) if p.strip()]
    return " ".join(parts)


def capability_matrix() -> list[dict[str, Any]]:
    """One row per graphic platform: shape, channels, what it still needs."""
    rows: list[dict[str, Any]] = []
    for pid in platform_ids():
        row = spec(pid)
        r = rules(pid)
        rows.append(
            {
                "platform_id": pid,
                "display_name": row["display_name"],
                "registry_row": row["registry_row"],
                "native_format": r["native_format"],
                "title_max_hard": r["title_max_hard"],
                "body_max_hard": r["body_max_hard"],
                "needs_cover": r["needs_cover"],
                "cover_ratio": r["cover_ratio"],
                "recommended_tags": r["recommended_tags"],
                "channels": [ch["id"] for ch in channels(pid)],
                "api_publish_path": can_publish_via_api(pid),
                "requires": requirements(pid),
                "note": str(row.get("note") or ""),
            }
        )
    return rows


def main(argv: Iterable[str] | None = None) -> int:
    """Tiny operator entry point: ``python -m ... graphic_specs [--json]``."""
    import json

    args = list(argv or sys.argv[1:])
    as_json = "--json" in args
    matrix = capability_matrix()
    if as_json:
        print(json.dumps({"platforms": matrix, "excluded": load_specs()["excluded"]},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"{'platform':16} {'reg':4} {'fmt':9} {'title':>6} {'body':>7} {'cover':>6}  channels")
    for row in matrix:
        print(
            f"{row['platform_id']:16} {'Y' if row['registry_row'] else '-':4}"
            f" {row['native_format']:9} {row['title_max_hard']:>6} {row['body_max_hard']:>7}"
            f" {row['cover_ratio']:>6}  {', '.join(row['channels'])}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
