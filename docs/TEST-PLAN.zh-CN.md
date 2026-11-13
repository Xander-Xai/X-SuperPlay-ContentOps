---
translation_of: docs/TEST-PLAN.md
language: zh-CN
translation_status: synced
---

# 测试计划

[English](TEST-PLAN.md) | [简体中文](TEST-PLAN.zh-CN.md)

> 本地验证策略权威文档、套件清单与 CI 接线。
>
> 最后验证：2026-11-13，PR #174 候选分支；主线原有测试契约保持不变。
> 本分支增加 X 本地数据分析测试及 CI 步骤，测试使用合成 CSV，不上传真实后台数据。

>
> 最后核验：2026-11-06，`fix/6-brief-copy-review`。

## 按风险等级进行本地验证

根据受影响的行为与风险选择检查，而不是根据改动文件数量。优先静态分析，再运行最小且直接相关的现有套件。未运行的测试**不等于**通过。没有直接适用的自动化测试时，不要仅为“有测试”而新增测试；只有明确证明覆盖不足且行为值得回归保护时，才补最小测试。

| 等级 | 范围 | 本地验证 |
|---|---|---|
| **L0 — 文档/非行为变更** | 文案、Markdown、注释、非行为性说明 | 不运行业务单元、集成或 E2E 测试。仅运行直接相关的文档/链接/一致性检查；修改双语镜像时运行 `check_i18n.py`。不运行 `doctor.py`、`qc_video.py` 或完整 `dev_check.py`。 |
| **L1 — 局部低风险代码** | 不改变公共契约的局部 Bug 修复/配置逻辑 | 优先静态分析；适用时通常最多运行一个直接相关的现有套件。若无适用套件，明确报告静态验证及尚未覆盖的运行时行为。不自动跑全量测试。 |
| **L2 — 常规功能** | 普通接口/组件、新业务逻辑、非关键媒体逻辑、Bundle/Router/工作流局部变更 | 运行相关现有测试，通常为 1–3 条针对性测试命令。跨模块契约受影响时只增加必要的契约检查，不扩展到无关模块。 |
| **L3 — 高风险** | 人工审批/执行授权；Provider 计费、额度或真实调用；媒体权利/证据；凭证/访问；CI/安全门禁/公共契约；固定 Easel 运行时/升级；数据损坏、重复扣费或错误发布 | 执行覆盖相应风险所需的单元、契约、集成及回归检查。保留 Fail-Closed 与人工审批。真实付费调用、外部写入、真实渲染或人工审核仍需单独授权。普通测试预算不能豁免必要安全检查。 |

### 本地命令按需触发

- `python scripts/doctor.py`：仅用于环境依赖、运行时、安装或部署状态变更。
- `python scripts/qc_video.py <project>`：仅用于实际视频产物或视频 QC 行为；不作为通用代码检查。
- `python scripts/test_basic.py`：仅用于相关脚本入口或基础行为。
- `python scripts/dev_check.py`：准备 PR 时运行一次完整本地门禁；不要求每次小改动后重复运行。
- `python scripts/dev_check.py --quick` **只跳过**仓库策略检查；仍运行子进程策略、skill 引用、文档、i18n、`test_basic.py` 和 `git diff --check`。它不是针对性或轻量相关测试模式。
- 仅当仓库文件放置/安全策略或 CI 套件接线受影响时运行 `python scripts/check_repo_policy.py`。

## 预算、重试与停止条件

普通开发任务的验证开销目标约占总投入 20%–30%，这是规划参考，不是安全上限。L0 不跑业务测试；L1 通常最多一条针对性测试命令；L2 通常最多三条相关测试命令；L3 根据实际风险确定。

后续改动不可能影响已通过命令时，不要重跑。失败后先诊断，只重跑受修复影响的检查，不盲目重试。没有证据表明存在覆盖缺口时，不扩展测试矩阵。若验证超出普通预算，说明其针对的具体风险。

当需求已实现、必要的直接相关验证通过、没有已知阻断缺陷且没有遗留关键风险时立即停止。测试通过后，不自主扩展测试、不做无关重构或新一轮全面审查。未运行的测试必须如实标记为未运行，不能写成通过。

## 本地开发与 PR/CI 的区别

