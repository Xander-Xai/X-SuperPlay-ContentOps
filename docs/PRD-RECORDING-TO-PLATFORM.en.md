# PRD — Manual Screen Recording → Two Accounts → Multi-Platform Delivery

[简体中文](PRD-RECORDING-TO-PLATFORM.md) | [English](PRD-RECORDING-TO-PLATFORM.en.md)

> Last verified: 2026-11-16 on `feat/173-easel-m0-pin`.
> Status: **Proposed** — requirements document; R1 has landed, the rest has not started.
> This document turns the real production line "I record the screen by hand → the project
> processes it → two accounts → several platforms" into acceptance criteria. Every
> "target / planned / not executed" statement below refers to something that has not
> happened yet.

## 0. Metadata

| Item | Value |
|---|---|
| Role | Production-line requirements: recording intake, two-account forking, platform adaptation, publishing authorisation |
| Relation to `PRD-EASEL-V030-FOUNDATION.md` | That document replaced the engine and the cockpit. This one covers the work that runs on top of them |
| Relation to `PRD.md` | Does not supersede it. Re-opens §6 publishing under the four tiers and carries both production lines through to platform delivery |
| Active engine | Easel v0.3.0 / `bb3c8ff0463f36c202454d74171682ba6e470cb1` (`runtime/easel-pins.json`, `active`) |
| Executed this round | R1 (recording intake gate) + account-DNA pin drift fix + M3 close-out. No publishing, no `Easel/` cleanup |
| Approver | Founder (Xander-Xai) |

---

## 1. Three questions, answered first

### 1.1 Is the requirement finished

**Not entirely.** What is finished is "the engine is adopted"; what is not finished is
"your production line runs end to end".

| Ask | State | Evidence |
|---|---|---|
| Adopt the latest ZJU-REAL/Easel as the engine | **Done** | `runtime/easel-pins.json` `active=v0.3.0`; `.runtime/easel-v030` VERIFIED (1071 baseline blobs + 14 overlay files, tree digest `c26fc96a…`) |
| The engine swap keeps production working | **Done** | `projects/m5-easel-pin` renders on v0.3.0, QC PASS, output sha256 **byte-identical** to v0.2.1 |
| Workbench usable | **Done** | `HOST_READY`, no blockers; one offline-task POST/GET reads back four artefacts, both authorisation flags false |
| Governance gates mounted in the engine | **Closed this round** | `extensions/contentops-gates/SKILL.md` + registry entry; `skill_route.py` accepts `root: repo` |
| My manual recordings become material the project processes | **Partial (first slice this round)** | Today `local_assets` registers user video as `evidence_capable: false`, `LOCAL_PREVIEW_ONLY` — it **cannot count as evidence**. The new gate is the first slice, not the whole path |
| Two accounts, different rules | **Partial** | The DNA already carries a `manual_recording` axis (1024 `ALLOWED_CROPPED`, Future Intelligence `FORBIDDEN`), but it is enforced only after QC, never at intake |
| Adapt to different platforms | **Partial** | `config/platforms/video-platforms.yaml` holds nine shape specs with `check()`; but **zero real publications**, eight of nine registry rows `PLANNED` |

In one line: **the engine has been replaced and the cockpit works; the throttle (recording
material) and the gearbox (platform delivery) are still disconnected.**

### 1.2 Does `D:\Projects\X-SuperPlay-ContentOps\Easel` do anything

**No. Zero calls, zero artefacts, zero receipts.** It is a leftover shallow clone:

| Fact | Value | How verified |
|---|---|---|
| Identity | gitignored directory, HEAD `4b9c03c` (24 commits past v0.2.1), two uncommitted modifications | `git -C Easel status` |
| Size | 2.2 GB (**deleted 2026-11-16**) | directory scan + `reports/audits/easel-legacy-clone-retirement-2026-11-16.md` |
| Accepted by the resolver | **No**, actively refused | `scripts/resolve_easel.py` accepts only registered roots |
| The tree production actually runs | `.runtime/easel-v030` | `runtime/easel-pins.json` → `root` |
| Anyone importing it | Nobody | `grep -rn "Easel/" scripts src` has no business hit |

Deleting it has zero production impact. Keeping it only misleads the next person — or the
next agent — about where the engine lives. Cleanup is R4 and **requires your confirmation**:
That was executed on 2026-11-16: deleted after Founder authorisation, with its two uncommitted modifications compared first and confirmed to be an earlier draft of this repository's own overlay. Evidence: `reports/audits/easel-legacy-clone-retirement-2026-11-16.md`.

### 1.3 Which version is "the latest"

