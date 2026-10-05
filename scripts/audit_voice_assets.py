"""Voice asset audit for the M4.6 A/B comparison. No provider call.

Answers one question per candidate honestly: does this audio actually represent the
narration the Evidence Lock pins, and can it be trusted as the baseline or candidate
voice stack?

Three things this deliberately does not do:

1. **Trust a filename.** Every candidate is hashed and probed. ``A-edge-tts.mp3``
   being named A proves nothing.
2. **Accept a hash mismatch silently.** The B receipt records a *normalised* text
   digest while the lock records the raw file digest. Those are different strings over
   different transformations, and treating them as equal because "the text is the
   same" is exactly the kind of hand-wave that lets a wrong asset into a controlled
   experiment.
3. **Rank the voices.** No scoring. The audit reports measurements; a human decides.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path("D:/Projects/X-SuperPlay-ContentOps")
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from process_utils import hidden_run  # noqa: E402

LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
NARRATION = ROOT / "projects/easel-review/script/narration.txt"
CAPTION = ROOT / "projects/easel-enhanced-golden/evidence/captions/easel.srt"
B_RECEIPT = ROOT / ".verify-tmp/m2/narration/receipt-golden-b.json"

CANDIDATES: List[str] = [
    ".verify-tmp/m2/ab/A-edge-tts.mp3",
    ".verify-tmp/m2/ab/B-minimax-mplan.wav",
    ".verify-tmp/m2/narration/narration-441c2b8634a43a33.wav",
    ".verify-tmp/m2/narration/narration-441c2b8634a43a33-raw.wav",
    "projects/easel-review/assets/voice_easel/narration.mp3",
    "projects/easel-review/assets/voice/shot_00.wav",
    "projects/easel-review/assets/voice/shot_01.wav",
    "projects/easel-review/assets/voice/shot_02.wav",
    "projects/easel-review/assets/voice/shot_03.wav",
    "projects/easel-review/assets/voice/shot_04.wav",
    "projects/easel-review/assets/voice/shot_05.wav",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_state(rel: str) -> str:
    tracked = hidden_run(
        ["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), timeout=60
    ).returncode == 0
    ignored = hidden_run(
        ["git", "check-ignore", "-q", "--no-index", "--", rel],
        cwd=str(ROOT), timeout=60,
    ).returncode == 0
    if tracked:
        return "TRACKED"
    return "IGNORED" if ignored else "UNTRACKED"


def probe(path: Path) -> Dict[str, Any]:
    out = hidden_run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        cwd=str(ROOT), timeout=180,
    )
    if out.returncode != 0:
        return {"probe_failed": True}
    payload = json.loads(out.stdout or "{}")
    fmt = payload.get("format", {})
    streams = payload.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    tags = fmt.get("tags") or {}
    return {
        "container": fmt.get("format_name"),
        "codec": audio.get("codec_name"),
        "sample_rate_hz": audio.get("sample_rate"),
        "channels": audio.get("channels"),
        "duration_s": round(float(fmt.get("duration", 0)), 3),
        "bytes": int(fmt.get("size", 0)),
        "bit_rate": fmt.get("bit_rate"),
        "tags": {k: v for k, v in tags.items() if k in ("title", "artist", "encoder", "comment")},
    }


def loudness(path: Path) -> Dict[str, Any]:
    """EBU R128 measurement. Diagnostic only; never used to choose a voice.

    The summary is parsed from **stderr**, not stdout. ffmpeg sends the null muxer's
    stream to stdout but the ebur128 summary to stderr, so an earlier version of this
    function returned None for every file while looking like it had measured nothing.
    """
    out = hidden_run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        cwd=str(ROOT), timeout=600,
    )
    text = f"{out.stdout or ''}\n{out.stderr or ''}"
    integrated = peak = None
    in_summary = False
    for line in text.splitlines():
        # ffmpeg prefixes filter output with `[Parsed_ebur128_0 @ 0000...]`, so the
        # summary marker is a substring rather than a prefix. Matching on startswith
        # returned None for every file while the measurement was plainly on screen.
        if "Summary:" in line:
            in_summary = True
            continue
        if not in_summary:
            continue
        stripped = line.strip()
        # Keep only what follows the last `]` so the filter prefix cannot hide the
        # field name.
        payload = stripped.rsplit("]", 1)[-1].strip()
        if payload.startswith("I:") and integrated is None:
            try:
                integrated = float(payload.split(":", 1)[1].split()[0])
            except (IndexError, ValueError):
                pass
        elif payload.startswith("Peak:") and peak is None:
            try:
                peak = float(payload.split(":", 1)[1].split()[0])
            except (IndexError, ValueError):
                pass
    return {
        "integrated_lufs": integrated,
        "true_peak_dbtp": peak,
        "note": "measured locally for consistency checking; not a selection criterion",
    }


def caption_end_srt() -> float:
    """End time of the last caption cue, in seconds."""
    text = CAPTION.read_text(encoding="utf-8")
    stamps = []
    for line in text.splitlines():
        if "-->" in line:
            end = line.split("-->")[1].strip().split()[0]
            hours, minutes, rest = end.split(":")
            seconds, millis = rest.split(",")
            stamps.append(int(hours) * 3600 + int(minutes) * 60 + int(seconds)
                          + int(millis) / 1000)
    return max(stamps) if stamps else 0.0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    locked_narration = lock["narration_text_sha256"]
    narration_text = NARRATION.read_text(encoding="utf-8")
    normalized_text = "\n".join(l for l in narration_text.splitlines() if l.strip())
    normalized_digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    caption_end = caption_end_srt()

    print("=== locked truth ===")
    print(f"  narration_text_sha256 (raw file)   : {locked_narration}")
    print(f"  sha256 (non-empty lines joined)    : {normalized_digest}")
    print(f"  canonical caption ends at          : {caption_end:.3f} s")
    print()

    receipt = json.loads(B_RECEIPT.read_text(encoding="utf-8")) if B_RECEIPT.is_file() else {}
    print("=== B receipt text binding ===")
    print(f"  display_text_sha256 : {receipt.get('display_text_sha256')}")
    print(f"  spoken_text_sha256  : {receipt.get('spoken_text_sha256')}")
    print(f"  display == normalised locked text : "
          f"{receipt.get('display_text_sha256') == normalized_digest}")
    print(f"  display == raw locked text        : "
          f"{receipt.get('display_text_sha256') == locked_narration}")
    print()

    print("=== candidate probe ===")
    rows: List[Dict[str, Any]] = []
    for rel in CANDIDATES:
        path = ROOT / rel
        if not path.is_file():
            print(f"  MISSING  {rel}")
            continue
        facts = probe(path)
        digest = sha256_file(path)
        state = git_state(rel)
        record = {
            "path": rel,
            "sha256": digest,
            "bytes": path.stat().st_size,
            "git": state,
            **facts,
        }
        rows.append(record)
        print(
            f"  {digest[:12]}  {state:9s} {str(facts.get('duration_s')):>8s}s "
            f"{str(facts.get('codec')):12s} {str(facts.get('sample_rate_hz')):>6s}Hz "
            f"{str(facts.get('channels'))}ch  {rel}"
        )

    print()
    print("=== identical-content groups ===")
    by_digest: Dict[str, List[str]] = {}
    for record in rows:
        by_digest.setdefault(record["sha256"], []).append(record["path"])
    for digest, paths in by_digest.items():
        if len(paths) > 1:
            print(f"  {digest[:12]}  identical bytes:")
            for path in paths:
                print(f"      {path}")

    print()
    print("=== loudness (diagnostic only) ===")
    for record in rows:
        if record["path"] in (
            ".verify-tmp/m2/ab/A-edge-tts.mp3",
            ".verify-tmp/m2/ab/B-minimax-mplan.wav",
            "projects/easel-review/assets/voice_easel/narration.mp3",
            ".verify-tmp/m2/narration/narration-441c2b8634a43a33-raw.wav",
        ):
            measured = loudness(ROOT / record["path"])
            record["loudness"] = measured
            deviation = (
                f"{measured['integrated_lufs'] + 16:+.2f}"
                if measured["integrated_lufs"] is not None else "n/a"
            )
            print(
                f"  {str(measured['integrated_lufs']):>8} LUFS  "
                f"{str(measured['true_peak_dbtp']):>7} dBTP  "
                f"{deviation:>7} vs -16   {record['path']}"
            )

    out = Path("D:/Temp/opencode/voice-audit.json")
    out.write_text(json.dumps({
        "locked_narration_text_sha256": locked_narration,
        "normalized_narration_text_sha256": normalized_digest,
        "caption_end_srt": caption_end,
        "candidates": rows,
        "identical_groups": {d: p for d, p in by_digest.items() if len(p) > 1},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print()
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())