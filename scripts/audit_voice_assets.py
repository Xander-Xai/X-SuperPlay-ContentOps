"""Voice asset audit for the M4.6 A/B comparison. No provider call.

Answers one question per candidate honestly: does this audio actually represent the
narration the Evidence Lock pins, and can it be trusted as the baseline or candidate
voice stack?

This is the **producer** of
``projects/easel-enhanced-golden/receipts/voice-asset-audit.json``. It used to be a
throwaway script that wrote to a temp directory, which meant the committed receipt had
no code behind it: nothing regenerated it, so it went stale silently. It still did --
it was reporting the *superseded* Windows working-tree narration digest
(``2f712222...``) as the locked truth after the Evidence Lock moved to the canonical
Git blob digest (``f2de808c...``). A receipt nobody can rebuild is a claim, not
evidence.

Four things this deliberately does not do:

1. **Trust a filename.** Every asset is hashed and probed.
   ``A-baseline-edge-tts.mp3`` being named that proves nothing.
2. **Accept a hash mismatch silently.** The B receipt records a *normalised* text
   digest while the lock records the raw file digest. Different strings over different
   transformations; treating them as equal because "the text is the same" is exactly
   the hand-wave that lets a wrong asset into a controlled experiment.
3. **Rank the voices.** No scoring. The audit reports measurements; a human decides.
4. **Upgrade a provenance class because a file is now tracked.** Arm A is committed so
   it exists on every machine. That makes it *findable*, not *verified*.

Runs on a clean checkout: the canonical fixtures are tracked, and the historical
candidates are optional (``present: false`` where absent) rather than required.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from process_utils import hidden_run  # noqa: E402

LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
NARRATION = ROOT / "projects/easel-review/script/narration.txt"
CAPTION = ROOT / "projects/easel-enhanced-golden/evidence/captions/easel.srt"
OUT = ROOT / "projects/easel-enhanced-golden/receipts/voice-asset-audit.json"

GOLDEN_VOICE = ROOT / "projects/easel-enhanced-golden/golden-assets/voice"
CANONICAL_A = "projects/easel-enhanced-golden/golden-assets/voice/A-baseline-edge-tts.mp3"
CANONICAL_B = "projects/easel-enhanced-golden/golden-assets/voice/B-minimax-speech-2.8-hd.wav"
CANONICAL_B_RECEIPT = (
    "projects/easel-enhanced-golden/golden-assets/voice/B-minimax-speech-2.8-hd.receipt.json"
)

#: The two approved inputs, with the classes decided from evidence and not from a
#: filename. ``approved_digest`` is what the Founder approved; the audit re-hashes the
#: tracked copy and reports both so a substitution would be visible here.
CANONICAL: Dict[str, Dict[str, Any]] = {
    "A": {
        "path": CANONICAL_A,
        "sha256": "bc6b721656a5aab3491d45b15a649ec6161eae04652a5e6d627f722ffbe8b625",
        "provenance_class": "CONSISTENT_HISTORICAL_BASELINE",
        "provider_receipt": None,
        "basis": (
            "byte-identical to projects/easel-review/assets/voice_easel/narration.mp3, "
            "the file the pinned render consumed; duration, sample rate and loudness "
            "match issue #19"
        ),
        "limitation": (
            "no surviving machine generation receipt binds this audio to the locked "
            "narration text, unlike the B asset. Tracking the bytes makes it available on "
            "every machine; it does not make it verified, so the class is unchanged"
        ),
        "historical_candidates": [
            ".verify-tmp/m2/ab/A-edge-tts.mp3",
            "projects/easel-review/assets/voice_easel/narration.mp3",
        ],
    },
    "B": {
        "path": CANONICAL_B,
        "sha256": "e2e014a916eb7a637b68d80ace27551c557d3797541b61f41c195f8256b86593",
        "provenance_class": "VERIFIED_CURRENT_BASELINE",
        "provider_receipt": CANONICAL_B_RECEIPT,
        "basis": (
            "provider receipt normalized_sha256 matches the asset bytes and "
            "display_text_sha256 matches the locked narration in normalised form"
        ),
        "limitation": (
            "the receipt's loudness bookkeeping is wrong and is preserved uncorrected; "
            "see receipt_loudness_conflict below"
        ),
        "historical_candidates": [
            ".verify-tmp/m2/ab/B-minimax-mplan.wav",
            ".verify-tmp/m2/narration/narration-441c2b8634a43a33.wav",
        ],
    },
}

#: Host-local candidates, probed only when present. Never required, never selected.
HISTORICAL_CANDIDATES: List[str] = [
    ".verify-tmp/m2/ab/A-edge-tts.mp3",
    ".verify-tmp/m2/ab/B-minimax-mplan.wav",
    ".verify-tmp/m2/narration/narration-441c2b8634a43a33.wav",
    ".verify-tmp/m2/narration/narration-441c2b8634a43a33-raw.wav",
    ".verify-tmp/m2/narration/receipt-golden-b.json",
    "projects/easel-review/assets/voice_easel/narration.mp3",
]

#: Tracked decoys. Being in Git is not evidence of being the narration.
DECOY_SHOTS = [f"projects/easel-review/assets/voice/shot_{i:02d}.wav" for i in range(6)]

SCHEMA = "contentops.voice-asset-audit/v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_ref(rel: str) -> str:
    return "repo://" + rel


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
    if not _has_tool("ffprobe"):
        return {"probe_skipped": "ffprobe unavailable on this host"}
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

    A measurement of about -17 LUFS on a file whose receipt claims -23.99 is a receipt
    defect, not an asset defect. The conflict is reported, never reconciled.
    """
    if not _has_tool("ffmpeg"):
        return {"measurement_skipped": "ffmpeg unavailable on this host"}
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
        # summary marker is a substring rather than a prefix.
        if "Summary:" in line:
            in_summary = True
            continue
        if not in_summary:
            continue
        payload = line.strip().rsplit("]", 1)[-1].strip()
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


