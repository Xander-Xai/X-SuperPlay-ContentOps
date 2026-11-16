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

PROPS_ENV = "CONTENTOPS_MANIM_PROPS"


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
    frame = Rectangle(
        width=config.frame_width + 1,
        height=config.frame_height + 1,
        fill_color=color,
        fill_opacity=1,
        stroke_width=0,
    )
    scene.add(frame)


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

        formula = VGroup()
        for index, term in enumerate(terms):
            color = palette["accent"] if index == len(terms) - 1 else palette["surface"]
            token = Text(term, font=_font(props), font_size=34, color=color)
            if formula:
                token.next_to(formula, RIGHT, buff=0.18)
            else:
                token.move_to(RIGHT * 0.3 + UP * 0.9)
            self.play(FadeIn(token, shift=UP * 0.2), run_time=max(0.12, term_time))
            formula.add(token)

        legend = VGroup()
        for item in variables:
            symbol = str(item.get("symbol") or "").strip()
            meaning = str(item.get("meaning") or "").strip()
            line = Text(
                f"{symbol}  =  {meaning}",
                font=_font(props),
                font_size=22,
                color=palette["sub"],
            )
            if legend:
                line.next_to(legend, DOWN, buff=0.28)
            else:
                line.move_to(DOWN * 0.55)
            self.play(FadeIn(line), run_time=max(0.12, var_time))
            legend.add(line)

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

        # Token row with single-direction arrows (an allowed DNA motion).
        token_group = VGroup()
        for index, token in enumerate(tokens):
            box = RoundedRectangle(
                width=1.5, height=0.55, corner_radius=0.1,
                fill_color=palette["bg"], fill_opacity=1,
                stroke_color=palette["accent"], stroke_width=2,
            )
            caption = Text(token, font=_font(props), font_size=16, color=palette["surface"])
            cell = VGroup(box, caption)
            if token_group:
                cell.next_to(token_group, RIGHT, buff=0.45)
            else:
                cell.move_to(UP * 2.1)
            self.play(FadeIn(cell), run_time=max(0.1, token_time))
            token_group.add(cell)
            if index < len(tokens) - 1:
                arrow = Arrow(
                    token_group[-1].get_right() + RIGHT * 0.05,
                    token_group[-1].get_right() + RIGHT * 0.35,
                    color=palette["accent"], stroke_width=2, buff=0,
                )
                self.play(FadeIn(arrow), run_time=0.12)

        # Matrix cells: opacity is proportional to the trusted weight value.
        grid = VGroup()
        flat_max = max((abs(c) for row in matrix for c in row), default=1.0) or 1.0
        for r, row in enumerate(matrix):
            cells = VGroup()
            for c, value in enumerate(row):
                ratio = min(1.0, max(0.0, abs(value) / flat_max))
                cell = Rectangle(
                    width=1.15, height=0.62,
                    fill_color=palette["accent"], fill_opacity=0.12 + 0.68 * ratio,
                    stroke_color=palette["bg"], stroke_width=1,
                )
                number = Text(
                    f"{value:.2f}", font=_font(props), font_size=15, color=palette["surface"],
                )
                cells.add(VGroup(cell, number))
            cells.arrange(RIGHT, buff=0.12)
            if grid:
                cells.next_to(grid, DOWN, buff=0.18)
            else:
                cells.move_to(DOWN * 0.7)
            for cell in cells:
                self.play(FadeIn(cell), run_time=max(0.06, cell_time))
            grid.add(cells)

        if labels:
            note = Text(
                " · ".join(labels[:6]),
                font=_font(props), font_size=16, color=palette["sub"],
            )
            note.to_edge(DOWN, buff=0.75)
            self.play(FadeIn(note), run_time=0.3)

        self.wait(max(0.2, total - 0.4 - token_time * len(tokens) - cell_time * len(matrix) * max(1, len(tokens))))
        _banner(self, props, palette["accent"], palette["surface"])
