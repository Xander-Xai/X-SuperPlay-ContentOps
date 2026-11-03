# ADR-017: A coding agent is a supported driver, not a new authority

Status: **Accepted — Owner direction, 2026-11-02**
Date: 2026-11-02
Issue: [#106](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/106)
Related: [ADR-016](ADR-016-easel-host-adoption.md), [ADR-015](ADR-015-platform-placeholders-and-content-bundle.md), [ADR-014](ADR-014-delivery-validation-hold.md)

## Context

ADR-016 adopted the pinned Easel host, but the host is `HOST_BLOCKED` on this
machine because FastAPI and uvicorn are absent, and enabling them is a separate
authorization (D6). That left an odd gap: the repository is developed and
operated inside a coding agent, yet the documented way to run production assumed
a browser workbench.

The Owner asked for the coding agent to be a first-class driver. Claude Code,
Codex CLI and OpenCode are all present on this machine. They already have the
repository, the tests and the shell; what they lack is a contract that says
which steps they may run, in what order, and what they must leave to a person.

## Decision

### D1 — The driver is a runtime, not an authority

A coding agent may read state and run production steps. It does not gain
publication, credential, installation, approval or spend authority by being the
driver. Everything ADR-016 D3 and D6 says about approval still holds.

### D2 — The contract is a plan plus one allowlisted step

`src/contentops/easel/driver.py` exposes:

- `build_plan(project, root)` — an ordered list of steps, each with a fixed
  `argv`, the receipts it produces, its authority and its dependencies;
- `run_step(project, step, execute=...)` — resolves one step; without
  `execute` it only prints the argv; with it, runs the argv through
  `scripts/process_utils.py` and writes `receipts/agent-driver-<step>.json`;
- `detect_hosts()` — which of `claude`, `codex`, `opencode` exist on PATH.

The agent never supplies a command string. It selects a step id from a fixed
table, so a prompt injection cannot turn the driver into a shell.

### D3 — Four authorities, one of them closed to the driver

| Authority | Meaning | Driver may run |
|---|---|---|
| `READ` | report state, run QC | yes |
| `PRODUCE` | render or build an artifact | yes |
| `HUMAN_ONLY` | sign the review, approve a workflow stage | **no** |

`publish` is not a step at all. A plan that could name one is rejected at
construction by the forbidden-token check.

### D4 — A receipt per executed step

Every execution writes `receipts/agent-driver-<step>.json` with the argv, a
logical `cwd` (`.`), return code, status, timestamps and bounded stdout/stderr
tails. The receipt carries `production_ready: false` and
`publish_authorized: false`; a successful command is not an approval.

### D5 — No new dependencies and no host requirement

The driver runs the existing `scripts/` entry points. It does not need FastAPI,
uvicorn, a browser or a running host. `host-status` is offered as a read step so
the agent can report the host state, not because it is required.

## Consequences

- `scripts/agent_drive.py status|plan|run` becomes the agent-facing entry point.
  The runbook documents the loop: `plan` → `run --step ... --execute` → read the
  receipt → repeat.
- The web host stays optional. Its absence no longer blocks production, and the
  host is not described as the only way to drive the system.
- A coding agent that misbehaves can still run arbitrary shell commands outside
  the driver. The driver is a contract for the supported path, not a sandbox;
  the guard and the human gates remain the load-bearing controls.
- `HUMAN_ONLY` is enforced by refusal, not by policy text. A driver cannot
  approve a stage even if asked.

## Acceptance

- `python tests/test_agent_driver.py` passes: plan order, human-step refusal,
  outside-repo refusal, dry-run not executing, receipt written on execution, and
  no forbidden capability in any argv.
- `python scripts/agent_drive.py plan --project projects/bundle-dual-line-video`
  lists four steps and names `produce-video` as next.
- The plan and every receipt contain logical paths only.
- `python scripts/dev_check.py` and CI pass, with the suite wired into
  `.github/workflows/ci.yml`.
