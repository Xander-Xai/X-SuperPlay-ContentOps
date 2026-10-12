"""Regression tests for the native CN T2A adapter. Issue #34.

Every test here runs offline. The provider is replaced by a fake transport that
receives the exact ``(url, headers, body, timeout)`` tuple the adapter would
send, so the schema, the host pinning, the single-request rule and the
credential isolation are all exercised without a socket.

The tests that matter most are the ones that keep Issue #34's two root causes
fixed:

- the adapter must refuse any host but the documented CN server, so a request
  cannot "work" against a service the balance evidence never proved;
- a provider refusal must preserve ``base_resp.status_code`` and ``trace_id``
  as separate fields, because the CLI transport destroyed exactly those.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.minimax_native_tts import (  # noqa: E402
    DOCUMENTED_CN_HOSTS,
    MINIMAX_CN_HOST,
    REFUSAL_HOST_NOT_DOCUMENTED_CN,
    REFUSAL_INVALID_PAYLOAD,
    REFUSAL_NETWORK,
    REFUSAL_NON_JSON,
    REFUSAL_PROVIDER_STATUS,
    REFUSAL_SCHEMA_CHANGED,
    T2A_PATH,
    NativeTtsRefusal,
    build_t2a_payload,
    decode_hex_audio,
    host_is_documented_cn,
    send_t2a_once,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


ACTIVATION_TEXT = "这是一段用于首次激活的最短自然中文语音样本。"
SECRET = "sk-api-TEST-SECRET-DO-NOT-PRINT-1234567890"


def _payload(**overrides):
    params = dict(text=ACTIVATION_TEXT, voice_id="founder_primary_v1", model="speech-2.8-hd")
    params.update(overrides)
    return build_t2a_payload(**params)


class FakeTransport:
    """Records every request and returns a scripted response. Never a socket."""

    def __init__(self, responders):
        self.responders = list(responders)
        self.calls = []

    def __call__(self, url, headers, body, timeout_s):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": json.loads(body.decode("utf-8")),
                "timeout_s": timeout_s,
            }
        )
        responder = self.responders.pop(0)
        if isinstance(responder, Exception):
            raise responder
        return responder


def _ok_envelope(audio_hex: str = "00" * 64) -> bytes:
    return json.dumps(
        {
            "data": {"audio": audio_hex, "status": 2},
            "extra_info": {
                "audio_length": 1000,
                "usage_characters": 44,
                "usage_voice_count": 1,
                "audio_format": "wav",
            },
            "trace_id": "0123456789abcdef0123456789abcdef",
            "base_resp": {"status_code": 0, "status_msg": "success"},
        }
    ).encode("utf-8")


def _error_envelope(code: int, msg: str) -> bytes:
    return json.dumps(
        {
            "trace_id": "fedcba9876543210fedcba9876543210",
            "base_resp": {"status_code": code, "status_msg": msg},
        }
    ).encode("utf-8")


# --- A. payload schema ---------------------------------------------------------


@test
def test_payload_carries_exactly_the_documented_fields_and_values():
    """The request schema is the documentation, verbatim. Extra keys are a bug.

    A payload with an invented field is not a superset of the documented
    request; it is a different request that no page describes, and the provider
    may bill or behave differently for it. This locks the shape.
    """
    payload = _payload()
    assert set(payload) == {
        "model",
        "text",
        "stream",
        "voice_setting",
        "audio_setting",
        "output_format",
    }, sorted(payload)
    assert payload["model"] == "speech-2.8-hd"
    assert payload["text"] == ACTIVATION_TEXT
    assert payload["stream"] is False
    assert payload["output_format"] == "hex"
    assert payload["voice_setting"] == {
        "voice_id": "founder_primary_v1",
        "speed": 1,
        "vol": 1,
        "pitch": 0,
    }
    assert payload["audio_setting"] == {
        "sample_rate": 32000,
        "format": "wav",
        "channel": 1,
    }
    print("[ok] 1. the payload is exactly the documented T2aV2 request shape")


@test
def test_payload_pronunciation_entries_map_to_the_documented_dict_shape():
    payload = _payload(pronunciation_entries=["Easel/伊泽尔"])
    assert payload["pronunciation_dict"] == {"tone": ["Easel/伊泽尔"]}
    bare = _payload()
    assert "pronunciation_dict" not in bare
    print("[ok] 2. pronunciation rules map to pronunciation_dict.tone only when present")


@test
def test_out_of_domain_values_are_refused_before_any_request():
    """A typo must be a local refusal, not a provider 2013 or a silent default."""
    for overrides in (
        dict(speed=0.1),
        dict(speed=2.5),
        dict(vol=0),
        dict(pitch=13),
        dict(sample_rate=12345),
        dict(fmt="ogg"),
        dict(channel=3),
        dict(model="speech-9.9"),
        dict(text="   "),
        dict(stream=True),
    ):
        try:
            _payload(**overrides)
        except NativeTtsRefusal as exc:
            assert exc.code == REFUSAL_INVALID_PAYLOAD, (overrides, exc.code)
        else:
            raise AssertionError(f"{overrides} should have been refused locally")
    print("[ok] 3. every out-of-domain value is refused locally, before the network")


# --- B. host pinning -----------------------------------------------------------


@test
def test_the_documented_host_is_the_only_accepted_origin():
    assert host_is_documented_cn(MINIMAX_CN_HOST) is True
    # Trailing slash or case must not defeat the check.
    assert host_is_documented_cn(MINIMAX_CN_HOST + "/") is True
    assert host_is_documented_cn(MINIMAX_CN_HOST.upper()) is True
    # A host that merely contains the string is not the origin.
    assert host_is_documented_cn(MINIMAX_CN_HOST + ".evil.example") is False
    assert host_is_documented_cn("https://api.example.invalid") is False
    assert host_is_documented_cn("") is False
    assert MINIMAX_CN_HOST in DOCUMENTED_CN_HOSTS
    print("[ok] 4. only the documented CN origin passes the host check")


@test
def test_a_foreign_base_url_is_refused_before_the_transport_is_touched():
    """The exact root-cause guard: the request must positively name the CN service."""
    transport = FakeTransport([(200, _ok_envelope())])
    try:
        send_t2a_once(
            payload=_payload(),
            credential=SECRET,
            base_url="https://api.example.invalid",
            transport=transport,
        )
    except NativeTtsRefusal as exc:
        assert exc.code == REFUSAL_HOST_NOT_DOCUMENTED_CN, exc.code
    else:
        raise AssertionError("a foreign host must be refused")
    assert transport.calls == [], "the transport must not have been called"
    print("[ok] 5. a non-CN base_url is refused before any request is built")


# --- C. the success path -------------------------------------------------------


@test
def test_one_request_produces_fully_parsed_audio_and_usage_fields():
    audio_hex = (b"RIFF" + b"\x00" * 60).hex()
    transport = FakeTransport([(200, _ok_envelope(audio_hex))])
    result = send_t2a_once(
        payload=_payload(), credential=SECRET, transport=transport
    )
    assert len(transport.calls) == 1, "exactly one request, ever"
    call = transport.calls[0]
    assert call["url"] == MINIMAX_CN_HOST + T2A_PATH
    assert call["headers"]["Authorization"] == "Bearer " + SECRET
    assert call["headers"]["Content-Type"] == "application/json"
    assert call["body"]["voice_setting"]["voice_id"] == "founder_primary_v1"
    assert call["body"]["model"] == "speech-2.8-hd"

    assert result.http_status == 200
    assert result.status_code == 0
    assert result.trace_id == "0123456789abcdef0123456789abcdef"
    assert result.audio_bytes == bytes.fromhex(audio_hex)
    assert result.usage_characters == 44
    assert result.usage_voice_count == 1, (
        "usage_voice_count is the documented signal that the one-time voice fee "
        "was charged on this request"
    )
    print("[ok] 6. one request yields audio, trace id, usage chars and voice count")


@test
def test_the_public_summary_never_contains_audio_or_credential_shaped_text():
    transport = FakeTransport([(200, _ok_envelope())])
    result = send_t2a_once(payload=_payload(), credential=SECRET, transport=transport)
    blob = json.dumps(result.public_summary(), ensure_ascii=False)
    assert SECRET not in blob
    assert "Bearer" not in blob
    summary = result.public_summary()
    assert summary["usage_voice_count"] == 1
    assert summary["trace_id"] == result.trace_id
    extra = summary.get("extra_info", {})
    assert "audio" not in extra, "the raw audio payload must never be in the summary"
    assert "data" not in summary, "the raw envelope must never be in the summary"
    assert summary["audio_hex_chars"] == len("00" * 64)
    assert summary["raw_response_stored_privately"] is True
    print("[ok] 7. the public summary is scrubable and audio-free")


# --- D. error taxonomy ---------------------------------------------------------


@test
def test_a_provider_business_refusal_preserves_http_code_msg_and_trace_separately():
    """The CLI destroyed these fields. This test keeps them destructured.

    Measured historical behaviour: the CLI emitted
    ``{"error": {"code": 1, "message": "API error: insufficient balance (HTTP 200)"}}``
    where ``1`` is the CLI's own general-error class. The provider's real
    ``base_resp.status_code`` (1008) and its ``trace_id`` never survived. A
    native refusal must not repeat that loss.
    """
    transport = FakeTransport([(200, _error_envelope(1008, "insufficient balance"))])
    try:
        send_t2a_once(payload=_payload(), credential=SECRET, transport=transport)
    except NativeTtsRefusal as exc:
        structured = exc.structured()
        assert exc.code == REFUSAL_PROVIDER_STATUS
        assert structured["http_status"] == 200
        assert structured["provider_status_code"] == 1008
        assert structured["provider_status_msg"] == "insufficient balance"
        assert structured["trace_id"] == "fedcba9876543210fedcba9876543210"
        assert structured["retry_allowed"] is False
        blob = json.dumps(structured, ensure_ascii=False)
        assert SECRET not in blob
        assert "Bearer" not in blob
    else:
        raise AssertionError("a 1008 envelope must be refused")
    assert len(transport.calls) == 1, "a refusal is never re-sent"
    print("[ok] 8. HTTP status, provider status code, message and trace id stay separate")


@test
def test_an_http_error_with_json_envelope_keeps_both_layers():
    transport = FakeTransport([(500, _error_envelope(1013, "service internal error"))])
    try:
        send_t2a_once(payload=_payload(), credential=SECRET, transport=transport)
    except NativeTtsRefusal as exc:
        structured = exc.structured()
        assert structured["http_status"] == 500
        assert structured["provider_status_code"] == 1013
    else:
        raise AssertionError("a 1013 envelope must be refused")
    print("[ok] 9. a 5xx that still carries base_resp keeps both status layers")


@test
def test_a_non_json_body_is_a_bounded_refusal_not_a_crash():
    transport = FakeTransport([(502, b"<html>gateway error</html>")])
    try:
        send_t2a_once(payload=_payload(), credential=SECRET, transport=transport)
    except NativeTtsRefusal as exc:
        assert exc.code == REFUSAL_NON_JSON
        assert exc.http_status == 502
        assert "gateway error" in exc.response_text
        assert SECRET not in exc.response_text
    else:
        raise AssertionError("a non-JSON body must be refused")
    print("[ok] 10. a non-JSON body becomes a bounded, credential-free refusal")


@test
def test_invalid_audio_hex_is_a_schema_refusal():
    body = json.dumps(
        {
            "data": {"audio": "not-hex-at-all-string", "status": 2},
            "base_resp": {"status_code": 0, "status_msg": "success"},
            "trace_id": "t",
        }
    ).encode()
    transport = FakeTransport([(200, body)])
    try:
        send_t2a_once(payload=_payload(), credential=SECRET, transport=transport)
    except NativeTtsRefusal as exc:
        assert exc.code == REFUSAL_SCHEMA_CHANGED
    else:
        raise AssertionError("invalid hex must be refused")
    straight = decode_hex_audio("00ff")
    assert straight == b"\x00\xff"
    try:
        decode_hex_audio("")
    except NativeTtsRefusal as exc:
        assert exc.code == REFUSAL_SCHEMA_CHANGED
    else:
        raise AssertionError("empty audio must be refused")
    print("[ok] 11. non-hex or empty audio is a schema refusal")


@test
def test_a_transport_failure_is_one_attempt_and_no_retry():
    transport = FakeTransport([ConnectionResetError("boom"), (200, _ok_envelope())])
    try:
        send_t2a_once(payload=_payload(), credential=SECRET, transport=transport)
    except NativeTtsRefusal as exc:
        assert exc.code == REFUSAL_NETWORK
        assert "ConnectionResetError" in exc.detail
        assert SECRET not in str(exc)
    else:
        raise AssertionError("a transport failure must be refused")
    assert len(transport.calls) == 1, (
        "the second scripted response must never be consumed: the adapter "
        "performs exactly one attempt"
    )
    print("[ok] 12. a transport failure is exactly one attempt, with no retry")


@test
def test_missing_credential_or_malformed_payload_never_reaches_the_transport():
    transport = FakeTransport([(200, _ok_envelope())])
    for payload, credential, expected in (
        (_payload(), "", REFUSAL_INVALID_PAYLOAD),
        ({}, SECRET, REFUSAL_INVALID_PAYLOAD),
    ):
        try:
            send_t2a_once(payload=payload, credential=credential, transport=transport)
        except NativeTtsRefusal as exc:
            assert exc.code == expected, (payload, credential, exc.code)
        else:
            raise AssertionError("invalid input must be refused")
    assert transport.calls == []
    print("[ok] 13. invalid inputs are refused before the transport")


def main() -> int:
    failures = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            print(f"[FAIL] {fn.__name__}: {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {fn.__name__}: {type(exc).__name__}({exc})")
            failures += 1
    total = len(TESTS)
    if failures:
        print(f"\n{failures} of {total} test(s) failed")
        return 1
    print(f"\nAll {total} native TTS adapter tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
