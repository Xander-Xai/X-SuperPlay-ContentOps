"""Regression tests for the host/region audit. Issue #34.

The audit script asks two questions that must never be answered by
configuration hope:

1. Is the host that reads balances the same host that will send the request?
2. Does the credential this repository binds actually reach the provider, or is
   the claim about the credential only a claim?

These tests drive the pure functions with fabricated facts, so CI -- which has
no MiniMax account, no ``~/.mmx`` and no CLI -- still proves the *math* of the
audit: a mismatch is detected, a match is recognised, a moved version is
flagged for re-analysis, and no credential value can leak into the report.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from audit_minimax_host_binding import (  # noqa: E402
    ANALYSED_CLI_VERSION,
    REGION_HOSTS,
    collect_local_facts,
    derive_cli_host,
    evaluate,
)
from contentops.media.minimax_native_tts import MINIMAX_CN_HOST  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def _facts(
    *,
    contentops_base_url=MINIMAX_CN_HOST,
    region="cn",
    cli_version="mmx 1.0.27",
    file_base_url=None,
    has_file_api_key=True,
    has_oauth=False,
):
    return {
        "env": {
            "contentops_base_url": contentops_base_url,
            "voice_clone_base_url": "",
            "has_minimax_api_key_env": False,
            "has_minimax_clone_key_env": True,
        },
        "cli": {"available": True, "version": cli_version, "config_show": {}},
        "mmx_config": {
            "config_present": True,
            "config_readable": True,
            "region": region,
            "file_base_url": file_base_url,
            "has_file_api_key": has_file_api_key,
            "has_oauth": has_oauth,
        },
    }


# --- A. host derivation --------------------------------------------------------


@test
def test_region_cn_derives_the_documented_cn_host():
    derived = derive_cli_host({"region": "cn"})
    assert derived["region"] == "cn"
    assert derived["host"] == MINIMAX_CN_HOST
    assert "region_table" in derived["resolved_from"]
    print("[ok] 1. region cn resolves to the documented CN host")


@test
def test_a_stored_base_url_overrides_the_region_table():
    derived = derive_cli_host({"region": "cn", "file_base_url": "https://stored.example"})
    assert derived["host"] == "https://stored.example"
    assert derived["resolved_from"] == "config.base_url"
    print("[ok] 2. a stored base_url wins over the region table, as the CLI does")


@test
def test_an_unknown_region_falls_back_to_global_like_the_cli():
    derived = derive_cli_host({"region": "mars"})
    assert derived["host"] == REGION_HOSTS["global"]
    print("[ok] 3. an unknown region falls back to the global default")


# --- B. the verdict ------------------------------------------------------------


@test
def test_matched_hosts_pass_and_the_binding_is_still_reported_unverified():
    """Hosts matching is necessary but not sufficient.

    Even with every host equal, the credential-binding question stands on its
    own: the audit must not report a verified binding just because the transport
    looks tidy.
    """
    audit = evaluate(_facts())
    assert audit["HOSTS_MATCH"] is True, audit
    assert audit["BALANCE_QUERY_HOST"] == MINIMAX_CN_HOST
    assert audit["CLI_ACTUAL_HOST"] == MINIMAX_CN_HOST
    assert audit["CREDENTIAL_BINDING_VERIFIED"] is False
    binding = audit["CREDENTIAL_BINDING"]
    assert binding["cli_version_matches_analysis"] is True
    assert binding["cli_honours_env_key_for_auth"] is False
    assert binding["file_api_key_present"] is True
    print("[ok] 4. matched hosts pass; the credential binding stays a separate fact")


@test
def test_a_balance_host_that_differs_from_the_request_host_is_flagged():
    audit = evaluate(_facts(contentops_base_url="https://legacy.example"))
    assert audit["HOSTS_MATCH"] is False
    assert audit["BALANCE_QUERY_HOST"] == "https://legacy.example"
    assert audit["CLI_ACTUAL_HOST"] == MINIMAX_CN_HOST
    joined = " ".join(audit["warnings"])
    assert "different services" in joined or "HOSTS_MATCH" in joined
    print("[ok] 5. a split between balance host and request host is detected")


@test
def test_an_unset_balance_host_is_not_a_match():
    audit = evaluate(_facts(contentops_base_url=""))
    assert audit["HOSTS_MATCH"] is False
    assert audit["BALANCE_QUERY_HOST"] is None
    print("[ok] 6. an unset balance host cannot be a match")


@test
def test_a_cli_version_moved_off_the_analysed_release_is_flagged_for_reanalysis():
    audit = evaluate(_facts(cli_version="mmx 1.0.28"))
    binding = audit["CREDENTIAL_BINDING"]
    assert binding["cli_version_matches_analysis"] is False
    assert binding["cli_honours_env_key_for_auth"] == "REANALYSE"
    assert "re-measured" in binding["why"] or "REANALYSE" in binding["why"]
    assert audit["CREDENTIAL_BINDING_VERIFIED"] is False
    print("[ok] 7. a version move invalidates the resolver finding instead of assuming it")


# --- C. collection never leaks values -----------------------------------------


@test
def test_config_collection_keeps_presence_but_never_the_key_value():
    secret = "sk-cp-TEST-VALUE-MUST-NOT-APPEAR-1234567890"
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / ".mmx").mkdir()
        (home / ".mmx" / "config.json").write_text(
            json.dumps({"region": "cn", "api_key": secret}), encoding="utf-8"
        )

        def fake_run(argv):
            if argv[-1] == "--version":
                return 0, "mmx 1.0.27\n", ""
            return 0, json.dumps({"region": "cn", "api_key": "sk-c...cr3t"}), ""

        facts = collect_local_facts(
            env={"MINIMAX_CLONE_KEY": "sk-api-TEST"},
            home=home,
            run=fake_run,
            cli_prefix=["mmx"],
        )
        blob = json.dumps(facts, ensure_ascii=False)
        assert secret not in blob, "the raw config key must never be collected"
        assert facts["mmx_config"]["has_file_api_key"] is True
        assert facts["mmx_config"]["region"] == "cn"
        assert facts["cli"]["version"] == "mmx 1.0.27"
        # The CLI's own redacted display form must be dropped too.
        assert "sk-c...cr3t" not in blob
        print("[ok] 8. config collection reports presence, never the value")


@test
def test_a_corrupt_config_is_reported_as_unreadable_not_invented():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        (home / ".mmx").mkdir()
        (home / ".mmx" / "config.json").write_text("{not json", encoding="utf-8")

        def fake_run(argv):
            return 1, "", ""

        facts = collect_local_facts(env={}, home=home, run=fake_run, cli_prefix=["mmx"])
        assert facts["mmx_config"]["config_present"] is True
        assert facts["mmx_config"]["config_readable"] is False
        assert "region" not in facts["mmx_config"]
        print("[ok] 9. a corrupt config is unreadable, not guessed at")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    failures = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            print(f"[FAIL] {fn.__name__}: {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {fn.__name__}: {type(exc).__name__}({exc})")
            failures += 1
    total = len(TESTS)
    if failures:
        print(f"\n{failures} of {total} test(s) failed")
        return 1
    print(f"\nAll {total} host-binding audit tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
