# Receipt secret guard — 2026-10-31

> This guard prevents **new** sensitive values from entering tracked receipts.
> It does not rotate a credential and does not erase public history. No values are
> recorded here.

## What runs

| Item | Path |
|---|---|
| Checker | `scripts/check_receipt_secrets.py` |
| Tests | `tests/test_receipt_secrets.py` |
| Baseline | `reports/audits/receipt-exposure-baseline.json` |
| CI | tests job (test) and repo-policy job (check) |

The checker scans tracked JSON receipts under `projects/` and
`research/providers/receipts/`. It rejects a new:

- raw `voice_id`, `task_id`, `trace_id`, `file_id` or `upload_file_id`;
- `payg_key_fingerprint`;
- `*_balance` amount;
- credential field (`api_key`, `secret_key`, access/auth token, cookie, password);
- key-like value in text.

A 64-hex identifier is treated as a hash and is not rejected. The baseline
suppresses only the exact existing `file → field::kind` paths; it never
authorizes a new one. The baseline stores field paths and kinds only — **zero
values**.

## Baseline on `main`

| Item | Value |
|---|---:|
| Tracked receipt JSON files scanned | 123 |
| Files with existing sensitive field paths | 12 |
| Baselined field paths | 71 |
| Values in the baseline | **0** |
| New violations | **fail** |

## Credential status

The receipts record the PAYG key as **exposed and not rotated**. Rotation is an
owner action at the provider; this guard cannot perform it. See
`reports/audits/credential-rotation-status.md` on the P0 branch (#58), which
records `NOT_ROTATED` without a key or fingerprint.

## History

The existing values are already in public commits on `main`. A new commit lowers
future exposure but does not remove history. A history rewrite (force-push) or a
repository visibility change needs explicit owner authorisation and is not part
of this change.

## Test evidence

```text
python tests/test_receipt_secrets.py
Ran 6 tests ... OK

python scripts/check_receipt_secrets.py
receipt-secrets PASS: 71 existing field paths, 71 baselined, 0 new
```
