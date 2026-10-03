# QC Checklist — V1 Video

A video is **production-ready** only if every PASS gate below is satisfied.

## A. File integrity

- [ ] `final.mp4` exists under `projects/<slug>/final/`
- [ ] file size >= 100 KB
- [ ] `ffprobe` parses cleanly (no error)

## B. Video specs

- [ ] 1080x1920
- [ ] 9:16 (1080 × 16 == 1920 × 9)
- [ ] H.264 video codec
- [ ] 30 <= duration <= 120 sec
- [ ] AAC audio codec
- [ ] at least one audio stream

## C. Evidence / Script

- [ ] `project.yaml` exists and parses
- [ ] `source_refs` recorded (>=1)
- [ ] `assets/captions/default.srt` exists
- [ ] at least one real asset (PNG/JPG) under `sources/screenshots` or `sources/diagrams`

## D. Content integrity

- [ ] No fabricated claims (script must reference real evidence)
- [ ] Voice quality is declared (`fallback` only allowed for smoke tests)

## E. Status

| Overall | Publish? |
|---|---|
| PASS | yes — manual publish to platforms |
| WARN | review manually before publishing |
| FAIL | NOT production-ready, regenerate |