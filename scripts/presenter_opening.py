"""The presenter opening is a pipeline step, not a one-off edit.

A project that wants a digital-human opening declares
``motion/presenter/contract.json``. The contract says *when* the opening is
mandatory (variant, clip, line, share ceiling); ``receipts/voice-lines.json``
stays the single source for *what* he says and which files carry it.

Two failure modes are refused here:

- the opening is declared but the timeline no longer carries it, so a later
  build would quietly ship a film without the presenter;
- the recorded hashes no longer match the files on disk, so the receipt would
  describe a shot that is not the shot in the film.

Run:
    python scripts/presenter_opening.py projects/easel-fi-what-is-agent --check
    python scripts/presenter_opening.py projects/easel-fi-what-is-agent --verify-speech --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

__all__ = [
    "CONTRACT_REL",
    "apply_verdict",
    "load_contract",
    "problems",
    "speech_verdict",
]

#: Where a project declares its presenter opening, if it wants one.
CONTRACT_REL = Path("motion") / "presenter" / "contract.json"

#: The line number the opening speaks; it precedes line 1, so it is line 0.
PRESENTER_LINE = 0


def load_contract(project: Path) -> Optional[Dict[str, Any]]:
    """The project's presenter declaration, or None when it opts out."""
    path = project / CONTRACT_REL
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(project: Path, logical: str) -> Path:
    """Turn a recorded ``project://`` path into a real one."""
    return project / str(logical).replace("project://", "").lstrip("/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def problems(contract: Optional[Dict[str, Any]], project: Path,
             segments: List[Dict[str, Any]], variant: str,
             voice: Dict[str, Any]) -> List[str]:
    """Everything that would let the declared opening go missing.

    An absent contract is not a problem: the opening is opt-in per project. A
    contract written for another variant is also not a problem here — that
    variant's build is the one that has to honour it.
    """
    if not contract:
        return []
    if contract.get("variant", "eras") != variant:
        return []

    issues: List[str] = []
    clip = contract.get("clip", "p00")
    presenters = [segment for segment in segments if segment.get("type") == "presenter"]
    if len(presenters) != 1:
        issues.append(
            f"the contract declares a presenter opening but the {variant} timeline "
            f"carries {len(presenters)} presenter segment(s)")
    elif presenters[0].get("clip") != clip:
        issues.append(
            f"the presenter segment renders {presenters[0].get('clip')!r}, "
            f"the contract says {clip!r}")

    block = voice.get("presenter")
    if not isinstance(block, dict) or not block.get("text"):
        issues.append("receipts/voice-lines.json has no presenter block, so the "
                      "opening has no words and no audio to place")
        return issues

    if contract.get("text") and block["text"] != contract["text"]:
        issues.append("the spoken text in voice-lines.json differs from the contract")

    for field, recorded, label in (("wav_sha256", block.get("wav_sha256"), "opening audio"),
                                   ("shot_sha256", block.get("shot_sha256"), "generated shot")):
        source = block.get("path") if field == "wav_sha256" else block.get("shot")
        if not source:
            issues.append(f"voice-lines.json records no {label} path")
            continue
        path = _resolve(project, source)
        if not path.is_file():
            issues.append(f"missing {label}: {path}")
        elif not recorded:
            issues.append(f"{label} has no recorded sha256")
        elif _sha256(path) != recorded:
            issues.append(f"{label} on disk no longer matches its recorded sha256")

    if contract.get("require_speech_verified") and not block.get("speech_text_verified"):
        issues.append("the contract requires the spoken line to be verified; "
                      "voice-lines.json still says speech_text_verified: false")

    ceiling = contract.get("max_share")
    if ceiling:
        film_s = sum(float(segment.get("duration") or 0) for segment in segments)
        presenter_s = sum(float(segment.get("duration") or 0)
                          for segment in presenters)
        if film_s and presenter_s / film_s > float(ceiling):
            issues.append(
                f"the opening is {presenter_s / film_s:.2%} of the film, "
                f"above the {float(ceiling):.0%} the contract allows")
    return issues


def speech_verdict(wav: Path, text: str, *, cli: Optional[str] = None) -> Dict[str, Any]:
    """Ask MiniMax ASR what the file actually says, and compare.

    A detector only: this can say the words are wrong, never that the delivery
    is good. ``SKIPPED`` means the tool was unavailable, which is never PASS.
    """
    from contentops.media.asr_backcheck import backcheck_speech

    return backcheck_speech(wav, text, cli=cli).as_dict()


