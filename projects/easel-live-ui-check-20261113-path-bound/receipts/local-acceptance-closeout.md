# Easel v0.3.0 local acceptance closeout

- Date: 2026-11-13 (Asia/Shanghai)
- Candidate: `D:\Projects\_worktrees\easel-v030-rebuild-20261113b`
- Upstream: `bb3c8ff0463f36c202454d74171682ba6e470cb1`
- Scope: locally approved rebuild, npm install/build, isolated offline host, profile/draft/receipt HTTP verification. No credentials, Gateway/model, publication, push, or production pin change.

## Verified

- `npm ci --registry=https://registry.npmjs.org/ --strict-ssl=true` and `npm run build` succeeded with Node `v24.16.0` / npm `11.13.0`. The audit reported 1 moderate, 3 high, and 1 critical vulnerability; no automatic fix was applied.
- Frontend manifest destination is bound to this candidate. `verify_easel_runtime.py --frontend-build` reports `VERIFIED` for all 5 files; tree SHA-256 `8ab3d814f2e8c8acf807c61c98a180b4a89fa6af65d8f88a9b4607b55944e5c1`.
- Overlay and generated profiles report `VERIFIED`: 1,071 upstream blobs matched; 14 declared overlay/profile files present; no missing, extra, mismatched, or unsafe files. Overlay source copies also verify.
- Reusing the new manifest with the earlier candidate directory fails closed with `MISMATCH: frontend build destination does not match the verified path`.
- Offline host reported `HOST_READY` / `OFFLINE_TASKS_ONLY`, bound only to `127.0.0.1:7861`, with no upstream Easel loaded, network tools denied, and Gateway/model calls false. The exact launched listener and launcher were stopped after verification; port 7861 is clear.
- Local HTTP served the HTML, JS, and CSS assets and profile API successfully; two valid profiles were selectable, while `x-superplay-english` was excluded as `ACCOUNT_DNA_INVALID`. Cross-origin profile access and `/api/chat` returned 403.
- Task `d592d958-8518-4484-9425-96ec152862e1` produced a deterministic offline scaffold and a project-bound receipt. Receipt and draft hashes were checked. Receipt state is `OFFLINE_DRAFT_ONLY`, `human_review=PENDING`, `production_ready=false`, and `publish_authorized=false`; it is not real Agent execution or production content.
- Checks passed: `test_easel_workbench_overlay.py` 46/46, `test_easel_host_guard.py` 27/27, `test_easel_offline_task.py` 18/18, `test_agent_driver.py` 29/29, `test_account_dna.py`, `test_easel_workbench_rebuild.py` 5/5, and `check_doc_freshness.py`.

## Not completed

- Browser screenshot/UI inspection was not run because the computer-use integration could not initialize its native pipe. HTTP/UI asset and API checks do not substitute for a visual browser acceptance.
- Real Agent/Gateway/model execution remains separately gated and was not attempted. System-level sandbox isolation has not been established.
- Production migration remains unaccepted: three golden renders, QC, human review, and Founder approval are outstanding. The v0.2.1 production pin remains unchanged.
- The earlier offline receipt in `projects/easel-live-ui-check-20261113` predates destination-path binding and must be treated as historical; the new receipt above is the path-bound replay.

## Worktree disposition

The implementation and evidence remain uncommitted on the existing worktree branch for review. No commit, push, PR, or cleanup was authorized or performed. The outstanding gates above are deliberate parking conditions, not claims of completion.

## Subsequent implementation — 2026-11-13

After the checks recorded above, the offline panel and guard were changed to
expose the fixed repository-owned `video-script` skill source with a manifest
digest check. Offline task submission and retrieval were also changed to
require the project's `project.yaml` to declare the selected account. The
earlier fixture projects lack that declaration, so their historical receipts
do not verify this new behavior. These later changes have not been run or
tested, at the user's request. They remain parked in the same worktree under
issue #173; no commit, push, or PR was authorized by the plan. Browser review,
real Agent isolation and execution, and production migration remain open.

Another subsequent change adds a read-only project materials assessment to the
offline panel, using the existing brief approval, evidence sufficiency and
Bundle handoff contracts. It has not been run or tested. It is not proof of a
draft, execution, production readiness, or approval.

The workbench subsequently gained an offline evidence-draft path using the
existing ContentOps script builder and project inputs. It writes a separate
draft and receipt, and has not been run or tested. The older results in this
receipt do not verify this path.

The evidence-draft path was further extended to retain lines, claim map,
storyboard and report in a digest-bound task artifact with a read-only panel.
This later implementation has not been run or tested; earlier receipts do not
verify it.

