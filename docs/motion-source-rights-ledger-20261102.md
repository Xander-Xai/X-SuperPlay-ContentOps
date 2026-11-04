# 动效素材来源权利台账（2026-11-02）

> **状态：DRAFT / 未清权。** 本台账记录“哪些来源被允许用于哪种用途”，它不是版权证明，不是公开授权，也不替代逐条人工核权。
> 文件名保留 2026-11-02 的原始日期；后续修订追加条目与复核日期，不抹除历史。

## 1. 使用规则

1. **无条目 = 不可用。** 一个来源没有出现在本台账，就不能进入动效交接或 M5。
2. **读台账不等于获得授权。** 台账说明记录在案的范围；实际使用仍受该范围的限制。
3. **新剪辑 / 新处理轮次 = 新审核。** 对同一来源再做一次裁剪、重排或导出，不自动继承上一次的许可。
4. **衍生权利与来源权利分开。** 允许“在本地重建一次”不等于允许“公开传播衍生物”。
5. 任何 `UNRESOLVED` 条目都只能用于内部审片，且不得进入发布包。

## 2. 条目字段

| 字段 | 说明 |
|---|---|
| `source_id` | 来源标识（与优化计划中的 #2 / #9 对应） |
| `origin` | 原始地址或文件位置；不得写私有凭据 |
| `owner` | 权利人 / 作者 |
| `capture_date` | 取得或录制日期 |
| `rights_status` | `UNRESOLVED` / `INTERNAL_ONLY` / `CLEARED_FOR_PUBLIC` |
| `permitted_uses` | 明确允许的用途（本地重建、内部审片、公开传播…） |
| `derivative_rights` | 是否允许再剪辑、重排、导出及公开 |
| `attribution` | 署名要求 |
| `evidence` | 支撑该结论的文件（许可、邮件、合同） |
| `reviewed_by` / `reviewed_at` | 人工核权人及日期 |
| `valid_until` | 过期日；过期后需重新核权 |

## 3. 当前条目（草案）

### S-02 — 参考片 #2（110–140 s 区间）

| 字段 | 值 |
|---|---|
| `origin` | 参考片 #2（本地重建素材） |
| `owner` | **UNRESOLVED** |
| `capture_date` | 2026-11-02 |
| `rights_status` | `UNRESOLVED` |
| `permitted_uses` | 仅限已记载的这一次本地重建与内部审片 |
| `derivative_rights` | **不允许公开传播**；新剪辑/新轮次需重新核权 |
| `attribution` | 待确认 |
| `evidence` | 尚无书面许可 |
| `reviewed_by` | — |
| `reviewed_at` | — |

### S-09 — 参考片 #9（944–1000 s 区间）

| 字段 | 值 |
|---|---|
| `origin` | 参考片 #9（本地重建素材） |
| `owner` | **UNRESOLVED** |
| `capture_date` | 2026-11-02 |
| `rights_status` | `UNRESOLVED` |
| `permitted_uses` | 仅限已记载的这一次本地重建与内部审片 |
| `derivative_rights` | **不允许公开传播**；新剪辑/新轮次需重新核权 |
| `attribution` | 待确认 |
| `evidence` | 尚无书面许可 |
| `reviewed_by` | — |
| `reviewed_at` | — |

### RT-MOTIONCLONE — 外部动效工具

| 字段 | 值 |
|---|---|
| `origin` | MotionClone 2.0.0（其 HyperFrames 0.8.33） |
| `owner` | 外部工具作者 |
| `rights_status` | `INTERNAL_ONLY`（本地离线使用） |
| `permitted_uses` | 本地制作与内部审片；不复制源码进本仓库 |
| `derivative_rights` | 工具产出的画面仍受来源素材权利约束 |
| `attribution` | 按工具要求执行 |
| `evidence` | 工具版本记录（待补 commit） |
| `reviewed_by` | — |
| `reviewed_at` | — |

## 4. 与交接合同的关系

`docs/motion-asset-handoff-draft.md` 的 `source_window` 必须引用本台账的 `source_id` 和允许区间；台账没有条目或条目为 `UNRESOLVED` 时，交接只能是内部审片，且 `publish_authorized` 必须为 `false`。

## 5. 待决事项

- [ ] S-02 / S-09 的原始作者、来源 URL 与书面许可。
- [ ] 衍生素材是否允许公开传播；若允许，条件是什么。
- [ ] 署名格式与位置。
- [ ] 台账归属（`docs/` 规范 vs `research/` 记录）。
