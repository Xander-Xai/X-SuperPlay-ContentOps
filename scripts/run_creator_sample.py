#!/usr/bin/env python3
"""Minimal D/E/F narration diagnosis with hidden candidate labels. Issue #34, v3.

The v2 listening verdict: tests passed, the voice still sounded mechanical and
the emotion/rhythm did not follow the content. The v3 diagnosis
(`projects/easel-enhanced-golden/review/narration-v3-diagnosis.md`) separated
the variables; this script generates one ~20 s sample with only one variable
changed per candidate:

```
D  new creator script + founder clone + auto emotion (no director controls)
E  the same text + the same clone + the director's selective controls
   (2 groups, 1 justified explicit emotion, intent-paced pauses)
F  the same text and parameters as D, but the subscription-confirmed official
   preset voice -- isolates "is it the voice?" from "is it the delivery?"
```

B and C from the v2 round are referenced (not regenerated) as the previous
baseline. The three new candidates are delivered as `candidate-1/2/3.wav` with
**no version information in the filenames**; the D/E/F mapping lives in the
receipt (`listening_key`) so the Founder can listen blind and reveal afterwards.

Safety, unchanged from the v2 rules: M Plan Subscription Key only (the strict
resolver), the M Plan gate plus before/after plan-quota and balance reads on
every real request, `--execute` as the explicit switch, hard caps on billable
characters and ASR calls. No re-clone, no top-up, no publish, no full-narration
run. `production_ready` stays false and `human_review` stays
`PENDING_FOUNDER_REVIEW`; ASR and CI passing is not a naturalness verdict.

Exit codes: 0 = completed (or dry run); 1 = refused; 2 = usage/validation; 3 =
provider or media failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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

from run_ab_sample import ExperimentRefusal, ExperimentRunner  # noqa: E402
from verify_creator_script import load_verified_plan, synthesis_text  # noqa: E402

from contentops.media.audio import measure_audio, normalise_speech, technical_qc  # noqa: E402
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
    strip_pause_markers,
)
from contentops.media.native_rounds import (  # noqa: E402
    MPLAN_NARRATION_ROUTE,
    delta_money,
    classify_mplan_only,
    read_money,
    write_private_provider_response,
)
from contentops.media.narration_director import mapped_groups  # noqa: E402
from contentops.media.t2a_segments import (  # noqa: E402
    SegmentSpec,
    build_segment_payload,
    concatenate_segments,
    estimated_billable_characters,
    lookup_cached_segment,
    segment_fingerprint,
    store_cached_segment,
)

MODEL = "speech-2.8-hd"
CLONE_VOICE = "founder_primary_v1"
CLONE_VOICE_ID_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"

#: The preset voice this account has already exercised on the M Plan
#: (receipt below). Preset voices are confirmed in-plan by that run; the D/E/F
#: billing gate still applies to every request regardless.
PRESET_VOICE = "Chinese (Mandarin)_Reliable_Executive"
PRESET_VOICE_EVIDENCE = {
    "voice_id": PRESET_VOICE,
    "basis": "used for the M2.0 Golden B asset on this account's M Plan",
    "receipt": "projects/easel-enhanced-golden/golden-assets/voice/B-minimax-speech-2.8-hd.receipt.json",
    "verified_on": "2026-10-04",
}

#: candidate-N -> candidate id. Fixed but deliberately not D/E/F-ordered, and
#: never written into a filename: listening is blind until the receipt is read.
LABEL_ORDER: Tuple[str, ...] = ("F", "D", "E")

RECEIPT_JSON = ROOT / "projects/easel-enhanced-golden/review/narration-v3-sample-receipt.json"
RECEIPT_MD = ROOT / "projects/easel-enhanced-golden/review/narration-v3-sample-receipt.md"
REVIEW_MD = ROOT / "projects/easel-enhanced-golden/review/listening-review-v3.md"
DEFAULT_OUT_DIR = "outputs/founder-v3-sample"
V2_DIR = ROOT / "outputs" / "founder-ab-sample"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _audio_record(path: Path) -> Dict[str, Any]:
    measured = measure_audio(path)
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "duration_s": measured.duration_s,
        "sample_rate_hz": measured.sample_rate_hz,
        "channels": measured.channels,
        "codec": measured.codec,
        "integrated_lufs": measured.integrated_lufs,
        "true_peak_db": measured.true_peak_db,
        "technical_qc": technical_qc(path, expected_sample_rate_hz=32000),
    }


def _reused_baselines() -> List[Dict[str, Any]]:
    """Reference the v2 B/C audio without regenerating it."""
    records: List[Dict[str, Any]] = []
    for name, path in (
        ("B_v2_single_request", V2_DIR / "B-spoken-auto.wav"),
        ("C_v2_segmented_join", V2_DIR / "C-segmented-joined.wav"),
    ):
        if path.is_file():
            record = {"name": name, "present": True}
            record.update(_audio_record(path))
            records.append(record)
        else:
            records.append({"name": name, "present": False, "path": str(path)})
    return records


def _write_receipt(receipt: Dict[str, Any]) -> None:
    receipt["finished_at"] = _now()
    blob = json.dumps(receipt, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to write a receipt containing {banned!r}")
    RECEIPT_JSON.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT_JSON.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"wrote {RECEIPT_JSON.relative_to(ROOT).as_posix()}")


def _write_review_template() -> None:
    """The Founder's listening template. Static; safe to overwrite."""
    text = """# Narration v3 listening review (Founder)

Listen to the three candidates first; do NOT read the key in
`narration-v3-sample-receipt.json` before scoring.

Files:

```
outputs/founder-v3-sample/candidate-1.wav
outputs/founder-v3-sample/candidate-2.wav
outputs/founder-v3-sample/candidate-3.wav
```

Score each candidate 1-5 on the six criteria and write down the failure
positions (timestamp or word). "ASR passed" and "CI passed" are not quality
verdicts and must not be treated as one.

| candidate | 1. sounds like a real person talking | 2. emotion fits the content | 3. pace changes are comfortable | 4. emphasis lands on the right words | 5. still sounds like the Founder | 6. no unnatural pauses or join artifacts | failure positions |
|---|---|---|---|---|---|---|---|
| candidate-1 | | | | | | | |
| candidate-2 | | | | | | | |
| candidate-3 | | | | | | | |

Free notes (what felt mechanical, which sentence felt wrong, which direction
sounds better):

```
```

Overall decision (pick one and write why):

- [ ] Copy still needs another edit
- [ ] Director strategy needs adjustment
- [ ] Voice (clone) is the limiting factor
- [ ] One candidate is acceptable to continue from
"""
    REVIEW_MD.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {REVIEW_MD.relative_to(ROOT).as_posix()}")


