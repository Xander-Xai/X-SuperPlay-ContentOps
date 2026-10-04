"""Deterministic local media for proving the convergence path. Never evidence.

What these are for
------------------
The M4.5 acceptance item is one **technical integration** output proving
``registry -> manifest -> compose -> final.mp4 -> final QC``. That needs media,
and generating it from a provider would spend weekly quota to test orchestration
code. So these builders synthesise media locally and deterministically.

What these are not
------------------
They are **not** real business evidence, and nothing here pretends otherwise:

- every file is drawn by a deterministic function, so it is obviously synthetic to
  anyone who looks at it
- each receipt declares ``fixture: true`` and names the builder that made it
- the manifest carries the same statement at the top level
- ``production_ready`` is ``false`` and ``human_review`` is pending on every one

A screenshot-shaped fixture is the one genuinely awkward case, because it has to
occupy the evidence-capable path for the routing to be exercised. It is therefore
labelled as a **fixture** in three independent places — the receipt, the manifest
and the integration report — rather than presented as a capture.

Every ffmpeg invocation goes through :mod:`process_utils`, so nothing here can
flash a console window on Windows.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from contentops.media.fingerprint import sha256_file

__all__ = [
    "FIXTURE_BANNER",
    "FIXTURE_NOTE",
    "build_narration_fixture",
    "build_screenshot_fixture",
    "build_shot_fixture",
    "write_fixture_receipt",
]

#: Burned into every fixture image, so a file that escapes its directory still
#: announces what it is.
FIXTURE_BANNER = "CONTENTOPS M4.5 TECHNICAL FIXTURE"

FIXTURE_NOTE = (
    "Deterministic local placeholder produced by src/contentops/media/"
    "fixtures_local.py. NOT a real business capture, NOT Founder approved, and "
    "NOT evidence of anything. It exists to prove the registry -> manifest -> "
    "compose -> QC path executes end to end without spending provider quota."
)

#: Composition resolution. Matches what ``qc_video.py`` grades against, so a
#: technical integration is not failed for being the wrong size.
PORTRAIT_WIDTH = 1080
PORTRAIT_HEIGHT = 1920


def _fixture_fingerprint(kind: str, seed: str) -> str:
    payload = json.dumps(
        {"fixture": kind, "seed": seed, "w": PORTRAIT_WIDTH, "h": PORTRAIT_HEIGHT},
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_fixture_receipt(
    *,
    path: Path,
    payload: Dict[str, Any],
) -> Path:
    """Write a fixture receipt next to its asset, matching the sidecar convention."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return target


def _base_receipt(
    *,
    kind: str,
    seed: str,
    provider: str,
    fingerprint: str,
    digest: str,
    canonical_path: str,
    technical_qc: Dict[str, Any],
) -> Dict[str, Any]:
    """The fields every fixture receipt shares.

    Note what is absent: no credential class claiming a subscription key that was
    never used, no quota snapshot, no task reference. A local draw consumed no
    plan entitlement, and a receipt that implied otherwise would be a small lie in
    the one place where lies are most expensive.
    """
    return {
        "provider": provider,
        "product": "contentops_local",
        "plan": "deterministic_fixture",
        "transport": "local_deterministic",
        "transport_version": "1",
        "fixture": True,
        "fixture_kind": kind,
        "fixture_note": FIXTURE_NOTE,
        "fingerprint": fingerprint,
        "canonical_path": canonical_path,
        "output_sha256": digest,
        "technical_qc": technical_qc,
        "billing_mode": "subscription",
        "payg_allowed": False,
        "credit_pack_allowed": False,
        "quota_consumed": False,
        "attempt": 1,
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }


# --- images -----------------------------------------------------------------


