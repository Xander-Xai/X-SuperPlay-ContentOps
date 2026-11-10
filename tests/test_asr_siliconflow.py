"""Offline tests for the SiliconFlow ASR transport adapter.

Every test drives a fake opener; no socket is opened and no key is real. The
point of this suite is to prove the adapter cannot turn an absent or malformed
answer into a passing verdict, because that is the only failure mode that would
matter to a founder reading a receipt.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media import asr_siliconflow as sf  # noqa: E402
from contentops.media.asr_backcheck import backcheck_speech, compare_transcript  # noqa: E402


def _audio(tmp: str, size: int = 2048) -> Path:
    path = Path(tmp) / "narration.wav"
    path.write_bytes(b"RIFF" + b"\0" * (size - 4))
    return path


class FakeOpener:
    """Records requests and replays a scripted sequence of responses."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append({"url": request.full_url, "headers": dict(request.headers),
                           "bytes": len(request.data or b"")})
        if len(self.responses) == 1:
            return self.responses[0]
        return self.responses.pop(0)


class SuccessPathTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get(sf.API_KEY_ENV)
        os.environ[sf.API_KEY_ENV] = "sk-test-not-a-real-key"

    def tearDown(self):
        if self._env is None:
            os.environ.pop(sf.API_KEY_ENV, None)
        else:
            os.environ[sf.API_KEY_ENV] = self._env

    def test_full_response_records_capabilities(self):
        body = json.dumps({
            "text": "这是完整的口播文本",
            "language": "zh",
            "words": [{"word": "这是", "start": 0.0, "end": 0.2}],
        }).encode("utf-8")
        opener = FakeOpener([(200, body)])
        with tempfile.TemporaryDirectory() as tmp:
            result = sf.transcribe(_audio(tmp), opener=opener, sleep=lambda _: None)
        self.assertEqual(result.text, "这是完整的口播文本")
        self.assertEqual(result.language, "zh")
        self.assertTrue(result.capabilities["timestamps"])
        self.assertTrue(result.capabilities["language"])
        self.assertFalse(result.capabilities["can_approve_quality"])

    def test_text_only_response_is_a_success_not_a_failure(self):
        opener = FakeOpener([(200, json.dumps({"text": "只有文本"}).encode("utf-8"))])
        with tempfile.TemporaryDirectory() as tmp:
            result = sf.transcribe(_audio(tmp), opener=opener, sleep=lambda _: None)
        self.assertEqual(result.text, "只有文本")
        self.assertFalse(result.capabilities["timestamps"])
        self.assertFalse(result.capabilities["language"])

    def test_request_is_multipart_with_model_field(self):
        opener = FakeOpener([(200, json.dumps({"text": "ok"}).encode("utf-8"))])
        with tempfile.TemporaryDirectory() as tmp:
            sf.transcribe(_audio(tmp), model="XingChenAGI/XingChenASR-V3.2",
                          opener=opener, sleep=lambda _: None)
        headers = {k.lower(): v for k, v in opener.calls[0]["headers"].items()}
        self.assertIn("multipart/form-data", headers["content-type"])
        self.assertGreater(opener.calls[0]["bytes"], 2048)


