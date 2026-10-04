"""Transport-level helpers shared by every MiniMax media provider.

Why these live here
-------------------
``resolve_cli``, ``verify_output`` and the sidecar conventions are properties of
the **transport**, not of speech. M2 proved them for speech; M3 needs the exact
same behaviour for image, and a second copy would be free to drift. One canonical
owner means a fix to the "CLI exited 0 but wrote nothing" defence protects every
modality at once.

``minimax_speech`` re-exports these names, so existing callers and tests keep
working while there is still only one implementation.

The sidecar convention
----------------------
A generated asset gets ``<asset>.receipt.json`` next to it. That file is the
**generation receipt** and it is immutable: the record of what was paid for, with
what, when. Reuse never rewrites it, because overwriting would destroy
``quota_before``, ``quota_after`` and the original attempt number — the exact
evidence that the asset came out of plan entitlement rather than pay-as-you-go.

Reuse activity is recorded separately, in an append-only event log, so provenance
and usage history cannot be confused for each other.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Media probing goes through the one sanctioned process layer, so nothing here can
# flash a console window on Windows.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from process_utils import hidden_run  # noqa: E402

__all__ = [
    "CLI_ENV_VAR",
    "HAVE_FFPROBE",
    "REQUIRED_SIDECAR_FIELDS",
    "SIDECAR_SUFFIX",
    "ffprobe_json",
    "load_sidecar",
    "resolve_cli",
    "sidecar_for",
    "sidecar_is_complete",
    "verify_output",
    "write_sidecar",
]

#: Environment override for the transport executable, used to point at a
#: stand-in during tests. Unset in production, where the official CLI on PATH is
#: used. A value starting with ``[`` is parsed as a JSON argv prefix, which is
#: what a stand-in launcher needs (an interpreter plus a script).
CLI_ENV_VAR = "CONTENTOPS_MINIMAX_CLI"


def resolve_cli() -> Any:
    """Absolute path to the official CLI launcher.

    On Windows the npm install produces ``mmx.cmd`` shims that CreateProcess
    cannot resolve from a bare ``mmx``, so resolution happens once here.
    """
    override = os.environ.get(CLI_ENV_VAR, "").strip()
    if override:
        if override.startswith("["):
            try:
                parsed = json.loads(override)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list) and parsed and all(
                isinstance(part, str) for part in parsed
            ):
                return parsed
        return override
    return shutil.which("mmx")


def have_ffprobe() -> bool:
    """True when ffprobe is on PATH. Probing media needs it; nothing else does."""
    return bool(shutil.which("ffprobe"))


#: Evaluated once at import so callers can skip probe-dependent paths cheaply.
HAVE_FFPROBE = have_ffprobe()


def ffprobe_json(path: Path) -> Dict[str, Any]:
    """Return ffprobe's JSON description of a media file.

    The single place ContentOps asks what a media file actually contains. Callers
    that need codec, dimensions, duration, frame rate or stream presence go
    through here rather than each parsing ffprobe output themselves.

    Raises:
        RuntimeError: ffprobe is unavailable, or the file cannot be read. Callers
            decide whether that blocks or degrades.
    """
    if not HAVE_FFPROBE:
        raise RuntimeError(
            "ffprobe is not on PATH, so media cannot be measured; install "
            "ffmpeg or skip the probe"
        )
    result = hidden_run(
        [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe could not read {path}: "
            f"{(result.stderr or '').strip()[-200:] or 'no detail'}"
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ffprobe returned unparsable JSON for {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"ffprobe returned an unexpected shape for {path}")
    return payload


def verify_output(path: Path, *, not_before: float, min_bytes: int = 1024) -> None:
    """Fail loudly when the CLI did not actually write what was asked for.

    Exit code 0 is not semantic success. Measured on the official CLI v1.0.27:
    a ``speech synthesize`` request whose text contained a newline still exited 0,
    silently ignored ``--out``, and wrote a differently-formatted file into the
    current working directory. Every modality therefore verifies the output file
    after the call rather than trusting the exit status.
    """
    path = Path(path)
    if not path.is_file():
        raise RuntimeError(
            f"the CLI reported success but {path} does not exist; it most "
            f"likely ignored --out. See the CLI output for the path it used."
        )
    if path.stat().st_mtime < not_before - 1:
        raise RuntimeError(
            f"{path} is stale (older than this request); refusing to treat a "
            f"previous run's output as this run's result"
        )
    if path.stat().st_size < min_bytes:
        raise RuntimeError(
            f"{path} is only {path.stat().st_size} bytes; treating it as a "
            f"failed generation rather than usable output"
        )


SIDECAR_SUFFIX = ".receipt.json"

#: Fields a cached generation receipt must carry before it may be reused.
#:
#: Every one of these was previously allowed to be blank on a cache hit, which
#: produced a receipt with an empty voice, empty text hashes and
#: ``lexicon_version="unknown"``. Fabricated provenance is worse than no cache: a
#: missing field is a cache miss, never something to fill in.
REQUIRED_SIDECAR_FIELDS = (
    "provider",
    "product",
    "plan",
    "model",
    "voice",
    "display_text_sha256",
    "spoken_text_sha256",
    "lexicon_version",
    "fingerprint",
    "raw_sha256",
    "normalized_sha256",
    "technical_qc",
    "semantic_qc",
    "billing_guard_verdict",
    "attempt",
    "human_review",
)

#: Fields whose value must not be an empty string.
NON_BLANK_SIDECAR_FIELDS = (
    "provider", "product", "plan", "model", "voice",
    "display_text_sha256", "spoken_text_sha256", "lexicon_version",
    "fingerprint", "raw_sha256", "normalized_sha256",
    "billing_guard_verdict", "human_review",
)


def sidecar_for(asset_path: Path) -> Path:
    """Path of the sanitised receipt that sits next to a generated asset."""
    return Path(asset_path).with_name(Path(asset_path).name + SIDECAR_SUFFIX)


def write_sidecar(path: Path, payload: Dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def sidecar_is_complete(payload: Optional[Dict[str, Any]]) -> bool:
    """True when a cached receipt carries every required provenance field.

    Rejects a missing key, a blank string where blank is meaningless, and a field
    of the wrong type for ``attempt``. Anything short of complete is a cache miss.
    """
    if not isinstance(payload, dict):
        return False
    for name in REQUIRED_SIDECAR_FIELDS:
        if name not in payload:
            return False
    for name in NON_BLANK_SIDECAR_FIELDS:
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip():
            return False
    for name in ("technical_qc", "semantic_qc"):
        if not isinstance(payload.get(name), dict):
            return False
    attempt = payload.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        return False
    return True


def load_sidecar(path: Path) -> Optional[Dict[str, Any]]:
    """Load a sidecar, returning ``None`` when it is absent or unusable.

    A corrupt or unreadable sidecar is treated as no cache at all rather than as
    a licence to invent provenance.
    """
    path = Path(path)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None