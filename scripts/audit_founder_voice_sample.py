"""Audit the Founder's voice sample locally and write the privacy receipt.

Why this is a tracked script and not a one-off
---------------------------------------------
The voice-asset audit receipt shipped without a producer once, and the result was a
receipt that had silently gone stale against the Evidence Lock it was supposed to
corroborate. The lesson recorded there applies here: a receipt nobody can rebuild is a
claim, not evidence. So this script *is* the producer named in
``founder-voice-sample-audit.json``, and re-running it regenerates that file.

What it will not do
-------------------
It reads the sample and never writes to it: no denoise, no normalise, no trim, no
resample, no re-encode. A clone reference is only meaningful if it is the recording the
Founder actually made, and every "cleanup" step would make some later similarity claim
harder to interpret. If a future audit shows the sample is unusable, the fix is a new
recording or an explicitly-authorised DERIVED sample, not a silent repair.

It also refuses to record an absolute path. The receipt is public-safe: hashes,
measurements, rights basis and the declared registry identity. No audio, no transcript,
no identity data, no host path.

The sample is a LOCAL PRIVATE INPUT. It is gitignored by both the ``assert/`` directory
rule and the global ``*.wav`` rule, and this script checks that rather than assuming it.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

SAMPLE = ROOT / "assert" / "voice-reference-clean.wav"
OUT = ROOT / "projects/easel-enhanced-golden/receipts/founder-voice-sample-audit.json"

PRODUCER = "scripts/audit_founder_voice_sample.py"

#: The digest the digital-asset registry declares for its primary voice reference.
#: Kept as data so a renamed or replaced working copy is caught rather than accepted
#: because it sits at the expected path.
REGISTERED_DIGEST = "bb56d052cd637bd8a369f6e37a745c7609de9988ada0fa0827d4d5c59035df8d"
REGISTERED_ASSET_ID = "voice-reference"
REGISTERED_RELATIVE_PATH = "R1D-15s.wav"

#: Current documented upload rules. Re-read from the official API reference before this
#: audit was written; a change there moves these constants and the compliance block
#: below moves with them.
DOCUMENTED = {
    "checked_at": "2026-10-12",
    "formats": ["mp3", "m4a", "wav"],
    "min_duration_s": 10,
    "max_duration_s": 300,
    "max_size_bytes": 20 * 1024 * 1024,
    "source": "current official voice-clone API reference",
}


def _ff(args: List[str], timeout: int = 600):
    return hidden_run(args, cwd=str(ROOT), timeout=timeout)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(path: Path) -> Dict[str, Any]:
    out = _ff([
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ])
    payload = json.loads(out.stdout or "{}")
    stream = next(
        (s for s in payload.get("streams", []) if s.get("codec_type") == "audio"), {}
    )
    return {"format": payload.get("format", {}), "stream": stream}


def _decode_ok(path: Path) -> bool:
    """A full decode. A file that probes cleanly can still fail partway through."""
    out = _ff(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"])
    return out.returncode == 0 and not (out.stderr or "").strip()


def _loudness(path: Path) -> Dict[str, Optional[float]]:
    """EBU R128. Parsed from stderr, where ffmpeg actually writes the summary."""
    out = _ff([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "ebur128=peak=true", "-f", "null", "-",
    ])
    text = f"{out.stdout or ''}\n{out.stderr or ''}"
    integrated = lra = peak = None
    in_summary = False
    for line in text.splitlines():
        if "Summary:" in line:
            in_summary = True
            continue
        if not in_summary:
            continue
        payload = line.strip().rsplit("]", 1)[-1].strip()
        if payload.startswith("I:") and integrated is None:
            integrated = float(payload.split(":", 1)[1].split()[0])
        elif payload.startswith("LRA:") and lra is None:
            lra = float(payload.split(":", 1)[1].split()[0])
        elif payload.startswith("Peak:") and peak is None:
            peak = float(payload.split(":", 1)[1].split()[0])
    return {"integrated_lufs": integrated, "loudness_range_lu": lra,
            "true_peak_dbfs": peak}


def _astats(path: Path) -> Dict[str, Optional[float]]:
    out = _ff([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "astats=metadata=1:reset=0", "-f", "null", "-",
    ])
    text = f"{out.stdout or ''}\n{out.stderr or ''}"

    def stat(name: str) -> Optional[float]:
        m = re.search(rf"{name}:\s*(-?[\d.]+)", text)
        return float(m.group(1)) if m else None

    return {
        "peak_level_db": stat("Peak level dB"),
        "rms_level_db": stat("RMS level dB"),
        "flat_factor": stat("Flat factor"),
        "peak_count": stat("Peak count"),
    }


def _silence(path: Path) -> List[Dict[str, float]]:
    out = _ff([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", "silencedetect=noise=-35dB:d=0.35", "-f", "null", "-",
    ])
    text = f"{out.stdout or ''}\n{out.stderr or ''}"
    gaps: List[Dict[str, float]] = []
    start: Optional[float] = None
    for line in text.splitlines():
        m = re.search(r"silence_start:\s*([\d.]+)", line)
        if m:
            start = float(m.group(1))
        m = re.search(
            r"silence_end:\s*([\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", line
        )
        if m and start is not None:
            gaps.append({
                "start_s": round(start, 3),
                "end_s": round(float(m.group(1)), 3),
                "duration_s": round(float(m.group(2)), 3),
            })
            start = None
    return gaps


def _window_rms(path: Path, a: float, b: float) -> Optional[float]:
    out = _ff([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-af", f"atrim={a}:{b},astats=metadata=1:reset=0", "-f", "null", "-",
    ])
    text = f"{out.stdout or ''}\n{out.stderr or ''}"
    m = re.search(r"RMS level dB:\s*(-?[\d.]+)", text)
    return float(m.group(1)) if m else None


def _git_state(rel: str) -> Dict[str, bool]:
    tracked = hidden_run(
        ["git", "ls-files", "--error-unmatch", "--", rel], cwd=str(ROOT), timeout=60
    ).returncode == 0
    ignored = hidden_run(
        ["git", "check-ignore", "-q", "--no-index", "--", rel], cwd=str(ROOT), timeout=60
    ).returncode == 0
    return {"tracked": tracked, "ignored": ignored}


def audit(path: Path = SAMPLE) -> Dict[str, Any]:
    if not path.is_file():
        raise SystemExit(
            f"the private sample is absent at {path.relative_to(ROOT).as_posix()}. "
            "This is a LOCAL PRIVATE INPUT and is gitignored by design, so it will "
            "never exist on a clean checkout. Refusing to write a receipt describing a "
            "file that was not measured."
        )

    digest = _sha256(path)
    probe = _probe(path)
    fmt, stream = probe["format"], probe["stream"]
    duration = float(fmt.get("duration", 0))
    decode_ok = _decode_ok(path)
    loud = _loudness(path)
    stats = _astats(path)
    gaps = _silence(path)
    total_silence = sum(g["duration_s"] for g in gaps)

    rel = path.relative_to(ROOT).as_posix()
    state = _git_state(rel)

    first_rms = _window_rms(path, 0, min(0.5, duration))
    last_rms = _window_rms(path, max(0.0, duration - 0.5), duration)

    technical: Dict[str, Any] = {
        "decode_success": decode_ok,
        **loud,
        **stats,
        "clipping_detected": bool((stats.get("flat_factor") or 0) > 0),
        "leading_silence_s": 0.0 if (first_rms or -99) > -50 else None,
        "trailing_silence_s": 0.0 if (last_rms or -99) > -50 else None,
        "silence_gaps": gaps,
        "total_silence_s": round(total_silence, 3),
        "silence_ratio": round(total_silence / duration, 4) if duration else None,
        "first_window_rms_db": first_rms,
        "last_window_rms_db": last_rms,
    }

    compliance = {
        "format_ok": fmt.get("format_name") == "wav"
        and stream.get("codec_name") == "pcm_s16le",
        "duration_ok": DOCUMENTED["min_duration_s"] <= duration
        <= DOCUMENTED["max_duration_s"],
        "size_ok": path.stat().st_size <= DOCUMENTED["max_size_bytes"],
        "mono_single_channel": int(stream.get("channels", 0)) == 1,
        "decode_ok": decode_ok,
        "no_clipping": not technical["clipping_detected"],
        "headroom_ok": (loud.get("true_peak_dbfs") is None)
        or loud["true_peak_dbfs"] < -0.1,
        "silence_ratio_reasonable": (technical["silence_ratio"] or 0) < 0.3,
    }

    return {
        "schema": "contentops.founder-voice-sample-audit/v1",
        "producer": PRODUCER,
        "sample_sha256": digest,
        "size_bytes": path.stat().st_size,
        "container": fmt.get("format_name"),
        "codec": stream.get("codec_name"),
        "sample_rate": int(stream.get("sample_rate", 0)),
        "channels": int(stream.get("channels", 0)),
        "duration": round(duration, 3),
        "bits_per_sample": stream.get("bits_per_sample"),
        "bit_rate": int(fmt.get("bit_rate", 0)),
        "source_class": "LOCAL_PRIVATE_INPUT",
        "rights_basis": "FOUNDER_OWN_VOICE",
        "public_safe_metadata": True,
        "registered_as": {
            "asset_id": REGISTERED_ASSET_ID,
            "declared_relative_path": REGISTERED_RELATIVE_PATH,
            "declared_sha256": REGISTERED_DIGEST,
            "matches_declared_digest": digest == REGISTERED_DIGEST,
            "note": (
                "same bytes under a working filename. The registry declares this digest "
                "as its primary voice reference; the working copy is named "
                "voice-reference-clean.wav. Identity is the digest, not the name."
            ),
        },
        "technical": technical,
        "documented_requirements_at_check_time": DOCUMENTED,
        "requirement_compliance": compliance,
        "all_requirements_met": all(compliance.values()),
        "privacy": {
            "git_tracked": state["tracked"],
            "git_ignored": state["ignored"],
            "ignore_rule": "assert/ (directory rule) and *.wav",
            "raw_audio_committed": state["tracked"],
            "absolute_path_recorded": False,
            "note": (
                "the raw sample stays a local private input. This receipt carries hashes "
                "and measurements only: no audio, no transcript, no identity data, no "
                "host path."
            ),
        },
        "derivations_created": [],
        "human_review": "PENDING_FOUNDER_REVIEW",
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    receipt = audit()

    print("=== FOUNDER VOICE SAMPLE AUDIT (local private input) ===")
    for key in ("sample_sha256", "size_bytes", "container", "codec", "sample_rate",
                "channels", "duration", "bits_per_sample"):
        print(f"  {key:18s}: {receipt[key]}")
    print("  --- technical ---")
    for key, value in receipt["technical"].items():
        if key != "silence_gaps":
            print(f"  {key:26s}: {value}")
    print(f"  {'silence_gaps':26s}: {len(receipt['technical']['silence_gaps'])}")
    print("  --- privacy ---")
    print(f"  tracked                   : {receipt['privacy']['git_tracked']}")
    print(f"  ignored                   : {receipt['privacy']['git_ignored']}")
    print("  --- compliance vs current documented rules ---")
    for key, ok in receipt["requirement_compliance"].items():
        print(f"  {key:26s}: {'PASS' if ok else 'FAIL'}")
    print(f"  {'ALL REQUIREMENTS MET':26s}: {receipt['all_requirements_met']}")

    if receipt["privacy"]["git_tracked"]:
        raise SystemExit(
            "FOUNDER_VOICE_PRIVACY_VIOLATION: the sample is tracked by Git. Stop and "
            "remove it from the index and history before doing anything else."
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print()
    print("wrote", OUT.relative_to(ROOT).as_posix())
    return 0 if receipt["all_requirements_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())