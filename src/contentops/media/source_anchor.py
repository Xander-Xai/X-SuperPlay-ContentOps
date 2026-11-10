"""Render a readable pinned-source excerpt card for vertical motion shots.

Why this module exists
----------------------
The first M5 auto-motion run fed Huashu's ``t2_keynote_ui`` grammar a tall
1080x1920 card whose code block occupied the top third at 20 px and left the
remaining ~60% of the frame as flat surface colour. Huashu then did exactly
what the grammar is built to do -- show the still full-bleed and push in once
-- so the film read as "one small screenshot, one push, repeat": the
skill's own first and fourth documented failure modes ("翻页式 PPT" and
"死背景、空画面"). The renderer was not the problem; the still was.

This module produces a still that is composed to be looked at:

* the excerpt window fills the frame, so there is no flat void;
* the code column is centred and hard-wrapped at :data:`WRAP_COLS` characters,
  which is the only lever that changes how large the text finally reads: the
  camera can push at most ``fill / rect_width``, and ``rect_width`` grows with
  characters-per-line, so effective on-screen text height is
  ``canvas_width / (0.55 * chars_per_line)`` regardless of the font size;
* every drawn line records its exact normalised rectangle, so the motion
  planner can point a camera at real source lines instead of guessing from
  OCR boxes (an OCR box on a 70-character line is ~0.85 of the frame wide and
  the camera can only push 1.18x -- the documented "框太宽推不进去" trap).

The output is a deterministic, source-traceable ``CODE_SNAPSHOT``. It is
visual support only: it never becomes evidence for a factual claim.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

# The card is rendered at the aspect of the motion grammar's content box
# (1080x1920 minus a 520 px subtitle band) so ``contain`` fit lands it
# edge-to-edge instead of shrinking it and exposing backdrop margins.
ANCHOR_WIDTH = 1080
ANCHOR_HEIGHT = 1688
ANCHOR_SCHEMA = "contentops.source-anchor/v1"

CODE_FONT_PX = 34
CODE_LEADING_PX = 48
WRAP_COLS = 32
GUTTER_COLS = 5
CODE_TOP_PX = 262
CODE_MAX_LINES = 26

PAD_X = 28
CARD_TOP = 20
CARD_BOTTOM = 1668
CARD_RADIUS = 26
TEXT_X = 64
RULE_Y = 226
FOOTER_RULE_Y = 1592
FOOTER_TEXT_Y = 1614

FONT_CANDIDATES = {
    "mono": ("C:/Windows/Fonts/consola.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
             "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf"),
    "mono_bold": ("C:/Windows/Fonts/consolab.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
                  "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf"),
    "sans": ("C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/msyh.ttc",
             "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/segoeui.ttf",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    "sans_regular": ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/segoeui.ttf",
                     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                     "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
}

KEYWORDS = frozenset("""
and as assert async await break class continue def del elif else except False
finally for from global if import in is lambda None nonlocal not or pass raise
return True try while with yield self super
fn func let mut pub struct impl use mod match enum trait where const static
SELECT FROM WHERE JOIN INSERT UPDATE DELETE CREATE TABLE
true false null nil
""".split())

_COMMENT_RE = re.compile(r"(\s*#|\s*//|\s*--|\s*;)")
_STRING_RE = re.compile(r"(\"(?:[^\"\\\\]|\\\\.)*\"|'(?:[^'\\\\]|\\\\.)*')")
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def visual_terms(text: str) -> set[str]:
    """Tokenise a sentence into comparable lowercase content terms."""
    terms = {token.casefold() for token in re.findall(r"[a-z0-9]{2,}", str(text), re.I)}
    terms.difference_update({"the", "and", "for", "with", "that", "this", "from", "into",
                             "are", "was", "were", "has", "have", "not", "you", "its",
                             "all", "any", "can", "one", "two", "use", "used", "using"})
    for phrase in re.findall(r"[\u3400-\u9fff]+", str(text)):
        terms.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return terms


def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in "WF" else 1 for char in text)


def _truncate_columns(text: str, columns: int) -> str:
    if _display_width(text) <= columns:
        return text
    out, used = [], 0
    for char in text:
        step = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used + step > columns - 1:
            break
        out.append(char)
        used += step
    return "".join(out) + "…"


def _break_index(body: str, limit: int) -> int:
    """Find a readable break point: never mid-identifier, prefer after punctuation."""
    used = 0
    fitted = 0
    for index, char in enumerate(body):
        step = 2 if unicodedata.east_asian_width(char) in "WF" else 1
        if used + step > limit:
            break
        used += step
        fitted = index + 1
    if fitted >= len(body):
        return len(body)
    window = body[:fitted]
    floor = max(1, int(len(window) * 0.55))
    for index in range(len(window) - 1, floor - 1, -1):
        if window[index] in " ,;":
            return index + 1
    for index in range(len(window) - 1, floor - 1, -1):
        if window[index] in "([{.":
            return index
    return fitted


def _wrap_source_line(text: str, columns: int = WRAP_COLS) -> List[str]:
    """Hard-wrap one source line so the indent plus the body never exceeds ``columns``."""
    expanded = str(text).expandtabs(4).rstrip()
    if not expanded:
        return [""]
    indent = min(len(expanded) - len(expanded.lstrip(" ")), 6)
    prefix = " " * indent
    body = expanded[indent:]
    budget = max(12, columns - indent)
    out: List[str] = []
    while body:
        if _display_width(body) <= budget:
            out.append(prefix + body.rstrip())
            break
        cut = _break_index(body, budget)
        out.append(prefix + body[:cut].rstrip())
        body = body[cut:].lstrip()
    return out or [prefix]


def _score_window(lines: Sequence[str], queries: Sequence[str], size: int,
                  used: set[int] | None = None) -> tuple[int, int, set[int]]:
    """Pick the contiguous source window that best covers the spoken terms.

    ``used`` holds zero-based line indices already shown by another still of the
    same document, so two shots that share a file never land on the same
    paragraph -- the visual-QC repeat rule would (correctly) reject that.
    """
    used = used or set()
    terms: set[str] = set()
    for query in queries:
        terms |= visual_terms(query)
    hits = [len(terms & visual_terms(line)) for line in lines]
    candidates = list(range(0, max(1, len(lines))))
    # Reading order fallback plus a hard cap on reusing an already-shown
    # window: two stills of one file must not land on the same paragraph.
    cap = max(2, size // 10)
    fresh = [start for start in candidates
             if sum(1 for index in range(start, min(start + size, len(lines)))
                    if index in used) <= cap]
    if not fresh:
        fresh = sorted(candidates, key=lambda start: sum(
            1 for index in range(start, min(start + size, len(lines))) if index in used))[:1]
    if not any(hits):
        start = fresh[0]
        return start, min(start + size, len(lines)), set()
    best_start, best_score = fresh[0], float("-inf")
    code_weight = [0.0] * len(lines)
    for index, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"(?:async\s+)?(?:def|class|fn|func|pub\s+fn)\s", stripped):
            code_weight[index] = 1.6
        elif stripped.startswith(("import ", "from ")):
            code_weight[index] = -1.1
    for start in fresh:
        span = hits[start:start + size]
        covered = {index for index, value in enumerate(span) if value}
        score = (sum(span) + 0.5 * len(covered)
                 + sum(code_weight[start:start + size]))
        if score > best_score:
            best_start, best_score = start, score
    end = min(best_start + size, len(lines))
    focus = {best_start + index for index, value in enumerate(hits[best_start:end]) if value}
    return best_start, end, focus


DECLARATION_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class|fn|func|export|pub\s+fn|@|\[|#)")


def _snap_to_declaration(lines: Sequence[str], start: int, end: int, span: int) -> tuple[int, int]:
    """Start the excerpt on a declaration so it reads as a unit, not a fragment."""
    for offset in range(0, 40):
        candidate = start - offset
        if candidate < 0:
            break
        if DECLARATION_RE.match(lines[candidate]):
            return candidate, min(candidate + span, len(lines))
    return start, end


def _font(kind: str, size: int):
    from PIL import ImageFont
    for candidate in FONT_CANDIDATES[kind]:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


@dataclass
class RenderedAnchor:
    """A rendered still plus the geometry the motion planner needs."""

    path: Path
    sha256: str
    width: int
    height: int
    lines: List[Dict[str, Any]] = field(default_factory=list)
    source_lines: List[int] = field(default_factory=list)
    focus_lines: List[int] = field(default_factory=list)
    schema: str = ANCHOR_SCHEMA
    group_size: int = 3

    def layout(self) -> Dict[str, Any]:
        return {"schema": self.schema, "canvas": [self.width, self.height],
                "wrap_cols": WRAP_COLS, "code_font_px": CODE_FONT_PX,
                "group_size": self.group_size,
                "lines": self.lines, "focus_source_lines": self.focus_lines}


def _syntax_runs(text: str) -> List[tuple[str, str]]:
    """Split a code line into (tone, text) runs. Tones: comment/string/word/plain."""
    stripped = text.lstrip()
    if not stripped:
        return [("plain", text)]
    comment = _COMMENT_RE.match(text)
    if comment:
        return [("comment", text)]
    runs: List[tuple[str, str]] = []
    cursor = 0
    for match in _STRING_RE.finditer(text):
        head = text[cursor:match.start()]
        runs.extend(_word_runs(head))
        runs.append(("string", match.group(0)))
        cursor = match.end()
    runs.extend(_word_runs(text[cursor:]))
    return [run for run in runs if run[1]]


def _word_runs(chunk: str) -> List[tuple[str, str]]:
    if not chunk:
        return []
    runs: List[tuple[str, str]] = []
    cursor = 0
    for match in _WORD_RE.finditer(chunk):
        if match.start() > cursor:
            runs.append(("plain", chunk[cursor:match.start()]))
        word = match.group(0)
        if word in KEYWORDS:
            runs.append(("keyword", word))
        elif word.isdigit() or re.fullmatch(r"\d+\.\d+", word):
            runs.append(("number", word))
        else:
            runs.append(("plain", word))
        cursor = match.end()
    if cursor < len(chunk):
        runs.append(("plain", chunk[cursor:]))
    return runs


def title_from_rows(rows: Sequence[Mapping[str, Any]], stem: str) -> str:
    """Name the excerpt from the code actually on the card."""
    texts = [str(row.get("text") or "") for row in rows]
    for text in texts:
        match = re.match(r"\s*(?:async\s+)?(?:def|class|fn|func)\s+([A-Za-z_][A-Za-z0-9_]*)", text)
        if match:
            words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2",
                           match.group(1).replace("_", " ")).strip()
            if words:
                return words[:1].upper() + words[1:]
    for text in texts:
        stripped = text.strip().lstrip("#/-* ")
        if len(stripped) >= 8 and not stripped.startswith(("import ", "from ", "@", '"', "'")):
            return stripped[:1].upper() + stripped[1:40].rstrip(" .,:;")
    return stem.replace("_", " ").replace("-", " ")


def render_anchor(*, source_text: str, filename: str, title: str,
                  repository: str, commit: str, spdx: str,
                  palette: Mapping[str, Any], queries: Sequence[str],
                  out_path: Path, footer: str = "SOURCE TEXT · NOT A LIVE RUNTIME RESULT",
                  exclude_lines: Iterable[int] = ()
                  ) -> RenderedAnchor:
    """Draw one excerpt card and return its pixel geometry."""
    from PIL import Image, ImageDraw

    bg = str(palette.get("bg") or "#F4F2ED")
    surface = str(palette.get("surface") or "#FFFFFF")
    ink = str(palette.get("ink") or "#18232B")
    sub = str(palette.get("sub") or "#5C6970")
    accent = str(palette.get("accent") or "#087FA6")

    raw_lines = str(source_text).splitlines()
    window_size = max(CODE_MAX_LINES * 3, 24)
    used = {int(value) for value in exclude_lines}

    def build(start: int, end: int, focus: set[int]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for index in range(start, min(end, len(raw_lines))):
            for segment_index, segment in enumerate(_wrap_source_line(raw_lines[index])):
                rows.append({"n": index + 1 if segment_index == 0 else None,
                             "text": segment,
                             "focus": index in focus and segment_index == 0})
        return rows

    def trim(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if len(rows) <= CODE_MAX_LINES:
            return rows
        # Open on a declaration when one is available: a card that begins in the
        # middle of a string literal reads as a fragment, not as source.
        for index, row in enumerate(rows[:max(0, len(rows) - CODE_MAX_LINES + 2)]):
            text = str(row.get("text") or "")
            if re.match(r"\s*(?:@|(?:async\s+)?(?:def|class|fn|func)\s)", text):
                if len(rows) - index >= CODE_MAX_LINES - 3:
                    return rows[index:index + CODE_MAX_LINES]
                break
        anchor = next((row for row in rows if row["focus"]), rows[0])
        centre = rows.index(anchor)
        first = max(0, min(centre - CODE_MAX_LINES // 2, len(rows) - CODE_MAX_LINES))
        return rows[first:first + CODE_MAX_LINES]

    # Pick a window that is both topical and, where the file is long enough,
    # disjoint from what another still of this document already shows. Files
    # that cannot supply N disjoint excerpts fall back to the least-overlapping
    # fullest window rather than to a five-line fragment.
    avoid = set(used)
    best: tuple[tuple[int, int, int], List[Dict[str, Any]]] | None = None
    for _ in range(12):
        start, end, focus = _score_window(raw_lines, queries, window_size, avoid)
        snapped = _snap_to_declaration(raw_lines, start, end, window_size)
        if snapped[0] not in avoid:
            start, end = snapped
        candidate = trim(build(start, end, focus))
        numbered = [row for row in candidate if row["n"] is not None]
        visible = {int(row["n"]) - 1 for row in numbered}
        overlap = len(visible & used)
        # A full card matters more than a disjoint one: a five-line excerpt in a
        # nineteen-row body is the dead-background failure this renderer exists
        # to remove, so prefer overlap over emptiness when the file is short.
        key = (1 if len(numbered) >= CODE_MAX_LINES - 5 else 0,
               1 if overlap == 0 else 0, len(numbered), -overlap)
        if best is None or key > best[0]:
            best = (key, candidate)
        if overlap == 0 and len(numbered) >= CODE_MAX_LINES - 4:
            break
        avoid |= set(range(start, end))
    flat = best[1] if best else build(0, min(window_size, len(raw_lines)), set())
    while len(flat) < CODE_MAX_LINES:
        flat.append({"n": None, "text": "", "focus": False})
    shown_title = title or title_from_rows(flat, Path(filename).stem)

    image = Image.new("RGB", (ANCHOR_WIDTH, ANCHOR_HEIGHT), bg)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((PAD_X, CARD_TOP, ANCHOR_WIDTH - PAD_X, CARD_BOTTOM),
                           radius=CARD_RADIUS, fill=surface,
                           outline=str(palette.get("accent2") or accent), width=2)
    draw.rounded_rectangle((TEXT_X, CARD_TOP + 30, TEXT_X + 132, CARD_TOP + 38),
                           radius=4, fill=accent)

    draw.text((TEXT_X, 78), "PINNED SOURCE EXCERPT", font=_font("mono_bold", 22), fill=accent)
    draw.text((TEXT_X, 112), _truncate_columns(shown_title, 26),
              font=_font("sans", 46), fill=ink)
    draw.text((TEXT_X, 176), _truncate_columns(
        f"{filename} · {repository} · {spdx} · {commit[:8]}", 58),
        font=_font("mono", 22), fill=sub)
    draw.line((TEXT_X, RULE_Y, ANCHOR_WIDTH - TEXT_X, RULE_Y), fill=accent, width=2)

    code_font = _font("mono", CODE_FONT_PX)
    code_bold = _font("mono_bold", CODE_FONT_PX)
    char_width = draw.textlength("0" * 40, font=code_font) / 40
    widest = max(_display_width(str(row["text"])) for row in flat)
    block_width = (GUTTER_COLS + widest) * char_width
    block_x = (ANCHOR_WIDTH - block_width) / 2
    gutter_x = block_x
    text_x = block_x + GUTTER_COLS * char_width

    tone_colour = {"comment": sub, "string": sub, "keyword": accent, "number": accent,
                   "plain": ink}
    rows: List[Dict[str, Any]] = []
    y = CODE_TOP_PX
    for row in flat:
        text = str(row["text"])
        if row["n"] is not None:
            draw.text((gutter_x, y), f"{row['n']:>4}", font=code_font, fill=sub)
        cursor = text_x
        for tone, run in _syntax_runs(text):
            font = code_bold if tone == "keyword" else code_font
            draw.text((cursor, y), run, font=font, fill=tone_colour[tone])
            cursor += draw.textlength(run, font=font)
        if row["n"] is not None:
            width = (GUTTER_COLS + max(_display_width(text), 4)) * char_width
            rows.append({"n": row["n"], "text": text, "focus": bool(row["focus"]),
                         "rect": [round(block_x / ANCHOR_WIDTH, 6), round(y / ANCHOR_HEIGHT, 6),
                                  round(width / ANCHOR_WIDTH, 6),
                                  round(CODE_LEADING_PX * 0.86 / ANCHOR_HEIGHT, 6)]})
        y += CODE_LEADING_PX

    draw.line((TEXT_X, FOOTER_RULE_Y, ANCHOR_WIDTH - TEXT_X, FOOTER_RULE_Y), fill=sub, width=1)
    draw.text((TEXT_X, FOOTER_TEXT_Y), footer, font=_font("mono", 19), fill=sub)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", optimize=True)
    return RenderedAnchor(path=out_path, sha256=_sha256(out_path),
                          width=ANCHOR_WIDTH, height=ANCHOR_HEIGHT,
                          lines=rows,
                          source_lines=sorted({row["n"] for row in rows}),
                          focus_lines=sorted({row["n"] for row in flat
                                              if row["focus"] and row["n"] is not None}))


def pick_rects(layout: Mapping[str, Any], text: str, *, max_groups: int = 2,
               exclude: Iterable[str] = ()) -> List[List[float]]:
    """Return up to ``max_groups`` line-window rectangles for a spoken line.

    A window is a run of consecutive rendered rows around the best term match,
    which keeps the camera on one idea instead of the whole excerpt.
    """
    rows = [row for row in (layout.get("lines") or []) if isinstance(row, dict)]
    if not rows:
        return []
    terms = visual_terms(text)
    scored = []
    for index, row in enumerate(rows):
        overlap = terms & visual_terms(str(row.get("text") or ""))
        if overlap:
            scored.append((len(overlap), index))
    scored.sort(key=lambda item: (-item[0], item[1]))
    group_size = int(layout.get("group_size") or 3)
    reach = max(0, group_size // 2)
    seen = {str(item) for item in exclude}
    out: List[List[float]] = []
    used: set[int] = set()
    for _, centre in scored:
        if len(out) >= max_groups:
            break
        if any(abs(centre - index) <= reach for index in used):
            continue
        group = [index for index in range(centre - reach, centre + reach + 1)
                 if 0 <= index < len(rows)]
        if not group:
            continue
        left = min(rows[index]["rect"][0] for index in group)
        right = max(rows[index]["rect"][0] + rows[index]["rect"][2] for index in group)
        top = min(rows[index]["rect"][1] for index in group)
        bottom = max(rows[index]["rect"][1] + rows[index]["rect"][3] for index in group)
        rect = [round(left, 6), round(top, 6), round(right - left, 6), round(bottom - top, 6)]
        key = str(rect)
        if key in seen:
            continue
        seen.add(key)
        used.update(group)
        out.append(rect)
    return out


FLOW_SCHEMA = "contentops.concept-anchor/v1"


def render_flow_anchor(*, title: str, steps: Sequence[str], palette: Mapping[str, Any],
                       out_path: Path, eyebrow: str = "CONCEPT DIAGRAM",
                       note: str = "SCHEMATIC · NOT A RUNTIME RESULT",
                       provenance: str = "") -> RenderedAnchor:
    """Draw a three-stage schematic card at the same canvas as the code card.

    The explanatory account is vector-led, but Huashu's 3b1b and whiteboard
    grammars lay one equation or one icon into a 1080x1920 frame and leave
    85-90% of it empty -- measured on the first re-render. What the account
    actually needs is a still that fills the frame *and* is drawn rather than
    photographed, so the schematic is composed here at card scale and the t2
    camera moves between its stages.
    """
    from PIL import Image, ImageDraw

    bg = str(palette.get("bg") or "#E9EDEF")
    surface = str(palette.get("surface") or "#F9FBFA")
    ink = str(palette.get("ink") or "#202B31")
    sub = str(palette.get("sub") or "#65747A")
    accent = str(palette.get("accent") or "#157F8B")
    accent2 = str(palette.get("accent2") or "#AABDC1")

    stages = [str(item) for item in steps][:3] or ["输入"]
    image = Image.new("RGB", (ANCHOR_WIDTH, ANCHOR_HEIGHT), bg)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((PAD_X, CARD_TOP, ANCHOR_WIDTH - PAD_X, CARD_BOTTOM),
                           radius=CARD_RADIUS, fill=surface, outline=accent2, width=2)
    draw.rounded_rectangle((TEXT_X, CARD_TOP + 30, TEXT_X + 132, CARD_TOP + 38),
                           radius=4, fill=accent)
    draw.text((TEXT_X, 78), eyebrow, font=_font("mono_bold", 22), fill=accent)
    draw.text((TEXT_X, 112), _truncate_columns(title, 24), font=_font("sans", 50), fill=ink)
    if provenance:
        draw.text((TEXT_X, 186), _truncate_columns(provenance, 56),
                  font=_font("mono", 21), fill=sub)
    draw.line((TEXT_X, 232, ANCHOR_WIDTH - TEXT_X, 232), fill=accent, width=2)

    top, node_h, gap = 292, 330, 118
    left, right = 74, ANCHOR_WIDTH - 74
    rows: List[Dict[str, Any]] = []
    for index, label in enumerate(stages):
        y0 = top + index * (node_h + gap)
        y1 = y0 + node_h
        draw.rounded_rectangle((left, y0, right, y1), radius=22, fill=bg, outline=accent2,
                               width=2)
        draw.rounded_rectangle((left, y0, left + 14, y1), radius=7, fill=accent)
        draw.text((left + 46, y0 + 40), f"{index + 1:02d}", font=_font("mono_bold", 30),
                  fill=accent)
        lines = _wrap_source_line(label, 16)
        draw.text((left + 46, y0 + 96), _truncate_columns(lines[0], 18),
                  font=_font("sans", 54), fill=ink)
        if len(lines) > 1:
            draw.text((left + 46, y0 + 166), _truncate_columns(
                "".join(lines[1:]), 22), font=_font("sans_regular", 34), fill=sub)
        if index < len(stages) - 1:
            mid = (left + right) // 2
            draw.line((mid, y1 + 12, mid, y1 + gap - 24), fill=accent2, width=6)
            draw.polygon([(mid - 18, y1 + gap - 30), (mid + 18, y1 + gap - 30),
                          (mid, y1 + gap - 4)], fill=accent)
        rows.append({"n": index + 1, "text": label,
                     "rect": [round(left / ANCHOR_WIDTH, 6), round(y0 / ANCHOR_HEIGHT, 6),
                              round((right - left) / ANCHOR_WIDTH, 6),
                              round(node_h / ANCHOR_HEIGHT, 6)]})

    draw.line((TEXT_X, FOOTER_RULE_Y, ANCHOR_WIDTH - TEXT_X, FOOTER_RULE_Y), fill=sub, width=1)
    draw.text((TEXT_X, FOOTER_TEXT_Y), note, font=_font("mono", 19), fill=sub)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG", optimize=True)
    return RenderedAnchor(path=out_path, sha256=_sha256(out_path),
                          width=ANCHOR_WIDTH, height=ANCHOR_HEIGHT, lines=rows,
                          source_lines=[], focus_lines=[], schema=FLOW_SCHEMA,
                          group_size=1)


__all__ = ["ANCHOR_HEIGHT", "ANCHOR_SCHEMA", "ANCHOR_WIDTH", "FLOW_SCHEMA",
           "RenderedAnchor", "WRAP_COLS", "pick_rects", "render_anchor",
           "render_flow_anchor", "title_from_rows", "visual_terms"]
