"""Reading a source, and failing in a way that names what went wrong.

Why this exists
---------------
A collector that raises is a collector that stops. A collector that silently
returns nothing is worse: the account's allowlist looks honoured while the
pool was empty, and the empty pool reads as "no topics matched" rather than
"the network was down".

So every fetch returns a :class:`FetchResult` that says what happened, and
every failure mode has its own code:

- ``SOURCE_UNAVAILABLE`` — the source could not be reached or answered badly;
- ``SOURCE_TIMEOUT`` — it did not answer in time;
- ``SOURCE_RATE_LIMITED`` — it asked us to slow down;
- ``SOURCE_DATA_MALFORMED`` — it answered with something we cannot read;
- ``SOURCE_UNAVAILABLE_STATE`` — the local TrendRadar database is absent or
  switched off.

A failed source is recorded and skipped. It never stops the other sources, and
it never turns into an empty candidate list presented as a result.

The adapters are deliberately narrow. Each one knows how to speak to one
service and nothing else, so a change in a service's shape is a change in one
file rather than a change in the collector.

Credentials
-----------
No adapter here needs a secret. GitHub's search API works unauthenticated at a
lower rate limit, and the hot-list services are public. That is a deliberate
property: a source that needs a key would make "no credentials" a second,
different failure mode, and the request says the collector must fail safely
without credentials. If a source is ever added that needs one, it must
degrade to a recorded ``SOURCE_CREDENTIALS_REQUIRED`` rather than prompting.
"""

from __future__ import annotations

import json
import http.client
import os
import random
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .source_registry import Source

#: What we call ourselves. The ``Mozilla/5.0 (compatible; …)`` form is the
#: long-standing convention for a non-browser agent, and it is not decoration:
#: the public NewsNow instance answers a bare ``contentops-router`` agent with
#: HTTP 403 and this form with 200. It identifies the caller honestly instead
#: of pretending to be a browser.
USER_AGENT = "Mozilla/5.0 (compatible; ContentOps/1.0)"

#: How long a single request may take. A slow source must not hold the pool.
DEFAULT_TIMEOUT_S = 12.0

#: The upstream list an item came from, when the source publishes one.
DEFAULT_MAX_BYTES = 4 * 1024 * 1024

#: TrendRadar's official compose runs with ``TZ=Asia/Shanghai`` and records
#: local wall-clock timestamps. Reading them as UTC would move every item
#: eight hours into the future, so the offset is stated here rather than
#: guessed at the call site.
TRENDRADAR_TZ = timezone(timedelta(hours=8))

#: A TrendRadar database whose newest crawl is older than this is a frozen
#: list. Its items record what was hot *then*; they may not enter a candidate
#: pool as if they were new.
TRENDRADAR_STALE_HOURS = 24.0


@dataclass(frozen=True)
class RetryPolicy:
    """How hard one request is allowed to try.

    ``attempts`` counts the first try. Three attempts with exponential backoff
    covers a blip; more than that is a service that is down, and hammering a
    down service is how a collector gets blocked.
    """

    attempts: int = 3
    base_delay: float = 0.8
    max_delay: float = 8.0
    #: Status codes worth a second try. Everything else is the request's fault.
    retry_on: Tuple[int, ...] = (429, 500, 502, 503, 504)


DEFAULT_RETRY = RetryPolicy()

#: How many consecutive failures stop a source being contacted in this process.
BREAKER_THRESHOLD = 3

#: How long a tripped breaker stays open.
BREAKER_COOLDOWN_S = 300.0

#: Per-process breaker state, keyed by source id. It is not persisted: a new
#: process is a new chance, which is what a daily run should get.
_BREAKER: Dict[str, Dict[str, float]] = {}


def record_source_result(source_id: str, ok: bool) -> None:
    """Count one outcome for a source, tripping the breaker when it keeps failing."""
    state = _BREAKER.setdefault(source_id, {"failures": 0.0, "opened_at": 0.0})
    if ok:
        state["failures"] = 0.0
        state["opened_at"] = 0.0
        return
    state["failures"] += 1
    if state["failures"] >= BREAKER_THRESHOLD and not state["opened_at"]:
        state["opened_at"] = time.monotonic()


