#!/usr/bin/env python3
"""Validate the account DNA files.

The account DNA is the gene the whole account workflow reads. When it drifts
from the brand base, two things break at once: the pipeline renders the wrong
look, and the one-click prompt asks for a different one. Neither failure is
visible in a rendered frame, so both are caught here instead.

Checks, per account:
  1. schema and required keys
  2. palette is a valid hex pair and the accent is not the base
  3. visual.accent is the one accent, not a second value
  4. composition segments are unique and sum to 100
  5. motion allow-list and deny-list are both non-empty and disjoint
  6. caption style is borderless and shadowless, as the brand base requires
  7. cover keeps the whitespace floor and a single title line
  8. the evidence mode is declared, and the recording policy, the composition
     and the QC checks all agree with it
  9. the render block names the engine, a 9:16 vertical canvas, the fonts, the
     audio and the QC checks, and its generated easel.yaml comes from this DNA
 10. the benchmark priority is a ranked TOP3 with a primary
 11. the one-click prompt exists, names every required output field, and
     repeats the same palette
 12. every skill_route entry resolves: its skill exists under a catalog root,
     its SKILL.md front matter declares the same name, and its script path
     exists under the base it declares

skill_route path bases
----------------------
Each entry names ``script`` relative to one of two bases, and says which:

  path_base: "catalog"   script is relative to the Easel checkout root, e.g.
                         ``skills/openclaw/video-script``. This is the default,
                         because every entry but the repository's own scripts
                         lives there.
  path_base: "repo"      script is relative to this repository's root, e.g.
                         ``scripts/qc_video.py``.

The base is declared, never guessed from the string prefix. An entry that
declares no base and whose skill is not in the catalog is reported as a
warning rather than silently assumed to be either one.

Exit 0 = pass, exit 1 = fail.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# The skill catalog is resolved by the same helper the router uses, so the DNA
# check and the router can never disagree about which skills exist.
from skill_route import (
    CATALOG_ROOTS,
    SHARED_SKILL_ROOT,
    _front_matter,
    catalog,
    shared_skill,
)

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS = ROOT / "config" / "accounts"

sys.path.insert(0, str(ROOT / "src"))
# The mode table and the composition rule live beside the QC that enforces
# them, so the DNA check cannot hold a second, drifting copy.
from contentops.media.claim_coverage import (  # noqa: E402
    EVIDENCE_MODES,
    composition_policy_errors,
)

SCHEMA = "contentops.account-dna/v2"

PATH_BASES = ("catalog", "repo", "shared")
DEFAULT_PATH_BASE = "catalog"

REQUIRED_TOP_LEVEL = (
    "schema", "slug", "account", "role", "promise", "audience", "prompt",
    "brand", "narrative", "visual", "evidence", "audio", "render", "qc_rules",
    "platform_note", "skill_route", "platforms", "title", "description",
    "hashtags", "forbidden", "retention",
)

REQUIRED_PROMPT_FIELDS = (
    "video_title", "cover_prompt", "hook_3s", "voice_script", "storyboard",
    "qc_rules", "platform_note",
)

BASELINE_FORBIDDEN = (
    "invented numbers",
    "generated evidence substituted for real screenshots",
    "auto-publish without human approval",
)

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX.match(value))


def check_account(
    dna: Dict[str, Any],
    root: Path,
    warnings: Optional[List[str]] = None,
) -> List[str]:
    """Every failure for one account DNA. Empty list means the file is sound.

    ``warnings`` is an optional sink for non-fatal findings that the caller
    should surface but must not fail on. It is a list the caller owns, so the
    return type stays a plain list of failures.

    Warnings reach the caller prefixed with the account slug, the same way
    failures are. A warning that does not name its account is useless when the
    check runs over both accounts and prints one flat list.
    """
    failures: List[str] = []
    warnings = warnings if warnings is not None else []
    local_warnings: List[str] = []
    slug = str(dna.get("slug") or "<no slug>")

    if dna.get("schema") != SCHEMA:
        failures.append(f"schema is {dna.get('schema')!r}, expected {SCHEMA!r}")

    for key in REQUIRED_TOP_LEVEL:
        if key not in dna:
            failures.append(f"missing required key {key!r}")

    brand = dna.get("brand") or {}
    palette = brand.get("palette") or {}
    for key in ("base", "accent", "ink", "muted", "surface"):
        if not _hex(palette.get(key)):
            failures.append(f"brand.palette.{key} is not a #RRGGBB value")
    if _hex(palette.get("base")) and _hex(palette.get("accent")):
        if palette["base"].lower() == palette["accent"].lower():
            failures.append("brand.palette.base and .accent are the same colour")
    if not brand.get("forbidden_effects"):
        failures.append("brand.forbidden_effects is empty")

    visual = dna.get("visual") or {}
    if _hex(palette.get("accent")) and _hex(visual.get("accent")):
        if palette["accent"].lower() != visual["accent"].lower():
            failures.append(
                f"visual.accent {visual['accent']} does not match "
                f"brand.palette.accent {palette['accent']}"
            )
    elif not _hex(visual.get("accent")):
        failures.append("visual.accent is not a #RRGGBB value")

    composition = visual.get("composition") or {}
    segments = composition.get("segments") or []
    if not segments:
        failures.append("visual.composition.segments is empty")
    else:
        roles = [str(segment.get("role")) for segment in segments]
        if len(roles) != len(set(roles)):
            failures.append("visual.composition.segments repeats a role")
        total = 0
        for segment in segments:
            pct = segment.get("pct")
            if not isinstance(pct, int) or isinstance(pct, bool) or pct <= 0:
                failures.append(f"composition segment {segment.get('role')!r} has pct {pct!r}")
            else:
                total += pct
        if total != 100:
            failures.append(f"visual.composition sums to {total}, expected 100")

    motion = visual.get("motion") or {}
    allowed = motion.get("allowed") or []
    denied = motion.get("forbidden") or []
    if not allowed:
        failures.append("visual.motion.allowed is empty")
    if not denied:
        failures.append("visual.motion.forbidden is empty")
    overlap = sorted(set(allowed) & set(denied))
    if overlap:
        failures.append(f"visual.motion allows and forbids the same effect: {overlap}")

    caption = visual.get("caption_style") or {}
    for key in ("font", "primary", "highlight", "outline", "shadow",
                "burn_style", "max_chars_per_line"):
        if key not in caption:
            failures.append(f"visual.caption_style is missing {key!r}")
    for key in ("primary", "highlight"):
        if key in caption and not _hex(caption[key]):
            failures.append(f"visual.caption_style.{key} is not a #RRGGBB value")
    if caption.get("outline") != "none":
        failures.append(f"visual.caption_style.outline is {caption.get('outline')!r}, expected 'none'")
    if caption.get("shadow") != "none":
        failures.append(f"visual.caption_style.shadow is {caption.get('shadow')!r}, expected 'none'")
    burn = str(caption.get("burn_style") or "")
    if burn:
        if "Outline=0" not in burn:
            failures.append("visual.caption_style.burn_style does not disable the outline")
        if "Shadow=0" not in burn:
            failures.append("visual.caption_style.burn_style does not disable the shadow")

    cover = visual.get("cover") or {}
    whitespace = cover.get("whitespace_min_ratio")
    if not isinstance(whitespace, (int, float)) or whitespace < 0.3:
        failures.append(
            f"visual.cover.whitespace_min_ratio is {whitespace!r}, expected at least 0.3"
        )
    if cover.get("title_lines") != 1:
        failures.append(f"visual.cover.title_lines is {cover.get('title_lines')!r}, expected 1")

    evidence = dna.get("evidence") or {}
    recording = evidence.get("manual_recording")
    if recording not in ("ALLOWED_CROPPED", "FORBIDDEN"):
        failures.append(f"evidence.manual_recording is {recording!r}")
    roles = {str(segment.get("role")) for segment in segments}
    if recording == "ALLOWED_CROPPED" and "screen_recording_evidence" not in roles:
        failures.append("cropped evidence is allowed but the composition has no evidence segment")
    if recording == "FORBIDDEN" and "screen_recording_evidence" in roles:
        failures.append("manual recording is forbidden but the composition requires one")

    # The mode is the account's answer to "which gate governs this film?", and
    # it is what the plan and the QC read. Left undeclared, each downstream
    # reader invented its own default, which is how a 100% vector cut ended up
    # carrying a 70% real-source floor it could never reach.
    mode = evidence.get("mode")
    qc_checks = [str(item) for item in (dna.get("render") or {}).get("qc_checks") or []]
    if mode not in EVIDENCE_MODES:
        failures.append(
            f"evidence.mode is {mode!r}, expected one of {EVIDENCE_MODES}"
        )
    else:
        failures.extend(composition_policy_errors(mode, segments))
        if mode == "EVIDENCE_LED" and "real_source_ratio_min_70" not in qc_checks:
            failures.append(
                "EVIDENCE_LED owns the whole-film real-source floor, but "
                "render.qc_checks does not list 'real_source_ratio_min_70'"
            )
        if mode != "EVIDENCE_LED" and "real_source_ratio_min_70" in qc_checks:
            failures.append(
                f"evidence.mode is {mode!r}, so the 70% real-source floor does not "
                "apply, but render.qc_checks still demands it"
            )
        if mode == "EXPLANATORY" and "composition_ratio" not in qc_checks:
            failures.append(
                "EXPLANATORY is gated by its declared composition instead, but "
                "render.qc_checks does not list 'composition_ratio'"
            )
        if mode == "EXPLANATORY" and recording != "FORBIDDEN":
            failures.append(
                "EXPLANATORY plans no recording asset, but evidence.manual_recording "
                f"is {recording!r}"
            )

    narrative = dna.get("narrative") or {}
    if not narrative.get("template"):
        failures.append("narrative.template is empty")
    if not narrative.get("speech_rate_cpm"):
        failures.append("narrative.speech_rate_cpm is missing")
    if not narrative.get("cta"):
        failures.append("narrative.cta is missing")
    if not dna.get("decision_question"):
        failures.append("decision_question is missing")
    if not dna.get("mission"):
        failures.append("mission is missing")
    if not dna.get("tagline"):
        failures.append("tagline is missing")
    if not dna.get("core_audience"):
        failures.append("core_audience is missing — the account writes for nobody in particular")

    pillars = dna.get("content_pillars") or []
    if not pillars:
        failures.append("content_pillars is empty")
    else:
        weighted = [p for p in pillars if p.get("weight_pct") is not None]
        if weighted:
            total = sum(int(p["weight_pct"]) for p in weighted)
            if total != 100:
                failures.append(f"content_pillars weights sum to {total}, expected 100")
            if len(weighted) != len(pillars):
                failures.append("content_pillars mixes weighted and unweighted pillars")
        for pillar in pillars:
            if not pillar.get("name"):
                failures.append("a content pillar has no name")
            if not pillar.get("structure"):
                failures.append(f"content pillar {pillar.get('name')!r} has no structure")

    rules = dna.get("non_negotiable") or []
    if len(rules) < 5:
        failures.append(f"non_negotiable has {len(rules)} rules, expected at least 5")

    ladder = dna.get("evidence_ladder") or {}
    if len(ladder.get("order") or []) < 4:
        failures.append("evidence_ladder.order has fewer than four rungs")
    if not ladder.get("rule"):
        failures.append("evidence_ladder has no rule")

    business = dna.get("business") or {}
    if not business.get("source_of_truth"):
        failures.append("business.source_of_truth is missing")
    if not business.get("rule"):
        failures.append("business has no rule")

    cadence = dna.get("cadence") or {}
    for key in ("baseline_videos_per_week", "source_artifacts_per_week", "founder_hours_per_week"):
        if key not in cadence:
            failures.append(f"cadence.{key} is missing")

    acceptance = dna.get("acceptance_metrics") or {}
    if len(acceptance.get("metrics") or []) < 5:
        failures.append("acceptance_metrics.metrics has fewer than five entries")
    if not acceptance.get("first_stage_priority"):
        failures.append("acceptance_metrics.first_stage_priority is missing")

    roles = dna.get("platform_roles") or {}
    for platform in dna.get("platforms") or []:
        if platform not in roles:
            failures.append(f"platform {platform!r} is active but has no platform role")
    for platform in dna.get("derived_platforms") or []:
        if platform not in roles:
            failures.append(f"derived platform {platform!r} has no platform role")

    coverage = narrative.get("template_coverage")
    if coverage:
        covered = set(coverage.get("covered") or [])
        deferred = set(coverage.get("deferred") or [])
        template = set(narrative.get("template") or [])
        if covered & deferred:
            failures.append(
                f"template_coverage covers and defers the same beat: {sorted(covered & deferred)}"
            )
        if covered | deferred != template:
            missing = sorted(template - (covered | deferred))
            extra = sorted((covered | deferred) - template)
            failures.append(
                f"template_coverage does not partition the template (missing={missing}, extra={extra})"
            )
        if deferred and not coverage.get("deferred_reason"):
            failures.append("template_coverage defers a beat without a reason")

    text_platforms = dna.get("text_platforms") or {}
    if text_platforms:
        overlap = set(text_platforms.get("platforms") or []) & set(dna.get("platforms") or [])
        if overlap:
            failures.append(
                f"a platform is mapped to both video and text distribution: {sorted(overlap)}"
            )
        if not text_platforms.get("reason"):
            failures.append("text_platforms has no reason")

    audio = dna.get("audio") or {}
    bgm = audio.get("bgm") or {}
    margin = bgm.get("max_db_below_voice")
    if not isinstance(margin, (int, float)) or margin < 18:
        failures.append(f"audio.bgm.max_db_below_voice is {margin!r}, expected at least 18")
    if not (audio.get("voice") or {}).get("persona"):
        failures.append("audio.voice.persona is missing")

    forbidden = dna.get("forbidden") or []
    for item in BASELINE_FORBIDDEN:
        if item not in forbidden:
            failures.append(f"forbidden is missing the baseline rule {item!r}")

    render = dna.get("render") or {}
    if render.get("engine") != "easel":
        failures.append(f"render.engine is {render.get('engine')!r}, expected 'easel'")
    easel_yaml = ROOT / "projects" / slug / "easel.yaml"
    if not easel_yaml.is_file():
        failures.append(f"missing generated config {easel_yaml.relative_to(ROOT).as_posix()}")
    else:
        text = easel_yaml.read_text(encoding="utf-8")
        if f"generated_from: config/accounts/{slug}.json" not in text:
            failures.append(
                f"{easel_yaml.relative_to(ROOT).as_posix()} is not generated from this DNA"
            )
    benchmarks = dna.get("benchmarks") or {}
    priority = benchmarks.get("priority") or []
    if len(priority) != 3:
        failures.append(f"benchmarks.priority has {len(priority)} entries, expected 3")
    else:
        ranks = [entry.get("rank") for entry in priority]
        if ranks != [1, 2, 3]:
            failures.append(f"benchmarks.priority ranks are {ranks}, expected [1, 2, 3]")
        if benchmarks.get("primary") != priority[0].get("account"):
            failures.append(
                f"benchmarks.primary {benchmarks.get('primary')!r} is not the rank-1 account"
            )
        for entry in priority:
            if not entry.get("adopt"):
                failures.append(f"benchmarks rank {entry.get('rank')} has no adopt note")

    canvas = render.get("canvas") or {}
    width, height = canvas.get("width"), canvas.get("height")
    for name, value in (("width", width), ("height", height)):
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            failures.append(f"render.canvas.{name} is {value!r}")
    if isinstance(width, int) and isinstance(height, int) and width and height:
        if canvas.get("orientation") == "vertical" and width * 16 != height * 9:
            failures.append(
                f"render.canvas {width}x{height} is not 9:16 for a vertical cut"
            )
    if not render.get("qc_checks"):
        failures.append("render.qc_checks is empty")
    if not (render.get("audio") or {}).get("voice_provider"):
        failures.append("render.audio.voice_provider is missing")
    if not (render.get("fonts") or {}).get("primary"):
        failures.append("render.fonts.primary is missing")

    if not dna.get("qc_rules"):
        failures.append("qc_rules is empty")
    if not dna.get("platform_note"):
        failures.append("platform_note is empty")

    route = dna.get("skill_route") or []
    if not route:
        failures.append("skill_route is empty")
    for entry in route:
        for key in ("step", "skill", "script", "why"):
            if not entry.get(key):
                failures.append(f"skill_route entry {entry.get('step')!r} is missing {key!r}")
    failures.extend(_check_skill_route(route, root, local_warnings))

    warnings.extend(f"[{slug}] {warning}" for warning in local_warnings)
    failures.extend(_check_prompt(dna, palette, root))
    return [f"[{slug}] {failure}" for failure in failures]


def _catalog_roots() -> List[Path]:
    """The catalog roots that exist on this checkout, in router order."""
    return [candidate for candidate in CATALOG_ROOTS if candidate.is_dir()]


def _catalog_skill(skill: str, roots: List[Path]):
    """The first catalog root holding ``skill``, and that skill's directory."""
    for root in roots:
        candidate = root / skill
        if candidate.is_dir():
            return root, candidate
    return None, None