# --- candidates ------------------------------------------------------------------


class Candidate:
    def __init__(
        self,
        *,
        cid: str,
        label: str,
        voice_id: str,
        text: str,
        emotion: Optional[str],
        speed: float,
        groups: Optional[List[Any]] = None,
        group_params: Optional[List[Tuple[Optional[str], float, float]]] = None,
    ) -> None:
        self.id = cid
        self.label = label
        self.voice_id = voice_id
        self.text = text
        self.emotion = emotion
        self.speed = speed
        self.groups = groups  # mapped sample groups when segmented
        self.group_params = group_params or []


def _write_summary_md(receipt: Dict[str, Any]) -> None:
    """Render the tracked JSON receipt into a readable markdown summary."""
    lines = [
        "# Narration v3 D/E/F sample receipt (Issue #34)",
        "",
        f"- attempt: `{receipt.get('attempt_id')}`",
        f"- executed: `{receipt.get('executed')}`",
        f"- outcome: `{receipt.get('outcome')}`",
        f"- model: `{receipt.get('model')}` / route `{receipt.get('route')}`",
        f"- credential class: `{receipt.get('credential_class')}` "
        f"(source `{receipt.get('credential_source')}`)",
        f"- budget used: `{(receipt.get('budget') or {}).get('usage_characters_used')}` "
        f"of `{(receipt.get('budget') or {}).get('budget_chars')}` billable characters",
        "",
        "## Listen first (gitignored real audio)",
        "",
        "```",
        "outputs/founder-v3-sample/candidate-1.wav",
        "outputs/founder-v3-sample/candidate-2.wav",
        "outputs/founder-v3-sample/candidate-3.wav",
        "```",
        "",
        "Score the three candidates in `listening-review-v3.md` BEFORE reading",
        "the key below.",
        "",
        "## Listening key (reveal after scoring)",
        "",
    ]
    for name, cid in (receipt.get("listening_key") or {}).items():
        candidate = (receipt.get("candidates") or {}).get(cid) or {}
        audio = candidate.get("audio") or {}
        lines.append(
            f"- `{name}` = **{cid}** -- {candidate.get('label', '')} "
            f"({audio.get('duration_s')} s)"
        )
    lines += [
        "",
        "## Machine facts (not quality verdicts)",
        "",
        "- ASR and technical QC passing is not a naturalness verdict; the six",
        "  listening criteria in the review template are the acceptance gate.",
        "- Durations, loudness, silence maps, trace ids and usage are in the JSON.",
        "- `production_ready` stays `false`; `human_review` stays",
        "  `PENDING_FOUNDER_REVIEW`.",
        "",
    ]
    RECEIPT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {RECEIPT_MD.relative_to(ROOT).as_posix()}")


