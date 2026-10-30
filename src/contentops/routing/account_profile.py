"""Resolve an account DNA into the profile that drives every retrieval decision.

Why this exists
---------------
The account DNA already said what an account is about: its pillars, its
audience, what it refuses to make, and the one question each episode answers.
Those facts lived in a document the pipeline read *after* the topic was
chosen. A hot-list collector, added on top, would have had to invent its own
account model — and an invented account model is the failure this module
exists to prevent: a broad collector that fetches everything and lets a model
sort it afterwards.

So the DNA is read first, and everything downstream is a consequence of it:

- **keywords** decide what a source is asked for;
- **source allowlist / blocklist** decide which sources are contacted at all;
- **pillars** decide which candidate belongs to which shelf;
- **not-doing** decides which candidates are rejected before a person sees them;
- **weights** decide the order of the shortlist.

The anti-invention guarantee
-----------------------------
A keyword may only exist if it can be traced to text the account owner wrote.
Each keyword carries an ``origin`` naming the DNA field it came from, and
:func:`verify_origin` resolves that reference against the DNA *in the same
file*. A keyword whose origin cannot be resolved is a failure, not a warning:
there is no path by which an unsourced term enters a search.

An English keyword is allowed to be a translation of a Chinese one, because a
translation is not a new positioning claim — but its Chinese source must
resolve the same way, and the translation is marked as such.

What is deliberately not claimed
--------------------------------
This module resolves what the account *declared*. It does not check whether the
declaration is a good one. A founder can write a profile with a bad source
allowlist; what they cannot do is write one that silently disagrees with the
keywords and pillars the router will actually use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import RoutingError

ACCOUNTS_DIR = Path("config") / "accounts"
DNA_SCHEMA = "contentops.account-dna/v2"
DISCOVERY_SCHEMA = "contentops.account-discovery/v1"

#: The fields a keyword may cite. Each is resolved against the account's own
#: DNA, so a citation that names a field the account does not have fails.
ORIGIN_KINDS: Tuple[str, ...] = (
    "pillar_name",
    "pillar_scope",
    "pillar_structure",
    "not_doing",
    "excluded",
    "promise",
    "decision_question",
    "mission",
    "tagline",
    "core_audience",
    "audience",
    "platform_note",
    "translation",
)

#: The routing weights, as percentages. They sum to 100 and they are the
#: account's to change: a hot list is not ranked by heat, it is ranked by how
#: well it fits *this* account.
DEFAULT_MATCH_WEIGHTS: Dict[str, int] = {
    "profile_relevance": 30,
    "audience_value": 15,
    "evidence_availability": 20,
    "freshness": 15,
    "cross_source_signal": 10,
    "originality_potential": 5,
    "non_repetition": 5,
}

MATCH_COMPONENTS: Tuple[str, ...] = tuple(DEFAULT_MATCH_WEIGHTS)


@dataclass(frozen=True)
class Keyword:
    """A search term with the DNA field it came from."""

    term: str
    language: str
    origin: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"term": self.term, "language": self.language, "origin": dict(self.origin)}


@dataclass(frozen=True)
class AccountProfile:
    """The account's positioning, as data the router can act on."""

    account_id: str
    slug: str
    platform: str
    positioning: str
    decision_question: str
    target_audience: Tuple[str, ...]
    content_pillars: Tuple[Dict[str, Any], ...]
    topics_include: Tuple[str, ...]
    topics_exclude: Tuple[str, ...]
    keywords_positive: Tuple[Keyword, ...]
    keywords_negative: Tuple[Keyword, ...]
    preferred_sources: Tuple[Dict[str, Any], ...]
    source_allowlist: Tuple[str, ...]
    source_blocklist: Tuple[str, ...]
    language: Tuple[str, ...]
    geography: Tuple[str, ...]
    content_formats: Tuple[str, ...]
    editorial_rules: Tuple[str, ...]
    approval_policy: Dict[str, Any]
    profile_version: str
    profile_source: str
    evidence_mode: str
    manual_recording: str
    target_duration_s: Tuple[float, ...]
    platforms: Tuple[str, ...]
    match_weights: Dict[str, int]
    #: Why the account named each source, keyed by source id.
    source_reasons: Dict[str, str] = field(default_factory=dict)
    #: Per-adapter query expressions, each term traceable to a declared
    #: keyword. Keyed by adapter name (``github_search``); the value is the
    #: ordered list of terms the account wants that source asked for. Empty
    #: means "use the keywords as they are".
    query_expressions: Dict[str, Tuple[str, ...]] = field(default_factory=dict)
    dna: Dict[str, Any] = field(default_factory=dict, repr=False)

    # -- convenience used by the collectors and the ranker ------------------

    @property
    def positive_terms(self) -> Tuple[str, ...]:
        return tuple(keyword.term for keyword in self.keywords_positive)

    @property
    def negative_terms(self) -> Tuple[str, ...]:
        return tuple(keyword.term for keyword in self.keywords_negative)

    def pillar_names(self) -> Tuple[str, ...]:
        return tuple(str(pillar.get("name")) for pillar in self.content_pillars
                     if pillar.get("name"))

    def pillar_for(self, text: str) -> Optional[str]:
        """The pillar a piece of text belongs to, by declared keyword overlap.

        The comparison is case-insensitive, because the account's terms are
        matched that way everywhere else and a title that says "github" is the
        same subject as one that says "GitHub".
        """
        haystack = (text or "").casefold()
        best: Optional[str] = None
        best_hits = 0
        for pillar in self.content_pillars:
            name = str(pillar.get("name") or "")
            scope = str(pillar.get("scope") or "").casefold()
            folded_name = name.casefold()
            hits = 0
            for keyword in self.keywords_positive:
                term = keyword.term.casefold()
                if term and term in haystack:
                    if term in scope or term in folded_name:
                        hits += 2
                    else:
                        hits += 1
            if hits > best_hits:
                best_hits = hits
                best = name or None
        return best

    def summary(self) -> Dict[str, Any]:
        """The profile as it is recorded on an intent and a search plan."""
        return {
            "account_id": self.account_id,
            "slug": self.slug,
            "platform": self.platform,
            "positioning": self.positioning,
            "decision_question": self.decision_question,
            "target_audience": list(self.target_audience),
            "content_pillars": [dict(pillar) for pillar in self.content_pillars],
            "topics_include": list(self.topics_include),
            "topics_exclude": list(self.topics_exclude),
            "language": list(self.language),
            "geography": list(self.geography),
            "content_formats": list(self.content_formats),
            "editorial_rules": list(self.editorial_rules),
            "approval_policy": dict(self.approval_policy),
            "profile_version": self.profile_version,
            "profile_source": self.profile_source,
            "evidence_mode": self.evidence_mode,
            "manual_recording": self.manual_recording,
            "target_duration_s": list(self.target_duration_s),
            "platforms": list(self.platforms),
            "keywords_positive": [keyword.to_dict() for keyword in self.keywords_positive],
            "keywords_negative": [keyword.to_dict() for keyword in self.keywords_negative],
            "source_allowlist": list(self.source_allowlist),
            "source_blocklist": list(self.source_blocklist),
            "preferred_sources": [dict(entry) for entry in self.preferred_sources],
            "match_weights": dict(self.match_weights),
        }


