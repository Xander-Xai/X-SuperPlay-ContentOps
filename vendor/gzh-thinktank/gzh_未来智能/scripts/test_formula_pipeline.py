#!/usr/bin/env python3
"""Regression tests for inline-code formula detection."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from formula_pipeline import find_unrendered_math_literals  # noqa: E402


def test_plain_audit_identifiers_are_not_math() -> None:
    text = "`principal_id` `trace_id` `approval_id` `result_digest`"
    assert find_unrendered_math_literals(text) == []


def test_shape_identifiers_are_still_math() -> None:
    text = "`d_model` `W_O` `n_q`"
    values = [item["value"] for item in find_unrendered_math_literals(text)]
    assert values == ["d_model", "W_O", "n_q"]
