"""Native, host-pinned HTTP adapter for the one authorised CN T2A call. Issue #34.

Why this module exists
----------------------
The first-activation synthesis was sent three times through the official
``mmx`` CLI and refused three times with ``insufficient balance``. Auditing the
pinned CLI (``mmx-cli`` 1.0.27, the version installed on this host) against its
own bundled source produced two structural findings that the CLI cannot fix from
the outside:

1. **Credential binding through the environment is a no-op.** ``child_env_for``
   injects the authorised key as ``MINIMAX_API_KEY`` into the child environment,
   and every receipt therefore *claims* the credential class that was injected.
   But the CLI's request-auth resolver is, in order: ``--api-key`` flag, then an
   OAuth token from ``~/.mmx/config.json``, then the ``api_key`` stored in that
   same config file. It never consults ``process.env.MINIMAX_API_KEY`` for
   request authentication; the variable is read only by the interactive
   onboarding prompt that offers to save it into the config file. All three
   "pay-as-you-go" attempts therefore authenticated with the Subscription Key
   stored in ``~/.mmx/config.json`` -- the same credential for all three -- and
   the pay-as-you-go route was never actually exercised.

2. **The request host is chosen by the CLI's own config, not by this
   repository.** The CLI resolves its base URL from (among others) the
   ``region`` field in ``~/.mmx/config.json`` -- ``cn`` maps to the documented
   API host -- while the balance reads performed by ``BillingGuard`` used
   ``CONTENTOPS_MINIMAX_BASE_URL``, a different host family. The proof chain
   ("this balance is visible to the service that will bill") was therefore never
   closed.

So the one authorised activation call must not go through the CLI at all. This
adapter speaks the documented public HTTP API directly:

- **Explicit CN base URL.** :data:`MINIMAX_CN_HOST` is the server address in the
  official OpenAPI definition for ``POST /v1/t2a_v2``. The adapter refuses to
  send to any other host, so "which service answered" is a checked fact rather
  than a configuration hope.
- **Explicit credential.** The caller passes the authorised key; it is used
  verbatim in one ``Authorization`` header and is never logged, echoed in an
  exception, or written to a receipt. There is no fallback chain to a stored
  credential.
- **Documented fields only.** The payload builder emits exactly the documented
  request schema and validates every value against the documented domains.
  Unknown or invented fields are impossible by construction.
- **Exactly one request, no retry.** There is no loop and no retry on any
  failure class. A refusal is reported with its full structured detail and the
  caller stops.
- **Full raw parsing.** HTTP status, ``base_resp.status_code``,
  ``base_resp.status_msg``, ``trace_id`` and ``extra_info`` are parsed as
  separate facts. The CLI collapsed all provider failures into
  ``API error: <msg> (HTTP 200)`` wrapped in ``{"error": {"code": 1, ...}}``,
  where ``1`` is the CLI's own general-error class and the provider's status
  code was lost. This adapter must not repeat that: a 1008 and a 2013 have to
  survive as themselves.

This is an ADAPTER (AGENTS.md extension policy): it wraps the provider's
documented HTTP surface in X-SuperPlay-owned space and touches no upstream code.

Scope
-----
Only the one-time activation synthesis of an already-existing cloned voice. No
upload, no clone, no regular narration. Regular narration stays on the M Plan
provider over the CLI; this module exists for the call whose billing chain was
provably broken by the CLI transport.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

__all__ = [
    "DOCUMENTED_CN_HOSTS",
    "MINIMAX_CN_HOST",
    "DOCUMENTED_MODELS",
    "DOCUMENTED_AUDIO_FORMATS",
    "DOCUMENTED_SAMPLE_RATES",
    "NativeTtsRefusal",
    "NativeTtsResult",
    "REFUSAL_HOST_NOT_DOCUMENTED_CN",
    "REFUSAL_HTTP_ERROR",
    "REFUSAL_INVALID_PAYLOAD",
    "REFUSAL_NETWORK",
    "REFUSAL_NON_JSON",
    "REFUSAL_PROVIDER_STATUS",
    "REFUSAL_SCHEMA_CHANGED",
    "T2A_PATH",
    "build_t2a_payload",
    "decode_hex_audio",
    "host_is_documented_cn",
    "normalize_host",
    "send_t2a_once",
]

#: The documented server for the T2A API, taken from the official OpenAPI
#: definition of ``POST /v1/t2a_v2`` and the voice-cloning endpoints. This is
#: the CN platform host; the CLI's own region table maps ``cn`` here as well.
#:
#: The literal lives in exactly one place, in this module, so that "the request
#: went to the documented CN service" is checkable by reading one constant
#: rather than by auditing an environment.
MINIMAX_CN_HOST = "https://api.minimax.cn"

#: Hosts that are treated as the documented CN surface. Kept as a tuple so an
#: alias can be added only deliberately, with a comment explaining what was
#: measured to make it an alias. Today there is exactly one.
DOCUMENTED_CN_HOSTS: Tuple[str, ...] = (MINIMAX_CN_HOST,)

T2A_PATH = "/v1/t2a_v2"

DOCUMENTED_MODELS: Tuple[str, ...] = (
    "speech-2.8-hd",
    "speech-2.8-turbo",
    "speech-2.6-hd",
    "speech-2.6-turbo",
    "speech-02-hd",
    "speech-02-turbo",
    "speech-01-hd",
    "speech-01-turbo",
)

DOCUMENTED_AUDIO_FORMATS: Tuple[str, ...] = (
    "mp3",
    "pcm",
    "flac",
    "wav",
    "pcmu_raw",
    "pcmu_wav",
    "opus",
)

DOCUMENTED_SAMPLE_RATES: Tuple[int, ...] = (8000, 16000, 22050, 24000, 32000, 44100)

REFUSAL_HOST_NOT_DOCUMENTED_CN = "HOST_NOT_DOCUMENTED_CN"
REFUSAL_INVALID_PAYLOAD = "INVALID_PAYLOAD"
REFUSAL_NETWORK = "NETWORK_ERROR"
REFUSAL_HTTP_ERROR = "HTTP_ERROR"
REFUSAL_NON_JSON = "NON_JSON_RESPONSE"
REFUSAL_PROVIDER_STATUS = "PROVIDER_STATUS"
REFUSAL_SCHEMA_CHANGED = "SCHEMA_CHANGED"


def normalize_host(url: str) -> str:
    """Normalise a base URL for comparison. No trailing slash, no case games."""
    return (url or "").strip().rstrip("/").lower()


def host_is_documented_cn(url: str) -> bool:
    """True only for the documented CN server address itself.

    A URL that merely *contains* the host (a proxy path, a suffix trick) does
    not count: the comparison is against the normalised origin, so a request
    cannot be pointed somewhere else by extending the string.
    """
    return normalize_host(url) in {normalize_host(h) for h in DOCUMENTED_CN_HOSTS}


class NativeTtsRefusal(RuntimeError):
    """One provider interaction failed, with every observable fact preserved.

    The fields deliberately mirror the four different "codes" a request can
    have, and they are never collapsed into one number:

    ``code``
        this adapter's own refusal class -- what to *do* about it.
    ``http_status``
        the transport-level HTTP status. ``200`` here means "the service
        answered", which says nothing about success.
    ``provider_status_code`` / ``provider_status_msg``
        MiniMax's own business status from ``base_resp``. This is the field
        the CLI discarded, and it is the field that distinguishes 1008 from
        2013 from 2042.
    ``trace_id``
        the provider's trace id, present whenever the provider answered with a
        JSON envelope. This is what vendor support asks for.

    The credential is never part of this object, its ``detail``, or its
    ``repr``: a failure report must be safe to paste into a ticket.
    """

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        http_status: Optional[int] = None,
        provider_status_code: Optional[int] = None,
        provider_status_msg: str = "",
        trace_id: str = "",
        raw: Optional[Dict[str, Any]] = None,
        response_text: str = "",
        retry_allowed: bool = False,
    ) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail
        self.http_status = http_status
        self.provider_status_code = provider_status_code
        self.provider_status_msg = provider_status_msg
        self.trace_id = trace_id
        self.raw = raw
        self.response_text = response_text
        #: False everywhere. One request per authorisation; a refusal that is
        #: re-sent is a second charge attempt, not a retry.
        self.retry_allowed = retry_allowed

    def structured(self) -> Dict[str, Any]:
        """The safe, serialisable error taxonomy. Contains no credential."""
        return {
            "refusal_code": self.code,
            "detail": self.detail,
            "http_status": self.http_status,
            "provider_status_code": self.provider_status_code,
            "provider_status_msg": self.provider_status_msg,
            "trace_id": self.trace_id or None,
            "raw_provider_error_available": bool(
                self.provider_status_code is not None or self.response_text
            ),
            "retry_allowed": self.retry_allowed,
        }


@dataclass(frozen=True)
class NativeTtsResult:
    """One successful provider answer, fully parsed.

    ``raw`` is the complete parsed JSON envelope. The public receipt is built
    from :meth:`public_summary`, which never contains the audio hex and never
    contains anything credential-shaped; ``raw`` exists for the private
    diagnostic record in ``.private/``.
    """

    http_status: int
    trace_id: str
    status_code: int
    status_msg: str
    audio_bytes: bytes
    audio_hex_chars: int
    extra_info: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def usage_characters(self) -> Optional[int]:
        value = self.extra_info.get("usage_characters")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def usage_voice_count(self) -> Optional[int]:
        """The billed first-use voice count.

        Documented: "本次请求计费的音色数量（音色首次使用时计费），仅在产生音色费用
        时返回" -- returned exactly when the one-time voice fee was charged. Its
        presence on the activation receipt is evidence the fee was collected.
        """
        value = self.extra_info.get("usage_voice_count")
        return int(value) if isinstance(value, (int, float)) else None

    def public_summary(self) -> Dict[str, Any]:
        """The scrubable summary a receipt may carry. No audio, no raw blob."""
        return {
            "http_status": self.http_status,
            "base_resp": {"status_code": self.status_code, "status_msg": self.status_msg},
            "trace_id": self.trace_id,
            "audio_hex_chars": self.audio_hex_chars,
            "extra_info": {
                key: value
                for key, value in self.extra_info.items()
                if key not in ("audio",)
            },
            "usage_characters": self.usage_characters,
            "usage_voice_count": self.usage_voice_count,
            "raw_response_stored_privately": True,
        }


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise NativeTtsRefusal(REFUSAL_INVALID_PAYLOAD, detail)


def build_t2a_payload(
    *,
    text: str,
    voice_id: str,
    model: str = "speech-2.8-hd",
    speed: float = 1,
    vol: float = 1,
    pitch: int = 0,
    sample_rate: int = 32000,
    fmt: str = "wav",
    channel: int = 1,
    pronunciation_entries: Optional[List[str]] = None,
    output_format: str = "hex",
    stream: bool = False,
) -> Dict[str, Any]:
    """Build the documented ``T2aV2Req`` payload. Never invents a field.

    Every value is validated against the documented domain before the request
    is built. A builder that forwards out-of-domain values would let a typo
    become a provider 2013 -- or, worse, silently disagree with the JSON this
    repository believed it had sent.
    """
    _require(isinstance(text, str) and text.strip() != "", "text must be non-empty")
    _require(isinstance(voice_id, str) and voice_id.strip() != "", "voice_id required")
    _require(model in DOCUMENTED_MODELS, f"model {model!r} is not documented")
    _require(0.5 <= float(speed) <= 2, f"speed {speed!r} outside documented [0.5, 2]")
    _require(0 < float(vol) <= 10, f"vol {vol!r} outside documented (0, 10]")
    _require(-12 <= int(pitch) <= 12, f"pitch {pitch!r} outside documented [-12, 12]")
    _require(
        int(sample_rate) in DOCUMENTED_SAMPLE_RATES,
        f"sample_rate {sample_rate!r} outside documented {DOCUMENTED_SAMPLE_RATES}",
    )
    _require(fmt in DOCUMENTED_AUDIO_FORMATS, f"format {fmt!r} is not documented")
    _require(int(channel) in (1, 2), f"channel {channel!r} outside documented [1, 2]")
    _require(output_format in ("hex", "url"), "output_format must be 'hex' or 'url'")
    _require(stream is False, "stream must be False; this adapter is non-streaming only")

    payload: Dict[str, Any] = {
        "model": model,
        "text": text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": speed,
            "vol": vol,
            "pitch": pitch,
        },
        "audio_setting": {
            "sample_rate": int(sample_rate),
            "format": fmt,
            "channel": int(channel),
        },
        "output_format": output_format,
    }
    if pronunciation_entries:
        payload["pronunciation_dict"] = {"tone": list(pronunciation_entries)}
    return payload


def decode_hex_audio(audio_hex: str) -> bytes:
    """Decode the documented hex-encoded audio payload, or refuse.

    Non-stream responses carry audio as a hex string ("采用 hex 编码"). A body
    that is not hex is a schema change, not audio, and must never be written to
    disk as if it were sound.
    """
    if not isinstance(audio_hex, str) or not audio_hex:
        raise NativeTtsRefusal(
            REFUSAL_SCHEMA_CHANGED, "response carried no data.audio string"
        )
    try:
        return bytes.fromhex(audio_hex)
    except ValueError as exc:
        raise NativeTtsRefusal(
            REFUSAL_SCHEMA_CHANGED,
            f"data.audio is not valid hex ({len(audio_hex)} chars): {exc}",
        ) from exc


#: A transport receives ``(url, headers, body_bytes, timeout_seconds)`` and
#: returns ``(http_status, body_bytes)``. It exists so every unit test can run
#: the full request/response pipeline with no network at all; production uses
#: :func:`_urllib_transport`, the only place in this module that touches a
#: socket.
Transport = Callable[[str, Dict[str, str], bytes, float], Tuple[int, bytes]]


def _urllib_transport(
    url: str, headers: Dict[str, str], body: bytes, timeout_s: float
) -> Tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return int(response.status), response.read()
    except urllib.error.HTTPError as exc:
        # An HTTP error still carries a body, and the body is where the
        # provider's base_resp lives. Reading it here is what makes a 4xx a
        # diagnosable provider answer instead of a bare status number.
        try:
            return int(exc.code), exc.read()
        except Exception:  # noqa: BLE001 - unreadable body is still an HTTP error
            return int(exc.code), b""


def send_t2a_once(
    *,
    payload: Dict[str, Any],
    credential: str,
    base_url: str = MINIMAX_CN_HOST,
    transport: Optional[Transport] = None,
    timeout_s: float = 600.0,
    clock: Optional[Callable[[], float]] = None,
) -> NativeTtsResult:
    """Send exactly one ``POST /v1/t2a_v2`` and parse the answer completely.

    Raises:
        NativeTtsRefusal: on any failure, with :meth:`NativeTtsRefusal.structured`
            fields preserved. There is no retry: this function is entered once
            per authorisation, and a second entry is a second charge attempt
            that only a new human authorisation may create.

    The credential appears in exactly one place: the ``Authorization`` header
    of the single request. It is not logged, not included in refusals and not
    stored anywhere by this module.
    """
    if not host_is_documented_cn(base_url):
        # The point of this adapter. A request that cannot name the service it
        # addresses must not leave the machine.
        raise NativeTtsRefusal(
            REFUSAL_HOST_NOT_DOCUMENTED_CN,
            f"base_url {base_url!r} is not the documented CN server "
            f"({', '.join(DOCUMENTED_CN_HOSTS)}). This adapter exists because the "
            "first-activation call must positively address the documented CN "
            "service; pointing it elsewhere is a stop, not a fallback.",
        )
    if not credential:
        raise NativeTtsRefusal(
            REFUSAL_INVALID_PAYLOAD, "no credential supplied; refusing to send"
        )
    if not isinstance(payload, dict) or not payload.get("model") or not payload.get("text"):
        raise NativeTtsRefusal(
            REFUSAL_INVALID_PAYLOAD,
            "payload must be the documented T2aV2 object; refusing to send "
            "anything else",
        )

    url = normalize_host(base_url) + T2A_PATH
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + credential,
        "Content-Type": "application/json",
        "User-Agent": "contentops-native-tts/1",
    }

    send = transport or _urllib_transport
    t0 = (clock or time.monotonic)()
    try:
        http_status, response_body = send(url, headers, body, float(timeout_s))
    except Exception as exc:  # noqa: BLE001 - any transport failure, never retried
        # ``type(exc)`` only: a transport exception message can contain the
        # URL, and for some libraries parts of the request; it never contains
        # the header, and neither will this refusal.
        raise NativeTtsRefusal(
            REFUSAL_NETWORK,
            f"transport failed before an HTTP response was received "
            f"({type(exc).__name__}). Exactly one request was attempted; it is "
            "not retried.",
        ) from exc
    elapsed_ms = int(((clock or time.monotonic)() - t0) * 1000)

    try:
        envelope = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        text_preview = response_body[:400].decode("utf-8", errors="replace")
        raise NativeTtsRefusal(
            REFUSAL_NON_JSON,
            f"provider answered HTTP {http_status} with a non-JSON body; "
            "the envelope this adapter parses is gone. Preview is bounded and "
            "credential-free.",
            http_status=http_status,
            response_text=text_preview,
        )
    if not isinstance(envelope, dict):
        raise NativeTtsRefusal(
            REFUSAL_SCHEMA_CHANGED,
            f"provider answered HTTP {http_status} with a JSON value that is not "
            "an object",
            http_status=http_status,
        )

    base = envelope.get("base_resp") or {}
    provider_code = base.get("status_code")
    provider_msg = str(base.get("status_msg") or "")
    trace_id = str(envelope.get("trace_id") or "")
    if provider_code is None and http_status >= 400:
        raise NativeTtsRefusal(
            REFUSAL_HTTP_ERROR,
            f"provider answered HTTP {http_status} without a base_resp envelope",
            http_status=http_status,
            trace_id=trace_id,
            raw=envelope,
        )
    try:
        provider_code_int = int(provider_code)
    except (TypeError, ValueError):
        raise NativeTtsRefusal(
            REFUSAL_SCHEMA_CHANGED,
            f"base_resp.status_code={provider_code!r} is not an integer; the "
            "schema this adapter was written against has changed",
            http_status=http_status,
            raw=envelope,
        )
    if provider_code_int != 0:
        raise NativeTtsRefusal(
            REFUSAL_PROVIDER_STATUS,
            f"provider refused with base_resp.status_code={provider_code_int} "
            f"({provider_msg or 'no message'}); HTTP {http_status}",
            http_status=http_status,
            provider_status_code=provider_code_int,
            provider_status_msg=provider_msg,
            trace_id=trace_id,
            raw=envelope,
        )

    data = envelope.get("data") or {}
    audio_hex = data.get("audio") if isinstance(data, dict) else None
    audio_bytes = decode_hex_audio(audio_hex)
    if len(audio_bytes) == 0:
        raise NativeTtsRefusal(
            REFUSAL_SCHEMA_CHANGED,
            "provider reported success but returned zero audio bytes",
            http_status=http_status,
            trace_id=trace_id,
            raw=envelope,
        )

    extra_info = envelope.get("extra_info") or {}
    if not isinstance(extra_info, dict):
        extra_info = {}
    extra_info = dict(extra_info)
    extra_info["_elapsed_ms"] = elapsed_ms

    return NativeTtsResult(
        http_status=http_status,
        trace_id=trace_id,
        status_code=provider_code_int,
        status_msg=provider_msg,
        audio_bytes=audio_bytes,
        audio_hex_chars=len(audio_hex) if isinstance(audio_hex, str) else 0,
        extra_info=extra_info,
        raw=envelope,
    )
