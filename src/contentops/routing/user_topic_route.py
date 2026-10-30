"""Route B: the user names the topic, and the router serves it.

Why this exists
---------------
This route is not a special case of the hot-list route. It is a different
entrance with different guarantees, and the differences matter:

- **The topic is the user's.** It is never replaced, reworded, or exchanged
  for something more timely. If the account's terms do not cover it, the
  account owner is asked to decide — the topic is not swapped out from under
  them.
- **The hot-list engine does not run.** There is no plan, no collection, no
  candidate pool. A user who knows what they want to talk about should not
  wait for a collector to find something else first.
- **The topic does not have to be recent.** A question about how a tool worked
  two years ago is a legitimate episode. Nothing in this route compares the
  topic against a freshness window.

What still happens
------------------
The same profile check, the same alignment judgement, the same brief package
and the same downstream pipeline. A topic that is off-profile produces a
review state, not a different kind of brief.

Evidence
--------
A user topic usually arrives with material: links, a local document, a
draft. Those become the topic's references. Additional evidence may be
fetched, but only from sources that accept a query — the list-only sources
are not consulted, because consulting them would be running the hot-list
engine with a different name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..routing.models import RoutingError, utcnow
from .account_profile import AccountProfile
from ..hotspots.adapters import FetchResult, RawItem
from .brief import alignment_for
from ..hotspots.source_registry import NATIVE_SEARCH, SOURCES


@dataclass
class UserTopicInput:
    """Everything the user may hand over as the starting material."""

    topic: str
    urls: List[str] = field(default_factory=list)
    local_paths: List[str] = field(default_factory=list)
    draft: Optional[str] = None
    notes: str = ""

    def is_empty(self) -> bool:
        return not self.topic.strip() and not self.urls and not self.local_paths \
            and not (self.draft or "").strip()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "urls": list(self.urls),
            "local_paths": list(self.local_paths),
            "has_draft": bool((self.draft or "").strip()),
            "notes": self.notes,
        }


def read_draft(path: str) -> str:
    """Read a draft the user pointed at.

    A path that cannot be read is a refusal with a name, not an empty draft:
    a silently empty draft would turn the user's material into nothing.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise RoutingError("INPUT_UNREADABLE",
                           f"the draft {path} does not exist")
    try:
        return resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RoutingError("INPUT_UNREADABLE",
                           f"the draft {path} is not UTF-8 text: {exc}") from None
    except OSError as exc:
        raise RoutingError("INPUT_UNREADABLE",
                           f"the draft {path} could not be read: {exc}") from None


def validate_references(urls: List[str]) -> List[str]:
    """Which of the given links are usable. Returns the failures."""
    from urllib.parse import urlparse
    failures: List[str] = []
    for url in urls:
        try:
            parsed = urlparse(url)
        except ValueError:
            failures.append(f"{url!r} is not a parsable URL")
            continue
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            failures.append(f"{url!r} is not an http(s) URL")
    return failures


def evaluate(profile: AccountProfile, payload: UserTopicInput) -> Dict[str, Any]:
    """The alignment judgement for a user topic.

    ``ALIGNED`` and ``ADJACENT`` proceed. ``OFF_POSITIONING`` is a review: the
    router returns it and the user decides whether to change the topic or to
    approve the exception explicitly.
    """
    text = " ".join(part for part in (
        payload.topic,
        " ".join(payload.urls),
        payload.draft or "",
        payload.notes,
    ) if part)
    result = alignment_for(profile, text)
    result["input"] = payload.to_dict()
    return result


def collect_evidence(profile: AccountProfile, payload: UserTopicInput, *,
                     adapters: Optional[Dict[str, Any]] = None,
                     timeout: float = 12.0,
                     per_source_limit: int = 10) -> List[FetchResult]:
    """Optional evidence, from query-accepting sources only.

    A list-only source is never contacted here. Reading somebody else's hot
    list because the user named a topic would be the hot-list route wearing a
    different hat, and the two routes are supposed to stay distinguishable.
    """
    from ..hotspots.adapters import adapter_for

    query = payload.topic.strip()
    if not query:
        return []
    terms = list(dict.fromkeys(
        [keyword.term for keyword in profile.keywords_positive if keyword.language == "en"]
        + [keyword.term for keyword in profile.keywords_positive if keyword.language == "zh"]
    ))
    if terms:
        # The topic and the account's terms are alternatives, not a
        # conjunction: a repository about any one of them is evidence for the
        # topic the owner named.
        query = " OR ".join([query] + terms[:8])
    results: List[FetchResult] = []
    for source_id, source in sorted(SOURCES.items()):
        if source.query_mode != NATIVE_SEARCH:
            continue
        if source_id not in (profile.source_allowlist or ()):
            continue
        if source_id in (profile.source_blocklist or ()):
            continue
        adapter = None
        if adapters is not None:
            adapter = adapters.get(source_id)
        if adapter is None:
            adapter = adapter_for(source)
        results.append(adapter.fetch(source, limit=per_source_limit,
                                     timeout=timeout, query=query))
    return results


def evidence_items(results: List[FetchResult]) -> List[Dict[str, Any]]:
    """The successful evidence results, in the shape an intent carries."""
    items: List[Dict[str, Any]] = []
    for result in results:
        if not result.ok:
            continue
        for item in result.items[:10]:
            items.append({
                "source_id": item.source_id,
                "title": item.title,
                "url": item.url,
                "published_at": item.published_at,
                "snippet": item.snippet[:300],
                "collected_at": utcnow(),
            })
    return items


def reference_ids(payload: UserTopicInput) -> List[str]:
    """The topic's own references, as ids the brief can cite."""
    refs: List[str] = []
    for index, url in enumerate(payload.urls, start=1):
        refs.append(f"REF-URL-{index:02d}")
    for index, path in enumerate(payload.local_paths, start=1):
        refs.append(f"REF-LOCAL-{index:02d}")
    if (payload.draft or "").strip():
        refs.append("REF-DRAFT-01")
    return refs


def local_reference_records(payload: UserTopicInput) -> List[Dict[str, Any]]:
    """What the user's local material is, recorded without its contents.

    The path and its size are recorded so a later reader can tell which file
    was meant; the file's text stays where it is, and a document that is not
    there yet is named as missing rather than quietly omitted.
    """
    records: List[Dict[str, Any]] = []
    for path in payload.local_paths:
        resolved = Path(path)
        exists = resolved.is_file()
        records.append({
            "kind": "local_document",
            "path": str(path),
            "exists": exists,
            "bytes": resolved.stat().st_size if exists else None,
        })
    return records