The v0.3 candidate composition option was subsequently changed to use a unique
project-local work directory and its own candidate receipt, without writing the
production final path. This later adapter change has not been run or tested;
no candidate video or QC result is claimed.

The candidate adapter was later extended with asset-manifest and rights checks,
narration-receipt binding, input path normalization and input hashes. This code
has not been run or tested, and remains an unverified implementation.

The article candidate option was subsequently changed to use distinct preview
and receipt paths. The card candidate option now blocks pending a verified
browser/network isolation boundary. These changes have not been run or tested.

The task POST guard was subsequently changed to require a matching HTTP Origin
and Host, including port, and reject duplicate Host/Origin headers. This change
has not been run or tested; the earlier HTTP observations do not cover it.

The project materials response was subsequently connected to the existing
driver's read-only receipt-based plan, and driver project-ID resolution was
changed to use the selected project rather than the server's current directory.
These changes have not been run or tested; earlier driver results do not cover them.

The panel was subsequently extended with a selected-account, DNA-derived
six-file profile detail. It has not been run or tested and does not prove that
the upstream snapshot or Gateway Agent consumed the projected profile.

The standalone account-profile verifier was subsequently changed to reject
undeclared snapshot entries, including additional Markdown files consumed by
upstream. This change has not been run or tested.

Candidate overlay verification and host startup were later changed to compare
the recorded and installed profile bytes with projections of current DNA. The
earlier VERIFIED result predates this new check; it has not been run or tested.

The offline task path was subsequently changed to create a redacted failure
attempt receipt after task binding and return its project-relative path. It has
not been run or tested; failures before project/task binding have no receipt.

Static inspection of the candidate TTS source shows that its Edge engine calls
an online service. No TTS or network call was made. V1's wrapper was subsequently
changed to keep a failed composition `BLOCKED` instead of labeling it ready for
human review; that change has not been run or tested.

The host CLI subsequently gained an offline panel URL in its status and startup
message. The message is not proof of a successful bind; it has not been run or tested.

The offline panel was subsequently given a task-ID lookup for existing project
drafts and receipts. This UI change has not been run or tested.

The guarded v0.3 host was later changed to serve only verified dist bytes for
its upstream UI and reject legacy static routes. A CSP limits external resource
loads, but is not OS network isolation. This change has not been run or tested.
The candidate static responder was subsequently changed to use explicit MIME
types for its frontend assets; it has not been run or tested.

Later source inspection found that upstream `/api/status` and `/api/skills`
both call `get_skills()`, which reads `.env`. The guard was changed to deny
both. The change has not been run or tested; earlier HTTP checks do not cover it.

The ContentOps panel subsequently gained its own offline status endpoint. It
reports the Gateway as not checked instead of inferring its state. This endpoint
has not been run or tested.

The candidate composition preflight was subsequently changed to resolve only
storyboard-used manifest assets. Used assets still require a unique matching
entry, digest and rights checks. This change has not been run or tested.

The candidate composer subsequently gained explicit rejection of empty subtitle
cues and cues that exceed its two-line display area, rather than reporting a
successful candidate after silently discarding subtitle text. This change has
not been run or tested.

Offline task failures now return their project-bound failure record to the panel
for display. The response and UI change have not been run or tested.
The panel can also reload a failure record by attempt ID with account and
project binding; this later change has not been run or tested.

