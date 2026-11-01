# ADR-009: Skill execution authorization is a grant bound to one request

Status: Proposed — design and deny-path tests only; not wired into any entry point
Date: 2026-10-31

> **Trust model:** `RESOLVABLE` says a capability may be handed to an adapter. It
> does not say a caller may run it. This ADR adds the missing step as an explicit,
> auditable grant, and leaves every existing gate — rights, runtime integrity,
> asset licensing — exactly where it is.
Issue: #57
Related: ADR-008 (`media-use` adapter and runtime lock), `docs/SKILL-REGISTRY.md`,
`security-and-hardening` acceptance in PR #71

## Context

PR #77 merged the skill router into `main`. It answers two questions:

1. **Discovery** — what skills exist on this host, with what licence evidence.
2. **Resolution** — may this declared capability be handed to an adapter.

Both answers are deliberately weak. `--resolve` returns `RESOLVABLE` and, on every
path, `execution_authorized: false`. That was the right shape, but it leaves the
question the product actually needs:

> May *this caller*, acting for *this account*, run *this operation* of *this
> pinned skill version*, now, once?

Three unsafe shortcuts were available and are rejected:

1. Treat `RESOLVABLE` as permission. Resolution ignores who is asking, for which
   account, with what budget, until when.
2. Treat a licence declaration or `provider.path_permitted` as permission. Both
   describe the capability, not the caller.
3. Add a second policy engine next to the adapter and M5 gates. Two authorities
   drift, and the weaker one wins in an incident.

## Decision

Add one small decision layer, `src/contentops/skills/authorization.py`, that
composes existing verdicts with an explicit **grant**.

```
DISCOVERED -> RESOLVABLE -> EXECUTION_REQUESTED -> AUTHORIZED -> EXECUTED
                  \______________ BLOCKED ______________/
```

Only `AUTHORIZED` is produced by the module. `EXECUTED` is recorded by the adapter
that actually ran, from its own receipt — this module never claims a run happened.

### What a grant binds

| Dimension | Why it is in the binding |
|---|---|
| `skill_id`, `skill_version` | a grant for one version must not authorize another |
| `account`, `pipeline`, `stage` | the same skill means different things per track |
| `operations` | the exact verbs; a superset request is refused, never narrowed silently |
| `issuer` vs `subject` | "who approved" and "who runs" are separate, so delegation is expressible without collapsing the two |
| `provenance` | the digest of the approval record the grant came from; a grant with no provenance is refused |
| `issued_at`, `expires_at` | authorization is time-bounded, not permanent |
| `max_units`, `max_uses`, `uses_consumed` | single-execution boundary and budget |
| `revoked`, `revoked_reason` | withdrawal is a first-class state |

### Where authority stays

| Question | Authority | This ADR |
|---|---|---|
| Is the skill declared, rights-verified, in scope? | `runtime/skill-registry.json` + router | consumes the verdict |
| Is the runtime tree intact at spawn? | `MediaUseAdapter.verify_runtime_lock` | does not re-hash, does not replace |
| Are the assets licensed for use? | M5 `media_use` `rights_reviewed` gate | does not re-judge |
| Was there human review? | existing HITL records / `PENDING_FOUNDER_REVIEW` | does not create a second review store |
| **May this caller run this once?** | **this module** | the only new decision |

The module deliberately has no network, no subprocess, no credential, and no
store. A grant must name the approval record it was derived from; locating and
hashing that record is the execution gate's job (ADR-010).

### Default deny, in this order

