# Sensitive receipt audit — 2026-10-31

> No secret values are reproduced in this report. Only file names, field names and
> counts are recorded.

## Scope

- `projects/easel-enhanced-golden/receipts/` in the current tree.
- The same path in `origin/main` and in the `feat/content-router` PR #49 diff.
- `research/providers/receipts/` and other tracked receipts for the same patterns.
- Patterns: provider keys, authorization tokens, cookies, private keys, voice IDs, task
  and trace IDs, file IDs, balances, emails, phone numbers.

## Findings

| Finding | Count | Files |
|---|---:|---|
| Receipt files in the directory | 16 | 16 JSON/MD files |
| Receipt files already on `origin/main` | 12 | 12 JSON/MD files |
| Receipt files added by PR #49 | 5 | `founder-voice-golden-narration-receipt.json`, `founder-voice-mplan-crosskey-receipt.json`, `founder-voice-payg-activation-settlement-receipt.json`, `founder-voice-payg-first-activation-receipt.json`, `founder-voice-sample-audit.json` |
| Files with a raw `voice_id` | 6 | diagnosis, cash activation, golden narration, MPlan cross-key, PAYG first activation, subscription activation |
| Files with a raw `task_id` / `trace_id` / `file_id` | 5 | activation history, golden narration, MPlan cross-key, PAYG settlement, PAYG first activation |
| Files with account balance values | 4 | cash activation, PAYG first activation, route, subscription activation |
| Actual provider key / bearer / cookie / private key | **0** | none found |
| Email address / phone number | **0** | none found |
| Key fingerprint values | 2 files | cash activation, PAYG first activation (`payg_key_fingerprint`) |

`research/providers/receipts/` contains sanitized receipts; no key-like value was
found there.

## The credential risk is real and still open

Two receipts record:

```text
payg_key_exposed = true
key_rotation_note = The key is NOT rotated...
```

The PAYG key value itself is **not** in this repository. The receipt records a real
exposure and a Founder-authorised one-use exception; the key was **not rotated**.
The public fingerprint is not the key, but it identifies the exposed credential.

**Required owner action: revoke and rotate that PAYG key at the provider.** Until
that happens, the exposure remains. This report does not attempt rotation and does
not print the fingerprint value.

## Exposure boundary

The 12 receipts are already on `origin/main`. The 5 additional receipt files are on
the public PR #49 branch. Therefore:

- The raw voice ID, provider task/trace IDs and balance values are already public
  history (for the 12) or public branch history (for the 5).
- Removing or sanitizing files in a new commit does **not** remove them from Git
  history. A history rewrite (force-push) or a repository visibility change is an
  owner decision; this run performs neither.
- The repository is public. Do not add new receipts with raw provider IDs, account
  balances, personal voice IDs or trace IDs.

## Recommended remediation

| Priority | Action | Owner |
|---|---|---|
| P0 | Revoke/rotate the exposed PAYG key at the provider | Owner |
| P1 | Move raw provider IDs and balances out of tracked receipts; keep hashes and measured summaries in the committed receipt | Engineering |
| P1 | Treat `.verify-tmp/` (gitignored) as the only place for raw task/voice IDs | Engineering |
| P2 | Decide whether to rewrite public history or accept the existing exposure; either way, record the decision | Owner |
| P2 | Add a receipt sanitizer test that refuses a raw `voice_id`, `task_id`, `trace_id`, balance or key shape in a tracked receipt | Engineering |

## Status

`CREDENTIAL_ROTATION_REQUIRED` — the key exposure is not fixed.
`HISTORY_EXPOSURE_ACKNOWLEDGED` — 12 receipt files are already on `main`.
`AWAITING_OWNER_ACTION` — rotation and any history rewrite require the owner.

## Addendum — tracked-receipt guard and public history

The guard is `scripts/check_receipt_secrets.py`; the value-free baseline is
`reports/audits/receipt-exposure-baseline.json`.

| Item | Value |
|---|---:|
| Tracked receipt JSON files scanned | 123 |
| Files with existing sensitive field paths | 20 (19 under `projects/easel-enhanced-golden/`) |
| Baselined field paths | 278 |
| Values stored in the baseline | **0** — field paths and kinds only |
| New raw provider IDs / balances / fingerprints | **rejected by CI** |

The guard rejects a new `voice_id`, `task_id`, `trace_id`, `file_id`,
`payg_key_fingerprint`, `*_balance`, credential field or key-like value. A
64-hex ID is treated as a hash and is not rejected. The baseline suppresses only
the exact existing `file → field::kind` paths; it does not authorize a new one.

### Public history

The receipt files were introduced across these public commits (dates from Git,
no values):

```text
aaa1059 2026-10-12  docs: activation executed and settled; cross-key verified; Golden narration generated (#34)
5d1fcf2 2026-10-12  fix: native CN T2A adapter + host/credential-binding audit (#43)
45c9e9c 2026-10-12  test: Founder-authorised exposed-key reuse; third refusal (#42)
2739a2b 2026-10-12  feat: CASH_ACTIVATION_RECOVERY; stopped on an exposed key (#41)
21afc42 2026-10-12  feat: Founder voice clone executed; the voucher does not fund it (#40)
ec297e8 2026-10-12  feat: encode FOUNDER_VOUCHER_ACTIVATION (#39)
af2f1dd 2026-10-12  fix: scope BillingGuard to the deduction chain (#38)
9b5f6f2 2026-10-12  fix: correct the clone route to VENDOR_CONFIRMED (#36)
0f871fd 2026-10-12  feat: gate the M2.2 two-key clone route (#35)
0eee9f1 2026-10-12  feat: add the M2.1 voice-clone capability (#32)
5a4ac76 2026-10-06  feat: build reproducible enhanced-golden A/B voice variants (#31)
93b7fd3 2026-10-06  feat: establish reproducible enhanced-golden baseline (#30)
```

The 12 files on `main` and the 5 added by #49 are public. A new commit lowers
future exposure but does not remove history. Removing it requires a rewrite
force-push or a repository visibility change, both of which need explicit owner
authorization; neither was performed.

### Rotation status

`reports/audits/credential-rotation-status.md` records `NOT_ROTATED` and the
owner action. No key value or fingerprint is written.
