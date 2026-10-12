#!/usr/bin/env python3
"""A/B/C listening experiment on a ~20-30 s narration sample. Issue #34.

What the experiment is
----------------------
The same opening of the locked Golden narration, in three arms:

```
A  original text, original parameters. Default: a local excerpt of the
   already-generated Golden narration (zero provider cost). `--a-mode fresh`
   re-synthesises the control instead, explicitly reproducing the pre-v2
   single-line parameters.
B  the spoken-script derivative: paragraph newlines restored, documented
   <#x#> pauses added, emotion left to the model (auto). One request.
C  B's text, delivered as per-segment requests with the segment-level emotion
   and speed from the spoken script, then concatenated. Exercises the segment
   cache, partial regeneration and the join path.
```

The provider calls are real, so every one of them is wrapped in a before/after
plan-quota and balance read; the run refuses unless the M Plan gate says
``SAFE_INCLUDED_PLAN`` on a Subscription-class credential, refuses to start
when the estimated billable characters exceed ``--budget-chars``, and refuses
to continue when accumulated usage would. There is no chat-style confirmation:
``--execute`` is the explicit switch and the budget is the hard bound.

Why A reuses audio by default
-----------------------------
The instruction for this round is explicit: the control arm should not repeat
quota spend "for the control experiment". The existing Golden narration IS arm
A's conditions (original text, flattened, no emotion, speed 1), so its opening
excerpt is cut locally at a detected silence boundary -- zero provider calls --
and the cut is described precisely in the receipt, including the boundary it
chose and what that choice can and cannot prove. ``--a-mode fresh`` exists for
a machine without the old asset, and is labelled as a fresh control.

What this script never does
---------------------------
No voice creation, no file transfer, no automatic top-up, no publish. It stops
at the point where a human must listen: ``human_review`` stays
``PENDING_FOUNDER_REVIEW`` and ``production_ready`` stays false, always.

Exit codes: 0 = completed (or dry run); 1 = refused (credential, billing,
budget, precondition); 3 = provider or media failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402

from contentops.media.asr_backcheck import backcheck_speech  # noqa: E402
from contentops.media.audio import (  # noqa: E402
    measure_audio,
    normalise_speech,
    technical_qc,
)
from contentops.media.clone_route import billable_characters  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_SUBSCRIPTION,
    load_local_env_file,
    resolve_subscription_credential,
)
from contentops.media.fingerprint import sha256_file  # noqa: E402
from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.minimax_native_tts import (  # noqa: E402
    MINIMAX_CN_HOST,
    NativeTtsRefusal,
    build_t2a_payload,
    normalize_paragraph_newlines,
    send_t2a_once,
    strip_pause_markers,
)
from contentops.media.minimax_speech import flatten_for_cli  # noqa: E402
from contentops.media.native_rounds import (  # noqa: E402
    MPLAN_NARRATION_ROUTE,
    canonical_blob_sha256,
    classify_mplan_only,
    decide_mplan_native,
    delta_money,
    read_money,
    write_private_provider_response,
)
from contentops.media.spoken_script import (  # noqa: E402
    SpokenScriptError,
    load_spoken_script,
    sample_original_text,
    verify_script,
)
from contentops.media.t2a_segments import (  # noqa: E402
    ACTION_REUSE_CACHE,
    SegmentSpec,
    build_segment_payload,
    concatenate_segments,
    estimated_billable_characters,
    lookup_cached_segment,
    plan_segment_renders,
    segment_fingerprint,
    store_cached_segment,
)

VOICE_ID = "founder_primary_v1"
VOICE_ID_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
MODEL = "speech-2.8-hd"

ORIGINAL = ROOT / "projects/easel-review/script/narration.txt"
EVIDENCE_LOCK = ROOT / "projects/easel-enhanced-golden/evidence/evidence-lock.json"
SPOKEN_SCRIPT = ROOT / "projects/easel-enhanced-golden/script/narration-spoken.json"
RECEIPT_JSON = ROOT / "projects/easel-enhanced-golden/review/ab-c-sample-receipt.json"
RECEIPT_MD = ROOT / "projects/easel-enhanced-golden/review/ab-c-sample-receipt.md"
DEFAULT_OUT_DIR = "outputs/founder-ab-sample"
DEFAULT_A_SOURCE = "outputs/founder-golden/golden-narration-founder_primary_v1.wav"

REFUSED = "REFUSED"
PROVIDER_FAILED = "PROVIDER_FAILED"


class ExperimentRefusal(RuntimeError):
    """A precondition refused. Nothing further may be sent."""

    def __init__(self, code: str, reasons: List[str]) -> None:
        super().__init__(f"[{code}] " + "; ".join(reasons))
        self.code = code
        self.reasons = list(reasons)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _expected_for_asr(display_text: str, lexicon) -> str:
    """What the listener should hear: lexicon applied, pause markers removed."""
    return strip_pause_markers(lexicon.spoken_text(display_text))


# --- A: local excerpt or fresh control -----------------------------------------


def _detect_silences(path: Path, *, noise_db: int = -40, min_s: float = 0.3) -> List[Dict[str, float]]:
    result = hidden_run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-i", str(path),
         "-af", f"silencedetect=n={noise_db}dB:d={min_s}", "-f", "null", "-"],
        timeout=300,
    )
    text = result.stderr or ""
    return [
        {"start_s": float(start), "end_s": float(end)}
        for start, end in re.findall(
            r"silence_start:\s*(-?[\d.]+).*?silence_end:\s*(-?[\d.]+)", text, re.S
        )
    ]


def _choose_cut_boundary(
    silences: List[Dict[str, float]],
    *,
    duration_s: float,
    target_s: float,
    min_s: float = 18.0,
    max_s: float = 31.0,
) -> Tuple[float, Optional[Dict[str, float]]]:
    """Cut at a detected silence end nearest the target inside [min_s, max_s].

    The existing Golden narration was generated from single-line text, so it has
    no paragraph-boundary pauses to align to; the honest reading is that the cut
    is an excerpt whose *text* alignment is approximate. The boundary is chosen
    at a silence so the cut never clips mid-word. If the window is empty the
    whole source (when it fits) or the clamped target is used, and the receipt
    records which case happened.
    """
    candidates = [s for s in silences if min_s <= s["end_s"] <= max_s]
    if candidates:
        chosen = min(candidates, key=lambda s: abs(s["end_s"] - target_s))
        return chosen["end_s"], chosen
    if min_s <= duration_s <= max_s:
        return duration_s, None
    return max(min_s, min(target_s, min(max_s, duration_s))), None


def _cut_excerpt(source: Path, end_s: float, out_path: Path) -> None:
    result = hidden_run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(source), "-to", f"{end_s:.3f}",
         "-c:a", "pcm_s16le", "-ar", "32000", "-ac", "1", str(out_path)],
        timeout=300,
    )
    if result.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            "A excerpt cut failed: " + (result.stderr or "")[-400:]
        )


# --- provider request plumbing --------------------------------------------------


class ExperimentRunner:
    """Holds the credential, the receipts-in-progress and the budget state."""

    def __init__(
        self,
        *,
        credential: Any,
        out_dir: Path,
        diagnostics_dir: Path,
        asr_budget: int,
    ) -> None:
        self.credential = credential
        self.out_dir = out_dir
        self.diagnostics_dir = diagnostics_dir
        self.asr_state = {"used": 0, "budget": asr_budget}
        self.requests: List[Dict[str, Any]] = []
        self.asr_records: List[Dict[str, Any]] = []

    def preflight(self) -> Dict[str, Any]:
        money = read_money(MINIMAX_CN_HOST, self.credential.key)
        decision = decide_mplan_native(
            credential_class=self.credential.credential_class,
            credential_source=self.credential.source,
            guard_verdict=money["verdict"],
            guard_reasons=money.get("reasons"),
            quota=money["quota"],
        )
        if not decision["authorised"]:
            raise ExperimentRefusal("MPLAN_GATE_REFUSED", decision["reasons"] or ["refused"])
        return {"money": money, "decision": decision}

    def synth(
        self,
        *,
        payload: Dict[str, Any],
        label: str,
        attempt_id: str,
        usage_running_total: List[int],
        budget_chars: int,
    ) -> Tuple[Any, Dict[str, Any]]:
        """One native request, with billing read before and after it."""
        before = read_money(MINIMAX_CN_HOST, self.credential.key)
        decision = decide_mplan_native(
            credential_class=self.credential.credential_class,
            credential_source=self.credential.source,
            guard_verdict=before["verdict"],
            guard_reasons=before.get("reasons"),
            quota=before["quota"],
        )
        if not decision["authorised"]:
            raise ExperimentRefusal(
                "MPLAN_GATE_REFUSED_BEFORE_REQUEST",
                [f"{label}: " + reason for reason in decision["reasons"]],
            )
        try:
            result = send_t2a_once(
                payload=payload,
                credential=self.credential.key,
                base_url=MINIMAX_CN_HOST,
                timeout_s=600,
            )
        except NativeTtsRefusal as refusal:
            write_private_provider_response(
                self.diagnostics_dir, attempt_id,
                host=MINIMAX_CN_HOST, route=MPLAN_NARRATION_ROUTE, refusal=refusal,
            )
            record = {
                "label": label,
                "attempt_id": attempt_id,
                "request_transmitted": True,
                **refusal.structured(),
            }
            self.requests.append(record)
            raise
        after = read_money(MINIMAX_CN_HOST, self.credential.key)
        deltas = delta_money(before, after)
        classification = classify_mplan_only(
            quota_before=before["quota"], quota_after=after["quota"], deltas=deltas
        )
        usage = result.usage_characters or 0
        usage_running_total[0] += usage
        record = {
            "label": label,
            "attempt_id": attempt_id,
            "request_transmitted": True,
            "billing": {
                "before_verdict": before["verdict"],
                "gate_decision": decision,
                "quota_before": before["quota"],
                "quota_after": after["quota"],
                "balances_before": before["balances"],
                "balances_after": after["balances"],
                "deltas": deltas,
                "plan_only_classification": classification,
            },
            "provider": {
                "http_status": result.http_status,
                "status_code": result.status_code,
                "status_msg": result.status_msg,
                "trace_id": result.trace_id,
                "usage_characters": result.usage_characters,
                "usage_voice_count": result.usage_voice_count,
            },
            "usage_running_total": usage_running_total[0],
            "budget_chars": budget_chars,
        }
        self.requests.append(record)
        write_private_provider_response(
            self.diagnostics_dir, attempt_id,
            host=MINIMAX_CN_HOST, route=MPLAN_NARRATION_ROUTE, result=result,
        )
        if usage_running_total[0] > budget_chars:
            raise ExperimentRefusal(
                "SYNTHESIS_BUDGET_EXCEEDED_AFTER_REQUEST",
                [
                    f"{label}: cumulative usage {usage_running_total[0]} exceeds "
                    f"budget {budget_chars}; no further request will be sent"
                ],
            )
        return result, record

    def asr(self, *, audio_path: Path, expected: str, label: str) -> Dict[str, Any]:
        if self.asr_state["used"] >= self.asr_state["budget"]:
            return {
                "label": label,
                "status": "SKIPPED_BUDGET_EXHAUSTED",
                "budget": dict(self.asr_state),
            }
        self.asr_state["used"] += 1
        result = backcheck_speech(audio_path, expected).as_dict()
        record = {
            "label": label,
            "audio": str(audio_path),
            "expected_spoken_text_sha256": _sha256_text(expected),
            "budget": dict(self.asr_state),
            **result,
        }
        self.asr_records.append(record)
        return record


def _audio_record(path: Path) -> Dict[str, Any]:
    """Measure one audio file fully: container, loudness, and technical QC.

    ``technical_qc`` carries the deterministic gate checks **and** the silence
    map, which is the machine evidence for join artifacts (a segment boundary
    should show up as the declared gap; a misplaced one shows up as silence in
    the middle of speech).
    """
    measured = measure_audio(path)
    technical = technical_qc(path, expected_sample_rate_hz=32000)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "duration_s": measured.duration_s,
        "sample_rate_hz": measured.sample_rate_hz,
        "channels": measured.channels,
        "codec": measured.codec,
        "integrated_lufs": measured.integrated_lufs,
        "true_peak_db": measured.true_peak_db,
        "technical_qc": technical,
    }


# --- receipt --------------------------------------------------------------------


def _receipt_paths(suffix: str) -> Tuple[Path, Path]:
    """``(json, md)`` receipt paths; a sanitised suffix names a separate run.

    The A/B/C sample receipt is one artifact and the bounded term check (for
    terms the 20-30 s sample does not contain) is another. Keeping them in
    separate files means neither can silently overwrite the other's evidence.
    """
    safe = re.sub(r"[^a-z0-9-]", "", (suffix or "").lower())
    if not safe:
        return RECEIPT_JSON, RECEIPT_MD
    return (
        RECEIPT_JSON.with_name(f"ab-c-sample-receipt-{safe}.json"),
        RECEIPT_MD.with_name(f"ab-c-sample-receipt-{safe}.md"),
    )


def _write_receipt(receipt: Dict[str, Any], json_path: Path) -> None:
    receipt["finished_at"] = _now()
    blob = json.dumps(receipt, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to write a receipt containing {banned!r}")
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"wrote {json_path.relative_to(ROOT).as_posix()}")


def _write_summary_md(receipt: Dict[str, Any], md_path: Path) -> None:
    lines = [
        "# A/B/C narration sample receipt (Issue #34)",
        "",
        f"- attempt: `{receipt.get('attempt_id')}`",
        f"- executed: `{receipt.get('executed')}`",
        f"- outcome: `{receipt.get('outcome')}`",
        f"- route: `{receipt.get('route')}` / model `{receipt.get('model')}`",
        f"- credential class: `{receipt.get('credential_class')}` "
        f"(source `{receipt.get('credential_source')}`)",
        "",
        "## Listen (gitignored real audio)",
        "",
    ]
    for arm, record in (receipt.get("variants") or {}).items():
        audio = record.get("audio") or {}
        if not audio.get("path"):
            audio = record.get("joined") or {}
        if audio.get("path"):
            lines.append(f"- **{arm}**: `{audio['path']}` "
                         f"({audio.get('duration_s')} s, sha256 "
                         f"`{str(audio.get('sha256'))[:16]}...`)")
        for seg in record.get("segments") or []:
            seg_audio = seg.get("audio") or {}
            if seg_audio.get("path"):
                lines.append(f"  - {arm} {seg.get('id')}: `{seg_audio['path']}` "
                             f"({seg_audio.get('duration_s')} s)")
    if receipt.get("variants", {}).get("A", {}).get("alignment_note"):
        lines += [
            "",
            "A is a local excerpt of the existing Golden narration, cut at a",
            "detected silence. Its alignment with the sample text is approximate",
            "and is described in `alignment_note` plus the A ASR record.",
        ]
    for extra in receipt.get("extra_segments") or []:
        audio = extra.get("audio") or {}
        if audio.get("path"):
            lines.append(
                f"- **extra {extra.get('id')}** (term check): `{audio['path']}` "
                f"({audio.get('duration_s')} s)"
            )
    lines += [
        "",
        "## Not decided by this receipt",
        "",
        "- Emotion naturalness, pace, pause naturalness, voice similarity, term",
        "  pronunciation and join artifacts are **listening** judgements.",
        "  Machine measurements (durations, ASR coverage, loudness, trace ids,",
        "  usage) are recorded in the JSON; they cannot replace the Founder's ears.",
        "- `production_ready` stays `false`; `human_review` stays",
        "  `PENDING_FOUNDER_REVIEW`.",
        "",
    ]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {md_path.relative_to(ROOT).as_posix()}")


def _recheck(args) -> int:
    """Recompute audio measurements (incl. technical QC and silence) in place.

    No provider call, no ASR call, no budget movement: the files on disk are
    re-measured so a receipt can be enriched or corrected when the measurement
    code improves, without re-generating anything. ASR records are deliberately
    left untouched -- retranscribing unchanged audio spends quota and proves
    nothing new.
    """
    json_path, md_path = _receipt_paths(args.receipt_suffix)
    if not json_path.is_file():
        print(f"REFUSED: no receipt to recheck at {json_path}", file=sys.stderr)
        return 2
    receipt = json.loads(json_path.read_text(encoding="utf-8"))
    updated = 0

    def refresh(audio: Dict[str, Any]) -> None:
        nonlocal updated
        path = Path(audio.get("path") or "")
        if path.is_file():
            audio.update(_audio_record(path))
            updated += 1

    for record in (receipt.get("variants") or {}).values():
        if isinstance(record.get("audio"), dict):
            refresh(record["audio"])
        if isinstance(record.get("joined"), dict):
            refresh(record["joined"])
        for seg in record.get("segments") or []:
            if isinstance(seg.get("audio"), dict):
                refresh(seg["audio"])
    for extra in receipt.get("extra_segments") or []:
        if isinstance(extra.get("audio"), dict):
            refresh(extra["audio"])

    receipt["rechecked_at"] = _now()
    receipt["recheck_note"] = (
        "audio measurements (technical QC and silence maps) recomputed from the "
        "files on disk; no provider call and no ASR call was made"
    )
    _write_receipt(receipt, json_path)
    _write_summary_md(receipt, md_path)
    print(f"rechecked {updated} audio file(s)")
    return 0


# --- main -----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="send the real provider requests. Without this, "
                             "nothing is transmitted and no money is read.")
    parser.add_argument("--variants", default="ABC",
                        help="subset of ABC to run (default: ABC)")
    parser.add_argument("--a-mode", choices=("reuse", "fresh"), default="reuse",
                        help="reuse = cut the existing Golden narration (no "
                             "provider cost); fresh = re-synthesise the control")
    parser.add_argument("--a-source", default=DEFAULT_A_SOURCE)
    parser.add_argument("--a-target-s", type=float, default=28.0)
    parser.add_argument("--budget-chars", type=int, default=1500,
                        help="hard cap on cumulative billable synthesis characters")
    parser.add_argument("--budget-asr-calls", type=int, default=6,
                        help="hard cap on ASR backcheck calls")
    parser.add_argument("--regenerate", default="",
                        help="comma-separated segment ids to force a fresh "
                             "synthesis even on a cache hit (partial regeneration)")
    parser.add_argument("--extra-segment", default="",
                        help="comma-separated spoken-script segment ids to "
                             "synthesise and ASR as bounded term checks; use "
                             "for vetted terms the sample does not contain "
                             "(e.g. doctor). Requires --execute to send.")
    parser.add_argument("--receipt-suffix", default="",
                        help="sanitised suffix for a separate receipt, e.g. "
                             "'term-check'; the sample receipt is never "
                             "overwritten by an auxiliary run")
    parser.add_argument("--recheck", action="store_true",
                        help="recompute audio measurements in the existing "
                             "receipt (no provider, no ASR, no budget)")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--skip-asr", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.recheck:
        return _recheck(args)

    variants = [v for v in args.variants.upper() if v in "ABC"]
    extra_ids = [s.strip() for s in args.extra_segment.split(",") if s.strip()]
    if not variants and not extra_ids:
        print(
            "no variants and no extra segments selected; nothing to do "
            "(use --variants ABC or --extra-segment S04)",
            file=sys.stderr,
        )
        return 2
    regenerate_ids = [s.strip() for s in args.regenerate.split(",") if s.strip()]
    receipt_json, receipt_md = _receipt_paths(args.receipt_suffix)

    load_local_env_file(ROOT / ".env")
    credential = resolve_subscription_credential()
    lexicon = default_zh_lexicon()

    receipt: Dict[str, Any] = {
        "schema": "contentops.ab-sample/v1",
        "stage": "AB_C_NARRATION_SAMPLE",
        "issue": "#34",
        "attempt_id": f"absample-{uuid.uuid4().hex[:12]}",
        "started_at": _now(),
        "executed": bool(args.execute),
        "variants_requested": list(variants),
        "extra_segments_requested": list(extra_ids),
        "voice_id": VOICE_ID,
        "voice_id_hash": VOICE_ID_HASH,
        "model": MODEL,
        "host": MINIMAX_CN_HOST,
        "transport": "native_http_cn",
        "route": MPLAN_NARRATION_ROUTE,
        "credential_class": credential.credential_class,
        "credential_source": credential.source,
        "payg_key_used_for_this_request": False,
        "provider_call_budget": {
            "subscription_tts_planned": 0,
            "asr_transcribe_planned": 0,
            "upload": 0,
            "voice_creation": 0,
            "automatic_retry": 0,
            "automatic_top_up": 0,
        },
        "notes": [],
    }

    # --- spoken script: verify before anything else ------------------------------
    if not SPOKEN_SCRIPT.is_file():
        print(f"REFUSED: spoken script missing: {SPOKEN_SCRIPT}", file=sys.stderr)
        return 1
    script = load_spoken_script(SPOKEN_SCRIPT)
    original_text = ORIGINAL.read_text(encoding="utf-8")
    lock_digest = json.loads(EVIDENCE_LOCK.read_text(encoding="utf-8")).get(
        "narration_text_sha256"
    )
    try:
        verification = verify_script(
            script,
            original_text=original_text,
            canonical_original_digest=canonical_blob_sha256(ORIGINAL),
            evidence_lock_digest=lock_digest,
        )
    except SpokenScriptError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    receipt["spoken_script"] = {
        "path": SPOKEN_SCRIPT.relative_to(ROOT).as_posix(),
        "original_canonical_blob_sha256": canonical_blob_sha256(ORIGINAL),
        "evidence_lock_sha256": lock_digest,
        "sample_segments": list(script.sample_segment_ids),
        "sample_original_paragraphs": list(script.sample_original_paragraphs),
        "verification": verification,
    }

    sample_original = sample_original_text(original_text, script.sample_original_paragraphs)
    sample_display = script.sample_text()
    sample_synthesis = normalize_paragraph_newlines(lexicon.spoken_text(sample_display))
    sample_segments = [
        SegmentSpec(
            id=spec.id,
            role=spec.role,
            text=spec.text,
            emotion=spec.c_emotion,
            speed=float(spec.c_speed) if spec.c_speed is not None else 1.0,
            pause_after_s=spec.pause_after_s,
        )
        for spec in script.sample_segments()
    ]
    c_synthesis_texts = [
        normalize_paragraph_newlines(lexicon.spoken_text(seg.text))
        for seg in sample_segments
    ]
    extra_specs: List[SegmentSpec] = []
    for sid in extra_ids:
        try:
            source_segment = script.segment(sid)
        except KeyError:
            print(
                f"REFUSED: --extra-segment {sid!r} is not a segment of the "
                f"spoken script (known ids: "
                f"{', '.join(spec.id for spec in script.segments)})",
                file=sys.stderr,
            )
            return 2
        extra_specs.append(
            SegmentSpec(
                id=source_segment.id,
                role=source_segment.role,
                text=source_segment.text,
                emotion=source_segment.c_emotion,
                speed=(
                    float(source_segment.c_speed)
                    if source_segment.c_speed is not None
                    else 1.0
                ),
                pause_after_s=source_segment.pause_after_s,
            )
        )
    if len({spec.id for spec in extra_specs}) != len(extra_specs):
        print("REFUSED: duplicate --extra-segment ids", file=sys.stderr)
        return 2
    extra_synthesis_texts = [
        normalize_paragraph_newlines(lexicon.spoken_text(spec.text))
        for spec in extra_specs
    ]
    receipt["sample"] = {
        "original_text_sha256": _sha256_text(sample_original),
        "display_sha256": _sha256_text(sample_display),
        "synthesis_sha256": _sha256_text(sample_synthesis),
        "synthesis_characters": len(sample_synthesis),
        "segments": [
            {
                "id": seg.id,
                "role": seg.role,
                "display_sha256": _sha256_text(seg.text),
                "synthesis_sha256": _sha256_text(text),
                "parameters": {
                    "c_emotion": seg.emotion or "auto (absent)",
                    "c_speed": seg.speed,
                    "pause_after_s": seg.pause_after_s,
                },
            }
            for seg, text in zip(sample_segments, c_synthesis_texts)
        ],
    }

    # --- budget and plan ---------------------------------------------------------
    out_dir = (ROOT / args.out_dir).resolve()
    cache_dir = out_dir / "segments"
    diagnostics_dir = ROOT / ".private" / "diagnostics"

    a_synthesis = normalize_paragraph_newlines(
        flatten_for_cli(lexicon.spoken_text(sample_original))
    )
    planned_syntheses: List[str] = []
    if "B" in variants:
        planned_syntheses.append(sample_synthesis)
    if "C" in variants:
        planned_syntheses += c_synthesis_texts
    planned_syntheses += extra_synthesis_texts
    if "A" in variants and args.a_mode == "fresh":
        planned_syntheses.append(a_synthesis)
    estimated_chars = estimated_billable_characters(planned_syntheses)
    planned_tts = (1 if "B" in variants else 0) + (
        len(sample_segments) if "C" in variants else 0
    ) + len(extra_specs) + (1 if ("A" in variants and args.a_mode == "fresh") else 0)
    planned_asr = 0 if args.skip_asr else len(variants) + len(extra_specs)
    receipt["provider_call_budget"]["subscription_tts_planned"] = planned_tts
    receipt["provider_call_budget"]["asr_transcribe_planned"] = planned_asr
    receipt["budget"] = {
        "estimated_billable_characters": estimated_chars,
        "budget_chars": args.budget_chars,
        "asr_calls_planned": planned_asr,
        "asr_calls_budget": args.budget_asr_calls,
        "a_mode": args.a_mode,
    }
    if estimated_chars > args.budget_chars:
        print(
            f"REFUSED: estimated {estimated_chars} billable characters exceed the "
            f"budget of {args.budget_chars}. Nothing was sent.",
            file=sys.stderr,
        )
        receipt["outcome"] = "REFUSED_BUDGET"
        _write_receipt(receipt, receipt_json)
        return 1
    if planned_asr > args.budget_asr_calls:
        print(
            f"REFUSED: {planned_asr} ASR calls exceed the budget of "
            f"{args.budget_asr_calls}.",
            file=sys.stderr,
        )
        receipt["outcome"] = "REFUSED_ASR_BUDGET"
        _write_receipt(receipt, receipt_json)
        return 1

    print("=== A/B/C NARRATION SAMPLE ===")
    print(f"  attempt_id     : {receipt['attempt_id']}")
    print(f"  variants       : {''.join(variants) or 'none'} (A mode: {args.a_mode})")
    if extra_specs:
        print(f"  extra segments : {', '.join(spec.id for spec in extra_specs)} (term checks)")
    print(f"  sample         : segments {list(script.sample_segment_ids)} / "
          f"original paragraphs {list(script.sample_original_paragraphs)}")
    print(f"  estimated chars: {estimated_chars} billable (budget {args.budget_chars})")
    print(f"  credential     : {credential.credential_class} ({credential.source})")

    if not args.execute:
        print("=== DRY RUN. NOTHING WAS SENT. ===")
        plan = {
            "a_mode": args.a_mode,
            "a_source": str((ROOT / args.a_source).resolve()),
            "a_source_exists": (ROOT / args.a_source).is_file(),
            "b_requests": 1 if "B" in variants else 0,
            "c_segments": [seg.id for seg in sample_segments] if "C" in variants else [],
            "extra_segments": [spec.id for spec in extra_specs],
            "regenerate": regenerate_ids,
            "sample_synthesis_sha256": _sha256_text(sample_synthesis),
            "receipt_path": str(receipt_json),
        }
        if "C" in variants:
            plan["c_plan"] = [
                {
                    "id": entry.spec.id,
                    "action": entry.action,
                    "fingerprint": entry.fingerprint,
                }
                for entry in plan_segment_renders(
                    sample_segments,
                    voice_id=VOICE_ID, model=MODEL, lexicon=lexicon,
                    cache_dir=cache_dir, regenerate_ids=regenerate_ids,
                    sample_rate=32000, fmt="wav", channel=1,
                )
            ]
        receipt["outcome"] = "DRY_RUN"
        receipt["plan"] = plan
        out_dir.mkdir(parents=True, exist_ok=True)
        plan_path = out_dir / "ab-c-sample-plan.json"
        plan_path.write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n",
        )
        print(f"  wrote dry-run plan: {plan_path}")
        for entry in plan.get("c_plan", []):
            print(f"  C {entry['id']}: {entry['action']}")
        return 0

    if credential.credential_class != CREDENTIAL_SUBSCRIPTION or not credential.usable:
        print(
            f"REFUSED: narration requires a Subscription-class credential; the "
            f"resolved class is {credential.credential_class} "
            f"(source {credential.source}). Nothing was sent.",
            file=sys.stderr,
        )
        receipt["outcome"] = "REFUSED_CREDENTIAL_CLASS"
        _write_receipt(receipt, receipt_json)
        return 1

    runner = ExperimentRunner(
        credential=credential,
        out_dir=out_dir,
        diagnostics_dir=diagnostics_dir,
        asr_budget=args.budget_asr_calls,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    usage_running = [0]
    variants_record: Dict[str, Any] = {}
    try:
        receipt["preflight"] = runner.preflight()

        # --- A -------------------------------------------------------------------
        if "A" in variants:
            a_out = out_dir / "A-original-excerpt.wav"
            if args.a_mode == "reuse":
                source = (ROOT / args.a_source).resolve()
                if not source.is_file():
                    raise ExperimentRefusal(
                        "A_SOURCE_ABSENT",
                        [
                            f"A reuse mode needs the existing Golden narration at "
                            f"{source}; it is not present. Either regenerate the "
                            f"Golden narration first or pass --a-mode fresh "
                            f"(a paid control reproduction). Nothing was sent."
                        ],
                    )
                duration = measure_audio(source).duration_s or 0.0
                silences = _detect_silences(source)
                boundary, chosen = _choose_cut_boundary(
                    silences, duration_s=duration, target_s=args.a_target_s
                )
                _cut_excerpt(source, boundary, a_out)
                variants_record["A"] = {
                    "mode": "reuse_local_excerpt",
                    "source": str(source),
                    "source_sha256": sha256_file(source),
                    "source_duration_s": duration,
                    "cut_end_s": boundary,
                    "cut_boundary_silence": chosen,
                    "detected_silences": silences,
                    "alignment_note": (
                        "The cut ends at a detected silence so it cannot clip "
                        "mid-word. The source was generated from single-line text, "
                        "so paragraph boundaries are not distinguishable from "
                        "sentence pauses in it; text alignment with the sample is "
                        "approximate and the ASR backcheck below is the evidence "
                        "for how close it is."
                    ),
                    "audio": _audio_record(a_out),
                }
            else:
                payload = build_t2a_payload(
                    text=a_synthesis, voice_id=VOICE_ID, model=MODEL,
                    speed=1.0, sample_rate=32000, fmt="wav", channel=1,
                )
                result, _ = runner.synth(
                    payload=payload, label="A",
                    attempt_id=f"{receipt['attempt_id']}-A",
                    usage_running_total=usage_running, budget_chars=args.budget_chars,
                )
                raw = out_dir / "A-original-fresh-raw.wav"
                raw.write_bytes(result.audio_bytes)
                normalisation = normalise_speech(raw, a_out)
                if not normalisation.get("ok"):
                    raise RuntimeError(f"A normalisation failed: {normalisation}")
                variants_record["A"] = {
                    "mode": "fresh_control_single_line",
                    "explanation": (
                        "Explicit reproduction of the pre-v2 parameters for the "
                        "control arm: original text flattened to one line by the "
                        "legacy CLI-compat helper, speed 1, no emotion."
                    ),
                    "synthesis_sha256": _sha256_text(a_synthesis),
                    "audio": _audio_record(a_out),
                }
            if not args.skip_asr:
                variants_record["A"]["asr"] = runner.asr(
                    audio_path=a_out,
                    expected=_expected_for_asr(sample_original, lexicon),
                    label="A",
                )

        # --- B -------------------------------------------------------------------
        if "B" in variants:
            b_out = out_dir / "B-spoken-auto.wav"
            b_fingerprint = segment_fingerprint(
                voice_id=VOICE_ID, model=MODEL, synthesis_text=sample_synthesis,
                emotion=None, speed=1.0, sample_rate=32000, fmt="wav", channel=1,
                lexicon_component=lexicon.fingerprint_component(),
            )
            cached = lookup_cached_segment(cache_dir, b_fingerprint)
            b_record: Dict[str, Any] = {
                "fingerprint": b_fingerprint,
                "synthesis_sha256": _sha256_text(sample_synthesis),
                "synthesis_characters": len(sample_synthesis),
                "parameters": {"emotion": "auto (absent)", "speed": 1.0},
            }
            if cached is not None and "B" not in regenerate_ids:
                shutil.copyfile(cached.normalised_path, b_out)
                b_record["provider_call"] = False
                b_record["cache"] = "hit"
            else:
                payload = build_t2a_payload(
                    text=sample_synthesis, voice_id=VOICE_ID, model=MODEL,
                    speed=1.0, sample_rate=32000, fmt="wav", channel=1,
                )
                result, request_record = runner.synth(
                    payload=payload, label="B",
                    attempt_id=f"{receipt['attempt_id']}-B",
                    usage_running_total=usage_running, budget_chars=args.budget_chars,
                )
                raw = out_dir / "B-spoken-auto-raw.wav"
                raw.write_bytes(result.audio_bytes)
                normalisation = normalise_speech(raw, b_out)
                if not normalisation.get("ok"):
                    raise RuntimeError(f"B normalisation failed: {normalisation}")
                store_cached_segment(
                    cache_dir, b_fingerprint,
                    raw_bytes=result.audio_bytes, normalised_path=b_out,
                    meta={
                        "segment_id": "B-sample",
                        "synthesis_sha256": _sha256_text(sample_synthesis),
                        "voice_id_hash": VOICE_ID_HASH,
                        "model": MODEL, "emotion": None, "speed": 1.0,
                        "sample_rate": 32000, "format": "wav", "channel": 1,
                        "lexicon_version": lexicon.version,
                        "provider": request_record["provider"],
                        "created_at": _now(),
                    },
                )
                b_record["provider_call"] = True
                b_record["cache"] = "miss"
                b_record["request"] = request_record
            b_record["audio"] = _audio_record(b_out)
            if not args.skip_asr:
                b_record["asr"] = runner.asr(
                    audio_path=b_out,
                    expected=_expected_for_asr(sample_display, lexicon),
                    label="B",
                )
            variants_record["B"] = b_record

        # --- C -------------------------------------------------------------------
        if "C" in variants:
            plan = plan_segment_renders(
                sample_segments,
                voice_id=VOICE_ID, model=MODEL, lexicon=lexicon,
                cache_dir=cache_dir, regenerate_ids=regenerate_ids,
                sample_rate=32000, fmt="wav", channel=1,
            )
            c_records: List[Dict[str, Any]] = []
            normalised_paths: List[Path] = []
            for index, entry in enumerate(plan):
                seg_out = out_dir / f"C-{entry.spec.id}.wav"
                record: Dict[str, Any] = {
                    "id": entry.spec.id,
                    "role": entry.spec.role,
                    "fingerprint": entry.fingerprint,
                    "synthesis_sha256": _sha256_text(entry.synthesis_text),
                    "synthesis_characters": len(entry.synthesis_text),
                    "parameters": {
                        "emotion": entry.spec.emotion or "auto (absent)",
                        "speed": entry.spec.speed,
                        "pause_after_s": entry.spec.pause_after_s,
                    },
                }
                if entry.action == ACTION_REUSE_CACHE and entry.cached is not None:
                    shutil.copyfile(entry.cached.normalised_path, seg_out)
                    record["provider_call"] = False
                    record["cache"] = "hit"
                else:
                    payload = build_segment_payload(
                        entry.spec, voice_id=VOICE_ID, model=MODEL, lexicon=lexicon,
                        sample_rate=32000, fmt="wav", channel=1,
                    )
                    result, request_record = runner.synth(
                        payload=payload, label=f"C:{entry.spec.id}",
                        attempt_id=f"{receipt['attempt_id']}-C-{entry.spec.id}",
                        usage_running_total=usage_running,
                        budget_chars=args.budget_chars,
                    )
                    raw = out_dir / f"C-{entry.spec.id}-raw.wav"
                    raw.write_bytes(result.audio_bytes)
                    normalisation = normalise_speech(raw, seg_out)
                    if not normalisation.get("ok"):
                        raise RuntimeError(
                            f"C:{entry.spec.id} normalisation failed: {normalisation}"
                        )
                    store_cached_segment(
                        cache_dir, entry.fingerprint,
                        raw_bytes=result.audio_bytes, normalised_path=seg_out,
                        meta={
                            "segment_id": entry.spec.id,
                            "role": entry.spec.role,
                            "synthesis_sha256": _sha256_text(entry.synthesis_text),
                            "voice_id_hash": VOICE_ID_HASH,
                            "model": MODEL,
                            "emotion": entry.spec.emotion,
                            "speed": entry.spec.speed,
                            "sample_rate": 32000, "format": "wav", "channel": 1,
                            "lexicon_version": lexicon.version,
                            "provider": request_record["provider"],
                            "created_at": _now(),
                        },
                    )
                    record["provider_call"] = True
                    record["cache"] = (
                        "forced_regenerate"
                        if entry.spec.id in regenerate_ids
                        else "miss"
                    )
                    record["request"] = request_record
                record["audio"] = _audio_record(seg_out)
                normalised_paths.append(seg_out)
                c_records.append(record)

            joined = concatenate_segments(
                normalised_paths,
                gaps_after_s=[entry.spec.pause_after_s for entry in plan],
                out_path=out_dir / "C-segmented-joined.wav",
                work_dir=out_dir / "work",
                sample_rate=32000,
                channels=1,
            )
            c_record = {
                "segments": c_records,
                "joined": _audio_record(joined),
                "join_note": (
                    "Segment boundaries are joined with the declared silence gaps "
                    "(pause_after_s); the provider's own paragraph pause for B is "
                    "not observable in the API response, so B and C are compared "
                    "as heard, not as a controlled join-duration experiment."
                ),
            }
            if not args.skip_asr:
                c_record["asr"] = runner.asr(
                    audio_path=joined,
                    expected=_expected_for_asr(sample_display, lexicon),
                    label="C",
                )
            variants_record["C"] = c_record

        # --- extra segments: bounded term checks ---------------------------------
        # A term the 20-30 s sample does not contain (doctor, in this round)
        # cannot be verified from the sample's audio. These extra segments are
        # generated with their authored parameters and ASR-checked on their own;
        # they never join the C arm. Partial regeneration applies here too: a
        # cached segment is reused, and --regenerate forces a fresh take.
        extra_records: List[Dict[str, Any]] = []
        for spec, synthesis_text in zip(extra_specs, extra_synthesis_texts):
            seg_out = out_dir / f"X-{spec.id}.wav"
            fingerprint = segment_fingerprint(
                voice_id=VOICE_ID, model=MODEL, synthesis_text=synthesis_text,
                emotion=spec.emotion, speed=spec.speed,
                sample_rate=32000, fmt="wav", channel=1,
                lexicon_component=lexicon.fingerprint_component(),
            )
            record: Dict[str, Any] = {
                "id": spec.id,
                "role": spec.role,
                "purpose": "TERM_CHECK_OUTSIDE_SAMPLE",
                "fingerprint": fingerprint,
                "synthesis_sha256": _sha256_text(synthesis_text),
                "synthesis_characters": len(synthesis_text),
                "parameters": {
                    "emotion": spec.emotion or "auto (absent)",
                    "speed": spec.speed,
                },
            }
            cached = lookup_cached_segment(cache_dir, fingerprint)
            if cached is not None and spec.id not in regenerate_ids:
                shutil.copyfile(cached.normalised_path, seg_out)
                record["provider_call"] = False
                record["cache"] = "hit"
            else:
                payload = build_segment_payload(
                    spec, voice_id=VOICE_ID, model=MODEL, lexicon=lexicon,
                    sample_rate=32000, fmt="wav", channel=1,
                )
                result, request_record = runner.synth(
                    payload=payload, label=f"extra:{spec.id}",
                    attempt_id=f"{receipt['attempt_id']}-X-{spec.id}",
                    usage_running_total=usage_running,
                    budget_chars=args.budget_chars,
                )
                raw = out_dir / f"X-{spec.id}-raw.wav"
                raw.write_bytes(result.audio_bytes)
                normalisation = normalise_speech(raw, seg_out)
                if not normalisation.get("ok"):
                    raise RuntimeError(
                        f"extra:{spec.id} normalisation failed: {normalisation}"
                    )
                store_cached_segment(
                    cache_dir, fingerprint,
                    raw_bytes=result.audio_bytes, normalised_path=seg_out,
                    meta={
                        "segment_id": spec.id,
                        "role": spec.role,
                        "purpose": "TERM_CHECK_OUTSIDE_SAMPLE",
                        "synthesis_sha256": _sha256_text(synthesis_text),
                        "voice_id_hash": VOICE_ID_HASH,
                        "model": MODEL,
                        "emotion": spec.emotion,
                        "speed": spec.speed,
                        "sample_rate": 32000, "format": "wav", "channel": 1,
                        "lexicon_version": lexicon.version,
                        "provider": request_record["provider"],
                        "created_at": _now(),
                    },
                )
                record["provider_call"] = True
                record["cache"] = (
                    "forced_regenerate" if spec.id in regenerate_ids else "miss"
                )
                record["request"] = request_record
            record["audio"] = _audio_record(seg_out)
            if not args.skip_asr:
                record["asr"] = runner.asr(
                    audio_path=seg_out,
                    expected=_expected_for_asr(spec.text, lexicon),
                    label=f"extra:{spec.id}",
                )
            extra_records.append(record)

        # --- postflight ----------------------------------------------------------
        post = read_money(MINIMAX_CN_HOST, credential.key)
        pre = receipt["preflight"]["money"]
        deltas = delta_money(pre, post)
        classification = classify_mplan_only(
            quota_before=pre["quota"], quota_after=post["quota"], deltas=deltas
        )
        receipt["postflight"] = {
            "quota_after": post["quota"],
            "balances_after": post["balances"],
            "deltas": deltas,
            "plan_only_classification": classification,
        }
        receipt["variants"] = variants_record
        receipt["extra_segments"] = extra_records
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage_running[0]
        receipt["budget"]["asr_calls_used"] = runner.asr_state["used"]
        receipt["listening_comparison"] = {
            "status": "PENDING_FOUNDER_LISTENING",
            "human_metrics": [
                "emotion naturalness",
                "speech pace",
                "pause naturalness",
                "voice similarity to founder_primary_v1",
                "term pronunciation accuracy",
                "audio join artifacts",
            ],
            "machine_metrics_note": (
                "Durations, loudness, ASR coverage and trace ids are recorded; "
                "none of them can approve quality or replace listening."
            ),
        }
        receipt["human_review"] = "PENDING_FOUNDER_REVIEW"
        receipt["production_ready"] = False
        receipt["outcome"] = "AB_C_READY_FOR_FOUNDER_LISTENING"
        if not classification["verified"]:
            receipt["notes"].append(
                f"plan-only verification: {classification['status']} "
                f"(basis {classification['basis']})"
            )
        _write_receipt(receipt, receipt_json)
        _write_summary_md(receipt, receipt_md)
        print("=== STOP: Founder listening is pending. ===")
        return 0
    except ExperimentRefusal as refusal:
        receipt["outcome"] = REFUSED
        receipt["refusal"] = {"code": refusal.code, "reasons": refusal.reasons}
        receipt["variants"] = variants_record
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage_running[0]
        _write_receipt(receipt, receipt_json)
        _write_summary_md(receipt, receipt_md)
        print(f"REFUSED [{refusal.code}]: " + "; ".join(refusal.reasons), file=sys.stderr)
        return 1
    except NativeTtsRefusal as refusal:
        receipt["outcome"] = PROVIDER_FAILED
        receipt["provider_status"] = refusal.structured()
        receipt["variants"] = variants_record
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage_running[0]
        _write_receipt(receipt, receipt_json)
        _write_summary_md(receipt, receipt_md)
        print(
            f"PROVIDER REFUSED: HTTP {refusal.http_status} / status "
            f"{refusal.provider_status_code}: {refusal.provider_status_msg}",
            file=sys.stderr,
        )
        return 3
    except Exception as exc:  # noqa: BLE001 - recorded, never silently swallowed
        receipt["outcome"] = PROVIDER_FAILED
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
        receipt["variants"] = variants_record
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage_running[0]
        _write_receipt(receipt, receipt_json)
        _write_summary_md(receipt, receipt_md)
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
