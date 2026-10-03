# ADR-001: Easel as pinned runtime

## Status

ACCEPTED

## Context

X-SuperPlay needs a content production runtime. Research (2026-10-01) evaluated 6 GitHub projects. Easel v0.2.1 was selected: 114 executable Skills, CLI + FastAPI + OpenClaw Gateway, native China platform support, Apache-2.0.

## Decision

Pin Easel v0.2.1 at commit `3fe2d9904c1619281ef57f81d9ee0b7854998399`. Acquire via release archive. Verify by per-file content hash (982/982 blobs). No auto-upgrade.

## Consequences

- Upstream changes require Founder approval + regression suite
- No upstream source modification (ADAPTER pattern only)
- Windows subtitle path bug worked around in `assemble_easel.py` (orchestration, not source edit)
- Web workbench unverified (6 doctor FAILs) — does not block video pipeline
