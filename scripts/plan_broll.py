#!/usr/bin/env python3
"""Materialize a B-roll shot plan from registered real media + spoken lines.

This is the *mechanism* that stops a video project from degrading into a deck of
static text cards. It reads what the project already owns -- registered stills
(real screenshots, generated illustrations) and the measured narration -- and
writes an explicit, materialized ``motion.shot_plan`` in which every spoken line
gets a visual whose duration is derived from the real audio, not from a guess.

Usage:
    python scripts/plan_broll.py <project> [--json] [--dry-run]

Preconditions (all fail closed, no silent degradation):
  * ``script/script.json`` and ``receipts/narration.json`` exist
  * ``sources/assets.json`` registers at least one usable still
  * each narration line carries a ``line_id`` matching a script line id
  * the account is a VIDEO account with a declared render_variant

What it writes (only when not --dry-run):
  * ``motion/broll/<line-id>.json`` -- one clip spec per line
  * ``motion/broll-plan.json``      -- schema contentops.m5-motion-shots/v1
  * ``project.yaml``                -- motion.shot_plan + motion.backend: remotion

It never renders, never approves copy, and never grants publication. A shot
whose line has no truthful visual is routed to an information graphic, never to
unrelated footage. Generated imagery is marked editorial, never evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

BLOCKED_EXIT = 4
PLAN_SCHEMA = "contentops.m5-motion-shots/v1"
MIN_CLIP_S = 2.0
MAX_CLIP_S = 8.0

# Visual kinds that may carry a real still as the main picture.
STILL_TYPES = {"REAL_SCREENSHOT", "GENERATED_IMAGE"}
USABLE_PERMISSIONS = {"OWNED", "CREATED_BY_OWNER", "LICENSED"}

# Camera moves rotate by line index; the variation is deliberate (no two
# adjacent shots share the same in-frame motion).
MOVES: Tuple[str, ...] = ("push", "pan-left", "pull", "pan-right")

# A line is routed to an evidence shot when a still is bound to it AND the
# spoken text is about something showable (interface, document, named artifact,
# or a concrete check). Abstract/opinion lines get an information graphic.
EVIDENCE_HINTS = (
    "readme", "文档", "截图", "界面", "项目", "运行", "http", "repo", "git",
    "框架", "工具", "路线", "评测", "案例", "指南", "说明", "边界", "trace",
    "rag", "agent", "agentguide", "仓库", "代码", "面板", "数据",
)
INFO_HINTS = (
    "我认为", "建议", "观点", "不代表", "不是", "而是", "希望大家", "谢谢",
)


class BrollPlanError(RuntimeError):
    """A fail-closed planning error."""


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise BrollPlanError(f"missing required file: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise BrollPlanError(f"invalid JSON at {path}: {exc}") from None
    if not isinstance(data, dict):
        raise BrollPlanError(f"expected an object at {path}")
    return data


def _usable_stills(project: Path) -> List[Dict[str, str]]:
    """Registered, rights-checked stills with a resolvable path inside the project."""
    doc = _load_json(project / "sources" / "assets.json")
    out: List[Dict[str, str]] = []
    for row in doc.get("assets") or []:
        if not isinstance(row, Mapping):
            continue
        kind = str(row.get("type") or "").upper()
        permission = str(row.get("permission") or "").upper()
        if kind not in STILL_TYPES or permission not in USABLE_PERMISSIONS:
            continue
        repo_path = str(row.get("repo_path") or "").strip()
        sha = str(row.get("sha256") or "").strip().lower()
        if not repo_path or len(sha) != 64:
            continue
        # repo_path is repo-root relative; strip the project prefix for the
        # per-project asset manifest, matching M5 registration conventions.
        project_prefix = project.as_posix().strip("/") + "/"
        rel = repo_path
        if rel.startswith(project_prefix):
            rel = rel[len(project_prefix):]
        full = (project / rel).resolve()
        try:
            full.relative_to(project.resolve())
        except ValueError:
            continue
        if not full.is_file():
            continue
        # Evidence grade is a rights fact, not just a media type. A locally
        # authored card registered as REAL_SCREENSHOT is still a mockup, never
        # a real captured artifact. Only a licensed/owned *capture* may carry
        # the "real project screen" label on screen.
        permission_upper = permission.upper()
        evidence_grade = "real" if (
            kind == "REAL_SCREENSHOT"
            and permission_upper in {"LICENSED", "OWNED"}
            and bool(str(row.get("license") or row.get("license_id") or "").startswith("CC"))
        ) else ("generated" if kind == "GENERATED_IMAGE" else "illustrative")
        # Illustrative cards are text-on-colour slide art, not B-roll pictures.
        # Including them as image candidates is what produced a deck of cards
        # in the first place, so they never enter the B-roll pool at all.
        if evidence_grade == "illustrative":
            continue
        out.append({"id": str(row.get("id") or ""), "path": rel, "sha256": sha,
                    "type": kind, "grade": evidence_grade})
    if not out:
        raise BrollPlanError(
            "no registered, rights-checked stills found; register real screenshots "
            "or generated illustrations in sources/assets.json first")
    return out


def _line_slot(narration: Mapping[str, Any]) -> Dict[str, Dict[str, float]]:
    slots: Dict[str, Dict[str, float]] = {}
    lines = narration.get("lines") or []
    for index, row in enumerate(lines):
        if not isinstance(row, Mapping):
            continue
        line_id = str(row.get("line_id") or "").strip()
        start = float(row.get("start") or 0.0)
        duration = float(row.get("duration") or 0.0)
        end = (float(lines[index + 1].get("start") or 0.0)
               if index + 1 < len(lines) and isinstance(lines[index + 1], Mapping)
               else start + duration)
        slots[line_id] = {"start": start, "duration": max(0.0, end - start)}
    return slots


def _route_kind(line: Mapping[str, Any], still: Optional[Mapping[str, Any]]) -> str:
    text = str(line.get("narration") or line.get("caption") or "").lower()
    if any(hint in text for hint in INFO_HINTS):
        return "info_graphic"
    if still is None:
        return "info_graphic"
    # A purely illustrative card can NEVER truthfully stand in for a real
    # screen, no matter how showable the line is. Routing it to evidence_shot
    # is exactly the "mockup presented as proof" defect. It always becomes an
    # information graphic instead.
    if still.get("grade") == "illustrative":
        return "info_graphic"
    if any(hint in text for hint in EVIDENCE_HINTS):
        return "evidence_shot"
    # A real capture or a generated illustration may carry the picture; both
    # are rights-checked and labelled by grade before they reach the screen.
    return "evidence_shot"


def _info_graphic_props(line: Mapping[str, Any]) -> Dict[str, Any]:
    segment = str(line.get("source_segment_id") or "").upper()
    text = str(line.get("narration") or line.get("caption") or "").strip()
    headline = text[:14]
    if "HOOK" in segment or "INTRO" in segment or "CTA" in segment:
        return {"kind": "quote", "eyebrow": "开场", "title": headline,
                "items": [text[:22]], "caption": "创作者观点 · 不是实测回执"}
    if any(h in text for h in ("对比", "而不是", "不是", "建议")):
        return {"kind": "compare", "eyebrow": "建议", "title": headline,
                "items": [text[:30], "围绕自己的项目验证"], "caption": "创作者建议"}
    if any(h in text for h in ("清单", "几件事", "第一", "第二")):
        return {"kind": "flow", "eyebrow": "检查项", "title": headline,
                "items": [text[:26]], "caption": "检查提纲示意"}
    return {"kind": "checklist", "eyebrow": "说明", "title": headline,
            "items": [text[:26]], "caption": "解释性示意"}


def _callout(line: Mapping[str, Any]) -> str:
    """A 2-6 char semantic keyword, never a duplicate of the burned subtitle.

    The subtitle already carries the full spoken sentence. Repeating it as a
    screen callout is the 'same sentence twice' defect -- the callout's job is
    a single anchor word the eye can land on while the ear hears the sentence.
    """
    text = str(line.get("narration") or line.get("caption") or "").strip()
    # Prefer an explicit visual_focus when the script supplies one.
    focus = str(line.get("visual_focus") or "").strip()
    if focus:
        return focus[:6]
    # Otherwise pick a short token from a small editorial vocabulary, matched
    # against the spoken text. This never asserts a fact not in the narration.
    keyword_map = (
        ("检验", ("检验", "检查", "几件事")),
        ("能不能跑", ("跑起来", "运行", "按说明")),
        ("能不能评测", ("评测", "量化", "案例")),
        ("能解释", ("解释", "失败", "trace", "追踪")),
        ("路线图", ("路线", "规划", "日程", "八周")),
        ("README", ("readme", "说明", "文档")),
        ("二次开发", ("二次开发", "harness", "评测类")),
        ("别照搬", ("不建议", "照搬", "重点")),
        ("边界", ("边界", "权限", "任务")),
        ("成本延迟", ("成本", "延迟", "复盘")),
        ("学Agent", ("agent", "学", "开发")),
    )
    lowered = text.lower()
    for keyword, hints in keyword_map:
        if any(hint.lower() in lowered for hint in hints):
            return keyword
    return "要点"


def build_plan(project: Path) -> Dict[str, Any]:
    script = _load_json(project / "script" / "script.json")
    narration = _load_json(project / "receipts" / "narration.json")
    lines = script.get("lines") or []
    if not isinstance(lines, list) or not lines:
        raise BrollPlanError("script has no lines")
    stills = _usable_stills(project)
    slots = _line_slot(narration)
    if not slots:
        raise BrollPlanError("narration has no measured line timings")

    config_path = project / "project.yaml"
    config_text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    account_match = re.search(r"^account_slug\s*:\s*(.+)$", config_text, re.MULTILINE)
    account_id = account_match.group(1).strip().strip('"').strip("'") if account_match else ""
    if not account_id:
        raise BrollPlanError("project.yaml has no account_slug; cannot resolve render variant")

    # Read the account's own reviewed default canvas. Fail closed if the
    # account has not declared one: an undeclared canvas is the blue-purple
    # default that repeats the defect.
    dna_path = ROOT / "config" / "accounts" / f"{account_id}.json"
    if not dna_path.is_file():
        raise BrollPlanError(f"account DNA not found: {dna_path}")
    dna = _load_json(dna_path)
    profile = (((dna.get("visual") or {}).get("motion") or {}).get("motion_profile") or {})
    built_variant = str(profile.get("render_variant") or "").strip()
    variants = profile.get("style_variants") or {}
    if not built_variant or built_variant not in variants:
        raise BrollPlanError(
            f"account {account_id} has no reviewed render_variant; "
            "declare one in visual.motion.motion_profile.render_variant")

    shots: List[Dict[str, Any]] = []
    specs: List[Tuple[str, Dict[str, Any]]] = []
    for index, line in enumerate(lines):
        if not isinstance(line, Mapping):
            continue
        line_id = str(line.get("id") or "").strip()
        if not line_id:
            raise BrollPlanError("every script line needs an id")
        slot = slots.get(line_id)
        if slot is None:
            raise BrollPlanError(f"narration has no timing for {line_id}")
        duration = min(MAX_CLIP_S, max(MIN_CLIP_S, round(slot["duration"], 3)))

        bound_id = str(line.get("asset_id") or "").strip()
        still = next((s for s in stills if s["id"] == bound_id), None)
        if still is None:
            still = stills[index % len(stills)]
        kind = _route_kind(line, still)

        props: Dict[str, Any] = {}
        if kind == "evidence_shot":
            grade = still.get("grade") or "illustrative"
            # A label is a rights claim: only a real, licensed capture may say
            # "证据画面". Everything else is explicitly marked not-evidence.
            kicker = {"real": "证据画面", "generated": "概念示意",
                      "illustrative": "示意卡"}.get(grade, "示意")
            note = {"real": "真实项目画面 · 见素材权利登记",
                    "generated": "原创配图 · 不是证据",
                    "illustrative": "原创示意卡 · 不是证据"}.get(grade, "示意")
            props = {
                "kicker": kicker,
                "callout": _callout(line),
                "note": note,
                "move": MOVES[index % len(MOVES)],
                "emphasis": "underline" if index % 2 else "box",
                "image_path": still["path"],
                "image_sha256": still["sha256"],
            }
        else:
            props = _info_graphic_props(line)

        spec = {
            "backend": "remotion",
            "template": kind,
            "shot_type": "architecture" if kind == "info_graphic" else "title_card",
            "duration_s": duration,
            # The account's reviewed render_variant is the video canvas. Without
            # it, animation_render falls back to the dark-blue brand.palette --
            # the generic AI look the visual gate flags as "blue-purple".
            "style_variant": built_variant,
            "props": props,
        }
        specs.append((line_id, spec))
        shots.append({
            "placement_id": line_id,
            "asset_id": f"br-{line_id}",
            "source_asset_id": still["id"],
            "backend": "remotion",
            "motion_backend": "remotion",
            "spec": f"motion/broll/{line_id}.json",
            "duration_s": duration,
            "visual_role": str(line.get("visual_role") or "explain"),
        })

    return {
        "plan": {"schema": PLAN_SCHEMA, "backend": "remotion", "shots": shots},
        "specs": specs,
        "account_id": account_id,
        "render_variant": built_variant,
        "total_s": round(sum(s["duration_s"] for s in shots), 3),
    }


def materialize(project: Path, built: Mapping[str, Any]) -> None:
    broll_dir = project / "motion" / "broll"
    broll_dir.mkdir(parents=True, exist_ok=True)
    for line_id, spec in built["specs"]:
        (broll_dir / f"{line_id}.json").write_text(
            json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (project / "motion" / "broll-plan.json").write_text(
        json.dumps(built["plan"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    config_path = project / "project.yaml"
    text = config_path.read_text(encoding="utf-8") if config_path.is_file() else ""
    # Remove any existing motion block, then append a clean one.
    text = re.sub(r"^motion:\s*$(?:\n[ \t]+.*)*", "", text, count=1, flags=re.MULTILINE)
    text = text.rstrip() + (
        "\n\nmotion:\n"
        "  backend: remotion\n"
        "  shot_plan: motion/broll-plan.json\n"
    )
    config_path.write_text(text, encoding="utf-8")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="compute and print the plan without writing files")
    args = parser.parse_args(argv)

    project = Path(args.project)
    try:
        built = build_plan(project)
        if not args.dry_run:
            materialize(project, built)
    except BrollPlanError as exc:
        payload = {"schema": "contentops.plan-broll/v1", "state": "BLOCKED",
                   "reason": str(exc)}
        print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json
              else f"BLOCKED: {exc}")
        return BLOCKED_EXIT

    shots = built["plan"]["shots"]
    kinds: Dict[str, int] = {}
    for shot in shots:
        spec = (next(s for lid, s in built["specs"]
                     if lid == shot["placement_id"]))
        kinds[spec["template"]] = kinds.get(spec["template"], 0) + 1
    payload = {
        "schema": "contentops.plan-broll/v1",
        "state": "PLANNED" if args.dry_run else "MATERIALIZED",
        "account_id": built["account_id"],
        "render_variant": built["render_variant"],
        "shots": len(shots),
        "kinds": kinds,
        "total_s": built["total_s"],
        "shot_plan": "motion/broll-plan.json",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json
          else f"{payload['state']}: {len(shots)} shots, {kinds}, {payload['total_s']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
