#!/usr/bin/env python3
"""Local stand-in for the official MiniMax CLI, used by tests only.

It exists so the whole speech pipeline — billing gate, cache, normalisation, QC,
fingerprint, receipt — can be exercised end to end **without a provider request
and without spending quota**. It writes a locally synthesised tone instead of
real narration, so no test can accidentally assert something about voice quality.

Supported argv shapes:
    --version
    config show --output json
    speech synthesize ... --out <path> [--text <t>] ...
    speech transcribe --file <path> --output json

An empty transcript is returned on purpose: the semantic gate must degrade to
SKIPPED rather than invent a pass.

Setting ``FAKE_MMX_FAIL=1`` makes ``speech synthesize`` exit non-zero without
writing anything. That is how tests produce a genuine FAILED attempt record, which
is the evidence a retry has to reference.
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

# The repository's own subprocess policy applies to test fixtures too: every
# child process goes through process_utils, so no fixture can pop a console
# window on Windows. The policy gate scans tracked files and caught the direct
# subprocess.run this fixture originally used.
from process_utils import hidden_run  # noqa: E402


def _flag(argv, name, default=None):
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return default


def main() -> int:
    argv = sys.argv[1:]

    if "--version" in argv:
        print("mmx 0.0.0-fixture")
        return 0

    if argv[:2] == ["config", "show"]:
        print(json.dumps({
            "region": "fixture",
            "base_url": "https://fixture.invalid",
            "output": "json",
        }))
        return 0

    if argv[:2] == ["speech", "transcribe"]:
        # No transcript: the semantic gate must report SKIPPED, never PASS.
        print(json.dumps({"text": "", "duration": 0}))
        return 0

    if argv[:2] == ["speech", "synthesize"]:
        out = _flag(argv, "--out")
        if not out:
            print("fixture: --out is required", file=sys.stderr)
            return 2
        if os.environ.get("FAKE_MMX_FAIL") == "1":
            # Deliberate provider failure: non-zero exit, nothing written.
            sys.stderr.write("fixture: simulated provider failure\n")
            return 7
        text = _flag(argv, "--text", "") or ""
        # ~6 characters per second keeps the duration plausible for the QC's
        # duration-plausibility window without pretending to be speech.
        seconds = max(1.0, min(20.0, len(text) / 6.0))
        result = hidden_run(
            ["ffmpeg", "-y", "-hide_banner", "-nostdin",
             "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds:.2f}",
             "-ar", "32000", "-ac", "1", "-c:a", "pcm_s16le", out],
            timeout=120,
        )
        if result.returncode != 0:
            sys.stderr.write(result.stderr or "")
            return result.returncode
        print(out)
        return 0

    sys.stderr.write(f"fixture: unsupported argv {argv!r}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())