An Agent workspace preparation module and CLI were subsequently added. They
stage the selected task and DNA-generated profile in a unique project-local
directory with hashes; they do not start an Agent or establish isolation. This
implementation has not been run or tested.
The guarded panel now exposes that preparation through a same-origin POST and
an explicit button. It does not execute the Agent; this change is not tested.
An unexecuted Linux bwrap launch-plan builder now validates exhaustive input and
runtime hashes and specifies separate read-only input/runtime, writable output,
cleared environment and namespaces. It is incomplete and not an isolation proof:
dependencies, fixed Agent invocation, tool/process restrictions, verification
and a task grant are still missing. It has not been run or tested.
The plan later gained an OpenClaw `agent exec` invocation with a staged prompt
containing the selected profile and a proposed deny-all tool policy. The policy
is not installed or verified; this invocation has not been run or tested.
Subsequently, newly prepared inputs gained the deny-all configuration, and the
candidate bwrap plan points OpenClaw's config and state variables to isolated
paths. Whether `agent exec` actually honors this configuration remains unverified.
The candidate plan subsequently gained explicit read-only mounts for packaged
Linux library directories; their provenance and runtime compatibility remain
unverified, and this change has not been run or tested.
An explicit file-list packaging command was added for a separate Linux runtime;
it has not been executed or tested and does not prove provenance or isolation.
Packaging now rejects a non-x86-64 ELF Node binary and records the OpenClaw
package version as unverified metadata. This addition has not been tested.
Static inspection on 2026-11-14 found the Windows installation contains
`@openclaw/fs-safe-win32-x64-msvc` but not its declared
`@openclaw/fs-safe-linux-x64-gnu` optional package. The candidate packager now
requires the matching Linux native package instead of silently accepting a
fallback. This is not a complete Linux dependency audit and was not tested.
An offline import command for a separately supplied, hash-pinned version 0.25.0
native npm archive was added. No archive was acquired or imported, publisher
identity is unverified, and this implementation has not been run or tested.
An opt-in downloader for the single specified npm package was prepared for
review; it has not been run. It is a network action requiring separate user
authorization, and registry integrity alone is not publisher verification.
The offline importer now accepts the adjacent download receipt as its digest
source and records that receipt's hash. No download or import has occurred, and
this code has not been run or tested.
Read-only inspection found no Rust or C/C++ source files in the installed
`@openclaw/fs-safe` package, and no matching package in the checked WSL npm
cache or conventional global locations. This does not exclude other copies.
The candidate launch-plan command now also compares the packaged version with
its manifest and checks the Node ELF header; this addition is untested.
A Linux command was then added to combine the prepared workspace and runtime
manifest into a reviewable sandbox plan. It never runs the resulting command;
this addition has not been run or tested.
The planning CLI now also requires a current, uncancelled project/account
workspace before and after plan construction. This change is untested.
It subsequently gained a call to the existing workbench resolver, binding the
candidate Easel commit and requiring upstream, overlay and profile verification.
This wiring has not been run or tested and does not authorize Agent execution.
Workspace status and candidate planning now also compare the overlay record
and previously verified frontend build against their current bytes. This is
untested and does not establish Agent isolation or execution authority.
An OpenClaw JSON result parser was added for bounded draft extraction. It does
not import output or establish execution provenance; it is not run or tested.
Its parser later gained nested bridge-call rejection and distinguishes a
reported zero tool count from a missing tool summary; it remains untested.
A project-bound result import function now writes candidate drafts and receipts
explicitly marked UNVERIFIED_RESULT_BYTES and NOT_PROVEN. It does not establish
an actual Agent run or authorize publishing, and has not been run or tested.
A CLI now connects this collector to the fixed project-local
`output/agent-result.json` path. It does not run an Agent or validate the
caller-provided exit code, and this addition has not been run or tested.
The fixed-path collector is now exposed through the guarded panel; its exit
code remains manually supplied and the result remains explicitly unverified.
This UI and route have not been run or tested.
An output capture storage primitive was added for a future supervisor. It does
not execute a process or prove origin; matching partial outputs may be resumed.
This addition has not been run or tested.
A POSIX child-supervision primitive was subsequently added with bounded stdout,
timeout and dedicated-process-group termination. It never starts a process or
grants authority and has not been run or tested.
Result collection now checks any existing capture record against the output,
account, project and exit code while holding the project lock. The binding is
unsigned and does not prove execution; this change has not been tested.
The panel can now retrieve such a candidate by attempt ID, verifying account,
project and draft digest; this read path is also untested.
Imported candidate receipts now retain evidence, profile and skill digests and
the frontend and overlay verification states. This addition has not been tested.
Failed candidate result imports also retain their bounded failure reason; this
addition has not been tested and does not establish actual execution.
Workspace status and unverified result import now also check the expected file
set, current DNA profiles, policy and evidence freshness. This is untested.
An x86-64 Linux seccomp preload source was added as a candidate subprocess
restriction. It is not compiled, connected, run or tested and proves no boundary.
An explicit compiler command and candidate LD_PRELOAD wiring were added later.
The dynamic loader may ignore a failed preload, so neither wiring nor a build
receipt proves enforcement. This change has not been built, run or tested.
A later startup tripwire checks for the preload marker and seccomp mode before
loading OpenClaw. It depends on trusted runtime bytes and has not been built,
run or tested; it is not evidence that the intended filter is effective.
On 2026-11-14, WSL Ubuntu-22.04 `/usr/bin/cc` built the current filter source
to `work/no_subprocess-20261114.so`; the adjacent build receipt records source
SHA-256 `81f9e601b9042c94780f71ee931d6e6af0b072ec181b8a47807ea66644715a6b`
and binary SHA-256 `efcd011f425c58dba3598523985d0e7ba0e677e828c9358a6f8febe0b69a1f72`.
The binary was not loaded or tested and isolation remains unverified.
Candidate launch planning subsequently gained an unsigned consistency binding
between current filter source, its build receipt and packaged binary digest.
The binding is not a signature or an isolation proof and has not been tested.
An explicit local runtime inventory command was subsequently added; it has not
been run or tested. WSL inspection identified Node v24.16.0 and its Linux shared
libraries; this is not a packaged or verified runtime.
The first actual inventory stopped on OpenClaw's `.bundle.hash` file. The
inventory and package allowlist now permit that exact filename; other hidden
entries remain restricted. No package or runtime verification resulted.
The second inventory stopped at `dist/extensions/a2a/.setup`; static source
inspection found setup-entry imports from it. The exact `.setup` directory name
is now allowed in candidate packaging; no runtime verification is implied.
The third inventory stopped on a protected path class; inspection found
OpenClaw's packaged `dist/extensions/browser` source as a possible match. The inventory and package
rules now allow only that exact source-to-target mapping while still denying
browser profile paths. No package or isolation validation resulted.
The fourth inventory ended with protected path class `secrets`; it produced no
package. Path-only inspection found both documentation and runtime source under
that name; no credential content was read. Whether either is needed remains
unresolved, and the protection has not been relaxed.
After path-only inspection, top-level OpenClaw documentation is explicitly
excluded and exactly one packaged `dist/secrets/egress-proxy/proxy.worker.js`
source path is permitted; other credential and secret paths remain denied.
This does not imply that provider credentials were read or execution approved.
The inventory command now requires an explicit existing Linux fs-safe package
directory before scanning and maps it into the candidate package; no dependency
was installed or fetched. This code change has not been run or tested.
Inventory now also requires the native package's offline-import receipt and
checks all imported file digests. This is an unsigned consistency binding, not
publisher verification; this change has not been run or tested.
The native import receipt digest and archive digest now propagate from inventory
through runtime package to candidate plan. The receipts remain unsigned and
publisher identity remains unverified. This change has not been run or tested.
The candidate `agent exec` argv subsequently gained explicit `--config` and a
120-second timeout. Runtime behavior and policy enforcement remain unverified.
Agent workspace preparation subsequently gained project locking and idempotent
keys; interrupted preparation fails closed for inspection. This is untested.
Prepared Agent workspaces can now be marked cancelled through the same-origin
panel route; launch planning rejects a cancellation marker. This does not stop
a running process and has not been run or tested.
Cancellation now also writes a project receipts entry, with repeat requests
checking the existing record. This addition has not been tested.
Unverified-result import now also refuses a cancelled workspace; it does not
assert or authorize any Agent execution. This change has not been tested.
Result import subsequently gained a deterministic attempt ID and recovery of
matching draft/receipt files, without replacing mismatched partial outputs. This
change has not been run or tested.
Malformed or tool-calling candidate results now produce a bounded failure code
without retaining raw provider output; this addition has not been tested.
Result parsing now rejects duplicate fields, non-finite values and ambiguous
tool-call counts. This addition has not been run or tested.
If interruption occurs after the workspace manifest is fully written, the next
matching request now checks the binding and input digests and completes its
index; incomplete workspaces remain blocked. This recovery is untested.
If interruption occurs before the workspace directory exists, a matching retry
now reuses its reserved run ID to prepare it. This change has not been tested.
Agent input preparation now includes bounded project evidence excerpts when a
valid pack exists, checks source hashes and literal excerpt presence, and marks
missing evidence explicitly. This addition has not been run or tested.
The panel subsequently gained project-bound Agent workspace status lookup and
input freshness reporting; this addition has not been run or tested.
Agent inputs now include the declared, digest-checked video-script overlay and reference;
historical examples are not treated as evidence. This change is untested.
Agent workspace and imported-result records now also carry candidate Easel,
overlay and frontend identity fields, without claiming Agent execution or
unverified overlay integrity. This addition has not been run or tested.

The offline panel subsequently gained tab-session retry keys for scaffold and
evidence-draft requests. It stores a request digest and opaque key, not the
brief text, so a matching request can reuse its key after a page reload. This
browser change has not been run or tested.

The candidate article adapter subsequently gained a project-local failure
receipt for planning or rendering errors after run allocation. This change has
not been run or tested.

The offline panel's pinned JavaScript digest was subsequently updated for the
retry change. Candidate compose and article entry points now check the lexical
project parent before resolving links. These changes have not been run or tested.
