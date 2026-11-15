# Upstream Easel Policy

[English](UPSTREAM-EASEL.md) | [简体中文](UPSTREAM-EASEL.zh-CN.md)

> How X-SuperPlay-ContentOps relates to the Easel upstream.

## Core Principle

```text
Production tracks stable releases only.
Upstream main is monitored for early-warning signals,
not consumed as production runtime.
```

## Current Pin

| Property | Value |
|---|---|
| Repo | https://github.com/ZJU-REAL/Easel |
| Tag | v0.3.0 |
| Commit | `bb3c8ff0463f36c202454d74171682ba6e470cb1` |
| Tree digest | `c26fc96a653c0ff25ef3bc7486eee372c81f44e67d5ff2c30f1786c63c7d4ec8` (1073 blobs) |
| Release date | 2026-10-12 |
| Adopted | 2026-11-15 (`scripts/easel_engine.py switch v0.3.0`) |
| Lock file | `runtime/easel.lock.json` — **derived** from the registry below; do not edit by hand |
| Source of truth | `runtime/easel-pins.json` — its `active` engine is what the lock projects, and code reads it instead of carrying a commit |
| Provenance | `runtime/easel-runtime-v0.3.0.json` (per-engine; the legacy single file stays v0.2.1's) |
| Local path | `.runtime/easel-v030/` (gitignored) |
| Acquisition | Pinned archive rebuild, installed by `scripts/easel_engine.py install`, which compares every file against `runtime/easel-workbench-upstream-tree.json` (or the overlay record for tuning) before copying |
| Verification | 1071 baseline blobs matched upstream + 14 overlay files matched their recorded digests, verified in overlay mode against the local pinned tree cache |
| Rollback tree | v0.2.1 / `3fe2d99` at `.runtime/easel/`, 982 blobs verified, `python scripts/easel_engine.py switch v0.2.1` |
| Switch record | `runtime/easel-engine-switch.json` — append-only |

## Rules

1. **No auto-upgrade.** Upstream upgrades require Founder approval.
2. **No upstream modification.** Extension via ADAPTER pattern only.
3. **No fork.** Fork is last resort, requires ADR.
4. **No main as production.** Upstream main is a compatibility radar, not a deployment source.
5. **Upgrade process:**
   - New release detected → CHANGELOG review
   - Diff relevant components
   - Run regression suite
   - Golden projects PASS
   - Founder approval
   - Update lock file

6. **Two trees, two roles.** Since 2026-11-15 `.runtime/easel-v030/` (v0.3.0) is
   the **production engine**; `.runtime/easel/` (v0.2.1) is the **rollback tree**
   and stays installed so a bad render can be undone with one command. Both are
   declared in `runtime/easel-pins.json`; only `active` moves. The earlier
   extracted `D://Projects//Easel-Workbench` remains a preserved snapshot. Moving
   `active` requires the upgrade gate below and goes through
   `scripts/easel_engine.py switch`, which verifies before it writes. See
   *Workbench instance* at the end of this document.

7. **Legacy clone remains on disk.** `Easel/` (commit `4b9c03c`, not the
   production pin) is not accepted by the production resolver. Its two local
   video-script files were rescued into the workbench overlay; the original
   clone and its uncommitted work have not been deleted. The source of the
   previously observed environment leak has not been established.

## Easel Upgrade Gate

Only an explicit Upgrade Issue allows:

```text
Acquire new release
    ↓
Verify provenance
    ↓
Run upstream diff analysis
    ↓
Run unit tests
    ↓
Run Windows tests
    ↓
Run 3 golden renders
    ↓
Compare receipts
    ↓
Human Review
    ↓
Founder approval
    ↓
Update lock
```

Any step FAIL → keep old pin.

## Easel Compatibility Matrix

| Easel Area | ContentOps Dependency | Regression Required |
|---|---|---|
| TTS | High | voice smoke |
| assemble/video | Critical | 3 golden renders |
| Windows subprocess | High | Windows CI/local |
| model registry | Medium | provider contract |
| doctor | Medium | doctor regression |
| gateway | Medium (target host) | gateway tests; never run direct |
| publishing | Medium (target host), execution denied | guard tests |
| Web Workbench | Medium (target host), read-only guard | host guard tests; no direct `0.0.0.0` |

## Upstream Delta Ledger

| Upstream | ContentOps | Decision |
|---|---|---|
| Easel v0.2.1 | pinned, installed | rollback tree since 2026-11-15 |
| Easel v0.3.0 | **adopted 2026-11-15** | production; adopted by digest, not tag (ADR-012 D3) |
| Easel main | monitored | no production consumption |
| next release | pending | compatibility gate |

Dynamic SHAs are not duplicated here. Real-time values come from `runtime/easel.lock.json` and the watch script output.

## v0.3.0 delta (measured 2026-11-01)

| Property | Value |
|---|---|
| Released | 2026-10-12 |
| Distance from the pin | 158 commits, 300 changed files |
| Breaking for this repository | **yes** |
| Decision | not adopted (ADR-012 D3) |

Three facts decide it:

1. **Skill paths moved.** Every skill moved from `skills/openclaw/` to
   `skills/builtin/`, and `auto-short-video/scripts/assemble.py` changed. The
   ContentOps composition, card, article and skill-catalog adapters now support
   both roots, preferring `openclaw` for the production pin. Focused path and
   guard tests pass, but this is not render or runtime acceptance.
2. **The tag was force-replaced.** Upstream published v0.3.0, then replaced it
   while keeping the version number. A tag that can be replaced is not a pin.
   Any future adoption must record a **content digest**, not only a tag.
3. **The scope is large.** The release adds a multi-agent execution engine
   (OpenClaw / Codex / OpenCode / ACP / chat-only) and changes install,
   login and artifact handling — a wider blast radius than a patch release.

Adoption, when it happens, runs the full upgrade gate above plus a digest
pinned release archive.

The v0.3.0 `web/app.py` also exposes settings/bootstrap, gateway restart,
local-agent/model-selection and artifact-archive routes. The ContentOps host
continues to deny those routes; representative deny tests are in
`tests/test_easel_host_guard.py`. v0.3.0's dependency manifest adds
`requests>=2.32,<3` and a broad media/runtime dependency set. The candidate has
not had that full dependency set installed or validated with `pip check`.

Candidate-only local composition, card audit and article validation each have
an explicit `--workbench-runtime` switch. They share
`resolve_easel_workbench()`, which requires an upstream, overlay-source and
generated-profile verification pass. Default commands continue to select the
v0.2.1 production runtime.

On Windows, the candidate entry points are:

```powershell
python scripts/assemble_easel.py projects/<project> --workbench-runtime --out-name easel
python scripts/render_article.py projects/<project> --workbench-runtime
```

Candidate videos are written below `work/easel-v030-candidate/<run-id>/final/`
and article previews below `work/easel-v030-article/<run-id>/`; their receipts
are separate files under the project `receipts/`. These commands require the
existing project inputs and verified candidate runtime. The current changes
have not been run or accepted; candidate output remains subject to QC and human
review, with `production_ready=false` and `publish_authorized=false`. Windows
Agent isolation and execution are not established by these commands.

## Host adoption (ADR-016, 2026-11-02)

The Owner adopted the full Easel system as the production base. That changes
the **target** surface, not the pin: v0.2.1 stays read-only and no v0.3.0
upgrade is authorized. The host is served only through
`src/contentops/easel/` on loopback with a read-only allowlist; the upstream
`0.0.0.0`/`CORS *` entry point is never executed directly. A capability being
present upstream is still not evidence that this repository verified it.

## Upstream Watch

```bash
python scripts/check_easel_upstream.py
```

Checks pinned release vs latest release vs main. Classifies impact areas. Never modifies the lock file.

### Impact Levels

| Level | Description |
|---|---|
| NONE | docs-only, unrelated platform skill |
| LOW | minor internal refactor, no watched interface change |
| MEDIUM | Windows behavior, TTS, assemble, doctor, gateway, provider registry, video pipeline |
| HIGH | new stable release, security fix, breaking runtime interface, video assembly behavior change, provider contract change |

### Noise Control

Daily watch runs, but only NEW STABLE RELEASE or MEDIUM/HIGH watched-path changes produce issue updates. No per-commit issue spam.

### Watcher Prohibitions

The watcher never:
- edits `runtime/easel.lock.json`
- downloads or replaces production Easel
- opens automatic upgrade PRs
- merges anything
- modifies ContentOps code

The watcher only: DETECT → CLASSIFY → REPORT.

## Verification Tool

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

Checks all 982 upstream blobs against local files. Tamper test included.

## Workbench instance

The Owner's 2026-11-12 decision is to run a mature Easel as the base and tune it,
not to keep calling the pinned v0.2.1 library. The current candidate was
reconstructed from the full commit archive on 2026-11-13. The earlier extracted
tree is retained unchanged as a historical snapshot:

```
D:\Projects\_worktrees\easel-v030-rebuild-20261113b  recorded v0.3.0 candidate + overlays
D:\Projects\Easel-Workbench                         earlier extracted snapshot, preserved
.runtime/easel                                       (this repo) production engine, v0.2.1
```

| Property | Value |
|---|---|
| Version | v0.3.0, commit `bb3c8ff0463f36c202454d74171682ba6e470cb1` |
| Upstream tree digest | `c26fc96a653c0ff25ef3bc7486eee372c81f44e67d5ff2c30f1786c63c7d4ec8` |
| Skill root | `skills/builtin/` (v0.3.0 moved them out of `skills/openclaw/`) |
| Tuning recorded in | `runtime/easel-workbench-overlay.json` |
| Verified with | `python scripts/verify_easel_runtime.py --overlay` |
| Clean rebuild | `python scripts/rebuild_easel_workbench.py --destination <new-absolute-path>` |
| Frontend | `npm ci` and `npm run build` completed; exact dist inventory is in `runtime/easel-workbench-frontend-build.json` |
| Host status | Historical 2026-11-13 evidence: the earlier candidate without the `b` suffix had an extra file and failed closed; the separate `20261113b` candidate subsequently passed the recorded source, overlay and frontend checks. The offline-only host served a profile/draft/receipt flow and stopped. Later code changes have not been rerun, and browser UI, real Agent isolation and gateway execution remain unverified. See `projects/easel-live-ui-check-20261113-path-bound/receipts/local-acceptance-closeout.md` and `windows-plan-status-20261114.md` in that receipt directory. |

The rebuild command downloads the archive for the full pinned commit, rejects
links/special files and path traversal, checks every extracted upstream blob,
copies only repository-owned skill sources, regenerates profiles from account
DNA, and verifies with generated-profile digests. It requires an absent target
under an existing parent and never overwrites. The rebuild command itself does
not install npm packages or build the frontend. For the current candidate,
`npm ci` and `npm run build` were run separately and the resulting dist inventory
was recorded. To check another rebuilt instance, pass its path explicitly with
`python scripts/verify_easel_runtime.py --overlay --generated-profiles --workbench <absolute-path>`.
The explicit `--workbench` target overrides the instance path in the overlay
record; the default verifier checks the recorded instance. Generated-profile
mode additionally checks those files against current account DNA.

`runtime/easel-workbench-upstream-tree.json` is a local index of upstream paths
and Git blob IDs. The verifier accepts it only when its full tree digest and
entry count match the overlay record; it then compares the selected runtime and
overlay bytes as before. The index can be acquired once with
`python scripts/cache_easel_upstream_tree.py` (public network required, no
overwrite). The offline startup path after this change has not been exercised.

**Why a verifier mode instead of "don't verify".** A byte comparison cannot
express "escal plus my changes": any local difference is a MISMATCH. Weakening
the comparison would make an unrecorded edit invisible. So overlay mode keeps the
full comparison and subtracts only what the record names:

- the **upstream baseline** must match the pinned commit byte for byte;
- every present overlay file must have a declared SHA-256 digest and match it;
- anything else that differs is still a failure.

Generated files, including the served frontend build, are excluded from this
comparison. Verification therefore does not establish frontend artifact provenance.
The workbench host separately requires `runtime/easel-workbench-frontend-build.json`:
it binds the frontend build to the pinned source commit, `package-lock.json`,
Node/npm versions, the reviewed `npm run build` command, and the exact `dist`
file inventory. Missing or changed artifacts block startup and browser page or
asset reads. This manifest is an integrity receipt, not a cryptographic signature.

That is what makes tuning auditable — the record names exactly which files are
ours, and a change anywhere else is still caught. A test pins this: the overlay
suite fails if an *unrecorded* file differs.

**Tuning is never a reason to drop a gate.** The workbench runs behind
`src/contentops/easel/`: loopback bind, audited read allowlist, and upstream
publish / login / credentials / settings / env-install / delete routes denied
before upstream. The candidate also has ContentOps-owned offline draft,
evidence-draft, and Agent workspace preparation/cancellation/result-collection
routes; reads and writes are bound to an existing project and account. These
routes do not start an Agent or call a model or gateway.
A tuned workbench is a working surface, not publication authority.

## See Also

- [ADR-001](adr/ADR-001-easel-runtime.md) — Easel runtime decision
- [ADR-022](adr/ADR-022-easel-v030-workbench-candidate.md) — staged v0.3.0 workbench candidate
- [ADR-006](adr/ADR-006-upstream-upgrade-policy.md) — Upgrade policy
