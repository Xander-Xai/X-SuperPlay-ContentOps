"""Policy tests for the A/B/C sample experiment plumbing. Issue #34, narration v2.

Three groups:

1. **Credential binding.** Narration resolution must never borrow the
   pay-as-you-go variable, and the general resolver other callers use must stay
   unchanged. The config-file fallback stays available (it holds the same
   subscription credential the official CLI uses) but is controlled in these
   tests so they neither read nor depend on the running machine's real config.
2. **Budget arithmetic and the sample plan.** The published counting rule and a
   sanity bound on the tracked sample.
3. **Dry run.** The experiment script without ``--execute`` must complete
   offline, transmit nothing and print no credential-shaped value.

No provider interaction exists anywhere in this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run, python_executable  # noqa: E402

import contentops.media.credentials as credentials  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_ABSENT,
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    SOURCE_API_KEY_ENV,
    SOURCE_MMX_CONFIG,
    SOURCE_SUBSCRIPTION_ENV,
    resolve_credential,
    resolve_subscription_credential,
)
from contentops.media.lexicon import default_zh_lexicon  # noqa: E402
from contentops.media.spoken_script import load_spoken_script  # noqa: E402
from contentops.media.t2a_segments import (  # noqa: E402
    estimated_billable_characters,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


SPOKEN_SCRIPT = ROOT / "projects/easel-enhanced-golden/script/narration-spoken.json"


class _NoConfig:
    """Forces the config-file fallback to look empty, whatever this machine has."""

    def __enter__(self):
        self._original = credentials._from_mmx_config
        credentials._from_mmx_config = lambda: ("", credentials.SOURCE_NONE)
        return self

    def __exit__(self, *exc):
        credentials._from_mmx_config = self._original
        return False


class _FakeConfig:
    def __init__(self, value: str):
        self._value = value
        self._original = None

    def __enter__(self):
        self._original = credentials._from_mmx_config
        credentials._from_mmx_config = (
            lambda: (self._value, SOURCE_MMX_CONFIG)
        )
        return self

    def __exit__(self, *exc):
        credentials._from_mmx_config = self._original
        return False


# --- A. credential binding ------------------------------------------------------


@test
def test_narration_resolution_never_borrows_the_payg_variable():
    with _NoConfig():
        payg_only = resolve_subscription_credential(
            env={"MINIMAX_API_KEY": "sk-api-TEST-VALUE-000"}
        )
    assert payg_only.credential_class == CREDENTIAL_ABSENT, (
        "the narration chain must contain no pay-as-you-go fallback; absence is "
        "the correct answer"
    )
    assert not payg_only.usable
    print("[ok] 1. narration resolution refuses the pay-as-you-go fallback")


@test
def test_narration_resolution_prefers_the_subscription_variable():
    resolved = resolve_subscription_credential(
        env={"MINIMAX_SUBSCRIPTION_KEY": "sk-cp-TEST-VALUE-000"}
    )
    assert resolved.credential_class == CREDENTIAL_SUBSCRIPTION
    assert resolved.source == SOURCE_SUBSCRIPTION_ENV
    assert resolved.usable
    print("[ok] 2. MINIMAX_SUBSCRIPTION_KEY is the narration default")


@test
def test_narration_resolution_may_fall_back_to_the_stored_subscription_config():
    with _FakeConfig("sk-cp-CONFIG-TEST-VALUE"):
        resolved = resolve_subscription_credential(env={})
    assert resolved.credential_class == CREDENTIAL_SUBSCRIPTION
    assert resolved.source == SOURCE_MMX_CONFIG
    with _FakeConfig("sk-api-CONFIG-PAYG-TEST"):
        payg_config = resolve_subscription_credential(env={})
    assert payg_config.credential_class == CREDENTIAL_PAYG, (
        "a stored pay-as-you-go key is returned with its class; refusing it is "
        "the M Plan gate's single job, not a second hidden policy here"
    )
    print("[ok] 3. the config fallback is recorded and classified, never payg-preferring")


@test
def test_the_general_resolver_used_by_other_callers_is_unchanged():
    general = resolve_credential(env={"MINIMAX_API_KEY": "sk-api-GENERAL-TEST"})
    assert general.credential_class == CREDENTIAL_PAYG
    assert general.source == SOURCE_API_KEY_ENV
    print("[ok] 4. other callers keep the general resolution order")


# --- B. budget arithmetic -------------------------------------------------------


@test
def test_the_tracked_sample_fits_the_default_budget():
    """Mirror the experiment's B+C estimate so the default budget stays honest."""
    script = load_spoken_script(SPOKEN_SCRIPT)
    lexicon = default_zh_lexicon()
    planned = [lexicon.spoken_text(script.sample_text())]
    planned += [lexicon.spoken_text(spec.text) for spec in script.sample_segments()]
    estimated = estimated_billable_characters(planned)
    assert estimated > 0
    assert estimated < 1500, (
        "the default --budget-chars is 1500; the sample must fit it, and if a "
        "future edit pushes it over, the experiment must be re-budgeted on "
        "purpose rather than silently refused at run time"
    )
    print("[ok] 5. the sample fits the default synthesis budget")


# --- C. dry run -----------------------------------------------------------------


@test
def test_the_experiment_dry_run_completes_offline_and_transmits_nothing():
    result = hidden_run(
        [python_executable(), "scripts/run_ab_sample.py"],
        cwd=str(ROOT),
        timeout=300,
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    out = result.stdout or ""
    assert "DRY RUN. NOTHING WAS SENT." in out
    assert "Bearer " not in out
    assert "sk-cp-" not in out and "sk-api-" not in out
    print("[ok] 6. dry run is offline and prints no credential-shaped value")


@test
def test_new_experiment_scripts_cannot_reach_a_forbidden_route():
    """Static guard: neither script may name a PAYG/clone/file-transfer path."""
    forbidden = (
        "MINIMAX_API_KEY",
        "child_env_for",
        "resolve_cli",
        "voice_clone",
        "/v1/files",
        "/v1/voice_clone",
        "auto_topup",
        "auto_recharge",
    )
    for name in ("run_ab_sample.py", "verify_spoken_script.py"):
        source = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in source, f"{name} references {token}"
    print("[ok] 7. new scripts have no payg, clone or transfer surface")


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
    print(f"\nAll {total} experiment-policy tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
