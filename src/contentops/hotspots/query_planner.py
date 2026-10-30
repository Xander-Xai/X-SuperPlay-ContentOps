"""Turn an account profile into a search plan, before anything is fetched.

Why this exists
---------------
The order of operations is the whole point. A collector that fetches first and
filters afterwards has already paid for the wrong thing, and it cannot honestly
say it searched for the account: it read a popular list. So the plan is built
and written down *first*, and the collection refuses to run without one.

The plan is also the record of what the account's positioning actually did.
Every source in it carries a reason; every query carries the terms that
produced it; and each source states whether it accepts a query or only
publishes a list. A reader of the plan can check the reasoning without
reading the code.

The estimated cost is real
--------------------------
Every source in this catalog is free to read and needs no credential, so the
estimated cost is zero. It is still stated, because a plan that omits the
cost line reads as "we did not think about it", and because the next source
added may not be free.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..canonical import digest, utcnow
from .source_registry import (
    LIST_ONLY,
    NATIVE_SEARCH,
    Source,
    preferred_reason,
    query_mode_note,
    resolve_sources,
)

#: The plan's own schema. It lives here, next to the plan it describes, and
#: not in the routing layer: a plan is built before any route exists.
SEARCH_PLAN_SCHEMA = "contentops.search-plan/v1"

#: The default freshness window, in hours. Two days is long enough that a
#: quiet topic still qualifies and short enough that "hot" means something.
DEFAULT_FRESHNESS_HOURS = 72

#: How many items a source may contribute in one run, before the account's
#: own limit applies.
DEFAULT_PER_SOURCE_LIMIT = 30

#: How many terms a native-search query may carry, and how long it may be.
#: A search service rejects an over-long query, and a query that carries
#: every term asks for too much to be useful.
MAX_QUERY_TERMS = 12
MAX_QUERY_CHARS = 220


def build_search_plan(profile: Any, *,
                      pillar: Optional[str] = None,
                      freshness_hours: int = DEFAULT_FRESHNESS_HOURS,
                      per_source_limit: int = DEFAULT_PER_SOURCE_LIMIT,
                      limit_override: Optional[Dict[str, int]] = None,
                      created_at: Optional[str] = None) -> Dict[str, Any]:
    """Build the search plan for one account, and for one pillar if named.

    The plan is a plain document so it can be written to disk, hashed and
    compared. Nothing here touches the network.
    """
    selected, rejected = resolve_sources(profile)
    limit_override = limit_override or {}

    terms_zh = [keyword.term for keyword in profile.keywords_positive
                if keyword.language == "zh"]
    terms_en = [keyword.term for keyword in profile.keywords_positive
                if keyword.language == "en"]
    exclude_terms = [keyword.term for keyword in profile.keywords_negative]

    pillars = [dict(entry) for entry in profile.content_pillars]
    if pillar:
        pillars = [entry for entry in pillars if entry.get("name") == pillar]
        if not pillars:
            raise ValueError(f"account {profile.account_id!r} has no pillar {pillar!r}")

    sources: List[Dict[str, Any]] = []
    requests = 0
    for source in selected:
        limit = int(limit_override.get(source.source_id, per_source_limit))
        limit = max(1, min(limit, source.max_items))
        entry: Dict[str, Any] = {
            "source_id": source.source_id,
            "name": source.name,
            "platform": source.platform,
            "language": list(source.language),
            "query_mode": source.query_mode,
            "query": _query_for(source, profile, pillar, terms_zh, terms_en),
            "max_items": limit,
            "why": (profile.source_reasons.get(source.source_id)
                    or preferred_reason(profile, source.source_id)
                    or source.note),
            "capability_note": query_mode_note(source),
            "freshness_hours": freshness_hours,
        }
        sources.append(entry)
        requests += 1

    document: Dict[str, Any] = {
        "schema": SEARCH_PLAN_SCHEMA,
        "account_id": profile.account_id,
        "account_profile_version": profile.profile_version,
        "profile_source": profile.profile_source,
        "positioning": profile.positioning,
        "decision_question": profile.decision_question,
        "target_audience": list(profile.target_audience),
        "pillars": pillars,
        "selected_pillar": pillar,
        "topics_include": list(profile.topics_include),
        "topics_exclude": list(profile.topics_exclude),
        "keywords_zh": terms_zh,
        "keywords_en": terms_en,
        "keywords_positive": [keyword.to_dict() for keyword in profile.keywords_positive],
        "exclude_terms": exclude_terms,
        "source_allowlist": list(profile.source_allowlist),
        "source_blocklist": list(profile.source_blocklist),
        "sources": sources,
        "rejected_sources": rejected,
        "time_window": {
            "freshness_hours": freshness_hours,
            "created_at": created_at or utcnow(),
        },
        "estimated_cost": {
            "currency": "USD",
            "amount": 0.0,
            "requests_planned": requests,
            "basis": "every source in this catalog is free to read and needs no "
                     "credential; the amount is zero because nothing is billed, "
                     "not because the cost was ignored",
        },
        "match_weights": dict(profile.match_weights),
        "created_at": created_at or utcnow(),
    }
    document["plan_id"] = "PLAN-" + digest(document)[:16].upper()
    document["summary"] = _summarise(document)
    return document


def _query_for(source: Source, profile: Any, pillar: Optional[str],
               terms_zh: List[str], terms_en: List[str]) -> Optional[str]:
    """The query string for a source, or ``None`` when it takes no query.

    Only a native-search source gets one. A list-only source is fetched as it
    is and filtered locally; giving it a query string would suggest a
    narrowing that the service does not perform.
    """
    if source.query_mode != NATIVE_SEARCH:
        return None
    # An account may state, per adapter, which of its declared terms are worth
    # asking a particular source about. That is a query decision, not a
    # positioning change: every term in the expression still names a keyword
    # the account declared, and the DNA check verifies the chain.
    expression = (getattr(profile, "query_expressions", None) or {}).get(source.adapter)
    if expression:
        terms = [str(term) for term in expression]
    elif source.adapter == "github_search":
        # GitHub's search ANDs space-separated terms, so asking for every one
        # of the account's terms at once would ask for a repository that
        # mentions all of them and find nothing. The account's terms are
        # alternatives — a repository about any one of them is worth looking
        # at — so they are OR'd, and the query is capped so the service
        # accepts it. The exact query is recorded in the plan, so a reader can
        # see what was actually asked.
        terms = list(dict.fromkeys(terms_en + terms_zh))
    else:
        return None
    if not terms:
        return None
    # A term that is the source's own name discriminates nothing here: on
    # GitHub, "GitHub" matches every repository, and asking for it spends one
    # of the few operators the service allows on a term that cannot narrow
    # anything. It stays in the account's keywords — it is still used for
    # filtering and ranking — it just does not lead the query.
    platform = str(getattr(source, "platform", "") or "").casefold()
    discriminating = [term for term in terms
                      if term.casefold() != platform and platform not in term.casefold()]
    terms = discriminating or terms
    # A stated expression carries the account's own order; the keyword-derived
    # fallback is re-ordered so a capped query keeps the specific terms.
    ordered = list(terms) if expression else _pillar_first(profile, pillar, terms)
    cap = source.max_query_terms or MAX_QUERY_TERMS
    chosen: List[str] = []
    for term in ordered:
        trial = chosen + [term]
        if len(" OR ".join(trial)) > MAX_QUERY_CHARS:
            break
        chosen = trial
        if len(chosen) >= cap:
            break
    return " OR ".join(chosen) if chosen else None


def _pillar_first(profile: Any, pillar: Optional[str], terms: List[str]) -> List[str]:
    """The most specific terms first, so a capped query keeps them.

    A pillar's scope is the account's own vocabulary for that content line, so
    a term drawn from it is the most specific thing the account can ask for.
    When the run is restricted to one pillar, that pillar leads; otherwise
    every pillar's scope does, and the order decides which alternatives
    survive the source's term cap.
    """
    entries = [entry for entry in (getattr(profile, "content_pillars", ()) or ())
               if isinstance(entry, dict)]
    if pillar:
        entries = [entry for entry in entries if entry.get("name") == pillar]
        if not entries:
            return list(terms)
    tokens: List[str] = []
    for entry in entries:
        scope = str(entry.get("scope") or "").replace("/", " ")
        tokens.extend(token.strip() for token in scope.split() if token.strip())
    if not tokens:
        return list(terms)
    lead = [term for term in terms
            if any(token.casefold() in term.casefold() or
                   term.casefold() in token.casefold() for token in tokens)]
    rest = [term for term in terms if term not in lead]
    return lead + rest


def _summarise(document: Dict[str, Any]) -> str:
    """A sentence a person can read to see what the plan will do."""
    sources = document.get("sources") or []
    native = [entry["source_id"] for entry in sources
              if entry.get("query_mode") == NATIVE_SEARCH]
    listed = [entry["source_id"] for entry in sources
              if entry.get("query_mode") == LIST_ONLY]
    pillar = document.get("selected_pillar")
    scope = f"pillar {pillar}" if pillar else "all pillars"
    parts = [
        f"{len(sources)} source(s) for {document.get('account_id')} "
        f"({scope}): {', '.join(entry['source_id'] for entry in sources) or 'none'}",
    ]
    if native:
        parts.append(f"server-side query on {', '.join(native)}")
    if listed:
        parts.append(f"locally filtered list on {', '.join(listed)}")
    parts.append(f"exclude terms: {', '.join(document.get('exclude_terms') or []) or 'none'}")
    parts.append(f"freshness window: {document.get('time_window', {}).get('freshness_hours')} h")
    return "; ".join(parts)


def plan_is_current(plan: Dict[str, Any], profile: Any) -> Tuple[bool, str]:
    """Whether a stored plan still describes the account it was built for.

    The account's profile version is the check. A profile edit produces a new
    version, and a plan built against the old one is stale — but the stale plan
    is kept, because a run that used it must remain able to show what it
    actually searched for.
    """
    if plan.get("account_id") != profile.account_id:
        return False, f"plan belongs to account {plan.get('account_id')!r}"
    if str(plan.get("account_profile_version")) != str(profile.profile_version):
        return False, (f"plan was built against profile version "
                       f"{plan.get('account_profile_version')!r} and the account is "
                       f"now {profile.profile_version!r}")
    return True, ""
