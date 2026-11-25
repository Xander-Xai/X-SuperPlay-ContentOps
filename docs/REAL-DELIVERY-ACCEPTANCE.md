# Real delivery acceptance / 真实交付验收 (#199)

> Last verified: 2026-11-26. Candidate engineering work only; no new media or human acceptance.

## Research and adoption boundary

- [Motion Canvas official rendering](https://github.com/motion-canvas/motion-canvas/blob/main/packages/docs/docs/getting-started/rendering/index.mdx) describes the editor Render operation and output directory. Keep the pinned editor/export/import path; compile success is not a real video export.
- [FFmpeg ffprobe](https://ffmpeg.org/ffprobe.html) supplies actual stream geometry/duration. Existing QC measures output and probes native landscape sources; a file with 16:9 dimensions alone cannot prove original landscape composition.
- [video-material-finder](https://github.com/30bewater/video-material-finder) is a discovery reference for source/license/attribution metadata, not an authorization or installed dependency. [b-roll-finder](https://github.com/louisedesadeleer/b-roll-finder) is a possible search methodology, not a verified match for the local shared-skill reference. Do not install or fetch media until the operator verifies the exact upstream identity, version, license and rights. Stock/generated illustrations cannot replace 1024 real capture.

## Operator acceptance

1. Use the existing pinned Motion Canvas template and `scripts/motion_canvas_adapter.py --prepare` with explicit spec, placement and asset ID. A blocked exit is expected until the editor has actually rendered the selected scene. Use `--import-editor-export --exported-mp4 <project-relative-file>` on the genuine MP4, with the same spec/placement/asset and purpose. Preserve the historical state01 blocked receipt; do not overwrite it to claim a render.
2. For the 1024 production project, import only operator-authorized real footage through the existing intake and rights gate; record crop, privacy, claim and source bindings. Run the stable production entry and final QC. A real-source label cannot override explicit generated/non-evidence metadata. Invalid timeline numbers block; the displayed rounded ratio cannot authorize a result below 70%.
3. For native Bilibili, use the actual landscape project and per-shot media. Run `python scripts/qc_video.py projects/<slug> --video <file>.mp4`. Inspect all checks, not merely exit code (WARN is not acceptance). Keep source hashes, full decode and visual review. The old 15-second test-only receipt is historical, not a full film.
4. Run both account pipelines using the exact Easel pin and separate account DNA. No automatic provider charges, permissions or publication. Require Founder review of full outputs, not synthetic fixtures. Record final SHA-256 and all relevant receipts in the operator's local workspace; keep private media off GitHub.

## Exit criteria

- Genuine mc-state01 editor export + verified import, technical checks and M4.5 registration.
- 1024 authorized footage with >=70% real visible time, actual native media checks and rights/claim review.
- Future Intelligence account-native deliverable, no forbidden recording, separate claim coverage.
- Full decode, review of readable frames and audio, clean-checkout reproduction, and human disposition.
- No `production_ready` or `publish_authorized` upgrade from this runbook or CI alone.

The duration calculation still relies on declared timeline and asset metadata; it cannot determine visual authenticity or occlusion. Human review and actual hash-bound media remain required.

Native candidate QC now requires FFmpeg full-stream decode and a stable SHA-256 of the actual output bytes. A corrupt file, missing tool or changed output fails. The regression creates only a tiny synthetic clip; it is not a real delivery.
