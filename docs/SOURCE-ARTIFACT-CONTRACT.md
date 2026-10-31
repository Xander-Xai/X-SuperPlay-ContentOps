# Source Artifact Contract

> Defines the unified input object for all ContentOps workflows.

## SourceArtifact Schema

```yaml
SourceArtifact:
  id:                    # unique identifier (e.g. SRC-20261003-001)
  source_type:           # github_repo | github_file | issue | pr | release | commit |
                         # experiment_receipt | research_report | local_file |
                         # demo_recording | delivery_artifact
  repo:                  # owner/repo (if applicable)
  ref:                   # commit SHA, PR number, issue number, etc.
  title:                 # human-readable title
  created_at:            # when the source was created
  collected_at:          # when ContentOps ingested it

  evidence:              # list of evidence items
    - type:              # screenshot | recording | document | code | data | log
      path:              # relative path within project
      description:       # what it shows

  claims:                # list of extractable claims
    - text:              # the claim
      source_refs:       # which evidence items support it
      verification:      # verified | documented_only | unverified
      confidence:        # high | medium | low
      publishable:       # true | false

  permission:
    visibility:          # public | private | internal
    permission_status:   # public_factual | approved | restricted | forbidden
    publishable_scope:   # what may be published (screenshots, numbers, architecture, code, claims)
    redactions:          # what must be redacted before publishing

  business_refs:         # optional links to OPC
    workstream:          # WS-XXX
    opportunity:         # OPP-XXX
    experiment:          # EXP-XXX
    offer:               # OFF-XXX

  content_eligibility:   # assessment of whether this source is suitable for content
    eligible:            # true | false
    reason:              # why or why not
```

## Rules

- Private repo sources → `permission_status: restricted` → Human Approval required
- No claim without evidence → delete or downgrade to opinion
- Evidence must be real (screenshots, recordings, data), not AI-fabricated
- `publishable_scope` defines what may appear in the final video

## Implementation (v1) — `contentops.source-artifact/v1`

`src/contentops/evidence/` enforces the two rules this contract calls decisive:
no claim without evidence, and evidence must be real. It implements a subset of
the schema above and is deliberately smaller than it.

| Contract field | Implemented as | Notes |
|---|---|---|
| `id`, `source_type`, `title` | same names | |
| `evidence[].path` | `path` | repository-relative; a path outside the repository is refused |
| (derived) | `sha256`, `bytes`, `captured_at` | computed from the file at build time |
| `permission.permission_status` | `permission` | `OWNED` \| `CREATED_BY_OWNER` \| `LICENSED` \| `NONE` |
| (derived) | `evidence_capable` | true only for the three citing permissions; `NONE` is material, never evidence |
| `claims[]` | `script/claims.json` (`contentops.claim-ledger/v1`) | a claim needs an artifact, and a quote that occurs verbatim in its text |
| `claims[].verification` | computed by `ClaimLedger.verify()` | a missing quote, changed bytes or a non-citing artifact is reported, not accepted |
| `publishable_scope`, `redactions` | `sources/assets.json` (`usage_scope`, `restrictions`) | per visual, declared rather than inferred |
| `business_refs`, `content_eligibility` | not implemented | no code reads them yet; adding them without a consumer would be a comment, not a control |

`permission_status` values from the contract map onto the implementation as:
`public_factual` and `approved` → `OWNED` or `CREATED_BY_OWNER`; `restricted` →
`LICENSED` only when the licence is recorded; `forbidden` → `NONE`. Publishing
permission remains a human decision (ADR-005); this layer decides only whether a
source may back a claim at all.