日常本地开发采用上述 L0–L3 策略。准备 PR 时保留完整现有本地门禁（`python scripts/dev_check.py`）及相关业务回归测试。GitHub Actions 仍是完整套件权威执行环境：Ubuntu 与 Windows 测试任务，加上仓库策略检查（含 receipt-secret 检查）。不得关闭、删除、弱化或绕过 CI、必需检查、分支保护或安全门禁。局部本地测试通过不代表完整 CI 矩阵通过。

## 套件运行方式与接线

本仓库**不使用 pytest**。每个套件是独立脚本，例如：

```bash
python tests/test_m5_evidence.py
python tests/test_media_convergence.py
```

当前套件权威清单为 `git ls-files 'tests/test_*.py'`；只有 `.github/workflows/ci.yml` 明确点名的套件才算接入 CI。CI 为每个套件显式配置步骤。`check_repo_policy.check_test_suites_registered_in_ci` 会发现未接线套件。

## 当前清单

套件内函数数目只是下限，因为列表驱动和 unittest 风格套件定义检查的方式不同。

| 套件 | 文件 | 数量 | CI |
|---|---|---:|---|
| 脚本冒烟 | `scripts/test_basic.py` | 10 | 是 |
| X 增长与文案 Skill 样本/草稿/指标契约 | `tests/test_x_organic_growth.py` | unittest（新增 11 项文案回归） | 是 |
| Windows 子进程 | `tests/test_windows_subprocess.py` | 47 | 是 |
| Windows 路径 | `tests/test_windows_paths.py` | 6 | 是 |
| M2 语音 | `tests/test_minimax_speech.py` | 86 | 是 |
| M2.1 声音克隆 | `tests/test_minimax_voice_clone.py` | 41 | 是 |
| M2.2 克隆路由 | `tests/test_minimax_clone_route.py` | 23 | 是 |
| M2.2 体验金激活 | `tests/test_voucher_activation.py` | 9 | 是 |
| 现金激活恢复 | `tests/test_cash_activation_recovery.py` | 20 | 是 |
| 原生 T2A 适配器 | `tests/test_minimax_native_tts.py` | 13 | 是 |
| 主机绑定审计 | `tests/test_host_binding_audit.py` | 9 | 是 |
| M3 图片 | `tests/test_minimax_image.py` | 85 | 是 |
| M4 H3 视频 | `tests/test_minimax_h3.py` | 108 | 是 |
| M4.5 媒体收敛 | `tests/test_media_convergence.py` | 97 | 是 |
| media-use 适配器 | `tests/test_media_use_adapter.py` | 56 | 是 |
| M4.6 enhanced golden | `tests/test_enhanced_golden.py` | 18 | 是 |
| Golden A/B 变体 | `tests/test_golden_variant_ab.py` | 13 | 是 |
| Golden 语音资产 | `tests/test_golden_voice_assets.py` | 10 | 是 |
| Golden 干净检出重建 | `tests/test_golden_voice_rebuildability.py` | 6 | 是 |
| 锁定输入可复现性 | `tests/test_locked_input_reproducibility.py` | 10 | 是 |
| 源证据 gitignore | `tests/test_gitignore_evidence_policy.py` | 14 | 是 |
| 本地审批 gitignore | `tests/test_local_approval_gitignore.py` | 5 | 是 |
| M5 证据 | `tests/test_m5_evidence.py` | 19 | 是 |
| GitHub 仓库来源适配器 | `tests/test_repo_source_adapter.py` | 3 | 是 |
| M5 media-use 工作流 | `tests/test_m5_media_use_workflow.py` | 列表驱动 | 是 |
| M5 媒体可追溯性 | `tests/test_m5_media_traceability.py` | 列表驱动 | 是 |
| 平台注册表 | `tests/test_platform_registry.py` | 22 | 是 |
| 稳定生产门禁 | `tests/test_production_gates.py` | 30 | 是 |
| 内容路由 | `tests/test_content_router.py` | 63 | 是 |
| 热点源 | `tests/test_hotspot_sources.py` | 51 | 是 |
| 账号 DNA | `tests/test_account_dna.py` | 37 | 是 |
| 账号发现 | `tests/test_account_discovery.py` | 23 | 是 |
| 脚本草稿 | `tests/test_script_draft.py` | 20 | 是 |
| 来源质量 | `tests/test_source_quality.py` | 21 | 是 |
| 账号路线 | `tests/test_account_route.py` | 12 | 是 |
| Brief → M5 桥 | `tests/test_brief_to_m5.py` | 13 | 是 |
| 真实素材时长门 | `tests/test_real_source_duration.py` | 17 | 是 |
| 卡片渲染器 | `tests/test_render_cards.py` | 18 | 是 |
| 公众号文章渲染器 | `tests/test_render_articles.py` | 35 | 是 |
| 公众号运行时适配器 | `tests/test_gzh_runtime.py` | 13 | 是 |
| ASR 传输（SiliconFlow） | `tests/test_asr_siliconflow.py` | 14 | 是 |
| M5 ASR 门禁 | `tests/test_m5_asr_gate.py` | 6 | 是 |
| 公众号草稿 | `tests/test_wechat_draft.py` | 15 | 是 |
| 公众号指标 | `tests/test_wechat_metrics.py` | 11 | 是 |
| SAU 登录 | `tests/test_sau_login.py` | 9 | 是 |
| 交付门禁 | `tests/test_delivery_gate.py` | 7 | 是 |
| 视频平台 | `tests/test_video_platforms.py` | 30 | 是 |
| 平台状态同步 | `tests/test_platform_status_sync.py` | 9 | 是 |
| 工作流契约 | `tests/test_workflow_contract.py` | 8 | 是 |
| 工作流门禁 | `tests/test_workflow_gate.py` | 11 | 是 |
| 发布回填 | `tests/test_publish_backfill.py` | 13 | 是 |
| 治理检查 | `tests/test_governance_checks.py` | 16 | 是 |
| 治理账本 | `tests/test_governance_ledger.py` | 列表驱动 | 是 |
| M5 动效集成 | `tests/test_m5_motion_integration.py` | 65 | 是 |
| Content Bundle 契约 | `tests/test_content_bundle_contract.py` | 13 | 是 |
| Easel 宿主门禁 | `tests/test_easel_host_guard.py` | 13 | 是 |
| Bundle 双格式 handoff | `tests/test_bundle_two_formats.py` | 14 | 是 |
| 图文工作流 | `tests/test_graphic_workflow.py` | 14 | 是 |
| M5 Bundle handoff | `tests/test_m5_bundle_handoff.py` | 5 | 是 |
| coding-agent 驱动 | `tests/test_agent_driver.py` | 29 | 是 |
| Skill doctor | `tests/test_skill_doctor.py` | 列表驱动 | 是 |
| Skill 引用完整性 | `tests/test_skill_references.py` | 6 | 是 |
| Skill 路由能力 | `tests/test_skill_router_capabilities.py` | 列表驱动 | 是 |
| Skill 执行授权 | `tests/test_skill_execution_authorization.py` | 列表驱动 | 是 |
| 受管 media-use 状态 | `tests/test_skill_execute_status.py` | 列表驱动 | 是 |
| 可信授权来源 | `tests/test_trusted_grant_source.py` | 列表驱动 | 是 |
| 执行门禁 | `tests/test_execution_gate.py` | 列表驱动 | 是 |

CI 还运行策略、文档、i18n、空白、子进程与 receipt-secret 检查。媒体 Provider 套件使用假传输，不会调用真实 Provider。依赖 `ffmpeg`、`Pillow`、media-use 运行时或被忽略产物的套件可能在本地跳过；需检查可用性/skip 输出。CI 会安装 `Pillow` 和 ffmpeg 并报告可用性。

## 新增测试套件

1. 只有在明确证明存在覆盖缺口时才新增 `tests/test_<area>.py`，并沿用独立脚本模式。
2. 在 `.github/workflows/ci.yml` 增加具名步骤。
3. 当已核实事实变化时，更新本清单和 `docs/CURRENT-STATE.md`。
4. 准备 PR 时运行新增套件和完整 PR 门禁，而不是每次中间修改都重复执行。

## 计划中

- 面向更多跨仓库 `SourceArtifact` 适配器的契约测试；路由层与一个 GitHub 适配器已在 `main`。
- 发布路径的回归套件 —— 在出现真实平台 URL 之前没有可断言的证据。

上表是下限而非完整枚举：2026-11-12 共 98 个套件，权威来源是
`git ls-files 'tests/test_*.py'`。