1. empty identity field, empty operation, or a non-integer/out-of-range count → `EMPTY_FIELD` / `INVALID_NUMBER`
2. no `RESOLVABLE` verdict → `NOT_RESOLVABLE`
3. a verdict that claims `execution_authorized: true` → `UNTRUSTED_VERDICT`
4. no registry entry, or the id is not the declared one → `UNKNOWN_SKILL`
5. the declaration pins no version, or the version differs → `VERSION_MISMATCH`
6. no grant → `NO_GRANT`
7. a grant with no provenance digest → `UNTRUSTED_GRANT`
8. empty grant identity, or invalid grant counts → `EMPTY_FIELD` / `INVALID_NUMBER`
9. revoked → `GRANT_REVOKED`
10. unusable, future-dated or expired → `GRANT_NOT_YET_VALID` / `GRANT_EXPIRED`
11. `issued_at >= expires_at` → `GRANT_WINDOW_INVALID`
12. any bound context differs → `CONTEXT_MISMATCH`
13. subject is not the granted subject → `SUBJECT_MISMATCH`
14. operation not granted → `OPERATION_NOT_GRANTED`
15. uses exhausted → `USES_EXHAUSTED`
16. budget exceeded → `BUDGET_EXCEEDED`
17. otherwise → `AUTHORIZED`

Every blocked path returns `execution_authorized: false` and a machine-readable
reason. A test asserts that no blocked path can report otherwise.

### Implemented here vs the gate's responsibility

| Property | In this module | Gate responsibility (ADR-010) |
|---|---|---|
| Version, account, pipeline, stage, operation, subject binding | enforced | — |
| Empty / invalid numeric input | refused | — |
| Inverted or unusable time windows | refused | — |
| Grant with no provenance | refused | verify the digest against the record |
| Verdict claiming execution authority | refused | call the router in-process; never accept a stored string |
| Unexpired / unrevoked / unexhausted | evaluated from the supplied grant | atomic consumption under concurrency |
| `registry_entry` omission | **refused** (required argument) | supply the real declaration |

The residual limit is stated plainly: a pure function cannot prove where its
arguments came from. Making provenance mandatory turns silent fabrication into a
named refusal, and the gate turns a named digest into a checked one.

## What this does not do

- It does not modify the `media-use` runtime approval, the adapter, or the M5
  `media_use` stage.
- It does not add a grant store, a UI, or an approval workflow.
- It does not verify provenance digests or make consumption atomic; ADR-010 adds
  a trusted source and a gate for that.
- It is not wired into `scripts/m5_production.py`. Wiring needs a separate
  decision, because it changes the failure mode of an already-verified chain.
- It does not close Issue #57 by itself: the final criterion — authorization has
  one authority, untrusted skills are denied by default, and a managed entry
  enforces the check — needs ADR-010 as well.

## Consequences

- A caller can no longer go from `RESOLVABLE` to an adapter call in one step; it
  must present a grant whose binding matches exactly.
- Grants are cheap to record (a frozen dataclass, JSON-serializable) and cannot
  be widened after the fact.
- The one new failure mode is operational: an expired grant blocks work that used
  to be implicit. That is the intended direction — it is discoverable and
  recoverable, unlike an unauthorized run.
- If a second authorization module ever appears, this ADR is the point of
  contention: there must be exactly one decision for a given request.

## Alternatives rejected

| Alternative | Rejected because |
|---|---|
| Put authorization in `skill_route.py` | the router must stay a read-only discovery/resolution tool, and a grant needs a caller identity it does not have |
| Add the checks to `MediaUseAdapter` | the adapter's job is to refuse unsafe bytes, not to identify callers; mixing them makes the adapter untestable in isolation |
| Add a new approval database | would become the second source of truth the doc warns about; the Owner decision already lives in HITL records |
| Time-only tokens without context binding | a token that authorizes "any media-use run" is exactly the cross-account grant this ADR prevents |

## Verification

`tests/test_skill_execution_authorization.py` (33 tests) exercises every deny
reason, input validation, the inverted time window, forged verdicts, grants
without provenance, delegation, the exact-context positive path, the registry
version pin, the no-borrowing rule and the invariant that no blocked decision is
authorized. The module is pure and deterministic; tests pass `now` explicitly.

What the tests do **not** prove, and must not be read as proving: that a grant
came from a real approval, or that two concurrent callers cannot both spend the
same single-use grant. Both require a filesystem and are tested in ADR-010.
