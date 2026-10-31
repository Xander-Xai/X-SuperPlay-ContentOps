"""Regression for the managed media-use status wrapper.

The adapter reports ``MediaUseStatus.available``. The managed entry must read
that field; it must not invent ``usable`` and fail after a grant is consumed.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import skill_execute  # noqa: E402


class SkillExecuteStatusContractTests(unittest.TestCase):
    def _status(self, available: bool):
        receipt = {"available": available, "reasons": [] if available else ["runtime lock missing"]}
        return SimpleNamespace(available=available, as_dict=lambda: dict(receipt))

    def test_status_wrapper_uses_available_not_usable(self):
        for available in (True, False):
            with self.subTest(available=available):
                with mock.patch.object(skill_execute, "MediaUseAdapter") as adapter_cls:
                    adapter_cls.return_value.status.return_value = self._status(available)
                    result = skill_execute._operation_executor("status")("status", None)
                self.assertEqual(result["ok"], available)
                self.assertEqual(result["receipt"]["available"], available)
                self.assertNotIn("usable", result["receipt"])

    def test_doctor_wrapper_uses_existing_doctor_contract(self):
        doctor = SimpleNamespace(
            ok=False,
            as_dict=lambda: {"ok": False, "checks": [], "status": {"available": False}},
        )
        with mock.patch.object(skill_execute, "MediaUseAdapter") as adapter_cls:
            adapter_cls.return_value.doctor.return_value = doctor
            result = skill_execute._operation_executor("doctor")("doctor", None)
        self.assertIn("status", result["receipt"])
        self.assertEqual(result["receipt"]["status"]["available"], False)


if __name__ == "__main__":
    unittest.main()