def build_screenshot_fixture(
    path: Path, *, seed: str = "shot-01", label: str = "fixture capture"
) -> Tuple[Path, Path, str]:
    """Draw a screenshot-shaped fixture and its receipt.

    Occupies the evidence-capable routing path so the real-material executor is
    genuinely exercised. Labelled as a fixture three times over, because
    screenshot-shaped bytes are exactly the thing that must never be mistaken for
    a capture.
    """
    from PIL import Image, ImageDraw

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (PORTRAIT_WIDTH, PORTRAIT_HEIGHT), (18, 22, 34))
    draw = ImageDraw.Draw(image)

    # A window chrome silhouette, so the file is unmistakably a UI placeholder.
    draw.rectangle([0, 0, PORTRAIT_WIDTH, 150], fill=(32, 40, 60))
    draw.text((36, 60), f"{FIXTURE_BANNER} — {label}", fill=(250, 210, 120))
    draw.rectangle([60, 210, PORTRAIT_WIDTH - 60, 700], outline=(90, 110, 150), width=4)
    draw.text((90, 250), "this panel is a deterministic placeholder", fill=(200, 210, 230))
    for row in range(6):
        y = 780 + row * 90
        draw.rectangle([90, y, PORTRAIT_WIDTH - 200 - row * 40, y + 44],
                       fill=(52, 66, 96))
    draw.rectangle([60, 1420, PORTRAIT_WIDTH - 60, 1560], fill=(52, 40, 70))
    draw.text((90, 1470), "seed: " + seed, fill=(226, 200, 240))
    draw.text(
        (36, PORTRAIT_HEIGHT - 90),
        "NOT a real capture. NOT evidence.",
        fill=(255, 150, 150),
    )
    image.save(target, format="PNG")

    fingerprint = _fixture_fingerprint("screenshot", seed)
    digest = sha256_file(target)
    receipt = _base_receipt(
        kind="screenshot_fixture",
        seed=seed,
        provider="contentops_local_fixture",
        fingerprint=fingerprint,
        digest=digest,
        canonical_path=str(target),
        technical_qc={
            "approved": True,
            "reasons": [],
            "container": "PNG",
            "width": PORTRAIT_WIDTH,
            "height": PORTRAIT_HEIGHT,
            "decodable": True,
        },
    )
    # This is a fixture, so it is explicitly NOT generated (nothing was inferred)
    # and NOT evidence-capable (the bytes prove nothing). The registration in the
    # execution layer records the *route* being exercised; these flags record what
    # the bytes actually are, and they disagree on purpose.
    receipt["generated"] = False
    receipt["evidence_capable"] = False
    receipt["routed_as"] = "SCREENSHOT"
    receipt["routing_note"] = (
        "Routed through the evidence-capable path so the real-material executor is "
        "exercised. The bytes are a fixture, so evidence_capable is recorded false "
        "here. A real run would carry a genuine capture and register with "
        "evidence_capable=true."
    )
    receipt_path = write_fixture_receipt(
        path=target.with_name(target.name + ".receipt.json"), payload=receipt
    )
    return target, receipt_path, fingerprint


