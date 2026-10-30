# 用 GitHub 学 LLM｜第 1 课：亲手证明 Causal Mask 为什么必要

**Build & Learn · Lab 01 · 2026-10-25**  
**复现状态：PASS（仅本仓库原创新手实验）** · **主课程状态：尚未执行 Datawhale 完整训练作业**  
**一项可观察成果：** 修改未来 token 后，验证开启因果掩码时此前 token 的注意力输出不会变化，而关闭掩码时会发生变化。

> 这是为学习 [Datawhale DIY-LLM 第四章](https://github.com/datawhalechina/diy-llm/blob/95a3b81d4b2686d33afc2d533b0f91d295ec9b78/docs/zh/chapter4/chapter4_%E7%AC%AC%E5%9B%9B%E7%AB%A0%E8%AF%AD%E8%A8%80%E6%A8%A1%E5%9E%8B%E6%9E%B6%E6%9E%84%E5%92%8C%E8%AE%AD%E7%BB%83%E7%9A%84%E6%8A%80%E6%9C%AF%E7%BB%86%E8%8A%82.md) 配套编写的**独立原创 CPU 小实验**，不是 Datawhale 官方作业结果或完整 Transformer，更不是已训练的 LLM。数据、输出和测试来自本次真实运行。

## 0. 为什么先做这个？

GitHub 有大量 LLM 课程，但“阅读仓库”“下载模型”“执行训练”不是同一件事。先从**可以用单元测试证明的一条模型性质**开始。

针对自回归 decoder-only 语言模型，在预测当前位置时，不应泄露未来位置的 token 信息。可以通过 causal attention 的上三角遮蔽来保证这一点。我们把最后一个值由 `3` 改成 `30`，观察**第一个位置**的输出是否变化。

这个测试只需要 Python 标准库（无 PyTorch、GPU、API Key、模型权重或账单）。

## 1. 前置知识与成本

| 项目 | 要求 |
|---|---|
| 读者 | 会运行 Python 文件、理解列表和函数 |
| 系统 | Linux/macOS/Windows；**本次只在 Linux 环境运行了验证** |
| Python | ≥3.9（因使用 `list[float]` 注解）；本次实测 3.13.5 |
| GPU | 不需要 |
| 第三方包 | 无（仅 `math` 和 `unittest`） |
| 费用 | 这个**本地实验**没有付费 API 调用；不代表 Datawhale 后续训练课程免费 |
| 数据 | 三个示例标量，无个人数据 |
| 源课程 | [datawhalechina/diy-llm](https://github.com/datawhalechina/diy-llm) ，固定参考提交 [`95a3b81`](https://github.com/datawhalechina/diy-llm/tree/95a3b81d4b2686d33afc2d533b0f91d295ec9b78) |

**注意**：这个 X 运营仓库当前为 **Private**。本课代码、完整文字当前只对有仓库权限的人开放；不得给普通 X 读者指向本私有目录并谎称他们可以公开访问。若要对外公开完整原创教程，先单独审核并将本课安全素材镜像到公开教程仓库，不要把整个私人运营仓库设为公开。

## 2. 对照 GitHub 原课程

先阅读 [DIY-LLM 第四章](https://datawhalechina.github.io/diy-llm/)，找到 **4.1.2 多头注意力**中的 scaled dot-product attention 公式：

`Attention(Q,K,V) = softmax(QKᵀ / sqrt(d_k)) V`

原课程实现涉及多维张量、投影、位置编码、多头及真实模型。这里刻意把每个 token 设成 **一个数值**，`Q=K=V` 并令 `d_k=1`，用标量软最大值说明因果掩码的影响。这个教学简化**不能用于评估真正 LLM 的质量或性能**。

## 3. 取得本实验文件

本目录包含：
- [`causal_attention.py`](causal_attention.py)：最小实验（原创建模）
- [`test_attention.py`](test_attention.py)：5 项标准库单元测试
- [`attention-mask-editorial.svg`](attention-mask-editorial.svg)：可编辑的英文对照图
- [`REPRODUCTION-2026-10-25.md`](REPRODUCTION-2026-10-25.md)：真实执行记录
- [`TUTORIAL-CARD.md`](TUTORIAL-CARD.md)：版本/视觉/发布审查

如果你**已获此私有仓库读权限**：

```bash
git clone https://github.com/Xander-Xai/X-SuperPlay-X-Growth-OS.git
cd X-SuperPlay-X-Growth-OS/tutorials/llm-causal-mask-mini-lab
python --version
```

Windows PowerShell 如 `python` 命令不存在，可尝试 `py -3 --version` 并将下列 `python` 改成 `py -3`。

**公开读者目前可先使用本对话附带的可下载 ZIP** 获得课程样例文件；该 ZIP 只有在作者自行上传到公开下载处后才对 X 读者可见。**不要把 Datawhale 原代码与本实验当作同一个来源**。

## 4. 执行操作（已在本环境真实跑过）

**Step 1 — 运行可比较实验**

```bash
python causal_attention.py
```

**本次真实运行输出：**

```text
Toy scalar Q=K=V attention (not a trained LLM)
causal     token0: 1.000000 -> 1.000000
non-causal token0: 2.575210 -> 30.000000
causal prefix unchanged: True
PASS: future tokens cannot affect earlier outputs when causal mask is on
```

**验证点：** 原始序列 `[1,2,3]` 与 `[1,2,30]`，**仅第三个值改变**。开启 causal mask 时第 0 个输出都是 `1.000000`；关闭时变成 `2.575210` 和 `30.000000`。

**Step 2 — 跑单元测试**

在同一目录：

```bash
python -m unittest -v
```

**实际结果（2026-10-25）：** `Ran 5 tests in 0.001s; OK`。测试覆盖：因果模式第一个输出、前缀不被未来修改影响、未遮蔽时确实受影响、空输入被拒绝、非数字被拒绝。完整名称和输出见 [复现日志](REPRODUCTION-2026-10-25.md)。

**Step 3 — 自己改变一个输入**

打开 `causal_attention.py` 的 `main()`，将

```python
modified_future = [1.0, 2.0, 30.0]
```

改成

```python
modified_future = [1.0, 2.0, 10.0]
```

再次运行后，**预期第 0 个 causal 输出仍是 `1.000000`**。非因果输出会变化，但不能未经执行就宣称本教程实测过这个新的 `10.0` 变体。完成自己的复现并记录值。

## 5. 为什么如此？技术解释

- **无遮挡（non-causal）**：第 0 个 query 会与三个 key 计算相似度，其中包含将来的第 2 项；它的加权和自然受改变后的第 2 项影响。
- **因果遮蔽**：在位置 `i` 处只纳入位置 `j ≤ i` 的 key/value，所以第 0 个输出只能使用自身信息。未来位置更改不会改变任何此前位置的本层注意力输出。
- **真实模型**：训练前会有 tokenizer、嵌入、可学习的 Q/K/V 投影、多头、RoPE、归一化、前馈网络和优化器。这个玩具实验只证明遮蔽的**一个性质**，并不等于实现真实 Transformer 或完整训练。

## 6. 常见失败与恢复

| 症状 | 检查方法 | 修复 |
|---|---|---|
| `python: command not found` | `python3 --version` 或 Windows `py -3 --version` | 使用可用的 Python ≥3.9；**不要**盲目执行陌生安装脚本 |
| `ModuleNotFoundError: causal_attention` | `pwd` / `ls` / Windows `dir` | 进入包含两个 `.py` 文件的**同一目录**再运行单元测试 |
| 测试 `FAIL` | 检查是否把 `positions = range(i+1)` 改成整个列表 | 恢复文件后对比 stdout；未来值不可出现在早期 causal key/value 中 |
| `git clone` 403/404 | 此运营仓库为私有，检查自己是否有权限 | 获取作者经批准提供的示例 ZIP；不要传播私有仓库 token |
| 图片中文字显示异常 | SVG 使用系统可替代字体 | 使用本次经检查的 PNG；不要把假输出补到图上 |

本实验没有服务端/付费资源。要撤销，只需移除单独下载的实验文件（不要删除其他项目目录、环境或课程记录）。

## 7. 跟着 GitHub 系统学习的下一步

| 课程阶段 | 官方仓库 | 掌握什么 | 本次执行状态 |
|---|---|---|---|
| 第 1 课（本课） | DIY-LLM 第四章（改写成独立 toy lab） | causal masking / future leakage / 单测 | **PASS**，5 个本地测试 |
| 下一课 | [DIY-LLM Assignment 1](https://github.com/datawhalechina/diy-llm/tree/95a3b81d4b2686d33afc2d533b0f91d295ec9b78/coursework/assignment1-basics) | 用真实 PyTorch 模型、tokenizer、优化器训练 tiny LM | **NOT_RUN**，需要数据与依赖 |
| 后续 | [LangChain Academy](https://github.com/langchain-ai/langchain-academy) | 在模型基础上学习 Agent 状态和工作流 | **NOT_RUN** |

**下节最小目标**：在可控 CPU / GPU 环境加载 Assignment 1 的模型，完成一段结构对照和一个真实测试；不要以原课程 README 的 `train.py` 例子声称已经训练。

## 8. 版权、复现证据与发布边界

- 原始学习资源归属 Datawhale，按其 [README 标注的 CC BY-NC-SA 4.0 条款](https://github.com/datawhalechina/diy-llm/blob/main/README.md) 使用。**本实验代码为独立教育示例，没有复制上游实现或图片**；商业复用上游材料前另核实授权。
- 事实来源：Datawhale [第 4 章](https://github.com/datawhalechina/diy-llm/tree/95a3b81d4b2686d33afc2d533b0f91d295ec9b78/docs/zh/chapter4)、[Assignment1 README](https://github.com/datawhalechina/diy-llm/blob/95a3b81d4b2686d33afc2d533b0f91d295ec9b78/coursework/assignment1-basics/README.md)、[PyTorch 官方 SDPA 文档](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html)。
- 本次只验证 Python 3.13.5/Linux；**未在 Windows、Python 3.9 或真实 GPU/完整训练环境运行**。再次分享时用用户实测结果更新日期。
- **X 完整交付需要英文文案 + 实际 PNG + ALT。** 本次图片在对话中可下载，GitHub 存 SVG 源文件，不谎称 PNG 二进制已入库。没有真实 X 帖子 URL 不得标记 `published`。
