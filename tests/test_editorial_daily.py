#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import editorial_daily as daily


class DailyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.draft = "draft.md"
        (self.root / self.draft).write_text("A real draft for this synthetic test.", encoding="utf-8")
        self.plan = {"queue": [
            dict(id=f"{i:016x}", account="fi", topic="agent", platform="bilibili",
                 format="video", cost_lane="L1", planned_date=day, minutes=mins,
                 decision=decision, score=90-i, evidence_ids=["s1","s2"])
            for i, day, mins, decision in [
                (1,"2026-11-25",20,"CANDIDATE"), (2,"2026-11-26",60,"CANDIDATE"),
                (3,"2026-11-26",10,"LOW_COST_VALIDATION"),
                (4,"2026-11-27",5,"CANDIDATE"), (5,"2026-11-26",5,"NEEDS_EVIDENCE"),
                (6,"2026-11-26",5,"CANDIDATE")]
        ]}
        self.ident = self.plan["queue"][0]["id"]

    def test_budget_and_provenance(self):
        (self.root / ("route-" + self.plan["queue"][5]["id"] + ".json")).touch()
        signals = [dict(signal_id="s1", source_url="https://example.org/a", kind="hotspot"),
                   dict(signal_id="s2", source_url="https://example.org/b", kind="buyer_request")]
        r = daily.capacity(self.root, self.plan, signals, "2026-11-26", 30)
        self.assertEqual(r["allocated_minutes"], 30)
        self.assertEqual(len(r["selected"]), 2)
        self.assertEqual(r["selected"][0]["demand_signal_urls"], 1)
        self.assertTrue(r["selected"][0]["overdue"])
        self.assertEqual({d["reason"] for d in r["deferred"]},
                         {"CAPACITY","FUTURE","NEEDS_EVIDENCE","ALREADY_ROUTED"})
        self.assertFalse(r["publish_authorized"])

    def filled(self):
        r = daily.template(self.root, self.plan, self.ident, self.draft)
        r["reviewer"] = "Synthetic Reviewer"
        for check in r["checks"].values():
            check.update(result="SATISFIED", note="Synthetic review observation")
        return r

    def test_review_and_stale(self):
        r = self.filled()
        r["checks"]["hook"]["result"] = "REVISE"
        out = daily.review(self.root, self.plan, self.ident, self.draft, r)
        self.assertEqual(out["revise_dimensions"], ["hook"])
        self.assertFalse(out["production_ready"])
        (self.root / self.draft).write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "STALE"):
            daily.review(self.root, self.plan, self.ident, self.draft, r)

    def test_no_implicit_approval(self):
        r = self.filled()
        r["publish_authorized"] = True
        with self.assertRaisesRegex(ValueError, "cannot authorize"):
            daily.review(self.root, self.plan, self.ident, self.draft, r)
        r["publish_authorized"] = False
        r["checks"]["hook"]["note"] = ""
        with self.assertRaisesRegex(ValueError, "concrete review note"):
            daily.review(self.root, self.plan, self.ident, self.draft, r)

    def test_path_escape(self):
        with self.assertRaises(ValueError):
            daily.template(self.root, self.plan, self.ident, "../draft.md")


if __name__ == "__main__":
    unittest.main()
