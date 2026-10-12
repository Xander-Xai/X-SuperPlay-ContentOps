"""M2.2 two-key clone-route regression tests. No provider call, no spend, no key.

What is under test
------------------
The commercial route for #34: which credential may create the clone, which may speak
with it, when the CNY 9.90 is actually charged, and what has to be true before any
of it runs. :mod:`contentops.media.clone_route` answers those questions with no I/O,
so every test here is pure policy.

The failure each test exists to prevent
---------------------------------------
A. **Wrong key, right code.** A PAYG key admitted where a Subscription Key is
   required, or vice versa, because the check looked at the key's prefix instead of
   the declared intent. Both directions bill a different pot.
B. **Silent fallback.** ``MINIMAX_CLONE_KEY`` missing, quietly inherited from the
   Subscription Key resolver's fallback chain. That is the exact configuration that
   would repeat the refused 2061 request.
C. **One key wearing two names.** Both resolvers returning the same secret, so the
   two-key route collapses to the single-key route that was already refused.
D. **Partial fix read as complete.** Provisioning a PAYG key clearing the route while
   the payment contradiction is still open. So the decision lists every blocker, not
   just the first.
E. **The 168-hour clone lifetime.** Cloned voices are temporary. Treating the clone as
   a durable asset means discovering the window closed after the fee was already
   authorised.
F. **A claim outrunning its evidence.** ``CROSS_KEY_TTS_VERIFIED`` being derivable
   from a passing ``get_voice`` listing, which proves visibility and not usability.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import clone_route as route  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_ABSENT,
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    CLONE_CREDENTIAL_ENV,
    DuplicateCredentialError,
    ResolvedCredential,
    TwoKeyPair,
    load_local_env_file,
    resolve_clone_credential,
    resolve_two_key_pair,
)
from contentops.media import minimax_voice_clone as vc  # noqa: E402

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


PAY_GATE = "SAFE_INCLUDED_PLAN"

#: The activation utterance, mirroring the one the preflight script uses.
ACTIVATION_TEXT = "这是一段用于首次激活的最短自然中文语音样本。"


def _pair(clone_key: str = "", tts_key: str = "sk-cp-subscription") -> TwoKeyPair:
    def resolve(key: str, source: str) -> ResolvedCredential:
        from contentops.media.credentials import classify_credential

        return ResolvedCredential(
            key=key, credential_class=classify_credential(key), source=source
        )

    return TwoKeyPair(clone=resolve(clone_key, "TEST"), tts=resolve(tts_key, "TEST"))


def _cost(**flags: Any) -> route.ActivationCost:
    """A realistic activation cost: 44 billable characters, nothing authorised."""
    return route.ActivationCost.for_text(ACTIVATION_TEXT, **flags)


def _decide(pair: TwoKeyPair, **kwargs: Any) -> route.RouteDecision:
    params: Dict[str, Any] = {
        "billing_verdict": PAY_GATE,
        "billing_reasons": [],
        "account_verified": True,
        "cross_key_verified": True,
        "activation_cost": _cost(),
    }
    params.update(kwargs)
    return route.decide_route(pair, **params)


# --- A. the clone credential is a declared intent, not an inferred prefix --------


@test
def test_the_clone_key_never_inherits_the_subscription_resolver_fallback_chain():
    """The clone key has exactly one source, and that source is the clone variable.

    :func:`resolve_credential` walks Subscription Key -> API Key -> ~/.mmx/config.json.
    That is right for TTS and fatal here: inheriting it means a machine with only a
    Subscription Key "resolves" a clone credential, and the clone is sent on the plan
    that already refused it with 2061.
    """
    env = {
        "MINIMAX_SUBSCRIPTION_KEY": "sk-cp-subscription",
        "MINIMAX_API_KEY": "sk-api-payg",
    }
    clone = resolve_clone_credential(env)
    assert not clone.usable, (
        "MINIMAX_CLONE_KEY was absent yet a credential resolved: "
        f"{clone.credential_class} from {clone.source}"
    )
    assert clone.credential_class == CREDENTIAL_ABSENT

    # And with the clone variable set, that variable wins and nothing else is read.
    env[CLONE_CREDENTIAL_ENV] = "sk-api-clone"
    clone = resolve_clone_credential(env)
    assert clone.usable and clone.credential_class == CREDENTIAL_PAYG
    assert clone.source == "MINIMAX_CLONE_KEY_ENV"
    print("[ok] 1. the clone key resolves only from MINIMAX_CLONE_KEY, never by fallback")


@test
def test_a_payg_credential_cannot_clone_unless_the_intent_was_declared():
    """Prefix family is not consent to spend.

    The default provider requires SUBSCRIPTION. A PAYG key is refused with no upload,
    which is the current measured state of the world. Only ``allow_payg_clone=True``
    admits it, so having a PAYG key lying around never quietly creates a billable path.
    """

    class _Transport:
        def upload(self, path, facts):
            raise AssertionError("must not upload")

        def clone(self, payload):
            raise AssertionError("must not clone")

    payg = ResolvedCredential(
        key="sk-api-payg", credential_class=CREDENTIAL_PAYG, source="TEST"
    )
    strict = vc.MiniMaxVoiceCloneProvider(
        credential=payg, base_url="https://example.invalid", transport=_Transport()
    )
    assert strict._required_credential_class == CREDENTIAL_SUBSCRIPTION
    try:
        strict.preflight(
            vc.VoiceCloneRequest(
                voice_alias="founder_primary_v1",
                provider_voice_id="XSuperPlayFounderV1",
                objective="speech-2.8-hd narration",
            )
        )
        raise AssertionError("a PAYG key must be refused by default")
    except vc.CloneRefusal as refusal:
        assert refusal.code == vc.REFUSAL_CREDENTIAL_CLASS, refusal.code
        assert "SUBSCRIPTION only" in refusal.detail, refusal.detail
    assert strict.upload_count == 0

    # Declared intent flips the requirement, and flips it to PAYG-only: the
    # subscription key is then the one that is refused, with the flag named so the
    # operator knows the other lever exists.
    declared = vc.MiniMaxVoiceCloneProvider(
        credential=payg,
        base_url="https://example.invalid",
        transport=_Transport(),
        allow_payg_clone=True,
    )
    assert declared._required_credential_class == CREDENTIAL_PAYG
    sub = ResolvedCredential(
        key="sk-cp-sub", credential_class=CREDENTIAL_SUBSCRIPTION, source="TEST"
    )
    swapped = vc.MiniMaxVoiceCloneProvider(
        credential=sub,
        base_url="https://example.invalid",
        transport=_Transport(),
        allow_payg_clone=True,
    )
    try:
        swapped.preflight(
            vc.VoiceCloneRequest(
                voice_alias="founder_primary_v1",
                provider_voice_id="XSuperPlayFounderV1",
                objective="speech-2.8-hd narration",
            )
        )
        raise AssertionError("a Subscription Key must be refused when PAYG is required")
    except vc.CloneRefusal as refusal:
        assert refusal.code == vc.REFUSAL_CREDENTIAL_CLASS, refusal.code
        assert "allow_payg_clone=True" in refusal.detail, refusal.detail
    print("[ok] 2. PAYG/Subscription admission is a declared argument, never a prefix")


@test
def test_the_payg_key_is_never_accepted_for_synthesis_policy():
    """Admitting a PAYG key for the clone must not loosen the TTS policy.

    The clone is one bounded, authorised CNY 9.90 event. PAYG TTS is an open-ended
    metered bill with no ceiling anywhere in the codebase. They are separate decisions
    and the second one stays refused.
    """
    assert vc.ALLOW_PAYG_TTS is False
    assert vc.ALLOW_CREDIT_PACK_TTS is False
    assert vc.TTS_BILLING_POLICY == "M_PLAN_SUBSCRIPTION"

    decision = _decide(_pair(clone_key="sk-api-clone", tts_key="sk-api-payg-for-tts"))
    assert not decision.authorised
    assert route.ROUTE_SUBSCRIPTION_BILLING_UNPROVEN in decision.blocked_by
    joined = " ".join(decision.reasons)
    assert "PAYG TTS is forbidden" in joined, joined
    print("[ok] 3. a PAYG TTS key stays refused even when PAYG clone is authorised")


# --- B/C. configuration degeneracy must fail loudly ---------------------------


@test
def test_two_identical_keys_are_refused_rather_than_treated_as_a_route():
    """A two-key route running on one key is a single-key route wearing a name."""
    env = {
        CLONE_CREDENTIAL_ENV: "sk-api-same",
        "MINIMAX_SUBSCRIPTION_KEY": "sk-api-same",
    }
    try:
        resolve_two_key_pair(env)
        raise AssertionError("identical route keys must be refused")
    except DuplicateCredentialError:
        pass

    # And a pair that is fine reports itself as distinct without leaking either value.
    pair = resolve_two_key_pair(
        {CLONE_CREDENTIAL_ENV: "sk-api-clone", "MINIMAX_SUBSCRIPTION_KEY": "sk-cp-sub"}
    )
    meta = pair.safe_metadata()
    assert meta["keys_distinct"] is True
    blob = str(meta)
    assert "sk-api-clone" not in blob and "sk-cp-sub" not in blob, blob
    print("[ok] 4. duplicate route keys are refused; a valid pair reports distinct safely")


@test
def test_an_absent_clone_key_is_reported_as_a_provisioning_action_not_a_design_failure():
    """The most likely state is the un-provisioned one, and it has its own code.

    ``CLONE_KEY_REQUIRED`` must not be conflated with the payment contradiction. One
    is fixed by a human creating a key; the other is not fixable by the operator at
    all. An operator who provisions the key and sees the same code again would
    reasonably conclude the key was wrong.
    """
    decision = _decide(_pair(clone_key=""))
    assert route.ROUTE_CLONE_KEY_REQUIRED in decision.blocked_by
    assert decision.route == route.ROUTE_CLONE_KEY_REQUIRED
    assert "MINIMAX_CLONE_KEY" in " ".join(decision.reasons)
    assert "接口密钥" in " ".join(decision.reasons), (
        "the reason must name the official console location, not just the variable"
    )
    print("[ok] 5. a missing clone key is its own stop code with a console location")


# --- D. every blocker, not the first one --------------------------------------


@test
def test_provisioning_the_clone_key_does_not_clear_the_payment_and_billing_gates():
    """The decisive trap: fixing the easy blocker must not look like a working route.

    An earlier revision concluded the payment route was *impossible*, from the published
    rules alone. The Founder has since obtained account-level vendor confirmation that
    the fee is collected at first activation and that an activated voice may then be
    used with M Plan -- so the route is no longer PROVEN_IMPOSSIBLE. But it is also not
    VERIFIED, and provisioning a key does not make it either. The remaining gates are
    a cash balance that cannot pay and a character fee nobody authorised.
    """
    before = _decide(_pair(clone_key=""))
    after = _decide(
        _pair(clone_key="sk-api-clone"),
        cash_balance=50.0,
        first_activation_authorised=True,
        activation_cost=_cost(
            first_activation_authorised=True,
            activation_character_authorised=True,
        ),
    )
    assert route.ROUTE_CLONE_KEY_REQUIRED in before.blocked_by
    assert route.ROUTE_CLONE_KEY_REQUIRED not in after.blocked_by
    assert route.ROUTE_ACTIVATION_CASH_INSUFFICIENT not in after.blocked_by, (
        "with cash available the payment route must be clear, not blocked on a "
        "contradiction that vendor confirmation resolved"
    )
    assert route.ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED not in after.blocked_by
    assert after.authorised, after.blocked_by

    # And provisioning a key alone, with the money undecided, still refuses.
    partial = _decide(_pair(clone_key="sk-api-clone"), cash_balance=50.0)
    assert not partial.authorised
    assert route.ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED in partial.blocked_by, (
        "a separate character charge still needs its own decision"
    )
    print("[ok] 6. a provisioned clone key clears the key gate but not the money gates")


@test
def test_a_zero_cash_balance_blocks_an_authorised_fee_from_being_charged():
    """An approved CNY 9.90 is not payable money.

    Only a pay-as-you-go key deducts account balance, and ``cash_balance`` is 0.00 on
    this account. Voucher (15.00) and Credit Pack are both forbidden to use
    automatically, so the charge has no source. Recording the fee as authorised while
    the balance is empty is how a run ends up attempting a charge that answers 1008 --
    or worse, quietly reaching for a pot it was told not to touch.
    """
    decision = _decide(
        _pair(clone_key="sk-api-clone"),
        cash_balance=0.0,
        first_activation_authorised=True,
    )
    assert route.ROUTE_ACTIVATION_CASH_INSUFFICIENT in decision.blocked_by
    joined = " ".join(decision.reasons)
    assert "cash_balance is 0.00" in joined, joined
    assert "forbidden" in joined, joined

    # Funded cash clears this gate and nothing else.
    funded = _decide(
        _pair(clone_key="sk-api-clone"),
        cash_balance=20.0,
        first_activation_authorised=True,
    )
    assert route.ROUTE_ACTIVATION_CASH_INSUFFICIENT not in funded.blocked_by
    print("[ok] 7. an authorised fee with an empty balance still fails closed")


@test
def test_the_activation_character_fee_is_never_written_as_zero():
    """The small number is the dangerous one.

    The activation synthesis is an ordinary billable TTS request: 44 characters at
    CNY 3.50/10k. It is separate from the CNY 9.90 voice fee, it has never been
    authorised, and it has never been observed on a receipt. Writing it as 0.00 would
    both overstate what the Founder approved and understate what the call costs, and
    "small" is exactly the reasoning that makes a number get waved through.
    """
    text = ACTIVATION_TEXT
    cost = route.ActivationCost.for_text(text)
    assert cost.first_activation_cny == "9.90"
    assert cost.clone_creation_cny == "0.00", "the clone call itself is officially free"
    assert cost.activation_character_cny == route.FIRST_ACTIVATION_TTS_FEE_UNKNOWN, (
        "an unobserved, unauthorised charge must not be rendered as a number"
    )
    assert cost.activation_character_cny != "0.00"
    assert cost.total_authorised_cny == "0.00", (
        "nothing is authorised until this run says so"
    )
    assert "0.015400" in cost.total_unauthorised_cny, cost.total_unauthorised_cny

    # And it blocks until separately approved.
    decision = _decide(_pair(clone_key="sk-api-clone"), cash_balance=20.0,
                       first_activation_authorised=True)
    assert route.ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED in decision.blocked_by
    joined = " ".join(decision.reasons)
    assert route.FIRST_ACTIVATION_TTS_FEE_UNKNOWN in joined, joined
    assert "44 billable characters" in joined, joined
    print("[ok] 8. the activation character fee is unknown, gated, and never zero")


@test
def test_billable_characters_follows_the_published_counting_rule():
    """One CJK ideograph counts as 2; everything else counts as 1.

    Getting this wrong by a factor of two would misprice the charge the Founder is
    being asked to approve, and the error would be invisible -- the total is tiny
    either way, which is precisely why it needs to be right rather than plausible.
    """
    assert route.billable_characters("") == 0
    assert route.billable_characters("abcd") == 4
    assert route.billable_characters("a b!") == 4
    assert route.billable_characters("中文") == 4
    assert route.billable_characters("中a") == 3
    assert route.billable_characters(
        "这是一段用于首次激活的最短自然中文语音样本。"
    ) == 44
    print("[ok] 9. billable characters count CJK as 2 and everything else as 1")


@test
def test_vendor_confirmation_is_recorded_as_commercial_evidence_not_api_success():
    """The correction must not overshoot into calling the route VERIFIED.

    The Founder obtained four explicit statements from MiniMax customer service. They
    settle how the fee is collected. They say nothing about whether the API permits the
    cross-key synthesis (2042 is documented for that), and nothing about whether this
    account can pay. So the status is VENDOR_CONFIRMED + LIVE_VERIFICATION_PENDING, and
    the evidence object says out loud that it is not proof of an API call succeeding.
    """
    confirmation = route.VENDOR_CONFIRMATION
    assert confirmation["evidence_class"] == route.EVIDENCE_VENDOR_CONFIRMATION
    assert confirmation["is_proof_of_api_success"] is False
    assert len(confirmation["claims"]) == 4
    assert confirmation["still_unverified"], "the gaps must be named, not implied"

    decision = _decide(_pair(clone_key="sk-api-clone"), cash_balance=20.0,
                       first_activation_authorised=True,
                       activation_cost=_cost(
                           first_activation_authorised=True,
                           activation_character_authorised=True,
                       ),
                       cross_key_verified=None)
    assert decision.commercial_status == route.ROUTE_VENDOR_CONFIRMED
    assert decision.verification_status == route.LIVE_VERIFICATION_PENDING
    assert decision.commercial_status != "VERIFIED", (
        "an account-level commercial confirmation is not an executed API call"
    )
    # And the cross-key gate survives the confirmation, because 2042 is an API error.
    assert route.ROUTE_CROSS_KEY_UNKNOWN in decision.blocked_by
    assert not decision.authorised, (
        "everything else can be cleared, but nothing has been executed yet"
    )
    print("[ok] 10. vendor confirmation is commercial evidence; the route stays unverified")


@test
def test_every_blocker_is_listed_so_a_partial_fix_cannot_read_as_complete():
    """A single-valued verdict is what makes a partial fix look like a whole one."""
    decision = _decide(
        _pair(clone_key=""),
        billing_verdict="BLOCKED_BILLING_SOURCE_UNCERTAIN",
        billing_reasons=["voucher_balance is 15.0"],
        cash_balance=0.0,
        first_activation_authorised=False,
        cross_key_verified=None,
        account_verified=None,
    )
    for code in (
        route.ROUTE_CLONE_KEY_REQUIRED,
        route.ROUTE_SUBSCRIPTION_BILLING_UNPROVEN,
        route.ROUTE_ACTIVATION_CASH_INSUFFICIENT,
        route.ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED,
        route.ROUTE_CROSS_KEY_UNKNOWN,
    ):
        assert code in decision.blocked_by, (code, decision.blocked_by)
    assert len(decision.reasons) >= len(decision.blocked_by), (
        "deduplicated codes with merged reasons hide which fix helped"
    )
    assert decision.blocked_by[0] == route.ROUTE_CLONE_KEY_REQUIRED, (
        "the provisioning action is reported first because nothing else can be "
        "attempted until it is done"
    )
    print("[ok] 11. all five independent gates are reported, provisioning action first")


@test
def test_billing_must_be_provable_before_the_clone_not_after():
    """A non-zero voucher means paid funds could be consumed, so nothing may start.

    The temptation this test resists is the obvious one: "the CNY 9.90 is authorised,
    so the guard no longer needs to apply". The guard asks whether *this subscription
    key* can spend outside included plan usage; the fee authorisation answers a
    different question. Relaxing the guard to get past a voucher balance would make
    every later narration unverifiable, in exchange for one voice.
    """
    decision = _decide(
        _pair(clone_key="sk-api-clone"),
        billing_verdict="BLOCKED_BILLING_SOURCE_UNCERTAIN",
        billing_reasons=["balance field voucher_balance is 15.0"],
        cash_balance=20.0,
        first_activation_authorised=True,
    )
    assert route.ROUTE_SUBSCRIPTION_BILLING_UNPROVEN in decision.blocked_by
    joined = " ".join(decision.reasons)
    assert "voucher_balance is 15.0" in joined, joined
    assert "not relaxed" in joined, joined
    print("[ok] 12. an authorised clone fee does not relax the BillingGuard")


# --- E. the 168-hour lifetime ------------------------------------------------


@test
def test_a_cloned_voice_expires_and_the_window_is_measurable_without_waiting():
    """Cloned voices are temporary and are deleted if unused within 168 hours.

    The clock is injected so the boundary is testable in microseconds rather than by
    trusting that a constant is 168. A clone created "for later" is a clone that may
    not exist by the time it is needed, which would mean paying the fee against a
    voice the provider has already removed.
    """
    assert route.CLONE_TTL_HOURS == 168
    assert route.CLONE_TTL_SECONDS == 168 * 3600

    created = 1_000_000.0
    fresh = _decide(_pair(clone_key="sk-api-clone"), clone_created_at=created,
                    now=created + 60)
    assert fresh.remaining_ttl == route.CLONE_TTL_SECONDS - 60
    assert fresh.ttl_deadline_iso() is not None

    expired = _decide(_pair(clone_key="sk-api-clone"), clone_created_at=created,
                      now=created + route.CLONE_TTL_SECONDS + 1)
    assert expired.remaining_ttl < 0
    assert not expired.authorised
    joined = " ".join(expired.reasons)
    assert "temporary" in joined and "deleted" in joined, joined

    # And no clone means no countdown to report, rather than a countdown from epoch.
    never = _decide(_pair(clone_key="sk-api-clone"))
    assert never.remaining_ttl is None
    assert never.ttl_deadline_iso() is None
    print("[ok] 13. the 168h clone lifetime is measured, enforced, and inert when uncreated")


# --- F. claims must not outrun their evidence --------------------------------


@test
def test_cross_key_verified_cannot_be_inferred_from_anything_but_a_real_answer():
    """``None`` blocks; only an explicit ``True`` clears it.

    The trap this closes is the local measurement that the Subscription Key's
    ``get_voice`` *lists* a voice created elsewhere. Listing is account-scoped and
    proves visibility. Error 2042 -- 无权访问该 voice_id -- is the documented symptom
    if visibility does not imply usability, so listing proves nothing about the
    synthesis this route depends on. Vendor confirmation does not close this either:
    it is a billing statement, and 2042 is an API permission error.
    """
    unverified = _decide(_pair(clone_key="sk-api-clone"), cross_key_verified=None)
    assert route.ROUTE_CROSS_KEY_UNKNOWN in unverified.blocked_by
    joined = " ".join(unverified.reasons)
    assert "2042" in joined, joined
    assert "visibility, not usability" in joined, joined

    proven = _decide(_pair(clone_key="sk-api-clone"), cross_key_verified=True)
    assert route.ROUTE_CROSS_KEY_UNKNOWN not in proven.blocked_by

    refuted = _decide(_pair(clone_key="sk-api-clone"), cross_key_verified=False)
    assert route.ROUTE_CROSS_KEY_UNKNOWN in refuted.blocked_by
    joined = " ".join(refuted.reasons)
    assert "no other key may be substituted" in joined, joined
    assert "does not override an API refusal" in joined, joined
    print("[ok] 14. cross-key support needs an explicit answer, not a listing or a call")


@test
def test_an_unverified_account_blocks_before_the_upload_would_be_spent():
    """2038 is returned for an unverified account; uploading first wastes the disclosure."""
    decision = _decide(_pair(clone_key="sk-api-clone"), account_verified=False)
    joined = " ".join(decision.reasons)
    assert "2038" in joined, joined
    assert not decision.authorised
    print("[ok] 15. an unverified account is refused before the sample is uploaded")


@test
def test_the_route_receipt_carries_no_secret_and_no_disallowed_permission():
    """Serialisation is where a receipt usually leaks, so it is checked, not trusted."""
    decision = _decide(_pair(clone_key="sk-api-clone-secret"), cash_balance=0.0)
    payload = decision.as_dict()
    blob = repr(payload)
    assert "sk-api-clone-secret" not in blob, blob
    assert "sk-cp-" not in blob and "Bearer " not in blob
    assert payload["payg_tts_allowed"] is False, (
        "regular PAYG TTS stays forbidden; only the bounded activation is allowed"
    )
    assert payload["payg_activation_tts_allowed"] is True
    assert payload["credit_pack_tts_allowed"] is False
    assert payload["voucher_consumption_allowed"] is False
    assert payload["automatic_topup_allowed"] is False
    assert payload["retry_allowed"] is False
    assert payload["production_ready"] is False
    assert payload["clone_fee_charged_at"] == "FIRST_SYNTHESIS_WITH_THIS_VOICE"
    assert payload["vendor_confirmation"]["is_proof_of_api_success"] is False
    print("[ok] 16. the route receipt is public-safe and forbids every disallowed payment")


@test
def test_the_route_receipt_refuses_the_excluded_moss_voice_family():
    """The pre-existing ``moss_audio_*`` voice must not be reachable as a fallback.

    It is not the Founder's approved voice, and using it as the target or as a
    "quick test" would produce narration that looks like success and measures nothing
    about the Founder at all. The exclusion is recorded in the receipt rather than
    only in prose, so it travels with the evidence.
    """
    receipt = json.loads(
        (
            ROOT / "projects" / "easel-enhanced-golden" / "receipts"
            / "founder-voice-route-receipt.json"
        ).read_text(encoding="utf-8")
    )
    assert receipt["excluded_voices"]["moss_audio_prefix"] == "FORBIDDEN"
    assert "must not be used" in receipt["excluded_voices"]["reason"]
    print("[ok] 17. the excluded moss_audio_* family is recorded as forbidden")


@test
def test_the_local_env_loader_returns_names_and_never_values():
    """The loader is the one place a secret passes through, so it is the one to pin.

    Three properties, each closing a way this file could become a leak: it reports
    variable *names* so a caller cannot print a secret while saying "loaded 2
    credentials"; it never overrides a variable already in the environment, so a
    stale file cannot displace a deliberately set key; and it refuses to read a file
    Git tracks, because a tracked secret is already in the repository's history.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        outside = Path(tmp) / ".env"
        outside.write_text(
            "MINIMAX_CLONE_KEY=sk-api-EXAMPLE\n"
            "# a comment\n"
            "CONTENTOPS_MINIMAX_BASE_URL=https://example.invalid\n",
            encoding="utf-8",
        )
        target = dict()
        loaded = load_local_env_file(outside, env=target)
        assert sorted(loaded) == ["CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_CLONE_KEY"]
        assert "sk-api-EXAMPLE" not in " ".join(loaded), (
            "the loader must report names, not values"
        )
        assert target["MINIMAX_CLONE_KEY"] == "sk-api-EXAMPLE"

        # An existing value wins over the file.
        preset = dict(target, MINIMAX_CLONE_KEY="sk-api-ALREADY-SET")
        again = load_local_env_file(outside, env=preset)
        assert "MINIMAX_CLONE_KEY" not in again, again
        assert preset["MINIMAX_CLONE_KEY"] == "sk-api-ALREADY-SET"

        # A missing file is not an error and loads nothing.
        assert load_local_env_file(Path(tmp) / "absent", env={}) == []

    # And the repository's own .env must never be a tracked file. If it were, the
    # repository would already hold a live credential. Routed through hidden_run
    # because a bare subprocess spawns a visible console window on Windows.
    from process_utils import hidden_run

    tracked = hidden_run(
        ["git", "ls-files", "--error-unmatch", "--", ".env"],
        cwd=str(ROOT), timeout=60,
    )
    assert tracked.returncode != 0, (
        ".env is tracked by Git; it holds a live credential and must be removed from "
        "the index and rotated"
    )
    print("[ok] 19. the local .env loader reports names, defers to the env, and "
          "refuses a tracked file")


