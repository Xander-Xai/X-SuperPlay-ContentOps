"""Persist runs, candidates and the audit trail, isolated per account.

Why this exists
---------------
A candidate pool that lives only in memory cannot answer a question the
account owner will ask: "have we made this one already?". It also cannot be
inspected after the fact, which is what makes a ranking decision reviewable.
So the pool is stored, and the storage is per account.

The isolation is not a filter applied at the end. Every statement that reads
or writes a candidate carries the account id in its ``WHERE`` clause, and
:func:`RouterStore.list_candidates` refuses an account id that does not match
the run's own account. Two accounts that share a repository share a database
file and share nothing else.

Where the file lives
--------------------
Under ``.local/content-router/``, which the repository already ignores. The
pool is runtime state, not source: it is rebuilt from a run, and a commit
should not carry another account's candidate titles. ``CONTENTOPS_ROUTER_HOME``
moves the whole directory for a machine that keeps runtime state elsewhere.

The schema is versioned
-----------------------
TrendRadar's schema can drift; this one is ours, but the same failure applies
— a table that lost a column would otherwise be read as "this row has no
title". The stored version is checked on open, and a mismatch is a refusal
rather than a silent migration.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence

SCHEMA_VERSION = 2

#: Where the router's runtime state lives, relative to the repository root.
DEFAULT_HOME = Path(".local") / "content-router"

#: The environment variable that relocates the whole directory.
HOME_ENV = "CONTENTOPS_ROUTER_HOME"

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    run_id                   TEXT PRIMARY KEY,
    account_id               TEXT NOT NULL,
    account_profile_version  TEXT NOT NULL,
    route_mode               TEXT NOT NULL,
    state                    TEXT NOT NULL,
    created_at               TEXT NOT NULL,
    updated_at               TEXT NOT NULL,
    plan_json                TEXT,
    intent_json              TEXT
);

CREATE TABLE IF NOT EXISTS candidates (
    run_id                   TEXT NOT NULL,
    candidate_id             TEXT NOT NULL,
    account_id               TEXT NOT NULL,
    account_profile_version  TEXT NOT NULL,
    title                    TEXT NOT NULL,
    url                      TEXT,
    source_id                TEXT,
    published_at             TEXT,
    collected_at             TEXT,
    pillar                   TEXT,
    category                 TEXT,
    score                    REAL,
    status                   TEXT NOT NULL,
    payload_json             TEXT NOT NULL,
    PRIMARY KEY (run_id, candidate_id)
);

CREATE TABLE IF NOT EXISTS candidate_sources (
    run_id        TEXT NOT NULL,
    candidate_id  TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    url           TEXT,
    published_at  TEXT,
    rank          INTEGER,
    PRIMARY KEY (run_id, candidate_id, source_id)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL,
    account_id  TEXT NOT NULL,
    at          TEXT NOT NULL,
    state       TEXT NOT NULL,
    detail      TEXT
);

CREATE INDEX IF NOT EXISTS candidates_by_account
    ON candidates (account_id, run_id);
CREATE INDEX IF NOT EXISTS candidates_by_title
    ON candidates (account_id, title);
"""


class StorageError(Exception):
    """The store could not be opened or written."""


