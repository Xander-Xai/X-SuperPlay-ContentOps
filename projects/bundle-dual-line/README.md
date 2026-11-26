# Bundle Video Sample

One Strategy Content Bundle (`CB-20261102-001`) feeds the retained video sample:

| Output | Project | State |
|---|---|---|
| Video | `projects/bundle-dual-line-video/` | 22.47 s MP4, h264 1080x1920 + AAC; QC `WARN`; `PENDING_FOUNDER_REVIEW` |

The video handoff carries bundle digest
`4836a1bfa3b1a3faaaec22486d9ae6804ccb7a56e498c0d0b86c0dffd60920c0`
and source mapping `SRC-20261102-001 -> adr016`. It names the Bundle file
(`bundle_path: projects/bundle-dual-line/bundle.json`, `bundle_scope: repo`), so
the pipeline refuses to build from a handoff whose Bundle has since changed.
The handoff does not carry `publish_authorized: true`.

## What actually ran

```powershell
python scripts/bundle_handoff.py projects/bundle-dual-line/bundle.json `
  --account explorer --format VIDEO --project-slug bundle-dual-line-video `
  --source-map SRC-20261102-001=adr016 `
  --out-project projects/bundle-dual-line-video

python scripts/m5_production.py projects/bundle-dual-line-video
```

No provider was called and no network was used. The video used Windows SAPI
narration and the pinned Easel composer.

## What is not committed

`final/`, `assets/voice/`, `assets/captions/` and `work/` are gitignored.
The receipts and scripts are committed. The MP4 exists only on the machine that
ran the command; a clean clone must re-run the chain to reproduce it.

## Honest boundaries

- QC `WARN` is a duration-range warning on a 22.47 s sample, not publication approval.
- The host itself is `HOST_BLOCKED` on this machine. The video did not start the
  host; it used the pinned composer adapter.
- 0 publications.
