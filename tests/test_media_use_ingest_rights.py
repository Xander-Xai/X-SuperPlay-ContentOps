"""The direct ``ingest`` entry must apply the same rights policy as ``import``.

PR #80 gated the direct import path. ``ingest`` copies a local file into the
project inventory through the same adapter, so a third-party licence there needs
a review record too; otherwise the policy can be avoided by choosing the other
verb. Owned material keeps its existing, stricter-in-the-other-direction
semantics: the operator's own capture needs no third-party URL.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import media_use_adapter as cli  # noqa: E402


def _cli_args(project: Path, license_name: str, rights_review: str = "") -> list[str]:
    argv = ["ingest", "--project", str(project), "--type", "sfx",
            "--source", str(project / "in.mp3"), "--license", license_name]
    if rights_review:
        argv += ["--rights-review", rights_review]
    return argv


class IngestRightsPolicyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run(self, argv: list[str]) -> int:
        with mock.patch.object(cli, "MediaUseAdapter") as adapter_cls:
            adapter_cls.return_value.ingest.return_value = {"type": "sfx"}
            with contextlib.redirect_stdout(io.StringIO()):
                return cli.main(argv)

    def test_ingest_refuses_a_software_licence(self):
        code = self._run(_cli_args(self.project, "GPL-3.0"))
        self.assertEqual(code, cli.EXIT_BLOCKED,
                         "a software licence cannot license media, even through ingest")

    def test_ingest_refuses_a_third_party_licence_without_a_review_record(self):
        code = self._run(_cli_args(self.project, "CC-BY-4.0"))
        self.assertEqual(code, cli.EXIT_BLOCKED,
                         "CC-BY-4.0 needs a review record; ingest must not skip it")

    def test_ingest_refuses_an_unknown_licence(self):
        code = self._run(_cli_args(self.project, "Totally-Made-Up-1.0"))
        self.assertEqual(code, cli.EXIT_BLOCKED)

    def test_ingest_accepts_an_owned_licence_without_a_review_record(self):
        code = self._run(_cli_args(self.project, "OWNED-BY-OPERATOR"))
        self.assertEqual(code, cli.EXIT_OK,
                         "operator-owned material keeps its existing semantics")

    def test_the_ingest_parser_exposes_a_rights_review_flag(self):
        parser = cli.build_parser()
        sub = next(action for action in parser._subparsers._group_actions
                   if isinstance(action, argparse._SubParsersAction))
        ingest = sub.choices["ingest"]
        dests = {action.dest for action in ingest._actions}
        self.assertIn("rights_review", dests,
                      "ingest must accept --rights-review like import does")


if __name__ == "__main__":
    unittest.main()
