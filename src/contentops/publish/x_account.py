"""The X account DNA contract, on its own.

``config/accounts/x-superplay-english.json`` is a text account
(``contentops.x-account/v1``). It is not a video account with keys removed: it
has a 280-character budget, one real 1600x900 image, a human review carrying a
proof grade, and a status URL or nothing at all. Validating it on a film
composition or an ``easel.yaml`` would be a lie dressed as a check.

This module is the X half of the repository's account-DNA checker. It depends
on the standard library and the X document only. It does not resolve the
account's ``skill_route`` entries against a skill catalog: that is the Skill
Router's job, and a tree without the router must still be able to validate the
document's own shape. The shape of each entry is checked, not its target.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

X_REQUIRED_TOP_LEVEL = (
    "schema", "slug", "account", "language", "platforms", "platform_roles",
    "mission", "promise", "tagline", "decision_question", "audience",
    "core_audience", "content_pillars", "non_negotiable", "evidence",
    "evidence_ladder", "editorial", "visual", "publication", "cadence",
    "business", "acceptance_metrics", "forbidden", "brand", "prompt",
    "skill_route", "pipeline",
)

X_REQUIRED_PROMPT_FIELDS = (
    "audience_job", "theses", "red_team", "proof_grade", "unique_artifact_ref",
    "experiment_variable", "post_copy", "image_brief", "alt_text", "status_url",
)

X_BASELINE_FORBIDDEN = (
    "invented numbers",
    "generated evidence substituted for real screenshots",
    "auto-publish without human approval",
    "published without a status URL",
)

#: The four states a post record may claim. Anything else is a different claim.
X_POST_STATUS = ("draft", "scheduled", "published", "failed")
X_IMAGE_STATUS = ("missing", "failed_qa", "pending_export", "generated",
                  "external_image_pending_archive")
X_FORMATS = ("png", "jpeg")
X_RECOVERY_FIELDS = ("audience_job", "proof_grade", "unique_artifact_ref",
                     "experiment_variable")

HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def _hex(value: Any) -> bool:
    return isinstance(value, str) and bool(HEX.match(value))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_prompt(
    dna: Dict[str, Any],
    palette: Dict[str, Any],
    root: Path,
    required_fields: Sequence[str] = X_REQUIRED_PROMPT_FIELDS,
) -> List[str]:
    """The prompt and the DNA must describe the same deliverable, in the same look."""
    failures: List[str] = []
    relative = dna.get("prompt")
    if not relative:
        return ["prompt path is missing"]
    path = Path(root) / str(relative)
    if not path.is_file():
        return [f"prompt file {relative} does not exist"]
    text = path.read_text(encoding="utf-8")
    for field in required_fields:
        if field not in text:
            failures.append(f"prompt {relative} does not name the output field {field!r}")
    for key in ("base", "accent"):
        value = palette.get(key)
        if _hex(value) and value.lower() not in text.lower():
            failures.append(f"prompt {relative} does not carry the {key} colour {value}")
    if dna.get("account") and str(dna["account"]) not in text:
        failures.append(f"prompt {relative} does not name the account {dna['account']}")
    return failures


def _check_pillars(pillars: Any) -> List[str]:
    """Weighted pillars that sum to 100."""
    failures: List[str] = []
    if not isinstance(pillars, list) or not pillars:
        return ["content_pillars is empty"]
    total = 0
    for pillar in pillars:
        name = pillar.get("name")
        if not name:
            failures.append("a content pillar has no name")
        weight = pillar.get("weight_pct")
        if not _is_int(weight) or weight <= 0:
            failures.append(f"content pillar {name!r} has weight_pct {weight!r}")
        else:
            total += weight
        if not pillar.get("structure"):
            failures.append(f"content pillar {name!r} has no structure")
    if total != 100:
        failures.append(f"content_pillars weights sum to {total}, expected 100")
    return failures


def check_x_account(
    dna: Dict[str, Any],
    root: Path,
    warnings: Optional[List[str]] = None,
) -> List[str]:
    """Every failure for one X account document, or an empty list."""
    failures: List[str] = []
    warnings = warnings if warnings is not None else []
    slug = str(dna.get("slug") or "<no slug>")

    for key in X_REQUIRED_TOP_LEVEL:
        if key not in dna:
            failures.append(f"missing required key {key!r}")

    if dna.get("language") != "en":
        failures.append(f"language is {dna.get('language')!r}, expected 'en'")
    if not str(dna.get("account") or "").strip():
        failures.append("account is empty")
    platforms = [str(item) for item in dna.get("platforms") or []]
    if platforms != ["x"]:
        failures.append(f"platforms is {platforms!r}; this account publishes to 'x' only")
    pipeline = dna.get("pipeline")
    if not isinstance(pipeline, str) or not pipeline.strip():
        failures.append(
            "pipeline is not a non-empty string; routing would have to guess an "
            "evidence mode this account does not have")

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

    failures.extend(_check_pillars(dna.get("content_pillars")))
    note = dna.get("content_pillars_note") or {}
    if note.get("superseded_mix") and not note.get("reason"):
        failures.append(
            "content_pillars_note records a superseded mix without a reason; "
            "a silent revert to the old quota mix would look like an edit")

    rules = dna.get("non_negotiable") or []
    if len(rules) < 5:
        failures.append(f"non_negotiable has {len(rules)} rules, expected at least 5")

    editorial = dna.get("editorial") or {}
    max_chars = editorial.get("max_chars_per_post")
    if max_chars != 280:
        failures.append(f"editorial.max_chars_per_post is {max_chars!r}, expected 280")
    thread = editorial.get("max_thread_posts")
    if not _is_int(thread) or not 1 <= thread <= 3:
        failures.append(f"editorial.max_thread_posts is {thread!r}, expected 1..3")
    theses = editorial.get("theses_required")
    if not _is_int(theses) or theses < 3:
        failures.append(f"editorial.theses_required is {theses!r}, expected at least 3")
    red_team = editorial.get("red_team_questions")
    if not _is_int(red_team) or red_team < 3:
        failures.append(f"editorial.red_team_questions is {red_team!r}, expected at least 3")
    hook = editorial.get("hook_chars")
    if not _is_int(hook) or hook <= 0 or (_is_int(max_chars) and hook > max_chars):
        failures.append(f"editorial.hook_chars is {hook!r} against a {max_chars!r}-char post")

    dimensions = editorial.get("review_dimensions") or []
    if not dimensions:
        failures.append("editorial.review_dimensions is empty")
    ids = [str(dimension.get("id")) for dimension in dimensions]
    if len(ids) != len(set(ids)):
        failures.append("editorial.review_dimensions repeats an id")
    total = 0
    for dimension in dimensions:
        maximum = dimension.get("max")
        if not _is_int(maximum) or maximum <= 0:
            failures.append(
                f"review dimension {dimension.get('id')!r} has max {maximum!r}")
        else:
            total += maximum
    floor = editorial.get("score_floor")
    if total and (not isinstance(floor, (int, float)) or isinstance(floor, bool)
                  or not 0 < floor <= total):
        failures.append(f"editorial.score_floor is {floor!r} against a {total}-point rubric")
    dimension_floor = editorial.get("dimension_floor")
    if not _is_int(dimension_floor) or not 1 <= dimension_floor <= 5:
        failures.append(
            f"editorial.dimension_floor is {dimension_floor!r}, expected 1..5")
    enforced = [str(item) for item in editorial.get("dimension_floor_required") or []]
    if not enforced:
        failures.append("editorial.dimension_floor_required is empty")
    unknown = sorted(set(enforced) - set(ids))
    if unknown:
        failures.append(
            f"editorial.dimension_floor_required names dimensions that do not exist: {unknown}")
    recovery = [str(item) for item in editorial.get("recovery_fields") or []]
    missing_recovery = [field for field in X_RECOVERY_FIELDS if field not in recovery]
    if missing_recovery:
        failures.append(f"editorial.recovery_fields is missing {missing_recovery}")
    if not editorial.get("source_analysis_label"):
        failures.append(
            "editorial.source_analysis_label is empty; a post with no firsthand "
            "artifact would have no honest label")

    prompts = editorial.get("prompts") or {}
    if not isinstance(prompts, dict) or not prompts:
        failures.append(
            "editorial.prompts is empty; a record may then name no prompt at all")
    else:
        for name, path in sorted(prompts.items()):
            candidate = Path(root) / str(path)
            if not candidate.is_file():
                failures.append(
                    f"editorial.prompts[{name!r}] points at {str(path)!r}, which is "
                    "not a file in this tree")

    visual = dna.get("visual") or {}
    width, height = visual.get("width"), visual.get("height")
    for name, value in (("width", width), ("height", height)):
        if not _is_int(value) or value <= 0:
            failures.append(f"visual.{name} is {value!r}")
    if _is_int(width) and _is_int(height) and width > 0 and height > 0:
        if width * 9 != height * 16:
            failures.append(f"visual canvas {width}x{height} is not 16:9")
        if visual.get("target") != f"{width}x{height}":
            failures.append(
                f"visual.target is {visual.get('target')!r}, expected '{width}x{height}'")
        if visual.get("aspect") != "16:9":
            failures.append(f"visual.aspect is {visual.get('aspect')!r}, expected '16:9'")
    formats = [str(item).lower() for item in visual.get("formats") or []]
    if not formats:
        failures.append("visual.formats is empty")
    unsupported = sorted(set(formats) - set(X_FORMATS))
    if unsupported:
        failures.append(f"visual.formats names formats X will not accept: {unsupported}")
    if visual.get("svg_alone") is not False:
        failures.append(
            "visual.svg_alone must be false: an SVG on its own is not uploadable to X")
    if visual.get("alt_required") is not True:
        failures.append("visual.alt_required must be true")
    image_statuses = [str(item) for item in visual.get("image_status_enum") or []]
    expected_image = sorted(X_IMAGE_STATUS)
    if sorted(image_statuses) != expected_image:
        failures.append(
            f"visual.image_status_enum is {sorted(image_statuses)}, expected {expected_image}")

    publication = dna.get("publication") or {}
    if publication.get("mode") != "MANUAL_ONLY":
        failures.append(
            f"publication.mode is {publication.get('mode')!r}; only MANUAL_ONLY is "
            "implemented, and an API publisher needs a capability spike first")
    if publication.get("requires_status_url") is not True:
        failures.append("publication.requires_status_url must be true")
    if publication.get("api") != "not_implemented":
        failures.append(
            f"publication.api is {publication.get('api')!r}; declaring an implemented "
            "API that does not exist is the fabricate-an-adapter failure")
    handle = publication.get("handle")
    handle_status = publication.get("handle_status")
    if handle in (None, ""):
        if handle_status not in ("UNKNOWN", "UNASSIGNED"):
            failures.append(
                f"publication.handle is unset but handle_status is {handle_status!r}; "
                "an unknown handle is UNKNOWN, not a guess")
    elif not isinstance(handle, str) or not handle.strip():
        failures.append(f"publication.handle is {handle!r}")
    elif handle_status in ("UNKNOWN", "UNASSIGNED"):
        failures.append(
            f"publication.handle is {handle!r} but handle_status is "
            f"{handle_status!r}; a handle must be recorded from a real status URL, "
            "and until then it is unknown")
    statuses = sorted(str(item) for item in publication.get("post_status_enum") or [])
    if statuses != sorted(X_POST_STATUS):
        failures.append(
            f"publication.post_status_enum is {statuses}, expected {sorted(X_POST_STATUS)}")

    evidence = dna.get("evidence") or {}
    ladder = evidence.get("proof_ladder") or {}
    if sorted(ladder) != ["P0", "P1", "P2", "P3"]:
        failures.append(
            f"evidence.proof_ladder declares {sorted(ladder)}, expected P0..P3")
    else:
        for rung, description in ladder.items():
            if not str(description).strip():
                failures.append(f"evidence.proof_ladder.{rung} is empty")
    if not evidence.get("required_evidence_class"):
        failures.append("evidence.required_evidence_class is empty")
    if evidence.get("firsthand_required_for_results") is not True:
        failures.append(
            "evidence.firsthand_required_for_results must be true: a results claim "
            "without a firsthand artifact is a SOURCE_ANALYSIS at best")

    engagement = dna.get("evidence_ladder") or {}
    if len(engagement.get("order") or []) < 4:
        failures.append("evidence_ladder.order has fewer than four rungs")
    if not engagement.get("rule"):
        failures.append("evidence_ladder has no rule")

    cadence = dna.get("cadence") or {}
    window = cadence.get("original_posts_per_week")
    if not (isinstance(window, list) and len(window) == 2
            and all(_is_int(item) for item in window)
            and 0 < window[0] <= window[1] <= 7):
        failures.append(
            f"cadence.original_posts_per_week is {window!r}, expected [low, high] inside 0..7")
    if cadence.get("max_original_posts_per_day") != 1:
        failures.append(
            f"cadence.max_original_posts_per_day is "
            f"{cadence.get('max_original_posts_per_day')!r}, expected 1")
    if not cadence.get("rule"):
        failures.append("cadence has no rule")

    business = dna.get("business") or {}
    if not business.get("source_of_truth"):
        failures.append("business.source_of_truth is missing")
    if not business.get("rule"):
        failures.append("business has no rule")

    acceptance = dna.get("acceptance_metrics") or {}
    if len(acceptance.get("metrics") or []) < 5:
        failures.append("acceptance_metrics.metrics has fewer than five entries")
    if not acceptance.get("first_stage_priority"):
        failures.append("acceptance_metrics.first_stage_priority is missing")

    roles = dna.get("platform_roles") or {}
    for platform in platforms:
        if platform not in roles:
            failures.append(f"platform {platform!r} is active but has no platform role")

    forbidden = dna.get("forbidden") or []
    for item in X_BASELINE_FORBIDDEN:
        if item not in forbidden:
            failures.append(f"forbidden is missing the baseline rule {item!r}")

    route = dna.get("skill_route") or []
    if not route:
        failures.append("skill_route is empty")
    for entry in route:
        for key in ("step", "skill", "script", "why"):
            if not entry.get(key):
                failures.append(f"skill_route entry {entry.get('step')!r} is missing {key!r}")

    failures.extend(check_prompt(dna, palette, Path(root), X_REQUIRED_PROMPT_FIELDS))
    return [f"[{slug}] {failure}" for failure in failures]
