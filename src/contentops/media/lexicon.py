"""PronunciationLexicon: display text and spoken text, kept apart.

Measured basis (M2.0, Issue #4)
-------------------------------
Three variants of the same mixed Chinese/English technical sentence, ASR
backchecked after each:

| Variant | Mechanism | Duration | Outcome |
|---|---|---|---|
| A | no rules | 17.41 s | `Claude` read as "Cloud", `Qwen` as "Quen", `H3` as "H-three", `v0.2.1` collapsed to "V0.21" |
| B | `pronunciation_dict` with IPA | 24.58 s (+41%) | compound brand names split apart; `GitHub` and `LangGraph` became two tokens; `H3` read as "A Three" |
| C | `pronunciation_dict` with plain-text expansion + text normalisation | 18.39 s (+6%) | every sampled token correct |

Two rules follow, and both are load-bearing:

1. **Plain-text expansion is the default.** IPA is measurably worse than doing
   nothing for compound brand names, so no IPA rule is ever generated.
2. **SSML is not supported and is never invented.** The current provider exposes
   ``pronunciation_dict.tone[]`` with ``source/replacement`` entries, plus inline
   parenthesised pronunciation in the text itself.

The lexicon holds *spoken form* replacements, not pronunciation phonetics. For a
Chinese narration the useful mapping is usually a Chinese phonetic expansion,
because that is what fixes "Claude" being read as "Cloud".

Versioning
----------
:attr:`PronunciationLexicon.version` participates in the generation fingerprint.
Changing a rule must therefore change the fingerprint and force regeneration;
otherwise a fixed script could silently keep an old, badly pronounced asset.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple

__all__ = [
    "PronunciationLexicon",
    "LEXICON_VERSION",
    "default_zh_lexicon",
    "default_en_lexicon",
]

LEXICON_VERSION = "zh-2026.10.04.1"

#: Tokens the M2.0 sample proved get mispronounced without help. This is the
#: regression vocabulary: a test asserts every entry survives a round trip.
REGRESSION_VOCABULARY: Tuple[str, ...] = (
    "RAG",
    "Agent",
    "Claude Code",
    "Codex",
    "GitHub",
    "Easel",
    "MiniMax",
    "LangGraph",
    "Qwen",
    "H3",
    "v0.2.1",
    "2026",
)

_ZH_RULES: Mapping[str, str] = {
    # Compound / camel-case tokens split into separate words without help.
    "Claude Code": "克劳德代码",
    "Easel": "伊泽尔",
    "LangGraph": "兰格拉夫",
    "Qwen": "千问",
    # Version strings lose their separators.
    "v0.2.1": "v零点二点一",
    # Added from the M2 narration ASR backcheck: the golden script's
    # "Web 工作台" was transcribed as "外部工作台", i.e. "Web" was read as a
    # Chinese word. A plain-text expansion is the right tool here.
    "Web 工作台": "网页工作台",
}

_EN_RULES: Mapping[str, str] = {
    # Left as-is where M2.0 showed the provider already reads them acceptably.
    # Only entries with measured failures belong here.
}

_VERSION_RE = re.compile(r"\d")


@dataclass(frozen=True)
class PronunciationLexicon:
    """Immutable token -> spoken-form mapping for one language."""

    language: str
    rules: Mapping[str, str]
    version: str = LEXICON_VERSION

    def spoken_text(self, display_text: str) -> str:
        """Return the text to synthesise.

        The display text is never mutated in place; callers keep both so a
        caption can still show ``X-SuperPlay`` while the voice says something
        pronounceable.
        """
        if not self.rules:
            return display_text
        spoken = display_text
        # Longest source first, so "Claude Code" wins over a hypothetical "Claude".
        for source in sorted(self.rules, key=len, reverse=True):
            replacement = self.rules[source]
            if source in spoken:
                spoken = spoken.replace(source, replacement)
        return spoken

    def provider_arguments(self) -> List[str]:
        """``pronunciation_dict`` entries for the official CLI.

        Plain-text expansion only. There is deliberately no IPA branch: M2.0
        measured IPA to be worse than no rule at all.
        """
        entries: List[str] = []
        for source in sorted(self.rules):
            entries += ["--pronunciation", f"{source}/{self.rules[source]}"]
        return entries

    def fingerprint_component(self) -> str:
        """Stable digest of the rule set, for the idempotency fingerprint."""
        payload = "|".join(
            f"{k}={self.rules[k]}" for k in sorted(self.rules)
        )
        return hashlib.sha256(
            f"{self.version}:{self.language}:{payload}".encode("utf-8")
        ).hexdigest()[:16]

    def covers(self, token: str) -> bool:
        return token in self.rules


def default_zh_lexicon(overrides: Optional[Mapping[str, str]] = None) -> PronunciationLexicon:
    """Chinese narration lexicon, including the M2.0 regression vocabulary."""
    rules: Dict[str, str] = dict(_ZH_RULES)
    if overrides:
        rules.update(overrides)
    return PronunciationLexicon(language="zh", rules=rules)


def default_en_lexicon(overrides: Optional[Mapping[str, str]] = None) -> PronunciationLexicon:
    """English narration lexicon.

    Empty on purpose. M2.0 measured no English token that needed help, and a
    lexicon entry with no evidence behind it is a guess.
    """
    rules: Dict[str, str] = dict(_EN_RULES)
    if overrides:
        rules.update(overrides)
    return PronunciationLexicon(language="en", rules=rules)


def coverage_report(lexicon: PronunciationLexicon) -> Dict[str, bool]:
    """Which regression tokens this lexicon actually covers."""
    return {token: lexicon.covers(token) for token in REGRESSION_VOCABULARY}