def breaker_open(source_id: str) -> bool:
    """Whether the breaker for a source is currently open."""
    state = _BREAKER.get(source_id)
    if not state or not state.get("opened_at"):
        return False
    if time.monotonic() - state["opened_at"] < BREAKER_COOLDOWN_S:
        return True
    # The cooldown elapsed: give the source one more chance.
    state["opened_at"] = 0.0
    state["failures"] = 0.0
    return False


def breaker_state() -> Dict[str, Dict[str, float]]:
    """The breaker's current view, for a receipt or a test."""
    return {key: dict(value) for key, value in _BREAKER.items()}


def reset_breakers() -> None:
    """Forget every counted failure. Tests and new operator sessions use this."""
    _BREAKER.clear()


def _backoff_delay(attempt: int, policy: RetryPolicy) -> float:
    """Exponential backoff with jitter, capped by the policy."""
    delay = policy.base_delay * (2 ** (attempt - 1))
    delay *= 1.0 + random.uniform(0.0, 0.25)
    return min(delay, policy.max_delay)


class FetchError(Exception):
    """A source failed in a way the collector can name."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass
class RawItem:
    """One item, normalised enough that the ranker does not care who sent it."""

    source_id: str
    title: str
    url: str
    published_at: Optional[str] = None
    rank: Optional[int] = None
    snippet: str = ""
    #: Platform-native counters. Recorded, never compared across platforms.
    metrics: Dict[str, Any] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "rank": self.rank,
            "snippet": self.snippet,
            "metrics": dict(self.metrics),
            "extra": dict(self.extra),
        }


@dataclass
class FetchResult:
    """What one source returned, and what happened instead if it did not."""

    source_id: str
    ok: bool
    items: List[RawItem] = field(default_factory=list)
    error_code: Optional[str] = None
    error_detail: str = ""
    query: Optional[str] = None
    requested: int = 0
    #: When the source says its data was collected. Absent when it does not say.
    observed_at: Optional[str] = None
    #: True when the data is real but older than the source's freshness limit.
    #: A stale list is evidence of what *was* hot; it may not pass as new.
    stale: bool = False
    #: Which upstream layout this result was read from, when it has one.
    schema: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "ok": self.ok,
            "count": len(self.items),
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "query": self.query,
            "requested": self.requested,
            "observed_at": self.observed_at,
            "stale": self.stale,
            "schema": self.schema,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_from_filename(path: str) -> Optional[str]:
    """The day a TrendRadar database covers, from ``YYYY-MM-DD.db``."""
    stem = Path(path).stem
    try:
        datetime.strptime(stem, "%Y-%m-%d")
    except ValueError:
        return None
    return stem


def _trendradar_time(created_at: Any, first_crawl_time: Any,
                     db_date: Optional[str]) -> Optional[datetime]:
    """When TrendRadar first saw a title, as an aware UTC datetime.

    Two shapes exist in a real database: ``created_at`` is a full
    ``YYYY-MM-DD HH:MM:SS`` local timestamp, and ``first_crawl_time`` is only
    ``HH-MM`` — its date is the file's. Both are read; anything else is left
    as no time at all rather than guessed.
    """
    text = str(created_at or "").strip()
    if text:
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(text, pattern).replace(
                    tzinfo=TRENDRADAR_TZ).astimezone(timezone.utc)
            except ValueError:
                continue
    clock = str(first_crawl_time or "").strip()
    if clock and db_date:
        for pattern in ("%H-%M", "%H:%M"):
            try:
                moment = datetime.strptime(f"{db_date} {clock}", "%Y-%m-%d " + pattern)
            except ValueError:
                continue
            return moment.replace(tzinfo=TRENDRADAR_TZ).astimezone(timezone.utc)
    return None


def http_error_code(code: int) -> str:
    """The failure code an HTTP status maps to.

    Kept separate from the request so the mapping can be checked without a
    network: a rate limit and a missing credential are different problems and
    must not be reported as the same one.
    """
    if code == 429:
        return "SOURCE_RATE_LIMITED"
    if code in (401, 403):
        return "SOURCE_CREDENTIALS_REQUIRED"
    return "SOURCE_UNAVAILABLE"


def _http_get(url: str, *, timeout: float, headers: Optional[Dict[str, str]] = None,
              source_id: str = "", policy: Optional[RetryPolicy] = None) -> bytes:
    """One GET, with a bounded retry for the failures that are worth retrying.

    A 429, a 5xx, a timeout or a dropped connection says "not now"; a 401/403
    or a 422 says "not like this", and retrying it would be hammering a door
    that is not going to open. Only the first group is retried, with
    exponential backoff and jitter, and a ``Retry-After`` header is obeyed
    when the service sends one.
    """
    policy = policy or DEFAULT_RETRY
    if source_id and breaker_open(source_id):
        raise FetchError("SOURCE_CIRCUIT_OPEN",
                         f"{source_id} failed {BREAKER_THRESHOLD} times in a row "
                         f"in this process; it is not contacted again for "
                         f"{BREAKER_COOLDOWN_S:.0f}s")
    last: Optional[FetchError] = None
    for attempt in range(1, policy.attempts + 1):
        wait = _backoff_delay(attempt, policy)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                       **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(DEFAULT_MAX_BYTES)
            if source_id:
                record_source_result(source_id, True)
            return body
        except urllib.error.HTTPError as exc:
            failure = http_error_code(exc.code)
            if failure == "SOURCE_RATE_LIMITED":
                last = FetchError(failure, f"{url} answered 429; this source is rate "
                                           f"limited (attempt {attempt}/{policy.attempts})")
                wait = _retry_after(exc) or _backoff_delay(attempt, policy)
            elif failure == "SOURCE_CREDENTIALS_REQUIRED":
                # Retrying a credential problem is hammering a door that is
                # closed to us; say so once and stop.
                if source_id:
                    record_source_result(source_id, False)
                raise FetchError(failure, f"{url} answered {exc.code}; this source needs "
                                          f"credentials, and the collector does not hold "
                                          f"any") from None
            elif exc.code in policy.retry_on:
                last = FetchError(failure, f"{url} answered HTTP {exc.code} "
                                           f"(attempt {attempt}/{policy.attempts})")
            else:
                # 404/422 and friends: the request itself is wrong, so a
                # retry would send the same wrong request again.
                if source_id:
                    record_source_result(source_id, False)
                raise FetchError(failure, f"{url} answered HTTP {exc.code}") from None
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                last = FetchError("SOURCE_TIMEOUT",
                                  f"{url} did not answer within {timeout:.0f}s "
                                  f"(attempt {attempt}/{policy.attempts})")
            else:
                last = FetchError("SOURCE_UNAVAILABLE",
                                  f"{url} could not be reached: {reason} "
                                  f"(attempt {attempt}/{policy.attempts})")
            wait = _backoff_delay(attempt, policy)
        except TimeoutError:
            last = FetchError("SOURCE_TIMEOUT",
                              f"{url} did not answer within {timeout:.0f}s "
                              f"(attempt {attempt}/{policy.attempts})")
            wait = _backoff_delay(attempt, policy)
        except http.client.HTTPException as exc:
            # A connection that drops mid-body is a truncated response, not a
            # wrong one. Reading it as data would give a half-parsed list, so
            # it is named and retried like any other blip.
            last = FetchError("SOURCE_UNAVAILABLE",
                              f"{url} dropped the connection while answering "
                              f"({type(exc).__name__}; attempt "
                              f"{attempt}/{policy.attempts})")
            wait = _backoff_delay(attempt, policy)
        if attempt == policy.attempts:
            break
        time.sleep(min(wait, policy.max_delay))
    if source_id:
        record_source_result(source_id, False)
    assert last is not None
    raise last


def _retry_after(exc: urllib.error.HTTPError) -> Optional[float]:
    """The delay a ``Retry-After`` header asks for, when it asks for seconds."""
    raw = None
    try:
        raw = exc.headers.get("Retry-After") if exc.headers else None
    except AttributeError:
        raw = None
    if not raw:
        return None
    try:
        return max(0.0, float(str(raw).strip()))
    except ValueError:
        return None


class NewsNowAdapter:
    """Reads a pre-ranked list from a NewsNow-compatible endpoint.

    The response shape is a list of objects under ``items`` (older
    deployments use ``data``), each with a ``title``, a ``url`` and an
    ``extra`` object carrying a hover description and a platform counter. The
    upstream is free to change that; when it does, the adapter reports
    ``SOURCE_DATA_MALFORMED`` rather than returning an empty list.
    """

    def fetch(self, source: Source, *, limit: int, timeout: float = DEFAULT_TIMEOUT_S,
              query: Optional[str] = None) -> FetchResult:
        url = source.endpoint
        try:
            body = _http_get(url, timeout=timeout, source_id=source.source_id)
        except FetchError as exc:
            return FetchResult(source.source_id, False, error_code=exc.code,
                               error_detail=exc.detail, query=query, requested=limit)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"{source.endpoint} did not return JSON: {exc}",
                               query=query, requested=limit)

        rows = None
        if isinstance(payload, dict):
            # The public instance answers with ``items``; some
            # NewsNow-compatible deployments wrap the same list in ``data``.
            rows = payload.get("items")
            if rows is None:
                rows = payload.get("data")
        elif isinstance(payload, list):
            rows = payload
        if not isinstance(rows, list):
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"{source.endpoint} returned no list of items",
                               query=query, requested=limit)

        items: List[RawItem] = []
        for index, row in enumerate(rows[:limit]):
            if not isinstance(row, dict):
                continue
            # List titles carry alignment padding ("HKUDS /      DeepTutor").
            title = " ".join(str(row.get("title") or "").split())
            if not title:
                continue
            extra = row.get("extra") if isinstance(row.get("extra"), dict) else {}
            items.append(RawItem(
                source_id=source.source_id,
                title=title,
                url=str(row.get("url") or row.get("mobileUrl") or ""),
                # A list item carries no publication time of its own. Left
                # absent rather than invented from the list's update time.
                published_at=_parse_timestamp(row.get("time")),
                rank=index + 1,
                snippet=str(row.get("description")
                            or extra.get("hover") or "")[:400],
                metrics=_metrics(row),
                extra={"upstream_id": source.upstream_id},
            ))
        return FetchResult(source.source_id, True, items=items, query=query,
                           requested=limit)


class GitHubSearchAdapter:
    """Searches GitHub repositories with a server-side query.

    This is the one source in the catalog that genuinely takes the account's
    keywords. The query is built from the account's terms and passed to
    GitHub, so the narrowing happens at the source and not afterwards.
    """

    def fetch(self, source: Source, *, limit: int, timeout: float = DEFAULT_TIMEOUT_S,
              query: Optional[str] = None) -> FetchResult:
        if not query:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_QUERY_REQUIRED",
                               error_detail="github-search accepts a query and none was given",
                               requested=limit)
        url = (f"{source.endpoint}?q={urllib.parse.quote(query)}"
               f"&sort=updated&order=desc&per_page={max(1, min(limit, 100))}")
        try:
            body = _http_get(url, timeout=timeout, source_id=source.source_id,
                             headers={"Accept": "application/vnd.github+json"})
        except FetchError as exc:
            return FetchResult(source.source_id, False, error_code=exc.code,
                               error_detail=exc.detail, query=query, requested=limit)
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail="github search did not return JSON: "
                                           f"{exc}",
                               query=query, requested=limit)
        rows = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail="github search returned no 'items' array",
                               query=query, requested=limit)

        items: List[RawItem] = []
        for index, row in enumerate(rows[:limit]):
            if not isinstance(row, dict):
                continue
            title = str(row.get("full_name") or row.get("name") or "").strip()
            if not title:
                continue
            items.append(RawItem(
                source_id=source.source_id,
                title=title,
                url=str(row.get("html_url") or ""),
                published_at=_parse_timestamp(row.get("pushed_at") or row.get("created_at")),
                rank=index + 1,
                snippet=str(row.get("description") or "")[:400],
                metrics={"stars": row.get("stargazers_count"),
                         "forks": row.get("forks_count")},
                extra={"language": row.get("language")},
            ))
        return FetchResult(source.source_id, True, items=items, query=query,
                           requested=limit)


class TrendRadarSqliteAdapter:
    """Reads a real TrendRadar database, read-only.

    TrendRadar v6 keeps one SQLite file per day per data type
    (``output/news/YYYY-MM-DD.db`` and ``output/rss/YYYY-MM-DD.db``) and,
    inside it, a ``news_items`` table with one row per (platform, rank, title).
    The platform names live in a ``platforms`` table and the crawl bookkeeping
    in ``crawl_records``.

    This adapter was rewritten against a database produced by a real crawl of
    a pinned v6.11.0 deployment, not against an imagined schema. The first
    version expected invented table names and would have answered
    ``SOURCE_DATA_MALFORMED`` on every genuine file — which is the failure mode
    a fixture can hide for a long time.

    Four things are named rather than smoothed over:

    - **the file is absent** — TrendRadar is not deployed here;
    - **the file is locked** — another process holds it;
    - **the schema drifted** — the columns this reader needs are gone;
    - **the data is stale** — the newest crawl is older than the source's own
      freshness limit, so its items are real but may not pass as new.

    TrendRadar records no publication time. What it records is when *it* first
    saw a title. That is what this adapter returns as ``published_at``, with
    ``extra["published_at_source"] = "trendradar_crawl_time"`` so no downstream
    reader can mistake it for the article's own date.
    """

    #: The table a v6 database carries.
    TABLE = "news_items"
    #: Columns without which the rows cannot be read as items.
    REQUIRED_COLUMNS = ("title", "platform_id", "rank")
    #: Columns read when present.
    OPTIONAL_COLUMNS = ("url", "created_at", "first_crawl_time", "crawl_count")

    def __init__(self, db_path: Optional[str] = None, *,
                 stale_after_hours: float = TRENDRADAR_STALE_HOURS) -> None:
        self.db_path = db_path
        self.stale_after_hours = stale_after_hours

    def _resolve_path(self) -> Optional[str]:
        candidate = self.db_path or os.environ.get("TRENDRADAR_DB_PATH") or None
        if not candidate:
            return None
        path = Path(candidate)
        if path.is_dir():
            # A deployment directory: read the newest day it has.
            known = sorted((path / "news").glob("*.db")) or sorted(path.glob("*.db"))
            return str(known[-1]) if known else None
        return str(path)

    def fetch(self, source: Source, *, limit: int, timeout: float = DEFAULT_TIMEOUT_S,
              query: Optional[str] = None) -> FetchResult:
        path = self._resolve_path()
        if not path:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_UNAVAILABLE_STATE",
                               error_detail="no TrendRadar database is configured; set "
                                           "TRENDRADAR_DB_PATH or pass --trendradar-db",
                               query=query, requested=limit)
        try:
            if not os.path.exists(path):
                return FetchResult(source.source_id, False,
                                   error_code="SOURCE_UNAVAILABLE_STATE",
                                   error_detail=f"the TrendRadar database {path} "
                                                f"does not exist; the service is not "
                                                f"deployed here",
                                   query=query, requested=limit)
            uri = f"file:{urllib.request.pathname2url(path)}?mode=ro"
            connection = sqlite3.connect(uri, uri=True, timeout=max(1.0, timeout / 4))
        except sqlite3.OperationalError as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_UNAVAILABLE_STATE",
                               error_detail=f"the TrendRadar database could not be "
                                            f"opened read-only: {exc}",
                               query=query, requested=limit)
        except (OSError, ValueError) as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_UNAVAILABLE_STATE",
                               error_detail=f"the TrendRadar database path {path} is "
                                            f"not usable: {exc}",
                               query=query, requested=limit)

        try:
            return self._read(connection, source, limit, query, path)
        except sqlite3.OperationalError as exc:
            code = "SOURCE_UNAVAILABLE_STATE" if "locked" in str(exc).lower() \
                else "SOURCE_UNAVAILABLE"
            return FetchResult(source.source_id, False, error_code=code,
                               error_detail=f"the TrendRadar database refused the read: "
                                            f"{exc}",
                               query=query, requested=limit)
        except sqlite3.DatabaseError as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the TrendRadar database is not readable "
                                            f"as SQLite: {exc}",
                               query=query, requested=limit)
        finally:
            connection.close()

    # -- reading ------------------------------------------------------------

    def _read(self, connection: sqlite3.Connection, source: Source, limit: int,
              query: Optional[str], path: str) -> FetchResult:
        try:
            tables = {str(row[0]).lower(): str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        except sqlite3.DatabaseError as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the TrendRadar database has no readable "
                                            f"schema: {exc}",
                               query=query, requested=limit)
        table = tables.get(self.TABLE)
        if table is None:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the TrendRadar database has no "
                                            f"{self.TABLE!r} table, so it is not a v6 "
                                            f"database; tables present: "
                                            f"{sorted(tables.values())}",
                               query=query, requested=limit)

        columns = [str(row[1]) for row in
                   connection.execute(f"PRAGMA table_info({table})").fetchall()]
        lowered = {column.lower(): column for column in columns}
        missing = [name for name in self.REQUIRED_COLUMNS if name not in lowered]
        if missing:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the TrendRadar table {table!r} no longer "
                                            f"has the columns {missing}; the upstream "
                                            f"schema drifted, so its rows are not read",
                               query=query, requested=limit)

        platforms = self._platforms(connection, tables)
        selected = [lowered[name] for name in
                    ("title", "platform_id", "rank") + self.OPTIONAL_COLUMNS
                    if name in lowered]
        order = f"{lowered['platform_id']}, {lowered['rank']}"
        rows = connection.execute(
            f"SELECT {', '.join(selected)} FROM {table} ORDER BY {order}").fetchall()

        db_date = _date_from_filename(path)
        items: List[RawItem] = []
        newest: Optional[datetime] = None
        seen: set = set()
        for row in rows:
            record = dict(zip(selected, row))
            title = " ".join(str(record.get(lowered["title"]) or "").split())
            if not title:
                continue
            platform_id = str(record.get(lowered["platform_id"]) or "")
            key = (title.casefold(), platform_id)
            if key in seen:
                # The same (title, platform) twice is one item. The same title
                # on two platforms is kept: that is a cross-platform signal,
                # not a duplicate.
                continue
            seen.add(key)
            moment = _trendradar_time(
                record.get(lowered.get("created_at", "")),
                record.get(lowered.get("first_crawl_time", "")),
                db_date)
            if moment is not None and (newest is None or moment > newest):
                newest = moment
            items.append(RawItem(
                source_id=source.source_id,
                title=title,
                url=str(record.get(lowered.get("url", "")) or "") if "url" in lowered else "",
                published_at=_iso(moment),
                rank=int(record.get(lowered["rank"]) or 0) or None,
                metrics={"crawl_count": record.get(lowered.get("crawl_count", ""))}
                        if "crawl_count" in lowered else {},
                extra={
                    "platform": platform_id,
                    "platform_name": platforms.get(platform_id, platform_id),
                    "published_at_source": "trendradar_crawl_time",
                },
            ))
            if len(items) >= limit:
                break

        observed = _iso(newest)
        stale = False
        if newest is not None and self.stale_after_hours:
            age = (_now() - newest).total_seconds() / 3600.0
            stale = age > self.stale_after_hours
        return FetchResult(source.source_id, True, items=items, query=query,
                           requested=limit, observed_at=observed, stale=stale,
                           schema=f"trendradar-v6/{self.TABLE}")

    @staticmethod
    def _platforms(connection: sqlite3.Connection,
                   tables: Dict[str, str]) -> Dict[str, str]:
        table = tables.get("platforms")
        if table is None:
            return {}
        try:
            return {str(row[0]): str(row[1]) for row in
                    connection.execute(f"SELECT id, name FROM {table}").fetchall()}
        except sqlite3.DatabaseError:
            # A missing name is cosmetic; the id is still the platform.
            return {}
class FixtureAdapter:
    """Serves a fixed list from a JSON file. Used by the offline tests.

    It exists so the whole collector can be exercised without a network, and
    it is deliberately the *only* adapter the test suite is allowed to use.
    """

    def __init__(self, fixtures: Dict[str, List[Dict[str, Any]]]) -> None:
        self.fixtures = fixtures

    def fetch(self, source: Source, *, limit: int, timeout: float = DEFAULT_TIMEOUT_S,
              query: Optional[str] = None) -> FetchResult:
        rows = self.fixtures.get(source.source_id)
        if rows is None:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_UNAVAILABLE",
                               error_detail=f"no fixture for {source.source_id}",
                               query=query, requested=limit)
        items = []
        for index, row in enumerate(rows[:limit]):
            items.append(RawItem(
                source_id=source.source_id,
                title=str(row.get("title") or ""),
                url=str(row.get("url") or ""),
                published_at=row.get("published_at"),
                rank=index + 1,
                snippet=str(row.get("snippet") or ""),
                metrics=dict(row.get("metrics") or {}),
                extra=dict(row.get("extra") or {}),
            ))
        return FetchResult(source.source_id, True, items=items, query=query,
                           requested=limit)


def adapter_for(source: Source, *, trendradar_db: Optional[str] = None) -> Any:
    """The adapter that speaks to a source."""
    if source.adapter == "github_search":
        return GitHubSearchAdapter()
    if source.adapter == "trendradar_sqlite":
        return TrendRadarSqliteAdapter(trendradar_db)
    return NewsNowAdapter()


def _metrics(row: Dict[str, Any]) -> Dict[str, Any]:
    """Platform counters, kept apart and never summed across platforms."""
    metrics: Dict[str, Any] = {}
    for key in ("hot", "heat", "views", "score", "extra"):
        if key in row and row[key] is not None:
            metrics[key] = row[key]
    return metrics


def _parse_timestamp(value: Any) -> Optional[str]:
    """Best-effort timestamp. Never raises: a missing time is a missing time."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:  # milliseconds
            seconds /= 1000.0
        try:
            return _iso(datetime.fromtimestamp(seconds, tz=timezone.utc))
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for pattern in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, pattern)
            except ValueError:
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return _iso(parsed)
        try:
            return _iso(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def freshness_hours_since(timestamp: Optional[str], *, now: Optional[datetime] = None
                           ) -> Optional[float]:
    """How old a timestamp is, in hours. ``None`` when it cannot be told."""
    if not timestamp:
        return None
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    reference = now or _now()
    return (reference - parsed).total_seconds() / 3600.0


def within_window(timestamp: Optional[str], hours: float,
                   *, now: Optional[datetime] = None) -> bool:
    """Whether a dated item falls inside the freshness window.

    An item with no timestamp is **not** excluded by the window: a window can
    only exclude what it can date. Such an item is kept and is scored zero on
    freshness, and its record says its freshness could not be established — so
    it is visibly weaker rather than silently present or silently missing.
    """
    if not hours or hours <= 0:
        return True
    if not timestamp:
        return True
    age = freshness_hours_since(timestamp, now=now)
    if age is None:
        return True
    return age <= hours


__all__ = [
    "DEFAULT_TIMEOUT_S",
    "FetchError",
    "FetchResult",
    "FixtureAdapter",
    "GitHubSearchAdapter",
    "NewsNowAdapter",
    "RawItem",
    "TrendRadarSqliteAdapter",
    "adapter_for",
    "freshness_hours_since",
    "http_error_code",
    "within_window",
]
