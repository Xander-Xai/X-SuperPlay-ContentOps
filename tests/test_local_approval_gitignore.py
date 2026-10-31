"""Local skill-execution records must never reach a public checkout.

The approval record names a real Owner identity; the consumption ledger and the
execution receipts carry request ids and adapter output. All three are written by
the gate under ``projects/<slug>/receipts/``, and none of them belongs in a public
repository. The risk is not a policy violation but an accident: after a real
authorized run they are simply untracked files, one ``git add -A`` away from being
published.

So the narrowness is what gets tested:

- the three local-state paths are ignored, for any project;
- no negation re-includes them;
- every project receipt that is already tracked stays visible and auditable.

``git check-ignore --no-index`` tests the rules themselves rather than the index,
so the suite still means something if one of these files is ever force-added.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_run  # noqa: E402

GITIGNORE = ROOT / ".gitignore"

#: Written by the managed gate; never committed, for any project.
LOCAL_STATE: List[str] = [
    "projects/m5-media-use/receipts/skill-execution-approval.json",
    "projects/m5-media-use/receipts/grants/use-0001.json",
    "projects/m5-media-use/receipts/grants/request-0123456789abcdef.json",
    "projects/m5-media-use/receipts/executions/apr-1-use-0001.json",
    "projects/another-project/receipts/skill-execution-approval.json",
    "projects/another-project/receipts/grants/use-0001.json",
    "projects/another-project/receipts/executions/apr-2-use-0002.json",
]

RULES: List[str] = [
    "projects/*/receipts/skill-execution-approval.json",
    "projects/*/receipts/grants/",
    "projects/*/receipts/executions/",
]

#: A negation for any of these would silently make the local state trackable.
NEGATIONS: List[str] = [
    r"^!\s*projects/\*/receipts/skill-execution-approval\.json\s*$",
    r"^!\s*projects/\*/receipts/grants/?\s*$",
    r"^!\s*projects/\*/receipts/executions/?\s*$",
    r"^!\s*projects/\*\*/receipts/?\s*$",
    r"^!\s*projects/\*/receipts/\*\*?\s*$",
]

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def ignored(rel: str) -> bool:
    out = hidden_run(
        ["git", "check-ignore", "-q", "--no-index", "--", rel],
        cwd=str(ROOT), timeout=60,
    )
    return out.returncode == 0


@test
def test_the_local_execution_state_is_ignored_for_every_project():
    wrong = [rel for rel in LOCAL_STATE if not ignored(rel)]
    assert not wrong, (
        "these local execution records would be committable and published by a "
        f"single `git add -A`: {wrong}"
    )
    print(f"[ok] 1. all {len(LOCAL_STATE)} local execution paths are ignored")


@test
def test_the_three_rules_are_present_verbatim():
    text = GITIGNORE.read_text(encoding="utf-8")
    missing = [
        rule for rule in RULES
        if not re.search(rf"^\s*{re.escape(rule)}\s*$", text, re.MULTILINE)
    ]
    assert not missing, f"the local-state ignore rule(s) are gone: {missing}"
    print("[ok] 2. the three local-state ignore rules are present")


@test
def test_no_negation_reincludes_the_local_state():
    """gitignore is last-match-wins, so one `!` line above the rules undoes them."""
    text = GITIGNORE.read_text(encoding="utf-8")
    present = [
        pattern for pattern in NEGATIONS
        if re.search(pattern, text, re.MULTILINE)
    ]
    assert not present, (
        f"negation(s) re-include local execution state: {present}. The approval, "
        "ledger and receipts must stay local."
    )
    print("[ok] 3. no negation re-includes the local execution state")


@test
def test_tracked_project_receipts_stay_visible():
    """The ignore must not swallow the auditable receipts already in Git."""
    out = hidden_run(
        ["git", "ls-files", "projects"], cwd=str(ROOT), timeout=60,
    )
    tracked = [
        line.strip() for line in out.stdout.splitlines()
        if "/receipts/" in line.strip()
    ]
    assert tracked, "no tracked project receipts found; the check is not testing anything"
    wrong = [rel for rel in tracked if ignored(rel)]
    assert not wrong, (
        "these tracked receipts are now ignored, so the new rules widened past the "
        f"local execution state: {wrong}"
    )
    print(f"[ok] 4. all {len(tracked)} tracked project receipts stay visible")


@test
def test_the_m5_review_record_is_still_tracked_and_trackable():
    """A content review is not an execution approval and must remain auditable."""
    rel = "projects/m5-media-use/receipts/human-review.json"
    assert not ignored(rel), f"{rel} became ignored; content review must stay in Git"
    out = hidden_run(
        ["git", "ls-files", "--error-unmatch", rel], cwd=str(ROOT), timeout=60,
    )
    assert out.returncode == 0, f"{rel} is no longer tracked"
    print("[ok] 5. the M5 human review stays tracked and readable")


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} local-approval gitignore policy tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