class FailurePathTests(unittest.TestCase):
    def setUp(self):
        os.environ[sf.API_KEY_ENV] = "sk-test-not-a-real-key"

    def tearDown(self):
        os.environ.pop(sf.API_KEY_ENV, None)

    def test_empty_transcript_is_skipped(self):
        opener = FakeOpener([(200, json.dumps({"text": "   "}).encode("utf-8"))])
        with tempfile.TemporaryDirectory() as tmp:
            result = backcheck_speech(
                _audio(tmp), "这是完整的口播文本",
                transcriber=lambda p: sf.transcribe(p, opener=opener, sleep=lambda _: None),
                provider="siliconflow")
        self.assertEqual(result.status, "SKIPPED")
        self.assertIsNone(result.coverage)

    def test_missing_text_field_is_skipped(self):
        opener = FakeOpener([(200, json.dumps({"result": "no text key"}).encode("utf-8"))])
        with tempfile.TemporaryDirectory() as tmp:
            result = backcheck_speech(
                _audio(tmp), "文本",
                transcriber=lambda p: sf.transcribe(p, opener=opener, sleep=lambda _: None),
                provider="siliconflow")
        self.assertEqual(result.status, "SKIPPED")
        self.assertIn("PROTOCOL", result.detail)

    def test_credential_error_is_not_retried(self):
        opener = FakeOpener([(401, b'{"message":"invalid token"}')])
        with tempfile.TemporaryDirectory() as tmp:
            result = backcheck_speech(
                _audio(tmp), "文本",
                transcriber=lambda p: sf.transcribe(p, opener=opener, sleep=lambda _: None),
                provider="siliconflow")
        self.assertEqual(result.status, "SKIPPED")
        self.assertEqual(len(opener.calls), 1)
        self.assertIn("CREDENTIAL", result.detail)

    def test_outage_retries_then_skips(self):
        opener = FakeOpener([(503, b"busy")] * 3)
        with tempfile.TemporaryDirectory() as tmp:
            result = backcheck_speech(
                _audio(tmp), "文本",
                transcriber=lambda p: sf.transcribe(
                    p, opener=opener, sleep=lambda _: None, max_attempts=3),
                provider="siliconflow")
        self.assertEqual(result.status, "SKIPPED")
        self.assertEqual(len(opener.calls), 3)
        self.assertIn("UNAVAILABLE", result.detail)

    def test_outage_then_success(self):
        opener = FakeOpener([(503, b"busy"),
                             (200, json.dumps({"text": "文本"}).encode("utf-8"))])
        with tempfile.TemporaryDirectory() as tmp:
            result = sf.transcribe(_audio(tmp), opener=opener, sleep=lambda _: None)
        self.assertEqual(result.text, "文本")
        self.assertEqual(result.attempts, 2)

    def test_missing_key_never_sends_a_request(self):
        os.environ.pop(sf.API_KEY_ENV, None)
        opener = FakeOpener([(200, b'{"text":"x"}')])
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sf.AsrTransportError) as ctx:
                sf.transcribe(_audio(tmp), opener=opener, sleep=lambda _: None)
        self.assertEqual(ctx.exception.kind, sf.MISSING_CREDENTIAL)
        self.assertEqual(len(opener.calls), 0)

    def test_oversize_file_never_sends_a_request(self):
        opener = FakeOpener([(200, b'{"text":"x"}')])
        with tempfile.TemporaryDirectory() as tmp:
            path = _audio(tmp)
            with path.open("r+b") as handle:
                handle.truncate(sf.MAX_FILE_BYTES + 1)
            with self.assertRaises(sf.AsrTransportError) as ctx:
                sf.transcribe(path, opener=opener, sleep=lambda _: None)
        self.assertEqual(ctx.exception.kind, sf.OVERSIZE)
        self.assertEqual(len(opener.calls), 0)


class ComparisonTests(unittest.TestCase):
    def test_comparison_uses_spoken_text_not_display_text(self):
        spoken = "九百八十二个文件逐个比对过哈希"
        display = "982 个文件逐个比对过哈希（字幕版）"
        result = compare_transcript(spoken, "982个文件逐个比对过哈希",
                                    provider="siliconflow")
        self.assertEqual(result.status, "NO_PROBLEM_DETECTED")
        mismatch = compare_transcript(display, "982个文件逐个比对过哈希",
                                      provider="siliconflow")
        self.assertEqual(mismatch.status, "DETECTED_PROBLEM")

    def test_coverage_below_floor_detects_problem(self):
        result = compare_transcript("完整的口播文本内容", "完全不同的东西",
                                    provider="siliconflow")
        self.assertEqual(result.status, "DETECTED_PROBLEM")
        self.assertLess(result.coverage, 0.85)

    def test_detector_never_grants_approval(self):
        payload = compare_transcript("文本", "文本", provider="siliconflow").as_dict()
        self.assertEqual(payload["role"], "DETECTOR_ONLY")
        self.assertFalse(payload["can_approve_quality"])
        self.assertNotIn("production_ready", payload)
        self.assertNotIn("publish_authorized", payload)


class ReceiptHygieneTests(unittest.TestCase):
    def test_credential_never_appears_in_detail_or_headers(self):
        secret = "sk-super-secret-value"
        os.environ[sf.API_KEY_ENV] = secret

        class EchoingOpener:
            def __call__(self, request, timeout):
                # A hostile or verbose server echoing the header must not leak it.
                return 401, f"bad key {secret}".encode("utf-8")

        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = backcheck_speech(
                    _audio(tmp), "文本",
                    transcriber=lambda p: sf.transcribe(
                        p, opener=EchoingOpener(), sleep=lambda _: None),
                    provider="siliconflow")
                payload = json.dumps(result.as_dict(), ensure_ascii=False)
        finally:
            os.environ.pop(sf.API_KEY_ENV, None)
        self.assertEqual(result.status, "SKIPPED")
        self.assertNotIn(secret, payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