def _summary_only(args) -> int:
    """Render the existing JSON receipt to markdown. No provider, no ASR."""
    if not RECEIPT_JSON.is_file():
        print(f"REFUSED: no receipt to summarise at {RECEIPT_JSON}", file=sys.stderr)
        return 2
    receipt = json.loads(RECEIPT_JSON.read_text(encoding="utf-8"))
    _write_summary_md(receipt)
    return 0


def _build_candidates(result: dict, lexicon) -> Dict[str, Candidate]:
    creator = result["creator"]
    plan = result["plan"]
    sample_ids = list(plan.sample_unit_ids)
    d_display = "\n".join(creator.unit(uid).text for uid in sample_ids)
    d_synthesis = synthesis_text(d_display, lexicon)
    sample_groups = mapped_groups(plan, creator, section="sample.groups")
    return {
        "D": Candidate(
            cid="D", label="new script + clone voice + auto emotion (no director controls)",
            voice_id=CLONE_VOICE, text=d_synthesis, emotion=None, speed=1.0,
        ),
        "E": Candidate(
            cid="E", label="same text + clone voice + selective director controls",
            voice_id=CLONE_VOICE, text="", emotion=None, speed=1.0,
            groups=sample_groups,
            group_params=[
                (
                    group.emotion,
                    group.speed,
                    group.pause_after_s,
                )
                for group in sample_groups
            ],
        ),
        "F": Candidate(
            cid="F", label="same script and parameters as D, official preset voice (auto emotion)",
            voice_id=PRESET_VOICE, text=d_synthesis, emotion=None, speed=1.0,
        ),
    }


def _candidate_expected_for_asr(candidate: Candidate, lexicon) -> str:
    if candidate.groups:
        joined = "\n".join(group.text for group in candidate.groups)
        return strip_pause_markers(synthesis_text(joined, lexicon))
    return strip_pause_markers(candidate.text)


def _fingerprint(candidate: Candidate, lexicon, text: str, emotion: Optional[str], speed: float) -> str:
    return segment_fingerprint(
        voice_id=candidate.voice_id,
        model=MODEL,
        synthesis_text=text,
        emotion=emotion,
        speed=speed,
        sample_rate=32000,
        fmt="wav",
        channel=1,
        lexicon_component=lexicon.fingerprint_component(),
    )


