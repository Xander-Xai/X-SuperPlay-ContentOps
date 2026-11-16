#!/usr/bin/env python3
"""Two parameterized Manim scenes for ContentOps short math/attention shots.

These are Manim ``Scene`` classes rendered by ``scripts/manim_render.py`` from an
isolated venv through the official ``python -m manim render`` CLI. They deliberately
use ONLY Manim's Pango ``Text`` and vector primitives (Rectangle / VGroup / Arrow):

* No MathTex/LaTeX. On Windows an elevated-privilege LaTeX pass hangs on the
  first ``\\documentclass`` call; Pango Text renders the same symbols in seconds.
* No colour literals. Every colour is resolved at runtime from ``palette`` in the
  props file, which ``animation_backend.palette_from_dna`` derives from
  ``config/accounts/<account>.json`` ``brand.palette``. ``style_variants`` never
  reaches here (plan_clip rejects it).
* No inventing algorithms. Formula ``terms`` / ``variables`` and attention
  ``matrix`` / ``tokens`` are taken verbatim from the trusted spec props. The
  scene animates the supplied values; it does not compute softmax or a formula.

Props are handed to the scene through the ``CONTENTOPS_MANIM_PROPS`` environment
variable, which points to a project-contained JSON file written by the render
entry. There is no network access and no global state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Arrow,
    FadeIn,
    Rectangle,
    RoundedRectangle,
    Scene,
    Text,
    VGroup,
    config,
)

# A true 9:16 logical frame. Manim's default frame is 16:9; rendering that at
# 1080x1920 pillarboxes it into black bars. Setting the frame ratio here makes
# the vector frame match the target pixel canvas, so the DNA background fills
# the whole vertical shot. The render entry passes -r 1080,1920 --fps 30.
config.frame_height = 8.0
config.frame_width = 8.0 * (1080.0 / 1920.0)  # 4.5

PROPS_ENV = "CONTENTOPS_MANIM_PROPS"
# Safe content bounds in the 4.5 x 8 portrait frame.
_HALF_W = config.frame_width / 2.0
_HALF_H = config.frame_height / 2.0


def _load_props() -> Dict[str, Any]:
    raw = os.environ.get(PROPS_ENV)
    if not raw:
        raise RuntimeError(f"{PROPS_ENV} is not set; refusing to render an unbound scene")
    payload = json.loads(Path(raw).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("manim props file must contain a JSON object")
    return payload


def _hex(value: str, fallback: str) -> str:
    text = str(value or "").strip()
    return text if text.startswith("#") and len(text) == 7 else fallback


def _palette(props: Dict[str, Any]) -> Dict[str, str]:
    palette = props.get("palette") or {}
    if not isinstance(palette, dict):
        palette = {}
    # All colours come from brand.palette via the render entry. The fallbacks
    # are only reached if a malformed props file omits a key; they are neutral
    # greys, never a second brand palette.
    return {
        "bg": _hex(palette.get("bg"), "#0F1117"),
        "surface": _hex(palette.get("surface"), "#F9FBFA"),
        "ink": _hex(palette.get("ink"), "#F9FBFA"),
        "accent": _hex(palette.get("accent"), "#38BDF8"),
        "sub": _hex(palette.get("sub"), "#65747A"),
    }


def _font(props: Dict[str, Any]) -> str:
    # DNA caption font; Pango falls back gracefully if the glyph is unavailable.
    return str(props.get("font") or "Noto Sans CJK SC")


def _background(scene: Scene, color: str) -> None:
    """Fill the whole frame with the DNA background colour."""
    scene.camera.background_color = color
    frame = Rectangle(
        width=config.frame_width + 0.02,
        height=config.frame_height + 0.02,
        fill_color=color,
        fill_opacity=1,
        stroke_width=0,
    )
    scene.add(frame)


def _fit_width(mobject, target: float):
    """Scale a group down if it is wider than the safe portrait frame."""
    if mobject.width > target and mobject.width > 0:
        mobject.scale(target / mobject.width)
    return mobject


def _banner(scene: Scene, props: Dict[str, Any], color: str, fg: str) -> None:
    text = str(props.get("testBanner") or "").strip()
    if not text:
        return
    label = Text(text, font=_font(props), font_size=18, color=fg)
    label.to_edge(DOWN, buff=0.35)
    scene.play(FadeIn(label), run_time=0.3)


def _title(scene: Scene, props: Dict[str, Any], palette: Dict[str, str]) -> None:
    text = str(props.get("title") or "数学示意").strip()
    label = Text(text, font=_font(props), font_size=30, color=palette["surface"])
    label.to_edge(UP, buff=0.5)
    scene.play(FadeIn(label), run_time=0.4)


class MathFormulaReveal(Scene):
    """Reveal a trusted formula term-by-term, then its variable explanations."""

    def construct(self) -> None:
        props = _load_props()
        palette = _palette(props)
        _background(self, palette["bg"])
        _title(self, props, palette)

        terms: List[str] = [str(t) for t in (props.get("terms") or [])]
        variables: List[Dict[str, Any]] = [
            v for v in (props.get("variables") or []) if isinstance(v, dict)
        ]
        total = float(props.get("duration_s") or 4.0)
        # Budget: title ~0.4s already spent; split the rest between terms and
        # variables, leaving a shorthold at the end.
        span = max(1.2, total - 0.9)
        term_time = (span * 0.55) / max(1, len(terms))
        var_time = (span * 0.40) / max(1, len(variables))

        # Pre-pack terms into rows by measured width, then reveal one by one.
        # Computing the layout first avoids any scratch VGroup reparenting and
        # guarantees no term crosses the safe portrait width.
        limit = config.frame_width - 0.5
        token_mobs: List[Text] = []
        for index, term in enumerate(terms):
            color = palette["accent"] if index == len(terms) - 1 else palette["surface"]
            token = Text(term, font=_font(props), font_size=24, color=color)
            if token.width > limit:
                token.scale(limit / token.width)
            token_mobs.append(token)

        rows: List[List[Text]] = []
        current: List[Text] = []
        current_w = 0.0
        for token in token_mobs:
            added = current_w + token.width + (0.1 if current else 0.0)
            if current and added > limit:
                rows.append(current)
                current, current_w = [], 0.0
                added = token.width
            current.append(token)
            current_w = added
        if current:
            rows.append(current)

        y = UP * 1.7
        for row in rows:
            row_group = VGroup(*row).arrange(RIGHT, buff=0.1)
            row_group.move_to(y)
            y += DOWN * 0.7
        for row in rows:
            for token in row:
                self.play(FadeIn(token, shift=UP * 0.2), run_time=max(0.12, term_time))

        legend = VGroup()
        for item in variables:
            symbol = str(item.get("symbol") or "").strip()
            meaning = str(item.get("meaning") or "").strip()
            line = Text(
                f"{symbol} = {meaning}",
                font=_font(props),
                font_size=20,
                color=palette["sub"],
            )
            _fit_width(line, config.frame_width - 0.4)
            if legend:
                line.next_to(legend, DOWN, buff=0.3)
            else:
                line.move_to(DOWN * 1.4)
            self.play(FadeIn(line), run_time=max(0.12, var_time))
            legend.add(line)
        legend.move_to(DOWN * 1.6)

        self.wait(max(0.2, total - 0.4 - term_time * len(terms) - var_time * len(variables)))
        _banner(self, props, palette["accent"], palette["surface"])


class AttentionMatrixFlow(Scene):
    """Animate a trusted attention matrix and single-direction token flow."""

    def construct(self) -> None:
        props = _load_props()
        palette = _palette(props)
        _background(self, palette["bg"])
        _title(self, props, palette)

        tokens: List[str] = [str(t) for t in (props.get("tokens") or [])]
        matrix: List[List[float]] = [
            [float(cell) for cell in row] for row in (props.get("matrix") or [])
        ]
        labels: List[str] = [str(label) for label in (props.get("labels") or [])]
        total = float(props.get("duration_s") or 4.0)
        span = max(1.2, total - 0.9)
        token_time = (span * 0.30) / max(1, len(tokens))
        cell_time = (span * 0.55) / max(1, len(matrix) * max(1, len(tokens)))

        # Token row with single-direction arrows (an allowed DNA motion). Sized
        # so that even the maximum of 12 tokens stays inside the portrait frame.
        n_tokens = max(1, len(tokens))
        box_w = min(0.9, (config.frame_width - 0.4 - 0.12 * (n_tokens - 1)) / n_tokens)
        token_group = VGroup()
        for index, token in enumerate(tokens):
            box = RoundedRectangle(
                width=box_w, height=0.5, corner_radius=0.08,
                fill_color=palette["bg"], fill_opacity=1,
                stroke_color=palette["accent"], stroke_width=1.5,
            )
            caption = Text(token, font=_font(props), font_size=14, color=palette["surface"])
            # Constrain BOTH axes so a wide CJK glyph never dwarf its box.
            if caption.width > box_w - 0.08:
                caption.scale((box_w - 0.08) / caption.width)
            if caption.height > 0.34:
                caption.scale(0.34 / caption.height)
            cell = VGroup(box, caption)
            if token_group:
                cell.next_to(token_group, RIGHT, buff=0.12)
            else:
                cell.move_to(UP * 2.6)
            self.play(FadeIn(cell), run_time=max(0.1, token_time))
            token_group.add(cell)
        token_group.move_to(UP * 2.6)

        # Matrix cells: cell width derived from token count so N columns always
        # fit the safe frame; opacity is proportional to the trusted weight.
        cell_w = min(0.85, (config.frame_width - 0.4 - 0.1 * (n_tokens - 1)) / n_tokens)
        grid = VGroup()
        flat_max = max((abs(c) for row in matrix for c in row), default=1.0) or 1.0
        for r, row in enumerate(matrix):
            cells = VGroup()
            for c, value in enumerate(row):
                ratio = min(1.0, max(0.0, abs(value) / flat_max))
                rect = Rectangle(
                    width=cell_w, height=0.6,
                    fill_color=palette["accent"], fill_opacity=0.12 + 0.68 * ratio,
                    stroke_color=palette["bg"], stroke_width=1,
                )
                number = Text(
                    f"{value:.2f}", font=_font(props), font_size=13, color=palette["surface"],
                )
                number.scale_to_fit_width(cell_w - 0.04)
                cells.add(VGroup(rect, number))
            cells.arrange(RIGHT, buff=0.1)
            if grid:
                cells.next_to(grid, DOWN, buff=0.16)
            else:
                cells.move_to(DOWN * 0.5)
            for cell in cells:
                self.play(FadeIn(cell), run_time=max(0.06, cell_time))
            grid.add(cells)
        grid.move_to(DOWN * 0.5)

        if labels:
            note = Text(
                "  ".join(labels[:3]),
                font=_font(props), font_size=14, color=palette["sub"],
            )
            _fit_width(note, config.frame_width - 0.3)
            note.to_edge(DOWN, buff=0.6)
            self.play(FadeIn(note), run_time=0.3)

        self.wait(max(0.2, total - 0.4 - token_time * len(tokens) - cell_time * len(matrix) * max(1, len(tokens))))
        _banner(self, props, palette["accent"], palette["surface"])