# ---------------------------------------------------------------------------
# origin resolution
# ---------------------------------------------------------------------------


def _pillar(dna: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    for pillar in dna.get("content_pillars") or []:
        if isinstance(pillar, dict) and pillar.get("name") == name:
            return pillar
    return None


def _resolve_origin_text(dna: Dict[str, Any], origin: Dict[str, Any]) -> Optional[str]:
    """The DNA text an origin points at, or ``None`` when it points nowhere."""
    kind = origin.get("kind")
    if kind == "pillar_name":
        pillar = _pillar(dna, str(origin.get("pillar") or ""))
        return None if pillar is None else str(pillar.get("name") or "")
    if kind == "pillar_scope":
        pillar = _pillar(dna, str(origin.get("pillar") or ""))
        return None if pillar is None else str(pillar.get("scope") or "")
    if kind == "pillar_structure":
        pillar = _pillar(dna, str(origin.get("pillar") or ""))
        if pillar is None:
            return None
        steps = pillar.get("structure") or []
        if not isinstance(steps, list):
            return None
        return "\n".join(str(step) for step in steps)
    if kind in ("not_doing", "excluded", "core_audience", "audience"):
        items = dna.get(kind) or []
        if not isinstance(items, list):
            return None
        index = origin.get("index")
        if not isinstance(index, int) or isinstance(index, bool):
            return None
        if index < 0 or index >= len(items):
            return None
        return str(items[index] or "")
    if kind in ("promise", "decision_question", "mission", "tagline", "platform_note"):
        value = dna.get(kind)
        return None if not isinstance(value, str) else value
    return None


def verify_origin(dna: Dict[str, Any], keyword: Keyword) -> List[str]:
    """Whether a keyword is traceable to text the account owner wrote.

    Returns a list of failures; an empty list means the keyword is sourced.
    """
    failures: List[str] = []
    term = keyword.term.strip()
    if not term:
        return ["a keyword term must not be empty"]
    origin = keyword.origin
    if not isinstance(origin, dict) or not origin:
        return [f"keyword {term!r} has no origin"]
    kind = origin.get("kind")
    if kind not in ORIGIN_KINDS:
        return [f"keyword {term!r} cites origin kind {kind!r}, "
                f"expected one of {list(ORIGIN_KINDS)}"]

    if kind == "translation":
        # A translation renders a term the account already declared into
        # another language. It introduces no new subject: the subject is
        # still the founder's word, only spelled differently. Both directions
        # are legitimate — an account that writes "Workflow" also needs
        # "工作流" for a Chinese-language source.
        inner_kind = origin.get("origin_kind")
        inner_term = str(origin.get("origin_term") or "")
        origin_language = str(origin.get("origin_language") or "")
        inner = {"kind": inner_kind, "pillar": origin.get("pillar"),
                 "index": origin.get("index")}
        text = _resolve_origin_text(dna, inner)
        if text is None:
            failures.append(f"keyword {term!r} translates {inner_term!r}, but its "
                            f"origin {inner_kind!r} resolves to nothing in this DNA")
        elif inner_term and inner_term not in text:
            failures.append(f"keyword {term!r} translates {inner_term!r}, which does "
                            f"not appear in the cited DNA text")
        if not origin_language:
            failures.append(f"keyword {term!r} is a translation but declares no "
                            f"origin_language")
        elif origin_language == keyword.language:
            failures.append(f"keyword {term!r} is a translation from "
                            f"{origin_language!r} into {keyword.language!r}; a "
                            f"translation has to change language, otherwise it "
                            f"should cite the field directly")
        return failures

    text = _resolve_origin_text(dna, origin)
    if text is None:
        failures.append(f"keyword {term!r} cites origin {kind!r} "
                        f"{origin.get('pillar') or origin.get('index') or ''!r}, which "
                        f"resolves to nothing in this DNA")
        return failures
    if term not in text:
        failures.append(f"keyword {term!r} does not appear in the DNA text it cites "
                        f"({kind})")
    return failures


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def accounts_dir(root: Path) -> Path:
    return Path(root) / ACCOUNTS_DIR


def list_account_slugs(root: Path) -> List[str]:
    directory = accounts_dir(root)
    if not directory.is_dir():
        return []
    slugs = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        slug = payload.get("slug") or path.stem
        slugs.append(str(slug))
    return slugs


def _keywords(block: Dict[str, Any], key: str) -> Tuple[Keyword, ...]:
    items = block.get(key) or []
    result: List[Keyword] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term") or "").strip()
        if not term:
            continue
        result.append(Keyword(
            term=term,
            language=str(item.get("language") or "zh"),
            origin=dict(item.get("origin") or {}),
        ))
    return tuple(result)


def _source_ids(value: Any) -> Tuple[str, ...]:
    """Source ids from a list of strings or of ``{source_id, why}`` objects.

    The account writes *why* it wants a source, and that reason travels into
    the search plan. The id is what the registry resolves.
    """
    if not isinstance(value, list):
        return ()
    ids: List[str] = []
    for item in value:
        if isinstance(item, str):
            candidate = item.strip()
        elif isinstance(item, dict):
            candidate = str(item.get("source_id") or "").strip()
        else:
            continue
        if candidate:
            ids.append(candidate)
    return tuple(ids)


def _source_entries(value: Any) -> Tuple[Dict[str, Any], ...]:
    """The allowlist or blocklist as records, keeping each entry's reason."""
    if not isinstance(value, list):
        return ()
    entries: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, str):
            entries.append({"source_id": item.strip(), "why": ""})
        elif isinstance(item, dict):
            source_id = str(item.get("source_id") or "").strip()
            if source_id:
                entries.append({"source_id": source_id,
                                "why": str(item.get("why") or "")})
    return tuple(entries)


