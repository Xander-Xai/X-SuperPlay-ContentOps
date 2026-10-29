---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# video-script 冒烟双稿｜独立复核与下一步提示词（2026-10-28）

## 0. 复核对象

- `outputs/scripts/x-superplay-1024-smoke-video-skill-route.md`（A 组，55s）
- `outputs/scripts/x-superplay-future-intelligence-smoke-video-skill-route.md`（B 组，105s）
- 对应 `.narration.txt` 两份

这两支是 **skill 接入冒烟测试**，目的是验证 video-script 能按双账号 DNA 出稿；**不是待发布成片**。

## 1. 我独立复跑的事实核对（不沿用冒烟报告结论）

| 稿内断言 | 复核命令 / 来源 | 结果 |
|---|---|---|
| catalog 共 114 个 skill | `python scripts/skill_route.py --list --json` 计数 | ✅ 114 |
| `.runtime/` 在 `.gitignore` 第 31 行 | `Select-String .gitignore runtime` | ✅ 第 31 行 `.runtime/` |
| wordcount.py 两份仅换行符差异、归一化一致 | 字节 + 正则统计换行 + 去 CRLF 比对 | ✅ 各 197 个换行；Easel 全 CRLF、.runtime 全 LF；`normalized equal: True` |
| `check_account_dna.py` 只校验四字段非空、不校验 skill 是否在 catalog | 读 `scripts/check_account_dna.py` 325–331 | ✅ 属实，真实缺口 |
| 同一条 `skill_route[]` 路径基准混用（Easel 相对 vs 仓库相对） | UTF-8 读两份 DNA 逐行列出 script | ✅ 属实：5 条是 `skills/openclaw|shared/...`，仅 `qc` 是 `scripts/qc_video.py` |
| B 组零录屏零鼠标 | 逐段读画面备注 | ✅ 全为矢量图 / 局部代码截图，无桌面、无光标 |
| 无 URL 未宣称上线；数字均来自本次实跑 | 全文扫描 | ✅ 无"已上线/已开源可用"；114/produce/md5/197 均可回溯 |

> 计数假象记录：`Get-Content` 在该环境对 LF 文件曾报 179 行，属计数口径问题；换行符以正则统计的 197 为准，勿被 179 误导。

## 2. 两支稿子的结构判定

### A 组（1024 / RESULT_FIRST）— 结构通过
- Hook「我改了 skill，路由没变。因为它读的不是我改的那份。」= Hook 库「翻车现场 + 反常识」，3 秒内成立。
- 七拍覆盖 6/7，`COST_AND_LIMITS` 按 DNA 显式 deferred，未编造成本数字。
- 有翻车拍（.runtime 不同步 + 哈希漂移），CTA 为 DNA 锁定原句。

### B 组（future / ENGINEERING_WALKTHROUGH）— 结构通过
- Hook 工程痛点开场；七拍全 covered，无 deferred。
- 锚点「目录即注册表」在 38s 与 48s 各回扣一次，符合手册第 3 节。
- 根因双坑（catalog 优先级 + 路径基准混用）、验收指标、复现三步齐全；无公开 URL 处未念链接。

## 3. 复核中发现、冒烟报告未说透的问题

1. **A 组真实素材比 42% < 70%（`real_source_ratio_min_70`），当前不可发布。**
   必须补一次真实终端捕获（`--list --json` + `md5sum`，裁切后 ≥38s），否则 qc 该检查不过。报告已列，但这是 **P0 阻塞项**，不是备注。
2. **B 组 423/423 贴字数上界，无余量。** 目标 385、上界 423.5，`social_count=423` 已贴边；TTS 一旦按 220cpm 略快或发音拉长就会破 120s。建议**写稿阶段就压到 380–400 字**，不要等配音超时长再删。
3. **A 组 Hook 是"失败先于成功"的前后叙事**，画面/字幕必须交代清楚"第一次没生效 → 同步后哈希一致"，避免观众误以为现在仍坏。当前口播成立，字幕卡需要补一句状态闭环。
4. **两支同源、开头框架近乎重复。** cadence 允许一个素材派生两条资产，但发布要错开周次，且两条 Hook 不得同周撞句。
5. 两个工具层缺口（目录成员校验缺失、路径基准混用）已被 B 组当成"风险/根因"讲出来，但**只是被叙述，工具本身还没修**；应在下一轮由 Claude Code 落到 `check_account_dna.py` 与 DNA schema。

## 4. 发布阻塞清单（两支均未解除前不得进入 compose/qc 成片）

- [ ] A：补真实终端录屏 ≥38s，真实素材比回到 ≥70%
- [ ] A：补 `.gitignore` 第 31 行实拍画面
- [ ] B：口播压到 380–400 字，重跑 `wordcount.py` 退出码 0
- [ ] B：补 `CATALOG_ROOTS` 三行、`check_account_dna.py` 四字段校验段两张局部源码截图
- [ ] B：仓库公开 URL 确认前，`REPRO_AND_REPO` 只留相对路径，不念链接、不写开源可用
- [ ] 人工评审通过前不发布、不生成发布链接；`assemble.py` 与 `qc_video.py` 判定逻辑不改

