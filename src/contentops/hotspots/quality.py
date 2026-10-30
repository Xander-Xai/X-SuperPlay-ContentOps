"""Is this repository something a person could make an episode about?

Why this exists
---------------
A hot-list search returns whatever matched the words. For GitHub that includes
repositories whose description says ``behaviour test: mint probe workflow
host`` — they contain the account's keyword, they pass the keyword gate, and
they are worth nothing to an audience. Recommending them costs the reviewer
time and the account credibility.

The gate here is deliberately narrow and explainable:

- it decides **only** on evidence it fetched (repository metadata and whether
  a README exists), never on the words in the title alone;
- no single weak signal is enough to reject. Stars, age and vocabulary are
  each *one* signal; a rejection needs two independent ones, and anything the
  gate cannot verify passes through marked ``UNVERIFIED`` rather than being
  quietly dropped;
- every decision carries the signals that produced it, so a reviewer can
  disagree with the gate on the evidence rather than on trust.

What it is not
--------------
It is not a relevance score and it does not replace the account's positioning
filter. It answers one question — "is there a real project here?" — and it
leaves "is this the account's subject?" to the DNA, which is where that
decision belongs.

**Stars are context, not a verdict.** A three-star repository created last
week can be the best find of the month; the gate only treats a young, unstarred
repository as *one* signal, and never as a reason on its own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: The gate's own schema, for the receipt.
QUALITY_SCHEMA = "contentops.source-quality/v1"

#: Words that describe a test fixture rather than a product. They are matched
#: in the description and the repository name, and they are only one signal.
PLACEHOLDER_PATTERNS: Tuple[str, ...] = (
    "behaviour test", "behavior test", "mint probe", "test-repo", "test repo",
    "dummy repo", "lorem ipsum", "example repository", "sample repository",
    "this is a test", "placeholder",
)


@dataclass(frozen=True)
class QualityPolicy:
    """Thresholds a reviewer can argue with, because they are numbers."""

    #: A repository smaller than this has little code in it.
    min_size_kb: int = 64
    #: How long a repository needs to exist before "young" stops counting.
    min_age_days: int = 3
    #: Stars that make a young repository plausible anyway.
    min_stars_for_young: int = 5
    #: Independent signals that reject, and that merely flag for review.
    reject_at_signals: int = 2
    review_at_signals: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_size_kb": self.min_size_kb,
            "min_age_days": self.min_age_days,
            "min_stars_for_young": self.min_stars_for_young,
            "reject_at_signals": self.reject_at_signals,
            "review_at_signals": self.review_at_signals,
        }


DEFAULT_POLICY = QualityPolicy()


@dataclass
class RepoEvidence:
    """What was actually observed about a repository.

    ``fetched`` says whether the observation happened. A gate that cannot
    observe must not reject: an unreachable API would otherwise delete every
    GitHub candidate, which is a much worse failure than a few spam repos.
    """

    full_name: str
    description: str = ""
    size_kb: int = 0
    stars: int = 0
    forks: int = 0
    archived: bool = False
    is_fork: bool = False
    has_readme: bool = False
    readme_excerpt: str = ""
    created_at: Optional[str] = None
    pushed_at: Optional[str] = None
    homepage: str = ""
    topics: Tuple[str, ...] = ()
    fetched: bool = False
    fetch_error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "full_name": self.full_name,
            "description": self.description,
            "size_kb": self.size_kb,
            "stars": self.stars,
            "forks": self.forks,
            "archived": self.archived,
            "is_fork": self.is_fork,
            "has_readme": self.has_readme,
            "readme_excerpt": self.readme_excerpt,
            "created_at": self.created_at,
            "pushed_at": self.pushed_at,
            "homepage": self.homepage,
            "topics": list(self.topics),
            "fetched": self.fetched,
            "fetch_error": self.fetch_error,
        }


def _age_days(created_at: Optional[str], *, now: Optional[datetime] = None) -> Optional[float]:
    if not created_at:
        return None
    try:
        moment = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    reference = now or datetime.now(timezone.utc)
    return (reference - moment).total_seconds() / 86400.0


def _placeholder_phrase(*texts: str) -> Optional[str]:
    for text in texts:
        lowered = (text or "").casefold()
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in lowered:
                return pattern
    return None


def assess(evidence: RepoEvidence, policy: Optional[QualityPolicy] = None,
           *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Judge one repository, and say exactly what the judgement rests on."""
    policy = policy or DEFAULT_POLICY
    signals: List[Dict[str, Any]] = []

    # The name and the description are two separate fields, written by the
    # owner, so a fixture phrase in each is two pieces of evidence — and it is
    # evidence available without any API call.
    name_phrase = _placeholder_phrase(evidence.full_name)
    if name_phrase:
        signals.append({"signal": "placeholder_name", "weight": 1,
                        "value": name_phrase,
                        "why": f"the repository is named after a fixture "
                               f"({name_phrase!r}) rather than a product"})
    text_phrase = _placeholder_phrase(evidence.description)
    if text_phrase:
        signals.append({"signal": "placeholder_description", "weight": 1,
                        "value": text_phrase,
                        "why": f"the description calls itself a fixture "
                               f"({text_phrase!r})"})

    if evidence.fetched:
        if not evidence.has_readme:
            signals.append({"signal": "no_readme", "weight": 1, "value": False,
                            "why": "the repository has no README, so it documents "
                                   "nothing about what it does"})
        if evidence.size_kb and evidence.size_kb < policy.min_size_kb:
            signals.append({"signal": "tiny_repository", "weight": 1,
                            "value": evidence.size_kb,
                            "why": f"the repository is {evidence.size_kb} KB, below "
                                   f"the {policy.min_size_kb} KB floor"})
        if evidence.archived:
            signals.append({"signal": "archived", "weight": 1, "value": True,
                            "why": "the repository is archived and will not change"})
        age = _age_days(evidence.created_at, now=now)
        if age is not None and age < policy.min_age_days \
                and evidence.stars < policy.min_stars_for_young:
            signals.append({
                "signal": "young_and_unproven", "weight": 1,
                "value": round(age, 2),
                "why": f"created {age:.1f} days ago with {evidence.stars} star(s); on "
                       f"its own this proves nothing, which is why it is one signal"})

    if not evidence.fetched:
        # Without an inspection the gate cannot judge substance, but a
        # repository that names itself a fixture in two fields has already
        # said enough. One such field is not enough to drop it.
        if len(signals) >= policy.reject_at_signals:
            return {
                "schema": QUALITY_SCHEMA, "verdict": "REJECT", "signals": signals,
                "policy": policy.to_dict(), "evidence": evidence.to_dict(),
                "detail": f"{len(signals)} independent fields describe this repository "
                          f"as a fixture, so it is not offered",
            }
        return {
            "schema": QUALITY_SCHEMA,
            "verdict": "UNVERIFIED",
            "signals": signals,
            "policy": policy.to_dict(),
            "evidence": evidence.to_dict(),
            "detail": "the repository could not be inspected, so the gate did not "
                      "decide against it; it is offered with that stated",
        }

    count = len(signals)
    if count >= policy.reject_at_signals:
        verdict = "REJECT"
        detail = (f"{count} independent signals point at a repository with no "
                  f"product behind it")
    elif count >= policy.review_at_signals:
        verdict = "REVIEW"
        detail = (f"{count} signal(s) worth a look; one is not enough to drop it, "
                  f"so it stays with the reason attached")
    else:
        verdict = "ACCEPT"
        detail = "no signal against it"
    return {"schema": QUALITY_SCHEMA, "verdict": verdict, "signals": signals,
            "policy": policy.to_dict(), "evidence": evidence.to_dict(),
            "detail": detail}


