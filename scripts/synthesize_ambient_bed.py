#!/usr/bin/env python3
"""Synthesise a quiet ambient bed from scratch.

No sample library and no provider: three detuned sines, a slow amplitude LFO
and a low-passed noise floor. The result is deterministic for a seed, carries
no licence obligation, and is written at a level that sits at least 18 dB under
the voice.

Usage::

    python scripts/synthesize_ambient_bed.py --duration 45 --out work/bgm.wav
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RATE = 32000
#: Peak target, about -24 dBFS. The voice peaks near -1.5 dBFS, so the bed sits
#: more than 18 dB below it before any ducking.
PEAK = 0.06


def build(duration: float, seed: int) -> np.ndarray:
    n = int(round(duration * RATE))
    t = np.arange(n) / RATE
    rng = np.random.default_rng(seed)
    # A minor-ish drone: 55, 82.5, 110 Hz, slightly detuned.
    layers: List[np.ndarray] = []
    for freq, detune, gain, lfo in ((55.0, 0.06, 1.0, 0.07),
                                    (82.5, -0.05, 0.55, 0.11),
                                    (110.0, 0.03, 0.30, 0.05)):
        lfo_wave = 0.65 + 0.35 * np.sin(2 * math.pi * lfo * t + rng.uniform(0, 6.28))
        layers.append(gain * lfo_wave * np.sin(2 * math.pi * (freq + detune) * t))
    # Low-passed noise floor: a moving average over white noise.
    noise = rng.normal(0, 1, n)
    kernel = np.ones(256) / 256
    noise = np.convolve(noise, kernel, mode="same")
    layers.append(0.06 * noise / (np.max(np.abs(noise)) or 1))
    bed = np.sum(layers, axis=0)
    # 1.5 s fade in and out so a cut never starts on a click.
    fade = int(1.5 * RATE)
    bed[:fade] *= np.linspace(0, 1, fade)
    bed[-fade:] *= np.linspace(1, 0, fade)
    bed = bed / (np.max(np.abs(bed)) or 1) * PEAK
    return bed


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    bed = build(args.duration, args.seed)
    pcm = (np.clip(bed, -1, 1) * 32767).astype("<i2")
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())

    receipt = {
        "schema": "contentops.ambient-bed/v1",
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "path": f"project://{out.relative_to(ROOT).as_posix()}" if out.is_relative_to(ROOT) else str(out),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "duration_s": round(args.duration, 3),
        "sample_rate_hz": RATE,
        "channels": 1,
        "peak_dbfs": round(20 * math.log10(PEAK), 1),
        "seed": args.seed,
        "licence": "none required — synthesised from sine waves and seeded noise",
        "style": "dark ambient drone, no drums, slow LFO",
        "policy": "none required — synthesised here, no sample library",
    }
    out.with_suffix(".json").write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
    print(json.dumps({"status": "OK", "path": str(out), "peak_dbfs": receipt["peak_dbfs"],
                      "duration_s": receipt["duration_s"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