| Statement | Fact | Basis |
|---|---|---|
| "2.0" | Upstream has **no 2.x**. The sequence is v0.1.0 → v0.1.1 → v0.2.0 → v0.2.1 → **v0.3.0** | five tags, five releases |
| "Latest" as latest release | **v0.3.0 (2026-10-12)**, already the production engine | `check_easel_upstream.py`: `release_update_available=false`, `recommendation=NO_ACTION` |
| Upstream `main` head | `e9d86ab4` (2026-11-15), **154 commits / 300 files** ahead of the tag, **unreleased** | GitHub compare `v0.3.0...main` |

So the latest *release* is already adopted and, by your decision, frozen at that version. Those 154 commits do contain things that matter
to you (the WeChat QR-login re-issue fix, the Toutiao login-page misread fix), but they carry
no tag. Under `ADR-012 D3` and `docs/UPSTREAM-EASEL.md`, an unreleased head is not promoted
to production because it "looks newer". Tracking it is R3's candidate-engine flow, separately
authorised.

---

## 2. What I understand your intent to be

1. **Recordings are your only real material.** You capture the real terminal, the real page,
   the real model output by hand; the project trims, narrates, burns subtitles and renders.
   You do not accept an AI drawing posed as a measurement.
2. **Two accounts are two production rules, not one template reskinned.**
   - `x-superplay-1024`: evidence-led (`EVIDENCE_LED`), recording **allowed but must be
     cropped**, 70% of final duration is recording evidence, 25% vector, 5% comparison card.
   - `x-superplay-future-intelligence`: explanatory (`EXPLANATORY`),
     **zero manual recording, zero mouse motion, zero desktop window**, 70% vector animation.
   - `x-superplay-english`: X only — one English post plus one real 16:9 image, no video line.
3. **Platform difference is a hard constraint, not a preference.** Douyin 9:16 with a
   three-second hook; Xiaohongshu is a video-only target (9:16 video, 3:4 cover) with a
   ≤20-character title; Bilibili a 16:9
   long cut with chapters; WeChat/Zhihu/CSDN a rewritten text piece; X a single post.

Every requirement below follows from these three. **If one is wrong, fix this section first,
then the code.**

---

## 3. Current facts (only what can be verified)

| Capability | State | Location |
|---|---|---|
| Import a recording into a project | Exists, but **downgraded to preview material** | `src/contentops/media/local_assets.py`: `evidence_capable: false`, `usage_scope: LOCAL_PREVIEW_ONLY` |
| Treat a recording as real evidence | The judge accepts it (`REAL_EVIDENCE_KINDS` contains `screen_capture`), **the intake does not** | `src/contentops/media/claim_coverage.py` vs `local_assets.py` |
| Per-account recording policy | Exists, enforced only at QC | `src/contentops/media/cut_qc.py::manual_recording_forbidden` |
| Real-source duration floor | Exists, hard gate at 70% | `cut_qc.MIN_REAL_SOURCE_RATIO = 0.70` |
| Per-platform shape specs | Exists, nine platforms, every limit carrying `*_basis` | `config/platforms/video-platforms.yaml` |
| Platform packaging | Exists (offline) | `scripts/video_deliver.py pack` |
| Real publications | **Zero** | eight of nine registry rows `PLANNED`; `x` is `MANUAL_ONLY` |
| Engine rendering | Exists, v0.3.0 | `.runtime/easel-v030` |
| Workbench | Exists, read-only plus offline tasks | `scripts/easel_host.py` |

**The central contradiction of this document**: `x-superplay-1024` demands that 70% of the
duration be recording evidence, while the importer that receives your recordings marks those
bytes as "not evidence". Both statements are true today, so **that film can never pass the 70%
gate** except by hand-editing `sources/assets.json` — which is exactly the hole this PRD closes.

---

## 4. Gaps

| # | Gap | Consequence | Requirement |
|---|---|---|---|
| G1 | Intake withholds evidence status from recordings | The 1024 line always lacks real material and hand-edits JSON | FR-REC |
| G2 | Account policy enforced only after QC | You record, cut and render before learning the account forbids it | FR-ACC |
| G3 | No binding between a recording and a claim | "The picture shows A, the narration says B" is only caught by a human | FR-REC-03 |
| G4 | Platform adaptation is shape validation only, with no variant plan | Manually deciding whether Bilibili needs a 16:9 cut | FR-ADP |
| G5 | Zero publications, no autonomy tiers | Every delivery stops at hand upload | FR-PUB (reuses the four tiers) |
| G6 | `Easel/` residue plus stale pins in account DNA | The engine's identity is misread; data contradicts documents | FR-CLN / FR-DOC |

---

## 5. Target state

