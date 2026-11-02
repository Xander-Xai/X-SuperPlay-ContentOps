"""Platform registry tests: coverage, honesty and public safety.

Status is a claim about evidence. These tests keep the registry from drifting
into a second strategy source, a second platform surface, or a private-data leak.

Run: python tests/test_platform_registry.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.platforms import (  # noqa: E402
    RegistryError,
    account_allows_format,
    load_accounts,
    load_platforms,
    validate_registry,
)

STRATEGY_PLATFORMS = {
    "douyin",
    "xiaohongshu",
    "bilibili",
    "wechat_channels",
    "wechat_official_account",
    "zhihu",
    "csdn",
    "youtube",
    "x",
}

REGISTRY_DIR = ROOT / "config" / "registry"


def _expect(code, fn):
    try:
        fn()
    except RegistryError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected RegistryError {code}, nothing was raised")


def _temp_registry(mutate):
    tmp = Path(tempfile.mkdtemp(prefix="contentops-platform-"))
    target = tmp / "config" / "registry"
    target.mkdir(parents=True)
    for name in ("accounts.json", "platforms.json"):
        (target / name).write_bytes((REGISTRY_DIR / name).read_bytes())
    payload = json.loads((target / "platforms.json").read_text(encoding="utf-8"))
    mutate(payload)
    (target / "platforms.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp


def test_registries_agree():
    assert validate_registry(ROOT) == []


def test_every_strategy_platform_is_represented():
    platforms = load_platforms(ROOT)
    mapped = {entry.strategy_platform for entry in platforms.values()}
    assert mapped == STRATEGY_PLATFORMS, f"missing {STRATEGY_PLATFORMS - mapped}, extra {mapped - STRATEGY_PLATFORMS}"


def test_xiaohongshu_split_maps_to_one_strategy_platform():
    platforms = load_platforms(ROOT)
    xhs = [e for e in platforms.values() if e.strategy_platform == "xiaohongshu"]
    assert len(xhs) == 2, f"expected video and image entries, got {len(xhs)}"
    assert {e.pipeline for e in xhs} == {"VIDEO", "XHS_EDITORIAL"}


def test_platform_ids_are_unique():
    payload = json.loads((REGISTRY_DIR / "platforms.json").read_text(encoding="utf-8"))
    ids = [row["platform_id"] for row in payload["platforms"]]
    assert len(ids) == len(set(ids)), f"duplicate platform_id in {ids}"


def test_github_is_documented_not_registered():
    payload = json.loads((REGISTRY_DIR / "platforms.json").read_text(encoding="utf-8"))
    ids = {row["platform_id"] for row in payload["platforms"]}
    assert "github" not in ids, "GitHub is proof infrastructure, not a publish target"
    assert "github" not in {row["strategy_platform"] for row in payload["platforms"]}


def test_only_x_is_integrated_and_it_carries_evidence():
    platforms = load_platforms(ROOT)
    integrated = [e for e in platforms.values() if e.status != "PLANNED"]
    assert [e.platform_id for e in integrated] == ["x"], (
        f"unexpected non-PLANNED platforms: {[e.platform_id for e in integrated]}")
    for entry in integrated:
        assert entry.evidence, f"{entry.platform_id} is {entry.status} with no evidence"


def test_every_planned_row_names_a_blocker():
    for entry in load_platforms(ROOT).values():
        if entry.status == "PLANNED":
            assert "BLOCKED:" in entry.not_claimed, (
                f"{entry.platform_id} is PLANNED without a BLOCKED reason")


def test_no_row_implies_publication_or_metrics():
    for entry in load_platforms(ROOT).values():
        assert entry.manual_review is True, f"{entry.platform_id} disabled manual review"
        assert entry.publish_mode in {"NOT_IMPLEMENTED", "MANUAL_ONLY", "DRAFT_ONLY"}
        assert entry.metrics in {"NONE", "MANUAL_RECORD", "API"}
        assert entry.status != "PRODUCTION_ACCEPTED", (
            f"{entry.platform_id} claims production acceptance without a published receipt")
        if entry.status != "PLANNED":
            assert entry.publish_mode != "NOT_IMPLEMENTED", (
                f"{entry.platform_id} is {entry.status} but claims no publish path")


def test_planned_format_is_not_available():
    _expect("CONTENT_FORMAT_NOT_ALLOWED",
            lambda: account_allows_format(ROOT, "x-superplay-english", "VIDEO"))


def test_accounts_referenced_exist():
    accounts = load_accounts(ROOT)
    for entry in load_platforms(ROOT).values():
        for slug in entry.accounts:
            assert slug in accounts, f"{entry.platform_id} names unknown account {slug}"


def test_strategy_platform_is_required():
    def drop_mapping(payload):
        payload["platforms"][0].pop("strategy_platform")

    tmp = _temp_registry(drop_mapping)
    _expect("PLATFORM_FIELD_INVALID", lambda: load_platforms(tmp))


def test_status_cannot_be_raised_without_evidence():
    def promote_without_evidence(payload):
        for row in payload["platforms"]:
            if row["platform_id"] == "douyin":
                row["status"] = "INTEGRATED"
                row["accounts"] = ["x-superplay-english"]
                row["publish_mode"] = "MANUAL_ONLY"
                row["evidence"] = []

    tmp = _temp_registry(promote_without_evidence)
    _expect("PLATFORM_EVIDENCE_MISSING", lambda: load_platforms(tmp))


def test_production_acceptance_requires_a_project_receipt():
    def accept_without_receipt(payload):
        for row in payload["platforms"]:
            if row["platform_id"] == "x":
                row["status"] = "PRODUCTION_ACCEPTED"
                row["evidence"] = ["tests/test_x_post.py"]

    tmp = _temp_registry(accept_without_receipt)
    _expect("PLATFORM_EVIDENCE_MISSING", lambda: load_platforms(tmp))


def test_unknown_account_is_refused():
    def add_unknown(payload):
        for row in payload["platforms"]:
            if row["platform_id"] == "x":
                row["accounts"] = ["no-such-account"]

    tmp = _temp_registry(add_unknown)
    _expect("PLATFORM_ACCOUNT_UNKNOWN", lambda: load_platforms(tmp))


def test_registry_carries_no_private_repository_fields():
    text = (REGISTRY_DIR / "platforms.json").read_text(encoding="utf-8")
    text += (REGISTRY_DIR / "accounts.json").read_text(encoding="utf-8")
    for marker in ("Xander-Xai/", "token", "cookie", "password", "api_key"):
        assert marker.lower() not in text.lower(), f"registry contains {marker!r}"


def test_registry_names_no_private_account_identity():
    accounts = load_accounts(ROOT)
    assert set(accounts) == {"x-superplay-english"}, (
        "only the account configuration tracked in this public repository may be named")


def main() -> int:
    tests = (
        test_registries_agree,
        test_every_strategy_platform_is_represented,
        test_xiaohongshu_split_maps_to_one_strategy_platform,
        test_platform_ids_are_unique,
        test_github_is_documented_not_registered,
        test_only_x_is_integrated_and_it_carries_evidence,
        test_every_planned_row_names_a_blocker,
        test_no_row_implies_publication_or_metrics,
        test_planned_format_is_not_available,
        test_accounts_referenced_exist,
        test_strategy_platform_is_required,
        test_status_cannot_be_raised_without_evidence,
        test_production_acceptance_requires_a_project_receipt,
        test_unknown_account_is_refused,
        test_registry_carries_no_private_repository_fields,
        test_registry_names_no_private_account_identity,
    )
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
    print("\nAll platform registry tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
