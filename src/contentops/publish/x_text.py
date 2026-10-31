"""X's weighted character count, and the little that can be known about language.

Two honest limits are encoded here.

**The count is an estimate.** X's composer measures the final weighted length;
this function re-implements the published rules closely enough to refuse an
obviously over-budget post before a person types it. A post that lands at 279 is
still checked in the composer, because an estimate is not the authority.

**Language is a refusal, not a detector.** The account publishes in English. A
CJK ideograph, kana or hangul syllable in the copy means this is not the English
post the account promises, so it is refused. That is a narrower claim than "this
text is English", and it is the only one worth making here.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

#: A URL is weighed as a fixed 23 characters, whatever its real length.
URL_WEIGHT = 23
URL = re.compile(r"https?://\S+")

#: Code points the composer weighs as two. CJK/latin ranges are exact; the emoji
#: ranges are the ones a post realistically uses, not the whole Unicode table.
_WIDE_RANGES = (
    (0x1100, 0x115F),   # Hangul Jamo
    (0x2E80, 0xA4CF),   # CJK radicals through Yi
    (0xAC00, 0xD7A3),   # Hangul syllables
    (0xF900, 0xFAFF),   # CJK compatibility ideographs
    (0xFE30, 0xFE4F),   # CJK compatibility forms
    (0xFF00, 0xFF60),   # fullwidth forms
    (0xFFE0, 0xFFE6),   # fullwidth signs
    (0x1F300, 0x1F5FF), # misc symbols and pictographs
    (0x1F600, 0x1F64F), # emoticons
    (0x1F680, 0x1F6FF), # transport
    (0x1F900, 0x1F9FF), # supplemental symbols
    (0x1FA70, 0x1FAFF), # symbols and pictographs extended-A
    (0x2600, 0x27BF),   # misc symbols, dingbats
)

#: Scripts the account does not publish in. Their presence is a hard refusal.
_CJK_RANGES = (
    (0x3040, 0x30FF),   # kana
    (0x3400, 0x4DBF),   # CJK extension A
    (0x4E00, 0x9FFF),   # CJK unified ideographs
    (0xAC00, 0xD7A3),   # hangul syllables
    (0xF900, 0xFAFF),   # CJK compatibility ideographs
    (0x20000, 0x2FA1F), # CJK extensions B-F and compatibility supplement
)


def _in_ranges(code_point: int, ranges: Sequence) -> bool:
    return any(low <= code_point <= high for low, high in ranges)


def is_wide(character: str) -> bool:
    return _in_ranges(ord(character), _WIDE_RANGES)


def x_weighted_length(text: str) -> int:
    """Estimate X's weighted length for one post body.

    Each URL counts :data:`URL_WEIGHT`; each wide code point counts 2; everything
    else counts 1. Newlines count as one, which is what the composer does.
    """
    count = 0
    position = 0
    for match in URL.finditer(text):
        count += sum(2 if is_wide(char) else 1 for char in text[position:match.start()])
        count += URL_WEIGHT
        position = match.end()
    count += sum(2 if is_wide(char) else 1 for char in text[position:])
    return count


def parts_lengths(parts: Iterable[str]) -> List[int]:
    return [x_weighted_length(part) for part in parts]


def foreign_scripts(text: str) -> List[str]:
    """The non-Latin code points in ``text``, as ``U+XXXX`` strings.

    Empty means "no script this account refuses was found". It does not mean the
    text is good English; that is a person's call.
    """
    found: List[str] = []
    for character in text:
        if _in_ranges(ord(character), _CJK_RANGES):
            marker = f"U+{ord(character):04X}"
            if marker not in found:
                found.append(marker)
    return found
