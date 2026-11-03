"""The material a technical episode is actually made of.

Why this exists
---------------
A brief can carry a topic and a link and still contain nothing a viewer would
learn. Turning that into a video means padding it with transitions and a call
to action, which is a hollow script that passes every schema check. This module
is the answer to that: the script stage is only allowed to speak about material
that was collected, saved and hashed.

What counts as material
-----------------------
An **evidence pack** — a JSON file listing what was read, where from, when, and
the file each excerpt was saved to. The files are written next to the script so
the digest in the claim map always names bytes a reviewer can open. Official
documentation, source code and data all qualify. A link on its own does not:
"there is a page somewhere" is not something an episode can teach.

What the digest proves, and what it does not
--------------------------------------------
The sha256 proves the file has not changed since it was collected. It says
nothing about whether the document is right, current, or relevant — that is the
reviewer's judgement, and the copy review is where it is exercised.

Sufficiency
-----------
:func:`sufficiency` answers one question: is there enough material for the
episode the account wants? Too little is reported as
``DRAFT_CONTENT_INSUFFICIENT`` with the specific gaps, never filled with
transitions.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PACK_SCHEMA = "contentops.evidence-pack/v1"

#: Where the pack lives inside a project.
PACK_FILE = Path("00_brief") / "evidence-pack.json"

#: How much material an episode needs before it may be drafted. These are the
#: numbers a reviewer can argue with; they are deliberately conservative.
MIN_ITEMS = 3
MIN_EXCERPT_CHARS = 400

#: A sentence longer than this is skipped rather than cut: a quote that stops
#: mid-clause is a sentence the source did not write.
MAX_QUOTE_CHARS = 150


@dataclass
class EvidenceItem:
    evidence_id: str
    kind: str
    title: str
    url: str
    excerpt: str
    document: str = ""
    sha256: str = ""
    retrieved_at: str = ""
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"evidence_id": self.evidence_id, "kind": self.kind,
                "title": self.title, "url": self.url, "excerpt": self.excerpt,
                "document": self.document, "sha256": self.sha256,
                "retrieved_at": self.retrieved_at, "note": self.note}


@dataclass
class EvidencePack:
    topic: str
    items: List[EvidenceItem] = field(default_factory=list)

    @property
    def characters(self) -> int:
        return sum(len(item.excerpt) for item in self.items)

    def to_dict(self) -> Dict[str, Any]:
        return {"schema": PACK_SCHEMA, "topic": self.topic,
                "items": [item.to_dict() for item in self.items]}


def load_pack(path: Path) -> EvidencePack:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != PACK_SCHEMA:
        raise ValueError(f"{path}: expected schema {PACK_SCHEMA!r}, "
                         f"got {document.get('schema')!r}")
    items = []
    for raw in document.get("items") or []:
        items.append(EvidenceItem(
            evidence_id=str(raw.get("evidence_id") or ""),
            kind=str(raw.get("kind") or ""),
            title=str(raw.get("title") or ""),
            url=str(raw.get("url") or ""),
            excerpt=str(raw.get("excerpt") or ""),
            document=str(raw.get("document") or ""),
            sha256=str(raw.get("sha256") or ""),
            retrieved_at=str(raw.get("retrieved_at") or ""),
            note=str(raw.get("note") or ""),
        ))
    return EvidencePack(topic=str(document.get("topic") or ""), items=items)


def sufficiency(pack: Optional[EvidencePack], *, min_items: int = MIN_ITEMS,
                min_chars: int = MIN_EXCERPT_CHARS) -> Dict[str, Any]:
    """Is there enough collected material to make an episode about?"""
    if pack is None or not pack.items:
        return {"ok": False, "code": "DRAFT_CONTENT_INSUFFICIENT",
                "missing": ["没有证据包：需要至少 "
                            f"{min_items} 条来自官方文档、源码或数据的可引用材料"],
                "items": 0, "characters": 0}
    missing: List[str] = []
    usable = [item for item in pack.items if item.excerpt.strip() and item.document]
    if len(usable) < min_items:
        missing.append(f"可引用材料只有 {len(usable)} 条，少于要求的 {min_items} 条")
    characters = sum(len(item.excerpt) for item in usable)
    if characters < min_chars:
        missing.append(f"可引用正文只有 {characters} 字，少于要求的 {min_chars} 字")
    for item in pack.items:
        if not item.url:
            missing.append(f"{item.evidence_id or '(no id)'} 没有来源链接")
        if not item.sha256:
            missing.append(f"{item.evidence_id or '(no id)'} 没有内容摘要")
    return {"ok": not missing, "code": "OK" if not missing else "DRAFT_CONTENT_INSUFFICIENT",
            "missing": missing, "items": len(usable), "characters": characters}


def quotes(pack: EvidencePack, *, per_item: Optional[int] = None,
           max_chars: int = MAX_QUOTE_CHARS) -> List[Tuple[EvidenceItem, str]]:
    """The sentences of the pack that a script may actually say.

    Order is the pack's order, which is the order the collector wrote, so the
    script follows the source rather than a ranking invented here.
    """
    chosen: List[Tuple[EvidenceItem, str]] = []
    for item in pack.items:
        sentences = _sentences(_clean(item.excerpt))
        for sentence in (sentences if per_item is None else sentences[:per_item]):
            if len(sentence) < 12 or len(sentence) > max_chars:
                continue
            if _code_like(sentence):
                continue
            chosen.append((item, sentence))
    return chosen


def _clean(text: str) -> str:
    """The readable prose of an excerpt, without the document's scaffolding.

    Front matter, MDX/JSX comments, HTML comments, code fences, headings and
    list markers are not something a narrator says, so they are removed before
    the text is split into sentences.
    """
    body = str(text or "").replace("\r\n", "\n")
    body = re.sub(r"\A\s*---\n.*?\n---\s*\n", "", body, flags=re.DOTALL)
    body = re.sub(r"\{/\*.*?\*/\}", " ", body, flags=re.DOTALL)
    body = re.sub(r"<!--.*?-->", " ", body, flags=re.DOTALL)
    body = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    body = re.sub(r"^\s{0,3}#{1,6}\s*", "", body, flags=re.MULTILINE)
    body = re.sub(r"^\s*[-*+]\s+", "", body, flags=re.MULTILINE)
    body = re.sub(r"[*_`]{1,3}", "", body)
    body = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", body)
    return body


def _code_like(sentence: str) -> bool:
    """True when a 'sentence' is really source code or a path."""
    text = sentence.strip()
    if not text:
        return True
    letters = sum(1 for char in text if char.isalpha())
    symbols = sum(1 for char in text if char in "{}[]();=<>/\\|$")
    return symbols > 0 and symbols >= letters / 3


def _sentences(text: str) -> List[str]:
    """Split on sentence ends without breaking on decimals or abbreviations."""
    normalised = " ".join(str(text or "").split())
    parts: List[str] = []
    current = ""
    for char in normalised:
        current += char
        if char in "。！？!?" or (char == "." and len(current) > 40):
            parts.append(current.strip())
            current = ""
    if current.strip():
        parts.append(current.strip())
    return [part for part in parts if part]
