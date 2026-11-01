#!/usr/bin/env python3
"""Repository policy checker.

Checks:
  1. No forbidden root files
  2. No local-only files tracked
  3. No large tracked binary files (threshold: 5 MB)
  4. Archive files have status: superseded header
  5. New research files have canonical: false header
  6. New canonical docs appear in docs/INDEX.md
  7. No private provider task state tracked
  8. Every tests/test_*.py suite is wired into the CI workflow

Exit 0 = pass, exit 1 = fail.
"""

import re
import sys
from pathlib import Path

from process_utils import hidden_run

ROOT = Path(__file__).resolve().parents[1]

# Files that must NEVER appear in the repo root
FORBIDDEN_ROOT = {
    "analysis.md", "notes.md", "report-final.md", "final-v2.md",
    "claude-output.md", "tmp.md", "TODO.md", "CHANGELOG-old.md",
    "credentials.txt", "secrets.md",
}

# Files that must be gitignored (never tracked)
LOCAL_ONLY = {
    ".env", ".verify-tmp", "docs/ai-provider-selection.md",
    "runtime-config-backups", "diagnostics", "outputs",
}

# Size threshold for tracked binary files (5 MB)
LARGE_FILE_THRESHOLD = 5 * 1024 * 1024


def _git_files():
    r = hidden_run(["git", "-C", str(ROOT), "ls-files"], timeout=30)
    if r.returncode != 0:
        return []
    return [line.strip() for line in r.stdout.splitlines() if line.strip()]


def check_no_tracked_task_state():
    """No private provider task state may ever be tracked.

    ``task-state/`` holds **raw** provider task ids. They exist for one legitimate
    reason: an interrupted generation must be able to resume the *same* task
    instead of paying for a second one. That makes them runtime state by
    definition, and the correct handling is to ignore them rather than sanitise
    them into a tracked artifact -- a sanitised copy would invite somebody to
    treat it as the recovery handle when it is not one.

    ``.gitignore`` already excludes them. This check is the second line, because a
    force-add, a copied work directory or a loosened ignore rule would otherwise
    leak a provider identifier into permanent history.
    """
    failures = []
    offenders = [
        path for path in _git_files()
        if "task-state/" in path.replace("\\", "/")
        or Path(path).name == "task-state"
    ]
    for path in offenders:
        failures.append(
            f"tracked private task state: {path} -- raw provider task ids must "
            f"never be committed; untrack it and keep it under an ignored "
            f"work directory"
        )
    return failures


#: Directory names that hold per-host runtime state. The leading dot keeps them out
#: of a normal source layout, but nothing stops `git add -A` from staging them.
LOCAL_STATE_DIRS = (".openclaw", ".hyperframes")


def is_local_agent_state(path):
    """Whether a repo-relative path sits inside a per-host runtime-state directory.

    Pure, so the rule can be tested without staging anything. Matches at any depth,
    because these directories are created beside a project rather than at a fixed
    level, and ``Path.parts`` already splits both separators on this host.
    """
    return any(part in LOCAL_STATE_DIRS for part in Path(path).parts)


def check_no_tracked_agent_state():
    """No agent session or render state may ever be tracked.

    ``.openclaw/`` holds live OpenClaw agent state -- SQLite databases, their WAL/SHM
    sidecars, a quarantine database and prompt scratch files. ``.hyperframes/`` holds
    per-composition render bookkeeping. Neither is source, evidence or a receipt: both
    are a running tool's memory on disk, and the SQLite sidecars are only coherent
    alongside the database they belong to.

    Both are already ignored. This is the second line for the same reason as
    ``task-state/``: ``.gitignore`` cannot stop ``git add -f``, and a force-added
    database would publish one operator's agent session history into permanent,
    public history.
    """
    failures = []
    for path in _git_files():
        if is_local_agent_state(path):
            failures.append(
                f"tracked local agent state: {path} -- session and render state must "
                f"never be committed; untrack it and let `.gitignore` keep it out"
            )
    return failures


def check_root_files():
    failures = []
    root_files = {p.name for p in ROOT.iterdir() if p.is_file() and not p.name.startswith('.')}
    for f in FORBIDDEN_ROOT:
        if f in root_files:
            failures.append(f"FORBIDDEN ROOT FILE: {f}")
    return failures


def check_local_only():
    failures = []
    tracked = set(_git_files())
    for item in LOCAL_ONLY:
        # Check if it appears as a tracked file
        for t in tracked:
            if t == item or t.startswith(item + "/"):
                failures.append(f"LOCAL-ONLY FILE TRACKED: {t} (must be gitignored)")
    return failures


def check_large_files():
    failures = []
    for rel in _git_files():
        path = ROOT / rel
        if path.is_file():
            try:
                size = path.stat().st_size
                if size > LARGE_FILE_THRESHOLD:
                    # Check allowlist
                    if rel in {"projects/easel-review/final/final.mp4"}:
                        continue
                    failures.append(f"LARGE TRACKED FILE ({size//1024//1024}MB): {rel}")
            except Exception:
                pass
    return failures


