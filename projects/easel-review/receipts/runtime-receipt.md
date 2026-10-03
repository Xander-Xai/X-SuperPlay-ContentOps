# Easel Runtime Receipt

**Recorded**: 2026-10-02
**Runtime**: `.runtime/easel`
**Engine**: Easel (ZJU-REAL/Easel) — pinned upstream runtime

## Pin

| Field | Value |
|---|---|
| repo | `ZJU-REAL/Easel` |
| release | `v0.2.1` |
| tag ref | `refs/tags/v0.2.1` |
| tag object | `b101c4f1e2204ceaf808f13ed0201e0fe78021d9` |
| expected commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| acquisition | `release_archive` |

No auto-upgrade. Upgrade requires explicit Founder approval.

## Acquisition log

Strategy A — `git fetch origin 3fe2d9904...` against the GitHub Smart HTTP
endpoint: **timed out** (120s, no progress). The previously attempted fetch had
left two aborted temp packs
(`.runtime/easel/.git/objects/pack/tmp_pack_*`, ~439 MB total) and no refs — a
broken, non-clone state with an empty working tree.

Strategy B — GitHub Release tarball via authenticated `gh`:

```
gh api repos/ZJU-REAL/Easel/tarball/v0.2.1
```

produced a 456 MB archive whose top-level directory is `ZJU-REAL-Easel-b101c4f/
` (tag object prefix). Extracted to `.runtime/easel` (982 files).

The archive carries **no `.git` metadata**, so identity is *not* proven by
`.git HEAD`. It is proven by content.

## Verification

Three independent signals:

1. **Tag resolution** — `gh api repos/ZJU-REAL/Easel/git/ref/tags/v0.2.1` peels
   to tag object `b101c4f1...`, whose target is commit `3fe2d99...`. The
   archive directory name `ZJU-REAL-Easel-b101c4f` matches that tag object.
2. **Per-file content hash** — every upstream tree blob at commit `3fe2d99`
   was compared against the local file's `git hash-object`:

   ```
   upstream blobs : 982
   match          : 982
   mismatch       : 0
   missing        : 0
   local-only     : 0
   VERIFIED_CONTENT_IDENTICAL
   ```

   Version corroboration: `pyproject.toml` → `version = "0.2.1"`;
   `CHANGELOG.md` head → `## [0.2.1] - 2026-09-24`.
3. **Reproducible re-verification (2026-10-03)** — the comparison is now a
   committed, runnable tool rather than a one-off claim:

   ```
   $ python scripts/verify_easel_runtime.py --resolve-tag
   status: VERIFIED · 982/982 blobs matched · 0 mismatch / 0 missing / 0 extra
   tag v0.2.1 resolves to 3fe2d9904c1619281ef57f81d9ee0b7854998399 (match)
   ```

   A tamper negative-test (one appended line in a scratch copy) flips it to
   `MISMATCH`, exit 1, naming the file — the check can fail, so the pass means
   something. `scripts/resolve_easel.py` is the single resolver used by both
   `doctor.py` and `run_v1.py`; it rejects a `.runtime/easel` whose git remote
   is not ZJU-REAL/Easel and refuses unpinned trees (the legacy `Easel/` clone
   at `4b9c03c` is never silently selected).

Machine-readable provenance: [`runtime/easel-runtime.json`](../../../runtime/easel-runtime.json).

## Broken runtime disposed

The pre-existing `.runtime/easel` was **not** a valid Easel checkout: it held
only two aborted `tmp_pack_*` files and no refs, no HEAD, no working tree. It
was renamed to `.runtime/easel.broken-fetch-20261002/` rather than deleted, so
the state is auditable. It is untracked (`.runtime/` is gitignored) and can be
reclaimed once this receipt is accepted.

Note: a real ZJU-REAL clone also exists at `Easel/` (remote
`https://github.com/ZJU-REAL/Easel.git`), but it is a **shallow clone pinned at
commit `4b9c03cf...`, not `v0.2.1`**, with no tags. It is therefore not the
production engine; `.runtime/easel` is.

## Doctor

`python -m easel doctor` (`PYTHONIOENCODING=utf-8`):

```
Easel — 环境检查

  Python >= 3.10                           OK
  Python venv module                       OK
  Node.js >= 24.16                         OK
  FFmpeg                                   OK
  openclaw command                         OK
  OpenClaw >= 2026.6.11                    OK
  Python package: fastapi                  FAIL   (pip install -e .)
  Python package: uvicorn                  FAIL   (pip install -e .)
  Python package: sse_starlette            FAIL   (pip install -e .)
  Python package: multipart                FAIL   (pip install -e .)
  Web frontend build                       FAIL   (cd web/frontend && npm ci && npm run build)
  Playwright Chromium                      OK
  .env (API Key)                           FAIL   (ANTHROPIC_API_KEY or EASEL_LLM_API_KEY + EASEL_LLM_BASE_URL)
  OpenClaw model routing                   OK
  OpenClaw gateway (localhost:18789)       OK
  Skills synced                            OK
  openclaw/openclaw.json5                  OK
  skills/openclaw/                         OK
  scripts/gateway.ps1                      OK
```

