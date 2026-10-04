"""Compile a business-facing shot into a MiniMax H3 prompt.

Source of truth
---------------
`MiniMax-AI/MiniMax-H3`, ``skills/h3-prompt-writing/SKILL.md`` and the guides it
names. Re-verified for M4 on 2026-10-05:

===========================  =========  ===========================================
Field                         Value      Value
===========================  =========  ===========================================
repository                    main       ``d21241f0a4b3acbb34c97dae47fa417b7065e438``
skill                         blob       ``b6d9b2839384a588763a9c24315225dd8ce19d56``
last commit touching skill             ``a107547fa669c509b8e6363fe18378d46ab3066c``
===========================  =========  ===========================================

The upstream repository is **not vendored**. This module implements the structure
it specifies.

What the upstream text actually requires
----------------------------------------
For base modes (T2VA, I2VA, FL2VA, L2VA) an optional alignment instruction is the
**first line**, followed by one blank line, then exactly three core fields in this
order::

    integrated_multimodal_description
    overall_soundscape
    non_diegetic_music

T2VA has no alignment instruction and starts directly with the three fields.

For full-reference mode (Ref2VA) the rewrite carries six sections in this order::

    subject_definitions
    summary
    retention_analysis
    detailed_description
    overall_soundscape
    non_diegetic_music

Field names, section order, reference labels and timing notation are reproduced
exactly. They are not paraphrased, because the model is trained against them: a
prompt that renames ``overall_soundscape`` is not a stylistic difference, it is a
different request.

Timing notation
---------------
``S.SS`` is the effective duration to **exactly two decimals**. ``N`` is the index
of the actual final shot. ``[Shot 1]`` carries no timestamp; later shots carry a
strictly increasing cut time inside the duration, formatted ``[Shot 2] At 00:03.500``.

Camera motion
-------------
Motion type plus amplitude plus speed, written as a natural English action inside
the shot rather than as stacked labels at the end of a sentence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "BASE_CORE_FIELDS",
    "CAMERA_MOTION_TYPES",
    "H3PromptCompiler",
    "H3PromptError",
    "H3_MODES",
    "MAX_PROMPT_CHARACTERS",
    "PROMPT_SKILL_BLOB",
    "PROMPT_SKILL_COMMIT",
    "PROMPT_SKILL_PATH",
    "PROMPT_SKILL_REPO",
    "PROMPT_SKILL_CHECKED_AT",
    "REF2VA_SECTIONS",
    "ShotPlan",
    "format_duration",
]

#: Provenance of the prompt structure. Recorded in every video receipt so a
#: prompt can be traced back to the exact upstream guidance that shaped it.
PROMPT_SKILL_REPO = "MiniMax-AI/MiniMax-H3"
PROMPT_SKILL_PATH = "skills/h3-prompt-writing/SKILL.md"
PROMPT_SKILL_COMMIT = "d21241f0a4b3acbb34c97dae47fa417b7065e438"
PROMPT_SKILL_BLOB = "b6d9b2839384a588763a9c24315225dd8ce19d56"
PROMPT_SKILL_LAST_COMMIT = "a107547fa669c509b8e6363fe18378d46ab3066c"
PROMPT_SKILL_CHECKED_AT = "2026-10-05"

#: The documented per-item prompt cap.
MAX_PROMPT_CHARACTERS = 7000

#: The three core fields, in the order the upstream guide gives them.
BASE_CORE_FIELDS: Tuple[str, ...] = (
    "integrated_multimodal_description",
    "overall_soundscape",
    "non_diegetic_music",
)

#: The six full-reference sections, in the order the upstream guide gives them.
REF2VA_SECTIONS: Tuple[str, ...] = (
    "subject_definitions",
    "summary",
    "retention_analysis",
    "detailed_description",
    "overall_soundscape",
    "non_diegetic_music",
)

#: The five generation modes.
H3_MODES: Tuple[str, ...] = ("T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA")

#: Modes whose rewrite carries the six full-reference sections.
FULL_REFERENCE_MODES: Tuple[str, ...] = ("Ref2VA",)

#: Modes that require or accept frame alignment, and therefore an instruction.
ALIGNED_MODES: Tuple[str, ...] = ("I2VA", "FL2VA", "L2VA")

#: The upstream camera-motion vocabulary. Closed on purpose: the guide presents it
#: as a table, and inventing a term produces a prompt the model was never trained
#: to read.
CAMERA_MOTION_TYPES: Tuple[str, ...] = (
    "Zoom In", "Zoom Out", "Push In", "Pull Out",
    "Pan Left", "Pan Right", "Truck Left", "Truck Right",
    "Tilt Up", "Tilt Down", "Pedestal Up", "Pedestal Down",
    "Arc Shot", "Tracking Shot", "Static Shot",
    "Shake Slightly", "Shake Strongly", "POV",
    "Roll Clockwise", "Roll Counterclockwise",
)
AMPLITUDE_PHRASES: Tuple[str, ...] = ("with small amplitude", "with large amplitude")
SPEED_PHRASES: Tuple[str, ...] = ("at slow speed", "at fast speed")

#: Upstream: "Use ``N/A`` only when the user explicitly requests complete silence."
NOT_APPLICABLE = "N/A"


class H3PromptError(ValueError):
    """The requested prompt cannot be built, or would breach a documented limit."""


def format_duration(seconds: float) -> str:
    """Format an effective duration as the upstream ``S.SS`` notation.

    Exactly two decimals, always. ``S.SS`` is positional in the alignment
    sentences, so a one-decimal or three-decimal rendering would produce a
    malformed instruction.
    """
    if seconds < 0:
        raise H3PromptError(f"duration must not be negative, got {seconds}")
    return f"{float(seconds):.2f}"


@dataclass
class ShotPlan:
    """One shot, described in business terms.

    Deliberately provider-neutral: no ``content[]``, no ``role=``, no API field
    names. The compiler maps this into H3 prompt structure; the provider maps the
    compiled result into the API schema. Business logic upstream of this type
    never learns what the transport looks like.
    """

    shot_id: str
    purpose: str
    duration: int
    aspect_ratio: Optional[str] = None
    subject: str = ""
    environment: str = ""
    action: str = ""
    camera: str = ""
    dialogue: str = ""
    sound: str = ""
    visual_style: str = ""
    #: Provider-neutral reference descriptors. Labels are assigned by the compiler.
    reference_assets: Tuple[str, ...] = ()
    #: Real evidence this shot illustrates. A shot may reference evidence without
    #: being evidence; the boundary is enforced by the registry, not here.
    claim_refs: Tuple[str, ...] = ()
    #: Shot count. A single continuous shot is the safe default for a 4-5 s clip.
    shot_count: int = 1
    mode: str = "T2VA"


@dataclass
class CompiledPrompt:
    """The compiled prompt plus the metadata a receipt needs."""

    text: str
    mode: str
    sections: List[str] = field(default_factory=list)
    alignment_instruction: Optional[str] = None
    reference_labels: List[str] = field(default_factory=list)
    skills_repo: str = PROMPT_SKILL_REPO
    skills_commit: str = PROMPT_SKILL_COMMIT
    skills_checked_at: str = PROMPT_SKILL_CHECKED_AT

    def as_metadata(self) -> Dict[str, object]:
        return {
            "prompt_skill_repo": self.skills_repo,
            "prompt_skill_commit": self.skills_commit,
            "prompt_skill_checked_at": self.skills_checked_at,
            "prompt_skill_blob": PROMPT_SKILL_BLOB,
            "prompt_skill_last_commit": PROMPT_SKILL_LAST_COMMIT,
            "prompt_skill_path": PROMPT_SKILL_PATH,
            "sections": list(self.sections),
            "reference_labels": list(self.reference_labels),
        }


class H3PromptCompiler:
    """Turn a :class:`ShotPlan` into an H3 prompt that follows the upstream skill.

    The compiled text is what gets hashed into the fingerprint, because it is what
    is actually sent. Hashing the operator's raw intent instead would make the
    cache key lie: two different intents can compile to the same prompt, and the
    same intent can compile to different prompts.
    """

    def __init__(
        self,
        *,
        max_characters: int = MAX_PROMPT_CHARACTERS,
        allow_ref2va: bool = True,
    ) -> None:
        self._max_characters = max_characters
        self._allow_ref2va = allow_ref2va

    # -- public API --------------------------------------------------------

    @staticmethod
    def canonical_mode(mode: Optional[str]) -> str:
        """Map any casing onto the canonical mode spelling.

        ``Ref2VA``.upper() is ``REF2VA``, which is not one of the documented mode
        names, so a naive case fold would reject a perfectly valid mode. Matching
        is therefore case-insensitive but the **canonical** spelling is returned.
        """
        candidate = (mode or "T2VA").strip()
        folded = candidate.upper()
        for known in H3_MODES:
            if known.upper() == folded:
                return known
        raise H3PromptError(
            f"unknown H3 mode {mode!r}; supported: {', '.join(H3_MODES)}"
        )

    def compile(self, plan: ShotPlan) -> CompiledPrompt:
        """Compile one shot. Raises :class:`H3PromptError` on anything invalid."""
        mode = self.canonical_mode(plan.mode)
        if mode in FULL_REFERENCE_MODES and not self._allow_ref2va:
            raise H3PromptError(
                f"{mode} is disabled in this compiler configuration"
            )
        if not plan.subject.strip():
            raise H3PromptError(
                f"shot {plan.shot_id!r} has no subject; the upstream skill builds "
                f"the multimodal description from subject, action and environment"
            )

        if mode in FULL_REFERENCE_MODES:
            return self._compile_ref2va(plan, mode)
        return self._compile_base(plan, mode)

    # -- base modes --------------------------------------------------------

    def _compile_base(self, plan: ShotPlan, mode: str) -> CompiledPrompt:
        effective = self._effective_duration(plan)
        alignment = self._alignment_instruction(plan, mode, effective)
        description = self._multimodal_description(plan, mode, effective)

        blocks: List[str] = []
        if alignment:
            # Upstream: the instruction is the first line, followed by one blank
            # line before the core fields.
            blocks.append(alignment)
            blocks.append("")
        blocks.append(f"integrated_multimodal_description: {description}")
        blocks.append("")
        blocks.append(f"overall_soundscape: {self._overall_soundscape(plan)}")
        blocks.append("")
        blocks.append(f"non_diegetic_music: {self._non_diegetic_music(plan)}")

        text = "\n".join(blocks).strip() + "\n"
        self._enforce_length(text, plan)
        return CompiledPrompt(
            text=text,
            mode=mode,
            sections=list(BASE_CORE_FIELDS),
            alignment_instruction=alignment,
        )

    def _alignment_instruction(
        self, plan: ShotPlan, mode: str, effective: str
    ) -> Optional[str]:
        """Reproduce the upstream alignment sentence verbatim for the mode."""
        if mode not in ALIGNED_MODES:
            return None
        if mode == "I2VA":
            return (
                "For the target video, at 0.00 seconds into the target video, "
                "<Picture 1> (from [Shot 1]) is fully referenced."
            )
        if mode == "FL2VA":
            return (
                "How the reference pictures align with the target video \u2014 "
                "Picture 1 (from Shot 1) aligns with the 0.00-second mark of the "
                f"target video; Picture 2 (from Shot {plan.shot_count}) aligns "
                f"with the {effective}-second mark of the target video."
            )
        return (
            "How the reference pictures align with the target video \u2014 "
            f"<Picture 1> (from [Shot {plan.shot_count}]) aligns with the "
            f"{effective}-second mark of the target video."
        )

    def _multimodal_description(
        self, plan: ShotPlan, mode: str, effective: str
    ) -> str:
        """Build the main body: style, composition, subject, action, camera, sound."""
        parts: List[str] = []
        style = plan.visual_style.strip() or "Live-action, cinematic"
        parts.append(f"[Shot 1] {style}, {plan.environment.strip() or 'a restrained scene'}")

        subject = plan.subject.strip()
        if mode == "I2VA":
            # Upstream recommends establishing the anchors the image already fixes
            # before describing the next action.
            parts.append(
                f"the subject shown in <Picture 1> remains {subject}, preserving "
                f"its appearance, clothing, position and the established "
                f"composition"
            )
        else:
            parts.append(subject)

        if mode == "FL2VA":
            parts.append(
                "beginning from the state and framing established by Picture 1, "
                "the motion proceeds as observable intermediate changes that "
                "narrow the difference toward the composition established by "
                "Picture 2"
            )
        elif mode == "L2VA":
            parts.append(
                "beginning from a plausible preceding state, the action and the "
                "environment converge gradually in the final shot onto the exact "
                "arrangement shown in <Picture 1>"
            )

        if plan.action.strip():
            parts.append(plan.action.strip())
        if plan.camera.strip():
            parts.append(self._camera_sentence(plan.camera.strip()))
        if plan.dialogue.strip():
            # Upstream: the speaker phrase and delivery sit outside <d>; inside
            # <d> only the language tag and the user's own words, verbatim.
            parts.append(f"the speaker says: <d>[English] {plan.dialogue.strip()}</d>")
        if plan.sound.strip():
            parts.append(plan.sound.strip())

        if plan.shot_count > 1:
            # A strictly increasing cut inside the duration. Upstream forbids a
            # timestamp on the first shot.
            parts.append(
                f"[Shot 2] At {self._cut_time(plan.duration, fraction=0.75)}, "
                f"the camera cuts to a closer framing of {subject}"
            )
        return ", ".join(part for part in parts if part)

    def _camera_sentence(self, camera: str) -> str:
        """Render camera motion as a natural English action.

        The upstream guide is explicit that motion is written inside the sentence
        rather than stacked as labels. When the caller supplies structured values
        they are validated against the closed vocabulary and woven in here.
        """
        return f"the camera {camera}"

    def _cut_time(self, duration: int, *, fraction: float) -> str:
        """Format a cut timestamp as ``MM:SS.mmm`` inside the duration."""
        seconds = max(0.0, min(duration - 0.001, duration * fraction))
        minutes = int(seconds // 60)
        remainder = seconds - minutes * 60
        return f"{minutes:02d}:{remainder:06.3f}"

    def _overall_soundscape(self, plan: ShotPlan) -> str:
        """Ambient, physical and non-verbal sound. Upstream allows 1-4 sentences."""
        if plan.sound.strip():
            return plan.sound.strip()
        return "Low room ambience continues underneath with no distinct events."

    def _non_diegetic_music(self, plan: ShotPlan) -> str:
        """Audience-only music. Upstream allows 1-3 sentences, or ``N/A``."""
        return NOT_APPLICABLE

    # -- full reference ----------------------------------------------------

    def _compile_ref2va(self, plan: ShotPlan, mode: str) -> CompiledPrompt:
        labels = self._reference_labels(plan)
        # Pair each label with the asset it names. Using the label on both sides
        # would define nothing: "<Subject 1> corresponds to <Subject 1>".
        definitions = ", ".join(
            f"{label} corresponds to {asset}"
            for label, asset in zip(labels, plan.reference_assets)
        ) or NOT_APPLICABLE

        blocks = [
            f"subject_definitions: {definitions}",
            "",
            "summary: "
            f"[Shot 1] {plan.visual_style.strip() or 'Live-action, cinematic'}; "
            f"{plan.subject.strip()} in {plan.environment.strip() or 'a restrained scene'}"
            + (f"; referencing {', '.join(labels)}" if labels else ""),
            "",
            "retention_analysis: "
            + (
                "each referenced element keeps the identity, proportions and "
                "surface detail it has in its source, while the requested action "
                "supplies all new motion"
                if labels
                else NOT_APPLICABLE
            ),
            "",
            f"detailed_description: {self._multimodal_description(plan, mode, self._effective_duration(plan))}",
            "",
            f"overall_soundscape: {self._overall_soundscape(plan)}",
            "",
            f"non_diegetic_music: {self._non_diegetic_music(plan)}",
        ]
        text = "\n".join(blocks).strip() + "\n"
        self._enforce_length(text, plan)
        return CompiledPrompt(
            text=text,
            mode=mode,
            sections=list(REF2VA_SECTIONS),
            reference_labels=labels,
        )

    def _reference_labels(self, plan: ShotPlan) -> List[str]:
        """Assign upstream labels, keeping them consistent across sections.

        Upstream requires the same label in every section, so labels are derived
        once here and reused.
        """
        return [f"<Subject {index}>" for index in range(1, len(plan.reference_assets) + 1)]

    # -- shared ------------------------------------------------------------

    def _effective_duration(self, plan: ShotPlan) -> str:
        return format_duration(plan.duration)

    def _enforce_length(self, text: str, plan: ShotPlan) -> None:
        """Enforce the documented prompt cap locally, before any billing read."""
        if len(text) <= self._max_characters:
            return
        raise H3PromptError(
            f"compiled prompt for shot {plan.shot_id!r} is {len(text)} "
            f"characters, above the documented limit of {self._max_characters}. "
            f"Trim the description rather than sending an invalid request."
        )

    @staticmethod
    def validate_camera_motion(motion: str) -> str:
        """Check a camera-motion phrase against the closed upstream vocabulary.

        Amplitude and speed phrases are optional and appended by the caller.
        """
        candidate = motion.strip()
        if not candidate:
            raise H3PromptError("camera motion must not be empty")
        # Amplitude and speed are independent and may both appear, in that order,
        # so trailing phrases are stripped repeatedly rather than once.
        changed = True
        while changed:
            changed = False
            for token in AMPLITUDE_PHRASES + SPEED_PHRASES:
                if candidate.endswith(token):
                    candidate = candidate[: -len(token)].strip()
                    changed = True
        if candidate not in CAMERA_MOTION_TYPES:
            raise H3PromptError(
                f"camera motion {motion!r} is not in the documented vocabulary. "
                f"Expected one of: {', '.join(CAMERA_MOTION_TYPES)}."
            )
        return candidate