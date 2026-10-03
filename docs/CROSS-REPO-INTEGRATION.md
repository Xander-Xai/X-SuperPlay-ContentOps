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

## Rules

- New repo: add to `config/repos.yaml`, no custom code
- Private repo: `permission_status: restricted` → Human Approval required
- No auto-publishing from any repo
- Business judgment stays in OPC Blueprint, not in ContentOps
