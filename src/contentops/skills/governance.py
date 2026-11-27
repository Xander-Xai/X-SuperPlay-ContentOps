"""Skills Governance Audit: separate installed, parseable, declared, executable, and effective.

Root-cause finding (T01/T02):
The host machine carries >250 global skills across ``~/.agents/skills``,
``~/.claude/skills``, and Codex paths. On Codex CLI, this overflows the model
skills context budget (dropping ALL skill descriptions and 233 skills). Inside
ContentOps, only 4 capabilities were declared in ``runtime/skill-registry.json``
while 5 core ``x-superplay-*`` skills remained marked ``UNMERGED`` since
2026-11-04 and account DNAs referenced retired Easel v0.2.1 ``skills/openclaw/``
paths.

This module provides a deterministic, offline audit classifying every
content-relevant skill honestly without inventing runtime readiness or execution
authority.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

SCHEMA = "contentops.skill-governance-audit/v1"

#: Recommended ceiling for host-visible skills before agent CLIs strip descriptions.
SAFE_HOST_SKILL_BUDGET = 60

#: Known overlapping / conflicting skill clusters in shared host stores.
OVERLAP_CLUSTERS: Dict[str, Sequence[str]] = {
    "chinese_humanizer": ("shuorenhua", "humanizer-zh", "zh-writing-humanizer", "human-writing-skill"),
    "video_motion_engines": ("huashu-art-motion", "x-superplay-huashu-motion", "hyperframes", "video-shotcraft", "jacky-motion"),
    "copywriting": ("x-superplay-copy-orchestrator", "copywriting", "creator-style-copywriter", "self-media-platform-copywriting"),
    "visual_design": ("x-superplay-design-direction", "high-end-visual-design", "minimalist-ui", "canvas-design", "card-design"),
    "graphic_illustration": ("ian-xiaohei-illustrations", "ian-xiaohei-scenes", "imagegen-frontend-web"),
}

#: Core content-production skill roster with clear stage ownership.
CORE_ROSTER: Sequence[Dict[str, str]] = (
    {"id": "contentops-production-gates", "stage": "gates", "role": "Fail-closed VIDEO / GRAPHIC_TEXT preflight gates", "source": "repo"},
    {"id": "x-superplay-copy-orchestrator", "stage": "copy", "role": "Canonical evidence-bound topic copy & format derivatives", "source": "shared"},
    {"id": "x-superplay-source-research", "stage": "research", "role": "Rights-aware source candidate shortlist", "source": "shared"},
    {"id": "x-superplay-capture-plan", "stage": "capture", "role": "Per-beat cropped screen-recording contract (1024 only)", "source": "shared"},
    {"id": "x-superplay-broll-production", "stage": "assets", "role": "Evidence-first B-roll & material duty plan", "source": "shared"},
    {"id": "x-superplay-design-direction", "stage": "visual", "role": "Episode visual direction & anti-fatigue rules", "source": "shared"},
    {"id": "x-superplay-huashu-motion", "stage": "motion", "role": "Account-DNA local non-paid Huashu motion render adapter", "source": "repo"},
    {"id": "huashu-art-motion", "stage": "motion", "role": "Upstream Huashu Art Motion director/grammar/render skill", "source": "shared"},
    {"id": "media-use", "stage": "assets", "role": "Local-only BGM/SFX/image resolver (requires host runtime lock)", "source": "shared"},
    {"id": "contentops-remotion-clips", "stage": "motion", "role": "Pinned Remotion 4.0.543 clip templates (optional)", "source": "repo"},
    {"id": "shuorenhua", "stage": "polish", "role": "Chinese anti-AI-slop editorial pass (facts preserved)", "source": "shared"},
    {"id": "ian-xiaohei-illustrations", "stage": "illustration", "role": "Optional host-invoked shot/prompt skill for GRAPHIC_TEXT", "source": "shared"},
)


def _front_matter(text: str) -> Dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out: Dict[str, str] = {}
    key: Optional[str] = None
    for raw in text[3:end].splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line[:1] in (" ", "\t") and key:
            out[key] = f"{out[key]} {line.strip()}".strip()
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            key = k.strip()
            out[key] = v.strip().strip('"').strip("'")
    return out


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _check_skill_file(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {"installed": False, "parseable": False, "issues": ["SKILL_MD_MISSING"]}
    text = path.read_text(encoding="utf-8", errors="replace")
    meta = _front_matter(text)
    issues: List[str] = []
    if not text.startswith("---"):
        issues.append("MISSING_YAML_FRONTMATTER")
    if not meta.get("name"):
        issues.append("MISSING_NAME")
    if not meta.get("description"):
        issues.append("MISSING_DESCRIPTION")
    elif len(meta["description"]) < 25:
        issues.append("WEAK_DESCRIPTION_UNDERTRIGGER_RISK")
    if "feat/content-router" in text or "not on the default branch yet" in text:
        issues.append("STALE_UNMERGED_BANNER")
    return {
        "installed": True,
        "parseable": "MISSING_YAML_FRONTMATTER" not in issues and "MISSING_NAME" not in issues,
        "name": meta.get("name") or path.parent.name,
        "description_len": len(meta.get("description") or ""),
        "issues": issues,
    }


def audit_skills(root: Path, *, shared_root: Optional[Path] = None) -> Dict[str, Any]:
    """Run the full 9-state governance audit across repo + shared skill store."""
    root = Path(root).resolve()
    shared = Path(shared_root) if shared_root else (Path.home() / ".agents" / "skills")
    registry = _read_json(root / "runtime" / "skill-registry.json")
    declared = {row["id"]: row for row in registry.get("skills") or [] if isinstance(row, dict) and row.get("id")}
    status_doc = _read_json(root / "runtime" / "content-skill-status.json")
    status_by_id = {row["id"]: row for row in status_doc.get("skills") or [] if isinstance(row, dict) and row.get("id")}

    # Scan shared store for total count (context-budget overflow detection)
    shared_skills: List[str] = []
    unparseable_shared: List[str] = []
    if shared.is_dir():
        for skill_md in sorted(shared.glob("*/SKILL.md")):
            shared_skills.append(skill_md.parent.name)
            info = _check_skill_file(skill_md)
            if not info["parseable"]:
                unparseable_shared.append(skill_md.parent.name)

    roster_rows: List[Dict[str, Any]] = []
    for item in CORE_ROSTER:
        sid = item["id"]
        reg = declared.get(sid)
        st = status_by_id.get(sid)
        if item["source"] == "repo":
            if reg and (reg.get("discovery") or {}).get("root") == "repo":
                skill_md = root / reg["discovery"]["dir"] / "SKILL.md"
            else:
                skill_md = root / "skills" / sid / "SKILL.md"
        else:
            skill_md = shared / sid / "SKILL.md"

        file_info = _check_skill_file(skill_md)
        has_canonical = bool(reg and (root / str(reg.get("canonical_path") or "")).is_file())
        if reg and has_canonical:
            governance_state = "DECLARED_EXECUTABLE"
        elif file_info["installed"] and st and st.get("references"):
            governance_state = "ADVISORY_WITH_UNMERGED_REFS"
        elif file_info["installed"]:
            governance_state = "INSTALLED_ADVISORY_ONLY"
        else:
            governance_state = "NOT_INSTALLED"

        roster_rows.append({
            "id": sid,
            "stage": item["stage"],
            "role": item["role"],
            "source": item["source"],
            "installed": file_info["installed"],
            "parseable": file_info["parseable"],
            "declared_in_registry": bool(reg),
            "canonical_adapter_present": has_canonical,
            "governance_state": governance_state,
            "issues": file_info["issues"],
            "path": str(skill_md) if file_info["installed"] else None,
        })

    # Detect active overlap clusters in shared store
    overlaps: List[Dict[str, Any]] = []
    shared_set = set(shared_skills)
    for cluster, names in OVERLAP_CLUSTERS.items():
        present = [n for n in names if n in shared_set or (root / "skills" / n / "SKILL.md").is_file()]
        if len(present) > 1:
            overlaps.append({
                "cluster": cluster,
                "present_skills": present,
                "recommendation": f"Use ContentOps progressive Context Pack to pin one primary owner per stage instead of exposing all {len(present)} simultaneously.",
            })

    # Check account DNA stale openclaw paths
    stale_dna_paths: List[Dict[str, str]] = []
    for dna_path in sorted((root / "config" / "accounts").glob("*.json")):
        dna = _read_json(dna_path)
        for step in dna.get("skill_route") or []:
            script = str(step.get("script") or "")
            if script.startswith("skills/openclaw/"):
                stale_dna_paths.append({
                    "account": dna_path.name,
                    "step": str(step.get("step") or ""),
                    "script": script,
                    "note": "Legacy Easel v0.2.1 openclaw path (Easel v0.3.0 uses skills/builtin/; resolved via skill_paths.resolve_skill_dir)",
                })

    budget_overflow = len(shared_skills) > SAFE_HOST_SKILL_BUDGET
    return {
        "schema": SCHEMA,
        "host_store": {
            "path": str(shared),
            "present": shared.is_dir(),
            "installed_count": len(shared_skills),
            "safe_budget": SAFE_HOST_SKILL_BUDGET,
            "budget_overflow_risk": budget_overflow,
            "budget_warning": (
                f"{len(shared_skills)} shared skills exceed safe agent prompt budget ({SAFE_HOST_SKILL_BUDGET}); "
                "Codex strips all skill descriptions when overloaded. Use `python scripts/make_content.py context` "
                "for progressive task-scoped skill loading."
                if budget_overflow else None
            ),
            "unparseable_skills": unparseable_shared,
        },
        "summary": {
            "declared_capabilities": len(declared),
            "core_roster_count": len(roster_rows),
            "installed_core": sum(1 for r in roster_rows if r["installed"]),
            "executable_core": sum(1 for r in roster_rows if r["governance_state"] == "DECLARED_EXECUTABLE"),
            "overlap_clusters": len(overlaps),
            "stale_dna_openclaw_refs": len(stale_dna_paths),
        },
        "core_roster": roster_rows,
        "overlap_clusters": overlaps,
        "stale_dna_paths": stale_dna_paths,
        "execution_authorized": False,
    }
