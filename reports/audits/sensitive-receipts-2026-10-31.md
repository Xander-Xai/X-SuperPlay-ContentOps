# Sensitive receipt audit — 2026-10-31

> No secret values are reproduced in this report. Only file names, field names and
> counts are recorded.

## Scope

- `projects/easel-enhanced-golden/receipts/` in the current tree.
- The same path in `origin/main` and in the `feat/content-router` PR #49 diff.
- `research/providers/receipts/` and other tracked receipts for the same patterns.
- Patterns: provider keys, bearer tokens, cookies, private keys, voice IDs, task
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
