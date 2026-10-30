#!/usr/bin/env python3
"""Run the collection on a clock, and record what happened.

What a scheduled run may do: crawl (through TrendRadar's own entry point),
find the newest database it wrote, collect for each account, and write an
observation record. What it may not do, by construction and by test: choose a
topic, approve a brief, generate media or publish. Those are person-steps and
the router refuses them without one.

Three things this has to get right on a Windows box that a cron line would
not:

- **only one run at a time.** A second run finds the lock and exits with
  ``ALREADY_RUNNING`` instead of crawling twice or reading a database that is
  being written.
- **the newest database, not a hard-coded date.** TrendRadar writes one file
  per day; the run discovers it, and falls back to the previous day when
  today's file is locked by a still-running crawl.
- **a record that survives a failure.** Every run writes a JSON receipt even
  when it fails, and ``status`` reports a missed run when the last successful
  one is older than the expected interval.

Usage:
    python scripts/router_schedule.py run
    python scripts/router_schedule.py run --skip-crawl          # read what exists
    python scripts/router_schedule.py status
    python scripts/router_schedule.py register                  # print the command
    python scripts/router_schedule.py register --apply          # create the task

Exit codes: 0 the run completed; 3 another run holds the lock; 4 the run
completed but a stage failed (the receipt says which).
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.hotspots.adapters import TRENDRADAR_STALE_HOURS  # noqa: E402
from contentops.hotspots.storage import RouterStore  # noqa: E402
from contentops.routing.router import ContentRouter  # noqa: E402
from process_utils import hidden_run  # noqa: E402

ACCOUNTS = ("x-superplay-1024", "x-superplay-future-intelligence")
DEFAULT_TRENDRADAR_HOME = Path(r"D:\Software\sansan0\TrendRadar\v6.11.0")
TASK_NAME = "ContentOps-Router-Observe"
EXIT_OK = 0
EXIT_LOCKED = 3
EXIT_STAGE_FAILED = 4


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _paths(home: Optional[Path]) -> Dict[str, Path]:
    store_home = Path(home) if home else RouterStore(ROOT).home
    base = store_home / "schedule"
    return {"store": store_home, "base": base, "lock": base / "lock.json",
            "runs": base / "runs"}


def _acquire_lock(lock_path: Path) -> bool:
    """Take the lock, or report that somebody else holds a live one."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in (1, 2):
        try:
            handle = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid(), "at": _now()}, stream)
            return True
        except FileExistsError:
            if attempt == 2:
                return False
            # A lock whose process is gone is not a lock. The threshold is
            # generous because a crawl can legitimately take many minutes.
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                return False
            if age > 3 * 3600:
                try:
                    lock_path.unlink()
                except OSError:
                    return False
                continue
            return False
    return False


def _release_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except OSError:
        pass


def _trendradar_home(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("TRENDRADAR_HOME")
    return Path(env) if env else DEFAULT_TRENDRADAR_HOME


def _python_for(home: Path) -> str:
    """The interpreter that has TrendRadar's dependencies, when it exists."""
    for candidate in (home / ".venv" / "Scripts" / "python.exe",
                      home / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _crawl(home: Path, timeout: float) -> Dict[str, Any]:
    """Run TrendRadar's own entry point. Its exit code and tail are recorded."""
    if not (home / "trendradar").is_dir():
        return {"ok": False, "code": "TRENDRADAR_NOT_DEPLOYED",
                "detail": f"{home} does not contain a TrendRadar checkout"}
    started = time.time()
    try:
        result = hidden_run([_python_for(home), "-m", "trendradar"], cwd=str(home),
                            timeout=timeout,
                            env={**os.environ, "PYTHONIOENCODING": "utf-8",
                                 "PYTHONUTF8": "1"})
    except OSError as exc:
        return {"ok": False, "code": "CRAWL_FAILED", "detail": str(exc),
                "elapsed_s": round(time.time() - started, 1)}
    tail = [line for line in (result.stdout or "").splitlines() if line.strip()][-6:]
    return {"ok": result.returncode == 0, "exit_code": result.returncode,
            "elapsed_s": round(time.time() - started, 1),
            "tail": tail,
            "code": None if result.returncode == 0 else "CRAWL_EXIT_NONZERO"}


def _readable(path: Path) -> bool:
    """Whether the file opens read-only and has the table the reader needs."""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        try:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='news_items'"
            ).fetchone()
            return row is not None
        finally:
            connection.close()
    except sqlite3.Error:
        return False


def _newest_database(home: Path) -> Dict[str, Any]:
    """The newest news database that can actually be read, and why it was chosen.

    TrendRadar writes both ``output/news`` and ``output/rss``; the router only
    reads news, but the newest RSS file is recorded too so a receipt shows
    whether the crawl produced both halves.
    """
    news_dir = home / "output" / "news"
    candidates = sorted(news_dir.glob("*.db"), key=lambda item: item.stem, reverse=True)
    considered: List[Dict[str, Any]] = []
    rss = sorted((home / "output" / "rss").glob("*.db"), key=lambda item: item.stem)
    rss_latest = rss[-1].stem if rss else None
    for path in candidates[:3]:
        readable = _readable(path)
        considered.append({"path": str(path), "date": path.stem, "readable": readable})
        if readable:
            # The data's own age, not the file's: a copied file keeps its rows'
            # timestamps, and it is the rows that decide whether this is news.
            data_age = _data_age_hours(path)
            file_age = (datetime.now(timezone.utc).timestamp()
                        - path.stat().st_mtime) / 3600.0
            age_h = data_age if data_age is not None else file_age
            return {"chosen": str(path), "date": path.stem,
                    "age_hours": round(age_h, 1),
                    "age_source": "rows" if data_age is not None else "file",
                    "file_age_hours": round(file_age, 1),
                    "stale": age_h > TRENDRADAR_STALE_HOURS,
                    "rss_latest": rss_latest, "considered": considered}
    return {"chosen": None, "rss_latest": rss_latest, "considered": considered}


def _data_age_hours(path: Path) -> Optional[float]:
    """How old the newest row in a TrendRadar database is, in hours.

    TrendRadar records local wall-clock timestamps (UTC+8), so the age is
    measured against that clock, not against UTC.
    """
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        try:
            row = connection.execute(
                "SELECT MAX(created_at) FROM news_items").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    if not row or not row[0]:
        return None
    try:
        moment = datetime.strptime(str(row[0]), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone(timedelta(hours=8)))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - moment.astimezone(timezone.utc)
            ).total_seconds() / 3600.0


