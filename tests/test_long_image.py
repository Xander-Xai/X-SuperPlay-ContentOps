"""Offline tests for stacking normalized cards into one vertical long image.

CI runs this file directly: ``python tests/test_long_image.py``. Pillow is the
only dependency and it is already required by ``contentops.media``; no network,
no platform and no renderer is involved.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.graphic import long_image as li  # noqa: E402


def _card(path: Path, size, color):
    from PIL import Image

    Image.new("RGB", size, color).save(path)
    return path


class GeometryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_height_formula(self):
        cards = [
            _card(self.tmp / "a.png", (1080, 1440), (200, 0, 0)),
            _card(self.tmp / "b.png", (1080, 1440), (0, 200, 0)),
            _card(self.tmp / "c.png", (1080, 1440), (0, 0, 200)),
        ]
        p = li.plan(cards, self.tmp / "out.png", gap=36, pad=60)

        self.assertEqual(p.canvas_width, 1080 + 60 * 2)
        self.assertEqual(p.canvas_height, 60 * 2 + 1440 * 3 + 36 * 2)
        self.assertEqual(p.offsets, (60, 60 + 1440 + 36, 60 + 2 * (1440 + 36)))

    def test_single_card_still_gets_the_padding(self):
        card = _card(self.tmp / "a.png", (1080, 1440), (10, 20, 30))
        p = li.plan([card], self.tmp / "out.png", gap=36, pad=60)

        self.assertEqual(p.canvas_height, 1440 + 120)
        self.assertEqual(p.offsets, (60,))

    def test_zero_gap_and_pad_are_allowed(self):
        cards = [
            _card(self.tmp / "a.png", (100, 50), (1, 1, 1)),
            _card(self.tmp / "b.png", (100, 50), (2, 2, 2)),
        ]
        p = li.plan(cards, self.tmp / "out.png", gap=0, pad=0)

        self.assertEqual((p.canvas_width, p.canvas_height), (100, 100))

    def test_variable_heights_are_kept(self):
        cards = [
            _card(self.tmp / "a.png", (100, 400), (5, 5, 5)),
            _card(self.tmp / "b.png", (100, 100), (6, 6, 6)),
        ]
        p = li.plan(cards, self.tmp / "out.png", gap=10, pad=0)

        self.assertEqual(p.canvas_height, 400 + 10 + 100)
        self.assertEqual(p.offsets, (0, 410))


class RefusalTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _code(self, callable_):
        with self.assertRaises(li.LongImageError) as ctx:
            callable_()
        return ctx.exception.code

    def test_empty_input_is_refused(self):
        self.assertEqual(
            self._code(lambda: li.plan([], self.tmp / "out.png")), "EMPTY_INPUT")

    def test_missing_card_is_named(self):
        with self.assertRaises(li.LongImageError) as ctx:
            li.plan([self.tmp / "nope.png"], self.tmp / "out.png")
        self.assertEqual(ctx.exception.code, "CARD_MISSING")
        self.assertIn("nope.png", ctx.exception.detail)

    def test_mixed_widths_are_refused_not_padded(self):
        cards = [
            _card(self.tmp / "a.png", (1080, 1440), (9, 9, 9)),
            _card(self.tmp / "b.png", (1200, 1440), (9, 9, 9)),
        ]
        self.assertEqual(
            self._code(lambda: li.plan(cards, self.tmp / "out.png")), "MIXED_WIDTH")

    def test_undecodable_card_is_refused(self):
        broken = self.tmp / "broken.png"
        broken.write_bytes(b"not a png at all")
        self.assertEqual(
            self._code(lambda: li.plan([broken], self.tmp / "out.png")), "CARD_UNDECODABLE")

    def test_negative_geometry_is_refused(self):
        card = _card(self.tmp / "a.png", (100, 100), (0, 0, 0))
        self.assertEqual(
            self._code(lambda: li.plan([card], self.tmp / "out.png", gap=-1)),
            "GEOMETRY_INVALID")

    def test_bad_background_is_refused(self):
        card = _card(self.tmp / "a.png", (100, 100), (0, 0, 0))
        self.assertEqual(
            self._code(lambda: li.plan([card], self.tmp / "out.png", background=(0, 0))),
            "BACKGROUND_INVALID")
        self.assertEqual(
            self._code(lambda: li.plan([card], self.tmp / "out.png", background=(0, 0, 300))),
            "BACKGROUND_INVALID")

    def test_canvas_over_the_limit_is_refused(self):
        card = _card(self.tmp / "a.png", (100, 100), (0, 0, 0))
        self.assertEqual(
            self._code(lambda: li.plan([card], self.tmp / "out.png", max_pixels=10_000)),
            "CANVAS_TOO_LARGE")

    def test_missing_out_dir_is_refused(self):
        card = _card(self.tmp / "a.png", (100, 100), (0, 0, 0))
        self.assertEqual(
            self._code(lambda: li.plan([card], self.tmp / "nope" / "out.png")),
            "OUT_DIR_MISSING")

    def test_unsupported_suffix_is_refused(self):
        card = _card(self.tmp / "a.png", (100, 100), (0, 0, 0))
        self.assertEqual(
            self._code(lambda: li.plan([card], self.tmp / "out.gif")), "OUT_INVALID")


class StitchTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_pixels_land_where_the_plan_says(self):
        from PIL import Image

        cards = [
            _card(self.tmp / "a.png", (100, 100), (200, 0, 0)),
            _card(self.tmp / "b.png", (100, 100), (0, 200, 0)),
        ]
        out = self.tmp / "out.png"
        li.stitch(cards, out, gap=20, pad=10)

        with Image.open(out) as image:
            self.assertEqual(image.size, (120, 10 * 2 + 100 * 2 + 20))
            self.assertEqual(image.getpixel((10, 10)), (200, 0, 0))
            self.assertEqual(image.getpixel((10, 10 + 100 + 20)), (0, 200, 0))
            self.assertEqual(image.getpixel((0, 0)), li.DEFAULT_BACKGROUND)

            canvas = Image.open(out).convert("RGB")
            # the gap row between the two cards is background, not a card
            self.assertEqual(canvas.getpixel((10, 10 + 100 + 10)), li.DEFAULT_BACKGROUND)

    def test_receipt_binds_inputs_and_output_by_digest(self):
        cards = [
            _card(self.tmp / "a.png", (1080, 1440), (200, 0, 0)),
            _card(self.tmp / "b.png", (1080, 1440), (0, 200, 0)),
        ]
        out = self.tmp / "out.png"
        receipt = li.stitch(cards, out)

        self.assertEqual(receipt["schema"], li.SCHEMA)
        self.assertEqual(receipt["card_count"], 2)
        self.assertEqual(receipt["canvas"], {"width": 1200, "height": 120 + 1440 * 2 + 36})
        self.assertFalse(receipt["authoritative"])

        self.assertEqual(
            [row["path"] for row in receipt["inputs"]],
            [card.resolve().as_posix() for card in cards],
        )
        self.assertEqual(
            [row["offset_y"] for row in receipt["inputs"]], [60, 60 + 1440 + 36])

        for row, card in zip(receipt["inputs"], cards):
            self.assertEqual(row["sha256"], li._sha256(card))
        self.assertEqual(receipt["output"]["sha256"], li._sha256(out))
        self.assertEqual(receipt["output"]["bytes"], out.stat().st_size)

    def test_no_partial_file_survives_a_finished_run(self):
        cards = [_card(self.tmp / "a.png", (100, 100), (1, 1, 1))]
        out = self.tmp / "out.png"
        li.stitch(cards, out)

        self.assertEqual(list(self.tmp.glob("*.partial*")), [])

    def test_jpeg_output_is_supported(self):
        cards = [_card(self.tmp / "a.png", (100, 100), (1, 1, 1))]
        out = self.tmp / "out.jpg"
        receipt = li.stitch(cards, out)

        self.assertTrue(out.is_file())
        self.assertEqual(receipt["output"]["width"], 220)

    def test_write_receipt_puts_the_file_under_receipts(self):
        project = self.tmp / "project"
        project.mkdir()
        cards = [_card(self.tmp / "a.png", (100, 100), (1, 1, 1))]
        receipt = li.stitch(cards, self.tmp / "out.png")
        target = li.write_receipt(project, receipt)

        self.assertEqual(target, (project / "receipts" / "long-image.json").resolve())
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), receipt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
