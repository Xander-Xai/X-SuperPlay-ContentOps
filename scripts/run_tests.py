#!/usr/bin/env python3
"""Run every `tests/test_*.py` suite and report one verdict.

Why discovery instead of a hand-maintained list: `dev_check.py` reported
"ALL CHECKS PASSED" while a migration suite was failing, because the suite was
never called. A test file that exists but is never executed cannot report a
pass, and the gate looks healthy while covering less than it appears to.

Each suite is its own process (the suites are standalone `main()` scripts, not
pytest modules). Child processes go through `process_utils` so Windows never
flashes a console window.

A suite that legitimately skips (missing ffmpeg, absent gitignored fixtures)
exits 0 by contract, so it is reported as PASS. A suite that cannot even start
is a FAIL, never a skip.

Usage:
  python scripts/run_tests.py                 # all suites
  python scripts/run_tests.py --list          # names only
  python scripts/run_tests.py --only workflow # substring filter
  python scripts/run_tests.py --timeout 600   # per-suite timeout
  python scripts/run_tests.py --missing-from .github/workflows/ci.yml
      # report suites that exist but no run: step in this file executes (CI drift guard)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

from process_utils import hidden_run, python_executable

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"


def discover() -> list[Path]:
    """Every suite, including one nested in a subdirectory.

    A non-recursive glob would leave `tests/integration/test_*.py` both unrun
    and unreported by the drift guard, which is the failure this file exists to
    prevent.
    """
    suites = sorted(TESTS.rglob("test_*.py"))
    basic = ROOT / "scripts" / "test_basic.py"
    if basic.is_file():
        suites.append(basic)
    return suites


def _tail(text: str, lines: int = 12) -> str:
    rows = [row for row in (text or "").splitlines() if row.strip()]
    return "\n".join(rows[-lines:])


def _console_safe(text: str) -> str:
    """Print captured output whatever the console encoding is.

    A failing suite's traceback can carry characters the Windows console code
    page cannot encode (a replacement character was the measured case). This
    reporter must survive to name the failing suite; it must never die while
    printing the failure it was reporting.
    """
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, errors="replace").decode(encoding, errors="replace")


def run_one(path: Path, timeout: int) -> tuple[bool, str, float]:
    started = time.monotonic()
    try:
        result = hidden_run([python_executable(), str(path)], cwd=str(ROOT), timeout=timeout)
    except subprocess.TimeoutExpired:
        # A hung suite is one failed suite, not the end of the run: letting the
        # exception escape would skip every suite sorted after it.
        return False, f"timed out after {timeout}s", time.monotonic() - started
    except OSError as exc:
        return False, f"could not start: {exc}", time.monotonic() - started
    elapsed = time.monotonic() - started
    if result.returncode == 0:
        return True, "", elapsed
    # Both streams matter: a suite that prints [ok] lines and then dies leaves
    # its traceback on stderr, and showing only stdout would report passing
    # lines for a failed suite.
    parts = []
    if _tail(result.stdout):
        parts.append("stdout:\n" + _tail(result.stdout))
    if _tail(result.stderr):
        parts.append("stderr:\n" + _tail(result.stderr))
    detail = "\n".join(parts) or f"exit {result.returncode}"
    return False, detail, elapsed


def executed_commands(text: str) -> str:
    """The shell a workflow file actually runs, with comments and keys removed.

    A raw substring search over the whole file lets a suite name in a comment
    ("# TODO: wire tests/test_x.py") satisfy the drift guard while nothing
    executes it. Only `run:` scalars and their block bodies count.

    A block scalar ends where YAML ends it: at the first line indented no deeper
    than the `run:` key. Ending it only on a bare `key:` line let a step's
    `name:` line be collected as if it were executed shell.
    """
    collected: list[str] = []
    block_indent: int | None = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if block_indent is not None:
            if indent > block_indent:
                if not stripped.startswith("#"):
                    collected.append(stripped)
                continue
            block_indent = None
        if stripped.startswith("#"):
            continue
        block = re.match(r"^-?\s*run:\s*[|>]-?\s*$", stripped)
        if block:
            block_indent = indent
            continue
        inline = re.match(r"^-?\s*run:\s*(\S.*)$", stripped)
        if inline:
            collected.append(inline.group(1))
    return "\n".join(collected)


def is_wired(name: str, commands: str) -> bool:
    """Is ``name`` the target of a python invocation in these shell commands?

    Requiring a `python ... <name>` shape rules out two lookalikes that a plain
    substring test accepts: a suite named in a step's `name:` line, and a suite
    named inside an `echo` explaining that it is not wired yet.
    """
    pattern = re.compile(r"(?<![\w.\-])" + re.escape(name) + r"(?![\w.\-])")
    return any("python" in line and pattern.search(line)
               for line in commands.splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all test suites")
    parser.add_argument("--list", action="store_true", help="List suites and exit")
    parser.add_argument("--only", default="", help="Only suites whose name contains this")
    parser.add_argument("--timeout", type=int, default=900, help="Per-suite timeout (s)")
    parser.add_argument("--missing-from", default="",
                        help="Report suites this file (e.g. ci.yml) never runs")
    args = parser.parse_args()

    every_suite = discover()
    suites = [p for p in every_suite if args.only.lower() in p.name.lower()]
    if not suites:
        print(f"no suites matched {args.only!r} under {TESTS}")
        return 1
    if args.missing_from:
        target = ROOT / args.missing_from
        try:
            text = target.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"cannot read {args.missing_from}: {exc}")
            return 1
        commands = executed_commands(text)
        # The guard always covers the whole discovered set: --only narrows what
        # runs, never what has to be wired.
        missing = [p for p in every_suite if not is_wired(p.name, commands)]
        if missing:
            print(f"{len(missing)} suite(s) exist but {args.missing_from} never runs them:")
            for path in missing:
                print(f"  {path.relative_to(ROOT).as_posix()}")
            return 1
        print(f"every suite is run by {args.missing_from} "
              f"({len(every_suite)} suites checked)")
        return 0
    if args.list:
        for path in suites:
            print(path.relative_to(ROOT).as_posix())
        return 0

    failures: list[tuple[str, str]] = []
    for path in suites:
        ok, detail, elapsed = run_one(path, args.timeout)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {path.name} ({elapsed:.1f}s)")
        if not ok:
            failures.append((path.name, detail))
            for row in detail.splitlines():
                print(_console_safe(f"    {row}"))

    print("\n" + "=" * 50)
    print(f"{len(suites) - len(failures)}/{len(suites)} suites passed")
    if failures:
        print("FAILED: " + ", ".join(name for name, _ in failures))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
