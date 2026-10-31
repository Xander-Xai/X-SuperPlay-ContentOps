#!/usr/bin/env python3
"""Route a deliverable to the project's own skills.

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
python scripts/skill_route.py --sources
```

Catalog resolution, in priority order: the pinned Easel runtime
(``.runtime/easel/skills/openclaw``), the working Easel checkout
(``Easel/skills/openclaw``), then the vendored 公众号 track
(``vendor/gzh-thinktank/.../skills``). A name that appears in more than one root
is indexed once, from the earliest root. Every root is gitignored or vendored,
so the helper reports a clear error rather than an empty success when none is
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
    ROOT / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills",
)

#: Read order is priority order: the pinned runtime shadows the working
#: checkout, and both shadow a vendored track, so a name is indexed once.
CATALOG_LABELS: Dict[str, str] = {
    ".runtime": "easel-pinned",
    "Easel": "easel-checkout",
    "gzh_未来智能": "gzh",
}

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


def _catalog_label(root: Path) -> str:
    for part in root.parts:
        if part in CATALOG_LABELS:
            return CATALOG_LABELS[part]
    return root.name


def catalog_sources() -> List[Dict[str, Any]]:
    """Every declared project catalog root, present or not.

    Read-only. It exists so the router can say *where* a skill came from and so
    an absent track (a clean checkout has neither Easel nor the gzh vendor) is
    reported honestly instead of silently contributing zero skills.
    """
    return [
        {
            "label": _catalog_label(root),
            "path": _display(root),
            "exists": root.is_dir(),
            "skills": len(list(root.glob("*/SKILL.md"))) if root.is_dir() else 0,
        }
        for root in CATALOG_ROOTS
    ]


def catalog() -> Tuple[List[Dict[str, Any]], Optional[Path]]:
    """Every skill across the declared catalog roots, deduplicated by name.

    Roots are read in declared order, so the pinned runtime shadows the working
    checkout and both shadow a vendored track. The second return value is the
    first root that exists, kept for callers that only need a display path.
    """
    existing = [candidate for candidate in CATALOG_ROOTS if candidate.is_dir()]
    if not existing:
        return [], None
    skills: List[Dict[str, Any]] = []
    by_name: Dict[str, Dict[str, Any]] = {}
    for root in existing:
        label = _catalog_label(root)
        for skill_md in sorted(root.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            meta = _front_matter(text)
            name = meta.get("name") or skill_md.parent.name
            if name in by_name:
                # A later root lost the name. Record it instead of dropping it
                # silently: a cross-track collision is a fact worth seeing.
                by_name[name].setdefault("shadowed", []).append({
                    "source": label,
                    "path": _display(skill_md),
                })
                continue
            entry = {
                "name": name,
                "layer": meta.get("layer", ""),
                "description": meta.get("description", ""),
                "source": label,
                "path": _display(skill_md),
            }
            by_name[name] = entry
            skills.append(entry)
    return skills, existing[0]


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


def _all_skill_entries() -> List[Dict[str, Any]]:
    """Every skill on every root, including names shadowed by an earlier root."""
    entries: List[Dict[str, Any]] = []
    for root in CATALOG_ROOTS:
        if not root.is_dir():
            continue
        label = _catalog_label(root)
        for skill_md in sorted(root.glob("*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            meta = _front_matter(text)
            entries.append({
                "name": meta.get("name") or skill_md.parent.name,
                "dir_name": skill_md.parent.name,
                "description": meta.get("description", ""),
                "source": label,
                "path": _display(skill_md),
                "resolved": str(skill_md.resolve()),
                "root": str(root.resolve()),
                "meta": meta,
            })
    if SHARED_SKILL_ROOT.is_dir():
        for skill_md in sorted(SHARED_SKILL_ROOT.glob("*/SKILL.md")):
            meta = _front_matter(skill_md.read_text(encoding="utf-8", errors="replace"))
            entries.append({
                "name": meta.get("name") or skill_md.parent.name,
                "dir_name": skill_md.parent.name,
                "description": meta.get("description", ""),
                "source": "shared",
                "path": str(skill_md.parent),
                "resolved": str(skill_md.resolve()),
                "root": str(SHARED_SKILL_ROOT.resolve()),
                "meta": meta,
            })
    return entries



def _archived_entries() -> List[Dict[str, Any]]:
    """Archived skills under ``_archive/`` are provenance, never dispatchable."""
    entries: List[Dict[str, Any]] = []
    for root in CATALOG_ROOTS:
        if not root.is_dir():
            continue
        label = _catalog_label(root)
        for skill_md in sorted(root.glob("_archive/*/SKILL.md")):
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            meta = _front_matter(text)
            entries.append({
                "name": meta.get("name") or skill_md.parent.name,
                "dir_name": skill_md.parent.name,
                "description": meta.get("description", ""),
                "source": label,
                "path": _display(skill_md),
                "resolved": str(skill_md.resolve()),
                "root": str(root.resolve()),
                "meta": meta,
                "text": text,
            })
    return entries


def _license_status(entry: Dict[str, Any]) -> Tuple[str, str, Optional[str]]:
    """(status, declared licence, licence file) for one skill.

    ``restricted`` means a copyleft/proprietary licence is present. ``declared``
    means a licence string exists. ``declared_file`` means only a LICENSE file
    exists. ``unknown`` means no evidence. None of these authorizes execution.
    """
    meta = entry["meta"]
    declared = str(meta.get("license") or meta.get("licence") or "").strip()
    parent = Path(entry["resolved"]).parent
    license_file = None
    for name in ("LICENSE", "LICENSE.md", "COPYING"):
        candidate = parent / name
        if candidate.is_file():
            license_file = candidate
            break
    file_text = ""
    if license_file is not None:
        file_text = license_file.read_text(encoding="utf-8", errors="replace")[:800]
    lowered = f"{declared} {file_text}".casefold()
    if "agpl" in lowered or "gnu affero" in lowered or "gpl" in lowered:
        return "restricted", declared or "LICENSE file", str(license_file) if license_file else None
    if declared:
        return "declared", declared, str(license_file) if license_file else None
    if license_file is not None:
        return "declared_file", "LICENSE file", str(license_file)
    return "unknown", "", None


def _hints(text: str) -> Tuple[bool, bool]:
    credential = bool(re.search(
        r"(?i)(api[_-]?key|access[_-]?token|auth[_-]?token|secret|mcporter|"
        r"requires\s*:|bins\s*:|mcp)", text))
    paid = bool(re.search(r"(?i)(paid|subscription|billing|pricing|price|quota|credit pack)", text))
    return credential, paid

def resolve_skill(name: str) -> List[Dict[str, Any]]:
    """Every exact occurrence of ``name``, in catalog priority order.

    A directory name and the declared ``name`` are both accepted. Shadowed
    copies are returned too, so a caller can see the collision instead of
    believing there is only one copy.
    """
    needle = (name or "").strip()
    if not needle:
        return []
    return [
        entry for entry in _all_skill_entries()
        if entry["name"] == needle or entry["dir_name"] == needle
    ]


def doctor() -> Dict[str, Any]:
    """Structural health of the catalogs. Read-only; no skill is executed."""
    entries = _all_skill_entries()
    archived_entries = _archived_entries()
    rights_unknown: List[str] = []
    restricted: List[str] = []
    declared_licences: List[str] = []
    credential_hints: List[str] = []
    paid_hints: List[str] = []
    for entry in entries:
        status, licence, license_file = _license_status(entry)
        if status == "restricted":
            restricted.append(entry["name"])
        elif status in {"declared", "declared_file"}:
            declared_licences.append(entry["name"])
        else:
            rights_unknown.append(entry["name"])
        text = Path(entry["resolved"]).read_text(encoding="utf-8", errors="replace")
        credential, paid = _hints(text)
        if credential:
            credential_hints.append(entry["name"])
        if paid:
            paid_hints.append(entry["name"])
    by_name: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        by_name.setdefault(entry["name"], []).append(entry)
    duplicates = [
        {"name": name, "copies": [
            {"source": item["source"], "path": item["path"]} for item in copies
        ]}
        for name, copies in sorted(by_name.items()) if len(copies) > 1
    ]
    missing_description = [entry["name"] for entry in entries
                           if not entry["description"].strip()]
    missing_name = [entry["dir_name"] for entry in entries
                    if not entry["meta"].get("name")]
    permission_fields = ("allowed-tools", "permissions", "tools", "requires")
    with_permissions = [
        entry["name"] for entry in entries
        if any(field in entry["meta"] for field in permission_fields)
    ]
    allowed_roots = [str(ROOT.resolve())] + [str(item.resolve())
                                             for item in CATALOG_ROOTS
                                             if item.is_dir()]
    if SHARED_SKILL_ROOT.is_dir():
        allowed_roots.append(str(SHARED_SKILL_ROOT.resolve()))
    unsafe = []
    dangling = []
    for entry in entries:
        original = Path(entry["path"])
        if not original.is_absolute():
            original = ROOT / original
        # A shared-store skill is a link into a catalog root by design. Its
        # original path is inside the shared store even when the link target
        # belongs to another checkout's runtime; do not call that unsafe.
        # Compare lexically: resolving the link would leave the shared root.
        try:
            in_shared = original.is_relative_to(SHARED_SKILL_ROOT)
        except (OSError, ValueError):
            in_shared = False
        resolved = Path(entry["resolved"])
        if not resolved.exists():
            dangling.append(entry["path"])
            continue
        if in_shared:
            continue
        if not any(str(resolved).startswith(root + os.sep) for root in allowed_roots):
            unsafe.append(entry["path"])
    roots = catalog_sources()
    shared_present = SHARED_SKILL_ROOT.is_dir()
    ok = bool(entries) and not unsafe
    return {
        "schema": "contentops.skill-doctor/v1",
        "ok": ok,
        "roots": roots,
        "shared": {
            "path": str(SHARED_SKILL_ROOT),
            "exists": shared_present,
            "skills": len(shared_catalog()),
        },
        "total": len(entries),
        "duplicates": duplicates,
        "missing_description": missing_description,
        "missing_name": missing_name,
        "permission_declarations": {
            "declared": len(with_permissions),
            "total": len(entries),
            "names": with_permissions,
        },
        "unsafe_paths": unsafe,
        "dangling_links": dangling,
        "rights": {
            "declared": len(declared_licences),
            "declared_names": declared_licences,
            "unknown": rights_unknown,
            "restricted": restricted,
        },
        "archived": [entry["name"] for entry in archived_entries],
        "credential_hints": credential_hints,
        "paid_hints": paid_hints,
        "execution": {
            "authorized": False,
            "scope": "diagnosis_only",
            "remaining_gate": "#57",
            "reason": "directory discovery and diagnosis never authorize execution",
        },
        "warnings": [warning for warning in (
            "no catalog or shared skill was found" if not entries else "",
            "the shared skill store is absent on this checkout" if not shared_present else "",
        ) if warning],
    }


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
    parser.add_argument("--sources", action="store_true", help="list every catalog root")
    parser.add_argument("--doctor", action="store_true",
                        help="check catalog roots, duplicates, permissions and paths")
    parser.add_argument("--resolve", default="",
                        help="resolve one exact skill name to every copy")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    if args.doctor:
        report = doctor()
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            for item in report["roots"]:
                state = "ok" if item["exists"] else "absent"
                print(f"{item['label']:<16} {state:<7} {item['skills']:>3} skills  {item['path']}")
            print(f"{'shared':<16} {'ok' if report['shared']['exists'] else 'absent':<7} "
                  f"{report['shared']['skills']:>3} skills  {report['shared']['path']}")
            print(f"total            {report['total']}")
            print(f"duplicates       {len(report['duplicates'])}")
            for duplicate in report["duplicates"][:10]:
                sources = ", ".join(copy["source"] for copy in duplicate["copies"])
                print(f"  {duplicate['name']}: {sources}")
            print(f"no description   {len(report['missing_description'])}")
            print(f"no declared name {len(report['missing_name'])}")
            print(f"permissions      {report['permission_declarations']['declared']}"
                  f"/{report['permission_declarations']['total']} declare a permission field")
            print(f"unsafe paths     {len(report['unsafe_paths'])}")
            print(f"dangling links   {len(report['dangling_links'])}")
            print(f"rights declared  {report['rights']['declared']} declared, "
                  f"{len(report['rights']['unknown'])} unknown, "
                  f"{len(report['rights']['restricted'])} restricted")
            print(f"archived         {len(report['archived'])} (never dispatched)")
            print(f"credential hints {len(report['credential_hints'])}")
            print(f"paid hints       {len(report['paid_hints'])}")
            print("execution        NOT AUTHORIZED — diagnosis only; gate remains #57")
            print("DIAGNOSIS OK" if report["ok"] else "DIAGNOSIS FAILED")
        return 0 if report["ok"] else 1

    if args.resolve:
        found = resolve_skill(args.resolve)
        if args.json:
            print(json.dumps({"name": args.resolve, "copies": found}, indent=2,
                             ensure_ascii=False))
        elif not found:
            print(f"no skill named {args.resolve!r}", file=sys.stderr)
        else:
            for item in found:
                print(f"[{item['source']}] {item['name']}  {item['path']}")
        return 0 if found else 2

    if args.sources:
        sources = catalog_sources()
        if args.json:
            print(json.dumps(sources, indent=2, ensure_ascii=False))
            return 0
        for item in sources:
            state = "ok" if item["exists"] else "absent"
            print(f"{item['label']:<16} {state:<7} {item['skills']:>3} skills  {item['path']}")
        return 0

    skills, root = catalog()
    shared = shared_catalog()
    if root is None:
        shared_hits = rank(shared, args.match)[: args.limit] if args.match else []
        if shared_hits:
            # A clean checkout has no project catalog (both are gitignored or
            # vendored). The shared store is still real, so routing must not
            # pretend otherwise.
            print(
                "no project skill catalog found ("
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
            "no project skill catalog found. Expected one of: "
            + ", ".join(_display(path) for path in CATALOG_ROOTS),
            file=sys.stderr,
        )
        return 2

    selected = rank(skills, args.match)[: args.limit] if args.match else skills
    # The shared store is not a project catalog and is ranked separately, so the
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
            "catalogs": catalog_sources(),
            "skills": selected,
            "shared_root": str(SHARED_SKILL_ROOT),
            "shared": shared_hits,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"catalog: {len(skills)} skills from {', '.join(item['label'] for item in catalog_sources() if item['exists'])}")
    for skill in selected:
        layer = f"[{skill['layer']}] " if skill["layer"] else ""
        print(f"  {layer}{skill['name']}  ({skill.get('source', '')})")
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
