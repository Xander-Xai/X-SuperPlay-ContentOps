# ADR-010: A trusted grant source, atomic consumption, and one managed execution gate

Status: Proposed — implemented behind an opt-in entry point; not a dependency of M5
Date: 2026-10-31

> **Trust model:** an approval is a human-written record whose *purpose* is
> `skill_execution`. A content review can never become one. Every scope field is
> read from that single record, so there is no derived copy to drift. It is
> spendable exactly as many times as it says, from one machine, and a spent use
> is visible on disk. This is tamper-evident and Owner-gated. It is **not**
> authentication, **not** a signature, and **not** an operating-system security
> boundary. Nothing here replaces the adapter's runtime lock, the M5 rights gate
> or human review.

Issue: #57
Related: ADR-009 (the decision), ADR-008 (`media-use` adapter), ADR-005 (human approval)

## Context

ADR-009 merged a pure decision function. Three questions a pure function cannot
answer stayed open: where a grant came from, whether a grant's own fields are the
ones that were approved, and whether two callers can spend one grant twice.

A first revision of this ADR answered them with a `skill-grant.json` that
*referenced* `receipts/human-review.json` by digest. Review found two real
defects:

1. **Path traversal.** `grant_id` came from editable JSON and was used directly
   as a directory name, so `../..` escaped the project.
2. **Scope drift.** The digest proved the review record was unchanged, but not
   that the grant's account, operations, subject, budget or expiry were the ones
   a human approved. Editing only the grant produced a valid authorization.

Those defects are why the design below differs from the first revision.

## Decision

### 1. One record, and its purpose is explicit

There is exactly one authorization record per project:
`receipts/skill-execution-approval.json`, schema
`contentops.skill-execution-approval/v1`. It requires:

```json
{
  "schema": "contentops.skill-execution-approval/v1",
  "purpose": "skill_execution",
  "approval_id": "apr-2026-10-31-media-use-1",
  "issuer": "<configured Owner identity>",
  "subject": "<the executor this approval names>",
  "skill_id": "media-use",
  "skill_version": "<pinned version>",
  "account": "<one concrete account>",
  "pipeline": "M5",
  "stage": "media_use",
  "operations": ["status"],
  "issued_at": "...", "expires_at": "...",
  "max_units": 1, "max_uses": 1
}
```

`load_grant` refuses unless every check holds:

| Check | Refusal code |
|---|---|
| the record exists and parses | `NO_GRANT_RECORD` / `GRANT_UNREADABLE` |
| its schema is the expected one | `GRANT_SCHEMA` |
| `purpose` is exactly `skill_execution` | `WRONG_PURPOSE` |
| the issuer is in the configured Owner list | `ISSUER_NOT_APPROVED` |
| `approval_id` is one safe path component | `UNSAFE_PATH` |
| account is concrete, not `*` | `GRANT_INVALID` |
| operations and counts are well-formed | `GRANT_INVALID` |
| optional supporting evidence still matches its digest | `EVIDENCE_MISSING` / `EVIDENCE_UNREADABLE` / `EVIDENCE_TAMPERED` |

**A content review never authorizes execution.** `receipts/human-review.json` is
a *video publication* decision; a first revision's digest reference quietly
promoted it into an execution approval. Now it is optional supporting evidence
only: checked for integrity, never consulted for permission. A project that only
has an `APPROVED` review still has no execution approval, and the gate refuses.

### 2. Every scope field is bound in the record that is approved

Because there is no derived copy, there is nothing to edit separately. The
approval's own digest is its provenance, and `evaluate` compares the request
against the grant field by field — skill, version, account, pipeline, stage,
subject, operations, budget, window. Editing any of them changes the digest and
invalidates the approval.

The gate also re-reads the approval immediately before spending. If the record
changed between evaluation and consumption it refuses with `GRANT_CHANGED`, and
a revocation written mid-flight is refused with `GRANT_REVOKED`. Neither spends
a use.

### 3. Path safety

`approval_id` is not sanitised, it is **refused** unless it is a single plain
component (`^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`). Silently rewriting an id would
let two different approvals share one consumption ledger. On top of the pattern,
Windows device names (`con`, `nul`, `com1`…`lpt9`) and names with a trailing dot
or space are refused, because Windows would resolve them to a different path than
the id reads as.

Every path is then resolved and checked for containment in the project root:
the approval record, the evidence record, the `receipts/grants` base, the grant
directory, the request marker and the use markers. `Path.resolve` follows
symlinks, so a symlinked `receipts` or grant directory pointing outside the
project is refused (`UNSAFE_PATH`) rather than written through. Filesystem
errors become structured `GrantSourceError` codes, never a traceback.

Tests assert that a traversal id creates nothing outside the project, and that a
symlinked receipts directory and a symlinked grant directory are both refused
with the outside directory left empty.

### 4. Identity: issuer, subject, and what neither proves

| Role | Where it comes from | What it proves |
|---|---|---|
| issuer | `issuer` field, must be in `CONTENTOPS_OWNER_IDENTITIES` | which identity is *allowed* to have written the approval |
| subject | `CONTENTOPS_EXECUTION_SUBJECT` on the host | which identity the host *claims* is executing |
| caller | the process itself | nothing |

The subject is deliberately not a CLI argument: a caller cannot widen a grant by
typing `--subject someone-else`. It is still only a label the environment
declares. `CONTENTOPS_OWNER_IDENTITIES` is an allow-list, not an authentication
system, and neither variable proves who is typing.

Therefore: with no trusted identity configured, managed execution is **denied by
default**. This mode is honest for one Owner on one workstation. It must not be
described as supporting untrusted multi-user or remote execution; that needs real
authentication, which is a separate Owner-approved decision. A future agent
delegation path must add an explicit delegated-subject field rather than reusing
the Owner allow-list.

