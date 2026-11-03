# ADR-019 — Receipt history exposure: rotate, accept, and keep guarding new receipts

- Status: **Accepted — Owner authorization, 2026-11-04**
- Complements: [rights audit report](../../reports/audits/rights-audit-2026-11-04.md)
- Refs: #56

## Context

The 2026-11-04 audit measured the receipts already published on `main`:

| Field class | Occurrences |
|---|---:|
| Account / cash / credit / voucher balances | 139 |
| Provider `voice_id` values | 13 |
| PAYG key fingerprints | 4 |
| Raw key, JWT, private key or cloud credential | **0** |

`scripts/check_receipt_secrets.py` reports 71 pre-existing baseline entries and
an empty growth list: its design correctly states that a new commit cannot
remove these values from public history, and only stops new or changed values.

## Decision

The Owner chose **rotate + record acceptance**, not a history rewrite:

1. **No history rewrite.** The public history stays intact. No force-push, no
   filter-repo rewrite, no GitHub cache-purge request.
2. **Rotate the PAYG key if it is still active.** Rotation is a provider-console
   action owned by the Owner. It is **not done by this ADR** and must be recorded
   in #56 with the rotation date and a confirmation that no key value is written
   into the repository.
3. **Accept the already-public data.** The balances, provider `voice_id`s and
   PAYG fingerprints are recorded as accepted exposure. This ADR does not claim
   they were removed.
4. **Keep guarding new receipts.** `check_receipt_secrets.py` remains
   diff-relative; every future receipt must pass it. No new raw provider ID,
   balance, task/trace ID or key fingerprint may be added to a committed
   receipt without review.

## Consequence

- The audit's finding remains true: the historical values are public. Nothing in
  this ADR says otherwise.
- #56 stays **open** until (a) the key rotation is confirmed by the Owner and
  (b) the separate GZH rights question is decided. The exposure decision does not
  close the rights audit.
- `allow_payg` remains `false`; this decision grants no provider spend or
  credential authority.

## Rotation checklist (Owner)

- [ ] Determine whether the fingerprinted PAYG key is still active in the
      provider console.
- [ ] If active, rotate it; store the new key outside the repository.
- [ ] Record rotation date and confirmation in #56. Do **not** write the key or
      its fingerprint into the repository.
- [ ] Re-run `python scripts/check_receipt_secrets.py` and confirm `growth: []`.
