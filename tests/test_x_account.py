"""The X account is a different kind of document, and must fail as one.

The risk this suite covers is not "does the X file parse" -- it is that an X
account silently inherits video rules it can never satisfy, or that a video-only
producer tries to read it and invents facts. So it asserts the boundaries in
both directions:

- the schema dispatch names the two known schemas and refuses a third;
- the X checker passes on the shipped document and names the blockers when they
  are present (no image enum, an API publisher, an SVG-only image, a score floor
  above the rubric);
- the video readers never see the X account;
- the one prompt this slice ships is real and names every X field.

Skill-catalog resolution is deliberately absent: that is the Skill Router's job
and it is BLOCKED_UPSTREAM for this branch.

Run: python tests/test_x_account.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import (  # noqa: E402
    VIDEO_SCHEMA,
    X_SCHEMA,
    account_kind,
    iter_accounts,
    video_accounts,
)
from contentops.publish.x_account import (  # noqa: E402
    X_REQUIRED_PROMPT_FIELDS,
    check_prompt,
    check_x_account,
)

ACCOUNTS = ROOT / "config" / "accounts"
X_PATH = ACCOUNTS / "x-superplay-english.json"

TESTS: list = []


def test(fn):
    TESTS.append(fn)
    return fn


def _x() -> dict:
    return json.loads(X_PATH.read_text(encoding="utf-8"))


def _mutated(**changes) -> dict:
    dna = copy.deepcopy(_x())
    for dotted, value in changes.items():
        node = dna
        parts = dotted.split("__")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = value
    return dna


def _failures(dna: dict) -> list:
    return check_x_account(dna, ROOT)


def _assert_fails(dna: dict, needle: str) -> None:
    failures = _failures(dna)
    assert any(needle in failure for failure in failures), (needle, failures)


@test
def test_every_account_declares_exactly_one_known_schema():
    kinds = {}
    for path, dna in iter_accounts(root=ROOT):
        kind = account_kind(dna)
        assert kind != "unknown", f"{path.name} declares an unowned schema {dna.get('schema')!r}"
        kinds[path.name] = kind
    assert kinds == {"x-superplay-english.json": "x"}, kinds
    print("[ok] 1. every account declares exactly one known schema")


@test
def test_an_unowned_schema_is_unknown_not_guessed():
    assert account_kind({"schema": VIDEO_SCHEMA}) == "video"
    assert account_kind({"schema": X_SCHEMA}) == "x"
    assert account_kind({"schema": "contentops.account-dna/v1"}) == "unknown"
    assert account_kind({}) == "unknown"
    print("[ok] 2. an unowned schema is reported as unknown, never guessed")


@test
def test_the_video_readers_never_see_the_x_account():
    assert list(video_accounts(root=ROOT)) == []
    print("[ok] 3. no video reader sees the X account")


@test
def test_the_x_account_carries_no_video_keys():
    dna = _x()
    for key in ("narrative", "render", "qc_rules", "audio", "retention"):
        assert key not in dna, f"the X account declares the video key {key!r}"
    print("[ok] 4. the X account declares no video-only key")


@test
def test_the_shipped_x_account_passes_its_own_checker():
    warnings: list = []
    failures = check_x_account(_x(), ROOT, warnings)
    assert failures == [], failures
    assert warnings == [], warnings
    print("[ok] 5. the shipped X account passes the X checker")


@test
def test_a_manual_only_account_may_not_declare_an_api_publisher():
    dna = _mutated(publication__mode="API", publication__api="implemented")
    _assert_fails(dna, "only MANUAL_ONLY is implemented")
    _assert_fails(dna, "declaring an implemented API")
    print("[ok] 6. a claimed API publisher fails until a capability spike exists")


@test
def test_an_svg_alone_or_an_off_ratio_canvas_is_refused():
    _assert_fails(_mutated(visual__svg_alone=True), "not uploadable to X")
    _assert_fails(_mutated(visual__width=1080), "is not 16:9")
    _assert_fails(_mutated(visual__formats=["png", "svg"]), "will not accept")
    print("[ok] 7. an SVG-only or non-16:9 image is refused")


@test
def test_the_score_floor_must_fit_the_rubric():
    _assert_fails(_mutated(editorial__score_floor=31), "against a 30-point rubric")
    _assert_fails(_mutated(editorial__score_floor=0), "against a 30-point rubric")
    print("[ok] 8. the score floor must sit inside the rubric it scores")


@test
def test_the_published_enum_and_the_recovery_fields_are_the_contracts():
    _assert_fails(_mutated(publication__post_status_enum=["draft", "live"]),
                  "post_status_enum")
    _assert_fails(_mutated(editorial__recovery_fields=["audience_job"]),
                  "recovery_fields is missing")
    _assert_fails(_mutated(editorial__source_analysis_label=""),
                  "source_analysis_label is empty")
    print("[ok] 9. the status enum and the recovery fields are the contract, not a paraphrase")


@test
def test_an_unknown_handle_is_unknown_and_not_a_guess():
    _assert_fails(_mutated(publication__handle="superplay"), "recorded from a real status URL")
    assert check_x_account(_mutated(publication__handle="superplay",
                                    publication__handle_status="RECORDED_FROM_URL"),
                           ROOT, []) == []
    print("[ok] 10. an unset handle must be UNKNOWN; a recorded one is allowed")


@test
def test_the_prompt_must_name_every_x_field_and_the_brand_colours():
    dna = _x()
    palette = dna["brand"]["palette"]
    failures = check_prompt(dna, palette, ROOT, X_REQUIRED_PROMPT_FIELDS)
    assert failures == [], failures

    original = (ROOT / dna["prompt"]).read_text(encoding="utf-8")
    assert "status_url" in original
    assert "#38BDF8" in original
    print("[ok] 11. the X prompt names every X field, the account and the brand colours")


@test
def test_a_prompt_that_is_not_in_this_tree_is_refused():
    _assert_fails(_mutated(prompt="config/accounts/prompts/absent.md"),
                  "does not exist")
    _assert_fails(_mutated(editorial__prompts={"post_brief": "vendor/absent.md"}),
                  "not a file in this tree")
    print("[ok] 12. a missing prompt file is refused by both checks")


@test
def test_the_vendor_prompts_are_declared_unavailable_not_copied():
    dna = _x()
    assert set(dna["editorial"]["prompts"]) == {"post_brief"}
    missing = dna["editorial"]["unavailable_prompts"]
    assert set(missing) == {"daily_post", "github_url", "x_signal", "tutorial",
                            "visual_brief"}
    for path in missing.values():
        assert not (ROOT / path).exists(), \
            f"{path} must not be copied into this slice"
    print("[ok] 13. the vendor prompts are recorded as unavailable, not copied")


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
    print(f"All {len(TESTS)} X account tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
