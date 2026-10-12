"""Execute the Founder voice clone and its one-time activation. Issue #34.

This is the **only** script in the repository that transmits a real human voice to a
paid provider endpoint, so it is written to be the last thing anyone has to trust.

What it is allowed to do, exactly once each
-------------------------------------------
============  ==========  ====================================================
call          credential  what it is for
============  ==========  ====================================================
``upload``    PAYG key    put the approved sample on provider storage -> file_id
``clone``     PAYG key    create ``founder_primary_v1``. Free on its own; the
                          CNY 9.90 is charged by the first synthesis.
``activation``PAYG key    ONE short synthesis. This is what pays the fee.
``crosskey``  Subscription One short synthesis. Proves the M-Plan-only claim and
                          consumes plan quota, not paid funds.
============  ==========  ====================================================

Every one of those is budgeted at exactly one. :class:`CallBudget` enforces it
mechanically, so no code path -- including a future edit, an exception handler, or a
second invocation in the same process -- can spend twice.

The rules this enforces rather than assumes
-------------------------------------------
* **No retry, anywhere.** Not on a transport error, not on a provider status, not on a
  balance error. The prior round's ``2061`` refusal is the worked example of why: the
  request was already correctly formed and re-sending it would have changed nothing
  except the bill.
* **The ``file_id`` is never lost.** It is written to ``.private/`` the moment the
  upload returns, before the clone is attempted, because an orphaned ``file_id`` means
  the Founder's voice sits on third-party storage with nothing referencing it.
* **Balances are read before and after every billable step**, so the receipt reports a
  measured delta rather than an inference from what the provider said it charged.
* **The two keys never mix.** The activation runs on the pay-as-you-go key because
  that is the only key the platform charges 账户余额 for. The cross-key proof runs on
  the Subscription Key because that is the claim being tested. Each is bound through
  :func:`contentops.media.credentials.child_env_for`, so the key the gate authorised is
  the key the child uses.

Dry run by default
------------------
``--execute`` is required. Without it the script resolves credentials, re-verifies the
sample digest, reads balances and prints the exact call plan, and exits without
transmitting anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402

from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.clone_route import (  # noqa: E402
    ACTIVATION_TEXT,
    CLONE_TTL_SECONDS,
    SPEECH_2_8_HD_CNY_PER_10K,
    billable_characters,
)
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    load_local_env_file,
    resolve_two_key_pair,
)
from contentops.media.minimax_voice_clone import (  # noqa: E402
    MiniMaxVoiceCloneProvider,
    VoiceCloneRequest,
    voice_id_hash,
)
from contentops.media.transport import resolve_cli  # noqa: E402

SAMPLE = ROOT / "assert" / "voice-reference-clean.wav"
EXPECTED_SAMPLE_SHA256 = (
    "bb56d052cd637bd8a369f6e37a745c7609de9988ada0fa0827d4d5c59035df8d"
)
VOICE_ALIAS = "founder_primary_v1"
PROVIDER_VOICE_ID = "founder_primary_v1"
OBJECTIVE = "speech-2.8-hd narration for the Enhanced Golden pipeline"
SAMPLE_DURATION_S = 15.0
MODEL = "speech-2.8-hd"

PRIVATE_DIR = ROOT / ".private"
PRIVATE_REGISTRY = PRIVATE_DIR / "founder-voice.json"
WORK = ROOT / ".verify-tmp" / "m23-founder-clone"
RECEIPT = ROOT / "projects/easel-enhanced-golden/receipts/founder-voice-activation-receipt.json"

#: The Founder's ceiling. Every measured delta is compared against this, and the run
#: stops if the combined observed spend would exceed it.
VOUCHER_CEILING_CNY = Decimal("10.00")

#: What the run is expected to cost, from the official rate. Not a cap -- the cap is
#: :data:`VOUCHER_CEILING_CNY` -- but the number a reader compares the receipt against.
EXPECTED_CLONE_FEE_CNY = Decimal("9.90")


class StopRun(RuntimeError):
    """A refusal. Nothing is retried and nothing after this point runs."""


class CallBudget:
    """Exactly one of each billable-or-disclosing call, enforced by counter.

    A dict of counts would be the obvious implementation and it would be advisory: any
    code path that forgot to increment would double-spend without complaint. This
    refuses at the point of use instead, so the failure mode of a mistake is a refusal
    rather than a second charge.
    """

    LIMITS = {"upload": 1, "clone": 1, "activation_tts": 1, "crosskey_tts": 1}

    def __init__(self) -> None:
        self.counts: Dict[str, int] = {name: 0 for name in self.LIMITS}
        self.spent: List[str] = []

    def take(self, name: str) -> None:
        limit = self.LIMITS.get(name)
        if limit is None:
            raise StopRun(f"unknown call {name!r}; the budget enumerates every call")
        if self.counts[name] >= limit:
            raise StopRun(
                f"{name} has already been used {self.counts[name]} time(s) against a "
                f"limit of {limit}. This run does not retry a billable call: an "
                "entitlement or payment failure fails identically the second time, and "
                "a success would be charged twice."
            )
        self.counts[name] += 1
        self.spent.append(name)

    def as_dict(self) -> Dict[str, int]:
        return dict(self.counts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url() -> str:
    for name in ("CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_VOICE_CLONE_BASE_URL"):
        value = os.environ.get(name, "").strip()
        if value:
            return value.rstrip("/")
    raise StopRun(
        "no provider host configured; set CONTENTOPS_MINIMAX_BASE_URL. There is "
        "deliberately no default: the wrong regional host answers with an "
        "invalid-api-key status, which reads as a broken credential."
    )


def read_money(base_url: str, credential: str) -> Dict[str, Any]:
    """One read-only balance + quota read. Never a generation call."""
    guard = BillingGuard(base_url=base_url, credential=credential)
    result = guard.evaluate("speech")
    balances = {
        k: v
        for k, v in (result.balances or {}).items()
        if k not in ("base_resp", "balance_alert_switch", "balance_alert_threshold")
    }
    return {
        "verdict": result.verdict,
        "credential_class": result.credential_class,
        "balances": balances,
        "observed_out_of_chain": list(result.observed_out_of_chain),
        "quota": None
        if result.quota is None
        else {
            "interval_remaining_percent": result.quota.interval_remaining_percent,
            "weekly_remaining_percent": result.quota.weekly_remaining_percent,
            "bucket": result.quota.bucket,
        },
    }


def money_delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Per-field movement. Computed, never guessed from what the provider claimed."""
    fields = ("cash_balance", "credit_balance", "voucher_balance", "owed_amount",
              "available_amount")
    out: Dict[str, Any] = {}
    for name in fields:
        try:
            b = Decimal(str(before["balances"].get(name)))
            a = Decimal(str(after["balances"].get(name)))
            out[name] = {
                "before": str(b),
                "after": str(a),
                "delta": str(a - b),
                "decreased": a < b,
                "increased": a > b,
            }
        except Exception:  # noqa: BLE001 - an unreadable field is reported, not guessed
            out[name] = {"before": before["balances"].get(name),
                         "after": after["balances"].get(name),
                         "delta": None,
                         "error": "field unreadable; not inferred"}
    return out


