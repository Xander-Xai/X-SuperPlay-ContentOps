"""Collapse the same story seen in two places into one candidate.

Why this exists
---------------
Two sources carrying the same story is a *signal*: it says the story reached
more than one list. It is not two signals. Left alone, the same headline
appears twice in the shortlist and the person choosing a topic sees a
duplicated option, and the shortlist looks busier than it is.

So duplicates are merged, and the merge is not a deletion: the surviving
candidate keeps the names of the other sources under ``also_seen_in``, and the
count of distinct sources feeds the ``cross_source_signal`` component of the
score. The evidence of broad coverage survives the de-duplication.

How two titles are judged the same
----------------------------------
By their normalised token sets, not by string equality. ``"LangGraph 1.0 发布"``
and ``"发布 LangGraph 1.0"`` normalise to the same tokens; a shared URL is an
exact match. A near-match with a different token count is *not* merged: two
genuinely different stories about the same product are two topics, and
merging them would lose the narrower one.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .ranking import normalise, token_set


def title_key(title: str) -> str:
    """The normalised form of a title, used as the merge key."""
    return normalise(title)


def url_key(url: str) -> str:
    """A URL reduced to what identifies it: no fragment, no trailing slash."""
    if not url:
        return ""
    trimmed = url.split("#", 1)[0].strip()
    if trimmed.endswith("/"):
        trimmed = trimmed[:-1]
    return trimmed.casefold()


def _tokens_of(candidate: Dict[str, Any]) -> frozenset:
    return token_set(str(candidate.get("title") or ""))


def same_story(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    """Whether two candidates are the same story.

    The rule is deliberately conservative, because merging two different
    stories loses one of them:

    - the same URL is the same story;
    - the same normalised title is the same story;
    - the same token set in a different order is the same story;
    - one title that adds at most one word to the other is the same story,
      provided the shorter one carries at least three words — otherwise
      "AI" would swallow "AI 新模型", which is a subject and not a qualifier.

    Anything beyond that is two topics. "LangGraph 1.0" and "LangGraph 1.0 的
    RAG 实践" differ by more than one word and stay apart.
    """
    left_url = url_key(str(left.get("url") or ""))
    right_url = url_key(str(right.get("url") or ""))
    if left_url and left_url == right_url:
        return True
    left_key = title_key(str(left.get("title") or ""))
    right_key = title_key(str(right.get("title") or ""))
    if not left_key or not right_key:
        return False
    if left_key == right_key:
        return True
    left_tokens = token_set(str(left.get("title") or ""))
    right_tokens = token_set(str(right.get("title") or ""))
    if not left_tokens or not right_tokens:
        return False
    if left_tokens == right_tokens:
        return True
    if left_tokens <= right_tokens or right_tokens <= left_tokens:
        smaller, larger = sorted((left_tokens, right_tokens), key=len)
        if len(smaller) >= 3 and len(larger) - len(smaller) <= 1:
            return True
    return False


def dedupe(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge duplicates, keeping the earliest-published as the survivor.

    The survivor is the one with the most sources already merged into it, and
    ties break on the publication time: the first report of a story is the one
    worth keeping the link to.
    """
    survivors: List[Dict[str, Any]] = []
    for candidate in candidates:
        match = None
        for survivor in survivors:
            if same_story(survivor, candidate):
                match = survivor
                break
        if match is None:
            survivors.append(dict(candidate))
            continue
        merged = list(match.get("also_seen_in") or [])
        source_id = str(candidate.get("source_id") or "")
        if source_id and source_id not in merged:
            merged.append(source_id)
        match["also_seen_in"] = merged
        # The survivor keeps its own title but inherits the earliest timestamp,
        # because that is when the story first appeared.
        existing = str(match.get("published_at") or "")
        incoming = str(candidate.get("published_at") or "")
        if incoming and (not existing or incoming < existing):
            match["published_at"] = incoming
        if not match.get("url") and candidate.get("url"):
            match["url"] = candidate["url"]
    return survivors


def distinct_sources(candidate: Dict[str, Any]) -> int:
    """How many distinct sources carry a candidate, after merging."""
    others = candidate.get("also_seen_in") or []
    sources = {str(candidate.get("source_id") or "")}
    sources.update(str(item) for item in others)
    sources.discard("")
    return len(sources)
