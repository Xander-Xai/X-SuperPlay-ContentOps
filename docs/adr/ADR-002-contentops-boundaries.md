# ADR-002: ContentOps boundaries

## Status

ACCEPTED

## Context

Easel is a Creator Content Operating System. X-SuperPlay-OPC-Blueprint is the Business Source of Truth. They must not overlap.

## Decision

ContentOps owns: source ingestion, evidence/claim binding, content run state, assets, provider receipts, QC receipts, publish receipts, performance references.

OPC owns: business judgment, commercial facts, problem/opportunity/offer management.

ContentOps does NOT copy business facts from OPC. It stores only references.

## Consequences

- No business logic in ContentOps
- Content results flow back to OPC as references, not as commercial decisions
- Easel stays as execution engine, not business brain
