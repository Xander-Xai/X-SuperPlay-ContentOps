# ADR-020: Optional external media analysis as a read-only adapter

- Date: 2026-11-09
- Status: PROPOSED — pending integration review / real-video smoke
- Scope: experiment on branch refactor/architecture-adapters-20261109

## Context

M5 already produces video and carries evidence, rights and human-review gates.
Raw reference footage lacks an independent shot-boundary discovery seam.
Adding a second full video pipeline would duplicate rendering and editorial
authority. External image/video tools must not silently become evidence.

## Decision

Use the documented PySceneDetect (BSD-3-Clause) ContentDetector as a local,
optional adapter. On explicit user invocation only, emit a SHA-bound
`contentops.scene-candidates/v1` receipt. This is **source footage
segmentation**, not semantic motion generation or final-video QC.

The receipt describes candidates, not authorized assets. No automatic link
to storyboard, no evidence promotion, no rights approval, no publication, no
provider calls. Source must resolve inside the project root. The optional
dependency is imported lazily; CI injects a fake detector and remains offline.
Any error must stop without fabricating scenes.

## Alternatives

- Another end-to-end video app: rejected (duplicated M5/Easel).
- Frame-only heuristic in ContentOps: rejected (reinvents tested OSS).
- WhisperX: complementary audio alignment, not shot boundary detection.
- Do nothing: retains manual segmentation; acceptable rollback.

## Acceptance

1. CI test has no network or external dependency and rejects path traversal,
   malformed scenes, empty output being promoted and unsafe output paths.
2. Record source hash, detector threshold/version and each proposed timestamp.
3. Prove with a real local, authorized reference MP4 on Windows and Linux
   before status changes from EXPERIMENTAL to VERIFIED.
4. Compare output with manually annotated cuts and record precision/recall and
   operator time saved. Unknown metrics remain unknown.
5. Disable by never invoking the CLI. No changes to M5 assembly paths.

## Consequences

A useful optional input tool with small surface area, but additional package
maintenance when installed. Not a shortcut to evidence quality or publishing.
