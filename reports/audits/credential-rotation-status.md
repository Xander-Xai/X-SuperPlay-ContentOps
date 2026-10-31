# PAYG credential rotation status — 2026-10-31

> No key value, fingerprint, account id or provider endpoint is recorded here.

| Field | Value |
|---|---|
| Credential class | PAYG (pay-as-you-go) provider key |
| Exposure recorded in repository | **true** |
| Rotation status | **NOT_ROTATED** |
| Evidence | Two receipts explicitly record `payg_key_exposed = true` and a rotation note saying the key was not rotated |
| Owner action | **REQUIRED** |
| Last audit | 2026-10-31 |
| Verified by | Repository owner with provider access; not performed by this agent |

## What the owner must do

1. Revoke the exposed PAYG key at the provider.
2. Issue a new key and store it only in the host environment or secret store,
   never in this repository.
3. Re-run the subscription/billing checks; record the result without the key.
4. Update this file: set `Rotation status` to `ROTATED`, add `Rotated at`,
   `Method`, and `Verified by`. Do not add the key or fingerprint.
5. Decide whether to rewrite public history or accept the existing exposure.

## What this repository now enforces

`scripts/check_receipt_secrets.py` rejects new raw provider IDs, balances,
credential fields and key fingerprints in tracked receipts. Existing values are
baselined by field path only. This prevents new exposure; it does not rotate the
credential and does not erase history.
