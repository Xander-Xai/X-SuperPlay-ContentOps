---
name: benchmark-playbook
description: >
  X-SuperPlay 双账号爆款复刻脚本手册。从 9 位对标博主（小天fotos/Simon林/浙大猫学长/
  Ai林爻/陈与小金/李白/柱子哥/花叔/秋芝2046）的逐字稿复核中提炼，供 video-script 在生成
  x-superplay-1024 与 x-superplay-future-intelligence 脚本时强制遵循。
  当目标账号是这两个账号之一时，必须读本文件再写稿。
---

# 爆款复刻脚本手册

> **证据来源与可信度**：2026-10-27/28 的抖音逐字稿复核。原始逐字稿与复核笔记
> （`research/video-replication/verification-round-2026-10-28.md`、
> `three-creators-analysis-2026-10-28.md`）**没有进入本仓库**，本文件是那次复核的
> 结论沉淀。引用逐字稿时请把它当作「当时记录的观察」，不是仓库内可复核的证据。
>
> **事实源**：本文件是 video-script 在「我们自己的账号」语境下的覆盖层。凡是
> 账号 DNA（`config/accounts/<slug>.json`）已经声明的事实——语速、时长窗口、拍数、
> CTA——**以 DNA 为准**，本文件只讲「怎么用」，不复述那些数值。

## 0. 第一条：语速与时长以账号 DNA 为准

通用 video-script 自带一个默认语速。**我们的两个账号都覆盖它**，事实源是各自 DNA 的
`narrative.speech_rate_cpm`。写稿时按下面的换算推导口播字数，而不是照抄任何写死的数字：

```
口播字数 ≈ (目标时长秒数 / 60) × narrative.speech_rate_cpm
容差 ±10%
画面时长 ≥ 口播时长（音频优先）
```

> 上面是公式，不是数值。时长窗口见 DNA 的 `narrative.target_duration_s`，语速见
> `narrative.speech_rate_cpm`。两个账号当前都是同一语速，但不保证永远相同——所以
> 写稿前读 DNA，不要记住某个数字。
>
> 音频优先：先定稿口播字数，再据此排画面。画面时长必须 ≥ 对应口播时长，否则音画
> 不同步（来源：小天fotos Tutor Skill 逐字稿「先分镜、先语音、再按语音长度设计画面」）。

## 1. 双账号脚本模板（逐拍对齐 DNA）

拍名以 DNA `narrative.template` 为准。下面是**每一拍怎么写**，不是「有哪些拍」——
拍清单去 DNA 读。

### A 组｜x-superplay-1024（Explore，实测+翻车+成本）

DNA `narrative.mode` = `RESULT_FIRST`，`narrative.opening` = `CONFLICT`，
节奏见 `narrative.pace`。逐拍写法：

| 拍 | 内容 | 写法要求 |
|---|---|---|
| HOOK_3S_CONFLICT | 3 秒内给反常识结论或翻车冲突 | 不铺垫、不「大家好」；对标：Simon林「我用 CEO Agent 把自己替换了」、小天fotos「今天很开心但很沮丧」 |
| TASK_STATEMENT | 一句话说清这次到底测了什么 | 范围锁死，不拔高 |
| MEASURED_PROCESS_WITH_EVIDENCE | 实测过程，证据型录屏（ALLOWED_CROPPED） | 每个事实头都能追溯到一次真实录制/真实回执；录屏只留报错/输出/日志区，先整段后放大 |
| FAILURE_OR_BOUNDARY | **必须讲翻车或边界**（Explore 灵魂） | 对标：小天fotos Agent Teams 荒诞现场、Simon林自曝无用功。诚实暴露失败 = 信任 |
| COST_AND_LIMITS | 成本与限制 | DNA 可能把这一拍标为 deferred（见 `narrative.template_coverage`）；deferred 时**禁止编造数字**填充 |
| WHO_IT_IS_FOR_AND_NOT_FOR | 这套适合谁、不适合谁 | 一句划清，不讨好所有人 |
| NEXT_VALIDATION_OPPORTUNITY | 下期验证钩子 | 不喊「关注我」，留一个具体待验证问题 |

CTA：**逐字使用 DNA `narrative.cta`**，不要改写。

### B 组｜x-superplay-future-intelligence（Build，可复现工程拆解）

DNA `narrative.mode` = `ENGINEERING_WALKTHROUGH`，开场 `EVIDENCE`，节奏按 DNA。逐拍写法：