def check_archive_metadata():
    failures = []
    archive_dir = ROOT / "research" / "archive"
    if archive_dir.exists():
        for f in archive_dir.rglob("*.md"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "status:" not in text or "superseded" not in text.lower():
                failures.append(f"ARCHIVE WITHOUT METADATA: {f.relative_to(ROOT)}")
    return failures


def check_research_metadata():
    failures = []
    research_dir = ROOT / "research"
    if research_dir.exists():
        for f in research_dir.rglob("*.md"):
            if "archive" in f.relative_to(ROOT).parts:
                continue
            text = f.read_text(encoding="utf-8", errors="ignore")
            if "canonical:" not in text or "false" not in text.lower():
                # Only flag if it looks like a research doc (not README.md)
                if f.name not in ("README.md",):
                    failures.append(f"RESEARCH WITHOUT METADATA: {f.relative_to(ROOT)}")
    return failures


def check_no_c0_control_chars():
    """Check tracked text files contain no C0 control chars (except LF/CR/TAB).

    Forbidden: U+0000-U+0008, U+000B, U+000C, U+000E-U+001F, U+007F
    Allowed:    U+0009 (TAB), U+000A (LF), U+000D (CR)

    C0 chars in tracked source/docs indicate corrupted file generation
    (e.g. PowerShell here-string escape misinterpretation).
    """
    failures = []
    FORBIDDEN = (
        set(range(0x00, 0x09))
        | {0x0B}
        | {0x0C}
        | set(range(0x0E, 0x20))
        | {0x7F}
    )
    TEXT_EXTS = {
        ".md", ".py", ".yaml", ".yml", ".json", ".txt",
        ".sh", ".ps1", ".example", ".gitignore",
        ".gitattributes", ".editorconfig",
    }

    for rel in _git_files():
        path = ROOT / rel
        if not path.is_file():
            continue
        if path.suffix not in TEXT_EXTS:
            continue
        parts = rel.split("/")
        if any(ex in parts for ex in {
            ".runtime", "Easel", "node_modules", ".venv",
            "__pycache__", ".git", ".workbuddy", "diagnostics",
            "runtime-config-backups", "runtime-diagnostics",
        }):
            continue
        try:
            data = path.read_bytes()
        except Exception:
            continue
        for i, b in enumerate(data):
            if b in FORBIDDEN:
                line_num = data[:i].count(b"\n") + 1
                failures.append(
                    f"C0 CONTROL CHAR (0x{b:02x}): {rel} line {line_num}"
                )
                break
    return failures


def check_index_tracking():
    failures = []
    index = ROOT / "docs" / "INDEX.md"
    if not index.exists():
        failures.append("MISSING: docs/INDEX.md")
        return failures
    text = index.read_text(encoding="utf-8", errors="ignore")

    # Check that key canonical docs are actually tracked
    required = [
        "CURRENT-STATE.md",
        "ARCHITECTURE.md",
        "PRD.md",
        "RUNBOOK.md",
        "QUALITY-STANDARD.md",
        "UPSTREAM-EASEL.md",
        "GLOSSARY.md",
        "adr/ADR-001",
        "adr/ADR-002",
        "adr/ADR-003",
        "adr/ADR-004",
        "adr/ADR-005",
        "adr/ADR-006",
    ]
    for doc in required:
        if doc not in text:
            failures.append(f"INDEX MISSING: {doc}")
    return failures


def check_test_suites_registered_in_ci():
    """Every suite under tests/ must be wired into the CI workflow.

    A suite that is not named in ``.github/workflows/ci.yml`` never runs, and a
    green CI run is then not evidence that it passed. That gap is invisible by
    construction: the file looks complete from the outside. Two milestone
    suites were merged unwired once, so the gap is checked, not remembered.
    """
    failures = []
    workflow = ROOT / ".github" / "workflows" / "ci.yml"
    if not workflow.exists():
        return ["MISSING: .github/workflows/ci.yml — cannot verify CI wiring"]

    text = workflow.read_text(encoding="utf-8", errors="ignore")
    tests_dir = ROOT / "tests"
    if not tests_dir.is_dir():
        return []

    for suite in sorted(tests_dir.glob("test_*.py")):
        rel = f"tests/{suite.name}"
        if rel not in text:
            failures.append(
                f"TEST SUITE NOT IN CI: {rel} — add a named step to "
                f".github/workflows/ci.yml or the suite never runs"
            )
    return failures


def main():
    all_failures = []
    checks = [
        ("forbidden_root", check_root_files),
        ("local_only", check_local_only),
        ("large_files", check_large_files),
        ("archive_metadata", check_archive_metadata),
        ("research_metadata", check_research_metadata),
        ("no_c0_chars", check_no_c0_control_chars),
        ("index_tracking", check_index_tracking),
        ("no_tracked_task_state", check_no_tracked_task_state),
        ("no_tracked_agent_state", check_no_tracked_agent_state),
        ("test_suites_in_ci", check_test_suites_registered_in_ci),
    ]
    for name, fn in checks:
        failures = fn()
        if failures:
            print(f"\n[{name}] FAIL")
            for f in failures:
                print(f"  [FAIL] {f}")
            all_failures.extend(failures)
        else:
            print(f"[{name}] PASS")

    if all_failures:
        print(f"\n{len(all_failures)} policy check(s) failed")
        return 1
    print("\nAll repository policy checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
