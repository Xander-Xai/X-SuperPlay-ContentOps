# 接管 Easel 宿主，先接管它的边界

# 接管 Easel 宿主，先接管它的边界

接管宿主不是把上游工作台直接暴露出去。ADR-016 把宿主限定为回环、只读入口：
发布、登录、凭据、设置写入和环境安装在到达上游前就被拒绝。

## 这次只证明边界，不证明发布

- 宿主状态可以是 `HOST_BLOCKED`，这比假装已接通更诚实；
- 视频线和图文线共享同一个 Content Bundle，但不共享审核；
- 人工包停在 `AWAITING_MANUAL_REVIEW`，`publish_authorized` 永远为 false。

配图使用仓库内已跟踪的 Easel 版本证据截图，不生成替代素材。

## Images

- `version_evidence` — 1080x1920 png
  ![Easel v0.2.1 版本证据截图](repo://projects/easel-review/sources/screenshots/12-easel-version-evidence.png)

## Review state

- status: `AWAITING_MANUAL_REVIEW`
- publish authorized: **no**
- blockers: HOST_CAPABILITY_UNVERIFIED, PLATFORM_PLACEHOLDER