| 拍 | 内容 | 写法要求 |
|---|---|---|
| HOOK_3S_PAIN | 3 秒直接抛工程痛点/故障 | 对标：Ai林爻「折腾了一周终于搞懂」、陈与小金「AI 不是给人用的吗？」 |
| REQUIREMENT_AND_TRADEOFF | 需求 + 为什么要这么做、放弃了什么 | 不堆 API 列表 |
| ARCHITECTURE_CHAIN | 架构链（配矢量动画，零录屏） | 对标 Ai林爻 RAG 全链路；工具分工表开场 |
| KEY_CODE_EXPLAINED | 关键实现讲透（一句话锚点+分步） | 对标：「预测下一个 token」一句话反复回扣；生活类比（DJ 台旋钮/开卷考试） |
| ROOT_CAUSE | 失败边界 / 根因 | 对标陈与小金「干活的人不能给自己打分」 |
| ACCEPTANCE_METRICS_AND_RISK | 验收指标与风险 | 指标必须来自真实运行结果，禁用示意数字 |
| REPRO_AND_REPO | 复现步骤 + 仓库链接收口 | 收藏优先：让人能回来照着做 |

CTA：**逐字使用 DNA `narrative.cta`**，不要改写。

## 2. 爆款 Hook 库（按已验证数据选用）

写 Hook 时从下面选，不要发明新类型。每条标注证据来源：

| Hook 类型 | 句式 | 已验证案例 |
|---|---|---|
| 角色替换/反常识 | 「我把自己换成了一个 X Agent」 | Simon林 CEO Agent（6.3k 赞） |
| 情绪反差 | 「今天很开心，但又很沮丧」 | 小天fotos GLM5 |
| 结果前置+利益承诺 | 「上线一天 star 破百」/「我全程只说了一句话」 | Simon林投研、陈与小金双 Agent |
| 翻车现场 | 直接展示失败/报错现场，不藏 | 小天fotos Agent Teams、Easel 实测 |
| 标题性报价 | 「40 分钟学会 Codex」（实际 40:28，说到做到） | 秋芝2046（收藏 = 点赞） |
| 身份精准触发 | 「如果你是拿 AI 去上班的打工人…」 | 秋芝2046 粉丝画像 |

> 案例里的赞数是**那次复核时看到的数字**，不是当前实时数据。引用前若用作断言，
> 必须有当前可核验来源；否则只说「有博主这样开头」，不报数。

禁用钩子：「大家好我是 XX」、「今天给大家分享」、震惊体「速看/已删」、与内容不符的悬念。

## 3. 节奏公式（直接套用）

- **A 组短平快（柱子哥公式，已验证 2:03 结构，压缩到我们 45–60s）**：
  3 秒爆点结论 → 10 秒任务/案例背景 → 主体实测+翻车 → 收口到「这跟你有什么关系」。
  （45–60s 是 DNA 的时长窗口示例，写稿前以 `narrative.target_duration_s` 为准。）
- **B 组收藏优先（秋芝2046 说明书式）**：
  标题写清「范围+成本+交付物」；先给结果/先上手，再讲门槛；复杂处分段，让观众能跳回来查。
  我们的 B 组不做爽片，做「值得收藏复看」的工程说明书。
- **一句话锚点**：全片挑一句核心论点（如「预测下一个 token」「文件即接口」），在开头和结尾各回扣一次。

## 4. 证据阶梯红线（写脚本时强制，违反即返工）

- 信号强度顺序见 DNA `evidence_ladder` / `non_negotiable`：**低阶信号永远不能冒充高阶**——
  不能把「有人点赞」写成「大家都在用 / 已经爆了」。
- 没有真实可访问 URL，不得宣称「已上线/已发布/已开源可用」。
- 数字必须来自真实运行回执或真实快照；**禁止编造 star/时长/成本/用户数**。没有就写
  「暂未测」，不留空也不编。
- 不得把代码完成当生产验证，不得把 AI 生成画面当真实证据。
- 不夸大项目阶段：业务阶段是 Stage 0（见 DNA `business.stage`），脚本不得暗示
  「已产品化/已盈利」。
- 高级断言（「最好的/第一/碾压」）必须配对一个可核验来源，否则降级为「我实测下来」。

## 5. 画面备注怎么写（喂给下游动画/录屏模块）

脚本的「画面」列不是写美术字，是给执行模块的指令：

- A 组：写清「录屏哪一段、保留什么区域、先整段后放大」；敏感信息（店名/凭据/无关窗口）
  必须标注 `REDACT`。
- B 组：写清「这里要一张什么架构图/流程图，节点 A→B→C，哪个节点高亮」；**禁止写
  「录屏/点击/鼠标」**（Build 组 manual recording = FORBIDDEN，见 DNA `evidence`）。
- 每个画面备注后标预计秒数，且 ≤ 对应口播字数换算的时长。

## 6. 写完自检（交付前逐条过）

- [ ] 口播字数落在「公式一」的推导区间内（`skills/shared/scripts/wordcount.py` 判定，不目测）
- [ ] Hook 来自第 2 节库，且 3 秒内出现
- [ ] 拍数与拍名对齐 DNA `narrative.template`；deferred 拍已显式注明
- [ ] A 组含翻车/边界；B 组含根因+复现步骤
- [ ] 每个数字都有真实来源；无 URL 处未宣称上线
- [ ] CTA 逐字等于 DNA `narrative.cta`，不是「点赞关注」
- [ ] 画面备注遵守该账号的录屏/红线规则
