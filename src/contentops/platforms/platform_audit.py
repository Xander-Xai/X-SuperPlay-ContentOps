"""Per-platform content audit: the part that is not about length.

Length limits were the only per-platform rule this project had, which meant four
platforms received byte-identical bodies and every one of them carried zero tags.
That is not "optimised per platform", it is one draft shipped four times.

This module adds the checks that actually differ by platform, all offline and
deterministic:

* **Topic coverage** - the title declares the topic; if the body never uses the
  title's own key terms, the article will not rank on that topic. Derived from
  the text itself, so it needs no keyword plan and no LLM.
* **Tag suggestions** - every platform in the spec recommends 2-6 tags and the
  pack reported ``TAGS_BELOW_RECOMMENDED`` for five of them. Tags are extracted
  from the body by n-gram frequency with an explicit stop-word list.
* **Digest** - WeChat and Toutiao want a short summary; the spec carried
  ``summary_max`` but nothing produced one.
* **Code fences** - CSDN and Juejin render fenced blocks with the language
  badge; an unlabelled fence becomes a grey box and breaks the article's
  technical credibility.

Design note: nothing here rewrites the article. It measures, proposes tags and
records findings, because silently rewriting the author's prose is how a
delivery pipeline starts shipping text nobody reviewed.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# Words that carry no topic signal. Kept small and explicit on purpose: a long
# opaque stop-word list is unreviewable, and for Chinese n-grams the most common
# errors are function words and connectives, which are easy to enumerate.
STOPWORDS: frozenset[str] = frozenset(
    """
    这个 那个 这些 那些 我们 你们 他们 它们 自己 什么 怎么 为什么 因为 所以 但是 如果
    而且 或者 以及 并且 然后 现在 刚才 已经 可以 应该 需要 必须 不是 就是 还是 只是
    非常 特别 十分 比较 更加 最为 一直 始终 总是 经常 有时 偶尔 从未 从来
    通过 关于 对于 由于 根据 按照 依照 基于 针对 除了 包括 例如 比如 就像 如同
    一下 一些 一种 一样 一起 有一点 有点 有些 有的 这样 那样 怎样 如何 是否
    上面 下面 前面 后面 里面 外面 之间 之中 之后 之前 之后 其中 其他 其它
    这里 那里 哪里 每个 各个 任何 所有 全部 整个 部分 大量 少量
    可以 能够 可能 或许 也许 大概 大约 左右 等等 之类 云云
    时候 时间 地方 东西 事情 问题 情况 方面 方式 方法 过程 结果 原因
    the and for that with from this are was were has have had not but you your
    """.split()
)

CJK_RUN = re.compile(r"[\u4e00-\u9fff]{2,}")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_+#.-]{2,}")
CODE_FENCE = re.compile(r"^```([A-Za-z0-9_+-]*)\s*$", re.M)
MD_NOISE = re.compile(r"```.*?```|`[^`]*`|!\[[^\]]*\]\([^)]*\)|\[[^\]]*\]\([^)]*\)", re.S)

# An n-gram that starts or ends with one of these is a fragment of a sentence,
# not a term: "管它的边" and "它的边界" are both pieces of "接管它的边界". Observing
# the first real run of this module produced exactly those two as tags.
PARTICLES = "的了和与及或在是有也就都而之为对把被从向于着过很更最又还再"


def _overlaps(a: str, b: str, minimum: int = 3) -> bool:
    """True when ``a`` and ``b`` share a contiguous run of ``minimum`` characters."""
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return True
    if len(shorter) < minimum:
        return False
    for size in range(len(shorter), minimum - 1, -1):
        for start in range(len(shorter) - size + 1):
            if shorter[start:start + size] in longer:
                return True
    return False


def _is_fragment(gram: str) -> bool:
    """Reject sentence pieces masquerading as terms.

    A particle at either end ("它的边界", "管它的边") marks a cut through a phrase.
    A particle in the middle ("管它的边" -> 的 at index 2) is the same problem seen
    from the other side: real Chinese terms almost never contain 的/了/和
    internally, while sliding n-grams over a sentence almost always do.
    """
    if not gram:
        return False
    if gram[0] in PARTICLES or gram[-1] in PARTICLES:
        return True
    return any(ch in PARTICLES for ch in gram[1:-1])


def _strip_markup(text: str) -> str:
    text = MD_NOISE.sub(" ", text)
    text = re.sub(r"^[#>\-\*\+\d.\s]+", " ", text, flags=re.M)
    return text


def _ngrams(run: str, sizes: Iterable[int] = (2, 3, 4)) -> Iterable[str]:
    for size in sizes:
        if len(run) < size:
            continue
        for start in range(len(run) - size + 1):
            gram = run[start:start + size]
            if gram in STOPWORDS or _is_fragment(gram):
                continue
            yield gram


def keyword_scores(text: str) -> dict[str, float]:
    """Score candidate topic terms in ``text``.

    Longer n-grams win ties because in Chinese a 3- or 4-gram is far more likely
    to be a real term ("混合专家模型") than a 2-gram fragment ("合专"). The score
    therefore multiplies frequency by a mild length bonus.
    """
    clean = _strip_markup(text)
    counts: dict[str, int] = {}

    for run in CJK_RUN.findall(clean):
        for gram in _ngrams(run):
            counts[gram] = counts.get(gram, 0) + 1
    for word in LATIN_WORD.findall(clean):
        lowered = word.lower()
        if lowered in STOPWORDS:
            continue
        counts[lowered] = counts.get(lowered, 0) + 1

    scored: dict[str, float] = {}
    for gram, count in counts.items():
        if count < 2 and len(gram) < 3:
            # A single occurrence of a 2-gram is noise, not a topic.
            continue
        length = len(gram)
        scored[gram] = count * (1.0 + 0.35 * max(0, length - 2))

    # Drop fragments fully contained in a stronger, longer candidate.
    ranked = sorted(scored.items(), key=lambda kv: (-kv[1], -len(kv[0])))
    kept: dict[str, float] = {}
    for gram, score in ranked:
        redundant = any(
            gram != other and gram in other and other_score >= score
            for other, other_score in kept.items()
        )
        if not redundant:
            kept[gram] = score
    return kept


def suggest_tags(title: str, body: str, limit: int) -> list[str]:
    """Pick up to ``limit`` topic tags, title terms first."""
    title_scores = keyword_scores(title)
    body_scores = keyword_scores(body)

    merged: dict[str, float] = {}
    for gram, score in body_scores.items():
        merged[gram] = score
    for gram, score in title_scores.items():
        # A term the author put in the title is a deliberate topic signal.
        merged[gram] = merged.get(gram, 0.0) + score * 2.0

    ranked = sorted(merged.items(), key=lambda kv: (-kv[1], -len(kv[0])))
    tags: list[str] = []
    for gram, _score in ranked:
        # Reject fragments of a term already kept, and anything sharing a long
        # run with it. Without this, "接管它的边界" yields both "管它的边" and
        # "它的边界" as separate tags.
        if any(_overlaps(gram, existing) for existing in tags):
            continue
        tags.append(gram)
        if len(tags) >= limit:
            break
    return tags


def build_digest(body: str, max_chars: int) -> str:
    """First sentences of the lede, trimmed to ``max_chars``."""
    if max_chars <= 0:
        return ""
    plain = _strip_markup(body)
    plain = " ".join(plain.split())
    if len(plain) <= max_chars:
        return plain
    cut = plain[:max_chars]
    for sep in ("。", "！", "？", "；", ".", "!", "?", ";"):
        pos = cut.rfind(sep)
        if pos >= max_chars * 0.5:
            return cut[: pos + 1]
    return cut.rstrip() + "…"


def unlabelled_code_fences(body: str) -> int:
    """Count fenced blocks that carry no language tag."""
    return sum(1 for lang in CODE_FENCE.findall(body) if not lang.strip())


def title_terms_missing_from_body(title: str, body: str, limit: int = 3) -> list[str]:
    """Title terms the body never uses again.

    Case-insensitive on purpose: the first real run reported ``easel`` missing
    from a body that says ``Easel`` four times. A check that fires on casing is
    noise, and noise in a warning list trains people to ignore the list.
    """
    body_clean = _strip_markup(body).lower()
    missing: list[str] = []
    for term, _score in sorted(
        keyword_scores(title).items(), key=lambda kv: (-kv[1], -len(kv[0]))
    ):
        if term.lower() not in body_clean:
            missing.append(term)
        if len(missing) >= limit:
            break
    return missing


def audit(platform_id: str, title: str, body: str, *, rules: dict[str, Any]) -> dict[str, Any]:
    """Run every per-platform content check and return findings.

    ``rules`` is the normalised dict from ``graphic_specs.rules()`` so this
    module never re-reads the spec file and stays a pure function of its inputs.
    """
    blockers: list[str] = []
    warnings: list[str] = []

    recommended = int(rules.get("recommended_tags") or 0)
    summary_max = int(rules.get("summary_max") or 0)

    tags = suggest_tags(title, body, recommended) if recommended else []
    if recommended and len(tags) < recommended:
        warnings.append(f"TAGS_EXTRACTED_BELOW_RECOMMENDED:{len(tags)}<{recommended}")

    digest = build_digest(body, summary_max) if summary_max else ""

    if title:
        missing = title_terms_missing_from_body(title, body)
        if missing:
            warnings.append("TITLE_TERM_ABSENT_FROM_BODY:" + ",".join(missing))

    if platform_id in ("csdn", "juejin"):
        bare = unlabelled_code_fences(body)
        if bare:
            warnings.append(f"CODE_FENCE_WITHOUT_LANGUAGE:{bare}")

    # Juejin requires a category and at least one tag before an article can be
    # submitted at all; the bridge CLI has no flag for either, so this must be a
    # pre-flight finding rather than a silent gap.
    if platform_id == "juejin" and len(tags) < 1:
        blockers.append("CATEGORY_AND_TAG_REQUIRED")

    return {
        "platform_id": platform_id,
        "suggested_tags": tags,
        "digest": digest,
        "digest_len": len(digest),
        "blockers": blockers,
        "warnings": warnings,
    }
