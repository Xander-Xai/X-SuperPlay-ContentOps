# Cross-repo Integration

> How any Xander-Xai business repository can use ContentOps.

## Repo Registry

```yaml
# config/repos.yaml (planned)
repos:
  Xander-Xai/Beauty-Industry-RAG-QA-System:
    enabled: true
    content_roles: [portfolio, engineering]
  Xander-Xai/Customer-Service-AI-Agent:
    enabled: true
  Xander-Xai/X-SuperPlay-OPC-Blueprint:
    enabled: true
    content_policy: governed
```

Only `enabled: true` repos may be used as sources. No auto-scanning all repos.

## RepoSourceAdapter (planned)

Supports source types: GitHub Repository, File, Issue, PR, Release, Commit, Experiment Receipt, Research Report, Local File, Demo Recording, Delivery Artifact.

All sources normalize into a `SourceArtifact` (see [SOURCE-ARTIFACT-CONTRACT.md](SOURCE-ARTIFACT-CONTRACT.md)).

## Content Bundle intake (Strategy → ContentOps)

Strategy owns the Content Kernel and the Content Bundle template. ContentOps
consumes a Bundle; it never creates a second one
([ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md)).

```bash
python scripts/content_bundle.py check path/to/content-bundle.yaml
python scripts/content_bundle.py summary path/to/content-bundle.yaml
```

The check is structural: identity shape, account treatments, the
`baseline | enhanced | experimental` lane, the `default | strict_evidence` hint,
asset capability and evidence-role enums, claim binding for `direct_evidence`,
the four fail-closed invariants, and credential-shaped fields. Passing the check
means the record may be consumed. It never means approved, rendered, or
published.

A Bundle is a plan. `bundle_is_not_published_content` is one of its own
invariants and this repository enforces it rather than restating it as intent.

### Handoff format

This repository consumes **JSON** by default. Strategy's template is YAML, and
YAML requires PyYAML, which CI does not install. Two honest options: export the
Bundle as JSON before handoff, or install PyYAML locally and pass the `.yaml`.
Without either, the loader returns `BUNDLE_NEEDS_PYYAML` — an explicit refusal,
not a silent partial read. A YAML Bundle is not directly consumable on a clean
checkout.

### What a passing check does not prove

`content_bundle.py check` is structural. `PASS` means the record is well formed
and its own invariants are asserted. It does **not** verify that `claim_refs`
resolve to a `ClaimLedger`, that permissions and source evidence were reviewed,
or that the content is publishable. Those belong to the evidence and rights
layers. Neither a Bundle `PASS` nor a QC `PASS` is a publication approval.

## Rules

- New repo: add to `config/repos.yaml`, no custom code
- Private repo: `permission_status: restricted` → Human Approval required
- No auto-publishing from any repo
- Business judgment stays in OPC Blueprint, not in ContentOps
