#!/usr/bin/env python3
"""Repository policy checker.

Checks:
  1. No forbidden root files
  2. No local-only files tracked
  3. No large tracked binary files (threshold: 5 MB)
  4. Archive files have status: superseded header
  5. New research files have canonical: false header
  6. New canonical docs appear in docs/INDEX.md

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
