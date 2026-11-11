# Platform Integration Status

[English](PLATFORM-INTEGRATION-STATUS.md) | [简体中文](PLATFORM-INTEGRATION-STATUS.zh-CN.md)

> What this repository can actually do per platform. Data lives in
> [`config/registry/platforms.json`](../config/registry/platforms.json); the
> decision behind it is [ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md).
> A row is a statement about **this branch**, never about the portfolio.
>
> Last regenerated from the registry: 2026-11-12, `main` at `c1da6dd`.

## How to read a status

| Status | Means | Requires |
|---|---|---|
| `PLANNED` | No bound public account and no publication authority, even when a transport exists | nothing (a placeholder) |
| `INTEGRATED` | Platform-specific code exists here and its offline tests pass | code + tests |
| `TESTED` | A real local run produced a receipt | code + tests + a run |
| `PILOT_READY` | A real platform draft was created | previous + a draft |
| `PRODUCTION_ACCEPTED` | A work was published and a receipt recorded it | previous + URL + human review |

A placeholder is not progress. `PLANNED` never means "configured", `INTEGRATED`
never means "published", and no row implies account access, metric ingestion or
publication authority. Delivery runners exist for both content lines; they raise
a row only when a real account is bound and a real receipt exists.

## Nine registry rows

| Platform | Local entry | Pipeline | Local status | Publish mode | Easel capability | Blocker |
|---|---|---|---|---|---|---|
| 抖音 douyin | `douyin` | `VIDEO` | `PLANNED` | `NOT_IMPLEMENTED` | `UPSTREAM_DECLARED` | `ACCOUNT_NOT_PUBLIC`; the uploader needs an operator grant and Douyin's policy acknowledgement |
| 小红书 xiaohongshu (video) | `xiaohongshu_video` | `VIDEO` | `PLANNED` | `NOT_IMPLEMENTED` | `UPSTREAM_DECLARED` | `ACCOUNT_NOT_PUBLIC`, `RIGHTS_UNRESOLVED` |
| B站 bilibili | `bilibili` | `VIDEO` | `PLANNED` | `NOT_IMPLEMENTED` | `UPSTREAM_DECLARED` | `ACCOUNT_NOT_PUBLIC`, `PUBLISH_NOT_IMPLEMENTED` (public counters can be read into a receipt) |
| 视频号 wechat_channels | `shipinhao` | `VIDEO` | `PLANNED` | `NOT_IMPLEMENTED` | `UPSTREAM_DECLARED` | `ACCOUNT_NOT_PUBLIC` |
| 公众号 wechat_official_account | `wechat_article` | `GZH_EDITORIAL` | `PLANNED` | `DRAFT_ONLY` | `UPSTREAM_DECLARED` | `ACCOUNT_NOT_PUBLIC`, `RIGHTS_UNRESOLVED`; `wechat_draft.py` can stop at a draft, the adapter is `VERIFY_ONLY` |
| X | `x` | `X_EDITORIAL` | `INTEGRATED` | `MANUAL_ONLY` | `ABSENT` | — |
| 知乎 zhihu | `zhihu` | `ARTICLE_EDITORIAL` | `PLANNED` | `NOT_IMPLEMENTED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`, `ACCOUNT_NOT_PUBLIC` |
| CSDN | `csdn` | `ARTICLE_EDITORIAL` | `PLANNED` | `NOT_IMPLEMENTED` | `ABSENT` | `PLATFORM_CODE_ABSENT`, `ACCOUNT_NOT_PUBLIC`, `EASEL_CAPABILITY_ABSENT` |
| YouTube | `youtube` | `VIDEO` | `PLANNED` | `NOT_IMPLEMENTED` | `ABSENT` | `ACCOUNT_NOT_PUBLIC`, `EASEL_CAPABILITY_ABSENT` |

`x` is the only non-`PLANNED` row, and it is deliberately narrow: the X post
gate packages a post and stops at `AWAITING_MANUAL_PUBLISH`. There is no branch
that returns `PUBLISHED`, `PublishMode.API` raises, and no metric is ingested.
That gate is this repository's own; it is not a claim of execution authority
for any other X repository.

`PLATFORM_CODE_ABSENT` is now the exception rather than the rule: a delivery
runner (`video_deliver.py`, `platform_delivery.py`) exists for every content
line, and `PLANNED` is held by the missing account and unresolved rights, not by
missing code. The two rows that still have no platform-specific code are 知乎
and CSDN; CSDN and YouTube additionally have no upstream Easel capability.

## Graphic delivery channels (not registry rows)

`config/platforms/graphic-platforms.yaml` shapes and hands off the graphic line
to seven platforms. Three of them have no registry row, by design — a delivery
channel is not a platform status:

| Platform | Registry row | Channels |
|---|---|---|
| `wechat_article` | yes | api, browser_bridge |
| `zhihu` | yes | browser_bridge (no official write API; only the logged-in bridge) |
| `csdn` | yes | browser_bridge |
| `x` | yes | api, browser_bridge |
| `juejin` | **no** | browser_bridge |
| `toutiao` | **no** | browser_bridge |
| `weibo` | **no** | browser_bridge |
| `xiaohongshu_image` | **no** — listed under `excluded` | — |

`xiaohongshu_image` was removed from the registry and excluded from the graphic
line on 2026-11-09 by operator instruction: the whole Xiaohongshu platform
belongs to the VIDEO line. The exclusion is recorded in the spec file, not left
implicit.

## GitHub — proof infrastructure, not a platform

GitHub is **not** a row in `platforms.json`. It has no pipeline, no account and
no publish target; the loader requires all three to carry a value, so a row
would force a false one. GitHub's role is recorded here instead.

| Field | Value |
|---|---|
| Row kind | `INFRASTRUCTURE` |
| Integration state | `NOT_APPLICABLE` — there is nothing to integrate |
| Publish target | `NOT_A_PUBLISH_TARGET` |
| Metrics | `NONE` |
| Local code | none; the only relation is this repository's own history and CI |

## Easel upstream coverage

Easel v0.2.1 (pinned, `3fe2d99`) names login, adaptation and publishing support
for several platforms. That is an upstream statement, not a verified capability
here. Each registry row records the binding as `easel_capability`:
`UPSTREAM_DECLARED` with the upstream skill path, or `ABSENT`. No row is
`verified_here: true`; the host itself is guarded and currently `HOST_BLOCKED`.

| Coverage | Platforms |
|---|---|
| Named upstream | douyin, xiaohongshu, bilibili, wechat_channels, wechat_official_account, zhihu |
| Not covered upstream | csdn, youtube, x |
| Upstream only, outside the portfolio | kuaishou — no local row, by design |

Six of nine platforms are named upstream. That is a fact about Easel, never a
limit on the nine-platform scope: CSDN, YouTube and X are native ContentOps
work, not gaps to be explained away. ADR-016 makes Easel the production base,
but an upstream declaration still does not raise a local platform above
`PLANNED`.

## Regenerate and check

```bash
python scripts/platforms.py check
python scripts/platforms.py list --json
python tests/test_platform_registry.py
```

Adding a platform means adding one row plus its evidence. It never means adding
a second production system.
