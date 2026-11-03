"""The source-quality gate: what it rejects, and what it refuses to reject on.

The gate exists because a keyword match is not a project. These tests pin the
two halves of that claim:

- a repository with no product behind it is rejected, with the signals that
  produced the decision kept on the record;
- no single weak signal — stars, age, or a word in the description — is ever
  enough on its own, and a repository the gate could not inspect passes
  through marked, never dropped.

Run: python tests/test_source_quality.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.hotspots.quality import (  # noqa: E402
    DEFAULT_POLICY,
    QualityPolicy,
    RepoEvidence,
    assess,
    repo_from_url,
)


def _evidence(**overrides) -> RepoEvidence:
    base = dict(full_name="owner/project", description="a real project",
                size_kb=2048, stars=120, forks=12, has_readme=True,
                created_at="2025-01-01T00:00:00Z", fetched=True)
    base.update(overrides)
    return RepoEvidence(**base)


def test_a_real_project_passes():
    verdict = assess(_evidence())
    assert verdict["verdict"] == "ACCEPT"
    assert verdict["signals"] == []
    assert verdict["evidence"]["fetched"] is True


def test_a_test_fixture_repository_is_rejected_with_its_evidence():
    verdict = assess(_evidence(
        full_name="halfsend-06/test-repo-02-mint-host",
        description="behaviour test: mint probe workflow host",
        size_kb=4, has_readme=False))
    assert verdict["verdict"] == "REJECT"
    names = {signal["signal"] for signal in verdict["signals"]}
    assert {"placeholder_name", "placeholder_description",
            "no_readme", "tiny_repository"} <= names
    assert verdict["evidence"]["size_kb"] == 4
    assert verdict["evidence"]["has_readme"] is False


def test_a_placeholder_word_alone_only_marks_for_review():
    """One signal is not a verdict; the reviewer still sees it."""
    verdict = assess(_evidence(description="test-repo for a demo",
                               size_kb=2048, has_readme=True))
    assert verdict["verdict"] == "REVIEW"
    assert len(verdict["signals"]) == 1


def test_a_repository_that_names_itself_a_fixture_twice_is_rejected_offline():
    """Name and description are separate fields, so two matches are two facts."""
    verdict = assess(RepoEvidence(full_name="halfsend-06/test-repo-11-mint-host",
                                  description="behaviour test: mint probe workflow host",
                                  fetched=False))
    assert verdict["verdict"] == "REJECT"
    assert {signal["signal"] for signal in verdict["signals"]} == {
        "placeholder_name", "placeholder_description"}


def test_stars_alone_never_decide():
    """A zero-star repository with a README and real code is not spam."""
    verdict = assess(_evidence(stars=0, forks=0))
    assert verdict["verdict"] == "ACCEPT"


def test_age_alone_never_decides():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    verdict = assess(_evidence(created_at=yesterday, stars=0, forks=0))
    # Young + unproven is one signal, so it is a look-at, not a rejection.
    assert verdict["verdict"] == "REVIEW"
    assert [signal["signal"] for signal in verdict["signals"]] == [
        "young_and_unproven"]


def test_a_new_starred_repository_passes():
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    verdict = assess(_evidence(created_at=yesterday, stars=40))
    assert verdict["verdict"] == "ACCEPT"


def test_an_uninspected_repository_is_never_rejected():
    """A failed API call must not delete a candidate."""
    verdict = assess(_evidence(fetched=False, fetch_error="SOURCE_TIMEOUT"))
    assert verdict["verdict"] == "UNVERIFIED"
    assert "could not be inspected" in verdict["detail"]


def test_the_thresholds_are_policy_not_prejudice():
    """Same evidence, different policy, different verdict — and it says which."""
    fixture = _evidence(full_name="owner/test-repo", size_kb=4, has_readme=False)
    lenient = assess(fixture, QualityPolicy(reject_at_signals=2))
    assert lenient["verdict"] == "REJECT"
    strict = assess(fixture, QualityPolicy(reject_at_signals=4))
    assert strict["verdict"] == "REVIEW"
    assert strict["policy"]["reject_at_signals"] == 4


def test_every_signal_explains_itself():
    verdict = assess(_evidence(full_name="owner/test-repo", size_kb=4,
                               has_readme=False))
    for signal in verdict["signals"]:
        assert signal["why"].strip()
        assert "signal" in signal and "value" in signal


def test_a_github_url_names_a_repository_and_other_urls_do_not():
    assert repo_from_url("https://github.com/IBM/mcp-context-forge") == \
        "IBM/mcp-context-forge"
    assert repo_from_url("https://github.com/IBM/mcp-context-forge/tree/main") == \
        "IBM/mcp-context-forge"
    assert repo_from_url("https://example.test/a/b") is None
    assert repo_from_url("") is None


def test_the_default_policy_states_its_numbers():
    assert DEFAULT_POLICY.reject_at_signals == 2
    assert DEFAULT_POLICY.min_size_kb > 0
    assert DEFAULT_POLICY.to_dict()["min_age_days"] == DEFAULT_POLICY.min_age_days


def test_a_rejection_is_reproducible_from_its_record():
    fixture = _evidence(full_name="halfsend-06/test-repo-02-mint-host",
                        description="behaviour test: mint probe workflow host",
                        size_kb=4, has_readme=False)
    first = assess(fixture)
    second = assess(RepoEvidence(**first["evidence"]))
    assert first["verdict"] == second["verdict"] == "REJECT"
    assert [s["signal"] for s in first["signals"]] == \
        [s["signal"] for s in second["signals"]]


def test_evidence_is_cached_on_disk_across_runs():
    import tempfile
    from contentops.hotspots.quality import GitHubRepoEvidenceFetcher
    calls = []

    def http_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/readme"):
            return b'{"content": "IyBSRUFETUU="}'
        return (b'{"description": "a real project", "size": 4096, '
                b'"stargazers_count": 40, "forks_count": 4, "archived": false, '
                b'"fork": false, "created_at": "2025-01-01T00:00:00Z", '
                b'"pushed_at": "2026-01-01T00:00:00Z", "homepage": "", "topics": []}')

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache.json"
        first = GitHubRepoEvidenceFetcher(http_get, cache_path=cache)
        first.fetch("owner/project")
        assert len(calls) == 2
        second = GitHubRepoEvidenceFetcher(http_get, cache_path=cache)
        evidence = second.fetch("owner/project")
        assert evidence.fetched is True
        assert len(calls) == 2, "a cached repository was fetched again"


def test_a_failed_inspection_is_not_cached():
    import tempfile
    from contentops.hotspots.quality import GitHubRepoEvidenceFetcher
    calls = []

    def http_get(url, **kwargs):
        calls.append(url)
        raise RuntimeError("rate limited")

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache.json"
        fetcher = GitHubRepoEvidenceFetcher(http_get, cache_path=cache)
        evidence = fetcher.fetch("owner/project")
        assert evidence.fetched is False
        assert "rate limited" in evidence.fetch_error
        assert not cache.exists() or "owner/project" not in cache.read_text(encoding="utf-8")


def test_cache_entries_expire():
    import tempfile
    from contentops.hotspots.quality import GitHubRepoEvidenceFetcher
    calls = []

    def http_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/readme"):
            return b"{}"
        return (b'{"description": "x", "size": 4096, "stargazers_count": 1, '
                b'"forks_count": 0, "archived": false, "fork": false, '
                b'"created_at": "2025-01-01T00:00:00Z", "pushed_at": null, '
                b'"homepage": "", "topics": []}')

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache.json"
        now = datetime.now(timezone.utc)
        GitHubRepoEvidenceFetcher(http_get, cache_path=cache, now=now).fetch("o/p")
        before = len(calls)
        later = now + timedelta(hours=200)
        GitHubRepoEvidenceFetcher(http_get, cache_path=cache, ttl_hours=168,
                                  now=later).fetch("o/p")
        assert len(calls) > before, "an expired entry was served from the cache"


def main() -> int:
    tests = tuple(value for name, value in sorted(globals().items())
                  if name.startswith("test_") and callable(value))
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} source-quality tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
