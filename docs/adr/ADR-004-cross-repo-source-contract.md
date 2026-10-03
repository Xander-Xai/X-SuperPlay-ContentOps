# ADR-004: Cross-repo source contract

## Status

ACCEPTED

## Context

ContentOps should serve all Xander-Xai business repos, not just one. But not auto-scan all repos.

## Decision

- `config/repos.yaml` defines which repos are enabled
- `RepoSourceAdapter` normalizes all source types into `SourceArtifact`
- New repo: add to config, no custom code
- Private repo: `permission_status: restricted` → Human Approval required
- No auto-publishing from any repo

## Consequences

- Any repo can call ContentOps via standard contract
- Business repos don't need video-specific code
- Historical forks are excluded by default
