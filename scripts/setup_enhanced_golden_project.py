"""Scaffold the Enhanced Golden experiment root.

Creates the directory layout and the neutral review placeholder. Deliberately does
**not** copy or modify `projects/easel-review/` — the historical baseline is a record
of what was actually rendered, and editing it in place would destroy the only
reference the audit could check the candidates against.

No asset is fetched, generated or substituted here. The baseline audit decides
whether real media may be acquired at all, and that decision is recorded separately
in `receipts/baseline-reproducibility.json`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from contentops.golden.identity import compare_evidence_identity  # noqa: E402
from contentops.golden.review import (  # noqa: E402
    PENDING,
    FounderReview,
    render_review_markdown,
)
from contentops.golden.variant import VARIANT_IDS  # noqa: E402

EXPERIMENT = ROOT / "projects" / "easel-enhanced-golden"

#: Created empty. Media binaries are gitignored; the receipts are not.
LAYOUT = (
    "baseline",
    "evidence",
    "enhancements",
    "review",
    "receipts",
    *(f"variants/{variant}" for variant in VARIANT_IDS),
)


def main() -> int:
    for relative in LAYOUT:
        (EXPERIMENT / relative).mkdir(parents=True, exist_ok=True)
    for relative in ("assets/voice", "assets/voice_baseline", "assets/generated",
                     "assets/support", "final"):
        (EXPERIMENT / relative).mkdir(parents=True, exist_ok=True)

    # A placeholder package so the shape of the review exists before there is
    # anything to review. It states that no review has happened.
    review = FounderReview(
        variant_ids=list(VARIANT_IDS),
        variant_receipts={arm: {"variant_id": arm} for arm in VARIANT_IDS},
        evidence_identity=compare_evidence_identity.__doc__ and {
            "verdict": "NOT_RUN",
            "all_identical": None,
            "placements_compared": 0,
            "mismatches": [],
            "note": (
                "No A/B/C/D builds exist yet, so cross-arm evidence identity has not "
                "been compared. It must read EXPERIMENT_VALID before a Founder review "
                "package is worth preparing."
            ),
        },
        artifacts={arm: f"project://variants/{arm}/final.mp4" for arm in VARIANT_IDS},
        notes={
            "status": PENDING,
            "blocked_by": (
                "Baseline sources are not in Git; see "
                "receipts/baseline-reproducibility.json"
            ),
        },
    )
    (EXPERIMENT / "review").mkdir(parents=True, exist_ok=True)
    review.write(EXPERIMENT / "review" / "founder-review.json")
    (EXPERIMENT / "review" / "founder-review.md").write_text(
        render_review_markdown(review), encoding="utf-8"
    )

    print(f"experiment root : repo://projects/easel-enhanced-golden")
    for relative in sorted(LAYOUT):
        print(f"  {relative}/")
    print()
    print("review package  : repo://projects/easel-enhanced-golden/review/founder-review.json")
    print("                 repo://projects/easel-enhanced-golden/review/founder-review.md")
    print()
    print("No asset was created, copied, fetched or generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
