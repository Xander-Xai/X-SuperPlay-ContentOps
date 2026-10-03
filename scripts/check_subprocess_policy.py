#!/usr/bin/env python3
"""Enforce the ContentOps subprocess policy.

Background child processes must go through ``scripts/process_utils.py`` so that
Windows console suppression (``CREATE_NO_WINDOW`` + ``STARTF_USESHOWWINDOW`` /
``SW_HIDE``) is applied in exactly one place. Any direct call to a process
spawning API bypasses that and will flash a CMD/conhost window on Windows.

This check fails CI, which means the rule holds for human contributors and for
Claude Code equally. Uses :mod:`ast` rather than grep so that string literals,
comments and unrelated identifiers containing the same words cannot cause false
positives or hide a real violation.

Usage:
  python scripts/check_subprocess_policy.py           # report and exit 1 on violation
  python scripts/check_subprocess_policy.py --quiet   # summary only

Run: part of scripts/dev_check.py and of the CI policy job.
"""

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from process_utils import hidden_run  # noqa: E402

# Process-spawning APIs that must not be called directly outside process_utils.
FORBIDDEN_SUBPROCESS_CALLS = frozenset({
    "run", "Popen", "call", "check_call", "check_output",
})

# os APIs that spawn a shell; equally forbidden.
FORBIDDEN_OS_CALLS = frozenset({
    "system", "popen",
})

# The abstraction itself. Everything else is business code.
ALLOWED_FILES = {
    "scripts/process_utils.py",
}

# Explicit interactive exceptions. Each entry MUST carry a reason, because an
# unexplained allowlist entry is indistinguishable from a workaround.
#
# Format: path -> reason
INTERACTIVE_ALLOWLIST: dict[str, str] = {}

# Path prefixes never scanned: third-party source that ContentOps does not own.
EXCLUDED_PREFIXES = (
    ".runtime/",
    "Easel/",
)

SKIPPED_DIRS = {".git", ".runtime", "__pycache__", "Easel", "node_modules", ".venv"}


def _tracked_python_files() -> list[Path]:
    """Return tracked *.py files, asking git rather than walking the tree.

    Using ``git ls-files`` means untracked scratch files and gitignored runtime
    checkouts are never scanned, so the policy result matches what CI will see.
    """
    r = hidden_run(["git", "-C", str(ROOT), "ls-files", "--", "*.py"], timeout=60)
    if r.returncode != 0:
        return sorted(p for p in ROOT.rglob("*.py") if _include(p))
    return sorted(
        (ROOT / line.strip())
        for line in (r.stdout or "").splitlines()
        if line.strip() and _include(ROOT / line.strip())
    )


def _include(path: Path) -> bool:
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        return False
    if rel.startswith(EXCLUDED_PREFIXES):
        return False
    return not any(part in SKIPPED_DIRS for part in path.parts)


def _dotted_name(node: ast.AST) -> str:
    """Render an attribute/name chain such as ``subprocess.run`` or ``os.system``."""
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    else:
        return ""
    return ".".join(reversed(parts))


def _shell_true_keyword(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg == "shell":
            if isinstance(kw.value, ast.Constant):
                return bool(kw.value.value)
            # shell=<variable> is unproven; treat as a violation to be explicit.
            return True
    return False


def _rel(path: Path) -> str:
    """Path relative to ROOT, or the absolute path when outside the repo.

    Tolerating out-of-tree paths keeps scan_file() usable for probing a
    candidate file before deciding where it belongs.
    """
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return (line, code, message) violations in one file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [(0, "PARSE_ERROR", f"cannot parse: {e}")]

    rel = _rel(path)
    if rel in ALLOWED_FILES:
        return []

    violations: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted_name(node.func)
        if not dotted:
            continue

        root, _, attr = dotted.rpartition(".")

        if root == "subprocess" and attr in FORBIDDEN_SUBPROCESS_CALLS:
            violations.append((
                node.lineno,
                "DIRECT_SUBPROCESS",
                f"subprocess.{attr}() bypasses process_utils and will flash a "
                f"console window on Windows. Use hidden_run()/hidden_popen() "
                f"for background work, interactive_run() for user-facing auth.",
            ))

        elif root == "os" and attr in FORBIDDEN_OS_CALLS:
            violations.append((
                node.lineno,
                "SHELL_SPAWN",
                f"os.{attr}() spawns a shell with no window control. Use "
                f"process_utils.hidden_run() with an argument list.",
            ))

        elif attr in FORBIDDEN_SUBPROCESS_CALLS and dotted.startswith("sp."):
            violations.append((
                node.lineno,
                "ALIASED_SUBPROCESS",
                f"{dotted}() bypasses process_utils. Import the helper instead.",
            ))

        if _shell_true_keyword(node) and (
            root in {"subprocess", "os", "sp"} or attr in FORBIDDEN_SUBPROCESS_CALLS
        ):
            violations.append((
                node.lineno,
                "SHELL_TRUE",
                "shell=True is forbidden. Pass an argument list, or invoke the "
                "shell as an explicit executable argument.",
            ))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce ContentOps subprocess policy")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    args = parser.parse_args()

    files = _tracked_python_files()
    total = 0
    reported = 0

    for path in files:
        violations = scan_file(path)
        if not violations:
            continue
        rel = _rel(path)
        for lineno, code, message in violations:
            total += 1
            reported += 1
            if not args.quiet:
                where = f"{rel}:{lineno}" if lineno else rel
                print(f"[FAIL] {where}  {code}")
                print(f"       {message}")

    checked = len(files)
    if total:
        print(f"\n[subprocess_policy] FAIL  {total} violation(s) in {checked} tracked file(s)")
        print("Use scripts/process_utils.py. See docs/audits/windows-subprocess-audit.md")
        return 1

    print(f"[subprocess_policy] PASS  {checked} tracked file(s), 0 direct process spawns")
    return 0


if __name__ == "__main__":
    sys.exit(main())