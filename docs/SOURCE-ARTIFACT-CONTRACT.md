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
