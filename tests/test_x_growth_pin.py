"""The X growth workflow's pin is only useful if it fails loudly.

`vendor/x-growth-os/` is an imported copy, not a checkout. The pin records the
commit, tree, file count, byte count and a content digest, and these tests pin
the properties that make that record worth trusting:

- the pin is internally well-formed (a hex digest is not a guess);
- the vendored tree on disk still matches it;
- our own `MANIFEST.md` is not part of the digest, so editing our notes is not an
  edit to vendored code;
- a missing tree, a credential-shaped file, an oversized binary and a checkout at
  the wrong commit are all named failures, never silent passes.
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

import x_growth_pin as pin  # noqa: E402
from process_utils import hidden_run  # noqa: E402

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def _hex(value: str) -> bool:
    return bool(value) and all(c in "0123456789abcdef" for c in value)


def _fixture(base: Path, files: dict[str, bytes]) -> Path:
    for rel, data in files.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return base


@test
def test_the_pin_is_internally_well_formed():
    data = pin.PIN
    assert len(data["commit"]) == 40 and _hex(data["commit"]), "commit is not 40 hex chars"
    assert len(data["tree"]) == 40 and _hex(data["tree"]), "tree is not 40 hex chars"
    assert len(pin.VENDORED_DIGEST) == 64 and _hex(pin.VENDORED_DIGEST), "digest is not 64 hex chars"
    assert data["tracked_files"] > 0 and data["total_bytes"] > 0, "counts must be positive"
    assert data["access"] == "private", "a private repository must be recorded as private"
    assert data["license"] == "ABSENT", "the source declares no license; that is the fact"
    assert data["repo"].startswith("https://github.com/"), "repo must be a full URL"
    print("[ok] 1. the pin is internally well-formed")


@test
def test_the_vendored_tree_matches_the_pin():
    result = pin.verify()
    assert result["ok"], f"vendored tree does not match the pin: {result['failures']}"
    print("[ok] 2. the vendored tree on disk matches files, bytes and digest")


@test
def test_a_missing_vendored_tree_is_a_named_failure():
    with tempfile.TemporaryDirectory() as temp:
        result = pin.verify(vendored=Path(temp) / "absent")
    assert result["failures"] == ["vendored_present"], result["failures"]
    print("[ok] 3. a missing vendored tree fails as vendored_present")


@test
def test_the_manifest_is_outside_the_digest():
    with tempfile.TemporaryDirectory() as temp:
        root = _fixture(Path(temp), {"docs/a.md": b"one\n", "posts/b.md": b"two\n"})
        before = pin.vendored_digest(root)
        (root / pin.MANIFEST_NAME).write_text("our provenance notes\n", encoding="utf-8")
        after = pin.vendored_digest(root)
        assert before == after, "MANIFEST.md changed the vendored digest"
        assert pin.vendored_digest(root, frozenset()) != before, (
            "without the exclusion MANIFEST.md must be counted, or the exclusion is untested")
    print("[ok] 4. MANIFEST.md is excluded from the digest and only it")


@test
def test_an_edited_file_changes_the_digest():
    with tempfile.TemporaryDirectory() as temp:
        root = _fixture(Path(temp), {"docs/a.md": b"one\n", "posts/b.md": b"two\n"})
        count_before, bytes_before, digest_before = pin.vendored_digest(root)
        (root / "posts" / "b.md").write_bytes(b"two!\n")
        count_after, bytes_after, digest_after = pin.vendored_digest(root)
    assert count_before == count_after, "an edit must not change the file count"
    assert bytes_before != bytes_after, "the byte count did not move with the edit"
    assert digest_before != digest_after, "an edited vendored file kept the same digest"
    print("[ok] 5. an edit that preserves the file count still changes bytes and digest")


@test
def test_a_credential_shaped_file_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        _fixture(Path(temp), {"docs/a.md": b"one\n", ".env": b"TOKEN=x\n"})
        result = pin.verify(vendored=Path(temp))
    assert "credential_shape" in result["failures"], result["failures"]
    print("[ok] 6. a credential-shaped file is a named failure")


@test
def test_an_oversized_file_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "big.bin").write_bytes(b"\0" * (pin.MAX_FILE_BYTES + 1))
        result = pin.verify(vendored=root)
    assert "oversize_file" in result["failures"], result["failures"]
    print("[ok] 7. a file over the repository's size limit is a named failure")


@test
def test_a_checkout_at_the_wrong_commit_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        checkout = Path(temp)
        hidden_run(["git", "init", "-q", str(checkout)], check=True)
        hidden_run(["git", "-C", str(checkout), "-c", "user.email=a@b", "-c", "user.name=a",
                    "commit", "-q", "--allow-empty", "-m", "not the pin"], check=True)
        result = pin.verify(checkout=checkout)
    assert "commit" in result["failures"], result["failures"]
    assert result["ok"] is False
    print("[ok] 8. a checkout at another commit fails by name")


@test
def test_a_missing_or_non_repository_checkout_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        missing = pin.verify(checkout=base / "absent")
        assert missing["failures"] == ["checkout_present"], missing["failures"]
        (base / "plain").mkdir()
        not_repo = pin.verify(checkout=base / "plain")
        assert not_repo["failures"] == ["checkout_is_repo"], not_repo["failures"]
    print("[ok] 9. a missing checkout and a non-repository are distinct failures")


@test
def test_the_vendored_suite_flag_reports_pass_and_failure():
    passing = "import unittest\nclass T(unittest.TestCase):\n    def test(self):\n        self.assertTrue(True)\n"
    failing = "import unittest\nclass T(unittest.TestCase):\n    def test(self):\n        self.fail('boom')\n"
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        (base / "tests").mkdir()
        (base / "tests" / "test_ok.py").write_text(passing, encoding="utf-8")
        ok = pin.run_vendored_suite(base)
        (base / "tests" / "test_ok.py").write_text(failing, encoding="utf-8")
        bad = pin.run_vendored_suite(base)
    assert ok["ok"] is True and ok["returncode"] == 0, ok["output"]
    assert bad["ok"] is False and bad["returncode"] != 0, bad["output"]
    assert "boom" in bad["output"], "a failing vendored test must surface its output"
    print("[ok] 10. --suite passes a green tree and reports a red one with its output")


@test
def test_the_digest_uses_a_case_sensitive_posix_order():
    """The same bytes must hash the same way on Windows and on Ubuntu.

    `sorted(Path)` compares case-insensitively on Windows and case-sensitively
    on POSIX, so `README.md` and `assets/` swap places and the two platforms
    disagree on a digest of identical content. Pinning the order explicitly is
    what makes the value portable.
    """
    import hashlib

    with tempfile.TemporaryDirectory() as temp:
        root = _fixture(
            Path(temp),
            {
                "README.md": b"readme\n",
                "CHANGELOG.md": b"changes\n",
                "assets/a.svg": b"<svg/>\n",
                "docs/b.md": b"doc\n",
            },
        )
        canonical = ["CHANGELOG.md", "README.md", "assets/a.svg", "docs/b.md"]
        order = [p.relative_to(root).as_posix() for p in pin._vendored_files(root, frozenset())]
        assert order == canonical, order

        expected = hashlib.sha256()
        for rel in canonical:
            body = hashlib.sha256((root / rel).read_bytes()).hexdigest()
            expected.update(rel.encode("utf-8") + b"\0" + body.encode("ascii") + b"\n")
        count, _, digest = pin.vendored_digest(root, frozenset())
    assert count == 4
    assert digest == expected.hexdigest(), "the digest did not follow the canonical order"
    print("[ok] 11. the digest orders files by case-sensitive POSIX path")


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
