#!/usr/bin/env python3
"""Enforce the ContentOps subprocess policy.

Background child processes must go through ``scripts/process_utils.py`` so that
Windows console suppression (``CREATE_NO_WINDOW`` + ``STARTF_USESHOWWINDOW`` /
``SW_HIDE``) is applied in exactly one place. Any direct call to a process
spawning API bypasses that and will flash a CMD/conhost window on Windows.

This check fails CI, which means the rule holds for human contributors and for
Claude Code equally.

Detection is semantic, not textual
----------------------------------
The scanner resolves imports before deciding what a call is, so an alias
cannot hide a violation:

===========================================  ==========================
source                                      resolved as
===========================================  ==========================
``import subprocess``                        ``subprocess``
``import subprocess as proc``                ``proc``
``import subprocess as anything``            ``anything``
``from subprocess import run``               ``run``
``from subprocess import run as execute``    ``execute``
``from subprocess import Popen``             ``Popen``
``import os as operating_system``            ``operating_system``
``from os import popen as pipe``             ``pipe``
===========================================  ==========================

Alias choice is never trusted: only the import binding matters, so naming an
alias ``sp`` grants nothing.

:mod:`ast` is used rather than grep, so string literals and comments cannot
produce false positives, and no comment or unusual formatting can hide a real
call.

Usage:
  python scripts/check_subprocess_policy.py           # report, exit 1 on violation
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

# Modules that can spawn a process, mapped to the attributes that actually do.
# Attribute lookups are constant-time dict access; an attribute not listed here
# (PIPE, DEVNULL, STARTUPINFO, TimeoutExpired, CompletedProcess, ...) is inert.
FORBIDDEN_ATTRIBUTES: dict[str, frozenset[str]] = {
    "subprocess": frozenset({"run", "Popen", "call", "check_call", "check_output"}),
    "os": frozenset({"system", "popen"}),
    # Covered so an async provider cannot bypass the gate later. Both spawn a
    # child process with the same console-visibility consequence.
    "asyncio": frozenset({"create_subprocess_exec", "create_subprocess_shell"}),
}

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


class SymbolTable:
    """Import bindings that can reach a process-spawning call.

    ``module_aliases`` maps a local name bound by ``import`` to the real root
    module (``proc`` -> ``subprocess``). ``from_aliases`` maps a local name
    bound by ``from x import y`` to ``(module, symbol)``. Star imports are
    recorded because they make the bindings unprovable.
    """

    def __init__(self) -> None:
        self.module_aliases: dict[str, str] = {}
        self.from_aliases: dict[str, tuple[str, str]] = {}
        self.star_modules: set[str] = set()

    def add_import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".")[0]
            if alias.asname:
                self.module_aliases[alias.asname] = root
            else:
                # `import a.b.c` binds the name `a`.
                self.module_aliases[root] = root

    def add_from_import(self, node: ast.ImportFrom) -> None:
        if node.level:  # relative import, never stdlib subprocess/os/asyncio
            return
        module = (node.module or "").split(".")[0]
        for alias in node.names:
            if alias.name == "*":
                self.star_modules.add(module)
                continue
            local = alias.asname or alias.name
            self.from_aliases[local] = (module, alias.name)

    def resolve_attribute(self, dotted: str) -> tuple[str, str] | None:
        """Return ``(module, symbol)`` for ``alias.symbol``, else None."""
        base, _, attr = dotted.rpartition(".")
        if not base:
            return None
        module = self.module_aliases.get(base)
        if module is None:
            # A bare `subprocess.run(...)` with no import in scope: still a hit.
            module = base
        return (module, attr)

    def resolve_bare(self, name: str) -> tuple[str, str] | None:
        """Return ``(module, symbol)`` for a bare ``name(...)``, else None."""
        return self.from_aliases.get(name)


def _build_symbol_table(tree: ast.AST) -> SymbolTable:
    table = SymbolTable()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            table.add_import(node)
        elif isinstance(node, ast.ImportFrom):
            table.add_from_import(node)
    return table


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


def _describe(module: str, symbol: str) -> str:
    if module == "asyncio":
        return (
            f"{module}.{symbol}() spawns a child process without window "
            f"control. Await it under process_utils, or record a reason in "
            f"INTERACTIVE_ALLOWLIST if a visible console is genuinely required."
        )
    return (
        f"{module}.{symbol}() bypasses process_utils and will flash a console "
        f"window on Windows. Use hidden_run()/hidden_popen() for background "
        f"work, interactive_run() for user-facing auth."
    )


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Return ``(line, code, message)`` violations in one file."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError) as e:
        return [(0, "PARSE_ERROR", f"cannot parse: {e}")]

    rel = _rel(path)
    if rel in ALLOWED_FILES:
        return []

    table = _build_symbol_table(tree)
    violations: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            module = (node.module or "").split(".")[0]
            for alias in node.names:
                if alias.name == "*" and module in FORBIDDEN_ATTRIBUTES:
                    violations.append((
                        node.lineno,
                        "STAR_IMPORT",
                        f"from {module} import * makes the bindings "
                        f"unprovable, so a process-spawning call could hide in "
                        f"it. Import the specific symbols you need.",
                    ))

        if not isinstance(node, ast.Call):
            continue

        resolved: tuple[str, str] | None = None
        code = ""

        # A bare Name means `from subprocess import run`; anything else is an
        # attribute access such as `proc.run`. Distinguishing on node type
        # matters: _dotted_name() returns "run" for a bare Name, which would
        # otherwise be misread as an attribute chain with an empty base.
        if isinstance(node.func, ast.Name):
            resolved = table.resolve_bare(node.func.id)
            code = "FROM_IMPORT_SUBPROCESS"
        else:
            dotted = _dotted_name(node.func)
            if dotted:
                resolved = table.resolve_attribute(dotted)
                code = "ALIASED_SUBPROCESS"

        if resolved:
            module, symbol = resolved
            if symbol in FORBIDDEN_ATTRIBUTES.get(module, frozenset()):
                violations.append((node.lineno, code, _describe(module, symbol)))

        if _shell_true_keyword(node) and resolved:
            module, symbol = resolved
            if symbol in FORBIDDEN_ATTRIBUTES.get(module, frozenset()):
                violations.append((
                    node.lineno,
                    "SHELL_TRUE",
                    "shell=True is forbidden. Pass an argument list, or invoke "
                    "the shell as an explicit executable argument.",
                ))

    return violations


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce ContentOps subprocess policy")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    args = parser.parse_args()

    files = _tracked_python_files()
    total = 0

    for path in files:
        violations = scan_file(path)
        if not violations:
            continue
        rel = _rel(path)
        for lineno, code, message in violations:
            total += 1
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