### 5. Atomic consumption — one machine, not a distributed guarantee

`consume()` performs two exclusive creations with `O_CREAT|O_EXCL`:

* `request-<sha256(request_id)[:16]>.json` — one attempt per request id, so
  re-sending the same request cannot spend a second use (`DUPLICATE_REQUEST`);
* `use-NNNN.json` — the use slots, so a single-use approval is won by exactly one
  caller (`USES_EXHAUSTED` otherwise).

The request marker is created first, so a duplicate request never even looks for a
free slot. Tests cover eight threads and four **separate processes** racing for
one single-use approval: exactly one wins. Grant ledgers are per `approval_id`, so
two approvals never share consumption state.

The honest limit: this is mutual exclusion on one local filesystem. It does not
claim distributed Exactly-Once on a network filesystem where `O_EXCL` semantics
are weaker, and a crash between the request marker and the use marker leaves a
spent attempt with no execution — visible, and refused as a duplicate on retry.

### 6. One operation per managed call

The gate runs `operations[0]`. Rather than silently ignore the rest, it refuses a
request with any other number of operations (`OPERATIONS_MUST_BE_SINGLE`). Batch
execution needs its own atomicity and budget semantics and is a separate
decision.

### 7. Gate order and receipts

`src/contentops/skills/execution_gate.py`:

```
single operation -> load approval -> evaluate -> re-read -> consume
                 -> adapter -> sanitized receipt
```

A refusal at any step records `decision.state = BLOCKED` and
`execution.state = NOT_EXECUTED`, and never calls the adapter. Once a use is
consumed it is spent even if the adapter fails; the receipt says `FAILED` and
carries the spent use, so a failed run never reports success.

Receipts are written to `receipts/executions/<approval_id>-use-NNNN.json` with an
exclusive create: an existing receipt is never overwritten, and a failure to
write one is recorded as `receipt_write_failed` rather than hidden. Before
writing, the payload is sanitized recursively — bearer-style tokens, `api_key=` /
`token=` / `secret=` / `password=` values, `sk-`/`ghp_`/`github_pat_` keys, and
absolute Windows and POSIX host paths are replaced. A test injects an error
string carrying a token, a key and two host paths and asserts none survive into
the receipt.

### 8. Legacy M5 is unchanged

`scripts/m5_production.py` does not import `execution_gate` or `grant_source`, and
a test asserts it. The verified M5 chain keeps its existing trust boundary.
Making authorization a mandatory M5 dependency requires a separate Owner-approved
migration decision.

## What this proves, and what it does not

| Claim | Status |
|---|---|
| No execution approval exists without a record whose purpose is `skill_execution` | proven by tests |
| A content review cannot be upgraded into an execution approval | proven by tests |
| Editing any scope field invalidates the approval | structural (one record, digest covers all fields) |
| A traversal or symlink escape writes nothing outside the project | proven by tests |
| Two threads or two processes cannot both spend a single-use approval | proven by tests |
| A duplicate `request_id` cannot spend a second use | proven by tests |
| A revocation written mid-flight is detected before spending | proven by tests |
| An existing execution receipt is never overwritten | proven by tests |
| Credentials and host paths do not reach a receipt | proven by tests |
| A refusal never reaches the adapter | proven by tests (recorder sees no call) |
| The adapter's own gates are not bypassed | structural: the gate calls the adapter, it does not replace it |
| **Distributed Exactly-Once across machines or network filesystems** | **not claimed** — single-machine local filesystem only |
| **Tamper-proof against an attacker with repository write access** | **not claimed** — tamper-evident and Owner-gated, not an OS boundary |
| **Signing / non-repudiation** | **not implemented** — no keys are used or generated |
| **Authenticated caller identity** | **not implemented** — the subject is a host-declared label |
| **Real-runtime authorized execution** | **pending Owner approval** — see below |

The last row matters. The tests exercise the gate with an injected recorder. The
real CLI was run against `projects/m5-media-use`, where it correctly refused with
`NO_TRUSTED_GRANT`; the adapter was not called, no provider request was made and
no media changed. No authorized real execution has occurred, and none is claimed
until an Owner writes an approval naming the project, identity, operation and
window.

## Consequences

- An operator writes one record to enable one execution. It names its own scope,
  so there is no second file to keep in sync.
- A spent use is permanent. Re-running requires a new approval, which is visible.
- The Owner identity list and the execution subject are deployment inputs; unset
  variables fail closed rather than open.
- There must be one consumption ledger per project. A second gate would be the
  contention point.

## Alternatives rejected

| Alternative | Rejected because |
|---|---|
| Derive the grant from `human-review.json` and anchor it by digest | a video-publication review is not a skill-execution approval; the derived scope could be edited independently |
| Use an editable CLI `--subject` | a caller could impersonate the authorized executor by typing a name |
| Sanitise an unsafe `approval_id` instead of refusing it | two different approvals would share one consumption ledger |
| A counter file updated with read-then-write | not atomic; two callers can spend the same use |
| Batch operations in one managed call | `operations[0]` would run while the rest were silently ignored |
| Sign grants with a private key | real, but adds key custody to a layer that does not need it yet; generating an unprotected key would only fabricate security |
| Wire the gate into `scripts/m5_production.py` | changes the failure mode of an already-verified chain without Owner approval |

## Verification

| Suite | Tests |
|---|---|
| `tests/test_trusted_grant_source.py` | 19 |
| `tests/test_execution_gate.py` | 22 |
| `tests/test_skill_execution_authorization.py` (ADR-009) | 33 |

Plus `python scripts/dev_check.py` and `scripts/check_subprocess_policy.py`.
