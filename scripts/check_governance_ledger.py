#!/usr/bin/env python3
"""Offline internal-consistency check for the governance ledger.

Verifies that the documented verification date and main SHA agree across:

  * ``docs/CURRENT-STATE.md`` (header + newest ``### Git`` snapshot)
  * ``docs/CURRENT-STATE.zh-CN.md`` (header + newest ``### Git`` snapshot)
  * ``config/governance/branch-registry.json`` (``verified_at`` date)

This catches the append-only drift recorded as E7 in
``docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md``: a fresh Git snapshot appended
while the header still names an older commit or date.

BOUNDARY: the check does NOT query GitHub, does NOT spawn a subprocess and does
NOT claim that the recorded SHA is the live remote head. It only proves that the
ledger agrees with itself. A green result is not evidence about remote state.

``--compare-head`` is a LOCAL, report-only convenience mode: it reads the
.git HEAD/refs files with plain Python (no git subprocess) and reports whether
the documented SHA matches the checked-out HEAD. It never changes the exit
code and must never be wired into CI as a gate — a PR checkout runs on a merge
commit, so a head comparison there would be permanently misleading.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EN_REL = "docs/CURRENT-STATE.md"
ZH_REL = "docs/CURRENT-STATE.zh-CN.md"
REGISTRY_REL = "config/governance/branch-registry.json"

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
SHA_RE = re.compile(r"`([0-9a-f]{7,40})`")
SECTION_RE = re.compile(r"^### Git[^\n]*?(\d{4}-\d{2}-\d{2})", re.M)
HEADER_EN_RE = re.compile(r"^>\s*Last verified:\s*(\d{4}-\d{2}-\d{2})", re.M)
HEADER_ZH_RE = re.compile(r"^>\s*最后验证：\s*(\d{4}-\d{2}-\d{2})", re.M)
NEXT_HEADING_RE = re.compile(r"^#{2,3} ", re.M)


def _header(text, pattern, label, errors):
    """Return (date, sha) from a 'Last verified' / '最后验证' header line."""
    m = pattern.search(text)
    if not m:
        errors.append("%s: missing verification header line" % label)
        return None, None
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.start())
    line = text[start:] if end == -1 else text[start:end]
    shas = SHA_RE.findall(line)
    if not shas:
        errors.append("%s: header line has no commit SHA" % label)
        return m.group(1), None
    return m.group(1), shas[0]


def _newest_git_block(text, label, errors):
    """Return (date, block) for the first '### Git ... <date>' section."""
    sections = list(SECTION_RE.finditer(text))
    if not sections:
        errors.append("%s: missing '### Git ... <date>' snapshot section" % label)
        return None, ""
    first = sections[0]
    following = NEXT_HEADING_RE.search(text, first.end())
    stop = following.start() if following else len(text)
    return first.group(1), text[first.end():stop]


def _branch_sha(block, marker, label, errors):
    """Extract the SHA from the Default-branch / 默认分支 table row."""
    for line in block.splitlines():
        if line.startswith("|") and marker in line:
            shas = SHA_RE.findall(line)
            if shas:
                return shas[0]
            errors.append("%s: branch row has no commit SHA" % label)
            return None
    errors.append("%s: newest Git snapshot has no '%s' row" % (label, marker))
    return None


def validate(root=ROOT):
    """Return a list of human-readable failures. Empty list means PASS."""
    root = Path(root)
    errors = []
    paths = {
        "EN": root / EN_REL,
        "ZH": root / ZH_REL,
        "registry": root / REGISTRY_REL,
    }
    for label, path in paths.items():
        if not path.exists():
            errors.append("%s: missing %s" % (label, path.name))
    if errors:
        return errors

    en = paths["EN"].read_text(encoding="utf-8")
    zh = paths["ZH"].read_text(encoding="utf-8")

    en_date, en_sha = _header(en, HEADER_EN_RE, "EN", errors)
    zh_date, zh_sha = _header(zh, HEADER_ZH_RE, "ZH", errors)
    en_sec_date, en_block = _newest_git_block(en, "EN", errors)
    zh_sec_date, zh_block = _newest_git_block(zh, "ZH", errors)

    if en_date and zh_date and en_date != zh_date:
        errors.append("verification date differs between EN (%s) and ZH (%s)" % (en_date, zh_date))
    if en_sha and zh_sha and en_sha != zh_sha:
        errors.append("header SHA differs between EN (%s) and ZH (%s)" % (en_sha, zh_sha))
    if en_date and en_sec_date and en_date != en_sec_date:
        errors.append("EN header date %s != newest Git snapshot date %s" % (en_date, en_sec_date))
    if zh_date and zh_sec_date and zh_date != zh_sec_date:
        errors.append("ZH header date %s != newest Git snapshot date %s" % (zh_date, zh_sec_date))

    en_branch_sha = _branch_sha(en_block, "Default branch", "EN", errors) if en_block else None
    zh_branch_sha = _branch_sha(zh_block, "默认分支", "ZH", errors) if zh_block else None
    if en_sha and en_branch_sha and en_sha != en_branch_sha:
        errors.append("EN header SHA %s != Default branch SHA %s" % (en_sha, en_branch_sha))
    if zh_sha and zh_branch_sha and zh_sha != zh_branch_sha:
        errors.append("ZH header SHA %s != 默认分支 SHA %s" % (zh_sha, zh_branch_sha))

    try:
        registry = json.loads(paths["registry"].read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append("registry: cannot parse JSON (%s)" % exc)
        return errors
    verified_at = str(registry.get("verified_at") or "")
    reg_date = DATE_RE.search(verified_at)
    if not reg_date:
        errors.append("registry: verified_at has no ISO date")
    elif en_date and reg_date.group(1) != en_date:
        errors.append("registry verified_at date %s != EN header date %s" % (reg_date.group(1), en_date))

    return errors


def summary(root=ROOT):
    """Return (date, sha) for the PASS message; never contacts the network."""
    root = Path(root)
    text = (root / EN_REL).read_text(encoding="utf-8")
    m = HEADER_EN_RE.search(text)
    if not m:
        return "unknown", "unknown"
    date = m.group(1)
    start = text.rfind("\n", 0, m.start()) + 1
    end = text.find("\n", m.start())
    line = text[start:] if end == -1 else text[start:end]
    shas = SHA_RE.findall(line)
    return date, (shas[0] if shas else "unknown")


def _head_sha(root):
    """Read the checked-out HEAD SHA from .git files. No subprocess, no network."""
    root = Path(root)
    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    if git_dir.is_file():  # linked worktree: 'gitdir: <path>' pointer
        try:
            pointer = git_dir.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if not pointer.startswith("gitdir:"):
            return None
        git_dir = Path(pointer.split(":", 1)[1].strip())
        if not git_dir.is_absolute():
            git_dir = (root / git_dir).resolve()
    head_file = git_dir / "HEAD"
    if not head_file.exists():
        return None
    try:
        head = head_file.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref: "):
        return head or None  # detached HEAD
    ref = head[5:].strip()
    ref_file = git_dir / ref
    if ref_file.exists():
        try:
            return ref_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None
    packed = git_dir / "packed-refs"
    if packed.exists():
        try:
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.startswith("#") or line.startswith("^"):
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
        except OSError:
            return None
    return None


def compare_head(root=ROOT):
    """Return (head_sha, ledger_sha, verdict). Report-only, never a failure."""
    root = Path(root)
    ledger_date, ledger_sha = summary(root)
    head = _head_sha(root)
    if not head:
        return None, ledger_sha, "unavailable (no readable .git HEAD)"
    if ledger_sha == "unknown":
        return head, ledger_sha, "unknown (ledger header has no SHA)"
    if head.startswith(ledger_sha) or ledger_sha.startswith(head):
        return head, ledger_sha, "in sync"
    return head, ledger_sha, "differs (ledger records the verification-time state; use git rev-list --count <sha>..HEAD for the distance)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT), help="repository root (for tests)")
    ap.add_argument("--compare-head", action="store_true",
                    help="LOCAL report-only: compare the ledger SHA with .git HEAD; never a CI gate")
    args = ap.parse_args()
    errors = validate(Path(args.root))
    if args.compare_head:
        head, ledger_sha, verdict = compare_head(Path(args.root))
        print("compare-head (local, report-only): HEAD=%s ledger=%s verdict=%s" % (
            head or "unavailable", ledger_sha, verdict))
    if errors:
        for e in errors:
            print("  [FAIL] %s" % e)
        print("governance-ledger FAIL: %d issue(s)" % len(errors))
        return 1
    date, sha = summary(Path(args.root))
    print("governance-ledger PASS: %s @ %s "
          "(offline internal consistency only; live GitHub state NOT verified)" % (date, sha))
    return 0


if __name__ == "__main__":
    sys.exit(main())