def _run_candidate_single(
    *, runner: ExperimentRunner, candidate: Candidate, out_raw: Path, out_norm: Path,
    cache_dir: Path, lexicon, receipt: Dict[str, Any], usage: List[int], budget: int,
) -> Dict[str, Any]:
    fingerprint = _fingerprint(candidate, lexicon, candidate.text, candidate.emotion, candidate.speed)
    cached = lookup_cached_segment(cache_dir, fingerprint)
    record: Dict[str, Any] = {
        "id": candidate.id,
        "label": candidate.label,
        "voice_id": candidate.voice_id,
        "voice_id_hash": hashlib.sha256(candidate.voice_id.encode()).hexdigest(),
        "fingerprint": fingerprint,
        "synthesis_sha256": _sha256_text(candidate.text),
        "synthesis_characters": len(candidate.text),
        "director_controls": {"emotion": "auto (absent)", "speed": 1.0},
    }
    if cached is not None:
        shutil.copyfile(cached.normalised_path, out_norm)
        record["provider_call"] = False
        record["cache"] = "hit"
    else:
        payload = build_t2a_payload(
            text=candidate.text, voice_id=candidate.voice_id, model=MODEL,
            speed=1.0, sample_rate=32000, fmt="wav", channel=1,
        )
        result_audio, request_record = runner.synth(
            payload=payload, label=candidate.id,
            attempt_id=f"{receipt['attempt_id']}-{candidate.id}",
            usage_running_total=usage, budget_chars=budget,
        )
        out_raw.write_bytes(result_audio.audio_bytes)
        normalisation = normalise_speech(out_raw, out_norm)
        if not normalisation.get("ok"):
            raise RuntimeError(f"{candidate.id} normalisation failed: {normalisation}")
        store_cached_segment(
            cache_dir, fingerprint,
            raw_bytes=result_audio.audio_bytes, normalised_path=out_norm,
            meta={
                "candidate": candidate.id,
                "voice_id": candidate.voice_id,
                "voice_id_hash": hashlib.sha256(candidate.voice_id.encode()).hexdigest(),
                "synthesis_sha256": _sha256_text(candidate.text),
                "model": MODEL, "emotion": candidate.emotion, "speed": candidate.speed,
                "lexicon_version": lexicon.version,
                "provider": request_record["provider"],
                "created_at": _now(),
            },
        )
        record["provider_call"] = True
        record["cache"] = "miss"
        record["request"] = request_record
    record["audio"] = _audio_record(out_norm)
    return record


#: creator beat -> segment role vocabulary (the delivery layer's own words).
_BEAT_TO_SEGMENT_ROLE = {
    "HOOK": "INTRO",
    "SETUP": "INTRO",
    "EVIDENCE": "EVIDENCE",
    "TURN": "TURN",
    "PROBLEM": "PROBLEM",
    "VALUE": "CONCLUSION",
    "ENDING": "CONCLUSION",
}


def _group_segment_role(group, creator) -> str:
    first_unit = group.units[0]
    for unit in creator.units:
        if unit.id == first_unit:
            return _BEAT_TO_SEGMENT_ROLE.get(unit.beat, "EVIDENCE")
    return "EVIDENCE"


