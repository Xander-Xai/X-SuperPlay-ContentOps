"""ASR backcheck as a **detector**, never as a quality judge.

What this is for
----------------
M2.0 used ASR successfully as a cheap detector: it agreed with the obvious wins
and losses in the pronunciation experiment. Transcription catches the failure
modes that are objectively wrong:

- missing words
- duplicated words
- numbers, dates and version strings mangled
- proper nouns flattened into something else
- technical vocabulary split or dropped

What this is deliberately **not** for
------------------------------------
Naturalness, emotion, pacing, pleasantness and publishability. No transcription
can tell you whether a voice sounds human, and a transcript that reads perfectly
can accompany audio nobody wants to publish. Those stay Human Review, and this
module's verdict can never set ``production_ready``.

The transcript is compared against the **spoken** text, not the display text,
because the lexicon deliberately rewrites tokens.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from process_utils import hidden_run  # noqa: E402

__all__ = ["AsrResult", "backcheck_speech", "token_overlap"]

_LATIN_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.+\-]*")
_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_PUNCT_RE = re.compile(r"[\s,.;:!?，。；：！？、\"'()（）\-—_/\\]+")


_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
           "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_UNITS = {"十": 10, "百": 100, "千": 1000}
_CJK_NUM_RE = re.compile(r"[零〇一二两三四五六七八九十百千点]+")


def _cn_number_to_digits(chunk: str) -> str:
    """Convert a Chinese numeral run to digits, best effort.

    Needed because ASR freely swaps forms: the narration says "982 个文件" and a
    transcript may come back as "九百八十二个文件", or the reverse. Without this
    the detector reports confident-looking false positives on every number in the
    script, which is how a detector gets ignored.
    """
    if not chunk or not any(c in _DIGITS or c in _UNITS for c in chunk):
        return chunk
    if "点" in chunk:
        head, _, tail = chunk.partition("点")
        whole = _cn_number_to_digits(head) if head else "0"
        if not whole.isdigit():
            return chunk
        decimals = "".join(str(_DIGITS[c]) for c in tail if c in _DIGITS)
        if not decimals:
            return chunk
        return f"{whole}.{decimals}"
    total = 0
    section = 0
    current = 0
    for char in chunk:
        if char in _DIGITS:
            current = _DIGITS[char]
        elif char in _UNITS:
            unit = _UNITS[char]
            section += (current or 1) * unit
            current = 0
        else:
            return chunk
    total += section + current
    result = str(total)
    # Never emit a partial conversion: an unrepresentable chunk such as one
    # containing 万 must be left alone rather than silently mangled.
    return result if result.isdigit() else chunk


def _reconcile_numerals(text: str) -> str:
    """Rewrite Chinese numeral runs as digits so both sides compare equal.

    Skipped entirely when 万 or 亿 appear: the converter does not implement those
    sections, and a partial substitution would silently mangle the text rather
    than leave it alone.
    """
    if "万" in text or "亿" in text:
        return text
    return _CJK_NUM_RE.sub(lambda m: _cn_number_to_digits(m.group(0)), text)


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = _reconcile_numerals(text)
    return text.lower()


def _tokens(text: str) -> List[str]:
    """Split into comparable units, script-aware.

    A whitespace tokeniser is wrong for Chinese: the golden narration has almost
    no spaces, so whitespace splitting yields sentence-long pseudo-tokens such as
    "个文件逐个比对过哈希" that can never match a transcript, and coverage
    collapses to a meaningless 0.31 on a perfectly good reading. Chinese is
    therefore compared per character, while space-delimited scripts keep word
    tokens so that "v0.2.1" is still checked as one unit.
    """
    normalised = _normalise(text)
    tokens: List[str] = list(_LATIN_TOKEN_RE.findall(normalised))
    tokens += _CJK_RE.findall(normalised)
    return tokens


def token_overlap(expected: str, actual: str) -> float:
    """Multiset recall of expected units in the transcript.

    Set-based overlap was wrong: it hid multiplicity loss. Expected "version
    version" against an actual "version" scored 1.0, which would have reported
    a clean bill of health for audio that dropped half the content. Counting
    multiplicity fixes that.

    Order is deliberately not checked. ASR reorders and re-punctuates freely, so
    an order check would produce noise, not signal.
    """
    want = Counter(_tokens(expected))
    have = Counter(_tokens(actual))
    total = sum(want.values())
    if total == 0:
        return 1.0
    matched = sum(min(count, have[token]) for token, count in want.items())
    return round(matched / total, 4)


def _multiplicity(expected: str, actual: str) -> Dict[str, List[str]]:
    """Split the difference into what is missing and what is in excess.

    A word or character that legitimately repeats is not an error: expected
    "哈哈" against actual "哈哈" has no missing and no excess, whereas expected
    "哈" against actual "哈哈" has one excess.
    """
    want = Counter(_tokens(expected))
    have = Counter(_tokens(actual))
    missing: List[str] = []
    excess: List[str] = []
    for token in sorted(set(want) | set(have)):
        delta = want[token] - have[token]
        if delta > 0:
            missing.extend([token] * delta)
        elif delta < 0:
            excess.extend([token] * (-delta))
    return {"missing": missing, "excess": excess}


@dataclass
class AsrResult:
    status: str
    transcript: Optional[str] = None
    coverage: Optional[float] = None
    issues: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)
    duplicated: List[str] = field(default_factory=list)  # units in excess
    detail: Optional[str] = None

    @property
    def detected_problem(self) -> bool:
        return self.status == "DETECTED_PROBLEM"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "role": "DETECTOR_ONLY",
            "can_approve_quality": False,
            "transcript": self.transcript,
            "coverage": self.coverage,
            "issues": self.issues,
            "missing": self.missing,
            "excess": self.duplicated,
            "detail": self.detail,
        }


def backcheck_speech(
    audio_path: Path,
    expected_spoken_text: str,
    *,
    cli: Optional[str] = None,
    coverage_floor: float = 0.85,
) -> AsrResult:
    """Transcribe and compare. Unavailable tooling yields SKIPPED, never PASS."""
    executable = cli or shutil.which("mmx")
    if not executable:
        return AsrResult(status="SKIPPED", detail="official MiniMax CLI not on PATH")

    result = hidden_run(
        [executable, "speech", "transcribe",
         "--file", str(audio_path),
         "--output", "json", "--quiet", "--non-interactive"],
        timeout=300,
    )
    if result.returncode != 0:
        return AsrResult(
            status="SKIPPED",
            detail=(result.stderr or "")[-300:],
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return AsrResult(status="SKIPPED", detail=f"unparsable ASR output: {exc}")

    transcript = payload.get("text") or ""
    if not transcript:
        return AsrResult(status="SKIPPED", detail="empty transcript")

    coverage = token_overlap(expected_spoken_text, transcript)
    diff = _multiplicity(expected_spoken_text, transcript)
    missing = diff["missing"]
    excess = diff["excess"]

    issues: List[str] = []
    if coverage < coverage_floor:
        issues.append(
            f"multiset coverage {coverage} below floor {coverage_floor}"
        )
    if missing:
        issues.append(f"{len(missing)} expected unit(s) absent from the transcript")
    if excess:
        issues.append(
            f"{len(excess)} unexpected repeated unit(s): {', '.join(excess[:5])}"
        )

    return AsrResult(
        status="DETECTED_PROBLEM" if issues else "NO_PROBLEM_DETECTED",
        transcript=transcript,
        coverage=coverage,
        issues=issues,
        missing=missing[:20],
        duplicated=excess[:20],
    )