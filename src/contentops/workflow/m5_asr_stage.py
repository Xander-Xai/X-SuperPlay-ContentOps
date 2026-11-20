"""M5 narration ASR backcheck stage (Issue #140 slice).

The detector result is recorded without becoming an approval. Account-bound
runs still fail closed when the detector cannot produce evidence.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from contentops.media.asr_backcheck import backcheck_speech


def stage_asr_backcheck(
    project: Path,
    config: Dict[str, Any],
    script: Dict[str, Any],
    narration: Dict[str, Any],
    *,
    transcriber: Optional[Any] = None,
    blocked_error: type[Exception],
    declared_account: Callable[[Dict[str, Any]], str],
    sha256: Callable[[Path], str],
    text_sha: Callable[[str], str],
    write_json: Callable[[Path, Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Transcribe narration for detection only; preserve the M5 gate contract."""
    runner = transcriber
    if runner is None:
        from contentops.media.asr_siliconflow import transcribe
        runner = lambda path: transcribe(path)  # noqa: E731 - one-line binding

    audio = Path(narration.get("audio") or "assets/voice/narration.wav")
    if not audio.is_absolute():
        audio = project / audio
    if not audio.is_file():
        raise blocked_error(f"ASR backcheck needs the narration track: {audio}")

    expected = "\n".join(str(line.get("narration") or "")
                         for line in (script.get("lines") or []))
    if not expected.strip():
        raise blocked_error("ASR backcheck has no spoken script to compare against")

    result = backcheck_speech(
        audio, expected,
        transcriber=runner,
        provider="siliconflow",
    )

    account = declared_account(config)
    blocked = bool(account) and result.status == "SKIPPED"

    receipt = {
        "schema": "contentops.asr-backcheck/v1",
        "provider": result.provider,
        "model": result.model,
        "capabilities": result.capabilities or {"text": False},
        "role": "DETECTOR_ONLY",
        "can_approve_quality": False,
        "audio": f"project://{audio.relative_to(project).as_posix()}",
        "audio_sha256": sha256(audio),
        "audio_bytes": audio.stat().st_size,
        "expected_sha256": text_sha(expected),
        "status": result.status,
        "coverage": result.coverage,
        "issues": result.issues,
        "missing": result.missing,
        "excess": result.duplicated,
        "detail": result.detail,
        "account_bound": bool(account),
        "blocks_human_review": blocked,
        "production_ready": False,
        "publish_authorized": False,
    }
    write_json(project / "receipts" / "asr-backcheck.json", receipt)

    if blocked:
        raise blocked_error(
            "ASR backcheck produced no usable evidence "
            f"({result.detail or 'unknown reason'}); an account-bound project "
            "cannot enter human review without it. Set SILICONFLOW_API_KEY and "
            "re-run, or treat this render as diagnostic only."
        )
    return receipt
