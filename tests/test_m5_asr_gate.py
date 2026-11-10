"""The ASR gate in M5: evidence, or a block — never a silent pass.

Three outcomes are pinned because they are easy to conflate:

* clean transcript      -> review proceeds, nothing is approved;
* detected problem      -> review proceeds *with the finding on the record*,
                           because deciding what a misread word means is a human
                           judgement, not a detector's;
* no transcript at all  -> an account-bound project stops before compose.

The last one is the whole reason this gate exists. Before it, a missing ASR
runtime meant "no semantic QC", which looked identical to "semantic QC found
nothing wrong" in every receipt that followed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT / "scripts"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import m5_production as m5  # noqa: E402
from contentops.media.asr_siliconflow import AsrTransportError  # noqa: E402


class _Transcript:
    def __init__(self, text, model="XingChenAGI/XingChenASR-V3.2"):
        self.text = text
        self.model = model
        self.capabilities = {"text": True, "timestamps": False, "language": False}


def _raise_missing_key(_path):
    raise AsrTransportError("MISSING_CREDENTIAL", "SILICONFLOW_API_KEY is not set")


SCRIPT = {"lines": [{"id": "l1", "narration": "这一集我们讲清楚混合专家模型的训练成本"}]}


def _project(tmp: str, *, account: str | None) -> Path:
    project = Path(tmp) / "sample"
    (project / "assets" / "voice").mkdir(parents=True)
    (project / "receipts").mkdir(parents=True)
    (project / "assets" / "voice" / "narration.wav").write_bytes(b"RIFF" + b"\0" * 4096)
    lines = ["id: sample"]
    if account:
        lines.append(f"account_slug: {account}")
    (project / "project.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return project


def _config(account: str | None) -> dict:
    return {"account_slug": account} if account else {}


class MissingEvidenceTests(unittest.TestCase):
    def test_account_project_is_blocked_and_receipt_still_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account="x-superplay-future-intelligence")
            with self.assertRaises(m5.M5Blocked) as ctx:
                m5.stage_asr_backcheck(project, _config("x-superplay-future-intelligence"),
                                       SCRIPT, {"audio": "assets/voice/narration.wav"},
                                       transcriber=_raise_missing_key)
            self.assertIn("SILICONFLOW_API_KEY", str(ctx.exception))
            receipt = json.loads((project / "receipts" / "asr-backcheck.json")
                                 .read_text(encoding="utf-8"))
        self.assertEqual(receipt["status"], "SKIPPED")
        self.assertTrue(receipt["blocks_human_review"])
        self.assertFalse(receipt["production_ready"])

    def test_unbound_project_records_skip_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account=None)
            receipt = m5.stage_asr_backcheck(
                project, _config(None), SCRIPT,
                {"audio": "assets/voice/narration.wav"},
                transcriber=_raise_missing_key)
        self.assertEqual(receipt["status"], "SKIPPED")
        self.assertFalse(receipt["account_bound"])
        self.assertFalse(receipt["blocks_human_review"])


class EvidenceTests(unittest.TestCase):
    def test_clean_transcript_proceeds_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account="acct")
            receipt = m5.stage_asr_backcheck(
                project, _config("acct"), SCRIPT,
                {"audio": "assets/voice/narration.wav"},
                transcriber=lambda _: _Transcript("这一集我们讲清楚混合专家模型的训练成本"))
        self.assertEqual(receipt["status"], "NO_PROBLEM_DETECTED")
        self.assertFalse(receipt["blocks_human_review"])
        self.assertFalse(receipt["production_ready"])
        self.assertFalse(receipt["publish_authorized"])
        self.assertEqual(receipt["role"], "DETECTOR_ONLY")

    def test_detected_problem_reaches_review_rather_than_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account="acct")
            receipt = m5.stage_asr_backcheck(
                project, _config("acct"), SCRIPT,
                {"audio": "assets/voice/narration.wav"},
                transcriber=lambda _: _Transcript("完全听不清的一段东西"))
        self.assertEqual(receipt["status"], "DETECTED_PROBLEM")
        self.assertFalse(receipt["blocks_human_review"])
        self.assertTrue(receipt["issues"])

    def test_receipt_uses_logical_paths_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account="acct")
            receipt = m5.stage_asr_backcheck(
                project, _config("acct"), SCRIPT,
                {"audio": "assets/voice/narration.wav"},
                transcriber=lambda _: _Transcript("这一集我们讲清楚混合专家模型的训练成本"))
            payload = json.dumps(receipt, ensure_ascii=False)
        self.assertEqual(receipt["audio"], "project://assets/voice/narration.wav")
        self.assertNotIn(str(project), payload)
        self.assertNotIn(":\\", payload)

    def test_comparison_target_is_spoken_narration_not_subtitle_text(self):
        """A subtitle-shaped expectation would report a false problem.

        The lexicon rewrites how a token is pronounced, so the gate must compare
        against ``narration``. Here the on-screen text is a different string; a
        transcript that matches the *narration* must come back clean.
        """
        script = {"lines": [{
            "id": "l1",
            "narration": "这一集我们讲清楚混合专家模型的训练成本",
            "display_text": "MoE 训练成本",
        }]}
        with tempfile.TemporaryDirectory() as tmp:
            project = _project(tmp, account="acct")
            receipt = m5.stage_asr_backcheck(
                project, _config("acct"), script,
                {"audio": "assets/voice/narration.wav"},
                transcriber=lambda _: _Transcript("这一集我们讲清楚混合专家模型的训练成本"))
        self.assertEqual(receipt["status"], "NO_PROBLEM_DETECTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