def apply_verdict(voice: Dict[str, Any], verdict: Dict[str, Any],
                  *, verified_on: str) -> bool:
    """Fold an ASR verdict into the presenter block. Returns whether it changed.

    Only ``NO_PROBLEM_DETECTED`` flips the flag. A skipped or failed check is
    recorded as evidence and leaves the line unverified, because "we could not
    check" and "the words are right" are different facts.
    """
    block = voice.get("presenter")
    if not isinstance(block, dict):
        return False
    passed = verdict.get("status") == "NO_PROBLEM_DETECTED"
    check = {
        "model": "asr-1.0",
        "provider": "minimax_m_plan",
        "status": verdict.get("status"),
        "role": verdict.get("role", "DETECTOR_ONLY"),
        "coverage": verdict.get("coverage"),
        "transcript": verdict.get("transcript"),
        "checked_on": verified_on,
        "detail": verdict.get("detail"),
    }
    before = (block.get("speech_text_verified"), block.get("speech_check"))
    block["speech_text_verified"] = passed
    block["speech_check"] = check
    return (block.get("speech_text_verified"), block.get("speech_check")) != before


def _dumps(payload: Any, indent: int = 0) -> str:
    """Serialise in the style these receipts are already written in.

    ``json.dumps(indent=2)`` would explode the twelve compact one-line narration
    records into five lines each, so a verdict write would show up as a whole-file
    reformat instead of the two fields it actually changed.
    """
    pad = "  " * indent
    if isinstance(payload, dict):
        if not payload:
            return "{}"
        if all(not isinstance(value, (dict, list)) for value in payload.values()):
            return json.dumps(payload, ensure_ascii=False)
        rows = [f'{pad}  {json.dumps(key, ensure_ascii=False)}: {_dumps(value, indent + 1)}'
                for key, value in payload.items()]
        return "{\n" + ",\n".join(rows) + "\n" + pad + "}"
    if isinstance(payload, list):
        if not payload:
            return "[]"
        rows = [f"{pad}  {_dumps(item, indent + 1)}" for item in payload]
        return "[\n" + ",\n".join(rows) + "\n" + pad + "]"
    return json.dumps(payload, ensure_ascii=False)


def _write(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(_dumps(payload) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--check", action="store_true",
                        help="verify the declared opening against the timeline and files")
    parser.add_argument("--verify-speech", action="store_true",
                        help="transcribe the opening with MiniMax ASR and compare it")
    parser.add_argument("--write", action="store_true",
                        help="persist the verdict into receipts/voice-lines.json")
    parser.add_argument("--variant", default="eras")
    parser.add_argument("--verified-on", default=None,
                        help="ISO date recorded with the verdict; defaults to today")
    args = parser.parse_args(argv)

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()

    contract = load_contract(project)
    voice_path = project / "receipts" / "voice-lines.json"
    voice = json.loads(voice_path.read_text(encoding="utf-8"))

    if args.verify_speech:
        block = voice.get("presenter") or {}
        if not block.get("path") or not block.get("text"):
            print(json.dumps({"status": "BLOCKED",
                              "reason": "voice-lines.json has no presenter block"},
                             ensure_ascii=False))
            return 4
        verdict = speech_verdict(_resolve(project, block["path"]), block["text"])
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
        from datetime import date
        changed = apply_verdict(voice, verdict,
                                verified_on=args.verified_on or date.today().isoformat())
        if args.write and changed:
            _write(voice_path, voice)
        return 0 if verdict.get("status") == "NO_PROBLEM_DETECTED" else 1

    if contract is None:
        print(json.dumps({"status": "NO_CONTRACT",
                          "note": "this project does not declare a presenter opening"},
                         ensure_ascii=False))
        return 0

    timeline = json.loads((project / "motion" / "timeline.json").read_text(encoding="utf-8"))
    segments = [segment for segment in timeline["segments"]
                if not segment.get("variant") or segment["variant"] == args.variant]
    issues = problems(contract, project, segments, args.variant, voice)
    print(json.dumps({"status": "BLOCKED" if issues else "READY",
                      "variant": args.variant,
                      "problems": issues}, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