def _query_expressions(discovery: Dict[str, Any]) -> Dict[str, Tuple[str, ...]]:
    """Per-adapter query terms, in the order the account wants them asked.

    A query expression is not a positioning change. Each term names the
    declared keyword it renders (``from_keyword``), and that keyword already
    carries its own origin in the DNA, so the chain back to something the
    owner wrote is unbroken. What the expression adds is a choice: which of
    those declared terms are worth spending a source's limited query budget
    on, and in what order.
    """
    raw = discovery.get("query_expressions")
    if not isinstance(raw, dict):
        return {}
    expressions: Dict[str, Tuple[str, ...]] = {}
    for adapter, spec in raw.items():
        if not isinstance(spec, dict):
            continue
        terms: List[str] = []
        for item in spec.get("terms") or []:
            if isinstance(item, dict):
                term = str(item.get("term") or "").strip()
            else:
                term = str(item or "").strip()
            if term and term not in terms:
                terms.append(term)
        if terms:
            expressions[str(adapter)] = tuple(terms)
    return expressions


def _strings(value: Any) -> Tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _pillar_topics(dna: Dict[str, Any]) -> Tuple[str, ...]:
    """The topics the account says it covers, taken from its own pillars."""
    topics: List[str] = []
    for pillar in dna.get("content_pillars") or []:
        if not isinstance(pillar, dict):
            continue
        for field in ("name", "scope"):
            value = str(pillar.get(field) or "").strip()
            if value:
                topics.append(value)
    return tuple(dict.fromkeys(topics))