def build_shot_fixture(
    path: Path, *, seed: str = "h3-hook", seconds: int = 6
) -> Tuple[Path, Path, str]:
    """Render a deterministic clip **with** an audio track.

    The audio is deliberate. H3 returns audio nobody asked for, and that is the
    whole reason :class:`AudioPolicy` exists, so a fixture that had no audio would
    make the ``MUTE`` / ``REPLACE`` postcondition vacuous. This fixture reproduces
    the condition being handled.
    """
    from process_utils import hidden_run

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run(
        [
            "ffmpeg", "-y", "-v", "error", "-nostdin",
            "-f", "lavfi",
            "-i", (
                f"testsrc=size={PORTRAIT_WIDTH}x{PORTRAIT_HEIGHT}:rate=24:"
                f"duration={seconds}"
            ),
            "-f", "lavfi",
            "-i", f"sine=frequency=220:duration={seconds}",
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", "96k", "-shortest",
            str(target),
        ],
        timeout=900,
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(
            "could not render the shot fixture: "
            f"{(result.stderr or '').strip()[-300:] or 'ffmpeg reported errors'}"
        )

    fingerprint = _fixture_fingerprint("shot", seed)
    digest = sha256_file(target)
    receipt = _base_receipt(
        kind="video_fixture",
        seed=seed,
        provider="contentops_local_fixture",
        fingerprint=fingerprint,
        digest=digest,
        canonical_path=str(target),
        technical_qc={
            "approved": True,
            "reasons": [],
            "container": "mp4",
            "codec": "h264",
            "width": PORTRAIT_WIDTH,
            "height": PORTRAIT_HEIGHT,
            "duration_s": float(seconds),
            "fps": 24.0,
            "has_audio": True,
            "audio_codec": "aac",
            "decodable": True,
        },
    )
    receipt.update({
        "schema": "contentops.video-receipt/v1",
        "model": "FIXTURE",
        "mode": "FIXTURE",
        "requested_duration_s": int(seconds),
        "actual_duration_s": float(seconds),
        "requested_resolution": "FIXTURE",
        "actual_width": PORTRAIT_WIDTH,
        "actual_height": PORTRAIT_HEIGHT,
        "audio_policy": "REPLACE",
        "audio_stream_present": True,
        "task_created": False,
        "task_ref_hash": "",
        "generated": True,
        "evidence_capable": False,
        "unrequested_audio_note": (
            "Carries an audio track nobody asked for, exactly as a real H3 shot "
            "does. That is the condition AudioPolicy exists to handle, so a "
            "fixture without one would make the MUTE/REPLACE postcondition "
            "vacuous."
        ),
    })
    receipt_path = write_fixture_receipt(
        path=target.with_name(target.name + ".receipt.json"), payload=receipt
    )
    return target, receipt_path, fingerprint


# --- narration --------------------------------------------------------------


def build_narration_fixture(
    path: Path, *, seed: str = "narration-01", seconds: float = 6.0
) -> Tuple[Path, Path, str]:
    """Render a deterministic narration WAV and a **speech-shaped** receipt.

    Speech-shaped means: no ``schema`` field and no ``generated`` /
    ``evidence_capable`` fields. Those absences are the real schema, and a fixture
    that added them would make the speech adapter's handling of them untested and
    would imply narration has an evidence boundary it does not have.

    The receipt's digest fields are ``raw_sha256`` and ``normalized_sha256`` for
    the same reason: that is what a speech receipt records, so the adapter's
    two-candidate digest lookup is genuinely exercised.
    """
    from process_utils import hidden_run

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 32000
    result = hidden_run(
        [
            "ffmpeg", "-y", "-v", "error", "-nostdin",
            "-f", "lavfi",
            "-i", f"sine=frequency=180:sample_rate={sample_rate}:duration={seconds}",
            "-ac", "1", "-c:a", "pcm_s16le", str(target),
        ],
        timeout=300,
    )
    if result.returncode != 0 or not target.is_file():
        raise RuntimeError(
            "could not render the narration fixture: "
            f"{(result.stderr or '').strip()[-300:] or 'ffmpeg reported errors'}"
        )

    fingerprint = _fixture_fingerprint("speech", seed)
    digest = sha256_file(target)
    receipt: Dict[str, Any] = {
        "provider": "contentops_local_fixture",
        "product": "contentops_local",
        "plan": "deterministic_fixture",
        "transport": "local_deterministic",
        "transport_version": "1",
        "fixture": True,
        "fixture_kind": "speech_fixture",
        "fixture_note": FIXTURE_NOTE,
        "model": "FIXTURE",
        "voice": "fixture_tone",
        "lexicon_version": "none",
        "fingerprint": fingerprint,
        "raw_path": str(target),
        "normalized_path": str(target),
        "raw_sha256": digest,
        "normalized_sha256": digest,
        "display_text_sha256": hashlib.sha256(
            f"fixture narration {seed}".encode("utf-8")
        ).hexdigest(),
        "spoken_text_sha256": hashlib.sha256(
            f"fixture narration {seed}".encode("utf-8")
        ).hexdigest(),
        "technical_qc": {
            "approved": True,
            "reasons": [],
            "duration_s": seconds,
            "sample_rate_hz": sample_rate,
            "channels": 1,
            "codec": "pcm_s16le",
        },
        "semantic_qc": {
            "approved": False,
            "reasons": [
                "a tone is not speech; semantic review is not applicable to a "
                "deterministic audio fixture"
            ],
        },
        "billing_mode": "subscription",
        "payg_allowed": False,
        "credit_pack_allowed": False,
        "quota_consumed": False,
        "attempt": 1,
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "fallback": {},
    }
    receipt_path = write_fixture_receipt(
        path=target.with_name(target.name + ".receipt.json"), payload=receipt
    )
    return target, receipt_path, fingerprint


def probe_fixture_media(path: Path) -> Dict[str, Any]:
    """Measure a fixture with the sanctioned probe, for the integration report."""
    from contentops.media.transport import ffprobe_json

    try:
        payload = ffprobe_json(Path(path))
    except Exception as exc:  # noqa: BLE001
        return {"probe_error": f"{type(exc).__name__}: {exc}"}
    streams = payload.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = payload.get("format") or {}
    duration = fmt.get("duration")
    try:
        duration_s = float(duration) if duration not in (None, "N/A") else None
    except (TypeError, ValueError):
        duration_s = None
    return {
        "container": fmt.get("format_name"),
        "video_codec": (video or {}).get("codec_name"),
        "width": (video or {}).get("width"),
        "height": (video or {}).get("height"),
        "duration_s": duration_s,
        "has_audio": audio is not None,
        "audio_codec": (audio or {}).get("codec_name"),
    }
