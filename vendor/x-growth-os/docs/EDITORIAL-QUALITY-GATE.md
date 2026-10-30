> **2026-10-26 RECOVERY OVERRIDE:** Independent proof and account/audience fit are now hard gates; read [recovery V2](X-GROWTH-RECOVERY-2026-10-26.md). A subjective 24/30 or 26/30 rating alone does NOT authorize publication, establish demand, or predict reach. Reject repeated three-step vendor summaries unless grounded in a unique decision-changing source analysis or a permission-cleared firsthand artifact. Add `audience_job`, `proof_grade=P0/P1/P2/P3`, `unique_artifact_ref` and `experiment_variable` to the draft card. Preserve existing source, permissions, image and originality checks.

---

# Editorial Quality Gate V1 — 非泛泛而谈的 X 技术观点

**生效：2026-10-25**。**2026-10-25 新增 X 热议数据与 GitHub 商业价值闸门**：按 [X Signal SOP](X-SIGNAL-RESEARCH.md) 核查互动数据的来源和日期，按 [GitHub Value Audit](GITHUB-VALUE-AUDIT-2026-10-25.md) 核实用户工作、可测试 ROI 及部署维护成本；热度/Star 不能代替事实或业务需求。适用于 DAILY-POST、GITHUB-URL-TO-X、Skill、72h News、商业假设。不改变 V0 人工发布政策。

## 反思原有两篇

- #001 Verification Before Completion：“No run = unverified fix”正确但更像检查清单。更有原创性的角度是：**Agent 的“完成声明”只是文本输出，团队需要让完成状态绑定可执行的验证证据**。这是编辑推断，不是实测改进率。
- #002 MCP Builder：“MCP ≠ API wrapper”正确但常见。更好的角度是：**API 单次调用成功 ≠ Agent 能找到正确工具、处理错误并完成真实任务**。Anthropic 上游确实包含工具命名、错误处理和 10 道可验证评测问题；不应将“高阶工具取代所有 API”误称官方建议。
- 上述两篇原稿仍为 `draft`；升级标准不意味着已改发、更没有真实涨粉证明。

## 发表前先进行四步分析，而不是立刻写推文

1. **Signal（证据）**：明确项目真实 Release/PR/Skill/代码事实，来源 URL 和事件时间。上热榜不是最近升级；旧 Skill 属于 evergreen。
2. **Tension（真实矛盾）**：原来怎样做？为什么常见方法无法解决某个具体工作流/商业决策？必须是可信的限制，不能刻意制造争议。
3. **Mechanism（因果链）**：具体输入→操作→输出→容易失败的环节；解释为什么会发生变化。区分**原文事实**、**作者推断**、**未经验证商业假设**。
4. **Consequence + Test（后果与验证）**：谁应该改变什么决定？用哪个简单可复现的实验/指标挑战这个结论？要列出最强反例和适用边界。

**先产出至少 3 个真正不同的候选判断**（推荐从隐藏瓶颈、成本/性能权衡、二阶影响、可收费交付中取 3 类），分别写判断、证据、反例、读者行动。不能把同一观点改三种句式当作三个候选。

## 人工原创洞察评分（0–5 / 项，总分 30）

| 维度 | 低分 | 高分 |
|---|---|---|
| 新颖性 | README 复述/常识 | 非显而易见且可辩护 |
| 证据 | 无法核实/无原始链接 | 一手资料、范围与反例清楚 |
| 因果机制 | “AI 提效”的泛泛判断 | 解释哪步变化、为何及何时失效 |
| 受众决策价值 | 读者无法行动 | 能影响一项实在的工具、开发或采购决策 |
| 具体可证伪 | 口号 | 给出有输入输出/指标的测试 |
| 表达张力 | 产品介绍 | 首两句准确揭示技术矛盾和后果 |

**建议入选 ≥24/30，且新颖性、证据、机制各≥4。** 这是人工编辑启发式评分，并非 X 平台公式，也不意味着保证传播。如果素材实在不够，换更有证据的 evergreen 主题；**不要编造“反常识”结论或者以低质量硬凑日更**。

### 三个必须通过的红队问题

- 抹掉项目名字，这是不是任何 AI 资讯号都能写的套话？若是，补充具体场景/因果机制。
- 资深工程师会拿什么反例驳倒它？删掉无法支持的绝对化主张。
- “So what?”：目标读者看完应该改哪项实践？如何判断改了有效？答不出则不发。

## 英文帖子及配图的验收

- 默认**一条英文帖**，必要时 2–3 条，最多三条。先写鲜明但真实的核心判断，再写机制/后果；**不是项目功能清单**。不要堆砌三种机制进 280 字符，挑最强一个。
- 加权字符符合 X 普通账号 280 上限；原始字符串长度不等于最终长度。给出代码点数、URL 加权估算，并在 X Composer 人工复核。
- 不造测试结果、10x 性能、商业收入、真实客户或时间新鲜度；如属预测明确标注“可能、需要验证”。
- 英文 16:9 图**强化这个观点的因果结构/失败链**，不得无关产品混入。生成工具返回错图就丢弃重做或明确未生成；不能把概念图当实测截图。
- 输出应包含：一手证据、三角度、最终判断、六维评分、最强反例、英文可复制正文、中文翻译、实际图和 ALT、发布建议。**没有实际 X URL，只能是 draft。**

## 参考依据

- X 官方关于原创评论与低增量转述的区别：https://help.x.com/en/using-x/original-content-rewards
- X 写作建议，强调 Hook、真实例子、易读、自然表达：https://help.x.com/en/using-x/articles
- GitLab 技术传播建议，强调见解与实际经验：https://handbook.gitlab.com/handbook/marketing/product-and-technical-marketing/developer-advocacy/social-media/

**说明**：标准是编辑原则，未通过真实 X 账户 A/B 实验验证；仍以每周有意义的互动和粉丝质量复盘。