def _last_success(runs_dir: Path) -> Optional[Dict[str, Any]]:
    if not runs_dir.is_dir():
        return None
    for path in sorted(runs_dir.glob("*.json"), reverse=True):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("status") == "OK":
            return record
    return None


def _missed(runs_dir: Path, interval_hours: float) -> Dict[str, Any]:
    last = _last_success(runs_dir)
    if last is None:
        return {"missed": False, "reason": "no previous successful run to measure against"}
    try:
        last_at = datetime.fromisoformat(str(last["started_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        return {"missed": False, "reason": "the previous receipt has no usable timestamp"}
    gap_h = (datetime.now(timezone.utc) - last_at).total_seconds() / 3600.0
    return {"missed": gap_h > interval_hours * 1.5,
            "hours_since_last_success": round(gap_h, 1),
            "expected_interval_hours": interval_hours,
            "last_success_at": last.get("started_at")}


def cmd_run(args: argparse.Namespace) -> int:
    paths = _paths(Path(args.home) if args.home else None)
    if not _acquire_lock(paths["lock"]):
        print("ALREADY_RUNNING: another scheduled collection holds the lock")
        return EXIT_LOCKED
    record: Dict[str, Any] = {"schema": "contentops.router-schedule/v1",
                              "started_at": _now(), "pid": os.getpid(),
                              "trendradar_home": str(_trendradar_home(args.trendradar_home)),
                              "skip_crawl": bool(args.skip_crawl)}
    status = EXIT_OK
    try:
        home = _trendradar_home(args.trendradar_home)
        record["crawl"] = ({"ok": True, "skipped": True, "code": None}
                           if args.skip_crawl else _crawl(home, args.crawl_timeout))
        if record["crawl"].get("ok"):
            record["database"] = _newest_database(home)
        else:
            record["database"] = {"chosen": None, "reason": "crawl did not succeed"}

        chosen = record["database"].get("chosen")
        accounts: List[Dict[str, Any]] = []
        if chosen:
            store = RouterStore(ROOT, home=paths["store"])
            router = ContentRouter(ROOT, store=store, trendradar_db=chosen)
            for account in (args.account,) if args.account else ACCOUNTS:
                entry: Dict[str, Any] = {"account": account}
                try:
                    result = router.start(account, "HOTSPOT_DISCOVERY")
                    collection = (result.detail or {}).get("collection") or {}
                    entry.update({"state": result.state, "run_id": result.run_id,
                                  "fetched": collection.get("fetched"),
                                  "candidates": collection.get("candidates"),
                                  "stale_sources": collection.get("stale_sources") or []})
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    entry.update({"state": "BLOCKED", "code": type(exc).__name__,
                                  "detail": str(exc)[:300]})
                accounts.append(entry)
        else:
            status = EXIT_STAGE_FAILED
        record["accounts"] = accounts

        if any(entry.get("state") == "BLOCKED" for entry in accounts) or \
                not record["crawl"].get("ok"):
            status = EXIT_STAGE_FAILED
        record["status"] = "OK" if status == EXIT_OK else "DEGRADED"
        record["missed_before_this_run"] = _missed(paths["runs"], args.interval_hours)
    finally:
        record["finished_at"] = _now()
        paths["runs"].mkdir(parents=True, exist_ok=True)
        out = paths["runs"] / f"{record['started_at'].replace(':', '').replace('-', '')}.json"
        out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        _release_lock(paths["lock"])

    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
    else:
        print(f"run        {record['started_at']} -> {record.get('status')}")
        crawl = record.get("crawl") or {}
        print(f"crawl      {'skipped' if crawl.get('skipped') else crawl.get('ok')} "
              f"{crawl.get('code') or ''}".rstrip())
        database = record.get("database") or {}
        print(f"database   {database.get('chosen') or database.get('reason')} "
              f"({database.get('age_hours')} h old)" if database.get("chosen")
              else f"database   {database.get('reason')}")
        for entry in record.get("accounts") or []:
            print(f"{entry['account']:34} {entry.get('state')} "
                  f"fetched={entry.get('fetched')} candidates={entry.get('candidates')} "
                  f"stale={entry.get('stale_sources')}")
        missed = record.get("missed_before_this_run") or {}
        if missed.get("missed"):
            print(f"missed     {missed.get('hours_since_last_success')} h since the last "
                  f"successful run (expected every {missed.get('expected_interval_hours')} h)")
        print(f"receipt    {out}")
    return status


def cmd_status(args: argparse.Namespace) -> int:
    paths = _paths(Path(args.home) if args.home else None)
    lock = paths["lock"]
    payload = {
        "lock_held": lock.exists(),
        "last_success": _last_success(paths["runs"]),
        "missed": _missed(paths["runs"], args.interval_hours),
        "recent": [],
    }
    if paths["runs"].is_dir():
        for path in sorted(paths["runs"].glob("*.json"), reverse=True)[:5]:
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            payload["recent"].append({"at": record.get("started_at"),
                                      "status": record.get("status"),
                                      "database": (record.get("database") or {}).get("date"),
                                      "accounts": [{e.get("account"): e.get("candidates")}
                                                   for e in record.get("accounts") or []]})
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"lock       {'HELD' if payload['lock_held'] else 'free'}")
    missed = payload["missed"]
    print(f"missed     {missed.get('missed')} "
          f"({missed.get('hours_since_last_success')} h since last success)")
    for entry in payload["recent"]:
        print(f"  {entry['at']}  {entry['status']:8} db={entry['database']} {entry['accounts']}")
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    script = ROOT / "scripts" / "router_schedule.py"
    command = f'"{sys.executable}" "{script}" run'
    # In PowerShell the whole /TR value is one single-quoted argument, so the
    # quotes around each path survive into the task definition. The previous
    # form nested double quotes and produced a command schtasks would reject.
    schtasks = (f"schtasks /Create /SC DAILY /ST {args.at} /TN \"{TASK_NAME}\" "
                f"/TR '{command}' /F")
    print("Register this task (run it yourself; it changes this machine):\n")
    print(f"  {schtasks}\n")
    print("Remove it with:\n")
    print(f'  schtasks /Delete /TN "{TASK_NAME}" /F')
    if not args.apply:
        return 0
    result = hidden_run(["schtasks", "/Create", "/SC", "DAILY", "/ST", args.at,
                         "/TN", TASK_NAME, "/TR", command, "/F"], timeout=60)
    print(result.stdout.strip() or result.stderr.strip())
    return 0 if result.returncode == 0 else EXIT_STAGE_FAILED


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="one scheduled collection cycle")
    run.add_argument("--account", default=None)
    run.add_argument("--home", default=None, help="router state directory")
    run.add_argument("--trendradar-home", default=None)
    run.add_argument("--skip-crawl", action="store_true",
                     help="read the newest existing database instead of crawling")
    run.add_argument("--crawl-timeout", type=float, default=900.0)
    run.add_argument("--interval-hours", type=float, default=24.0)
    run.add_argument("--json", action="store_true")
    run.set_defaults(func=cmd_run)

    status = sub.add_parser("status", help="lock state, last runs, missed detection")
    status.add_argument("--home", default=None)
    status.add_argument("--interval-hours", type=float, default=24.0)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=cmd_status)

    register = sub.add_parser("register", help="print or create the scheduled task")
    register.add_argument("--at", default="09:10", help="daily start time, HH:MM")
    register.add_argument("--apply", action="store_true")
    register.set_defaults(func=cmd_register)

    args = parser.parse_args(argv)
    # A scheduled task may run under pythonw.exe, where stdout and stderr are
    # None. The receipt is written either way; this keeps console output from
    # turning a successful run into a crash.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
