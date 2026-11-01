"""The editorial gate: three real theses, a human review, and a proof grade.

The vendored `docs/EDITORIAL-QUALITY-GATE.md` and the 2026-10-26 recovery override
state four requirements that can be checked mechanically once a post record holds
them:

1. **Three genuinely different candidate theses**, each with its own evidence,
   counterexample and reader action. Three rewordings of one judgment fail.
2. **The four recovery fields** — ``audience_job``, ``proof_grade``,
   ``unique_artifact_ref``, ``experiment_variable``.
3. **A human review** scored on the account's own six dimensions, at or above the
   floor, with the three fixed dimensions each at their own floor.
4. **An honest label**: a `P0` post is `SOURCE_ANALYSIS` and may not claim a
   result nobody ran.

What this module cannot check is whether the theses are *good*. It checks that
they exist as distinct claims with their counterexamples attached, which is the
part that decays silently. The score is a person's; this only refuses an
unscored post and a score below the account's floor.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

#: ``(code, detail)`` pairs. `x_post` wraps them in its own Issue type.
Finding = Tuple[str, str]

#: The vendor's four recovery fields, in its own names.
RECOVERY_FIELDS = ("audience_job", "proof_grade", "unique_artifact_ref", "experiment_variable")
PROOF_GRADES = ("P0", "P1", "P2", "P3")

#: A thesis is a claim plus what would make it wrong plus what the reader does.
THESIS_FIELDS = ("thesis", "evidence", "counterexample", "reader_action")

#: First-person result claims. A `P0` post may describe a mechanism, never a run.
FIRSTHAND_CLAIMS = (
    "i tested", "i ran", "i measured", "i benchmarked",
    "we tested", "we ran", "we measured", "we benchmarked",
)

#: Words too common to tell two theses apart.
_STOPWORDS = frozenset(
    "the a an and or of to in on for with is are was were be been it this that "
    "as at by from not no you your we our i my they their".split())

#: Two theses sharing more than this share of their meaningful vocabulary are one
#: judgment written twice.
SAME_THESIS_OVERLAP = 0.8


def _words(text: str) -> set:
    return {word for word in re.findall(r"[a-z]{4,}", text.lower())
            if word not in _STOPWORDS}


def _overlap(left: str, right: str) -> float:
    a, b = _words(left), _words(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def editorial_rules(account: Dict[str, Any]) -> Dict[str, Any]:
    """The account's editorial block, with the vendor defaults it must declare."""
    return dict(account.get("editorial") or {})


