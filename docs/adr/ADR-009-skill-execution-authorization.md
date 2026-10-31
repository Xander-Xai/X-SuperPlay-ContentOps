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
| `principal` vs request `caller` | a grant cannot be borrowed by another caller |
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
store. Grants are supplied by the caller from wherever the Owner decision is
recorded; issuing them is out of scope here.

### Default deny, in this order

1. no `RESOLVABLE` verdict → `NOT_RESOLVABLE`
2. skill id not the declared one → `UNKNOWN_SKILL`
3. pinned version differs from the declaration → `VERSION_MISMATCH`
4. no grant → `NO_GRANT`
5. revoked → `GRANT_REVOKED`
6. unusable, future-dated or expired → `GRANT_NOT_YET_VALID` / `GRANT_EXPIRED`
7. any bound context differs → `CONTEXT_MISMATCH`
8. caller is not the principal → `CALLER_MISMATCH`
9. operation not granted → `OPERATION_NOT_GRANTED`
10. uses exhausted → `USES_EXHAUSTED`
11. budget exceeded → `BUDGET_EXCEEDED`
12. otherwise → `AUTHORIZED`

Every blocked path returns `execution_authorized: false` and a machine-readable
reason. A test asserts that no blocked path can report otherwise.

## What this does not do

- It does not modify the `media-use` runtime approval, the adapter, or the M5
  `media_use` stage.
- It does not add a grant store, a UI, or an approval workflow.
- It is not wired into `scripts/m5_production.py`. Wiring needs a separate
  decision, because it changes the failure mode of an already-verified chain.
- It does not close Issue #57 by itself: the final criterion — authorization has
  one authority and untrusted skills are denied by default — is met by this
  design, but closure is an Owner decision.

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

`tests/test_skill_execution_authorization.py` (20 tests) exercises every deny
reason, the exact-context positive path, the registry version pin, the
no-borrowing rule and the invariant that no blocked decision is authorized. The
module is pure and deterministic; tests pass `now` explicitly.
