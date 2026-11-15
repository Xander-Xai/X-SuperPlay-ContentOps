# ADR-022: Easel v0.3.0 workbench candidate

Status: **Accepted for staged implementation — Owner directive, 2026-11-13**
Date: 2026-11-13
Issue: [#173](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/173)
Related: [ADR-016](ADR-016-easel-host-adoption.md), [ADR-017](ADR-017-coding-agent-driver.md), [ADR-021](ADR-021-stable-production-gates.md)

## Context

ADR-016 adopts the pinned Easel host as the production base, but its accepted
runtime is v0.2.1 and its host surface is read-only. Issue #173 evaluates the
v0.3.0 workbench as a candidate entry point. The v0.3.0 source tree is distinct
from `.runtime/easel/`; its complete commit is
`bb3c8ff0463f36c202454d74171682ba6e470cb1` because the upstream tag has changed.

The candidate adds a React frontend, account profile files and possible agent
execution. HTTP route filtering alone cannot establish frontend provenance,
profile freshness, tool restrictions or operating-system isolation. Existing
ContentOps production receipts remain anchored on the v0.2.1 pipeline.

## Decision

### D1 — Keep separate runtime roles

`.runtime/easel/` remains the v0.2.1 production candidate and stays pinned by
`runtime/easel.lock.json`. The v0.3.0 tree is a workbench candidate only. It does
not change production routing, existing receipts, the production lock or the
upgrade gate.

### D2 — Treat workbench provenance as two independent proofs

The workbench overlay verifier must prove the complete upstream baseline and
require SHA-256 digests for every present overlay file. The frontend build needs
a separate receipt binding the source commit, `package-lock.json`, Node/npm
versions, `npm run build`, and the exact `web/frontend/dist` inventory. An
existing `dist` directory or an upstream source match is not build provenance.
Missing or changed frontend evidence blocks the guarded host and browser asset
reads.

For the v0.3 candidate, the guarded upstream page serves `/` and `/assets/`
from the verified dist inventory, checks the requested bytes before returning
them, and denies legacy `/static/` and `/onepage` resources outside that
inventory. A restrictive content-security policy limits external resources;
this is not proof of operating-system network isolation. This change has not
been run or browser-tested.
The candidate host explicitly labels HTML, JavaScript modules, CSS and SVG
with browser-compatible MIME types rather than relying on Windows registry
defaults; this change is also untested.

Review of the two local `video-script` overrides found creator-specific
strategy and time-bound engagement examples that refer to source notes absent
from this repository. Their source copies are now present under
`extensions/easel-workbench/skills/builtin/video-script/` and the overlay
verifier checks each installed file against its repository-owned source digest.
The original benchmark transcripts and review notes remain absent; historical
examples and metrics are explicitly unverified and must not be presented as
current facts. The source copies make the declared overlay reproducible, but do
not establish the truth of the historical claims or settle any separate
redistribution question.

### D3 — Keep upstream routes read-only and isolate one offline task API

The upstream pass-through stays read-only. For scaffold tasks, the workbench
guard accepts `POST /api/contentops/draft-task`,
`GET /api/contentops/draft-task/{task_id}`, and
`GET /api/contentops/draft-task/{task_id}/draft`. The POST schema contains only
`account`, `project`, `brief`, and `idempotency_key`; it calls the deterministic
offline scaffold executor, not Easel chat, a model, gateway, shell or network.
The two GET routes require the matching account and existing project and
verify the receipt and draft bytes before returning them. The API enforces a
32 KiB request cap, idempotency, project-level concurrency and exact paths.
Submission and retrieval also require a matching, unambiguous `account_slug`
in the existing project's `project.yaml`; an unbound project is rejected.
After a task ID is assigned, a failed attempt writes a separate, redacted
project receipt with the failure code and input/DNA digests. It does not replace
the idempotency state or a successful receipt; failures before a safe project
and task binding can only be returned to the caller. This behavior is untested.
The additional evidence-draft mutation is described below; other mutations and
unknown routes remain denied before upstream.

The separate `scripts/easel_host.py serve --offline-tasks-only` mode serves the
ContentOps-owned panel and API on loopback without importing or proxying Easel.
It defaults to port 7862, checks for already-installed `uvicorn` and PyYAML, and
returns 404 for every other route. Its status is independent of the upstream
frontend build receipt. It writes offline scaffold or evidence-based draft
artifacts inside an existing project; production and publication flags remain
false. It does not perform browser acceptance or start a host as part of this
decision. Route-scoped `OPTIONS` responses report the exact method for each
allowed route and emit no CORS allow-origin header; non-loopback Origins remain
denied.

The offline mode's status reports its default panel URL, and the host CLI prints
the selected loopback URL as it starts. A startup message does not establish
that the port was successfully bound. This change has not been run or tested.

Task POSTs require an HTTP Origin whose host and port match the request Host;
missing, duplicate or different-origin headers are rejected. The local CLI is
independent of this HTTP rule. This change has not been run or tested.

Raw `/api/chat`, profile/skill/output readers, account routes, credential
routes, publish routes, settings writes, install routes and deletes remain
denied. Unknown routes, unsafe scopes, path traversal, cross-account reads and
unverified browser assets fail closed.

The source audit found that `/api/personas` enumerates every profile directory
and returns names plus identity descriptions; `/api/persona/{name}` and
`/files` are not restricted to the two ContentOps account IDs. The skill list
and detail handlers call `_read_env()` to derive API configuration status, so
they perform indirect `.env` reads. The raw `/api/chat` route starts or proxies
a gateway turn. These upstream routes stay closed; the ContentOps-owned offline
task routes do not invoke them.

Both upstream `/api/skills` and `/api/status` invoke `get_skills()`, which
reads the runtime `.env`; the guard therefore rejects both routes. The
ContentOps-owned profile, skill and project APIs do not forward to them. This
guard correction has not been run or tested.

`GET /api/contentops/status` reports the offline mode, that gateway state was
not checked, and that real Agent execution is not authorized. It does not
replace the upstream status with a fabricated connected/disconnected result.
This endpoint has not been run or tested.

The offline panel also provides `GET /api/contentops/skills/video-script`.
It reads only the fixed repository-owned `SKILL.md`, checks its declared overlay
source and SHA-256 on each request, and fails closed if the source changes.
It does not expose arbitrary skill paths or call the upstream skill handler.
Historical examples in the content still require independent verification.

The ContentOps-owned `GET /api/contentops/profiles/{account}` projects the
selected DNA into the six profile files in memory and returns their digests and
text. It does not assert that the installed snapshot or an Agent context was
verified. Source inspection of the pinned candidate shows upstream direct mode
appends `load_profile_text` to its system context; gateway mode uses
`chat_turn_message` and `persona_prefix`, which name a profile and tell the
Agent where to read it. That source path alone does not prove that a gateway
Agent actually read the files. This route has not been run or tested.
The same upstream `persona.py` appends `TURN_REMINDER` to gateway chat messages;
that reminder references logged-in accounts and public-platform content. It is
not a permission boundary. The ContentOps guard keeps raw upstream chat closed;
any future Agent requires separately proven tool, credential and network isolation.

The standalone profile verifier also rejects undeclared entries in an account
snapshot, because the upstream loader appends additional Markdown files beyond
the six named files. This verifier change has not been run or tested.

Candidate runtime resolution and host startup require the generated-profile
mode to compare installed snapshots and manifest digests against a fresh
projection of current account DNA. A matching historical manifest alone no
longer marks a changed account as current. This added check is untested.

`GET /api/contentops/project-readiness` reports the selected project's brief
approval, evidence-pack sufficiency and document hashes, and matching video
Bundle handoff. It is a read-only assessment, not a production grant or full
draft validation. Project inputs must remain within permitted non-linked paths.
The offline host requires the existing PyYAML dependency for project binding.
The response also summarizes the existing agent driver's receipt-based plan,
including human-only steps, without returning executable commands or running
them. This does not establish that the pipeline is authorized or ready.

`POST /api/contentops/evidence-draft` accepts an account, an existing project,
and an idempotency key. It requires the matching approved Brief, checked evidence
pack and video Bundle before calling `contentops.script.draft.build` in memory.
It writes a separate project-local Markdown draft and receipt through the same
offline task mechanism; it does not overwrite the production script files. The
receipt binds the Brief digest, evidence-pack digest and Bundle digest. This is
an offline evidence-based draft requiring human copy review, not an Easel Agent
run, production authorization or publication. These newly added routes and
behavior have not yet been executed or tested.

The offline panel can reopen a completed task using its ID and its original
account and project. The existing receipt and draft checks remain authoritative;
the panel does not grant access to a task for a different project or account.
This lookup UI has not been run or tested.

The evidence task also stores a task-bound JSON artifact containing the lines,
claim map, storyboard and report. `GET /api/contentops/draft-task/{task_id}/artifacts`
checks the selected project, account, task ID and recorded digest before
returning it. Neither this JSON nor the Markdown replaces the production script.

### D4 — Do not run a real Agent without system isolation

An offline deterministic executor may be developed and tested without claiming
real Agent execution. A real Agent run requires a separately approved task and
verified low-privilege isolation: dedicated workspace, bounded writable output,
no inherited host credentials or browser state, default-deny network, and an
audited named tool set. Prompts are not a security boundary. If those properties
cannot be demonstrated on Windows, the run remains `BLOCKED`.

The Windows candidate includes a sandbox-launch prototype and Node-level output
capture. The launch entry point unconditionally refuses execution: neither a
local receipt nor an environment variable enables it. The prototype and capture
have not been exercised; capture does not cover native or child-process writes.
Neither component proves OS isolation or grants a real task.

Static inspection of the installed OpenClaw 2026.10.5 tool-policy documentation
shows that even its `minimal` profile includes a Gateway update capability;
`coding` also includes runtime, web and session tool groups. Neither profile is
an acceptable implicit allowlist for this task. A future isolated executor must
explicitly deny unneeded tools and plugins in addition to proving OS isolation;
the installed policy has not been exercised here.

The explicitly selected v0.3 candidate composer uses the existing
`assemble_easel.py` adapter but writes its intermediate and final video into a
unique project-local `work/easel-v030-candidate/<run-id>/` directory, with a
separate `build-easel-v030-<run-id>.json` receipt. The candidate subprocess
receives a reduced environment and private temporary directory. This is not a
proven OS sandbox or a production migration; candidate output remains pending
QC and human review, and the production pin is unchanged. This adapter change
has not been run or tested.

Before candidate composition, the adapter resolves each used visual, BGM and
sound effect against the project's existing asset manifest and rights checks;
narration must match the existing narration receipt. It records input hashes,
rejects missing or changed inputs, and does not silently skip declared tracks.
These checks are implementation only until the candidate path is exercised.
Only assets referenced by the storyboard are required to resolve; missing or
invalid unused manifest entries do not prevent composition. Used assets still
require an unambiguous manifest entry, matching digest and applicable rights.

The candidate article adapter writes previews and receipts to unique project
paths and uses a reduced child-process environment. Candidate card
rendering remains blocked: the upstream renderer launches a browser that can
fetch remote resources, and an isolated browser/network boundary has not been
established. These adapter changes have not been run or tested.

### D5 — Keep ContentOps ownership of evidence and delivery

Any resulting draft must bind to the selected account DNA, task input, runtime
and build identities, and the existing project receipt chain. Generated text is
not evidence. `production_ready` and `publish_authorized` remain false pending
the established QC, human review and delivery gates. No account connection,
provider spend or external publication is granted here.

## Consequences

- The workbench can be prepared in parallel without moving the v0.2.1 pin.
- The host stays blocked until its dependencies, upstream bytes, overlay and
  frontend build have all been verified.
- The isolated offline panel can be served for a future browser review without
  loading the blocked upstream workbench; serving it still requires a separate
  explicit operator action.
- Profile snapshots that no longer match account DNA are rejected; refreshing
  existing local profiles is a distinct file mutation and must be reviewed.
- A real task, browser acceptance and production migration remain separate
  milestones with their own evidence. This ADR does not authorize dependency
  installation, host startup, model/network calls, commits, pushes, PRs or
  cleanup of old runtimes.

## Re-review

Reopen this decision if the workbench requires upstream edits, if an audited
route exposes data outside its selected project/account, if the build cannot be
recreated from the pinned source and lockfile, or before changing the production
runtime from v0.2.1.
