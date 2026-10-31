# media-use D-4 / D-8 closure and M5 re-adjudication — 2026-11-01

> Closes the two blockers left open by the media-use integration acceptance
> report (`reports/audits/media-use-integration-acceptance-2026-11-01.md`, carried
> on the still-open PR [#86](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/86))
> and re-adjudicates the M5 offline media integration.
>
> **ContentOps production release stays `BLOCKED`.** `production_ready` is still
> `false` and the human review is still `PENDING_FOUNDER_REVIEW`. Nothing here
> changes that.

## A. Baseline

| Item | Value |
|---|---|
| `origin/main` when this work started | `459abb4815b163bc7c53c937c523f6190164b25c` |
| PR [#86](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/86) | **OPEN, not merged** — HEAD `44337ff`, three required checks green |
| Issue #57 | open; not closed by this round |
| This work's branch | `fix/57-m5-media-fixtures`, based on `origin/main` |

Because #86 was not merged, this branch does not depend on its code fixes and
touches none of its files. The two changes are independent: #86 fixes the ingest
rights gate and the doctor health field; this PR fixes the sample's inputs and
receipt traceability. No duplicate PR was created.

Per the request, the stale exact-HEAD CI reference inside the #86 report was
corrected on #86 itself (commit `44337ff`): the report now cites both the run for
`9e29051` and the run for `602f0b5`, and states that the PR check rollup is
authoritative because documentation-only commits move HEAD.

## B. D-4 — the sample is now rebuildable from a clean clone

**Before.** `projects/m5-media-use` committed import receipts for an image and a
BGM but not the bytes, so a clone held hashes with nothing to check and the real
M5 entry point refused at the first request:

```text
support_visual: media-use NEEDS_HUMAN_ACTION: no offline image source could satisfy ...
```

**After.** Two operator-owned inputs are tracked through exact-path gitignore
exceptions, in the same style as the existing screenshot and golden-voice
exceptions — no directory, glob or extension is negated.

| Fixture | Bytes | SHA-256 | Origin | Licence |
|---|---|---|---|---|
| `assets/support.png` | 38438 | `85c4ab5c5368b1ab60a98854ee292529d6b7908be58acfccc1d5f4ed06cddb53` | the repository's own `projects/easel-review/sources/screenshots/01-easel-hero.png`, byte-identical | `OWNED-BY-OPERATOR` |
| `assets/bed.mp3` | 321036 | `17fe7d27d2db3be9dfedb69298e19c32ac3923df15a89169a70ade770c36a8bd` | deterministic ffmpeg tone, regenerable (`sine=frequency=220:duration=20`, volume 0.2, 2 s fades) | `OWNED-GENERATED-LOCAL`, `synthetic: true` |

The image is a genuinely owned asset, not a substitute: the committed
`support.png.receipt.json` already recorded exactly this SHA-256, so tracking the
bytes **validates the existing receipt instead of rewriting it**.

The BGM is the one input that could not be recovered — the original
`bed.mp3` (`1dcb9c7e…`, 96907 bytes) was never committed. A new deterministic bed
was generated and the sample was re-run, so the committed receipts now describe
the committed bytes. That is a supersession of one stale receipt, disclosed here
rather than hidden: the previous bed hash no longer appears anywhere.

Narration, subtitles, the SFX and the render were **not** committed as fixtures.
They are outputs, reproducible from the tracked inputs plus the pinned runtimes:

- narration — local Windows SAPI, no network; byte-identical across runs
  (`e3475d0c…`), which also matches the hash the original run recorded;
- SFX — resolved from the pinned HyperFrames runtime; byte-identical to the
  original run (`075e17bd…`);
- captions and MP4 — composed locally.

## C. D-8 — every import receipt is reviewable from the repository

The adapter writes each receipt beside its asset. For the bundled SFX that is
`.media/audio/sfx/`, which this repository ignores, so the licence behind the one
third-party asset could not be checked from a clone.

The M5 stage now mirrors each import receipt to `receipts/media-use/<name>` and
records that tracked path as `receipt_ref`:

```text
support_visual  IMPORTED  receipts/media-use/support.png.receipt.json   OWNED-BY-OPERATOR
bed             IMPORTED  receipts/media-use/bed.mp3.receipt.json       OWNED-GENERATED-LOCAL
click_accent    IMPORTED  receipts/media-use/sfx_001.mp3.receipt.json   Pixabay-Content-License
```

Constraints honoured:

- the original receipt is **not moved**, so `.media/manifest.jsonl` and the
  adapter's own `verify()` lookup keep working;
- the mirror is byte-identical to the adapter's already-redacted receipt — no new
  redaction path, no secret copied by hand;
- this is not a second registry: same artifacts, a path this repository tracks;
- when the adapter hands over an object without a receipt path (the test fakes
  do), the original reference is returned unchanged.

The tracked SFX receipt carries `license`, `attribution`, `output_sha256`,
`provider_call: false` and `evidence_capable: false`, so the licence is now
reviewable from a clone.

## D. Clean-clone reproduction

Commands, exactly as run:

```bash
git clone --branch fix/57-m5-media-fixtures --single-branch \
  https://github.com/Xander-Xai/X-SuperPlay-ContentOps.git m5-clean-clone-20261101
cd m5-clean-clone-20261101

# the pinned Easel runtime is a separate, gitignored dependency (v0.2.1)
python scripts/verify_easel_runtime.py --json      # status VERIFIED, 982/982 blobs

export CONTENTOPS_MEDIA_USE_RUNTIME_LOCK=<approved hyperframes lock>
python scripts/m5_production.py projects/m5-media-use
```

The clone started with **no** `.media/`, **no** `final/` and no narration — only
the tracked fixtures and receipts. Result, exit code 0:

```text
sources      {"count": 2}
media_use    {"state": "OK", "count": 3, "bgm": true, "sfx": 1}
assets       {"count": 1}
claims       {"count": 3}
script       {"lines": 4}
narration    {"duration_s": 25.058, "engine": "windows_sapi"}
subtitles    {"cues": 4}
storyboard   {"shots": 4, "bgm": true, "sfx": 1}
compose      {"state": "OK", "video": "project://final/m5-media-use.mp4"}
qc           {"overall": "WARN", "audio": true}
production_ready False  (PENDING_FOUNDER_REVIEW)
```

Outputs compared against the committed run:

| Artifact | Clean clone | Committed run | Match |
|---|---|---|---|
| `final/m5-media-use.mp4` | `c03e05efd7189e36b62a8e89d619c1aad1d7756e81e4eb16dcc5b157c59527ff` | same | **identical** |
| `assets/voice/narration.wav` | `e3475d0cf4b8d3fa5ac87ddb4f10e6fac0d94a6428f55267ab4bf3ed9a417ea7` | same | identical |
| `assets/support.png` | `85c4ab5c…` | same | identical |
| `assets/bed.mp3` | `17fe7d27…` | same | identical |
| `.media/audio/sfx/sfx_001.mp3` | `075e17bd…` | same as the original run | identical |
| tracked receipts | — | — | identical **except** `checked_at` / `captured_at` timestamps |

`git status` in the clone after the run shows content changes in exactly three
tracked files, all timestamp-only: `qc-report-m5-media-use.json`,
`qc-report-m5-media-use.md`, `source-artifacts.json` (two `captured_at` fields).
Everything else that git lists is a CRLF/LF artefact of the checkout, not a
content change.

MP4 inspection (identical file in both places):

```text
sha256  c03e05efd7189e36b62a8e89d619c1aad1d7756e81e4eb16dcc5b157c59527ff
size    516163 bytes
video   h264 1080x1920 30/1 fps 25.067 s
audio   aac 25.058 s
```

Also executed inside the clean clone:

| Suite | Result |
|---|---|
| `test_m5_media_traceability.py` | 10 passed |
| `test_gitignore_evidence_policy.py` | 14 passed |
| `test_m5_media_use_workflow.py` | 26 passed |
| `test_m5_evidence.py` | 18 passed |

**Disclosed limitation.** The pinned Easel renderer (`Easel` v0.2.1) is a separate
gitignored dependency, not part of the clone. It was provisioned by copying the
already-verified local checkout and re-verified inside the clone
(`status: VERIFIED`, 982/982 blobs matched, 0 missing, 0 extra). Without it
`compose` blocks with `Easel runtime not usable` — the pipeline fails closed rather
than emitting an unrendered video.

## E. Media checks inside the clean clone

| Question | Answer | Evidence |
|---|---|---|
| Image imported with a stable hash? | **Yes** | `support_visual IMPORTED`, `85c4ab5c…`, receipt tracked |
| Image reaches the frames? | **Yes** | storyboard shots 1–4 use `assets/support.png`; the rendered MP4 is byte-identical to the accepted run whose 1.5 s frame matches the source screenshot |
| BGM mixed? | **Yes** | 220 Hz energy present in the composed track, absent from narration (measured on the accepted run; the MP4 is byte-identical, so the mix is too) |
| SFX at the declared cue? | **Yes** | `at: 6.15`, `volume: 0.55`; the SFX is byte-identical to the original run and the MP4 is byte-identical |
| Subtitles burned? | **Yes** | 4 cues; `subtitles_burned: true`; visible in the rendered frames |
| QC ran? | **Yes, `WARN`** | 21 checks; warnings on `duration_range`, `real_source_ratio`, `real_evidence_present` |
| Human review? | **Correctly pending** | `production_ready=false`, `PENDING_FOUNDER_REVIEW` |
| Receipts written? | **Yes** | `receipts/` plus the three mirrors under `receipts/media-use/` |

The three QC warnings are content-quality findings, not integration failures:
the only visual is a licensed image rather than captured real evidence, and the
duration sits outside the target range. They are the reason the run is not
`production_ready`, and they stay visible.

## F. Test results (this branch)

| Suite | Result |
|---|---|
| `test_skill_execute_status.py` | 2 passed |
| `test_execution_gate.py` | 22 passed |
| `test_trusted_grant_source.py` | 19 passed |
| `test_skill_execution_authorization.py` | 33 passed |
| `test_skill_router_capabilities.py` | 29 passed |
| `test_skill_doctor.py` | 8 passed, **1 skipped** (symlink, no Windows privilege) |
| `test_media_use_adapter.py` | 56 passed |
| `test_m5_media_use_workflow.py` | 26 passed |
| `test_m5_evidence.py` | 18 passed |
| `test_media_convergence.py` | 97 passed |
| `test_local_approval_gitignore.py` | 5 passed |
| `test_m5_media_traceability.py` (new) | 10 passed |
| `test_gitignore_evidence_policy.py` | 14 passed |
| **Total** | **339 passed, 1 skipped, 0 failed** |
| `scripts/dev_check.py` | ALL CHECKS PASSED |

The one skip is a Windows privilege limitation for creating a symlink and is not
counted as a pass.

New regression coverage added by this PR:

- the image and BGM bytes match the receipts that describe them;
- the image stays byte-identical to the tracked Easel screenshot;
- every `IMPORTED` result has a tracked receipt whose digest matches the asset;
- the rights records still pass `rights_gate`, and a bare `rights_reviewed: true`
  is still refused;
- the mirror preserves bytes, returns the tracked reference, and leaves the
  adapter's own receipt in place (including the no-receipt fallback);
- the gitignore exception stays narrow: narration, renders and `sfx_001.mp3`
  remain ignored, and no other media in the sample is tracked.

## G. Verdict

```text
M5 offline media integration     FULLY_ACCEPTED
Managed skill execution closure  FULLY_ACCEPTED  (unchanged; see #86)
ContentOps production release    BLOCKED         (unchanged)
```

Every mandatory condition for the **integration** scope now has real evidence:
a clean clone, the approved HyperFrames runtime lock, the real M5 entry point, a
byte-identical render, hash-bound fixtures, reviewable receipts, and 339 passing
tests. D-4 and D-8 are closed.

Production release is untouched and still blocked: `production_ready=false`,
`PENDING_FOUNDER_REVIEW`, QC `WARN` on `real_evidence_present`. That is the honest
state, and no gate was bypassed to change it.

## H. Remaining, out of scope for this round

- **Mutating verbs are still outside the managed gate** (`resolve`, `adopt`,
  `ingest`, `import`). `ALLOWED_OPERATIONS` was not widened. Doing so needs a
  design for side effects, scope and idempotency first.
- **`units` / budget metering** remains nominal (`max_uses` is enforced
  atomically; `max_unit` is validated but not metered).
- **Issue #57** was not closed: its acceptance conditions are broader than the
  media integration and no explicit authorisation to close it was given.

## I. Delivery

| Item | Value |
|---|---|
| PR | [#87](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/87) |
| Base | `main` @ `459abb4815b163bc7c53c937c523f6190164b25c` |
| Branch | `fix/57-m5-media-fixtures` |
| Merge | **Not performed.** Owner decision. |