def default_home(root: Path) -> Path:
    """The directory the router's runtime state belongs in."""
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override)
    return Path(root) / DEFAULT_HOME


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class RouterStore:
    """The candidate pool and the run record, for one repository.

    Every operation opens its own connection and closes it before returning.
    The alternative — one long-lived connection — holds the database file open
    for the life of the object, which on Windows makes the directory
    impossible to delete, remove or back up while a host process is alive. A
    connection that lives only for the length of one statement costs a few
    milliseconds and cannot do that.
    """

    def __init__(self, root: Path, *, home: Optional[Path] = None) -> None:
        self.root = Path(root)
        self.home = Path(home) if home is not None else default_home(self.root)
        self.db_path = self.home / "router.db"

    # -- lifecycle ----------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """A fresh, verified connection. The caller owns it and must close it.

        Prefer :meth:`session`, which closes it for you.
        """
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.db_path), timeout=10.0)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(DDL)
            row = connection.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                connection.execute("INSERT INTO schema_version (version) VALUES (?)",
                                   (SCHEMA_VERSION,))
            elif int(row["version"]) != SCHEMA_VERSION:
                connection.close()
                raise StorageError(
                    f"the router store at {self.db_path} has schema version "
                    f"{row['version']}, but this code expects {SCHEMA_VERSION}; "
                    f"refusing to read a store whose shape may differ")
            connection.commit()
        except sqlite3.OperationalError as exc:
            raise StorageError(f"the router store at {self.db_path} could not be "
                               f"opened: {exc}") from None
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        """One transaction on one connection, closed on the way out."""
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    # -- runs ---------------------------------------------------------------

    def save_run(self, run_id: str, *, account_id: str, profile_version: str,
                 route_mode: str, state: str, plan: Optional[Dict[str, Any]] = None,
                 intent: Optional[Dict[str, Any]] = None) -> None:
        stamp = _now()
        with self.session() as connection:
            connection.execute(
                "INSERT INTO runs (run_id, account_id, account_profile_version, "
                "route_mode, state, created_at, updated_at, plan_json, intent_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(run_id) DO UPDATE SET "
                "account_profile_version=excluded.account_profile_version, "
                "route_mode=excluded.route_mode, state=excluded.state, "
                "updated_at=excluded.updated_at, plan_json=excluded.plan_json, "
                "intent_json=excluded.intent_json",
                (run_id, account_id, profile_version, route_mode, state, stamp, stamp,
                 json.dumps(plan, ensure_ascii=False) if plan is not None else None,
                 json.dumps(intent, ensure_ascii=False) if intent is not None else None))

    def update_run_state(self, run_id: str, state: str) -> None:
        with self.session() as connection:
            connection.execute("UPDATE runs SET state=?, updated_at=? WHERE run_id=?",
                               (state, _now(), run_id))

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self.session() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?",
                                     (run_id,)).fetchone()
        return dict(row) if row is not None else None

    def list_runs(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.session() as connection:
            if account_id:
                rows = connection.execute(
                    "SELECT * FROM runs WHERE account_id=? ORDER BY created_at DESC",
                    (account_id,)).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM runs ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def run_belongs_to(self, run_id: str, account_id: str) -> bool:
        run = self.get_run(run_id)
        return bool(run and str(run.get("account_id")) == account_id)

    # -- candidates ---------------------------------------------------------

    def save_candidates(self, run_id: str, *, account_id: str, profile_version: str,
                        candidates: Sequence[Dict[str, Any]]) -> List[str]:
        """Store a candidate pool for a run, replacing that run's previous pool."""
        ids: List[str] = []
        with self.session() as connection:
            # The source rows go first, and by run id: a candidate id belongs
            # to the account, so deleting by candidate id would take another
            # run's rows with it.
            connection.execute("DELETE FROM candidate_sources WHERE run_id=?", (run_id,))
            connection.execute("DELETE FROM candidates WHERE run_id=? AND account_id=?",
                               (run_id, account_id))
            for candidate in candidates:
                candidate_id = str(candidate.get("candidate_id"))
                ids.append(candidate_id)
                connection.execute(
                    "INSERT OR REPLACE INTO candidates (candidate_id, run_id, account_id, "
                    "account_profile_version, title, url, source_id, published_at, "
                    "collected_at, pillar, category, score, status, payload_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (candidate_id, run_id, account_id, profile_version,
                     str(candidate.get("title") or ""), candidate.get("url"),
                     candidate.get("source_id"), candidate.get("published_at"),
                     candidate.get("collected_at"), candidate.get("pillar"),
                     candidate.get("category"),
                     float((candidate.get("relevance") or {}).get("score") or 0.0),
                     str(candidate.get("status") or "candidate"),
                     json.dumps(candidate, ensure_ascii=False)))
                for source in candidate.get("sources") or []:
                    connection.execute(
                        "INSERT OR REPLACE INTO candidate_sources (run_id, candidate_id, "
                        "source_id, url, published_at, rank) VALUES (?, ?, ?, ?, ?, ?)",
                        (run_id, candidate_id, str(source.get("source_id") or ""),
                         source.get("url"), source.get("published_at"),
                         source.get("rank")))
        return ids

    def list_candidates(self, account_id: str, *, run_id: Optional[str] = None,
                        status: Optional[str] = None) -> List[Dict[str, Any]]:
        """The candidates of one account. Another account's rows are never read."""
        clauses = ["account_id=?"]
        params: List[Any] = [account_id]
        if run_id:
            clauses.append("run_id=?")
            params.append(run_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        with self.session() as connection:
            rows = connection.execute(
                f"SELECT * FROM candidates WHERE {' AND '.join(clauses)} "
                f"ORDER BY score DESC, published_at DESC", params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def get_candidate(self, account_id: str, candidate_id: str) -> Optional[Dict[str, Any]]:
        """The candidate, from the most recent run that carried it.

        A candidate id is the account's identity for a story, not a run's, so
        the same story found twice belongs to two runs. The newest one is the
        one a person is choosing from.
        """
        with self.session() as connection:
            row = connection.execute(
                "SELECT payload_json FROM candidates WHERE candidate_id=? AND account_id=? "
                "ORDER BY collected_at DESC LIMIT 1",
                (candidate_id, account_id)).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def find_candidate_run(self, account_id: str, candidate_id: str) -> Optional[str]:
        """The run a candidate belongs to, so a choice can name one id."""
        with self.session() as connection:
            row = connection.execute(
                "SELECT run_id FROM candidates WHERE candidate_id=? AND account_id=? "
                "ORDER BY collected_at DESC LIMIT 1",
                (candidate_id, account_id)).fetchone()
        return str(row["run_id"]) if row is not None else None

    def account_of_run(self, run_id: str) -> Optional[str]:
        """Which account a run belongs to."""
        run = self.get_run(run_id)
        return str(run["account_id"]) if run is not None else None

    def set_candidate_status(self, account_id: str, candidate_id: str, status: str,
                             run_id: Optional[str] = None) -> bool:
        """Mark a candidate chosen or otherwise.

        The run id narrows the change to one pool when the caller knows it;
        without it, the most recent pool holding the candidate is marked.
        """
        with self.session() as connection:
            if run_id:
                cursor = connection.execute(
                    "UPDATE candidates SET status=? WHERE candidate_id=? AND "
                    "account_id=? AND run_id=?",
                    (status, candidate_id, account_id, run_id))
            else:
                cursor = connection.execute(
                    "UPDATE candidates SET status=? WHERE candidate_id=? AND account_id=? "
                    "AND run_id = (SELECT run_id FROM candidates WHERE candidate_id=? "
                    "AND account_id=? ORDER BY collected_at DESC LIMIT 1)",
                    (status, candidate_id, account_id, candidate_id, account_id))
            changed = cursor.rowcount
        return changed > 0

    def title_appearances(self, account_id: str, title: str) -> int:
        """How often this account has already seen a title.

        This is what makes the ``non_repetition`` component mean something: a
        topic that has already been offered to this account scores lower than
        one that has not, and the count comes from this account's own history.
        """
        with self.session() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM candidates WHERE account_id=? AND title=?",
                (account_id, title)).fetchone()
        return int(row["n"]) if row is not None else 0

    # -- audit trail --------------------------------------------------------

    def record_event(self, run_id: str, account_id: str, state: str,
                     detail: str = "") -> None:
        with self.session() as connection:
            connection.execute(
                "INSERT INTO events (run_id, account_id, at, state, detail) "
                "VALUES (?, ?, ?, ?, ?)", (run_id, account_id, _now(), state, detail))

    def list_events(self, run_id: str) -> List[Dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id=? ORDER BY id ASC",
                (run_id,)).fetchall()
        return [dict(row) for row in rows]