def _run_candidate_groups(
    *, runner: ExperimentRunner, candidate: Candidate, creator, out_dir: Path,
    cache_dir: Path, lexicon, receipt: Dict[str, Any], usage: List[int], budget: int,
) -> Dict[str, Any]:
    records: List[Dict[str, Any]] = []
    normalised_paths: List[Path] = []
    gaps: List[float] = []
    for group in candidate.groups:
        synth_text = synthesis_text(group.text, lexicon)
        fingerprint = _fingerprint(candidate, lexicon, synth_text, group.emotion, group.speed)
        seg_out = out_dir / f"E-{group.id}.wav"
        record: Dict[str, Any] = {
            "group": group.id,
            "units": list(group.units),
            "fingerprint": fingerprint,
            "synthesis_sha256": _sha256_text(synth_text),
            "synthesis_characters": len(synth_text),
            "director_controls": {
                "emotion": group.emotion or "auto (absent)",
                "speed": group.speed,
                "pause_after_s": group.pause_after_s,
            },
        }
        cached = lookup_cached_segment(cache_dir, fingerprint)
        if cached is not None:
            shutil.copyfile(cached.normalised_path, seg_out)
            record["provider_call"] = False
            record["cache"] = "hit"
        else:
            spec = SegmentSpec(
                id=group.id,
                role=_group_segment_role(group, creator),
                text=group.text,
                emotion=group.emotion,
                speed=group.speed,
                pause_after_s=group.pause_after_s,
            )
            payload = build_segment_payload(
                spec, voice_id=candidate.voice_id, model=MODEL, lexicon=lexicon,
                sample_rate=32000, fmt="wav", channel=1,
            )
            result_audio, request_record = runner.synth(
                payload=payload, label=f"E:{group.id}",
                attempt_id=f"{receipt['attempt_id']}-E-{group.id}",
                usage_running_total=usage, budget_chars=budget,
            )
            raw = out_dir / f"E-{group.id}-raw.wav"
            raw.write_bytes(result_audio.audio_bytes)
            normalisation = normalise_speech(raw, seg_out)
            if not normalisation.get("ok"):
                raise RuntimeError(f"E:{group.id} normalisation failed: {normalisation}")
            store_cached_segment(
                cache_dir, fingerprint,
                raw_bytes=result_audio.audio_bytes, normalised_path=seg_out,
                meta={
                    "candidate": "E",
                    "group": group.id,
                    "voice_id": candidate.voice_id,
                    "voice_id_hash": hashlib.sha256(candidate.voice_id.encode()).hexdigest(),
                    "synthesis_sha256": _sha256_text(synth_text),
                    "model": MODEL, "emotion": group.emotion, "speed": group.speed,
                    "lexicon_version": lexicon.version,
                    "provider": request_record["provider"],
                    "created_at": _now(),
                },
            )
            record["provider_call"] = True
            record["cache"] = "miss"
            record["request"] = request_record
        record["audio"] = _audio_record(seg_out)
        normalised_paths.append(seg_out)
        gaps.append(group.pause_after_s)
        records.append(record)

    joined = concatenate_segments(
        normalised_paths, gaps_after_s=gaps,
        out_path=out_dir / "E-joined.wav", work_dir=out_dir / "work",
        sample_rate=32000, channels=1,
    )
    return {
        "id": candidate.id,
        "label": candidate.label,
        "voice_id": candidate.voice_id,
        "voice_id_hash": hashlib.sha256(candidate.voice_id.encode()).hexdigest(),
        "segmented": True,
        "groups": records,
        "join_note": (
            "groups share one delivery each; joins use the declared pause_after_s "
            "gaps. Fewer groups than units is enforced by the director plan."
        ),
        "audio": _audio_record(joined),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="send the real provider requests; without it nothing "
                             "transmits and no money is read")
    parser.add_argument("--budget-chars", type=int, default=1200,
                        help="hard cap on cumulative billable synthesis characters")
    parser.add_argument("--budget-asr-calls", type=int, default=5,
                        help="hard cap on ASR backcheck calls")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--skip-asr", action="store_true")
    parser.add_argument("--summary-only", action="store_true",
                        help="render the existing JSON receipt to markdown; no "
                             "provider call, no ASR call")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.summary_only:
        return _summary_only(args)

    load_local_env_file(ROOT / ".env")
    credential = resolve_subscription_credential()
    lexicon = default_zh_lexicon()
    result = load_verified_plan()
    candidates = _build_candidates(result, lexicon)
    plan = result["plan"]

    out_dir = (ROOT / args.out_dir).resolve()
    cache_dir = out_dir / "segments"
    diagnostics_dir = ROOT / ".private" / "diagnostics"

    d_billable = estimated_billable_characters([candidates["D"].text])
    f_billable = estimated_billable_characters([candidates["F"].text])
    e_texts = [synthesis_text(group.text, lexicon) for group in candidates["E"].groups]
    e_billable = estimated_billable_characters(e_texts)
    estimated_chars = d_billable + e_billable + f_billable
    planned_tts = 2 + len(candidates["E"].groups)
    planned_asr = 0 if args.skip_asr else 3

    receipt: Dict[str, Any] = {
        "schema": "contentops.narration-v3-sample/v1",
        "stage": "NARRATION_V3_DE_F_SAMPLE",
        "issue": "#34",
        "attempt_id": f"v3sample-{uuid.uuid4().hex[:12]}",
        "started_at": _now(),
        "executed": bool(args.execute),
        "model": MODEL,
        "host": MINIMAX_CN_HOST,
        "transport": "native_http_cn",
        "route": MPLAN_NARRATION_ROUTE,
        "credential_class": credential.credential_class,
        "credential_source": credential.source,
        "payg_key_used_for_this_request": False,
        "creator_script": result["digests"]["creator_script_working_tree_sha256"],
        "director_plan": result["digests"]["director_plan_working_tree_sha256"],
        "diagnosis": "projects/easel-enhanced-golden/review/narration-v3-diagnosis.md",
        "preset_voice_evidence": dict(PRESET_VOICE_EVIDENCE),
        "listening_key": {
            f"candidate-{index + 1}": cid for index, cid in enumerate(LABEL_ORDER)
        },
        "listening_instructions": (
            "Listen to candidate-1/2/3 first and score them in listening-review-v3.md; "
            "only then compare with listening_key above."
        ),
        "provider_call_budget": {
            "subscription_tts_planned": planned_tts,
            "asr_transcribe_planned": planned_asr,
            "upload": 0,
            "voice_creation": 0,
            "automatic_retry": 0,
            "automatic_top_up": 0,
        },
        "budget": {
            "estimated_billable_characters": estimated_chars,
            "budget_chars": args.budget_chars,
            "asr_calls_planned": planned_asr,
            "asr_calls_budget": args.budget_asr_calls,
        },
        "reused_baselines": _reused_baselines(),
        "notes": [],
    }

    print("=== NARRATION V3: D/E/F SAMPLE ===")
    print(f"  attempt_id     : {receipt['attempt_id']}")
    print(f"  sample units   : {plan.sample_unit_ids} / groups "
          f"{[group.id for group in plan.sample_groups]}")
    print(f"  estimated chars: {estimated_chars} billable "
          f"(D {d_billable} + E {e_billable} + F {f_billable}; budget {args.budget_chars})")
    print(f"  credential     : {credential.credential_class} ({credential.source})")
    print(f"  candidate files: candidate-1/2/3.wav (mapping in the receipt, listen first)")

    if estimated_chars > args.budget_chars:
        print(
            f"REFUSED: estimated {estimated_chars} billable characters exceed the "
            f"budget of {args.budget_chars}. Nothing was sent.",
            file=sys.stderr,
        )
        receipt["outcome"] = "REFUSED_BUDGET"
        _write_receipt(receipt)
        _write_summary_md(receipt)
        return 1
    if planned_asr > args.budget_asr_calls:
        print(
            f"REFUSED: {planned_asr} ASR calls exceed the budget of "
            f"{args.budget_asr_calls}.",
            file=sys.stderr,
        )
        receipt["outcome"] = "REFUSED_ASR_BUDGET"
        _write_receipt(receipt)
        _write_summary_md(receipt)
        return 1

    if not args.execute:
        print("=== DRY RUN. NOTHING WAS SENT. ===")
        receipt["outcome"] = "DRY_RUN"
        receipt["plan"] = {
            "candidates": {
                cid: {
                    "label": candidate.label,
                    "voice_id": candidate.voice_id,
                    "director_controls": (
                        [
                            {"group": group.id, "emotion": group.emotion, "speed": group.speed}
                            for group in candidate.groups
                        ]
                        if candidate.groups
                        else {"emotion": "auto (absent)", "speed": 1.0}
                    ),
                }
                for cid, candidate in candidates.items()
            },
            "candidate_files": {
                f"candidate-{index + 1}": cid for index, cid in enumerate(LABEL_ORDER)
            },
        }
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "narration-v3-plan.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n",
        )
        return 0

    if credential.credential_class != CREDENTIAL_SUBSCRIPTION or not credential.usable:
        print(
            f"REFUSED: narration requires a Subscription-class credential; the "
            f"resolved class is {credential.credential_class} "
            f"(source {credential.source}). Nothing was sent.",
            file=sys.stderr,
        )
        receipt["outcome"] = "REFUSED_CREDENTIAL_CLASS"
        _write_receipt(receipt)
        _write_summary_md(receipt)
        return 1

    runner = ExperimentRunner(
        credential=credential,
        out_dir=out_dir,
        diagnostics_dir=diagnostics_dir,
        asr_budget=args.budget_asr_calls,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    usage = [0]
    candidate_records: Dict[str, Any] = {}
    try:
        receipt["preflight"] = runner.preflight()

        candidate_records["D"] = _run_candidate_single(
            runner=runner, candidate=candidates["D"],
            out_raw=out_dir / "D-raw.wav", out_norm=out_dir / "D-auto-clone.wav",
            cache_dir=cache_dir, lexicon=lexicon, receipt=receipt, usage=usage,
            budget=args.budget_chars,
        )
        candidate_records["E"] = _run_candidate_groups(
            runner=runner, candidate=candidates["E"], creator=result["creator"],
            out_dir=out_dir, cache_dir=cache_dir, lexicon=lexicon, receipt=receipt,
            usage=usage, budget=args.budget_chars,
        )
        candidate_records["F"] = _run_candidate_single(
            runner=runner, candidate=candidates["F"],
            out_raw=out_dir / "F-raw.wav", out_norm=out_dir / "F-auto-preset.wav",
            cache_dir=cache_dir, lexicon=lexicon, receipt=receipt, usage=usage,
            budget=args.budget_chars,
        )

        for cid, record in candidate_records.items():
            if not args.skip_asr:
                expected = _candidate_expected_for_asr(candidates[cid], lexicon)
                record["asr"] = runner.asr(
                    audio_path=Path(record["audio"]["path"]),
                    expected=expected,
                    label=cid,
                )

        # Hidden-label packaging: candidate-N points at the candidate's audio.
        for index, cid in enumerate(LABEL_ORDER):
            source = Path(candidate_records[cid]["audio"]["path"])
            shutil.copyfile(source, out_dir / f"candidate-{index + 1}.wav")

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
        receipt["candidates"] = candidate_records
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage[0]
        receipt["budget"]["asr_calls_used"] = runner.asr_state["used"]
        receipt["listening_comparison"] = {
            "status": "PENDING_FOUNDER_LISTENING",
            "human_metrics": [
                "sounds like a real person talking",
                "emotion fits the content",
                "pace changes are comfortable",
                "emphasis lands on the right words",
                "still sounds like the Founder",
                "no unnatural pauses or join artifacts",
            ],
            "machine_metrics_note": (
                "Durations, loudness, silence maps, ASR coverage and trace ids are "
                "recorded; none of them can approve naturalness, and this receipt "
                "does not claim it. ASR/CI passing is not a quality verdict."
            ),
        }
        receipt["human_review"] = "PENDING_FOUNDER_REVIEW"
        receipt["production_ready"] = False
        receipt["outcome"] = "NARRATION_V3_CANDIDATES_READY_FOR_FOUNDER_LISTENING"
        if not classification["verified"]:
            receipt["notes"].append(
                f"plan-only verification: {classification['status']} "
                f"(basis {classification['basis']})"
            )
        _write_receipt(receipt)
        _write_summary_md(receipt)
        _write_review_template()
        print("=== STOP: Founder listening is pending; score before reading the key. ===")
        return 0
    except ExperimentRefusal as refusal:
        receipt["outcome"] = "REFUSED"
        receipt["refusal"] = {"code": refusal.code, "reasons": refusal.reasons}
        receipt["candidates"] = candidate_records
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage[0]
        _write_receipt(receipt)
        _write_summary_md(receipt)
        _write_review_template()
        print(f"REFUSED [{refusal.code}]: " + "; ".join(refusal.reasons), file=sys.stderr)
        return 1
    except NativeTtsRefusal as refusal:
        receipt["outcome"] = "PROVIDER_FAILED"
        receipt["provider_status"] = refusal.structured()
        receipt["candidates"] = candidate_records
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage[0]
        _write_receipt(receipt)
        _write_summary_md(receipt)
        _write_review_template()
        print(
            f"PROVIDER REFUSED: HTTP {refusal.http_status} / status "
            f"{refusal.provider_status_code}: {refusal.provider_status_msg}",
            file=sys.stderr,
        )
        return 3
    except Exception as exc:  # noqa: BLE001 - recorded, never silently swallowed
        receipt["outcome"] = "PROVIDER_FAILED"
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
        receipt["candidates"] = candidate_records
        receipt["requests"] = runner.requests
        receipt["asr_backchecks"] = runner.asr_records
        receipt["budget"]["usage_characters_used"] = usage[0]
        _write_receipt(receipt)
        _write_summary_md(receipt)
        _write_review_template()
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
