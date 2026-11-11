#!/usr/bin/env python3
"""i18n consistency checker for Tier-1 bilingual documentation.

Checks:
  1. Every Tier-1 doc has its mirror in the declared direction
  2. Every zh-CN mirror has a valid translation_of header
  3. Every zh-CN mirror has language: zh-CN marker
  4. Language switch links are bidirectional and not broken
  5. No stale translation_status: missing
  6. No C0 control characters (except LF/CR/TAB) in zh-CN mirrors

Direction
---------
Tier-1 docs are English-primary by default: the canonical file is the English
original and ``<stem>.zh-CN.md`` is its translation. README is the declared
exception (2026-11-12): this repository's audience is Chinese-first, so
``README.md`` is the Chinese original and ``README.en.md`` is the English
mirror. The pair is still machine-checked -- existence, a bidirectional language
switch, and the absence of a stale second Chinese copy -- just in the other
direction. No front matter is required on a primary-language landing page,
because GitHub renders YAML front matter as a table at the top of the page.

Exit 0 = pass, exit 1 = fail.
Machine checks structural synchronization only, not translation quality.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TIER1_DOCS = [
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "docs/INDEX.md",
    "docs/CURRENT-STATE.md",
    "docs/ARCHITECTURE.md",
    "docs/PRD.md",
    "docs/RUNBOOK.md",
    "docs/QUALITY-STANDARD.md",
    "docs/DEVELOPMENT-STANDARD.md",
    "docs/FILE-PLACEMENT-POLICY.md",
    "docs/DEVELOPMENT-PLAN.md",
    "docs/TEST-PLAN.md",
    "docs/UPSTREAM-EASEL.md",
    "docs/GLOSSARY.md",
    "docs/PLATFORM-INTEGRATION-STATUS.md",
    "docs/DOC-SYNC.md",
]

# Docs whose canonical file is the Chinese original. Value = the English mirror.
# Everything else is English-primary with a `.zh-CN.md` mirror.
ZH_PRIMARY_DOCS = {
    "README.md": "README.en.md",
}

# Chinese copies that must not come back once a doc is Chinese-primary: a second
# Chinese file is exactly how two landing pages drift apart.
STALE_ZH_MIRRORS = {
    "README.md": "README.zh-CN.md",
}


def _mirror_rel(en_rel):
    """Return the repo-relative path of a doc's mirror."""
    if en_rel in ZH_PRIMARY_DOCS:
        return ZH_PRIMARY_DOCS[en_rel]
    p = Path(en_rel)
    return str(p.parent / (p.stem + ".zh-CN.md")).replace("\\", "/")


def _mirror_path(en_rel):
    return ROOT / _mirror_rel(en_rel)


def check_pairs_exist():
    failures = []
    for en_rel in TIER1_DOCS:
        en_path = ROOT / en_rel
        mirror = _mirror_path(en_rel)
        if not en_path.exists():
            continue
        if not mirror.exists():
            failures.append(
                f"MISSING mirror: {mirror.relative_to(ROOT)} (for {en_rel})"
            )
        stale_rel = STALE_ZH_MIRRORS.get(en_rel)
        if stale_rel and (ROOT / stale_rel).exists():
            failures.append(
                f"STALE second Chinese copy: {stale_rel} — {en_rel} is "
                f"Chinese-primary, its English mirror is {_mirror_rel(en_rel)}"
            )
    return failures


def check_translation_headers():
    """Check zh-CN mirrors have translation_of / language front matter.

    A Chinese-primary doc has no mirror to check here: the English mirror is the
    translation, and requiring YAML front matter on a landing page would print a
    table above the title on GitHub.
    """
    failures = []
    header_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL | re.MULTILINE)
    for en_rel in TIER1_DOCS:
        if en_rel in ZH_PRIMARY_DOCS:
            continue
        zh_path = _mirror_path(en_rel)
        if not zh_path.exists():
            continue
        text = zh_path.read_text(encoding="utf-8", errors="ignore")
        m = header_re.match(text)
        if not m:
            failures.append(f"MISSING YAML front matter: {zh_path.relative_to(ROOT)}")
            continue
        front = m.group(1)
        if "translation_of:" not in front:
            failures.append(f"MISSING translation_of: {zh_path.relative_to(ROOT)}")
        else:
            to_match = re.search(r"translation_of:\s*(\S+)", front)
            if to_match:
                stated = to_match.group(1).strip('"')
                if stated != en_rel:
                    failures.append(
                        f"WRONG translation_of: {zh_path.relative_to(ROOT)} "
                        f"says '{stated}', expected '{en_rel}'"
                    )
        if "language:" not in front:
            failures.append(f"MISSING language marker: {zh_path.relative_to(ROOT)}")
        else:
            lang_match = re.search(r"language:\s*(\S+)", front)
            if lang_match and lang_match.group(1).strip() != "zh-CN":
                failures.append(
                    f"WRONG language: {zh_path.relative_to(ROOT)} "
                    f"says '{lang_match.group(1)}', expected 'zh-CN'"
                )
    return failures


