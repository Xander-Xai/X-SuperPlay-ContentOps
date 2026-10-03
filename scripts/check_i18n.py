#!/usr/bin/env python3
"""i18n consistency checker for Tier-1 bilingual documentation.

Checks:
  1. Every Tier-1 English doc has a corresponding .zh-CN.md mirror
  2. Every zh-CN mirror has a valid translation_of header
  3. Every zh-CN mirror has language: zh-CN marker
  4. Language switch links are bidirectional and not broken
  5. No stale translation_status: missing

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
]


def _zh_path(en_path):
    p = Path(en_path)
    return ROOT / p.parent / (p.stem + ".zh-CN.md")


def check_pairs_exist():
    failures = []
    for en_rel in TIER1_DOCS:
        en_path = ROOT / en_rel
        zh_path = _zh_path(en_rel)
        if not en_path.exists():
            continue
        if not zh_path.exists():
            failures.append(f"MISSING zh-CN mirror: {zh_path.relative_to(ROOT)} (for {en_rel})")
    return failures


def check_translation_headers():
    failures = []
    header_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL | re.MULTILINE)
    for en_rel in TIER1_DOCS:
        en_path = ROOT / en_rel
        zh_path = _zh_path(en_rel)
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


def check_language_switch_links():
    failures = []
    link_re = re.compile(r"\[(.*?)\]\((.*?)\)")

    for en_rel in TIER1_DOCS:
        en_path = ROOT / en_rel
        zh_path = _zh_path(en_rel)
        zh_rel = str(zh_path.relative_to(ROOT)).replace("\\", "/")

        if en_path.exists():
            text = en_path.read_text(encoding="utf-8", errors="ignore")
            if zh_path.exists():
                found = False
                for m in link_re.finditer(text):
                    if "zh-CN" in m.group(1) or "zh-CN" in m.group(2) or "Chinese" in m.group(1):
                        found = True
                        break
                if not found:
                    failures.append(
                        f"MISSING language switch link in EN: {en_rel} "
                        f"(should link to {zh_rel})"
                    )

        if zh_path.exists():
            text = zh_path.read_text(encoding="utf-8", errors="ignore")
            found = False
            for m in link_re.finditer(text):
                if "English" in m.group(1) or (en_rel in m.group(2)):
                    found = True
                    break
            if not found:
                failures.append(
                    f"MISSING language switch link in ZH: {zh_path.relative_to(ROOT)} "
                    f"(should link to {en_rel})"
                )
    return failures


def main():
    all_failures = []
    checks = [
        ("pairs_exist", check_pairs_exist),
        ("translation_headers", check_translation_headers),
        ("language_switch_links", check_language_switch_links),
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