"""Idempotency fingerprint for generated narration.

A fingerprint exists so that re-running a build does not silently spend quota
and does not silently keep a stale asset. It must therefore cover every input
that can change the produced audio:

- who produced it: provider, product, plan
- what produced it: model, voice, speed, text-normalisation flag
- what was said: the **spoken** text, not the display text
- how it was corrected: the lexicon version and rule digest
- how it was finished: the normalisation target

The display text is deliberately excluded from the spoken-content part of the
digest but recorded in the receipt, because changing only what the reader sees
must not force a new generation, while changing what the voice says must.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

__all__ = ["speech_fingerprint", "sha256_text", "sha256_file"]


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def speech_fingerprint(
    *,
    provider: str,
    product: str,
    plan: str,
    model: str,
    voice: str,
    spoken_text: str,
    lexicon_component: str,
    speed: float | None = None,
    text_normalization: bool = True,
    normalisation_target_lufs: float | None = None,
    normalisation_true_peak_db: float | None = None,
) -> str:
    """Return a stable digest of every input that affects the produced audio."""
    payload: Dict[str, Any] = {
        "provider": provider,
        "product": product,
        "plan": plan,
        "model": model,
        "voice": voice,
        "spoken_sha256": sha256_text(spoken_text),
        "lexicon": lexicon_component,
        "speed": speed,
        "text_normalization": bool(text_normalization),
        "norm_lufs": normalisation_target_lufs,
        "norm_tp": normalisation_true_peak_db,
    }
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()