```text
your manual recording (mp4/mov)
        │
        ▼
[R1 intake gate]  account policy → crop rectangle → duration/resolution → claim binding → receipt
        │                                  (a FORBIDDEN account is refused here)
        ▼
sources/assets.json  (kind=recording, evidence_capable=true, boundary declared)
        │
        ▼
[VIDEO line] script → narration → storyboard → CutPlan → compose (Easel v0.3.0) → QC
        │                                            ▲ the engine renders, never judges
        ▼
[R2 platform adaptation]  account × platform → variant plan → receipt
        │
        ▼
[R3 publishing tiers]  MANUAL → DRAFT_AUTO → GRAY_AUTO → FULL_AUTO, per platform
```

Three boundaries are unchanged: the engine's bytes are never modified; governance can veto the
engine; the engine never publishes on its own authority.

---

## 6. Functional requirements

Risk levels follow `docs/TEST-PLAN.md` L0–L3.

### 6.1 REC — recording intake

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-REC-01 | Intake reads `account_slug` from `project.yaml`, then `evidence.manual_recording` from the DNA: `FORBIDDEN` → `REFUSED`; `ALLOWED_CROPPED` without a crop rectangle → `BLOCKED`; undeclared account → `BLOCKED` | `python scripts/ingest_recording.py --project <p> --file <f> --claim <id>` has a distinct verdict per path | L2 | R1 ✅ |
| FR-REC-02 | Intake registers the asset as **evidence-capable**: `type=recording`, `origin=SELF_CAPTURED`, `evidence_capable=true`, `distribution_authorized=false`, `requires_human_review=true`; existing rows keep their meaning | the new row has every field; the 70% gate can be satisfied by a real recording | L2 | R1 ✅ |
| FR-REC-03 | Every recording binds a `claim_id`; an unknown claim → `BLOCKED` | receipt `bindings[]` agrees with `script/claim-map.json` | L2 | R1 ✅ |
| FR-REC-04 | The crop rectangle must lie inside the source frame and is recorded for human review of what was cropped away | out-of-bounds → `BLOCKED CROP_OUT_OF_BOUNDS`; receipt carries `crop` and `frame_size` | L2 | R1 ✅ |
| FR-REC-05 | `receipts/recording-intake.json` always carries `production_ready:false` and `publish_authorized:false` | schema test | L1 | R1 ✅ |
| FR-REC-06 | Automatic slicing (silence/scene change → candidate segments plus a CutPlan draft) | a 90-second recording yields candidate segments | L3 | R2 |

### 6.2 ACC — two-account forking

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-ACC-01 | One DNA field drives both intake and QC; no second copy of the policy | `cut_qc.STRICTNESS` and the intake read the same field; a FORBIDDEN account is covered by test | L2 | R1 ✅ |
| FR-ACC-02 | `render.runtime_pin` in the DNA may not contradict `runtime/easel-pins.json` | the two strings agree (fixed this round, v0.2.1 → v0.3.0) | L1 | R1 ✅ |
| FR-ACC-03 | The 70/25/5 split on 1024 mirrors to 70 vector / 25 code / 5 chart on Future Intelligence, with each line's gate applying to its own mix | the same storyboard yields different verdicts per account | L2 | R2 |
| FR-ACC-04 | A project without `account_slug` is `BLOCKED`; there is no default account | `ACCOUNT_UNANNOUNCED` | L2 | R1 ✅ |

### 6.3 ADP — platform adaptation

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-ADP-01 | Generate a **variant plan** from account `platform_roles` × `video-platforms.yaml`: one row per platform with aspect, duration limit, title length, tag count, cover ratio, CTA, uploader | `python scripts/platform_adapt.py plan --project <p>` | L2 | R2 ✅ |
| FR-ADP-02 | The plan must name which platforms need a second render (Bilibili 16:9 long cut) instead of pretending one file fits all | rows carry `requires_variant: true/false` with a reason | L2 | R2 ✅ |
| FR-ADP-03 | Unknown platform, or a platform the account does not declare → `BLOCKED`, never silently skipped | unit test | L2 | R2 ✅ |
| FR-ADP-04 | The plan plans; it neither re-renders nor publishes. `publish_authorized` is always false | receipt schema | L1 | R2 ✅ |

### 6.4 PUB — publishing tiers

Reuses `PRD-EASEL-V030-FOUNDATION.md` §11 unchanged: `MANUAL → DRAFT_AUTO → GRAY_AUTO →
FULL_AUTO`, authorised per platform, Douyin stays `UNCONDITIONALLY_REFUSED`.

