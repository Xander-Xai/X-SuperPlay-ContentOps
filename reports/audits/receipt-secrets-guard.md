# Receipt secret guard — 2026-10-31

> This guard prevents **new or changed** sensitive values from entering tracked
> receipts. It does not rotate a credential and does not erase public history.
> No values are recorded here or in the baseline.

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
- key-like value in text;
- malformed receipt JSON.

A 64-hex identifier is treated as a hash and is not rejected.

## Why the baseline is diff-relative

The first version suppressed a baselined `file → field::kind` path without
binding its value. Replacing the value at that same path therefore passed. That
is the bypass tracked as Issue #61.

The baseline (`contentops.receipt-exposure-baseline/v2`) still stores field
paths and kinds only — **zero values, zero value hashes**. A baselined path now
passes only when the current value is byte-equivalent to the value at the same
path in a trusted base commit (`--base`, the PR base SHA or the previous `main`
commit). The checker rejects:

| Reason | Meaning |
|---|---|
| `new_path` | a sensitive field path absent from the baseline |
| `changed_value` | the same path now holds a different value |
| `changed_text_token` | a key-like string changed inside receipt text |
| `malformed_json` | a receipt no longer parses |
| `baseline_growth` | the baseline itself gained a path versus the base commit |

A legacy v1 baseline is refused rather than interpreted. `--write-baseline`
refuses growth unless `--allow-baseline-growth` is given for an explicitly
reviewed migration; CI never passes that flag. No failure message prints a
value.

## Baseline on `main`

| Item | Value |
|---|---:|
| Tracked receipt JSON files scanned | 123 |
| Files with existing sensitive field paths | 12 |
| Baselined field paths | 71 |
| Values in the baseline | **0** |
| New or changed values | **fail** |

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
Ran 12 tests ... OK

python scripts/check_receipt_secrets.py --base origin/main
receipt-secrets PASS: 71 existing values, 71 baselined paths, base origin/main, 0 new
```

The decisive regression test replaces a baselined `voice_id` value in place and
asserts the check fails with `changed_value`, without printing or storing the
value. Further tests cover a changed balance, a changed fingerprint, a changed
key-like token, a new path, malformed JSON, baseline growth and refusal of a v1
baseline.

## CI base selection

The repo-policy job checks out full history (`fetch-depth: 0`) and passes
`--base` the PR base SHA, or `github.event.before` on a `main` push. If neither
is available it falls back to `origin/main`. A missing base is a refusal
(`BASE_REQUIRED`), not a pass.