_TOOL_CACHE: Dict[str, bool] = {}


def _has_tool(name: str) -> bool:
    if name not in _TOOL_CACHE:
        _TOOL_CACHE[name] = hidden_run(
            [name, "-version"], cwd=str(ROOT), timeout=60
        ).returncode == 0
    return _TOOL_CACHE[name]


def caption_end_srt() -> float:
    """End time of the last caption cue, in seconds."""
    stamps = []
    for line in CAPTION.read_text(encoding="utf-8").splitlines():
        if "-->" in line:
            end = line.split("-->")[1].strip().split()[0]
            hours, minutes, rest = end.split(":")
            seconds, millis = rest.split(",")
            stamps.append(
                int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000
            )
    return max(stamps) if stamps else 0.0


def describe(rel: str, *, loud: bool = False) -> Dict[str, Any]:
    """Hash and probe one path. Absent paths are reported, never skipped silently."""
    path = ROOT / rel
    record: Dict[str, Any] = {"path": rel, "ref": repo_ref(rel), "git": git_state(rel)}
    if not path.is_file():
        record["present"] = False
        return record
    record["present"] = True
    record["sha256"] = sha256_file(path)
    record["bytes"] = path.stat().st_size
    record.update(probe(path))
    if loud:
        record["loudness"] = loudness(path)
    return record


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    locked_narration = lock["narration_text_sha256"]
    narration_text = NARRATION.read_text(encoding="utf-8")
    normalized_text = "\n".join(l for l in narration_text.splitlines() if l.strip())
    normalized_digest = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
    caption_end = caption_end_srt()

    print("=== locked truth (from the Evidence Lock, Git blob digest) ===")
    print(f"  evidence_lock_fingerprint          : {lock['fingerprint']}")
    print(f"  narration_text_sha256 (blob)       : {locked_narration}")
    print(f"  sha256 (non-empty lines joined)    : {normalized_digest}")
    print(f"  canonical caption ends at          : {caption_end:.3f} s")
    print()

    receipt: Dict[str, Any] = {}
    receipt_path = ROOT / CANONICAL_B_RECEIPT
    if receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    print("=== B receipt text binding (tracked canonical receipt) ===")
    print(f"  receipt display_text_sha256        : {receipt.get('display_text_sha256')}")
    print(f"  display == normalised locked text  : "
          f"{receipt.get('display_text_sha256') == normalized_digest}")
    print(f"  display == raw locked text         : "
          f"{receipt.get('display_text_sha256') == locked_narration}")
    print()

    canonical_records: Dict[str, Any] = {}
    for arm, spec in CANONICAL.items():
        record = describe(spec["path"], loud=True)
        approved = spec["sha256"]
        actual = record.get("sha256")
        record.update({
            "ref": repo_ref(spec["path"]),
            "approved_digest": approved,
            "matches_approved_digest": actual == approved,
            "provenance_class": spec["provenance_class"],
            "provider_receipt": (
                repo_ref(spec["provider_receipt"]) if spec["provider_receipt"] else None
            ),
            "basis": spec["basis"],
            "limitation": spec["limitation"],
            "historical_candidates": [repo_ref(c) for c in spec["historical_candidates"]],
        })
        canonical_records[arm] = record
        print(f"=== canonical {arm} ===")
        print(f"  path              : {repo_ref(spec['path'])}")
        print(f"  git               : {record['git']}")
        print(f"  present           : {record.get('present')}")
        print(f"  sha256            : {actual}")
        print(f"  matches approved  : {record['matches_approved_digest']}")
        print(f"  provenance_class  : {spec['provenance_class']}")
        print(f"  provider_receipt  : {record['provider_receipt']}")
        if record.get("loudness", {}).get("integrated_lufs") is not None:
            print(f"  measured loudness : {record['loudness']['integrated_lufs']} LUFS / "
                  f"{record['loudness']['true_peak_dbtp']} dBTP")
        print()

    historical = [describe(rel) for rel in HISTORICAL_CANDIDATES]
    present_hist = [h for h in historical if h.get("present")]
    print(f"=== historical candidates === {len(present_hist)}/{len(historical)} present")
    print("  (audit metadata only; never selected, never required)")
    for record in historical:
        if record.get("present"):
            print(f"  {record['sha256'][:12]}  {record['git']:9s} {record['path']}")
    print()

    decoys = [describe(rel) for rel in DECOY_SHOTS]
    present_decoys = [d for d in decoys if d.get("present")]
    total_s = sum(d.get("duration_s", 0) or 0 for d in present_decoys)
    print(f"=== decoys === {len(present_decoys)}/{len(decoys)} present, "
          f"{total_s:.1f}s total")
    print("  UNRELATED: per-shot fragments, not the narration. Being tracked in Git is")
    print("  not evidence of anything.")
    print()

    # Identical-content groups, computed across canonical + historical so the
    # byte-identity of A with the render input is visible rather than asserted.
    groups: Dict[str, List[str]] = {}
    for record in [*canonical_records.values(), *historical]:
        if record.get("sha256"):
            groups.setdefault(record["sha256"], []).append(record["path"])
    identical_groups = {d: p for d, p in groups.items() if len(p) > 1}
    print("=== identical-content groups ===")
    for digest, paths in identical_groups.items():
        print(f"  {digest[:12]}  identical bytes:")
        for path in paths:
            print(f"      {path}")
    print()

    # The known receipt defect, reported as a conflict between two records rather than
    # corrected in either one.
    receipt_loudness = (receipt.get("technical_qc", {}).get("measurements") or {}).get(
        "integrated_lufs"
    )
    measured_b = (canonical_records.get("B", {}).get("loudness") or {}).get(
        "integrated_lufs"
    )
    conflict: Optional[Dict[str, Any]] = None
    if receipt_loudness is not None and measured_b is not None:
        agrees = abs(receipt_loudness - measured_b) < 0.5
        print("=== receipt loudness conflict (historical vs measured) ===")
        print(f"  receipt integrated_lufs : {receipt_loudness}")
        print(f"  measured integrated_lufs: {measured_b}")
        print(f"  agrees                  : {agrees}")
        print("  Both records are kept. The receipt is not rewritten and the measurement")
        print("  does not overwrite it: a historical receipt and a later measurement are")
        print("  different kinds of claim.")
        print()
        conflict = {
            "receipt_integrated_lufs": receipt_loudness,
            "receipt_loudness_before": (receipt.get("asset") or {}).get("loudness_before"),
            "receipt_loudness_after": (receipt.get("asset") or {}).get("loudness_after"),
            "receipt_true_peak_db": (receipt.get("technical_qc", {}).get("measurements") or {})
            .get("true_peak_db"),
            "measured_integrated_lufs": measured_b,
            "agrees": agrees,
            "resolution": (
                "receipt preserved uncorrected; this audit is the measured current "
                "evidence. Rewriting the historical receipt would hide a real defect."
            ),
        }

    payload = {
        "schema": SCHEMA,
        "producer": "scripts/audit_voice_assets.py",
        "provider_calls": {"speech": 0, "image": 0, "video": 0},
        "billing_guard_consulted": False,
        "locked_truth": {
            "evidence_lock_fingerprint": lock["fingerprint"],
            "narration_text_sha256": locked_narration,
            "narration_text_digest_source": "git_blob",
            "normalized_narration_text_sha256": normalized_digest,
            "canonical_caption_end_srt": caption_end,
            "superseded_working_tree_digests": {
                "narration_text_sha256": (
                    "2f7122228c53de128d04541ec1c4086dedd22ddc51bb0347d605e1c789a02348"
                ),
                "note": (
                    "the CRLF working-tree digest that the Evidence Lock pinned before "
                    "lock digests were taken from Git blobs. Historical only; it is not "
                    "the locked narration on any clean checkout"
                ),
            },
        },
        "b_receipt_text_binding": {
            "receipt_ref": repo_ref(CANONICAL_B_RECEIPT),
            "display_text_sha256": receipt.get("display_text_sha256"),
            "matches_normalized_locked_text": (
                receipt.get("display_text_sha256") == normalized_digest
            ),
            "matches_raw_locked_text": (
                receipt.get("display_text_sha256") == locked_narration
            ),
            "note": (
                "display_text_sha256 covers the locked narration with blank lines "
                "removed; it is not the raw file digest and the two are not "
                "interchangeable"
            ),
        },
        "canonical_assets": canonical_records,
        "historical_candidates": historical,
        "historical_candidates_note": (
            "Host-local, gitignored, audit-only. The selected inputs are the canonical "
            "Golden copies; these exist to document where those bytes came from."
        ),
        "decoys": {
            "classification": "UNRELATED",
            "reason": (
                "per-shot fragments totalling roughly 26.9 s at 22050 Hz against a 61.9 s "
                "narration at 24000 Hz. Being tracked in Git is not evidence of anything"
            ),
            "present_count": len(present_decoys),
            "files": decoys,
        },
        "identical_groups": identical_groups,
        "receipt_loudness_conflict": conflict,
        "human_review": "PENDING_FOUNDER_REVIEW",
        "winner_declared": False,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())