| ID | Requirement | Risk | Milestone |
|---|---|---|---|
| FR-PUB-01 | The first `DRAFT_AUTO` pilot is `wechat_article` (the only `publish_mode: DRAFT_ONLY` row), and its `draft_support: NONE` channel must be built first | L3 | R3 |
| FR-PUB-02 | Before any real external write, both the variant plan and the QC receipt must be present | L3 | R3 |

### 6.5 CLN / DOC

| ID | Requirement | Acceptance signal | Risk | Milestone |
|---|---|---|---|---|
| FR-CLN-01 | Before `Easel/` is cleaned, the two uncommitted modifications are diffed and the conclusion recorded; deletion or archiving needs Founder confirmation item by item | a diff conclusion plus a confirmation record | L3 | R4 |
| FR-CLN-02 | The v0.2.1 rollback tree is kept for one full release cycle after R2, then may be archived | registry row still says `role: rollback` | L2 | R4 |
| FR-DOC-01 | This document and its mirror are paired with working bidirectional language links and tracked by `doc-freshness` | `check_i18n.py` / `check_doc_freshness.py` green | L0 | R1 |

---

## 7. Milestones and acceptance

| Milestone | Goal | State | Acceptance |
|---|---|---|---|
| **R0** | Engine adopted (v0.3.0 production + workbench + gates mounted) | **Done** | `python scripts/easel_engine.py show`; `python scripts/easel_host.py status --workbench` |
| **R1** | A recording can lawfully become evidence; account policy applies at intake | **Done this round** | `python tests/test_recording_intake.py`; `python scripts/ingest_recording.py …` |
| **R2** | Platform variant plan (✅ done) + automatic recording slicing (not started, FR-REC-06) | Partial | `python scripts/platform_adapt.py plan --project <p>` |
| **R3** | First real platform draft | Not started | draft receipt + human confirmation timestamp |
| **R4** | `Easel/` and stale pin residue cleaned | Not started (needs confirmation) | diff conclusion + `Easel/` gone + `resolve_easel.py` still OK |

R1 exit criteria (machine-checkable): a FORBIDDEN account is `REFUSED` with the DNA field named;
an `ALLOWED_CROPPED` account without a crop is `BLOCKED` and with a legal crop is `ACCEPTED` and
written with `evidence_capable: true`; the receipt always carries both false flags; a project
without `account_slug` is `BLOCKED` with no default fallback.

---

## 8. Risks

| # | Risk | Signal | Mitigation |
|---|---|---|---|
| R1 | "Evidence-capable" is read as "cleared to publish" | someone treats the flag as distribution authority | the row and receipt both carry `distribution_authorized:false`; publishing still goes through the tiers |
| R2 | A recording shows third-party repository or AI output whose rights are unclear | "that is someone else's interface" | the evidence asserts only "what the screen displayed"; rights stay human-reviewed |
| R3 | The crop is legal but fails to remove desktop or credentials | `CROP_OUT_OF_BOUNDS` passes, a human notices later | receipt keeps `crop` + `frame_size`; R2 adds sampled review frames |
| R4 | Tracking upstream `main` (154 commits) introduces behavioural drift | the render changes | candidate-engine flow: third tree → verify → golden rerun → then switch |
| R5 | Deleting `Easel/` hits the wrong tree | archive or production damaged | diff first, confirm first, record per AGENTS §10; never `Remove-Item -Recurse` on a junction |

---

## 9. Open decisions

| # | Decision | Owner |
|---|---|---|
| 1 | ~~Adopt upstream `main` (`e9d86ab4`) as a candidate engine~~ | **Decided (2026-11-16)**: frozen at v0.3.0, upstream not followed; only Founder-requested changes on the pinned tree |
| 2 | ~~Archive or delete `Easel/` (2.2 GB)~~ | **Decided**: deleted (2026-11-16) |
| 3 | First `DRAFT_AUTO` platform: `wechat_article` or `xiaohongshu_video` (video target; graphic/image-text is out of scope here) | Founder |
| 4 | May a recording contain third-party AI product UI (compliance boundary) | Founder + legal |
| 5 | Retention deadline for the v0.2.1 rollback tree | Founder |

---

## 10. Appendix — what this round actually executed

| File | Purpose |
|---|---|
| `src/contentops/media/recording_intake.py` | intake gate: policy → probe → crop validation → claim binding → asset row → receipt |
| `scripts/ingest_recording.py` | CLI entry |
| `tests/test_recording_intake.py` | four verdict paths plus receipt honesty |
| `config/accounts/*.json` | `render.runtime_pin` corrected from v0.2.1 to v0.3.0 |
| `extensions/contentops-gates/SKILL.md` | gate skill declaration (R0 close-out) |
