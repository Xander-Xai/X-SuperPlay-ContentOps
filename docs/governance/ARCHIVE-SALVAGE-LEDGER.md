# Archive salvage ledger (three-state, read-only)

Generated 2026-11-11 during governance round 5. Source: archive snapshot commit
`7aef6ae` on `archive/minimax-wt-snapshot-20261110`.

## Boundary

- Comparison is **path + blob** against `main`: it proves a file is absent from
  `main`, not that its functionality is missing. Re-implementations under other
  paths are not detected by this method.
- The archive branch is a **third, independent snapshot**; #149 / #150 salvaged
  the two island tags, not this branch.
- Classification below is an **automatic first pass** and requires Owner review.
  No file was copied, moved, changed or deleted to produce this ledger.
- The branch must be retained. Any deletion requires a separately approved,
  per-file disposition and a verified backup.

## States

| State | Meaning | Default disposition |
|---|---|---|
| `SALVAGE-CANDIDATE` | Code / script / skill / config that may be worth re-landing | Evaluate against `main`; re-land via a narrow PR only if still needed |
| `EVIDENCE-ONLY` | Receipts, QC reports, licences, fonts, binary assets | Keep in the archive; do not copy into `main` by default |
| `MANUAL-REVIEW` | Project inputs, HTML, motion specs, storyboards | Owner decides per item |

## Counts

- `SALVAGE-CANDIDATE`: **15**
- `EVIDENCE-ONLY`: **49**
- `MANUAL-REVIEW`: **49**
- Total absent from `main`: **113**

## Per-file classification

