# 从零用 GitHub 学 LLM｜寻找项目、动手验证、建立个人学习仓库

> **完整教程（13 节）** · 2026-10-25 · 来源于官方 GitHub / Datawhale / Microsoft 文档的原创学习方案。文章完整可编辑版本也以 `GitHub_LLM_Full_Guide.md` 的形式随本次 ChatGPT 对话交付。  
> **读者最终交付**：自己的 `llm-learning-notes` 仓库，包含项目筛选、固定版本、至少一次亲自执行的实验记录、错误处理和下一步学习路线。  
> **状态区分**：这里的 GitHub 网页操作为**未在新测试账号上逐步复核**的教学说明；其中第 7 节原创新手小实验确实在 Linux/Python 3.13.5 执行并通过 5 项测试。Datawhale 完整训练教程尚未执行。

## 1. 从一个成果开始，而不是从术语开始

“我要学 LLM”没有明确完成标准。先决定今天的结果：**找 3 个可靠项目、挑出一个能跑的练习、把结果记进个人 GitHub 仓库**。Star 20 个项目不算学会；能给出版本、步骤、输出和失败说明才算形成学习证据。

**检查点**：写一句自己的目标，如“我能解释 Causal Mask 并通过一个 CPU 测试说明未来 token 不应影响先前输出”。

## 2. 搜索 GitHub：用任务词而不是热词

