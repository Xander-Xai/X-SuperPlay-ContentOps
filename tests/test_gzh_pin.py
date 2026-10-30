"""The 公众号 archive pin is only useful if it fails loudly.

The workflow's local history diverged from GitHub origin, so "clone upstream and
compare" — the pattern the Easel runtime verifier uses — cannot check it. The pin
therefore records a cold archive (commit, tree, tracked file count, bundle digest)
and these tests pin the properties that make a restore trustworthy:

- the pin is internally well-formed (a hex digest is not a guess);
- a missing bundle is a named failure, not a silent pass;
- a checkout that is not a repository, or is the wrong commit, is refused;
- the two account names are mapped explicitly rather than assumed equal.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import gzh_pin as pin  # noqa: E402

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


@test
def test_the_pin_is_internally_well_formed():
    data = pin.PIN
    assert len(data["commit"]) == 40 and all(c in "0123456789abcdef" for c in data["commit"])
    assert len(data["tree"]) == 40 and all(c in "0123456789abcdef" for c in data["tree"])
    assert len(data["bundle_sha256"]) == 64
    assert isinstance(data["tracked_files"], int) and data["tracked_files"] > 0
    assert data["diverged_from"]["commit"] != data["commit"], (
        "the pin must not pretend the remote reproduces this history")
    assert pin.ACCOUNT["gzh_account_id"] != pin.ACCOUNT["contentops_account_slug"]
    print("[ok] 1. the pin is well-formed and does not hide the divergence")


@test
def test_a_missing_bundle_is_a_named_failure():
    with tempfile.TemporaryDirectory() as temp:
        result = pin.verify(bundle=Path(temp) / "absent.bundle")
    assert result["ok"] is False
    assert result["failures"] == ["bundle_present"], result["failures"]
    print("[ok] 2. a missing archive is refused by name")


@test
def test_a_wrong_bundle_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        fake = Path(temp) / "fake.bundle"
        fake.write_bytes(b"not a bundle")
        result = pin.verify(bundle=fake)
    assert result["ok"] is False
    assert "bundle_bytes" in result["failures"], result["failures"]
    assert "bundle_digest" in result["failures"], result["failures"]
    print("[ok] 3. a bundle with the wrong size and digest is refused")


@test
def test_a_missing_checkout_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        result = pin.verify(checkout=Path(temp) / "nope",
                            bundle=pin.PIN["bundle"] if pin.PIN["bundle"].is_file() else None)
    # The bundle check is whatever this machine has; the checkout must fail regardless.
    assert "checkout_present" in result["failures"], result["failures"]
    print("[ok] 4. a checkout that does not exist is refused")


@test
def test_a_checkout_that_is_not_a_repository_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        result = pin.verify(checkout=Path(temp))
    assert "checkout_is_repo" in result["failures"], result["failures"]
    print("[ok] 5. a directory that is not a checkout is refused")


@test
def test_the_vendored_digest_catches_an_edit_in_place():
    """The vendored copy is not a checkout, so only its bytes can identify it."""
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "a").mkdir()
        (root / "a" / "one.py").write_text("x = 1\n", encoding="utf-8")
        (root / "b.md").write_text("hello\n", encoding="utf-8")
        count, first = pin.vendored_digest(root)
        assert count == 2, count
        assert len(first) == 64
        assert pin.vendored_digest(root) == (count, first), "the digest is not deterministic"
        (root / "a" / "one.py").write_text("x = 2\n", encoding="utf-8")
        count, second = pin.vendored_digest(root)
        assert count == 2 and second != first, "an edited vendor tree kept the same digest"
    print("[ok] 6. the vendored digest is deterministic and catches an edit")


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
    print(f"All {len(TESTS)} external-pin tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
