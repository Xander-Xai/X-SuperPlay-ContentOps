# Skill Registry and Doctor

[English](SKILL-REGISTRY.md) | [简体中文](SKILL-REGISTRY.zh-CN.md)

> One resolver, three questions: what exists, which copy wins, and what can it
> reach. The doctor never executes a skill.

## Entry point

`scripts/skill_route.py` is the only resolver. This change adds inspection; it
does not create a second catalog or a second skill engine.

| Command | Answer |
|---|---|
| `python scripts/skill_route.py --sources` | every declared catalog root, present or absent |
| `python scripts/skill_route.py --list` | every deduplicated skill |
| `python scripts/skill_route.py --match "<deliverable>"` | ranked candidates |
| `python scripts/skill_route.py --resolve <name>` | every exact copy, including shadowed ones |
| `python scripts/skill_route.py --doctor` | roots, duplicates, permissions and unsafe paths |

Add `--json` for a machine-readable record.

## Catalog roots

| Priority | Root | Track |
|---:|---|---|
| 1 | `.runtime/easel/skills/openclaw` | pinned Easel runtime |
| 2 | `Easel/skills/openclaw` | working Easel checkout |
| 3 | `vendor/gzh-thinktank/gzh_未来智能/skills` | vendored 公众号 |
| — | `~/.agents/skills` | shared store, resolved separately |

A name in more than one root is indexed once, from the earliest root. The later
copy is reported as `shadowed`; `--doctor` counts every collision.

The XHS skill library is **not** a catalog root on this branch. It is part of the
unmerged migration and is under the rights review in issue #56/#51.

## Five separate layers

| Layer | Owner | This PR |
|---|---|---|
| 1. Directory discovery | `skill_route.py` | yes |
| 2. Information diagnosis | `skill_route.py --doctor` | yes |
| 3. Licence record | the skill's own front matter / LICENSE; legal clearance is separate | reports, does not clear |
| 4. Permission declaration | the skill's own permission fields | counts, does not grant |
| 5. Execution authorization | the producer / account route and the execution gate in #57 | **not provided** |

The doctor is layers 1–2. It may report that a licence is declared, unknown or
restricted, and that a permission field exists. It never turns either into an
execution authorization.

## Doctor fields

| Field | Meaning |
|---|---|
| `roots[].exists` / `skills` | whether each root is present and how many `SKILL.md` files it has |
| `shared.exists` / `skills` | whether the shared store is present |
| `duplicates` | names with more than one copy and the tracks that hold them |
| `missing_description` / `missing_name` | front-matter gaps |
| `permission_declarations` | how many skills declare `allowed-tools`, `permissions`, `tools` or `requires` |
| `rights` | declared licences, unknown rights and restricted (AGPL/GPL) skills |
| `archived` | skills under `_archive/`; provenance, never dispatched |
| `credential_hints` / `paid_hints` | text that suggests a credential or paid dependency; a review signal only |
| `unsafe_paths` | a catalog skill whose resolved path leaves the checkout and declared roots |
| `dangling_links` | a shared-store link whose target does not exist |
| `execution` | always `authorized: false`; `scope: diagnosis_only`; `remaining_gate: #57` |

`ok` is false only when no skill exists or a catalog path leaves the trusted
roots. A duplicate is a warning: priority already chose one copy, and the
collision is visible. Rights-unknown, restricted and archived skills are
reported; they are not dispatched by default.

## Current snapshot

On the audit host (2026-10-31), with the pinned Easel runtime absent and the
shared store present:

```text
gzh              ok       40 skills
shared           ok      225 skills
total                    267
duplicates                16
permissions               15/267 declare a permission field
rights declared           67 declared, 199 unknown, 1 restricted
archived                   9 (never dispatched)
credential hints          87
paid hints                30
unsafe paths               0
dangling links             0
execution                 NOT AUTHORIZED — diagnosis only; gate remains #57
DIAGNOSIS OK
```

These are host-dependent evidence, not a permanent count. A clean checkout
without `.runtime` or the shared store reports those roots as `absent` and still
passes when the vendored 公众号 catalog is present.

## Boundaries

- The doctor does not install, upgrade, execute or sandbox a skill.
- A declared permission field is a review signal, not an authorization system.
- A declared licence is a record, not a legal clearance; `OWNER_ATTESTED` and
  `RIGHTS_UNKNOWN` are not public-release approvals.
- A platform-specific skill is not made valid for another platform by being
  visible to the resolver.
- A rights-unknown, restricted or archived skill must not be dispatched by
  default. The execution gate remains #57.