打开 [GitHub](https://github.com)，搜索 `LLM from scratch`、`LLM tutorial`、`LLM deployment` 并切到 **Repositories**。缩小范围时尝试：

```text
llm in:name,description
llm in:readme
llm language:Python
llm stars:>500
llm pushed:>2026-01-01
```

这些查询是过滤候选的方法，不是可靠性排名。`pushed` 表示提交时间而不是重大更新；Star ≠ 内容适用。**检查点**：留下三个**完整**仓库 URL 和一句选择理由。

## 3. 识别你拿到的是“课程、代码库，还是应用”

查看 `README`（先修和目标）、`docs`（完整内容）、`examples/notebooks`（有无实验）、`Releases/Tags`（版本）、`Issues/Discussions`（报错）、`LICENSE`（复用限制）。课程有章节并不保证可直接运行；应用的 Install 并不等于学习底层模型架构。

| 动作 | 实际意义 |
|---|---|
| Star | 收藏、关注 |
| Download ZIP | 当前分支源文件快照，没有完整 Git 历史 |
| Clone | 取得仓库及其 Git 版本历史用于本地开发 |
| Fork | 创建自己账号下的关联副本 |
| PR | 对代码修改进行比较、审查与合并 |

**检查点**：辨别选中的每个仓库是原理课程、带代码的实验，还是可下载运行的工具。

## 4. 三条真实 LLM 学习路线

| 完整原仓库 | 适合目标 | 先核验什么 |
|---|---|---|
| [microsoft/generative-ai-for-beginners](https://github.com/microsoft/generative-ai-for-beginners) | 从应用认识生成式 AI | 21 个章节、练习和 API 费用/账号前置 |
| [datawhalechina/diy-llm](https://github.com/datawhalechina/diy-llm) | Transformer、Tokenizer、模型训练原理 | Python/PyTorch、数学先修、数据集与 GPU 要求 |
| [datawhalechina/self-llm](https://github.com/datawhalechina/self-llm) | 实际开源模型部署、推理与微调 | Linux 环境、所选模型是否仍受支持、显存和模型许可 |

不要一次 Fork 十个。**建议先选一条主线**：本教程以 [DIY-LLM 第四章](https://datawhalechina.github.io/diy-llm/) 为概念来源，先跑一个原创小实验，然后再学习上游真实训练作业。

## 5. 在 GitHub 建一个自己的 `llm-learning-notes`

访问 [New Repository](https://github.com/new)，命名 `llm-learning-notes`，描述填 `Reproducible LLM learning: sources, experiments, results and next steps`。私密笔记可选 Private；准备公开教程时先检查隐私与许可。勾选 README 并创建仓库。

将 README 初稿改成：

```markdown
# My LLM Learning Notes
Goal: Learn one concept by running a verifiable experiment.

## Sources
- Datawhale DIY-LLM: https://github.com/datawhalechina/diy-llm
- Microsoft GenAI: https://github.com/microsoft/generative-ai-for-beginners

## Experiments
| Experiment | Status | Evidence |
|---|---|---|
| Causal attention | NOT_RUN | Pending |

## Next
Select a precise chapter and pin a source version.
```

点击 **Commit changes**。**检查点**：自己的仓库出现 README 和 `NOT_RUN`，而不是复制别人的成功日志。

## 6. 固定来源和版本，避免教程漂移

打开 [DIY-LLM 源仓库](https://github.com/datawhalechina/diy-llm)，阅读 [第四章](https://github.com/datawhalechina/diy-llm/tree/95a3b81d4b2686d33afc2d533b0f91d295ec9b78/docs/zh/chapter4) 的注意力部分。记录参考提交 `95a3b81d4b2686d33afc2d533b0f91d295ec9b78` 与读者的操作系统/解释器版本。将这段信息写到 `sources.md`。

**检查点**：可以回答“我跟的是哪一版，是否需要下载训练数据、是否需要模型权重”。不要把原作业的 `train.py` 简写成零依赖/一键训练：README 要求 tokenizer、数据以及 PyTorch 等依赖。

## 7. 动手练习：证明 Causal Mask 的一项性质（已实测）

这次**不是**运行完整 Datawhale 作业，而是根据注意力公式自主编写一个一维 `Q=K=V` 的 CPU 玩具模型。配套文件：

- [`causal_attention.py`](../llm-causal-mask-mini-lab/causal_attention.py)
- [`test_attention.py`](../llm-causal-mask-mini-lab/test_attention.py)
- [真实 5 项测试和运行记录](../llm-causal-mask-mini-lab/REPRODUCTION-2026-10-25.md)

在拥有文件的目录运行（Python ≥3.9）：

```bash
python causal_attention.py
python -m unittest -v
```

真正执行过的输出：

```text
causal     token0: 1.000000 -> 1.000000
non-causal token0: 2.575210 -> 30.000000
causal prefix unchanged: True
PASS: future tokens cannot affect earlier outputs when causal mask is on
```

实验只把未来 token 从 `3` 变成 `30`。因果掩码使第一个位置看不到未来，所以第一个输出不变；无遮挡的结果会变化。**本次 Python 3.13.5/Linux 测试 5/5 PASS**，但不代表真实 Transformer 训练/微调通过。

## 8. 出错时先定位环节，再找 Issue

| 报错 | 优先检查 |
|---|---|
| `python: command not found` | Windows `py -3 --version`、macOS/Linux `python3 --version` |
| `ModuleNotFoundError` | 是否在包含两份 Python 文件的同一工作目录 |
| GitHub `404` / `Repository not found` | URL、权限、Private 仓库能否访问 |
| 真实训练显存不足 | 单独核实 batch size、context length、模型规模和实际 GPU 环境，不盲目复制别人配置 |

保存**真实失败**同样是一项学习成果。绝不把密码、API Key、终端令牌加入截图或 Git 历史。

## 9. 把自己的输出而不是别人的 README 存入学习仓

在自己的仓库建立 `experiments/attention-mask.md`：

```markdown
# Experiment 01 — Causal Mask
Source: https://github.com/datawhalechina/diy-llm
Environment: [MY OS, PYTHON VERSION]
Input changed: [1, 2, 3] -> [1, 2, 30]
Expected: earlier causal output unchanged
Observed: [MY ACTUAL STDOUT]
Tests: [MY COUNT, PASS / FAIL]
Next: [ONE PRECISE FOLLOW-UP]
```

通过网页添加，或者使用本地 Git 提交。**检查点**：别人看得懂来源、输入、输出、结论与边界；`NOT_RUN` 必须有实际证据后才改为 `PASS`。

## 10. 用一次 Branch 和 PR 记录学习进步

在自己的笔记仓创建 `add-first-experiment` 分支，编辑实验文件，通过 PR 比较后再合并。这会让你理解“实验如何进入主线”，也练习工程审查。

已配置 Git 且有正确账号权限时可尝试：

```bash
git clone https://github.com/YOUR_USERNAME/llm-learning-notes.git
cd llm-learning-notes
git switch -c add-first-experiment
# 本地创建 experiments/attention-mask.md 后：
git add experiments/attention-mask.md
git commit -m "Document causal attention experiment"
git push -u origin add-first-experiment
```

在 GitHub 新建 PR，查看差异并合并。首次 Git 使用可能还需要身份与凭据配置，详情见 [GitHub Git Docs](https://docs.github.com/en/get-started/using-git/about-git)。**检查点**：在自己仓库的 PR/提交历史中找到这次学习增量。

## 11. 系统学习地图：每层都要有作品

| 阶段 | 重点 | 通过标准 |
|---|---|---|
| GitHub 基础 | Search、README、Releases、Issues、PR | 有 3 项来源和自己的笔记 |
| LLM 原理 | Tokens、QKV、Attention、Mask、RoPE | 自己解释并运行一项模型性质 |
| Tiny 模型训练 | Tokenizer、训练循环、Loss | 根据上游完整依赖运行一项真实训练 |
| 运行开源模型 | Transformers、设备与许可 | 真正本地推理并记录显存/时长 |
| AI 应用 | RAG、Agent、Evaluation | 有可复核的任务和评测 |
| 商业验证 | 买方、成本、验收、维护 | 有付费意愿和真实试点证据 |

**我们目前只完成了其中一个 CPU 玩具实验。** 后续环节是学习计划，不是已交付训练结果。

## 12. 怎样用学习成果提效、甚至验证商业机会？

真正有价值的不是“安装了一个很火的仓库”，而是能否解决一个重复工作：文档处理、知识库查询、客服工单、内容生产流程等。

用**相同样本**比较人工和工具流程：净节省时间 = 原人工时间 − 工具操作时间 − 审核时间 − 重做时间。考虑部署、API、维护与隐私成本。要做收费服务，先确认买方、重复需求、交付范围、可核实的验收标准和愿付价格；GitHub Stars、X Views 都不是商业收入证据。

## 13. 这篇教程是否真的学完了？

- [ ] 创建自己的 `llm-learning-notes` 仓库并保存 README。
- [ ] 留下三个完整原始学习仓库链接，解释目标与门槛。
- [ ] 固定一个章节、代码版本和实际运行环境。
- [ ] 自己执行一次小实验并记录 stdout 或失败。
- [ ] 保存实验笔记，通过 Git 提交或 PR 留下历史。
- [ ] 写下一个具体、可被验证的后续学习任务。

**最后的成果不是一份“最好的 100 个 LLM 仓库清单”，而是一份能证明你确实在学习的 GitHub 记录。**

---

### 归属、公开性与阅读范围

- 教学结构参考 [G哥 X Article](https://x.com/goan999999/status/2113525221374488901) 的任务驱动和长文章做法；所有 LLM 学习路径、示例仓库、文案为独立创作，未复制原文与截图。
- 内容来源：[GitHub Docs](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories)、[Microsoft GenAI Beginners](https://github.com/microsoft/generative-ai-for-beginners)、[DIY-LLM](https://github.com/datawhalechina/diy-llm)、[Self-LLM](https://github.com/datawhalechina/self-llm)。
- 课程原始 Markdown 更完整的本次作者对话交付文件：`GitHub_LLM_Full_Guide.md`，**已生成可下载但并非 GitHub 自动同步的文件**。
- 本运营仓库仍为 **Private**。本地址是内部审核地址，不可冒充公开 X 长文链接。若需要面向 X 读者提供完整版，应通过可访问的 X Article（取决于账号资格）或专门公开教程库发布，**不得直接公开整个私人运营仓库**。