## 5. 下一步交给 Claude Code 的提示词

见同目录 `claude-code-step2-hardening-prompt.md`。

## 6. Round 3 独立复核（2026-10-28，Step 2 回报后复跑）

### 6.1 命令层复跑结果（未沿用 Claude 回报，本机重跑）

| 检查 | 复跑结果 |
|---|---|
| `python scripts/check_account_dna.py` | PASS，2 accounts，退出码 0，0 warning |
| `skill_route.py --list --json` 计数 | 114，`video-script` 在 produce 层 |
| `python tests/test_account_dna.py` 直接运行 | 退出码 0；含新增 `unknown skill fails` / `repo-relative must exist` / `undeclared base not assumed` / `repo-only declared` 四条 |
| `python scripts/dev_check.py` | ALL CHECKS PASSED，退出码 0 |
| A `wordcount.py check --target 202` | social_count **205**，区间 [182,222]，退出码 0 |
| B `wordcount.py check --target 385` | social_count **390**，区间 [347,423]，退出码 0（距上界 33 字 ≈9s 余量） |

### 6.2 diff 复核

- `git diff --name-only` 中 **`auto-short-video/scripts/assemble.py`、`scripts/qc_video.py` 零改动**；修改仅限两份 DNA、`check_account_dna.py`、`test_account_dna.py`、`research/README.md`。
- 两份 DNA 的 `qc` 条目各加一行 `"path_base": "repo"`，其余条目缺省 `catalog`。
- 新校验复用 `skill_route.CATALOG_ROOTS / _front_matter / catalog`，校验目录存在、SKILL.md 存在、frontmatter `name` 匹配、catalog 相对脚本存在、repo 相对文件存在；无 catalog 时报 warning 不 failure；缺省 `catalog` 但既非目录成员又未声明基准时，failure + warning。非空壳实现。

### 6.3 脚本一致性复核（程序化比对，非目测）

- A：md 口播 8 行 = narration 8 行，`identical=True`；B：10 行 = 10 行，`identical=True`。
- B CTA 仍为 DNA 锁定原句「需要复现或交付，评论区说你的技术栈。」；A CTA「先把 CLI 线跑一遍，再决定要不要用。」未改。

### 6.4 本轮新发现 / 仍未解除的阻塞

1. **A 组 `NEXT_VALIDATION_OPPORTUNITY` 仍是 stale 口播**：narration 第 7 行「下期验证：让 DNA 的路径和 skill 目录自动对账」对应的校验本轮已落进 `check_account_dna.py`，进 compose 前必须改写为真正的下一步（如「把这条校验挂到 CI，每次提交自动跑」）。当前 md 剪辑备注已标注，但**脚本正文未改**。
2. **B 组根因二拍口播仍是过去时**：`还有一个坑…两种基准，容易写错`，画面备注已更新为「靠声明不靠猜」，口播未补「现已由 `path_base` 显式声明」；不阻塞字数，属措辞打磨。
3. B 组锚点「目录即注册表」口播只出现一次，第二次回扣是字幕/画面层；手册第 3 节偏好口播回扣，非阻塞项。
4. 真实素材缺口与上节一致：A 组终端录屏 ≥38s、`.gitignore` 实拍；B 组 `CATALOG_ROOTS` 与 `_check_skill_route` 源码截图；公开 URL 确认前不念链接。

> 备注：本地 Python 环境未装 `pytest`，无法复现回报中的「28/28」pytest 计数；按测试脚本自带的直接运行入口（`python tests/test_account_dna.py`）已全部通过，结论不受影响。


## 7. 收口复核（2026-10-28 晚）

§6.4 的四项，现状如下（复核方式与结果见
`research/video-replication/dy1024-absorption-2026-10-28.md` 的「Step-3 script
smoke closure」表）：

1. A 组 stale 口播行：**已改写**，现为「下一步：CI 拿不到 catalog，校验只能跳过，得让它真跑起来。」仓库内已无可复现的 stale 句。
2. B 组根因二拍：**已补**收口句「现在靠 path_base 字段显式声明，不靠前缀猜。」
3. 「目录即注册表」第二次回扣仍是字幕/画面层，**保持非阻塞**，未改口播。
4. 真实素材缺口**未解除**：A 组终端录屏 ≥38s 与 `.gitignore` 实拍、B 组 `CATALOG_ROOTS` 与 `_check_skill_route` 源码截图、公开 URL，都只能由人录制/确认。本轮未编造任何替代素材。

一致性回归：md 口播与 `.narration.txt` 逐行一致（A 8/8，B 10/10）；`wordcount.py
check` 在 200/202 与 389/385 均退出 0；两条 CTA 未改。
