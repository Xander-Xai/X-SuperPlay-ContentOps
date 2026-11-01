# ADR-011: Proposed managed authorization for mutating `media-use` operations

Status: **Proposed — design only; NOT APPROVED for implementation or execution**
Date: 2026-11-01
Issue: #57
Related: [ADR-008](ADR-008-media-use-adapter.md), [ADR-009](ADR-009-skill-execution-authorization.md), [ADR-010](ADR-010-trusted-grant-execution-gate.md), [ADR-005](ADR-005-human-approval.md)

## Context and scope

The existing managed entry `scripts/skill_execute.py` deliberately exposes only `status` and `doctor`. Its real-grant, replay and atomic-use tests support that **read-only** scope. Direct operator and M5 entry points can reach `resolve`, `adopt`, `ingest` and `import` through existing adapter interfaces, but those paths are **not** covered by this managed grant gate. This is a documented scope boundary, not proof of an exploit.

This ADR proposes how to decide whether to extend the gate; it does **not** approve extending `ALLOWED_OPERATIONS`, changing M5, making provider calls, or publishing.

## Side-effect inventory (verify against exact implementation before coding)

| Operation | Potential effects to bind | Required safety questions |
|---|---|---|
| `resolve` | May select or materialize candidates; may update project-local `.media/` inventory or invoke an upstream provider depending on source | Does it produce bytes, invoke a generator or network, or consume a provider budget? Treat uncertain effects as mutating |
| `adopt` | Incorporates existing local media into project inventory, may copy material and persist metadata | Source file identity, path containment, licensing and duplicate handling |
| `ingest` | Copies a file and writes project-local records | Pre-copy rights review, exact input digest, allowed destination, idempotent retries |
| `import` | Writes sidecar receipt/asset records, may create additional project artifacts | Validate rights before I/O, record identities and hashes, prevent asset/evidence privilege escalation |

The table is a **threat-model checklist**, not a substitute for the current code's actual call graph. In particular, do not equate `resolve` with a harmless read or assume every command always invokes the same provider.

## Proposed authorization boundaries

1. **Keep one authority.** Reuse `authorization.py`, `grant_source.py`, `execution_gate.py` and the approved Skill Registry; do not create a second grant ledger, router or media inventory. A `RESOLVABLE` verdict is never an execution grant.
2. **Bind the request to effects.** In addition to existing skill/version/account/pipeline/stage/subject/operation, bind canonical project root, input path(s) and SHA-256, requested asset ID/kind, source/provider allowlist, rights-review record digest, expected output scope, network flag, paid flag and approved budget. Reject drift before consuming the grant and before filesystem writes.
3. **Preserve default deny.** Unknown effects, provider choice, cross-project paths, unreviewed material, symlink escape, absent runtime lock, and any network/paid operation not separately approved must refuse. The existing offline-only `hyperframes@0.8.222` baseline grants no network, paid or cross-project rights.
4. **Human approvals are distinct.** `receipts/human-review.json` and the media Rights Review are neither execution grants nor publication approvals. Only a purpose-bound `skill_execution` record may grant a particular effect.
5. **Identity is not authentication.** The present Owner allowlist and host subject are declarative local labels (ADR-010). Do not expose mutating commands to remote or untrusted multi-user callers until real authentication and isolation are designed and approved.
6. **Budget must describe real cost.** Existing `max_uses` is atomically consumed; `max_units` is not evidence of measured media cost. Specify a canonical `units` and budget metering contract before enabling any billed action, and never allow a paid operation on the basis of a nominal `max_units` field.
7. **No implicit migration.** Existing M5 `stage_media_use` is not wired to the managed gate; making it depend on a grant is a separate migration decision with backward-compatibility and fail-closed tests.

## Proposed idempotency and failure model

- Assign a stable request ID and an operation-specific **effect fingerprint**, derived from immutable approval scope, source digests and destination identity. A repeated request with a changed fingerprint is rejected.
- Reuse atomic `O_EXCL` request/use markers for **single-host admission control** only. They are not distributed Exactly-Once.
- Before each write, validate the approved destination; write to contained staging paths and commit atomically where supported; never overwrite an existing unverified asset or receipt silently.
- Separate `AUTHORIZED`, `ATTEMPTED`, `EXECUTED`, `FAILED` and `RECONCILIATION_REQUIRED`. A process crash after consumption must not be silently retried under a new request ID, or represented as a successful import.
- Persist a sanitized operation receipt that links the approved scope, consumed slot, input/output hashes, rights decision and side effects. Never include credentials, raw host paths, private identifiers or provider balances.
- Specify partial failure recovery for pairs of writes (asset and sidecar; inventory and receipt), atomic rename constraints on Windows/Linux, and human reconciliation of uncertain state.
- Refuse concurrent conflicting writes to the same project/asset even when they use different approvals; do not assume a grant-use lock is an asset lock.

## Required adversarial tests before any implementation approval

No grant; wrong account/stage/asset ID; forged rights record; rights record changed after authorization; file changed after fingerprint; path traversal and symlink escape; unknown provider; network or paid escalation; budget meter overflow; duplicated/replayed request; concurrent conflicting asset writes; crash between copy and receipt; exhausted grant; revoked/expired grant; unreadable ledger; partial rollback; sanitized audit output; clean clone; Windows and Linux filesystem behavior. Test `resolve` separately for catalog-only and materializing/provider modes.

## Decision gates (all currently **NOT APPROVED**)

1. Owner signs off the exact per-operation effect matrix and threat model.
2. Owner decides whether the managed CLI should expose each verb, whether M5 must migrate, and what compatibility behavior is acceptable.
3. If a paid/network path is contemplated, Owner separately authorizes provider, account, maximum amount, one-attempt policy and billing proof. The current baseline does not permit it.
4. Only after approval: implement test-first in a separate PR; verify current runtime lock, rights gate and receipt semantics; obtain exact-head Ubuntu, Windows and repo-policy checks.
5. Reassess public-repository exposure and Issue #57 scope before any merge.

## Non-goals and current disposition

**No code or permission change is authorized by this ADR.** `ALLOWED_OPERATIONS` stays `("status", "doctor")`; no M5 gate migration, provider call, auto-publication, grant rewrite, history rewrite, issue closure or `production_ready` change. ContentOps production release remains **BLOCKED** until quality evidence and Founder review independently pass.
