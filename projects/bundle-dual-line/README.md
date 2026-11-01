# Bundle Dual-Line Sample

One Strategy Content Bundle (`CB-20261102-001`) feeds two independent outputs:

| Output | Project | State |
|---|---|---|
| Video | `projects/bundle-dual-line-video/` | 21.63 s MP4, h264 1080x1920 + AAC; QC `WARN`; `PENDING_FOUNDER_REVIEW` |
| Graphic text | `projects/bundle-dual-line-graphic/` | manual package + preview; `AWAITING_MANUAL_REVIEW` |

Both handoffs carry the same `bundle_sha256`
`4836a1bfa3b1a3faaaec22486d9ae6804ccb7a56e498c0d0b86c0dffd60920c0`
and the same source mapping `SRC-20261102-001 -> adr016`. Neither carries
`publish_authorized: true`, and neither inherits the other's review.

## What actually ran

```powershell
python scripts/bundle_handoff.py projects/bundle-dual-line/bundle.json `
  --account explorer --format VIDEO --project-slug bundle-dual-line-video `
  --source-map SRC-20261102-001=adr016 --platform douyin `
  --out-project projects/bundle-dual-line-video

python scripts/m5_production.py projects/bundle-dual-line-video

python scripts/bundle_handoff.py projects/bundle-dual-line/bundle.json `
  --account explorer --format GRAPHIC_TEXT --project-slug bundle-dual-line-graphic `
  --source-map SRC-20261102-001=adr016 --platform wechat_article `
  --out-project projects/bundle-dual-line-graphic

python scripts/graphic_package.py `
  --project projects/bundle-dual-line-graphic `
  --handoff projects/bundle-dual-line-graphic/receipts/bundle-handoff-graphic_text.json `
  --input projects/bundle-dual-line-graphic/graphic-input.json
```

No provider was called and no network was used. The video used Windows SAPI
narration and the pinned Easel composer. The graphic line made no render and no
platform draft.

## What is not committed

`final/`, `assets/voice/`, `assets/captions/` and `work/` are gitignored.
The receipts and scripts are committed. The MP4 exists only on the machine that
ran the command; a clean clone must re-run the chain to reproduce it.

## Honest boundaries

- QC `WARN` is a duration-range warning on a 21.63 s sample, not publication approval.
- `wechat_article` is `PLANNED`; the graphic package records `PLATFORM_PLACEHOLDER`.
- The host itself is `HOST_BLOCKED` on this machine. The video did not start the
  host; it used the pinned composer adapter.
- 0 publications.
