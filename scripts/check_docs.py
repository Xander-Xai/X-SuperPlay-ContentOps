#!/usr/bin/env python3
"""Documentation consistency and public-repo safety checker.

Checks:
    1. Broken internal markdown links
    2. Stale active version references (0.1.1 outside research/archive/)
    3. Canonical doc files exist
    4. Runtime pin consistency (lock file vs active docs)
    5. Sensitive string patterns (no secrets in public repo)

Exit 0 = all pass, exit 1 = failures found.
Never prints secret values — only file, line, and rule name.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# --- Canonical files that must exist ---
CANONICAL_DOCS = [
    "docs/INDEX.md",
    "docs/CURRENT-STATE.md",
    "docs/ARCHITECTURE.md",
    "docs/PRD.md",
    "docs/RUNBOOK.md",
    "docs/QUALITY-STANDARD.md",
    "docs/DEVELOPMENT-PLAN.md",
    "docs/TEST-PLAN.md",
    "docs/UPSTREAM-EASEL.md",
    "docs/SOURCE-ARTIFACT-CONTRACT.md",
    "docs/MEDIA-PROVIDER-CONTRACT.md",
    "docs/CROSS-REPO-INTEGRATION.md",
    "docs/AUDIT-REPORT.md",
    "docs/adr/ADR-001-easel-runtime.md",
    "docs/adr/ADR-002-contentops-boundaries.md",
    "docs/adr/ADR-003-minimax-plan-provider.md",
    "docs/adr/ADR-004-cross-repo-source-contract.md",
    "docs/adr/ADR-005-human-approval.md",
    "docs/adr/ADR-006-upstream-upgrade-policy.md",
    "README.md",
    "AGENTS.md",
    "research/README.md",
]

# --- Sensitive patterns (checked in tracked files only) ---
SENSITIVE_PATTERNS = [
    (r"api\.minimaxi\.com", "provider_endpoint"),
    (r"Bearer\s+[A-Za-z0-9]", "bearer_token"),
    (r"api_key\s*=\s*[A-Za-z0-9]{10,}", "api_key_value"),
    (r"sk-ant-[A-Za-z0-9]{10,}", "anthropic_key"),
    (r"sk-proj-[A-Za-z0-9]{10,}", "openai_key"),
    (r"MINIMAX_API_KEY\s*=\s*[A-Za-z0-9]{10,}", "minimax_key_value"),
    (r"ANTHROPIC_API_KEY\s*=\s*sk-", "anthropic_key_value"),
    (r"password\s*=\s*[^\s]{6,}", "password_value"),
    (r"cookie\s*[:=]\s*[A-Za-z0-9]{20,}", "cookie_value"),
]

# --- Directories excluded from all checks (upstream / vendored / archived) ---
EXCLUDE_DIRS = {
    ".runtime",        # vendored Easel runtime
    "Easel",           # upstream Easel working clone
    "node_modules",    # npm packages
    ".venv",           # Python venvs
    "__pycache__",
    ".git",
    ".workbuddy",
    "diagnostics",
    "runtime-config-backups",
    "runtime-diagnostics",
    "runtime-diagnostics",
    "01-Experiments",  # will be archived in Commit 7
    "02-Runtime",      # will be archived in Commit 7
    "projects",        # checked separately below
}


def _is_active_doc(path: Path) -> bool:
    """A doc is 'active' if it's not in research/archive/ or an excluded dir."""
    parts = path.relative_to(ROOT).parts if path.is_absolute() else path.parts
    return (
        "archive" not in parts
        and not any(ex in parts for ex in EXCLUDE_DIRS)
    )


def _scan_markdown_files(extra_dirs: list[Path] = None) -> list[Path]:
    """Scan .md files in ROOT + docs + research (not archive) + extra_dirs."""
    md_files = []
    scan_dirs = [ROOT, ROOT / "docs", ROOT / "research"] + (extra_dirs or [])
    for d in scan_dirs:
        if not d.exists():
            continue
        for f in d.rglob("*.md"):
            parts = f.relative_to(ROOT).parts
            if "archive" in parts:
                continue
            if any(ex in parts for ex in EXCLUDE_DIRS):
                continue
            md_files.append(f)
    return md_files


def check_canonical_files():
    """Check that all canonical doc files exist."""
    failures = []
    for rel in CANONICAL_DOCS:
        if not (ROOT / rel).is_file():
            failures.append(f"MISSING canonical doc: {rel}")
    return failures


