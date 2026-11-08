"""External B-roll discovery for the M5 chain, deliberately narrow in scope.

This module adds the missing ``search -> rank -> preview -> authorize ->
download -> register -> reuse`` layer for Pexels and Pixabay. It is NOT a new
asset registry: registered rows go into the existing ``sources/assets.json``
manifest and are checked by the existing :mod:`contentops.media.rights_gate`.

Hard boundaries:

* Stock material is illustrative B-roll only. It can never become factual
  evidence, and its allowed visual roles are ``context`` / ``transition``.
* No network request happens without an explicit, per-call
  :class:`StockAuthorization`. Missing credentials are a normal, non-fatal
  state so the local-only pipeline still completes.
* Downloaded bytes are never marked rights-reviewed. The rights review record
  is emitted with an empty reviewer and ``PENDING_HUMAN_REVIEW``; the real
  Rights Gate then refuses it. That refusal is the correct outcome, not a
  failure to be worked around.
* Every provider interaction goes through an injectable transport, so parsing,
  ranking, caching, 429 handling and refusal paths are fully testable offline.

Inspired by MoneyPrinterTurbo's search/cache shape; no MoviePy chain, no
systematic scraping, no unbounded downloads.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from contentops.media.rights_gate import (
    RightsError,
    license_policy,
    validate_declared_asset,
)

SCHEMA = "contentops.stock-media/v1"
RIGHTS_REVIEW_SCHEMA = "contentops.media-rights-review/v1"
MANIFEST_SCHEMA = "contentops.m5-assets/v1"

CACHE_TTL_S = 24 * 60 * 60
CACHE_SUBDIR = Path(".verify-tmp") / "stock-media-cache"
MAX_CANDIDATES_PER_SEARCH = 30
MAX_PER_PAGE = 15
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
MAX_VIDEO_DURATION_S = 60.0
REQUEST_TIMEOUT_S = 20.0

STATE_READY = "READY"
STATE_NEEDS_ASSET = "NEEDS_ASSET"
STATE_NO_CREDENTIALS = "NO_CREDENTIALS"
STATE_NOT_AUTHORIZED = "NETWORK_NOT_AUTHORIZED"
STATE_RATE_LIMITED = "RATE_LIMITED"
STATE_PROVIDER_ERROR = "PROVIDER_ERROR"

BROLL_ROLES = ("context", "transition")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
VIDEO_SUFFIXES = (".mp4", ".mov", ".webm")

PROVIDERS: Dict[str, Dict[str, str]] = {
    "pexels_photos": {
        "url": "https://api.pexels.com/v1/search",
        "env": "PEXELS_API_KEY",
        "license": "Pexels-License",
        "kind": "image",
        "auth": "header",
    },
    "pexels_videos": {
        "url": "https://api.pexels.com/v1/videos/search",
        "env": "PEXELS_API_KEY",
        "license": "Pexels-License",
        "kind": "video",
        "auth": "header",
    },
    "pixabay_photos": {
        "url": "https://pixabay.com/api/",
        "env": "PIXABAY_API_KEY",
        "license": "Pixabay-Content-License",
        "kind": "image",
        "auth": "query",
    },
    "pixabay_videos": {
        "url": "https://pixabay.com/api/videos/",
        "env": "PIXABAY_API_KEY",
        "license": "Pixabay-Content-License",
        "kind": "video",
        "auth": "query",
    },
}

API_HOSTS = ("api.pexels.com", "pixabay.com")
DOWNLOAD_HOSTS = (
    "images.pexels.com", "videos.pexels.com", "www.pexels.com",
    "cdn.pixabay.com", "pixabay.com",
)

# Magic bytes for the formats we accept. A renamed .exe must not be importable.
_MAGIC = {
    "image": (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"RIFF"),
    "video": (b"\x00\x00\x00\x18ftyp", b"\x00\x00\x00\x20ftyp", b"\x00\x00\x00\x1cftyp"),
}


class StockMediaError(ValueError):
    """A stock-media request cannot be satisfied safely."""


@dataclass(frozen=True)
class StockQuery:
    keyword: str
    kind: str = "image"                 # "image" | "video"
    orientation: str = "portrait"      # "portrait" | "landscape" | "square" | "any"
    min_duration_s: float = 0.0
    max_duration_s: float = MAX_VIDEO_DURATION_S
    min_width: int = 720
    min_height: int = 1280
    page: int = 1
    per_page: int = 10
    providers: Tuple[str, ...] = ()

    def cache_key(self) -> str:
        body = json.dumps(self.as_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword.strip(), "kind": self.kind,
            "orientation": self.orientation,
            "min_duration_s": self.min_duration_s,
            "max_duration_s": self.max_duration_s,
            "min_width": self.min_width, "min_height": self.min_height,
            "page": self.page, "per_page": self.per_page,
            "providers": list(self.providers),
        }

    def active_providers(self) -> List[str]:
        if self.providers:
            unknown = [p for p in self.providers if p not in PROVIDERS]
            if unknown:
                raise StockMediaError(f"unknown stock providers: {unknown}")
            return [p for p in self.providers if PROVIDERS[p]["kind"] == self.kind]
        return [name for name, spec in PROVIDERS.items() if spec["kind"] == self.kind]


@dataclass(frozen=True)
class StockAuthorization:
    """A separate, explicit grant for a single network operation.

    ``search_only`` never permits a download. There is no ambient or implicit
    authorization: a caller must construct this with a real grantor identity.
    """

    granted_by: str
    granted_at: str
    scope: str = "search_only"          # "search_only" | "search_and_download"
    max_downloads: int = 1

    def valid(self) -> bool:
        return bool(self.granted_by.strip()) and bool(self.granted_at.strip())

    def allows_download(self) -> bool:
        return self.valid() and self.scope == "search_and_download" and self.max_downloads > 0


@dataclass
class Candidate:
    provider: str
    kind: str
    provider_id: str
    download_url: str
    page_url: str
    author: str
    license_id: str
    width: int = 0
    height: int = 0
    duration_s: float = 0.0
    description: str = ""
    preview_url: str = ""
    accepted: bool = False
    score: float = 0.0
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        row = {
            "provider": self.provider, "kind": self.kind,
            "provider_id": self.provider_id, "download_url": self.download_url,
            "page_url": self.page_url, "author": self.author,
            "license_id": self.license_id, "width": self.width,
            "height": self.height, "duration_s": round(self.duration_s, 3),
            "description": self.description, "preview_url": self.preview_url,
            "visual_role_allowlist": list(BROLL_ROLES),
            "evidence_capable": False,
        }
        return row


@dataclass
class SearchResult:
    state: str
    candidates: List[Candidate] = field(default_factory=list)
    requests: int = 0
    cache_hits: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    retry_after_s: Optional[int] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": SCHEMA, "state": self.state,
            "candidates": [c.as_dict() | {"accepted": c.accepted,
                                          "score": round(c.score, 3),
                                          "reasons": c.reasons}
                           for c in self.candidates],
            "requests": self.requests, "cache_hits": self.cache_hits,
            "errors": self.errors, "retry_after_s": self.retry_after_s,
        }


# ---------------------------------------------------------------------------
# Response parsing (pure, offline-testable)
# ---------------------------------------------------------------------------

def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _licensed(provider: str) -> str:
    return PROVIDERS[provider]["license"]


def parse_response(provider: str, payload: Mapping[str, Any]) -> List[Candidate]:
    """Turn one provider JSON response into normalised candidates.

    Malformed items are skipped with a reason rather than crashing the search;
    a provider changing its schema must not take the local pipeline down.
    """
    if provider not in PROVIDERS:
        raise StockMediaError(f"unknown stock provider {provider!r}; refusing to parse")
    out: List[Candidate] = []
    license_id = _licensed(provider)
    if provider == "pexels_photos":
        for item in payload.get("photos") or []:
            if not isinstance(item, Mapping):
                continue
            src = item.get("src") or {}
            url = src.get("original") or src.get("large") or ""
            if not url:
                continue
            out.append(Candidate(
                provider=provider, kind="image", provider_id=str(item.get("id") or ""),
                download_url=str(url), page_url=str(item.get("url") or ""),
                author=str(item.get("photographer") or ""), license_id=license_id,
                width=_int(item.get("width")), height=_int(item.get("height")),
                description=str(item.get("alt") or ""),
                preview_url=str(src.get("portrait") or src.get("medium") or ""),
            ))
    elif provider == "pexels_videos":
        for item in payload.get("videos") or []:
            if not isinstance(item, Mapping):
                continue
            files = [f for f in (item.get("video_files") or [])
                     if isinstance(f, Mapping) and str(f.get("file_type") or "").startswith("video/")]
            chosen = next((f for f in files if f.get("width") and f.get("height")),
                          files[0] if files else None)
            if not chosen or not chosen.get("link"):
                continue
            user = item.get("user") or {}
            out.append(Candidate(
                provider=provider, kind="video", provider_id=str(item.get("id") or ""),
                download_url=str(chosen["link"]), page_url=str(item.get("url") or ""),
                author=str(user.get("name") or "") if isinstance(user, Mapping) else "",
                license_id=license_id, width=_int(chosen.get("width")),
                height=_int(chosen.get("height")), duration_s=_float(item.get("duration")),
                description=str(item.get("title") or ""),
                preview_url=str(item.get("image") or ""),
            ))
    elif provider == "pixabay_photos":
        for item in payload.get("hits") or []:
            if not isinstance(item, Mapping):
                continue
            url = item.get("largeImageURL") or item.get("webformatURL") or ""
            if not url:
                continue
            out.append(Candidate(
                provider=provider, kind="image", provider_id=str(item.get("id") or ""),
                download_url=str(url), page_url=str(item.get("pageURL") or ""),
                author=str(item.get("user") or ""), license_id=license_id,
                width=_int(item.get("imageWidth")), height=_int(item.get("imageHeight")),
                description=str(item.get("tags") or ""),
                preview_url=str(item.get("previewURL") or ""),
            ))
    elif provider == "pixabay_videos":
        for item in payload.get("hits") or []:
            if not isinstance(item, Mapping):
                continue
            videos = item.get("videos") or {}
            chosen = (videos.get("large") or videos.get("medium")
                      or videos.get("small")) if isinstance(videos, Mapping) else None
            if not isinstance(chosen, Mapping) or not chosen.get("url"):
                continue
            out.append(Candidate(
                provider=provider, kind="video", provider_id=str(item.get("id") or ""),
                download_url=str(chosen["url"]), page_url=str(item.get("pageURL") or ""),
                author=str(item.get("user") or ""), license_id=license_id,
                width=_int(chosen.get("width")), height=_int(chosen.get("height")),
                duration_s=_float(item.get("duration")),
                description=str(item.get("tags") or ""),
                preview_url=str(item.get("picture_id") or ""),
            ))
    return out[:MAX_CANDIDATES_PER_SEARCH]


def rank_candidates(candidates: Sequence[Candidate], query: StockQuery) -> List[Candidate]:
    """Score and accept/reject candidates using declared, explainable criteria.

    Every candidate keeps its reasons, so a rejected item is auditable rather
    than silently disappearing. Nothing here upgrades stock material to proof.
    """
    tokens = [t for t in re.split(r"[^\w]+", query.keyword.lower()) if t]
    ranked: List[Candidate] = []
    for cand in candidates:
        c = Candidate(**{k: v for k, v in cand.__dict__.items()})
        text = f"{c.description} {c.provider}".lower()
        overlap = sum(1 for t in tokens if t in text)
        c.score = float(overlap) * 2.0
        c.reasons = []

        if not c.download_url.startswith("https://"):
            c.reasons.append("reject: download URL is not https")
            ranked.append(c)
            continue
        try:
            host = urllib.parse.urlsplit(c.download_url).hostname or ""
        except ValueError:
            host = ""
        if not any(host == h or host.endswith("." + h) for h in DOWNLOAD_HOSTS):
            c.reasons.append(f"reject: download host {host!r} is not an approved CDN")
            ranked.append(c)
            continue
        try:
            license_policy(c.license_id)
        except RightsError as exc:
            c.reasons.append(f"reject: {exc}")
            ranked.append(c)
            continue

        if tokens:
            c.reasons.append(f"keyword overlap {overlap}/{len(tokens)}")
        if c.kind == "video":
            if c.duration_s and not (query.min_duration_s <= c.duration_s <= query.max_duration_s):
                c.reasons.append(
                    f"reject: duration {c.duration_s}s outside "
                    f"[{query.min_duration_s}, {query.max_duration_s}]s")
                ranked.append(c)
                continue
            if not c.duration_s:
                c.reasons.append("reject: video has no measurable duration")
                ranked.append(c)
                continue
            c.score += 1.0
        if c.width and c.height:
            ratio = c.width / c.height
            wanted = {"portrait": (0.45, 0.75), "landscape": (1.3, 2.2),
                      "square": (0.85, 1.2)}.get(query.orientation)
            if wanted and not (wanted[0] <= ratio <= wanted[1]):
                c.reasons.append(f"reject: aspect ratio {ratio:.2f} does not fit {query.orientation}")
                ranked.append(c)
                continue
            if query.orientation == "portrait" and (c.height < query.min_height or c.width < query.min_width):
                c.reasons.append(f"reject: resolution {c.width}x{c.height} below "
                                 f"{query.min_width}x{query.min_height}")
                ranked.append(c)
                continue
            c.score += min(2.0, (c.width * c.height) / (1280 * 720))
        else:
            c.reasons.append("reject: missing resolution metadata")
            ranked.append(c)
            continue

        c.accepted = True
        c.reasons.append("accept: illustrative B-roll only; evidence_capable=false")
        ranked.append(c)
    ranked.sort(key=lambda c: (-c.score, c.provider, c.provider_id))
    return ranked


# ---------------------------------------------------------------------------
# Search cache (>= 24h) and transport
# ---------------------------------------------------------------------------

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def default_transport(request: urllib.request.Request,
                      timeout: float = REQUEST_TIMEOUT_S) -> Tuple[int, Mapping[str, str], bytes]:
    """Single-request transport. Redirects are refused, never followed blindly."""
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            return (int(response.status), dict(response.headers.items()),
                    response.read(MAX_DOWNLOAD_BYTES + 1))
    except urllib.error.HTTPError as exc:
        return int(exc.code), dict(exc.headers.items()), exc.read(MAX_DOWNLOAD_BYTES + 1)


Transport = Callable[[urllib.request.Request], Tuple[int, Mapping[str, str], bytes]]


class SearchCache:
    """Filesystem cache of raw search responses, valid for at least 24 hours."""

    def __init__(self, root: Path, *, clock: Callable[[], datetime] | None = None,
                 ttl_s: int = CACHE_TTL_S):
        self.root = Path(root)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.ttl_s = ttl_s

    def path_for(self, provider: str, query: StockQuery) -> Path:
        digest = hashlib.sha256(f"{provider}:{query.cache_key()}".encode()).hexdigest()[:24]
        return self.root / f"{digest}.json"

    def get(self, provider: str, query: StockQuery) -> Optional[Mapping[str, Any]]:
        path = self.path_for(provider, query)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            fetched = datetime.fromisoformat(payload["fetched_at"])
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            age = (self.clock() - fetched).total_seconds()
            if age < 0 or age > self.ttl_s:
                return None
            return payload.get("response")
        except (OSError, ValueError, KeyError):
            return None

    def put(self, provider: str, query: StockQuery, response: Mapping[str, Any]) -> None:
        path = self.path_for(provider, query)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "schema": SCHEMA, "provider": provider, "query": query.as_dict(),
            "fetched_at": self.clock().isoformat(), "ttl_s": self.ttl_s,
            "response": response,
        }, ensure_ascii=False), encoding="utf-8")


def _request_for(provider: str, query: StockQuery, key: str) -> urllib.request.Request:
    spec = PROVIDERS[provider]
    params: Dict[str, str] = {"query" if provider.startswith("pexels") else "q": query.keyword,
                              "page": str(max(1, query.page)),
                              "per_page": str(max(1, min(query.per_page, MAX_PER_PAGE)))}
    if provider.startswith("pexels"):
        if query.orientation != "any":
            params["orientation"] = query.orientation
        if provider == "pexels_videos":
            if query.min_duration_s:
                params["min_duration"] = str(int(query.min_duration_s))
            if query.max_duration_s < MAX_VIDEO_DURATION_S:
                params["max_duration"] = str(int(query.max_duration_s))
    else:
        params["key"] = key
        if query.orientation != "any":
            params["orientation"] = query.orientation
    url = f"{spec['url']}?{urllib.parse.urlencode(params)}"
    headers = {"Accept": "application/json", "User-Agent": "X-SuperPlay-ContentOps/1.0"}
    if spec["auth"] == "header":
        headers["Authorization"] = key
    return urllib.request.Request(url, headers=headers, method="GET")


def _header(headers: Mapping[str, str], name: str) -> str:
    lowered = name.lower()
    for key, value in headers.items():
        if str(key).lower() == lowered:
            return str(value)
    return ""


def search(query: StockQuery, *, authorization: Optional[StockAuthorization],
           cache_root: Path, transport: Optional[Transport] = None,
           env: Optional[Mapping[str, str]] = None,
           clock: Optional[Callable[[], datetime]] = None) -> SearchResult:
    """Search, rank and preview. Never downloads, never spends without a grant."""
    if not query.keyword.strip():
        raise StockMediaError("a non-empty search keyword is required")
    if authorization is None or not authorization.valid():
        return SearchResult(state=STATE_NOT_AUTHORIZED,
                            errors=[{"reason": "an explicit StockAuthorization is required"}])
    environ = env if env is not None else os.environ
    cache = SearchCache(cache_root, clock=clock)
    send = transport or default_transport
    result = SearchResult(state=STATE_NEEDS_ASSET)
    all_candidates: List[Candidate] = []
    missing_keys: List[str] = []

    for provider in query.active_providers():
        spec = PROVIDERS[provider]
        key = str(environ.get(spec["env"]) or "").strip()
        if not key:
            missing_keys.append(spec["env"])
            continue
        payload = cache.get(provider, query)
        if payload is not None:
            result.cache_hits += 1
        else:
            result.requests += 1
            status, headers, body = send(_request_for(provider, query, key))
            if status == 429:
                raw_retry = _header(headers, "Retry-After")
                result.retry_after_s = int(raw_retry) if raw_retry.isdigit() else None
                result.state = STATE_RATE_LIMITED
                result.errors.append({"provider": provider, "status": 429,
                                      "retry_after_s": result.retry_after_s,
                                      "reason": "provider rate limit; no automatic re-submit"})
                continue
            if status != 200:
                result.state = STATE_PROVIDER_ERROR
                result.errors.append({"provider": provider, "status": status,
                                      "reason": "non-200 search response"})
                continue
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                result.state = STATE_PROVIDER_ERROR
                result.errors.append({"provider": provider,
                                      "reason": f"unparseable response: {exc}"})
                continue
            if not isinstance(payload, Mapping):
                result.state = STATE_PROVIDER_ERROR
                result.errors.append({"provider": provider, "reason": "response is not an object"})
                continue
            cache.put(provider, query, payload)
        all_candidates.extend(parse_response(provider, payload))

    result.candidates = rank_candidates(all_candidates, query)
    accepted = [c for c in result.candidates if c.accepted]
    # A failure in one provider must not erase usable candidates returned by
    # another; every failure stays visible in ``errors`` and ``retry_after_s``.
    if accepted:
        result.state = STATE_READY
    elif result.state == STATE_RATE_LIMITED:
        pass
    elif any(error.get("status") not in (None, 429)
             or "unparseable" in str(error.get("reason"))
             or "not an object" in str(error.get("reason"))
             for error in result.errors):
        result.state = STATE_PROVIDER_ERROR
    elif missing_keys and not result.requests and not result.cache_hits:
        result.state = STATE_NO_CREDENTIALS
        result.errors.append({"reason": "no provider credentials configured; "
                                        "the local-only asset library remains usable",
                              "missing_env": sorted(set(missing_keys))})
    else:
        result.state = STATE_NEEDS_ASSET
        result.errors.append({"reason": "no candidate passed keyword, ratio, "
                                        "duration, resolution and licence checks"})
    return result


def preview_candidates(result: SearchResult) -> List[Dict[str, Any]]:
    """Human-readable preview rows; no bytes are fetched here."""
    return [{"provider": c.provider, "id": c.provider_id, "author": c.author,
             "license": c.license_id, "description": c.description,
             "width": c.width, "height": c.height, "duration_s": c.duration_s,
             "preview_url": c.preview_url, "accepted": c.accepted,
             "score": round(c.score, 3), "reasons": c.reasons}
            for c in result.candidates]


# ---------------------------------------------------------------------------
# Safe download and registration
# ---------------------------------------------------------------------------

def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "-", value)[:60] or "asset"


def validate_download_url(url: str, *,
                          resolver: Optional[Callable[..., Any]] = None) -> str:
    """Refuse non-TLS, non-CDN, credential-bearing and private-network targets."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError as exc:
        raise StockMediaError(f"malformed download URL: {exc}") from exc
    if parts.scheme != "https":
        raise StockMediaError("download URL must use https")
    if parts.username or parts.password:
        raise StockMediaError("download URL must not carry credentials")
    if parts.port not in (None, 443):
        raise StockMediaError("download URL must use the default TLS port")
    host = parts.hostname or ""
    if not any(host == h or host.endswith("." + h) for h in DOWNLOAD_HOSTS):
        raise StockMediaError(f"download host {host!r} is not an approved CDN")
    if "%" in url or "\\" in url:
        raise StockMediaError("download URL contains suspicious escaping")
    resolve = resolver or socket.getaddrinfo
    try:
        infos = resolve(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise StockMediaError(f"download host cannot be resolved safely: {exc}") from exc
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except (ValueError, IndexError, TypeError):
            raise StockMediaError("download host returned an unparseable address")
        if (address.is_private or address.is_loopback or address.is_link_local
                or address.is_reserved or address.is_multicast or address.is_unspecified):
            raise StockMediaError(f"download host resolves to a non-public address {address}")
    return url


def _suffix_for(url: str, kind: str) -> str:
    path = urllib.parse.urlsplit(url).path.lower()
    allowed = IMAGE_SUFFIXES if kind == "image" else VIDEO_SUFFIXES
    for suffix in allowed:
        if path.endswith(suffix):
            return suffix
    return ".jpg" if kind == "image" else ".mp4"


def _check_magic(data: bytes, kind: str) -> None:
    if not data:
        raise StockMediaError("downloaded asset is empty")
    # MP4 ftyp boxes vary in length; accept any leading box that declares ftyp.
    looks_mp4 = len(data) >= 12 and data[4:8] == b"ftyp"
    valid = looks_mp4 if kind == "video" else any(data.startswith(m) for m in _MAGIC["image"])
    if not valid:
        raise StockMediaError(f"downloaded bytes do not look like a {kind} asset")


def download(candidate: Candidate, *, authorization: Optional[StockAuthorization],
             project_dir: Path, transport: Optional[Transport] = None,
             resolver: Optional[Callable[..., Any]] = None,
             max_bytes: int = MAX_DOWNLOAD_BYTES) -> Dict[str, Any]:
    """Download one authorized candidate, with hard size/URL/content limits."""
    if authorization is None or not authorization.allows_download():
        return {"state": "BLOCKED", "reason": "an explicit search_and_download "
                                              "authorization is required"}
    if not candidate.accepted:
        return {"state": "BLOCKED", "reason": "candidate was not accepted by ranking"}
    project = Path(project_dir).resolve()
    try:
        url = validate_download_url(candidate.download_url, resolver=resolver)
    except StockMediaError as exc:
        return {"state": "INVALID_ASSET", "reason": str(exc)}

    send = transport or default_transport
    status, headers, body = send(urllib.request.Request(url, method="GET"))
    if status == 429:
        raw = _header(headers, "Retry-After")
        return {"state": STATE_RATE_LIMITED, "retry_after_s": int(raw) if raw.isdigit() else None,
                "reason": "provider rate limit; no automatic re-submit"}
    if status != 200:
        return {"state": STATE_PROVIDER_ERROR, "status": status,
                "reason": "download did not return 200"}
    declared = _header(headers, "Content-Length")
    if declared.isdigit() and int(declared) > max_bytes:
        return {"state": "INVALID_ASSET", "reason": "declared size exceeds download cap"}
    if len(body) > max_bytes:
        return {"state": "INVALID_ASSET", "reason": "downloaded bytes exceed download cap"}
    try:
        _check_magic(body, candidate.kind)
    except StockMediaError as exc:
        return {"state": "INVALID_ASSET", "reason": str(exc)}

    digest = hashlib.sha256(body).hexdigest()
    suffix = _suffix_for(url, candidate.kind)
    folder = project / "assets" / "imported" / "stock"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{digest[:16]}-{_safe_name(candidate.provider_id)}{suffix}"
    try:
        target.resolve(strict=False).relative_to(project)
    except ValueError:
        return {"state": "INVALID_ASSET", "reason": "download destination escapes the project"}
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
        state = "REUSED"
    else:
        target.write_bytes(body)
        state = "DOWNLOADED"
    return {
        "state": state, "sha256": digest, "bytes": len(body),
        "path": target.relative_to(project).as_posix(),
        "provider": candidate.provider, "provider_id": candidate.provider_id,
        "source_url": candidate.page_url or url, "download_url": url,
        "author": candidate.author, "license_id": candidate.license_id,
        "kind": candidate.kind, "visual_role_allowlist": list(BROLL_ROLES),
        "evidence_capable": False,
    }


def find_reusable(row: Mapping[str, Any], project_dir: Path,
                  manifest_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Return an already registered, byte-identical asset instead of downloading."""
    path = manifest_path or (Path(project_dir) / "sources" / "assets.json")
    if not path.is_file():
        return None
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for asset in manifest.get("assets") or []:
        if not isinstance(asset, Mapping):
            continue
        if (asset.get("stock_provider_id") == row.get("provider_id")
                and asset.get("sha256") == row.get("sha256")):
            candidate = Path(project_dir) / str(asset.get("repo_relative_path") or "")
            if candidate.is_file() and hashlib.sha256(candidate.read_bytes()).hexdigest() == row.get("sha256"):
                return {"state": "REUSED", "asset_id": asset.get("id"),
                        "sha256": asset.get("sha256"), "path": str(candidate)}
    return None


def register(row: Mapping[str, Any], *, project_dir: Path,
             repo_root: Optional[Path] = None,
             downloaded_at: Optional[str] = None) -> Dict[str, Any]:
    """Register downloaded bytes without inventing a human rights review.

    Writes source provenance, an explicit PENDING rights review record, and a
    manifest row scoped to local B-roll preview only. The existing Rights Gate
    is then called for real; its refusal is reported as ``RIGHTS_REVIEW_REQUIRED``.
    """
    if row.get("state") not in ("DOWNLOADED", "REUSED"):
        return {"state": "REGISTRATION_REFUSED", "reason": "nothing was downloaded"}
    project = Path(project_dir).resolve()
    root = (Path(repo_root).resolve() if repo_root is not None
            else project.parent.parent)
    try:
        project.relative_to(root)
    except ValueError:
        return {"state": "REGISTRATION_REFUSED", "reason": "project lies outside repo root"}
    digest = str(row.get("sha256") or "")
    asset_file = project / str(row.get("path") or "")
    if not asset_file.is_file() or hashlib.sha256(asset_file.read_bytes()).hexdigest() != digest:
        return {"state": "REGISTRATION_REFUSED", "reason": "downloaded bytes failed hash verification"}

    stamp = downloaded_at or datetime.now(timezone.utc).date().isoformat()
    asset_id = f"stock-{digest[:16]}"
    provenance = {
        "schema": f"{SCHEMA}/provenance", "asset_id": asset_id,
        "provider": row.get("provider"), "provider_id": row.get("provider_id"),
        "source_url": row.get("source_url"), "download_url": row.get("download_url"),
        "author": row.get("author"), "license_id": row.get("license_id"),
        "downloaded_at": stamp, "sha256": digest, "bytes": row.get("bytes"),
        "kind": row.get("kind"), "visual_role_allowlist": list(BROLL_ROLES),
        "evidence_capable": False,
        "note": "illustrative B-roll only; may not support a factual claim",
    }
    prov_path = project / "assets" / "imported" / "stock" / f"{asset_id}.source.json"
    prov_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    review = {
        "schema": RIGHTS_REVIEW_SCHEMA,
        "state": "PENDING_HUMAN_REVIEW",
        "license_id": row.get("license_id"),
        "source_url": row.get("source_url"),
        "reviewed_by": "",
        "reviewed_at": "",
        "attribution": row.get("author") or "",
        "synthetic": False,
        "note": "Automated systems must not fabricate human rights review. "
                "A person must fill reviewed_by/reviewed_at before production use.",
    }
    review_path = project / "assets" / f"{asset_id}.rights.json"
    review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")

    manifest_path = project / "sources" / "assets.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"state": "REGISTRATION_REFUSED", "reason": "existing manifest is unreadable"}
        if manifest.get("schema") != MANIFEST_SCHEMA:
            return {"state": "REGISTRATION_REFUSED", "reason": "unsupported manifest schema"}
    else:
        manifest = {"schema": MANIFEST_SCHEMA,
                    "policy": "Stock B-roll is local-preview-only until a human rights review.",
                    "assets": []}
    rows = [a for a in manifest.get("assets") or [] if isinstance(a, Mapping)]
    if not any(a.get("id") == asset_id for a in rows):
        rows.append({
            "id": asset_id, "sha256": digest,
            "type": "EXTERNAL_BROLL_IMAGE" if row.get("kind") == "image"
                    else "EXTERNAL_BROLL_VIDEO",
            "origin": "STOCK_PROVIDER", "permission": "EXTERNAL_BROLL_PENDING_RIGHTS",
            "usage_scope": "LOCAL_PREVIEW_ONLY", "distribution_authorized": False,
            "evidence_capable": False, "visual_role_allowlist": list(BROLL_ROLES),
            "repo_path": asset_file.relative_to(root).as_posix(),
            "repo_relative_path": asset_file.relative_to(project).as_posix(),
            "stock_provider_id": row.get("provider_id"),
            "source_url": row.get("source_url"), "author": row.get("author"),
            "license": row.get("license_id"), "downloaded_at": stamp,
            "rights": {
                "schema": "contentops.media-rights/v1",
                "license_id": row.get("license_id"),
                "source_url": row.get("source_url"),
                "reviewed_by": "", "reviewed_at": "",
                "review_evidence": review_path.relative_to(project).as_posix(),
                "attribution": row.get("author") or "", "synthetic": False,
            },
            "source_provenance": prov_path.relative_to(project).as_posix(),
        })
        manifest["assets"] = rows
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")

    registered = next((a for a in rows if a.get("id") == asset_id), None)
    gate_state = "RIGHTS_REVIEW_REQUIRED"
    gate_reason = ""
    if registered is None:
        gate_reason = "manifest row missing after registration"
    else:
        try:
            validate_declared_asset({"permission": "LICENSED",
                                     "license": row.get("license_id"),
                                     "rights": registered["rights"]}, project)
            # An empty reviewer can never clear the gate; if a future policy
            # change ever lets it through, keep the fail-closed outcome here.
            gate_reason = "human rights review is still pending"
        except RightsError as exc:
            gate_reason = str(exc)
    return {
        "schema": f"{SCHEMA}/registration", "state": gate_state,
        "asset_id": asset_id, "sha256": digest,
        "provenance": prov_path.relative_to(project).as_posix(),
        "rights_review": review_path.relative_to(project).as_posix(),
        "rights_gate_detail": gate_reason,
        "distribution_authorized": False, "evidence_capable": False,
        "visual_role_allowlist": list(BROLL_ROLES),
        "human_rights_review": "PENDING",
    }