def _check_skill_route(
    route: List[Dict[str, Any]],
    root: Path,
    warnings: List[str],
) -> List[str]:
    """Resolve every declared skill and script against its declared base.

    A route entry that names a skill nobody ships is the failure this exists
    for: the DNA would otherwise read as sound while pointing at a directory
    that does not exist.
    """
    failures: List[str] = []
    roots = _catalog_roots()
    catalog_names = {item["name"] for item in catalog()[0]}
    if not roots:
        warnings.append(
            "no skill catalog root is present on this checkout; skill membership "
            "and catalog-relative script paths were not verified"
        )
    shared_present = SHARED_SKILL_ROOT.is_dir()
    if not shared_present:
        warnings.append(
            f"the shared skill store {SHARED_SKILL_ROOT} is absent on this "
            f"checkout; shared routes were not verified"
        )

    for entry in route:
        step = entry.get("step")
        skill = str(entry.get("skill") or "")
        script = str(entry.get("script") or "")
        if not skill or not script:
            continue  # already reported as a missing required key

        declared = "path_base" in entry
        base = entry.get("path_base", DEFAULT_PATH_BASE)
        if base not in PATH_BASES:
            failures.append(
                f"skill_route entry {step!r} has path_base {base!r}, "
                f"expected one of {list(PATH_BASES)}"
            )
            continue

        if base == "catalog":
            if not roots:
                continue
            catalog_root, skill_dir = _catalog_skill(skill, roots)
            if skill_dir is None:
                failures.append(
                    f"skill_route entry {step!r} names skill {skill!r}, which is "
                    f"not present under any catalog root "
                    f"({', '.join(r.relative_to(root).as_posix() for r in roots)})"
                )
                if not declared:
                    warnings.append(
                        f"skill_route entry {step!r} declares no path_base and "
                        f"skill {skill!r} is not in the catalog; its path base "
                        f"could not be determined"
                    )
                continue
            try:
                (catalog_root / skill).resolve().relative_to(catalog_root.resolve())
            except ValueError:
                failures.append(
                    f"skill_route entry {step!r} names skill {skill!r}, which "
                    f"resolves outside its catalog root"
                )
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                failures.append(
                    f"skill_route entry {step!r} names skill {skill!r}, but "
                    f"{skill_md.relative_to(root).as_posix()} does not exist"
                )
                continue
            meta = _front_matter(skill_md.read_text(encoding="utf-8", errors="replace"))
            declared_name = meta.get("name") or skill_dir.name
            if declared_name != skill:
                failures.append(
                    f"skill_route entry {step!r} names skill {skill!r}, but "
                    f"{skill_md.relative_to(root).as_posix()} declares name "
                    f"{declared_name!r}"
                )
            # A catalog-relative script may name a skill directory or a file
            # inside it; both are legitimate, so existence is the test.
            bases = {catalog_root.parent.parent for catalog_root in roots}
            if not any((catalog_base / script).exists() for catalog_base in bases):
                failures.append(
                    f"skill_route entry {step!r} script {script!r} does not exist "
                    f"under any catalog base"
                )
        elif base == "repo":
            if not (root / script).is_file():
                failures.append(
                    f"skill_route entry {step!r} script {script!r} does not exist "
                    f"relative to the repository root"
                )
            if declared and skill in catalog_names:
                warnings.append(
                    f"skill_route entry {step!r} uses path_base 'repo' but "
                    f"skill {skill!r} is also in the catalog; confirm the base"
                )
        else:  # shared
            if not shared_present:
                # Same rule as an absent catalog root: the store is host-local
                # (a CI runner has no ~/.agents/skills), so its absence is a
                # warning about what was not verified, not a DNA failure.
                continue
            skill_dir = shared_skill(skill)
            if skill_dir is None:
                failures.append(
                    f"skill_route entry {step!r} names skill {skill!r}, which is "
                    f"not present in the shared skill store {SHARED_SKILL_ROOT}"
                )
                continue
            meta = _front_matter(
                (skill_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
            declared_name = meta.get("name") or skill_dir.name
            if declared_name != skill:
                failures.append(
                    f"skill_route entry {step!r} names skill {skill!r}, but the "
                    f"shared copy declares name {declared_name!r}"
                )
            script_path = (SHARED_SKILL_ROOT / script).resolve()
            try:
                script_path.relative_to(SHARED_SKILL_ROOT.resolve())
            except ValueError:
                failures.append(
                    f"skill_route entry {step!r} script {script!r} resolves "
                    f"outside the shared skill store"
                )
                continue
            if not script_path.exists():
                failures.append(
                    f"skill_route entry {step!r} script {script!r} does not exist "
                    f"relative to the shared skill store"
                )
    return failures


def _check_prompt(dna: Dict[str, Any], palette: Dict[str, Any], root: Path) -> List[str]:
    """The prompt and the DNA must describe the same video, in the same look."""
    failures: List[str] = []
    relative = dna.get("prompt")
    if not relative:
        return ["prompt path is missing"]
    path = root / str(relative)
    if not path.is_file():
        return [f"prompt file {relative} does not exist"]
    text = path.read_text(encoding="utf-8")
    for field in REQUIRED_PROMPT_FIELDS:
        if field not in text:
            failures.append(f"prompt {relative} does not name the output field {field!r}")
    for key in ("base", "accent"):
        value = palette.get(key)
        if _hex(value) and value.lower() not in text.lower():
            failures.append(f"prompt {relative} does not carry the {key} colour {value}")
    if dna.get("account") and str(dna["account"]) not in text:
        failures.append(f"prompt {relative} does not name the account {dna['account']}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    paths = sorted(ACCOUNTS.glob("*.json"))
    if not paths:
        print(f"no account DNA found under {ACCOUNTS.relative_to(ROOT).as_posix()}/")
        return 1

    failures: List[str] = []
    warnings: List[str] = []
    checked: List[str] = []
    for path in paths:
        dna = json.loads(path.read_text(encoding="utf-8"))
        checked.append(str(dna.get("slug") or path.stem))
        failures.extend(check_account(dna, ROOT, warnings))

    # The catalog-absent warning is raised once per account; report it once.
    warnings = list(dict.fromkeys(warnings))

    if args.json:
        print(json.dumps({
            "schema": "contentops.account-dna-check/v1",
            "accounts": checked,
            "overall": "FAIL" if failures else "PASS",
            "failures": failures,
            "warnings": warnings,
        }, indent=2, ensure_ascii=False))
        return 1 if failures else 0

    if failures:
        print("[account_dna] FAIL")
        for failure in failures:
            print(f"  [FAIL] {failure}")
        for warning in warnings:
            print(f"  [WARN] {warning}")
        print(f"\n{len(failures)} account DNA failure(s)")
        return 1
    for warning in warnings:
        print(f"  [WARN] {warning}")
    print(f"[account_dna] PASS ({len(checked)} accounts: {', '.join(checked)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