def _exclude_topics(dna: Dict[str, Any]) -> Tuple[str, ...]:
    """What the account says it does not do, plus the audiences it drops."""
    topics: List[str] = []
    for key in ("not_doing", "excluded"):
        for value in _strings(dna.get(key)):
            topics.append(value)
    return tuple(dict.fromkeys(topics))


def _editorial_rules(dna: Dict[str, Any]) -> Tuple[str, ...]:
    rules: List[str] = []
    for key in ("forbidden", "non_negotiable"):
        for value in _strings(dna.get(key)):
            rules.append(value)
    for value in _strings((dna.get("evidence") or {}).get("rules")):
        rules.append(value)
    return tuple(dict.fromkeys(rules))


def _video_capable(dna: Dict[str, Any]) -> Tuple[str, ...]:
    """The platforms this account actually publishes video on.

    ``platforms`` is the account's own active video list; ``derived_platforms``
    and ``text_platforms`` are downstream surfaces reached from a video, not
    places a video is cut for. A text-only account therefore has an empty
    tuple and is refused a video pipeline rather than forced into one.
    """
    return _strings(dna.get("platforms"))


def load_profile(root: Path, slug: str) -> AccountProfile:
    """Resolve one account's DNA into an :class:`AccountProfile`.

    Raises :class:`RoutingError` with ``ACCOUNT_DNA_MISSING`` when the account
    has no DNA, or when its DNA carries no usable discovery block. There is no
    fallback that guesses: an account the owner has not described is an
    account the router cannot search on behalf of.
    """
    root = Path(root)
    path = accounts_dir(root) / f"{slug}.json"
    if not path.is_file():
        raise RoutingError(
            "ACCOUNT_DNA_MISSING",
            f"no account DNA at {path.as_posix()}; the router will not invent "
            f"an account's positioning")
    try:
        dna = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RoutingError("ACCOUNT_DNA_MALFORMED",
                           f"{path.as_posix()} is not valid JSON: {exc}") from None
    if not isinstance(dna, dict):
        raise RoutingError("ACCOUNT_DNA_MALFORMED",
                           f"{path.as_posix()} must contain a JSON object")
    if dna.get("schema") != DNA_SCHEMA:
        raise RoutingError(
            "ACCOUNT_DNA_MALFORMED",
            f"{path.as_posix()} declares schema {dna.get('schema')!r}; this router "
            f"reads {DNA_SCHEMA!r}")

    discovery = dna.get("discovery")
    if not isinstance(discovery, dict):
        raise RoutingError(
            "ACCOUNT_DNA_MISSING",
            f"{slug} has no discovery block, so it has no source allowlist and no "
            f"search terms; hotspot collection is refused until the account owner "
            f"declares them")
    if discovery.get("schema") != DISCOVERY_SCHEMA:
        raise RoutingError(
            "ACCOUNT_DNA_MALFORMED",
            f"{slug} discovery block declares schema {discovery.get('schema')!r}; "
            f"expected {DISCOVERY_SCHEMA!r}")

    positive = _keywords(discovery, "keywords_positive")
    negative = _keywords(discovery, "keywords_negative")
    if not positive:
        raise RoutingError(
            "ACCOUNT_DNA_MISSING",
            f"{slug} declares no positive keywords, so a collector would have to "
            f"search the whole web; that is exactly the undirected collection "
            f"this router refuses")

    failures: List[str] = []
    for keyword in positive + negative:
        failures.extend(verify_origin(dna, keyword))
    if failures:
        raise RoutingError(
            "ACCOUNT_DNA_MALFORMED",
            f"{slug} has keywords that no DNA field supports: " + "; ".join(failures))

    allowlist = _source_ids(discovery.get("source_allowlist"))
    blocklist = _source_ids(discovery.get("source_blocklist"))
    if not allowlist:
        raise RoutingError(
            "ACCOUNT_DNA_MISSING",
            f"{slug} declares no source allowlist, so the router would have to "
            f"contact every source it knows")

    weights = discovery.get("match_weights") or dict(DEFAULT_MATCH_WEIGHTS)
    if not isinstance(weights, dict) or sum(weights.values()) != 100:
        raise RoutingError(
            "ACCOUNT_DNA_MALFORMED",
            f"{slug} match_weights must be a percentage map summing to 100, got "
            f"{weights!r}")
    unknown = sorted(set(weights) - set(MATCH_COMPONENTS))
    if unknown:
        raise RoutingError(
            "ACCOUNT_DNA_MALFORMED",
            f"{slug} match_weights names unknown components: {unknown}")

    narrative = dna.get("narrative") or {}
    evidence = dna.get("evidence") or {}
    duration = narrative.get("target_duration_s") or []
    platforms = _video_capable(dna)

    return AccountProfile(
        account_id=str(dna.get("slug") or slug),
        slug=str(dna.get("slug") or slug),
        platform=(platforms[0] if platforms else ""),
        positioning=str(dna.get("promise") or dna.get("mission") or ""),
        decision_question=str(dna.get("decision_question") or ""),
        target_audience=_strings(dna.get("core_audience")) or _strings(dna.get("audience")),
        content_pillars=tuple(pillar for pillar in (dna.get("content_pillars") or [])
                               if isinstance(pillar, dict)),
        topics_include=_pillar_topics(dna),
        topics_exclude=_exclude_topics(dna),
        keywords_positive=positive,
        keywords_negative=negative,
        preferred_sources=tuple(entry for entry in (discovery.get("preferred_sources") or [])
                                if isinstance(entry, dict)),
        source_allowlist=allowlist,
        source_blocklist=blocklist,
        language=_strings(discovery.get("language")) or ("zh",),
        geography=_strings(discovery.get("geography")),
        content_formats=_strings(discovery.get("content_formats")),
        editorial_rules=_editorial_rules(dna),
        approval_policy=dict(discovery.get("approval_policy") or {}),
        profile_version=str(discovery.get("profile_version") or "0"),
        profile_source=str(discovery.get("profile_source") or path.as_posix()),
        evidence_mode=str(evidence.get("mode") or ""),
        manual_recording=str(evidence.get("manual_recording") or ""),
        target_duration_s=tuple(float(value) for value in duration
                                if isinstance(value, (int, float)) and not isinstance(value, bool)),
        platforms=platforms,
        match_weights={str(k): int(v) for k, v in weights.items()},
        source_reasons={entry["source_id"]: entry["why"]
                        for entry in _source_entries(discovery.get("source_allowlist"))
                        if entry["why"]},
        query_expressions=_query_expressions(discovery),
        dna=dna,
    )


def load_all_profiles(root: Path) -> Dict[str, AccountProfile]:
    """Every account whose DNA resolves. An account that does not resolve is
    absent rather than fatal, so one broken account cannot hide the others."""
    profiles: Dict[str, AccountProfile] = {}
    for slug in list_account_slugs(root):
        try:
            profile = load_profile(root, slug)
        except RoutingError:
            continue
        profiles[profile.account_id] = profile
    return profiles


def profile_video_capable(profile: AccountProfile) -> bool:
    """Whether this account has a platform the video pipeline can target."""
    return bool(profile.platforms)


def target_pipeline_for(profile: AccountProfile) -> str:
    """The pipeline this account may use.

    A text-only account is not silently pushed into the video generator: it is
    given ``TEXT_ARTICLE`` and the video route is refused for it.
    """
    return "VIDEO" if profile.platforms else "TEXT_ARTICLE"
