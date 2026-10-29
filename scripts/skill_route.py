#!/usr/bin/env python3
"""Route a deliverable to the project's own Easel skills.

Why this exists
---------------
The Easel checkout is a skill library, not just ``auto-short-video/assemble.py``.
A compositor call is the last step of a production decision, not the decision
itself. This helper makes the routing step one command, so "which skill owns
this deliverable?" is answered before any code or ffmpeg filter chain is
written.

It reads front matter only -- no dependency, no network, no provider call.

Usage
-----
```
python scripts/skill_route.py --match "vertical evidence explainer with narration"
python scripts/skill_route.py --list
python scripts/skill_route.py --list --json
```

Catalog resolution: the pinned runtime first (``.runtime/easel/skills/openclaw``),
then the working checkout (``Easel/skills/openclaw``). Both are gitignored, so
the helper reports a clear error rather than an empty success when neither is
present.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

CATALOG_ROOTS: Tuple[Path, ...] = (
    ROOT / ".runtime" / "easel" / "skills" / "openclaw",
    ROOT / "Easel" / "skills" / "openclaw",
)

#: Skills installed in the agent shared store. They are not Easel skills and do
#: not live under a catalog root, so they need their own declared base. The
#: store is the single authoritative copy; host directories only link to it.
SHARED_SKILL_ROOT: Path = Path(
    os.environ.get("AGENT_SHARED_SKILLS", str(Path.home() / ".agents" / "skills"))
)

#: The routing rule that this helper implements. The policy test asserts it is
#: present in both agent instruction files.
RULE_MARKER = "Skill-First Routing"


def _front_matter(text: str) -> Dict[str, str]:
    """Minimal YAML front matter reader for the fields this helper needs."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data: Dict[str, str] = {}
    key: Optional[str] = None
    for raw in text[3:end].splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line[:1] in (" ", "\t") and key:
            data[key] = f"{data[key]} {line.strip()}".strip()
            continue
        if ":" in line:
            name, _, value = line.partition(":")
            key = name.strip()
            data[key] = value.strip().strip('"').strip("'")
    return data


def catalog() -> Tuple[List[Dict[str, Any]], Optional[Path]]:
    """Every skill under the first catalog root that exists."""
    root = next((candidate for candidate in CATALOG_ROOTS if candidate.is_dir()), None)
    if root is None:
        return [], None
    skills: List[Dict[str, Any]] = []
    for skill_md in sorted(root.glob("*/SKILL.md")):
        text = skill_md.read_text(encoding="utf-8", errors="replace")
        meta = _front_matter(text)
        skills.append({
            "name": meta.get("name") or skill_md.parent.name,
            "layer": meta.get("layer", ""),
            "description": meta.get("description", ""),
            "path": skill_md.relative_to(ROOT).as_posix(),
        })
    return skills, root


def shared_skill(name: str) -> Optional[Path]:
    """The shared-store directory for ``name``, if it ships a SKILL.md."""
    candidate = SHARED_SKILL_ROOT / name
    return candidate if (candidate / "SKILL.md").is_file() else None


def shared_catalog() -> List[Dict[str, Any]]:
    """Every skill in the shared store, in name order.

    Read-only and dependency-free. It exists so the DNA checker and the router
    can name shared skills without treating the store as an Easel catalog.
    """
    if not SHARED_SKILL_ROOT.is_dir():
        return []
    skills: List[Dict[str, Any]] = []
    for skill_md in sorted(SHARED_SKILL_ROOT.glob("*/SKILL.md")):
        meta = _front_matter(skill_md.read_text(encoding="utf-8", errors="replace"))
        skills.append({
            "name": meta.get("name") or skill_md.parent.name,
            "description": meta.get("description", ""),
            "path": str(skill_md.parent),
        })
    return skills


def rank(skills: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """Keyword overlap against name + description, with name hits weighted 3x."""
    terms = [term for term in re.split(r"[\s,，/、]+", query.lower()) if term]
    if not terms:
        return []
    scored = []
    for skill in skills:
        name = skill["name"].lower()
        body = skill["description"].lower()
        score = sum(3 * name.count(term) + body.count(term) for term in terms)
        if score:
            scored.append((score, skill))
    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    return [skill for _, skill in scored]


def _display(path: Path) -> str:
    """Repo-relative when possible; a configured root may live elsewhere."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="list every skill")
    parser.add_argument("--match", default="", help="rank skills for a deliverable")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    skills, root = catalog()
    shared = shared_catalog()
    if root is None:
        shared_hits = rank(shared, args.match)[: args.limit] if args.match else []
        if shared_hits:
            # A clean checkout has no Easel runtime (it is gitignored). The
            # shared store is still real, so routing must not pretend otherwise.
            print(
                "no Easel skill catalog found ("
                + ", ".join(_display(path) for path in CATALOG_ROOTS)
                + "); routing against the shared store only",
                file=sys.stderr,
            )
            print(f"shared store: {SHARED_SKILL_ROOT} ({len(shared)} skills)")
            for skill in shared_hits:
                print(f"  [shared] {skill['name']}")
                if skill["description"]:
                    print(f"      {skill['description'][:160]}")
                print(f"      {skill['path']}")
            return 0
        print(
            "no Easel skill catalog found. Expected one of: "
            + ", ".join(_display(path) for path in CATALOG_ROOTS),
            file=sys.stderr,
        )
        return 2

    selected = rank(skills, args.match)[: args.limit] if args.match else skills
    # The shared store is not an Easel catalog and is ranked separately, so the
    # catalog answer keeps its meaning while a project skill still shows up.
    shared_hits = rank(shared, args.match)[: args.limit] if args.match else []
    if args.match and not selected and not shared_hits:
        print(
            f"no skill matches {args.match!r}. Read the catalog with --list and "
            "state explicitly that no skill owns the deliverable before coding.",
            file=sys.stderr,
        )

    if args.json:
        payload = {
            "catalog": _display(root),
            "skills": selected,
            "shared_root": str(SHARED_SKILL_ROOT),
            "shared": shared_hits,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"catalog: {_display(root)} ({len(skills)} skills)")
    for skill in selected:
        layer = f"[{skill['layer']}] " if skill["layer"] else ""
        print(f"  {layer}{skill['name']}")
        if skill["description"]:
            print(f"      {skill['description'][:160]}")
        print(f"      {skill['path']}")
    if shared_hits:
        print(f"\nshared store: {SHARED_SKILL_ROOT} ({len(shared)} skills)")
        for skill in shared_hits:
            print(f"  [shared] {skill['name']}")
            if skill["description"]:
                print(f"      {skill['description'][:160]}")
            print(f"      {skill['path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
