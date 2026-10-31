"""Traceability for the M5 media-use sample inputs.

Closes two audit findings:

* **D-4** — the sample shipped receipts for an image and a BGM that were never
  committed, so a clone held hashes with nothing to check them against and
  ``python scripts/m5_production.py projects/m5-media-use`` could not run.
* **D-8** — the SFX import receipt lived under gitignored ``.media/``, so the
  licence behind one third-party asset was unreviewable from the repository.

Every assertion here is one link in the chain a reviewer needs:
fixture bytes -> import receipt -> rights record -> stage reference.
"""
from __future__ import annotations

import hashlib
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
from contentops.media import rights_gate  # noqa: E402
from process_utils import hidden_run  # noqa: E402

PROJECT = ROOT / "projects" / "m5-media-use"
ASSETS = PROJECT / "assets"
RECEIPTS = PROJECT / "receipts"

IMAGE = ASSETS / "support.png"
IMAGE_RECEIPT = ASSETS / "support.png.receipt.json"
BGM = ASSETS / "bed.mp3"
BGM_RECEIPT = ASSETS / "bed.mp3.receipt.json"
SOURCE_SCREENSHOT = ROOT / "projects" / "easel-review" / "sources" / "screenshots" / "01-easel-hero.png"

MEDIA_SUFFIXES = {".png", ".jpg", ".jpeg", ".mp3", ".wav", ".m4a", ".mp4"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _receipt(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _tracked(rel: str) -> bool:
    out = hidden_run(["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), timeout=60)
    return out.returncode == 0


def _requests() -> dict:
    config = m5._read_yaml(PROJECT / "project.yaml")
    return {item["id"]: item for item in config["media_use"]["requests"]}


class FixtureTests(unittest.TestCase):
    def test_the_image_fixture_is_tracked_and_matches_its_receipt(self):
        self.assertTrue(IMAGE.is_file(), f"{IMAGE} is missing")
        self.assertEqual(_sha(IMAGE), _receipt(IMAGE_RECEIPT)["output_sha256"],
                         "the committed image does not match the receipt that describes it")
        self.assertTrue(_tracked("projects/m5-media-use/assets/support.png"),
                        "the image is not tracked; a clone would not have it")

    def test_the_bgm_fixture_is_tracked_and_matches_its_receipt(self):
        self.assertTrue(BGM.is_file(), f"{BGM} is missing")
        self.assertEqual(_sha(BGM), _receipt(BGM_RECEIPT)["output_sha256"])
        self.assertTrue(_tracked("projects/m5-media-use/assets/bed.mp3"),
                        "the BGM is not tracked; a clone would not have it")

    def test_the_image_fixture_is_the_repository_own_screenshot(self):
        self.assertTrue(SOURCE_SCREENSHOT.is_file())
        self.assertEqual(_sha(IMAGE), _sha(SOURCE_SCREENSHOT),
                         "the sample image must stay byte-identical to the tracked "
                         "Easel screenshot its rights record describes")

    def test_no_other_media_in_this_sample_is_tracked(self):
        out = hidden_run(["git", "ls-files", "projects/m5-media-use"],
                         cwd=str(ROOT), timeout=60)
        self.assertEqual(out.returncode, 0)
        media = sorted(
            name for name in out.stdout.split()
            if Path(name).suffix.lower() in MEDIA_SUFFIXES
        )
        self.assertEqual(
            media,
            ["projects/m5-media-use/assets/bed.mp3",
             "projects/m5-media-use/assets/support.png"],
            "the fixture exception must stay narrow: only these two media files",
        )


class RightsTests(unittest.TestCase):
    def test_every_request_proves_its_rights(self):
        """Each declared need must survive the same gate the stage runs."""
        for asset_id, request in _requests().items():
            with self.subTest(asset=asset_id):
                record = rights_gate.validate_request_rights(request, PROJECT)
                self.assertEqual(record["license_id"], request["rights"]["license_id"])
                self.assertFalse(record["evidence_capable"],
                                 "media can never back a factual claim")

    def test_a_bare_confirmation_cannot_stand_in_for_rights(self):
        request = dict(_requests()["support_visual"])
        request.pop("rights", None)
        request["rights_reviewed"] = True
        with self.assertRaises(rights_gate.RightsError):
            rights_gate.validate_request_rights(request, PROJECT)


class ReceiptMirrorTests(unittest.TestCase):
    def test_every_imported_asset_has_a_tracked_receipt(self):
        stage = json.loads((RECEIPTS / "media-use-stage.json").read_text(encoding="utf-8"))
        imported = [row for row in stage["results"] if row["state"] == "IMPORTED"]
        self.assertEqual(len(imported), 3, "the sample imports an image, a BGM and an SFX")
        for row in imported:
            with self.subTest(asset=row["id"]):
                ref = row["receipt_ref"]
                self.assertTrue(ref.startswith("receipts/media-use/"),
                                f"{row['id']} still points outside the tracked tree: {ref}")
                path = PROJECT / ref
                self.assertTrue(path.is_file(), f"{ref} is missing")
                self.assertEqual(_receipt(path)["output_sha256"], row["sha256"],
                                 "the tracked receipt describes different bytes")
                self.assertTrue(_tracked(f"projects/m5-media-use/{ref}"),
                                f"{ref} is not tracked; the reference would dangle")

    def test_the_sfx_receipt_carries_its_licence_and_attribution(self):
        sfx = _receipt(RECEIPTS / "media-use" / "sfx_001.mp3.receipt.json")
        self.assertEqual(sfx["schema"], "contentops.media-import/v1")
        self.assertEqual(sfx["license"], "Pixabay-Content-License")
        self.assertTrue(sfx["attribution"].strip())
        self.assertFalse(sfx["evidence_capable"])
        self.assertFalse(sfx["provider_call"])

    def test_a_receipt_is_mirrored_and_the_original_is_left_alone(self):
        with tempfile.TemporaryDirectory() as raw:
            project = Path(raw)
            source = project / ".media" / "audio" / "sfx" / "sfx_001.mp3.receipt.json"
            source.parent.mkdir(parents=True)
            source.write_text('{"schema": "contentops.media-import/v1"}\n', encoding="utf-8")

            class Imported:
                receipt_path = str(source)
                receipt_ref = "sfx_001.mp3.receipt.json"

            ref = m5._mirror_import_receipt(project, Imported())
            self.assertEqual(ref, "receipts/media-use/sfx_001.mp3.receipt.json")
            mirror = project / ref
            self.assertTrue(mirror.is_file())
            self.assertEqual(mirror.read_bytes(), source.read_bytes(),
                             "the mirror must be byte-identical to the adapter receipt")
            self.assertTrue(source.is_file(), "the adapter receipt must not be moved")

    def test_a_missing_receipt_keeps_the_original_reference(self):
        with tempfile.TemporaryDirectory() as raw:
            class Imported:
                receipt_path = str(Path(raw) / "absent.receipt.json")
                receipt_ref = "absent.receipt.json"

            self.assertEqual(m5._mirror_import_receipt(Path(raw), Imported()),
                             "absent.receipt.json")


if __name__ == "__main__":
    unittest.main()