| Path | Initial state |
|---|---|
| `docs/governance/HUASHU-EXECUTION-AUTHORIZATION-REQUEST.md` | `SALVAGE-CANDIDATE` |
| `projects/huashu-motion-p01-20261106/.om/renders.jsonl` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-p01-20261106/assets/fonts/LICENSES.md` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-p01-20261106/assets/fonts/NotoSansSC-500.woff` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-p01-20261106/assets/fonts/NotoSansSC-900.woff` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-p01-20261106/assets/fonts/OFL.txt` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-p01-20261106/index.html` | `MANUAL-REVIEW` |
| `projects/huashu-motion-p01-20261106/vendor/GSAP-LICENSE.html` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-p01-20261106/vendor/GSAP-LICENSE.txt` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-p01-20261106/vendor/gsap.min.js` | `MANUAL-REVIEW` |
| `projects/huashu-motion-p01-20261106/vendor/om.js` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/assets/motion/paper-texture.svg` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/huashu-motion/index.html` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/huashu-motion/project.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/asset-mapping.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/specs/p01.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/specs/p02.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/specs/p03.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/specs/p04.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/specs/p05.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/specs/p06.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/motion/visual-spec.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/project.yaml` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/receipts/render-status.json` | `EVIDENCE-ONLY` |
| `projects/huashu-motion-sample/script/storyboard.json` | `MANUAL-REVIEW` |
| `projects/huashu-motion-sample/sources/sample-design-note.md` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/project.yaml` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/README.md` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/claim-verification.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/compose.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/human-review.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/m5-manifest-bridge.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/m5-run.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/media-manifest.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/narration-padded-4s.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/narration.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/p01-huashu-motion-record.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/qc-report-huashu-p01-bridge-technical-20261107.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/qc-report-huashu-p01-bridge-technical-20261107.md` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/script-check.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/source-artifacts.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/receipts/subtitles.json` | `EVIDENCE-ONLY` |
| `projects/huashu-p01-bridge-technical-20261107/script/claims.json` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/script/master.md` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/script/script.json` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/script/storyboard.json` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/sources/diagrams/README.md` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/sources/documents/README.md` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/sources/recordings/README.md` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/sources/screenshots/README.md` | `MANUAL-REVIEW` |
| `projects/huashu-p01-bridge-technical-20261107/sources/urls/README.md` | `MANUAL-REVIEW` |
| `projects/m5-manifest-bridge-e2e-20261106/project.yaml` | `MANUAL-REVIEW` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/claim-verification.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/compose.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/human-review.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/m5-manifest-bridge.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/m5-run.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/media-manifest.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/narration.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/qc-report-m5-manifest-bridge-e2e-20261106.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/qc-report-m5-manifest-bridge-e2e-20261106.md` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/script-check.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/source-artifacts.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/receipts/subtitles.json` | `EVIDENCE-ONLY` |
| `projects/m5-manifest-bridge-e2e-20261106/script/claims.json` | `MANUAL-REVIEW` |
| `projects/m5-manifest-bridge-e2e-20261106/script/master.md` | `MANUAL-REVIEW` |
| `projects/m5-manifest-bridge-e2e-20261106/script/script.json` | `MANUAL-REVIEW` |
| `projects/m5-manifest-bridge-e2e-20261106/script/storyboard.json` | `MANUAL-REVIEW` |
| `projects/m5-manifest-bridge-e2e-20261106/sources/fixture-note.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-1024-motion-20261107/project.yaml` | `MANUAL-REVIEW` |
| `projects/x-superplay-1024-motion-20261107/receipts/README.md` | `EVIDENCE-ONLY` |
| `projects/x-superplay-1024-motion-20261107/receipts/build-technical-preview-easel.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-1024-motion-20261107/receipts/media-manifest.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-1024-motion-20261107/receipts/p6-native-motion-preview.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-1024-motion-20261107/receipts/skill-execution-approval.draft.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-1024-motion-20261107/script/technical-preview-storyboard.json` | `MANUAL-REVIEW` |
| `projects/x-superplay-1024-motion-20261107/sources/diagrams/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-1024-motion-20261107/sources/documents/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-1024-motion-20261107/sources/recordings/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-1024-motion-20261107/sources/screenshots/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-1024-motion-20261107/sources/urls/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/project.yaml` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/README.md` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/build-technical-preview-easel.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/claim-verification.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/media-manifest.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/p6-native-motion-preview.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/skill-execution-approval.draft.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/source-artifacts.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/receipts/visual-rough-cut.json` | `EVIDENCE-ONLY` |
| `projects/x-superplay-future-intelligence-motion-20261107/script/claims.json` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/script/technical-preview-storyboard.json` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/script/visual-rough-cut-storyboard.json` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/sources/diagrams/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/sources/documents/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/sources/recordings/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/sources/screenshots/README.md` | `MANUAL-REVIEW` |
| `projects/x-superplay-future-intelligence-motion-20261107/sources/urls/README.md` | `MANUAL-REVIEW` |
| `runtime/huashu-art-motion-baseline.json` | `MANUAL-REVIEW` |
| `scripts/contentops_video_local.py` | `SALVAGE-CANDIDATE` |
| `scripts/copy_strategy.py` | `SALVAGE-CANDIDATE` |
| `scripts/huashu_execute.py` | `SALVAGE-CANDIDATE` |
| `scripts/native_motion_preview.py` | `SALVAGE-CANDIDATE` |
| `skills/contentops-native-motion/SKILL.md` | `SALVAGE-CANDIDATE` |
| `src/contentops/media/manifest_m5_bridge.py` | `SALVAGE-CANDIDATE` |
| `src/contentops/media/motion_manifest.py` | `SALVAGE-CANDIDATE` |
| `src/contentops/skills/huashu_execution.py` | `SALVAGE-CANDIDATE` |
| `tests/fixtures/generate_m5_manifest_bridge_project.py` | `SALVAGE-CANDIDATE` |
| `tests/test_huashu_execution_gate.py` | `SALVAGE-CANDIDATE` |
| `tests/test_huashu_motion_manifest.py` | `SALVAGE-CANDIDATE` |
| `tests/test_huashu_motion_sample.py` | `SALVAGE-CANDIDATE` |
| `tests/test_m5_manifest_bridge.py` | `SALVAGE-CANDIDATE` |
| `tests/test_native_motion_preview.py` | `SALVAGE-CANDIDATE` |

---

Refs #147, #155. Generated by a read-only local audit; not a receipt of
any salvage or deletion action.