def _links(text):
    return re.findall(r"\[(.*?)\]\((.*?)\)", text)


def _links_to(text, target_rel, labels=()):
    for label, url in _links(text):
        if url.strip() == target_rel:
            return True
        if any(token in label for token in labels):
            return True
    return False


def check_language_switch_links():
    failures = []
    for en_rel in TIER1_DOCS:
        en_path = ROOT / en_rel
        mirror_file = _mirror_path(en_rel)
        mirror_rel = _mirror_rel(en_rel)

        if en_rel in ZH_PRIMARY_DOCS:
            # Chinese original -> English mirror, and back.
            if en_path.exists():
                text = en_path.read_text(encoding="utf-8", errors="ignore")
                if not _links_to(text, mirror_rel, ("English",)):
                    failures.append(
                        f"MISSING language switch link in {en_rel} "
                        f"(should link to {mirror_rel})"
                    )
            if mirror_file.exists():
                text = mirror_file.read_text(encoding="utf-8", errors="ignore")
                if not _links_to(text, en_rel, ("简体中文", "中文")):
                    failures.append(
                        f"MISSING language switch link in {mirror_rel} "
                        f"(should link to {en_rel})"
                    )
            continue

        if en_path.exists():
            text = en_path.read_text(encoding="utf-8", errors="ignore")
            if mirror_file.exists():
                found = False
                for label, url in _links(text):
                    if "zh-CN" in label or "zh-CN" in url or "Chinese" in label:
                        found = True
                        break
                if not found:
                    failures.append(
                        f"MISSING language switch link in EN: {en_rel} "
                        f"(should link to {mirror_rel})"
                    )

        if mirror_file.exists():
            text = mirror_file.read_text(encoding="utf-8", errors="ignore")
            found = False
            for label, url in _links(text):
                if "English" in label or (en_rel in url):
                    found = True
                    break
            if not found:
                failures.append(
                    f"MISSING language switch link in ZH: {mirror_file.relative_to(ROOT)} "
                    f"(should link to {en_rel})"
                )
    return failures


def check_translation_status():
    """Check zh-CN mirrors have translation_status: synced in front matter."""
    failures = []
    header_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL | re.MULTILINE)
    for en_rel in TIER1_DOCS:
        if en_rel in ZH_PRIMARY_DOCS:
            continue
        zh_path = _mirror_path(en_rel)
        if not zh_path.exists():
            continue
        text = zh_path.read_text(encoding="utf-8", errors="ignore")
        m = header_re.match(text)
        if not m:
            continue
        front = m.group(1)
        if "translation_status:" not in front:
            failures.append(f"MISSING translation_status: {zh_path.relative_to(ROOT)}")
        else:
            ts_match = re.search(r"translation_status:\s*(\S+)", front)
            if ts_match:
                val = ts_match.group(1).strip('"')
                if val != "synced":
                    failures.append(
                        f"STALE translation_status: {zh_path.relative_to(ROOT)} "
                        f"is '{val}', expected 'synced'"
                    )
    return failures


def check_no_c0_control_chars():
    """Check zh-CN mirrors contain no C0 control characters (except LF/CR/TAB).

    Forbidden: U+0000-U+0008, U+000B, U+000C, U+000E-U+001F, U+007F
    Allowed:    U+0009 (TAB), U+000A (LF), U+000D (CR)
    """
    failures = []
    # C0 chars minus allowed LF/CR/TAB
    FORBIDDEN = (
        set(range(0x00, 0x09))   # NUL-ACK
        | {0x0B}                  # VT (vertical tab)
        | {0x0C}                  # FF (form feed)
        | set(range(0x0E, 0x20))  # SO-US
        | {0x7F}                  # DEL
    )

    for en_rel in TIER1_DOCS:
        zh_path = _mirror_path(en_rel)
        if not zh_path.exists():
            continue
        try:
            data = zh_path.read_bytes()
        except Exception:
            continue
        for i, b in enumerate(data):
            if b in FORBIDDEN:
                line_num = data[:i].count(b"\n") + 1
                col = i - max(0, data.rfind(b"\n", 0, i))
                failures.append(
                    f"C0 CONTROL CHAR (0x{b:02x}): {zh_path.relative_to(ROOT)} "
                    f"line {line_num}, col {col}"
                )
                break  # one report per file
    return failures


def main():
    all_failures = []
    checks = [
        ("pairs_exist", check_pairs_exist),
        ("translation_headers", check_translation_headers),
        ("language_switch_links", check_language_switch_links),
        ("translation_status", check_translation_status),
        ("no_c0_chars", check_no_c0_control_chars),
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
        print(f"\n{len(all_failures)} i18n check(s) failed")
        return 1
    print("\nAll i18n consistency checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