def write_private_registry(**fields: Any) -> None:
    """Persist a provider handle to the gitignored local registry.

    Two handles are recorded and neither may ever be committed:
    ``upload_file_id`` points at the Founder's voice on provider storage and
    ``provider_voice_id`` is what synthesises with it.
    """
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {}
    if PRIVATE_REGISTRY.is_file():
        try:
            payload = json.loads(PRIVATE_REGISTRY.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload.update(fields)
    PRIVATE_REGISTRY.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def synthesize(
    *,
    text: str,
    voice: str,
    out_path: Path,
    credential: str,
) -> Dict[str, Any]:
    """One TTS call through the official CLI, with the authorised key bound in.

    The key goes in through a child-only environment, never argv: argv is world-readable
    on the host, and the credential that authorised a charge and the credential that
    performs it have to be the same one.
    """
    from contentops.media.credentials import (
        ResolvedCredential,
        classify_credential,
        child_env_for,
    )

    resolved = ResolvedCredential(
        key=credential,
        credential_class=classify_credential(credential),
        source="EXECUTED_BY_THIS_SCRIPT",
    )
    env = child_env_for(resolved)
    # resolve_cli(), not a bare "mmx". On Windows npm writes mmx.cmd, and
    # CreateProcess cannot resolve a batch shim from a bare name -- the run dies with
    # WinError 2 before the provider is ever contacted. The rest of the repository
    # already routes through here; this script has to as well, or it is the one path
    # that works on Linux and fails on the Founder's own machine.
    cli = resolve_cli()
    if not cli:
        raise StopRun("official MiniMax CLI not on PATH; install: npm install -g mmx-cli")
    prefix = list(cli) if isinstance(cli, (list, tuple)) else [str(cli)]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()
    started = time.time()
    result = hidden_run(
        prefix
        + [
            "speech", "synthesize",
            "--model", MODEL,
            "--text", text,
            "--voice", voice,
            "--format", "wav",
            "--sample-rate", "44100",
            "--out", str(out_path),
            "--quiet", "--non-interactive",
        ],
        env=env,
        timeout=600,
    )
    ok = result.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 1024
    if ok and out_path.stat().st_mtime < started - 1:
        ok = False
    return {
        "ok": ok,
        "returncode": result.returncode,
        "bytes": out_path.stat().st_size if out_path.is_file() else 0,
        "path": str(out_path),
        "stderr_tail": (result.stderr or "")[-400:],
        "stdout_tail": (result.stdout or "")[-200:],
    }


def read_private_registry() -> Dict[str, Any]:
    """The local, gitignored record of what has already happened to this voice."""
    if not PRIVATE_REGISTRY.is_file():
        return {}
    try:
        data = json.loads(PRIVATE_REGISTRY.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="actually transmit. Without this the script performs no provider write.",
    )
    parser.add_argument(
        "--skip-crosskey",
        action="store_true",
        help="stop after the activation; used only when the cross-key proof is not wanted",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "continue from whatever the local registry already records. A previous "
            "invocation may have uploaded and cloned successfully and then failed "
            "before the activation; re-running without this would create a SECOND "
            "clone and a second disclosure of the Founder's voice."
        ),
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    load_local_env_file(ROOT / ".env")
    base_url = _base_url()
    pair = resolve_two_key_pair()
    budget = CallBudget()
    receipt: Dict[str, Any] = {
        "schema": "contentops.voice-activation-receipt/v1",
        "producer": "scripts/execute_founder_voice_activation.py",
        "provider": "minimax",
        "voice_alias": VOICE_ALIAS,
        "provider_voice_id_hash": voice_id_hash(PROVIDER_VOICE_ID),
        "sample_sha256": EXPECTED_SAMPLE_SHA256,
        "model": MODEL,
        "base_url_host": base_url,
        "started_at": _now(),
        "executed": bool(args.execute),
        "credentials": pair.safe_metadata(),
        "activation_text": ACTIVATION_TEXT,
        "provider_call_budget": CallBudget.LIMITS,
        "provider_call_counts": budget.as_dict(),
        "retries_performed": 0,
        "notes": [],
    }

    # --- local preconditions, before anything is transmitted --------------------
    if pair.clone.credential_class != CREDENTIAL_PAYG:
        raise SystemExit("MINIMAX_CLONE_KEY is not a pay-as-you-go key; refusing.")
    if pair.tts.credential_class != CREDENTIAL_SUBSCRIPTION:
        raise SystemExit("the TTS credential is not the Subscription Key; refusing.")
    if not SAMPLE.is_file():
        raise SystemExit(f"the approved sample is absent at {SAMPLE}; refusing.")
    digest = _sha256(SAMPLE)
    if digest != EXPECTED_SAMPLE_SHA256:
        raise SystemExit(
            f"sample digest changed: {digest} != {EXPECTED_SAMPLE_SHA256}. Refusing to "
            "clone a different recording than the one the Founder approved."
        )

    chars = billable_characters(ACTIVATION_TEXT)
    est_chars = Decimal(SPEECH_2_8_HD_CNY_PER_10K) * chars / Decimal(10000)
    projected = EXPECTED_CLONE_FEE_CNY + est_chars

    print("=== LOCAL PRECONDITIONS ===")
    print(f"  sample sha256    : {digest}")
    print(f"  sample duration  : {SAMPLE_DURATION_S}s (declared by the asset registry)")
    print(f"  provider voice_id: {PROVIDER_VOICE_ID} -> sha256 "
          f"{voice_id_hash(PROVIDER_VOICE_ID)[:16]}")
    print(f"  clone credential : {pair.clone.credential_class} / {pair.clone.source}")
    print(f"  tts credential   : {pair.tts.credential_class} / {pair.tts.source}")
    print(f"  keys distinct    : {pair.safe_metadata()['keys_distinct']}")
    print(f"  activation text  : {ACTIVATION_TEXT}")
    print(f"  billable chars   : {chars} -> est CNY {est_chars:.6f}")
    print(f"  projected total  : CNY {projected:.4f} (ceiling CNY {VOUCHER_CEILING_CNY})")
    print()
    if projected > VOUCHER_CEILING_CNY:
        raise SystemExit(
            f"projected CNY {projected:.4f} exceeds the authorised ceiling "
            f"CNY {VOUCHER_CEILING_CNY}. Nothing was transmitted."
        )

    before = read_money(base_url, pair.clone.key)
    receipt["money_before_this_invocation"] = before
    print("=== MONEY BEFORE THIS INVOCATION (read-only, PAYG key) ===")
    print(f"  {json.dumps(before['balances'], ensure_ascii=False)}")
    print(f"  quota: {before['quota']}")
    print()

    # The spend that matters is the spend of the whole activation, not of whichever
    # process happened to run last. A resumed run starts after the clone, so measuring
    # from here would report the activation alone and silently drop any cost the
    # earlier steps incurred. The first reading is therefore pinned in the registry and
    # reused, which makes the ceiling check span the entire issue rather than one call.
    registry = read_private_registry()
    baseline = registry.get("money_baseline_balances")
    if not baseline:
        baseline = dict(before["balances"])
        write_private_registry(
            money_baseline_balances=baseline,
            money_baseline_at=_now(),
            money_baseline_note=(
                "first read-only balance snapshot for this voice, taken before the "
                "upload. Every later delta is measured from here so a resumed run "
                "cannot report a smaller total than was actually spent."
            ),
        )
    receipt["money_baseline"] = baseline
    print("=== SPEND BASELINE FOR THE WHOLE ACTIVATION ===")
    print(f"  {json.dumps(baseline, ensure_ascii=False)}")
    print()

    if not args.execute:
        print("=== DRY RUN. NOTHING WAS TRANSMITTED. ===")
        print("  1. upload  assert/voice-reference-clean.wav  (PAYG)   -> file_id")
        print(f"  2. clone   voice_id={PROVIDER_VOICE_ID}          (PAYG)")
        print(f"  3. activate one short synthesis               (PAYG)   pays CNY 9.90")
        print(f"  4. crosskey one short synthesis            (Subscription) M Plan only")
        print()
        print("Re-run with --execute to run it. Each call is budgeted at one.")
        return 0

    provider = MiniMaxVoiceCloneProvider(
        credential=pair.clone, base_url=base_url, allow_payg_clone=True
    )
    request = VoiceCloneRequest(
        voice_alias=VOICE_ALIAS,
        provider_voice_id=PROVIDER_VOICE_ID,
        objective=OBJECTIVE,
        expected_fee_cny=EXPECTED_CLONE_FEE_CNY,
        sample_path=SAMPLE,
        sample_sha256=digest,
    )
    receipt["request_fingerprint"] = request.fingerprint()

    # --- 1 + 2. upload and clone, or resume past them -------------------------
    #
    # A voice_id is permanent and a voice_id cannot be re-created under the same name
    # (2039), so re-running the upload and clone after a *post-clone* failure would
    # burn a second upload of the Founder's voice and then fail on the duplicate id --
    # turning a recoverable crash into a permanent one. The local registry is what
    # makes the resume safe: the file_id and the voice_id are written the moment they
    # exist, so "did this already happen" is a fact on disk and not a memory.
    registry = read_private_registry()
    already_cloned = registry.get("provider_voice_id") == PROVIDER_VOICE_ID
    already_uploaded = bool(registry.get("upload_file_id"))

    # A refusal is not an absence. ``CallBudget`` caps calls within one process, but a
    # second invocation starts with a fresh budget -- so without this the only thing
    # preventing a repeated paid attempt after a refusal is an operator remembering.
    # The Founder's authorisation forbids both a duplicate activation and an automatic
    # retry, and "we tried it and it did not work" is exactly the case where re-running
    # looks tempting: the clone exists, so the next run looks cheaper, and it would be
    # a second charge against a voice that already failed once.
    if registry.get("activation_refused"):
        raise SystemExit(
            ".private/founder-voice.json records activation_refused="
            f"{registry.get('activation_refused_at')!r} for this voice. That attempt was "
            "a single authorised one and it was refused; a second one would be a second "
            "charge and is not authorised. Resolve the recorded blocker first, and only "
            "then clear the flag deliberately, with the reason recorded alongside it."
        )

    if already_cloned and not args.resume:
        raise SystemExit(
            f"{PRIVATE_REGISTRY.relative_to(ROOT).as_posix()} already records "
            f"provider_voice_id={PROVIDER_VOICE_ID}"
            + (
                " and activated=true. Nothing to do; refusing to clone again."
                if registry.get("activated")
                else ". Re-run with --resume to continue from the activation instead of "
                "uploading and cloning a second time."
            )
        )
    if (already_cloned or already_uploaded) and not args.resume:
        raise SystemExit(
            "the local registry already records an upload for this voice; re-run with "
            "--resume so the existing file_id is reused instead of disclosing the "
            "sample twice."
        )

    if args.resume and already_cloned:
        clone_created_at = float(registry.get("created_at_unix") or time.time())
        receipt["resumed_from_registry"] = True
        receipt["upload_file_id_hash"] = voice_id_hash(
            str(registry.get("upload_file_id", ""))
        )
        receipt["clone_status"] = "CLONED"
        receipt["clone_created_at"] = registry.get("created_at")
        receipt["clone_created_at_unix"] = clone_created_at
        budget.counts["upload"] = 1
        budget.counts["clone"] = 1
        ttl_left = CLONE_TTL_SECONDS - (time.time() - clone_created_at)
        print("=== 1-2/4 RESUMING FROM THE LOCAL REGISTRY ===")
        print(f"  voice_id already exists: {PROVIDER_VOICE_ID}")
        print(f"  upload and clone are NOT repeated (provider_call_counts records them)")
        print(f"  temporary-voice window remaining: {ttl_left / 3600:.1f}h of 168h")
        if ttl_left <= 0:
            raise SystemExit(
                "the cloned voice has already passed the 168-hour window and provider "
                "storage will have deleted it. It cannot be activated. Do not synthesise."
            )
        print()

    if not already_cloned:
        # --- 1. upload --------------------------------------------------------
        print("=== 1/4 UPLOAD (PAYG key) ===")
        budget.take("upload")
        try:
            file_id = provider.upload_sample(SAMPLE)
        except Exception as exc:  # noqa: BLE001
            receipt["clone_status"] = "REFUSED"
            receipt["stopped_at"] = "upload"
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            _finish(receipt)
            print(f"  REFUSED: {exc}")
            return 1
        # Persisted BEFORE the clone is attempted, so an orphaned sample on provider
        # storage is always traceable to this run.
        write_private_registry(
            upload_file_id=file_id,
            sample_sha256=digest,
            uploaded_at=_now(),
            upload_call="scripts/execute_founder_voice_activation.py",
        )
        receipt["upload_file_id_hash"] = voice_id_hash(str(file_id))
        print("  ok. file_id persisted to .private/founder-voice.json (value not printed)")
        print()

        # --- 2. clone --------------------------------------------------------
        print("=== 2/4 CLONE (PAYG key) ===")
        budget.take("clone")
        try:
            provider.create_clone(file_id, PROVIDER_VOICE_ID, confirm_fee=True)
        except Exception as exc:  # noqa: BLE001
            receipt["clone_status"] = "REFUSED"
            receipt["stopped_at"] = "clone"
            receipt["error"] = f"{type(exc).__name__}: {exc}"
            receipt["money_after_clone"] = read_money(base_url, pair.clone.key)
            _finish(receipt)
            print(f"  REFUSED: {exc}")
            print("  file_id is preserved in .private/founder-voice.json -- do not re-upload.")
            return 1
        clone_created_at = time.time()
        write_private_registry(
            provider_voice_id=PROVIDER_VOICE_ID,
            voice_id_hash=voice_id_hash(PROVIDER_VOICE_ID),
            created_at=datetime.fromtimestamp(clone_created_at, tz=timezone.utc).isoformat(),
            created_at_unix=clone_created_at,
            ttl_seconds=CLONE_TTL_SECONDS,
            activated=False,
        )
        receipt["clone_status"] = "CLONED"
        receipt["clone_created_at"] = datetime.fromtimestamp(
            clone_created_at, tz=timezone.utc
        ).isoformat()
        receipt["clone_created_at_unix"] = clone_created_at
        print(f"  ok. voice_id={PROVIDER_VOICE_ID} created and persisted locally.")
        print()

    # --- 3. activation (PAYG) ------------------------------------------------
    print("=== 3/4 FIRST ACTIVATION SYNTHESIS (PAYG key) -- this pays CNY 9.90 ===")
    money_pre_activation = read_money(base_url, pair.clone.key)
    budget.take("activation_tts")
    activation_out = WORK / "activation-founder_primary_v1.wav"
    act = synthesize(
        text=ACTIVATION_TEXT,
        voice=PROVIDER_VOICE_ID,
        out_path=activation_out,
        credential=pair.clone.key,
    )
    money_post_activation = read_money(base_url, pair.clone.key)
    receipt["money_pre_activation"] = money_pre_activation
    receipt["money_post_activation"] = money_post_activation
    receipt["activation_delta"] = money_delta(money_pre_activation, money_post_activation)
    receipt["activation_tts"] = {
        k: v for k, v in act.items() if k not in ("path",)
    }
    receipt["activation_audio"] = str(activation_out)
    print(f"  ok={act['ok']} returncode={act['returncode']} bytes={act['bytes']}")
    print(f"  delta: {json.dumps(receipt['activation_delta'], ensure_ascii=False)}")
    if not act["ok"]:
        print(f"  stderr: {act['stderr_tail']}")
        receipt["voice_activated"] = False
        receipt["stopped_at"] = "activation"
        receipt["activation_refusal"] = act["stderr_tail"].strip()[:400]
        # Persisted so a later invocation cannot turn this single authorised attempt
        # into a second charge.
        write_private_registry(
            activation_refused=True,
            activation_refused_at=_now(),
            activation_refusal_provider_message=act["stderr_tail"].strip()[:400],
            activation_refusal_evidence=(
                "paid balances were read before and after; see "
                "projects/easel-enhanced-golden/receipts/founder-voice-activation-receipt.json"
            ),
        )
        _finish(receipt)
        print("  NOT ACTIVATED. No second paid attempt will be made.")
        return 1
    receipt["voice_activated"] = True
    write_private_registry(activated=True, activated_at=_now())
    print("  VOICE_ACTIVATED = VERIFIED")
    print()

    # --- ceiling enforcement on what was actually measured --------------------
    spent = _observed_spend(receipt)
    receipt["observed_spend_cny"] = spent
    if spent is not None and spent > VOUCHER_CEILING_CNY:
        receipt["stopped_at"] = "CEILING_EXCEEDED"
        _finish(receipt)
        print(
            f"STOP: measured spend CNY {spent} exceeds the authorised ceiling "
            f"CNY {VOUCHER_CEILING_CNY}. No further generation is permitted."
        )
        return 1
    print(f"=== MEASURED SPEND AGAINST THE CEILING: CNY {spent} / "
          f"CNY {VOUCHER_CEILING_CNY} ===")
    print()

    # --- 4. cross-key (Subscription) -----------------------------------------
    if args.skip_crosskey:
        receipt["stopped_at"] = "CROSSKEY_SKIPPED_BY_OPERATOR"
        _finish(receipt)
        return 0

    print("=== 4/4 CROSS-KEY SYNTHESIS (Subscription Key) -- M Plan quota only ===")
    quota_before = money_post_activation.get("quota")
    budget.take("crosskey_tts")
    cross_out = WORK / "crosskey-founder_primary_v1.wav"
    cross = synthesize(
        text=ACTIVATION_TEXT,
        voice=PROVIDER_VOICE_ID,
        out_path=cross_out,
        credential=pair.tts.key,
    )
    money_post_cross = read_money(base_url, pair.tts.key)
    receipt["crosskey_tts"] = {k: v for k, v in cross.items() if k not in ("path",)}
    receipt["crosskey_audio"] = str(cross_out)
    receipt["crosskey_credential"] = {
        "credential_class": pair.tts.credential_class,
        "credential_source": pair.tts.source,
    }
    receipt["money_post_crosskey"] = money_post_cross
    receipt["crosskey_money_delta"] = money_delta(money_post_activation, money_post_cross)
    receipt["crosskey_quota_delta"] = {
        "before": quota_before,
        "after": money_post_cross.get("quota"),
    }
    print(f"  ok={cross['ok']} returncode={cross['returncode']} bytes={cross['bytes']}")
    if not cross["ok"]:
        print(f"  stderr: {cross['stderr_tail']}")
        receipt["cross_key_tts_verified"] = False
        receipt["stopped_at"] = "crosskey"
        _finish(receipt)
        print("  CROSS_KEY_TTS_VERIFIED = False. The activated voice and every")
        print("  credential record are preserved. Nothing is recreated.")
        return 1
    receipt["cross_key_tts_verified"] = True
    print("  CROSS_KEY_TTS_VERIFIED = True")
    print()

    receipt["m_plan_only_verified"] = _m_plan_only(receipt)
    receipt["notes"].append(
        "no retry was performed at any step; CallBudget caps upload, clone, activation "
        "and cross-key at one each and refuses before the second use"
    )
    _finish(receipt)
    print("=== DONE ===")
    return 0


def _observed_spend(receipt: Dict[str, Any]) -> Optional[str]:
    """How much paid funds actually left the account across the whole activation.

    Measured from the pinned baseline in the local registry -- not from this
    invocation's opening reading -- so a run that had to be resumed after the clone
    still reports the total. Derived from balances, never from what the provider said
    it charged: a provider's self-report is a claim, a balance delta is evidence.

    Only a *decrease* in a paid balance counts as spend. An increase is not negative
    spend, it is a recharge, which is forbidden here and must therefore be visible as
    its own fact rather than netted away.
    """
    baseline = receipt.get("money_baseline") or {}
    current = (receipt.get("money_post_activation") or {}).get("balances") or {}
    if not baseline or not current:
        return None
    total = Decimal("0")
    seen = False
    increases: Dict[str, str] = {}
    for name in ("cash_balance", "credit_balance", "voucher_balance"):
        try:
            b = Decimal(str(baseline.get(name)))
            a = Decimal(str(current.get(name)))
        except Exception:  # noqa: BLE001
            continue
        seen = True
        value = a - b
        if value < 0:
            total += -value
        elif value > 0:
            increases[name] = str(value)
    receipt["balance_increases_after_baseline"] = increases
    receipt["balance_increases_note"] = (
        "any entry here is an INCREASE in a paid balance. That is not negative spend "
        "and it is not permitted by this authorisation; treat it as an incident."
        if increases
        else "no paid balance increased at any point in the run"
    )
    return str(total) if seen else None


def _m_plan_only(receipt: Dict[str, Any]) -> bool:
    """True when the cross-key synthesis moved plan quota and no paid balance."""
    quota = receipt.get("crosskey_quota_delta") or {}
    after = quota.get("after") or {}
    before = quota.get("before") or {}
    if not before or not after:
        return False
    moved = any(
        after.get(k) is not None
        and before.get(k) is not None
        and float(after[k]) < float(before[k])
        for k in ("interval_remaining_percent", "weekly_remaining_percent")
    )
    delta = receipt.get("crosskey_money_delta") or {}
    for name in ("cash_balance", "credit_balance", "voucher_balance"):
        row = delta.get(name) or {}
        if row.get("decreased"):
            return False
    return bool(moved)


def _finish(receipt: Dict[str, Any]) -> None:
    receipt["finished_at"] = _now()
    receipt["provider_call_counts"] = {
        "upload": 1 if receipt.get("upload_file_id_hash") else 0,
        "clone": 1 if receipt.get("clone_status") == "CLONED" else 0,
        "activation_tts": 1 if receipt.get("activation_tts") else 0,
        "crosskey_tts": 1 if receipt.get("crosskey_tts") else 0,
    }
    receipt.setdefault("voice_activated", False)
    receipt.setdefault("cross_key_tts_verified", False)
    blob = json.dumps(receipt, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to write a receipt containing {banned!r}")
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {RECEIPT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    raise SystemExit(main())