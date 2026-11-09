# Platform Delivery Bypass Audit — 2026-11-09

> Scope: the untracked delivery artifacts sitting in the working tree, and the one
> gate that decides whether a packed draft may leave the repository.
>
> This audit does **not** commit, move or delete any of them. It records what each
> one does, what it would take to make it safe, and where the authoritative check
> now lives.

## What the single registry actually says

`config/registry/platforms.json` is the only platform list. Ten rows, and not one
of them currently authorises external delivery:

| platform_id | pipeline | status | draft_support | publish_mode |
|---|---|---|---|---|
| douyin | VIDEO | PLANNED | NONE | NOT_IMPLEMENTED |
| bilibili | VIDEO | PLANNED | NONE | NOT_IMPLEMENTED |
| xiaohongshu_video | VIDEO | PLANNED | NONE | NOT_IMPLEMENTED |
| xiaohongshu_image | XHS_EDITORIAL | PLANNED | NONE | NOT_IMPLEMENTED |
| shipinhao | VIDEO | PLANNED | NONE | NOT_IMPLEMENTED |
| wechat_article | GZH_EDITORIAL | PLANNED | NONE | NOT_IMPLEMENTED |
| x | X_EDITORIAL | INTEGRATED | NONE | MANUAL_ONLY |
| zhihu | ARTICLE_EDITORIAL | PLANNED | NONE | NOT_IMPLEMENTED |
| csdn | ARTICLE_EDITORIAL | PLANNED | NONE | NOT_IMPLEMENTED |
| youtube | VIDEO | PLANNED | NONE | NOT_IMPLEMENTED |

This matters more than any individual script. A local runner that can technically
push a draft to WeChat is not evidence that WeChat delivery is implemented — the
registry says it is not, and the registry is the record.

## The gate

`src/contentops/platforms/delivery_gate.py` answers one question: may this packed
draft be handed to a delivery tool, and how far?

| Condition | Outcome |
|---|---|
| platform absent from the registry | refused — `PLATFORM_NOT_IN_REGISTRY` |
| Douyin | refused unconditionally — delegated publishing is not integrated |
| draft asserts `publish_authorized: true` | refused — that flag is a founder decision, not a draft field |
| adapter validation missing or failing | refused — delivery consumes validation, never replaces it |
| rights not cleared | refused |
| registry row says delivery is not implemented | refused |
| intended mode is anything but `draft` | refused |
| WeChat, mode other than `draft` | refused — `WECHAT_MASS_SEND_REFUSED` |
| all of the above satisfied, draft mode | `DRAFT_ONLY`, and `may_publish` is always `false` |

Against the registry as it ships, every one of the ten platforms is refused. That
is the correct answer today, not a bug: nothing has verified delivery capability.

## The artifacts, one by one

| Artifact | What it does | Verdict | Evidence |
|---|---|---|---|
| `src/contentops/platforms/multichannel.py` | offline `pack` / `validate`; `prepare_handoff` stops at `AWAITING_MANUAL_PUBLISH`; `publish` raises without a verified authorization; never imports the external CLI | **merge** (into the tracked tree) | module docstring states each boundary; no network or credential path |
| `src/contentops/platforms/graphic_specs.py` | per-platform shaping data and hard limits | **merge** | used by `multichannel`; contains no delivery path |
| `src/contentops/platforms/platform_audit.py` | offline text measurement: topic coverage, tags, digest, code fences. Explicitly rewrites nothing | **merge** | module docstring; pure functions over the draft |
| `scripts/platform_delivery.py` | `list` / `self-test` / `pack` / `dispatch` / `status` around the above | **split** — `pack`/`status` merge; `dispatch` must call `authorize_delivery` before it runs | `cmd_dispatch` (line 387) checks only: draft file exists, `platform_id` in the delivery list, external CLI installed, a channel resolves. It reads no authorization, no rights state and no registry capability |
| `scripts/gzh_workflow_run.py` | read-only gate driver for the GZH workflow: probes runtime, validates the matrix, runs the 10 gate checks, writes a status receipt | **keep** | its docstring and body never advance a gate or publish; it shells out to gate commands and reports their real exit state |
| `scripts/wechatsync_browser.py` | launches a dedicated Chromium profile so the Wechatsync extension can be logged in by a human | **keep as an operator tool** | never types a password, never reads a credential; it only makes a bridge exist. It is a precondition for `dispatch`, so it inherits that gate rather than needing its own |

Nothing is marked for deletion. No artifact was proven useless, and "unused" is
not the same as "unproven".

## Why `dispatch` is the actual bypass

The packer is careful: its self-test asserts `handoff_never_publishes`. The
dispatcher is not: given any well-formed draft file it resolves a browser-bridge
channel and shells out to the external CLI, because the only thing it verifies is
that the pieces exist. A hand-edited draft, or a draft from an older run, is
enough. That is the bypass — not a malicious script, just a checker that stopped
one step early.

The fix is a call, not a redesign:

```python
from contentops.platforms.delivery_gate import authorize_delivery, load_registry_rows

decision = authorize_delivery(
    doc,
    registry_rows=load_registry_rows(ROOT),
    mode="draft",
)
if not decision.allowed:
    _emit({"status": "blocked", "network_called": False,
           "platform_id": decision.platform_id,
           "reason": decision.reasons[0], "conditions": decision.as_dict()})
    return 1
```

The draft also has to carry what the gate checks: the adapter's `validation`
result and a `rights: {cleared: ...}` block. A packer that omits them is refused,
which is the intended direction — the refusal names what is missing.

## Migration order

These files are untracked in the working tree, and this audit deliberately does
not commit them (they are a separate production attempt, not part of this
convergence change). When they are brought in:

1. `delivery_gate.py` and its tests — already tracked, already green.
2. `multichannel.py`, `graphic_specs.py`, `platform_audit.py` — packaged as one
   delivery-adapter change, with a real adapter validation result on every draft.
3. `platform_delivery.py` with `dispatch` wired to the gate **in the same commit**
   that introduces it. Landing `dispatch` first would re-open the bypass.
4. `wechatsync_browser.py` and `gzh_workflow_run.py` as operator tooling, with a
   note that they are not entry points for production delivery.

## What this audit did not establish

- **Whether WeChat drafts actually work end to end.** No credential was used and no
  browser session was opened. The registry says delivery is not implemented; this
  audit does not contradict it.
- **Whether `gzh_workflow_run.py` makes any network call.** It shells out to gate
  commands; whether those reach the network was not traced here.
- **Platform terms beyond Douyin.** The Douyin refusal rests on published subject
  eligibility, per-use authorization and anti-homogenisation limits. Equivalent
  terms for the other platforms were not re-verified in this pass.
