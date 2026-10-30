# 视觉导演计划｜MCP工具调用之后，谁来管Agent的下一步？

- 账号：thinktank
- 视觉系统：thinktank-atlas
- 证据策略：证据素材优先；确定性图优先；Agnes 仅用于 illustrative 视觉增强
- 生成素材版权策略：生成图标记 illustrative；不冒充事实证据；人工复核后方可发布
- 移动端安全区：关键主体和信息位于画布 10% 内边距；公众号标题由 HTML 后置叠加
- 连续生图上限：2 张

| 素材 | 读者任务 | 视觉负责人 | 生成模式 | 来源策略 | fallback | 状态 |
|---|---|---|---|---|---|---|
| cover | 首屏用可信英文主题文案清晰说明文章主题：A PRACTICAL ENGINEERING MAP；背景只承担氛围与视觉隐喻。 | illustration | agnes | generated-illustrative | text_poster.py | ready |
| body-01 | 解释“一、能调用工具，不等于能安全上线”中最重要的一条因果或结构关系 | diagram | deterministic | deterministic-renderer | deterministic-svg | ready |
| body-02 | 呈现“二、MCP的新边界：请求本身要能被治理”中节点、状态与流转关系 | diagram | deterministic | deterministic-renderer | deterministic-svg | ready |
| body-03 | 用可运行代码（默认 PyTorch 实战，基础版可用 NumPy 直觉）复现「四、显式许可：让工具调用先过一道看得见的门」的核心公式或算法，控制在前 40 行内 | diagram | deterministic | deterministic-renderer | code-block | ready |
| body-04 | 呈现“五、最小可复现实践：用三个工具跑通治理闭环”从入口到运行时与持久化的系统边界 | diagram | deterministic | deterministic-renderer | deterministic-svg | ready |
| body-05 | 呈现“七、结语：治理的对象是下一步动作”从入口到运行时与持久化的系统边界 | diagram | deterministic | deterministic-renderer | deterministic-svg | ready |