def validate_theses(post: Dict[str, Any], editorial: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    theses = post.get("theses")
    required = editorial.get("theses_required")
    required = required if isinstance(required, int) and required > 0 else 3
    if not isinstance(theses, list) or len(theses) < required:
        count = len(theses) if isinstance(theses, list) else 0
        return [("THESES_INSUFFICIENT",
                 f"the record carries {count} thesis candidate(s); the gate requires {required}")]
    for index, thesis in enumerate(theses, start=1):
        if not isinstance(thesis, dict):
            findings.append(("THESES_INSUFFICIENT", f"thesis {index} is not an object"))
            continue
        for field in THESIS_FIELDS:
            if not str(thesis.get(field) or "").strip():
                findings.append(
                    ("THESES_INSUFFICIENT",
                     f"thesis {index} has no {field!r}; a claim without its "
                     "counterexample is not a candidate"))
    if findings:
        return findings
    for left in range(len(theses)):
        for right in range(left + 1, len(theses)):
            overlap = _overlap(str(theses[left]["thesis"]), str(theses[right]["thesis"]))
            if overlap >= SAME_THESIS_OVERLAP:
                findings.append(
                    ("THESES_INSUFFICIENT",
                     f"theses {left + 1} and {right + 1} share "
                     f"{overlap:.0%} of their vocabulary; that is one judgment "
                     "written twice, not two candidates"))
    return findings


def validate_recovery(post: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    for field in RECOVERY_FIELDS:
        if not str(post.get(field) or "").strip():
            findings.append(("RECOVERY_FIELD_MISSING", f"the record has no {field!r}"))
    grade = str(post.get("proof_grade") or "")
    if grade and grade not in PROOF_GRADES:
        findings.append(
            ("RECOVERY_FIELD_MISSING",
             f"proof_grade is {grade!r}; expected one of {list(PROOF_GRADES)}"))
    variable = str(post.get("experiment_variable") or "").strip()
    if variable and ("," in variable or " and " in variable.lower()):
        findings.append(
            ("RECOVERY_FIELD_MISSING",
             f"experiment_variable is {variable!r}; one variable, not several, or "
             "nothing learned from it can be attributed"))
    return findings


def validate_review(post: Dict[str, Any], editorial: Dict[str, Any]) -> List[Finding]:
    review = post.get("review")
    if not isinstance(review, dict):
        return [("REVIEW_MISSING",
                 "no human review is recorded; an assistant may prepare one and "
                 "may not approve it")]
    findings: List[Finding] = []
    if not str(review.get("reviewer") or "").strip():
        findings.append(("REVIEW_MISSING", "the review names no reviewer"))
    if not str(review.get("reviewed_at") or "").strip():
        findings.append(("REVIEW_MISSING", "the review has no reviewed_at date"))

    dimensions = editorial.get("review_dimensions") or []
    scored = review.get("dimensions") or {}
    if not isinstance(scored, dict):
        return findings + [("REVIEW_MISSING", "review.dimensions is not an object")]

    total = 0
    for dimension in dimensions:
        name = str(dimension.get("id"))
        maximum = dimension.get("max")
        value = scored.get(name)
        if not isinstance(value, int) or isinstance(value, bool):
            findings.append(
                ("REVIEW_MISSING", f"the review does not score {name!r} at all"))
            continue
        if isinstance(maximum, int) and not 0 <= value <= maximum:
            findings.append(
                ("REVIEW_SCORE_INCONSISTENT",
                 f"{name} is {value}, outside its 0..{maximum} range"))
        total += value

    floor = editorial.get("dimension_floor")
    enforced = [str(item) for item in editorial.get("dimension_floor_required") or []]
    if isinstance(floor, int):
        for name in enforced:
            value = scored.get(name)
            if isinstance(value, int) and value < floor:
                findings.append(
                    ("REVIEW_DIMENSION_LOW",
                     f"{name} scores {value}, below the required {floor}"))

    score = review.get("score")
    score_floor = editorial.get("score_floor")
    if not isinstance(score, int) or isinstance(score, bool):
        findings.append(("REVIEW_SCORE_LOW", "the review records no total score"))
        return findings
    if isinstance(score_floor, int) and score < score_floor:
        findings.append(
            ("REVIEW_SCORE_LOW",
             f"the review scores {score}, below the account's floor of {score_floor}"))
    if score != total:
        findings.append(
            ("REVIEW_SCORE_INCONSISTENT",
             f"the total is {score} but the six dimensions sum to {total}"))
    return findings


def validate_label(post: Dict[str, Any], copy_text: str, editorial: Dict[str, Any]) -> List[Finding]:
    """A source-only post says so, and does not claim a run nobody did."""
    findings: List[Finding] = []
    label = post.get("label")
    source_label = str(editorial.get("source_analysis_label") or "SOURCE_ANALYSIS")
    grade = str(post.get("proof_grade") or "")
    if grade == "P0" and label != source_label:
        findings.append(
            ("RECOVERY_FIELD_MISSING",
             f"proof_grade is P0 but label is {label!r}; a post with no firsthand "
             f"artifact must carry {source_label!r}"))
    lowered = copy_text.lower()
    if grade == "P0":
        for phrase in FIRSTHAND_CLAIMS:
            if phrase in lowered:
                findings.append(
                    ("FIRSTHAND_CLAIM_UNSUPPORTED",
                     f"the copy says {phrase!r} but the proof grade is P0 (source "
                     "read only); a claim of a run needs a P1 artifact"))
                break
    return findings


def validate_editorial(post: Dict[str, Any], account: Dict[str, Any],
                       copy_text: str) -> List[Finding]:
    editorial = editorial_rules(account)
    findings: List[Finding] = []
    findings.extend(validate_theses(post, editorial))
    findings.extend(validate_recovery(post))
    findings.extend(validate_review(post, editorial))
    findings.extend(validate_label(post, copy_text, editorial))
    red_team = post.get("red_team")
    required = editorial.get("red_team_questions")
    required = required if isinstance(required, int) and required > 0 else 3
    if not isinstance(red_team, list) or len(red_team) < required:
        findings.append(
            ("THESES_INSUFFICIENT",
             f"the record answers {len(red_team) if isinstance(red_team, list) else 0} "
             f"red-team question(s); the gate requires {required}"))
    else:
        for index, answer in enumerate(red_team, start=1):
            if not str(answer or "").strip():
                findings.append(
                    ("THESES_INSUFFICIENT", f"red-team question {index} has no answer"))
    return findings
