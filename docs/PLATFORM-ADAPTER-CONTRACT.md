# Platform Adapter Contract

> Design contract for the L3 delivery layer. It defines how a future platform
> adapter plugs into the existing registry **without** creating a second
> production engine or a second registry.
>
> No adapter except the X manual-only gate exists today. This document is
> proposed, not implemented.

Status: proposed — 2026-11-02
Related: [ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md) (D3–D8),
[ADR-016](adr/ADR-016-easel-host-adoption.md) (D4–D6),
[PLATFORM-INTEGRATION-STATUS.md](PLATFORM-INTEGRATION-STATUS.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [CONTENT-LIFECYCLE-STAGES.md](CONTENT-LIFECYCLE-STAGES.md)

## Position in the system

A production line produces **once per medium**: `VIDEO` or `GRAPHIC_TEXT`. A
platform adapter maps a finished, human-reviewed package to a platform's native
shape. An adapter is **delivery, not production**; a platform never gets its own
production engine (ADR-015 D8).

```text
production line → reviewed package + receipt
    → adapter.pack() → platform draft
    → validate → prepare_handoff → human review
    → publish (only with a separately verified authorization)
    → delivery receipt
    → optional metric snapshot
```

## Authority boundaries

Two kinds of authority must not be conflated:

| Authority | Owner | This contract's role |
|---|---|---|
| **Platform strategy** — which platforms exist, what they are for, portfolio and account positioning | `X-SuperPlay-Strategy` (private repo: Platform Operating Matrix, Content Bundle spec) | consumed as `strategy_platform` mappings; never re-decided here |
| **Local execution truth** — what code exists on this branch, what it can produce, what blocks it | `X-SuperPlay-ContentOps` (`config/registry/platforms.json`) | describes this branch only |

`platforms.json` is therefore the local execution registry, **not** "the
platform truth". It resolves the Strategy `strategy_platform` id into local
facts. It carries no private repository names, no account identities, no
portfolio status and no credentials (ADR-015 D5). GitHub is proof
infrastructure, not a publishing row.

## The registry is the only local truth source

`config/registry/platforms.json` (`contentops.platform-registry/v1`) remains the
single machine-readable **local execution** registry, loaded and validated by
`src/contentops/platforms/registry.py` and operated by `scripts/platforms.py`.
Platform **strategy** (which platforms the portfolio carries and why) is owned
by Strategy and reaches this repo only as the `strategy_platform` field.

This document describes the **behavior** that the owner of a registry row must
implement. It does not add a file, a schema or a second source. A YAML registry
or a second JSON registry is a defect, not an alternative (ADR-015 D3).

A platform adapter is an implementation of a row. It is not a new row, and it
does not upgrade a row's status.

## Interface (design)

A future Python protocol. Nothing below is wired today.

```python
class PlatformAdapter(Protocol):
    platform_id: str          # matches a platforms.json entry
    strategy_platform: str    # maps to exactly one Strategy platform
    content_types: tuple[str, ...]
    pipeline: str             # local registry pipeline label

    def capabilities(self) -> AdapterCapabilities: ...
    def pack(self, package: ReviewedPackage, account: AccountIdentity) -> PlatformDraft: ...
    def validate(self, draft: PlatformDraft) -> ValidationResult: ...
    def prepare_handoff(self, draft: PlatformDraft) -> HandoffReceipt: ...
    def publish(self, draft: PlatformDraft,
                authorization: PublishAuthorization) -> PublishReceipt: ...
    def read_metrics(self, receipt: PublishReceipt) -> MetricSnapshot | None: ...
```

Rules:

- `pack` and `validate` are **offline and deterministic**. They may not touch the
  network or a provider.
- `prepare_handoff` produces a handoff receipt for a **human** to act on. It is
  the terminal state of a manual-only adapter. It never publishes and never
  records a URL.
- `publish` must raise unless a `PublishAuthorization` exists **and passes the
  authorization check** below. The default implementation is manual-only and
  has no branch that returns `PUBLISHED`.
- `read_metrics` is optional. Absent means `NONE`, never a fabricated number.
- No adapter may read credentials, install dependencies or start a host.

### The three delivery actions are separate

| Action | Method | Terminal state | Records a URL? |
|---|---|---|---|
| Prepare a human handoff | `prepare_handoff` | `AWAITING_MANUAL_PUBLISH` | no |
| Authorized publication (future) | `publish` | publication state set by a separately approved adapter | per adapter, only with an approved authorization |
| Record a manual URL a person already obtained | **separate receipt recorder** (not an adapter method) | see `REPORTED_PUBLISHED` / `VERIFIED_PUBLISHED` | yes |

A single `PublishAuthorization` object is **not** sufficient to publish. Before
`publish` acts, the authorization must be verified to name:

- the `platform_id` and the account this draft is for;
- the package identity and the `bundle_sha256` of the source Bundle;
- the human reviewer and a fresh, not-yet-consumed approval;
- an expiry, and the scope (what this authorization permits);
- the publish mode actually implemented by the adapter.

An authorization that fails any check is refused — the adapter raises, it does
not degrade to a handoff.

### Manual URL recording

When a person publishes by hand and supplies the URL, the recorder first writes
`REPORTED_PUBLISHED` — a human-entered fact, not platform evidence. It upgrades
to `VERIFIED_PUBLISHED` only when external verification evidence exists (for
example, an independently fetched platform readback recorded in the receipt).
The state vocabulary:

| State | Meaning |
|---|---|
| `REPORTED_PUBLISHED` | A person entered the URL; no independent verification. |
| `VERIFIED_PUBLISHED` | External verification evidence is recorded alongside. |

The registry status `PRODUCTION_ACCEPTED` additionally requires human review
(ADR-015 D4). A `REPORTED_PUBLISHED` receipt alone never upgrades a row, and
`REPORTED_PUBLISHED` must never be converted automatically:
`PRODUCTION_ACCEPTED` requires **all three** — external verification evidence
(`VERIFIED_PUBLISHED`), a valid written human approval, and a complete delivery
receipt recording both. Any one missing leaves the row at its current status.

## `AdapterCapabilities`

Mirrors the registry's capability fields; do not duplicate their values in a
second place.

| Field | Meaning |
|---|---|
| `draft` | Can produce a platform-native draft locally. |
| `prepare_handoff` | Can emit a human handoff receipt. Default for a manual-only adapter. |
| `publish` | Can publish automatically. Always `false` until separately authorized. |
| `metrics` | Can ingest platform metrics. `NONE` by default. |
| `media_upload` | Can upload assets to the platform. Credential-gated. |
| `draft_support` | The registry's `draft_support` value. |
| `publish_mode` | The registry's `publish_mode` value. |

## Delivery receipt (proposed)

Schema id: `contentops.platform-delivery/v1`.

| Field | Rule |
|---|---|
| `platform_id`, `strategy_platform` | Must match a registry row. |
| `package_id`, `bundle_sha256` | Bind the delivery to the reviewed package and the Bundle. |
| `adapter_version` | Adapter identity. |
| `draft_ref` | Logical path (`project://` / `repo://`), never an absolute host path. |
| `publish_mode` | `MANUAL_ONLY`, `API_DISABLED`, … |
| `publication_state` | `NOT_PUBLISHED`, `AWAITING_MANUAL_PUBLISH`, `REPORTED_PUBLISHED`, `VERIFIED_PUBLISHED`. No receipt state exists above `VERIFIED_PUBLISHED` except the registry's own `PRODUCTION_ACCEPTED`, which additionally requires human review. |
| `published_url` | Present only when a human recorded a real platform URL; see `REPORTED_PUBLISHED` / `VERIFIED_PUBLISHED`. |
| `publish_authorized` | `false` by default. |
| `human_review` | `PENDING` until a person writes the review. |
| `metric_snapshot_ref` | Logical pointer, or `null`. |
| `blockers` | Named reasons when the delivery cannot proceed. |

The existing receipt rules apply unchanged: no secrets, no absolute host paths,
and no receipt without a real run.

## State machine (unchanged)

`PLANNED → INTEGRATED → TESTED → PILOT_READY → PRODUCTION_ACCEPTED`.

| State | Required evidence |
|---|---|
| `PLANNED` | Nothing; the blocker is named. |
| `INTEGRATED` | Adapter code plus offline tests. |
| `TESTED` | A real local run produced a receipt. |
| `PILOT_READY` | A real platform draft was created. |
| `PRODUCTION_ACCEPTED` | A work was published and a receipt recorded the URL. |

A row is **never** upgraded because an account exists, a render passed, or a
configuration was written. Status is a claim about evidence.

## Per-platform mapping (this branch)

The registry stores local pipeline labels that name a platform's native shape
(`XHS_EDITORIAL`, `GZH_EDITORIAL`, `X_EDITORIAL`, `ARTICLE_EDITORIAL`). They are
**storage labels**, not production lines. Production is identified by
normalizing them onto the shared lines:

| Registry pipeline label | Normalizes to production line |
|---|---|
| `VIDEO` | the `VIDEO` line (`contentops.copy-to-video/v1`) |
| `XHS_EDITORIAL` | the `GRAPHIC_TEXT` line (`contentops.copy-to-graphic/v1`) |
| `GZH_EDITORIAL` | the `GRAPHIC_TEXT` line (`contentops.copy-to-graphic/v1`) |
| `ARTICLE_EDITORIAL` | textual editorial (no graphic/video line today; no production engine implies one) |
| `X_EDITORIAL` | textual editorial over the existing publish/ track |

Rules:

- The mapping is declared, not inferred. An adapter states the production line
  it consumes; a registry row states the normalization it uses.
- `XHS_EDITORIAL` and `GZH_EDITORIAL` remain local content-type labels; they map
  to the shared `GRAPHIC_TEXT` line and **do not** justify a separate production
  engine.
- The production-line identifiers (`VIDEO`, `GRAPHIC_TEXT`) stay the names of
  existing code; the editorial labels never shadow them.
- **`X_EDITORIAL` content production is owned by `src/contentops/publish/`.** X
  text authoring facts (`x_text.py`, 280 weighted-char budget), image facts
  (`x_image.py`, real 1600×900) and editorial review dimensions
  (`x_editorial.py`) are the content-production components for the X track; the
  X gate (`publisher.py`, `x_post.py`) is only their packaging and handoff
  stage. They already run inside the one `publish/` package — they are not a
  third production engine, and they do not create a `copy-to-x` contract.

| Strategy platform | Local entry | Pipeline | Local status | Easel capability | Next action |
|---|---|---|---|---|---|
| douyin | `douyin` | `VIDEO` | `PLANNED` | `UPSTREAM_DECLARED` | adapter not started |
| xiaohongshu | `xiaohongshu_video`, `xiaohongshu_image` | `VIDEO`, `XHS_EDITORIAL` | `PLANNED` | `UPSTREAM_DECLARED` | rights unresolved |
| bilibili | `bilibili` | `VIDEO` | `PLANNED` | `UPSTREAM_DECLARED` | adapter not started |
| wechat_channels | `shipinhao` | `VIDEO` | `PLANNED` | `UPSTREAM_DECLARED` | adapter not started |
| wechat_official_account | `wechat_article` | `GZH_EDITORIAL` | `PLANNED` | `UPSTREAM_DECLARED` | rights unresolved |
| zhihu | `zhihu` | `ARTICLE_EDITORIAL` | `PLANNED` | `UPSTREAM_DECLARED` | adapter not started |
| csdn | `csdn` | `ARTICLE_EDITORIAL` | `PLANNED` | `ABSENT` | native adapter required |
| youtube | `youtube` | `VIDEO` | `PLANNED` | `ABSENT` | native adapter required |
| x | `x` | `X_EDITORIAL` | `INTEGRATED` | `ABSENT` | manual-only gate; `prepare_handoff` ends `AWAITING_MANUAL_PUBLISH`; `REPORTED_PUBLISHED` not yet exercised |

`XHS_EDITORIAL` and `GZH_EDITORIAL` are local content-type labels. They map to
the shared `GRAPHIC_TEXT` production line; they do **not** justify a separate
production engine.

## Non-negotiables

1. An adapter is delivery, not production.
2. One Bundle may feed several platforms; it never gets one production engine per
   platform.
3. No automatic publication. `publish` needs explicit human authorization.
4. No credentials, tokens or cookies in this repository.
5. No metric scraping. Missing metrics are `NONE`, not zero.
6. The rights gate and Bundle digest binding still apply to delivered assets.
7. `publish_authorized: false` is the default in every receipt.

## Acceptance tests for a future adapter (offline)

- An unknown `platform_id` is rejected.
- The registry validates and duplicate ids are refused.
- `pack` / `validate` are deterministic and use no network.
- `prepare_handoff` never publishs and never records a URL.
- `publish` without a valid, verified authorization raises; an authorization
  failing any required check (platform, account, package digest, reviewer,
  expiry, scope) is refused.
- No branch returns `PUBLISHED` without external verification evidence
  (`VERIFIED_PUBLISHED`); a manually recorded URL is `REPORTED_PUBLISHED`.
- The receipt contains no secret-shaped value and no absolute host path.
- An unlicensed asset is refused by the rights gate.
- A changed Bundle digest makes the delivery refuse `BUNDLE_CHANGED`.

## What this document is not

- It is not an implementation. No adapter is added by it.
- It does not upgrade any authority: Strategy keeps platform-strategy authority;
  this row set stays the local execution registry.
- It does not grant any X authority to another repository.
- It does not merge PR #101 or treat it as approved.
- It does not upgrade any registry row.
