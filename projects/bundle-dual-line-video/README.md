# Bundle Dual-Line Video Sample

Bound to `CB-20261102-001` through `project.yaml` `content_bundle`. The M5 run
wrote `receipts/bundle-handoff-video.json` before the sources stage.

| Fact | Value |
|---|---|
| Source | `docs/adr/ADR-016-easel-host-adoption.md` (`adr016`) |
| Source mapping | `SRC-20261102-001 -> adr016` |
| Narration | Windows SAPI, 22.443 s (offline, not production-grade voice) |
| Composition | pinned Easel v0.2.1 via `assemble_easel.run` |
| Output | `project://final/bundle-dual-line-video.mp4` — 21.63 s, 1080x1920, h264 + AAC |
| QC | `WARN` (duration range only), no FAIL |
| Human review | `PENDING_FOUNDER_REVIEW` |
| `production_ready` | `false` |
| Publication | none |

`final/`, `assets/voice/`, `assets/captions/` and `work/` are gitignored; the
MP4 is local until the chain is re-run on another machine. The committed
receipts are the evidence that this run happened.