Honest reading of the FAILs (**10-02 run: 6 FAIL / 13 OK / 19 check rows** — the
count was re-checked against fresh runs on 2026-10-03; an earlier draft of this
receipt and the video script said "5", which undercounted the Web frontend
build):

- The four missing Python packages, the web frontend build and the missing
  `.env` are **Web workbench** dependencies. V1 uses the video production path
  (SKILL orchestration + `assemble.py`, both stdlib-only), so these do not gate
  the video pipeline. They are recorded, not silenced — and they are the
  on-screen evidence for shot 5 (`15-easel-doctor-fails.png`).
- `.env (API Key)` — the doctor looks for an LLM key in the *runtime* root
  `.env`, which does not exist yet. The working LLM credential lives in the
  OpenClaw `easel` profile config, which is what the agent actually routes
  through (see "OpenClaw model routing OK" and the successful ping).

## Ping

`python -m easel ping`:

```
[easel] 连通性测试

  Step 1: Gateway healthz (localhost:18789)          OK
  Step 2: OpenClaw agent via Gateway (say PONG)      OK

✓ 全部通过
```

## 2026-10-03 re-run (current state)

The default-profile OpenClaw gateway that was serving `127.0.0.1:18789` on
10-02 has since stopped, and it will not restart: its agent database needs a
schema migration (`openclaw doctor --fix` on the **default** profile — the
user's own tool state, deliberately left untouched by this repo).

The easel profile gateway (config `~/.openclaw-easel/openclaw.json`,
port **37289**) runs fine and serves the real agent round-trip.

Current results, re-run today on the pinned runtime:

```
doctor : 12 OK / 7 FAIL (19 check rows)
         (the 10-02 list — 13 OK / 6 FAIL — plus "OpenClaw gateway
         (localhost:18789) FAIL" now that the default gateway is down)
ping   : Step 1 FAIL (healthz@18789) / Step 2 OK (agent round-trip via 37289)
```

Root cause of the step-1 failure, read from upstream source: the healthz probe
is **hardcoded** to `http://127.0.0.1:18789/healthz` in
`easel/commands/ping.py:56` and `easel/commands/doctor.py:120`.
`EASEL_GATEWAY_PORT` (gateway_questions.py:42) only steers the WS channel, not
the healthz probe. So doctor/ping's gateway row tracks the *default* gateway,
not the easel one. The video states this on screen instead of claiming
"ping 全通". Rebinding the easel profile to 18789 would make both rows green
but changes user-level config — pending explicit Founder approval; the pipeline
does not need it (TTS + assemble never touch the gateway).

## Gateway + model routing (2026-10-02 record)

The `easel` OpenClaw profile runs its own gateway on **127.0.0.1:37289**
(config `~/.openclaw-easel/openclaw.json`, `gateway.port: 37289`).

Two upstream issues had to be worked around to make routing live. Both are
environment/config fixes — **no Easel source was modified**:

1. **Provider URL scheme.** The profile's `models.providers.anthropic.baseUrl`
   was using a plain-HTTP base URL (port 80) for the LLM provider. In this
   network port 80 is blackholed (connect timeout); HTTPS is fine. The gateway
   log showed the failure as `LLM request failed: network connection error |
   fetch failed | failoverReason=timeout`. Changed the scheme to `https://`.
   Backup at `~/.openclaw-easel/openclaw.json.bak-20261002`.
   Verified directly: the same request over HTTPS returns HTTP 200.

2. **Port mismatch in `gateway.ps1`.** `scripts/gateway.ps1` hardcodes
   `$Port = 18789` for its health probe, but the `easel` profile binds 37289.
   So *start* always reported "already running" (probing the unrelated default
   gateway) and never launched the easel gateway; *status* reported "running"
   on the same false positive. The gateway was started explicitly on 37289
   instead. `easel ping` step 2 is the authoritative check, and it passes.

Neither workaround edits pinned upstream files.

## Conclusion

```
EASEL_RUNTIME PASS
acquisition=release_archive
release=v0.2.1
expected_commit=3fe2d9904c1619281ef57f81d9ee0b7854998399
verified=true (982/982 blob hashes; re-verified 2026-10-03 via scripts/verify_easel_runtime.py)
doctor=12 OK / 7 FAIL (2026-10-03; 6 on the Web workbench path + gateway-healthz
      row red because upstream hardcodes the probe to 18789 — see re-run note)
ping=Step 2 (agent round-trip via easel gateway 37289) OK; Step 1 (healthz@18789) FAIL
```
