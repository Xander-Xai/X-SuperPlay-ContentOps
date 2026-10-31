# ADR-010: A trusted grant source, atomic consumption, and one managed execution gate

Status: Proposed — implemented behind an opt-in entry point; not a dependency of M5
Date: 2026-10-31

> **Trust model:** a grant is not a credential the caller invents. It is derived
> from an existing human decision record, anchored by digest, issued only by a
> configured Owner identity, and spendable exactly as many times as it says.
> Editing either record is detectable. Nothing here is a substitute for the
> adapter's runtime lock, the M5 rights gate or human review.

Issue: #57
Related: ADR-009 (the decision), ADR-008 (`media-use` adapter), ADR-005 (human approval)

## Context

ADR-009 merged a pure decision function. Two things it deliberately could not
do:

1. **Provenance.** A pure function cannot check where a grant came from, so a
   grant invented in memory only had to *claim* a provenance string.
2. **Atomicity.** `uses_consumed` was a number the caller supplied, so two
   concurrent callers could both read `0` and both run.

Both are filesystem questions. This ADR answers them without adding a second
authorization ledger.

## Decision

### 1. The anchor is the record that already exists

The repository already has one authoritative human record per project:
`receipts/human-review.json`. It ships with `decision: null` and the note *"this
file is not an approval"*.

A skill grant (`receipts/skill-grant.json`, schema
`contentops.skill-execution-grant/v1`) is a derived artifact. It does not carry
the decision; it references the decision:

```
skill-grant.json --approval.sha256--> receipts/human-review.json
                                        decision: APPROVED
                                        reviewer, reviewed_at
```

`load_grant` refuses unless **all** hold:

| Check | Refusal code |
|---|---|
| the grant record exists and parses | `NO_GRANT_RECORD` / `GRANT_UNREADABLE` |
| its schema is the expected one | `GRANT_SCHEMA` |
| the issuer is in the configured Owner list | `ISSUER_NOT_APPROVED` |
| the referenced review record exists | `APPROVAL_MISSING` |
| its `decision` is exactly `APPROVED` | `APPROVAL_NOT_APPROVED` |
| `reviewer` and `reviewed_at` are filled | `APPROVAL_INVALID` |
| the review digest still matches the approved digest | `APPROVAL_TAMPERED` |
| operations and counts are well-formed | `GRANT_INVALID` |

The Owner list comes from `CONTENTOPS_OWNER_IDENTITIES`. Unset means **no
identity is trusted**, so a clean environment authorizes nothing.

This does not create a competing ledger: `human-review.json` remains the only
human decision record, and there is exactly one grant record per project.

### 2. Atomic consumption

`consume()` spends a use by creating `receipts/grants/<grant_id>/use-NNNN.json`
with `O_CREAT|O_EXCL`. Two racing callers both scan the directory; exactly one
`open()` succeeds and the other gets `FileExistsError` and continues to the next
slot or refuses with `USES_EXHAUSTED`. A read-then-write counter would let both
win; an exclusive file creation does not.

A test runs eight concurrent callers against a single-use grant and asserts
exactly one success.

### 3. The gate order

`src/contentops/skills/execution_gate.py`:

```
load trusted grant -> evaluate -> consume atomically -> adapter -> receipt
```

Refusals at any step return a receipt with `execution.state = NOT_EXECUTED` and
never call the adapter. Once a use is consumed it is spent even if the adapter
then fails; the failure and the spent use are both in the receipt.

### 4. What the adapter still owns

The gate passes an injected executor. In `scripts/skill_execute.py` that executor
is the real `MediaUseAdapter`, so the adapter's own gates still run unchanged:
runtime lock verification, offline-only, no paid path, no cross-project reuse.
The M5 stage's `rights_reviewed` gate and Founder review are untouched.

**Only read-only operations (`status`, `doctor`) are exposed.** `resolve`,
`adopt` and `ingest` write into a project; exposing them requires the grant
vocabulary to name their effects first, and is a separate decision.

### 5. Legacy M5 is unchanged

`scripts/m5_production.py` does not import `execution_gate` or `grant_source`,
and a test asserts it. The verified M5 chain keeps its existing trust boundary.
Making authorization a mandatory M5 dependency requires a separate Owner-approved
migration decision.

## What this proves, and what it does not

| Claim | Status |
|---|---|
| No execution grant exists without a recorded `APPROVED` human decision | proven by tests |
| Editing the review after approval is detected | proven by tests |
| Two concurrent callers cannot both spend a single-use grant | proven by tests (8 threads) |
| A refusal never reaches the adapter | proven by tests (recorder sees no call) |
| The adapter's own gates are not bypassed | structural: the gate calls the adapter, it does not replace it |
| **Tamper-proof against an attacker with repository write access** | **not claimed** — this is tamper-evident and Owner-gated, not an OS boundary |
| **Signing / non-repudiation** | **not implemented** — no keys are used |
| **Real-runtime authorized execution** | **not demonstrated** — no project currently carries an `APPROVED` review, so every real grant load correctly refuses |

The last row matters: the tests exercise the gate with an injected recorder, and
the real CLI was run against `projects/m5-media-use` where it correctly refused
with `NO_TRUSTED_GRANT`. No authorized real execution has occurred, and none is
claimed.

## Consequences

- An operator must write two records to enable one execution: the human review
  decision and the grant. That friction is the point.
- A spent use is permanent. Re-running requires a new grant, which is visible.
- The Owner identity list becomes a deployment input; an unset variable fails
  closed rather than open.
- If a second gate ever appears, this ADR is the contention point: there must be
  one consumption ledger per project.

## Alternatives rejected

| Alternative | Rejected because |
|---|---|
| Store the approval inside `skill-grant.json` | it would become the decision record itself, duplicating `human-review.json` |
| Reuse `human-review.json` as the grant | a video-publication review would then authorize unrelated future skill runs |
| A counter file updated with read-then-write | not atomic; two callers can spend the same use |
| Sign grants with a private key | real, but adds key custody to a layer that does not need it yet; digest anchoring is testable today |
| Wire the gate into `scripts/m5_production.py` | changes the failure mode of an already-verified chain without Owner approval |

## Verification

| Suite | Tests |
|---|---|
| `tests/test_trusted_grant_source.py` | 15 |
| `tests/test_execution_gate.py` | 17 |
| `tests/test_skill_execution_authorization.py` (ADR-009) | 33 |

Plus `python scripts/dev_check.py` and the subprocess policy check.
