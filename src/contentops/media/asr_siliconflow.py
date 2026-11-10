"""SiliconFlow speech-to-text: transport and response validation only.

Scope
-----
This module moves bytes and checks the shape of the answer. It does **not**
compare the transcript against the script and it never issues a quality verdict.
That comparison already lives in :mod:`contentops.media.asr_backcheck`, which
remains the single place where coverage is computed and where the
``SKIPPED`` / ``DETECTED_PROBLEM`` / ``NO_PROBLEM_DETECTED`` vocabulary is
defined. Splitting transport from judgement is what keeps a provider swap from
silently changing the verdict.

Why there is no "fallback to a local model"
-------------------------------------------
A missing credential, an unreachable endpoint and a malformed response all raise
:class:`AsrTransportError`. None of them degrade into a passing transcript. The
caller maps the error to ``SKIPPED``, and ``SKIPPED`` is not a pass — it is the
absence of evidence, which an account-bound project must treat as a block.

What the provider actually returns
----------------------------------
Per the vendor's published contract for ``POST /v1/audio/transcriptions`` the
200 body carries ``text`` and nothing else is guaranteed. Timestamps, segments
and language are therefore treated as *optional*: present and well-formed, they
are recorded as capabilities; absent, the request still succeeds and the receipt
says ``timestamps: false`` / ``language: false``. A missing optional field is
never a failure and never a pass.

Credential handling
-------------------
The key is read from ``SILICONFLOW_API_KEY``. It is never written to a receipt,
a log line, a CLI argument or an exception message. :func:`redact` exists so a
caller that must echo an error can do so without leaking it.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "API_KEY_ENV",
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL",
    "ENDPOINT_ENV",
    "MAX_FILE_BYTES",
    "MODEL_ENV",
    "AsrTransportError",
    "Transcription",
    "redact",
    "transcribe",
]

#: Published endpoint. Overridable by environment variable so the one real smoke
#: run can be pointed at a staging host without editing code.
DEFAULT_ENDPOINT = "https://api.siliconflow.cn/v1/audio/transcriptions"
DEFAULT_MODEL = "XingChenAGI/XingChenASR-V3.2"

API_KEY_ENV = "SILICONFLOW_API_KEY"
ENDPOINT_ENV = "SILICONFLOW_ASR_ENDPOINT"
MODEL_ENV = "SILICONFLOW_ASR_MODEL"

#: Vendor-documented upload ceiling. A narration track for a few minutes is far
#: below this; the check exists so an unexpected input fails loudly and early
#: instead of being silently truncated or rejected by the server as a 413.
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_DURATION_S = 3600

#: Error kinds. The caller distinguishes them because the right operator action
#: differs: a missing key is a configuration task, an outage is a retry task, and
#: a protocol error means the provider changed its contract.
MISSING_CREDENTIAL = "MISSING_CREDENTIAL"
CREDENTIAL = "CREDENTIAL"
UNAVAILABLE = "UNAVAILABLE"
REQUEST = "REQUEST"
OVERSIZE = "OVERSIZE"
PROTOCOL = "PROTOCOL"
EMPTY_TRANSCRIPT = "EMPTY_TRANSCRIPT"


class AsrTransportError(RuntimeError):
    """A transcription could not be obtained. Never a passing result."""

    def __init__(
        self,
        kind: str,
        detail: str,
        *,
        status: Optional[int] = None,
        attempts: int = 1,
    ) -> None:
        self.kind = kind
        self.detail = detail
        self.status = status
        self.attempts = attempts
        super().__init__(f"{kind}: {detail}")


@dataclass(frozen=True)
class Transcription:
    """A validated transcript plus what the provider actually gave us."""

    text: str
    model: str
    endpoint: str
    attempts: int
    language: Optional[str] = None
    timestamps: Tuple[Dict[str, Any], ...] = ()
    capabilities: Dict[str, Any] = field(default_factory=dict)
    request_id: Optional[str] = None


def redact(value: str, api_key: Optional[str] = None) -> str:
    """Remove a credential from text that is about to be logged or receipted."""
    text = str(value or "")
    secrets: List[str] = []
    if api_key:
        secrets.append(api_key)
    env_key = os.environ.get(API_KEY_ENV)
    if env_key:
        secrets.append(env_key)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return text


def _resolve_key(api_key: Optional[str]) -> str:
    key = (api_key if api_key is not None else os.environ.get(API_KEY_ENV) or "").strip()
    if not key:
        raise AsrTransportError(
            MISSING_CREDENTIAL,
            f"{API_KEY_ENV} is not set; no transcription was attempted",
        )
    return key


def _multipart(
    *,
    fields: Dict[str, str],
    file_name: str,
    file_bytes: bytes,
    boundary: str,
) -> bytes:
    """Build a multipart/form-data body with the standard library only.

    ``requests`` is deliberately not introduced: adding a dependency to move one
    request would be a change bigger than the feature.
    """
    chunks: List[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("utf-8"))
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        )
        chunks.append(str(value).encode("utf-8"))
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}\r\n".encode("utf-8"))
    chunks.append(
        f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode(
            "utf-8"
        )
    )
    chunks.append(b"Content-Type: application/octet-stream\r\n\r\n")
    chunks.append(file_bytes)
    chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks)


def _default_opener(request: urllib.request.Request, timeout: float) -> Tuple[int, bytes]:
    """Perform the request. Tests inject their own opener instead of patching."""

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        body = b""
        try:
            body = exc.read()
        except Exception:  # noqa: BLE001 - the status code is the useful part
            pass
        return int(exc.code), body


def _classify_status(status: int) -> str:
    if status in (401, 403):
        return CREDENTIAL
    if status == 413:
        return OVERSIZE
    if status == 429 or 500 <= status < 600:
        return UNAVAILABLE
    return REQUEST


def _validate_body(payload: Any) -> Tuple[str, Optional[str], Tuple[Dict[str, Any], ...]]:
    """Check the response shape without inventing fields the vendor omits."""
    if not isinstance(payload, dict):
        raise AsrTransportError(PROTOCOL, "response is not a JSON object")

    text = payload.get("text")
    if not isinstance(text, str):
        raise AsrTransportError(
            PROTOCOL, "response has no string 'text' field"
        )
    if not text.strip():
        raise AsrTransportError(EMPTY_TRANSCRIPT, "provider returned an empty transcript")

    language = payload.get("language")
    if language is not None and not isinstance(language, str):
        raise AsrTransportError(PROTOCOL, "'language' is present but is not a string")

    words: Tuple[Dict[str, Any], ...] = ()
    for key in ("words", "segments"):
        candidate = payload.get(key)
        if candidate is None:
            continue
        if not isinstance(candidate, list):
            raise AsrTransportError(PROTOCOL, f"'{key}' is present but is not a list")
        words = tuple(item for item in candidate if isinstance(item, dict))
        break

    return text, language, words


def transcribe(
    audio_path: Path,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    endpoint: Optional[str] = None,
    timeout: float = 180.0,
    max_attempts: int = 3,
    opener: Optional[Callable[[urllib.request.Request, float], Tuple[int, bytes]]] = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Transcription:
    """Transcribe one audio file. Raises :class:`AsrTransportError` on any doubt.

    Args:
        audio_path: the narration track to transcribe.
        model: model id; defaults to ``SILICONFLOW_ASR_MODEL`` then
            :data:`DEFAULT_MODEL`.
        api_key: only for tests. Production reads ``SILICONFLOW_API_KEY``.
        endpoint: overrides the published endpoint.
        timeout: per-attempt socket timeout in seconds.
        max_attempts: retries for outages only. A credential error is never retried.
        opener: test seam returning ``(status, body)``.
        sleep: test seam so retry tests do not wait.
    """
    audio = Path(audio_path)
    if not audio.is_file():
        raise AsrTransportError(REQUEST, "audio file does not exist")
    size = audio.stat().st_size
    if size <= 0:
        raise AsrTransportError(REQUEST, "audio file is empty")
    if size > MAX_FILE_BYTES:
        raise AsrTransportError(
            OVERSIZE,
            f"audio is {size} bytes, above the {MAX_FILE_BYTES}-byte upload ceiling",
        )

    resolved_model = (
        model or os.environ.get(MODEL_ENV) or DEFAULT_MODEL
    ).strip()
    if not resolved_model:
        raise AsrTransportError(REQUEST, "no ASR model id was supplied")
    resolved_endpoint = (
        endpoint or os.environ.get(ENDPOINT_ENV) or DEFAULT_ENDPOINT
    ).strip()

    key = _resolve_key(api_key)
    perform = opener or _default_opener

    fields = {"model": resolved_model}
    boundary = f"----contentops{uuid.uuid4().hex}"
    body = _multipart(
        fields=fields,
        file_name=audio.name,
        file_bytes=audio.read_bytes(),
        boundary=boundary,
    )

    last: Optional[AsrTransportError] = None
    for attempt in range(1, max(1, max_attempts) + 1):
        request = urllib.request.Request(
            resolved_endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Accept": "application/json",
            },
        )
        try:
            status, raw = perform(request, timeout)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = AsrTransportError(
                UNAVAILABLE, redact(f"transport failure: {exc}", key), attempts=attempt
            )
            if attempt < max_attempts:
                sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
                continue
            raise last from None

        if status == 200:
            try:
                payload = json.loads(raw.decode("utf-8", errors="replace") or "{}")
            except ValueError as exc:
                raise AsrTransportError(
                    PROTOCOL, f"response is not valid JSON: {exc}", status=status,
                    attempts=attempt,
                ) from None
            text, language, words = _validate_body(payload)
            return Transcription(
                text=text,
                model=resolved_model,
                endpoint=resolved_endpoint,
                attempts=attempt,
                language=language,
                timestamps=words,
                capabilities={
                    "text": True,
                    "timestamps": bool(words),
                    "language": language is not None,
                    "role": "DETECTOR_ONLY",
                    "can_approve_quality": False,
                },
                request_id=payload.get("trace_id") if isinstance(payload, dict) else None,
            )

        kind = _classify_status(status)
        snippet = redact(raw.decode("utf-8", errors="replace")[:200], key)
        last = AsrTransportError(
            kind, f"HTTP {status}: {snippet}", status=status, attempts=attempt
        )
        if kind == UNAVAILABLE and attempt < max_attempts:
            sleep(min(8.0, 0.5 * (2 ** (attempt - 1))))
            continue
        raise last

    raise last or AsrTransportError(UNAVAILABLE, "no attempt was made")
