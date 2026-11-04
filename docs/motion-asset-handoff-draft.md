# 外部动效资产交接合同（草案）

> **状态：DRAFT，未实现，未授权。** 本文件是评审材料，不是 schema、不是许可、不是执行授权。
> 它描述“外部动效工具产出的素材如何被 ContentOps 接收”，不复制任何外部工具代码，也不授予第三方衍生素材的公开使用权。
> 归属决定：待 Owner 决定本文档是并入 `docs/` 规范体系，还是作为 Issue 草案归档。

## 1. 目的与边界

MotionClone 等外部工具是独立制作环境。ContentOps 只接收**有权利边界、哈希、版本和真实文件**的回执，再由固定 Easel 合成。

本合同的产出永远是：

```
generated = true
evidence_capable = false
role = VISUAL_SUPPORT
publish_authorized = false
```

也就是说：动效可以“解释”，不能“证明”；记录存在不等于素材获准公开；接收不等于进入 M5 或发布。

## 2. 回执结构（草案字段）

| 字段 | 类型 | 规则 |
|---|---|---|
| `schema` | string | `contentops.motion-handoff/v1`（草案名，未冻结） |
| `handoff_id` | string | 非空、唯一 |
| `asset_id` | string | 与 M5 资产 ID 一致；不得与既有资产重复 |
| `account_role` | enum | `explorer` / `thinktank` |
| `runtime` | object | `{tool, version, commit}`；必须是已记录的工具版本，不得“最新版” |
| `project.original_sha256` | sha256 | 原始可编辑工程哈希 |
| `project.reordered_sha256` | sha256 | 重排后工程哈希 |
| `inputs[]` | array | `{logical_path, sha256, time_range}`；只能是 `project://` 或 `repo://` |
| `outputs[]` | array | `{logical_path, sha256, duration_s, silent}`；真实文件，非占位 |
| `source_window` | object | `{source_id, start_s, end_s}`，必须落在权利台账允许的区间内 |
| `rights` | object | `{scope, reviewed_by, reviewed_at, evidence}`；scope 至少为 `internal_only` |
| `silent` | bool | 样片必须为 `true` |
| `role` | string | 固定 `VISUAL_SUPPORT` |
| `generated` | bool | 固定 `true` |
| `evidence_capable` | bool | 固定 `false` |
| `publish_authorized` | bool | 固定 `false`；任何 `true` 直接拒绝 |
| `created_at` | ISO-8601 | UTC |

## 3. 校验规则（实现时必须逐条拒绝）

1. 所有路径必须是 `project://` 或 `repo://`；绝对路径、盘符路径、`..` 逃逸、跨仓路径一律拒绝。
2. `inputs` / `outputs` 的文件必须存在，`sha256` 必须与文件字节一致；哈希漂移拒绝。
3. 输出必须是真实 MP4，可用 `ffprobe` 读取；时长与 `duration_s` 一致（容差 ≤0.1 s）。
4. 输出必须静音（无音频流）。
5. `runtime.version` / `runtime.commit` 必须与已记录的运行时台账一致；未知版本拒绝。
6. `source_window` 必须落在 `docs/motion-source-rights-ledger-20261102.md` 对应来源的已允许区间内；越界拒绝。
7. `rights.scope` 为 `internal_only` 或更严格；`publish_authorized: true` 拒绝。
8. 回执过期（超过约定有效期）或状态为 `REJECTED` 的 job 不得重新登记。
9. 同一 `asset_id` 只能有一个当前回执；旧回执保留为历史，不覆盖。

## 4. 拒绝代码（草案）

| 代码 | 含义 |
|---|---|
| `MOTION_HANDOFF_MISSING` | 回执不存在 |
| `MOTION_HANDOFF_MALFORMED` | JSON/schema 不合法 |
| `MOTION_PATH_ILLEGAL` | 绝对路径、逃逸或跨仓 |
| `MOTION_FILE_MISSING` | 输入/输出文件不存在 |
| `MOTION_HASH_DRIFT` | 文件字节与记录不符 |
| `MOTION_OUTPUT_NOT_MP4` | 输出不是可读 MP4 |
| `MOTION_OUTPUT_NOT_SILENT` | 输出有音频流 |
| `MOTION_RUNTIME_UNKNOWN` | 工具版本/commit 未记录 |
| `MOTION_SOURCE_WINDOW_DENIED` | 来源时间窗越界或来源未登记 |
| `MOTION_RIGHTS_INSUFFICIENT` | 权利范围不足或要求公开授权 |
| `MOTION_STALE_OR_REJECTED` | 旧回执或已拒绝 job |
| `MOTION_DUPLICATE_ASSET` | 同一 asset_id 已有当前回执 |

## 5. 与 M5 的关系

- 合同通过后，动效仍只是 `generated=true` 的辅助资产，必须由人显式登记进**唯一** `MediaManifest` 活动 timeline。
- 不得因为“有回执”就自动进入 M5、时间线或发布。
- 进入整片后仍受 70% 真实素材可见时长门约束；动效时长计入非真实部分。

## 6. 明确不做

- 不复制 MotionClone / HyperFrames 源码，不升级版本，不与 media-use 0.8.222 混锁。
- 不解析第三方参考片的原帧、原声作为输出。
- 不自动签名、不自动批准、不发布。
- 不把本合同当作任何素材的公开授权。

## 7. 待决事项

- [ ] 本文档归属（规范 vs Issue 草案归档）。
- [ ] MotionClone 运行时版本与 commit 的正式记录位置。
- [ ] 第三方衍生素材的公开传播权利由谁、依据什么文件确认。
- [ ] 回执有效期与重新审核周期。