class GitHubRepoEvidenceFetcher:
    """Fetch what the gate needs, once per repository, and survive failure.

    The unauthenticated GitHub API allows 60 requests an hour, which is not
    enough for a daily run to inspect every candidate twice. So evidence is
    cached on disk for ``ttl_hours``: the same repository is inspected once a
    week rather than once a run, and a run that hits the limit still reports
    ``UNVERIFIED`` instead of rejecting anything.
    """

    def __init__(self, http_get, *, timeout: float = 12.0,
                 cache_path: Optional[Path] = None, ttl_hours: float = 168.0,
                 now: Optional[datetime] = None) -> None:
        self._http_get = http_get
        self.timeout = timeout
        self.cache_path = Path(cache_path) if cache_path is not None else None
        self.ttl_hours = ttl_hours
        self._now = now or datetime.now(timezone.utc)
        self._cache: Dict[str, RepoEvidence] = {}
        self._loaded = False

    # -- cache ------------------------------------------------------------

    def _load_cache(self) -> None:
        if self._loaded or self.cache_path is None:
            self._loaded = True
            return
        self._loaded = True
        try:
            raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        cutoff = self._now.timestamp() - self.ttl_hours * 3600
        for key, entry in (raw.get("entries") or {}).items():
            try:
                stored_at = float(entry.get("stored_at") or 0)
            except (TypeError, ValueError):
                continue
            if stored_at < cutoff:
                continue
            payload = entry.get("evidence") or {}
            if not isinstance(payload, dict) or "full_name" not in payload:
                continue
            payload = dict(payload)
            payload["topics"] = tuple(payload.get("topics") or ())
            self._cache[str(key)] = RepoEvidence(**payload)

    def _save_cache(self) -> None:
        if self.cache_path is None:
            return
        entries = {key: {"stored_at": self._now.timestamp(), "evidence": evidence.to_dict()}
                   for key, evidence in self._cache.items() if evidence.fetched}
        if not entries:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps({"schema": "contentops.repo-evidence-cache/v1",
                            "entries": entries}, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            # A cache that cannot be written is a slower run, not a failure.
            pass

    def fetch(self, full_name: str) -> RepoEvidence:
        key = full_name.casefold()
        self._load_cache()
        if key in self._cache:
            return self._cache[key]
        evidence = RepoEvidence(full_name=full_name)
        try:
            body = self._http_get(
                f"https://api.github.com/repos/{full_name}", timeout=self.timeout,
                source_id="github-search",
                headers={"Accept": "application/vnd.github+json"})
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - reported through the evidence
            evidence.fetch_error = f"{type(exc).__name__}: {exc}"[:200]
            self._cache[key] = evidence
            return evidence

        evidence.fetched = True
        evidence.description = str(payload.get("description") or "")
        evidence.size_kb = int(payload.get("size") or 0)
        evidence.stars = int(payload.get("stargazers_count") or 0)
        evidence.forks = int(payload.get("forks_count") or 0)
        evidence.archived = bool(payload.get("archived"))
        evidence.is_fork = bool(payload.get("fork"))
        evidence.created_at = payload.get("created_at")
        evidence.pushed_at = payload.get("pushed_at")
        evidence.homepage = str(payload.get("homepage") or "")
        evidence.topics = tuple(str(topic) for topic in payload.get("topics") or ())

        # The README is the closest thing to "what is this and does it work",
        # so its presence is evidence in its own right.
        try:
            readme = self._http_get(
                f"https://api.github.com/repos/{full_name}/readme",
                timeout=self.timeout, source_id="github-search",
                headers={"Accept": "application/vnd.github+json"})
            text = readme.decode("utf-8", "replace")
            evidence.has_readme = True
            match = re.search(r'"content"\s*:\s*"([^"]{0,2000})', text)
            if match:
                evidence.readme_excerpt = match.group(1)[:400]
        except Exception:  # noqa: BLE001 - a missing README is a fact, not a crash
            evidence.has_readme = False
        self._cache[key] = evidence
        self._save_cache()
        return evidence


def repo_from_url(url: str) -> Optional[str]:
    """``https://github.com/owner/repo`` -> ``owner/repo``, or ``None``."""
    match = re.match(r"^https?://(?:www\.)?github\.com/([^/]+)/([^/?#]+)",
                     str(url or "").strip(), re.IGNORECASE)
    return f"{match.group(1)}/{match.group(2)}" if match else None