@test
def test_every_official_citation_is_attributable():
    """A stop code that cannot be traced to a page is an assertion, not evidence."""
    seen = set()
    for entry in route.OFFICIAL_BASIS:
        assert entry["id"] and entry["page"] and entry["fact"], entry
        assert entry["id"] not in seen, f"duplicate basis id {entry['id']}"
        seen.add(entry["id"])
    ids = {entry["id"] for entry in route.OFFICIAL_BASIS}
    for required in (
        "clone-fee-timing",
        "plan-excludes-cloning",
        "credits-same-coverage",
        "balance-only-via-payg-key",
        "temporary-voice-ttl",
        "error-2042",
    ):
        assert required in ids, f"missing official basis: {required}"
    assert any("2061" in entry["fact"] for entry in route.OFFICIAL_BASIS), (
        "2061 is absent from MiniMax's own error table, and that gap is itself the "
        "fact that must be recorded"
    )
    # The rate the activation character cost is computed from must itself be cited.
    assert any("speech-2.8-hd" in entry["fact"] or "3.50" in entry["fact"]
               for entry in route.OFFICIAL_BASIS), (
        "a computed charge with no cited rate is a guess with a decimal point"
    )
    print("[ok] 20. every stop code and every computed charge traces to a named page")


def main() -> int:
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
    print(f"\nAll {total} clone-route regression tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())