def check_broken_links():
    """Check internal markdown links in X-SuperPlay-owned tracked docs."""
    failures = []
    # Markdown link pattern: [text](path)
    link_re = re.compile(r'\[([^\]]*)\]\(([^)]+)\)')

    # Scan docs, research (not archive), plus projects/easel-review (receipts)
    md_files = _scan_markdown_files(extra_dirs=[ROOT / "projects" / "easel-review"])

    for md in md_files:
        text = md.read_text(encoding="utf-8")
        for m in link_re.finditer(text):
            link = m.group(2)
            # Skip http links and anchors
            if link.startswith(("http://", "https://", "#", "mailto:")):
                continue
            # Strip anchor
            path_part = link.split("#")[0]
            if not path_part:
                continue
            # Resolve relative to the markdown file's directory (not ROOT)
            target = (md.parent / path_part).resolve()
            if not target.exists():
                rel = md.relative_to(ROOT)
                failures.append(f"BROKEN LINK: {rel} -> {link}")
    return failures


def check_stale_version():
    """Check no active X-SuperPlay-owned doc references Easel 0.1.1 as current.

    Files in research/archive/ are historical and skipped.
    Files in .runtime/, Easel/ (upstream) are excluded.
    Files in 01-Experiments/ and 02-Runtime/ are pending archive (M0 Commit 7).
    docs/AUDIT-REPORT.md and research/README.md legitimately document 0.1.1
    as historical fact and are excluded.
    """
    failures = []
    # Files that legitimately reference 0.1.1 as documented history
    historical_context_files = {
        "docs/AUDIT-REPORT.md",
        "research/README.md",
    }
    # Directories that are pending archive (stale refs are expected, M0 Commit 7)
    pending_archive_dirs = {"01-Experiments", "02-Runtime"}

    md_files = _scan_markdown_files()
    for f in md_files:
        parts = f.relative_to(ROOT).parts
        if "archive" in parts:
            continue  # historical, skip
        if any(ex in parts for ex in (".runtime", "Easel", ".venv")):
            continue  # upstream, skip
        if parts[0] in pending_archive_dirs:
            continue  # pending archive in Commit 7, skip for now
        # Normalize to forward slashes for consistent comparison
        rel = "/".join(parts)
        if rel in historical_context_files:
            continue  # explicitly documented history, not stale
        text = f.read_text(encoding="utf-8")
        if re.search(r'\b0\.1\.1\b', text) and "Easel" in text:
            failures.append(f"STALE VERSION: {rel} references Easel 0.1.1")
    return failures


def check_lock_consistency():
    """Check Easel version in lock file matches CURRENT-STATE."""
    failures = []
    lock_path = ROOT / "runtime" / "easel.lock.json"
    if not lock_path.exists():
        failures.append("MISSING: runtime/easel.lock.json")
        return failures

    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_version = lock.get("tag", "")
    lock_commit = lock.get("commit", "")[:12]

    current_state = ROOT / "docs" / "CURRENT-STATE.md"
    if current_state.exists():
        text = current_state.read_text(encoding="utf-8")
        if lock_version and lock_version not in text:
            failures.append(
                f"VERSION MISMATCH: lock file says {lock_version} "
                f"but CURRENT-STATE.md doesn't mention it"
            )
        if lock_commit and lock_commit not in text:
            failures.append(
                f"COMMIT MISMATCH: lock file says {lock_commit}... "
                f"but CURRENT-STATE.md doesn't mention it"
            )
    return failures


def check_sensitive_strings():
    """Check for sensitive patterns in files that would be committed."""
    failures = []
    # Get tracked files
    import subprocess
    r = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode != 0:
        return ["ERROR: could not list git-tracked files"]

    tracked = [line.strip() for line in r.stdout.splitlines() if line.strip()]
    for rel in tracked:
        path = ROOT / rel
        # Skip non-text files
        if path.suffix not in (".md", ".py", ".yaml", ".yml", ".json", ".txt",
                               ".sh", ".ps1", ".example", ".gitignore"):
            continue
        # Skip files in excluded directories
        parts = rel.split("/")
        if any(ex in parts for ex in EXCLUDE_DIRS):
            continue
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pattern, rule in SENSITIVE_PATTERNS:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                line_num = text[:m.start()].count("\n") + 1
                failures.append(
                    f"SENSITIVE ({rule}): {rel}:{line_num} — "
                    f"(value redacted, pattern matched)"
                )
    return failures


def main():
    all_failures = []

    checks = [
        ("canonical_files", check_canonical_files),
        ("broken_links", check_broken_links),
        ("stale_version", check_stale_version),
        ("lock_consistency", check_lock_consistency),
        ("sensitive_strings", check_sensitive_strings),
    ]

    for name, fn in checks:
        failures = fn()
        if failures:
            print(f"\n[{name}] {'FAIL' if failures else 'PASS'}")
            for f in failures:
                print(f"  [FAIL] {f}")
            all_failures.extend(failures)
        else:
            print(f"[{name}] PASS")

    if all_failures:
        print(f"\n{len(all_failures)} check(s) failed")
        return 1
    print("\nAll documentation checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
