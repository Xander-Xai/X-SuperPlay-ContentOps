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
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "ok": self.ok,
            "count": len(self.items),
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "query": self.query,
            "requested": self.requested,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _http_get(url: str, *, timeout: float, headers: Optional[Dict[str, str]] = None
              ) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(DEFAULT_MAX_BYTES)
    except urllib.error.HTTPError as exc:
        failure = http_error_code(exc.code)
        if failure == "SOURCE_RATE_LIMITED":
            raise FetchError(failure, f"{url} answered 429; this source is rate "
                                      f"limited") from None
        if failure == "SOURCE_CREDENTIALS_REQUIRED":
            raise FetchError(failure, f"{url} answered {exc.code}; this source needs "
                                      f"credentials, and the collector does not hold "
                                      f"any") from None
        raise FetchError(failure, f"{url} answered HTTP {exc.code}") from None
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
            raise FetchError("SOURCE_TIMEOUT",
                             f"{url} did not answer within {timeout:.0f}s") from None
        raise FetchError("SOURCE_UNAVAILABLE",
                         f"{url} could not be reached: {reason}") from None
    except TimeoutError:
        raise FetchError("SOURCE_TIMEOUT",
                         f"{url} did not answer within {timeout:.0f}s") from None
    return body


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
            body = _http_get(url, timeout=timeout)
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
            body = _http_get(url, timeout=timeout,
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
    """Reads a TrendRadar SQLite database, read-only.

    TrendRadar runs outside this repository, so its database is read through a
    URI in read-only mode and is never written to. Four things can go wrong
    and each is named:

    - **the file is absent** — TrendRadar is not deployed here;
    - **the file is locked** — another process holds it;
    - **the schema drifted** — a column this adapter expects is gone;
    - **the rows are duplicated** — the same item appears more than once.

    The schema check is strict on purpose: reading a drifted table and
    returning whatever fits would fill the pool with rows from a table whose
    meaning changed.
    """

    #: The columns this adapter needs. A table without them is refused.
    REQUIRED_COLUMNS = ("title",)
    OPTIONAL_COLUMNS = ("url", "published_at", "rank", "platform", "heat")

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path

    def _resolve_path(self) -> Optional[str]:
        if self.db_path:
            return self.db_path
        return os.environ.get("TRENDRADAR_DB_PATH") or None

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
            return self._read(connection, source, limit, query)
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

    def _read(self, connection: sqlite3.Connection, source: Source, limit: int,
              query: Optional[str]) -> FetchResult:
        try:
            tables = [row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        except sqlite3.DatabaseError as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the TrendRadar database has no readable "
                                           f"schema: {exc}",
                               query=query, requested=limit)
        table = None
        for name in tables:
            if name.lower() in ("trend_data", "news", "hotspots", "items"):
                table = name
                break
        if table is None:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the TrendRadar database has no recognised "
                                           f"table; tables present: {tables}",
                               query=query, requested=limit)
        try:
            columns = [row[1] for row in connection.execute(
                f"PRAGMA table_info({table})").fetchall()]
        except sqlite3.DatabaseError as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the table {table} could not be described: "
                                           f"{exc}",
                               query=query, requested=limit)

        lowered = {str(column).lower(): str(column) for column in columns}
        missing = [column for column in self.REQUIRED_COLUMNS if column not in lowered]
        if missing:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the table {table} no longer has the "
                                           f"columns {missing}; the upstream schema "
                                           f"drifted, so its rows are not read",
                               query=query, requested=limit)

        def column(name: str) -> Optional[str]:
            return lowered.get(name)

        selected = [column("title")] + [column(name) for name in self.OPTIONAL_COLUMNS]
        selected = [name for name in selected if name]
        placeholders = ", ".join("?" for _ in selected)
        order = column("rank") or "rowid"
        sql = (f"SELECT {', '.join(selected)} FROM {table} "
               f"ORDER BY {order} ASC LIMIT ?")
        try:
            rows = connection.execute(sql, (limit,)).fetchall()
        except sqlite3.DatabaseError as exc:
            return FetchResult(source.source_id, False,
                               error_code="SOURCE_DATA_MALFORMED",
                               error_detail=f"the table {table} could not be read: {exc}",
                               query=query, requested=limit)

        items: List[RawItem] = []
        seen: set = set()
        for index, row in enumerate(rows):
            record = dict(zip(selected, row))
            title = str(record.get(column("title")) or "").strip()
            if not title:
                continue
            key = title.casefold()
            if key in seen:
                # A duplicated row is dropped here rather than becoming two
                # candidates that look like two signals.
                continue
            seen.add(key)
            url = str(record.get(column("url")) or "") if column("url") else ""
            items.append(RawItem(
                source_id=source.source_id,
                title=title,
                url=url,
                published_at=_parse_timestamp(record.get(column("published_at"))
                                             if column("published_at") else None),
                rank=index + 1,
                metrics={"heat": record.get(column("heat"))} if column("heat") else {},
                extra={"platform": record.get(column("platform"))} if column("platform") else {},
            ))
        return FetchResult(source.source_id, True, items=items, query=query,
                           requested=limit)


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
