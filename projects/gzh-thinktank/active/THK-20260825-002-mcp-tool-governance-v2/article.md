# MCP工具调用之后，谁来管Agent的下一步？

Agent第一次成功调用工具时，团队往往会觉得“能力已经打通”。真正进入生产环境后，问题才开始出现：它能不能调用不该调用的工具？连续调用时，前一步的结果是否会改变下一步权限？执行失败后，谁能停止、回滚并解释这次动作？

这篇文章不把多个资料硬拼成“统一标准”，而是把它们放在各自的位置上：MCP 2026-07-28 规范说明无状态传输、请求头、可选传输层授权和 MRTR 如何变化；Dogwood 提供一种带事件历史和时间条件的授权思路；Anthropic Claude Code 文档展示显式许可、拒绝规则和权限提示的产品实现。基于这些边界清晰的证据，我们整理一套可落地的 MCP 工具调用生产治理验收方法。

## 一、能调用工具，不等于能安全上线

![配图：从工具调用到生产治理的风险断点](imgs/section-01.png)

把 Agent 看成一个“会规划的调用器”，风险就更容易看清。调用工具至少包含四个动作：选择工具、填写参数、执行副作用、处理结果。只要其中一个动作没有边界，系统就可能出现越权、误操作或无法追责。

生产治理要回答的不是“模型聪不聪明”，而是四个可验收的问题：

1. **权限**：当前身份和当前任务，允许哪些工具、哪些参数？
2. **审批**：哪些动作必须让人确认，哪些低风险动作可以自动放行？
3. **审计**：能否还原谁在什么时间、基于什么上下文发起了什么调用？
4. **回滚**：动作失败或策略变化后，能否撤销、补偿或阻断后续动作？

这四个问题构成文章的治理闭环。它们是本文的工程综合，不是某一份资料声称已经提供的完整产品方案。

## 二、MCP的新边界：请求本身要能被治理

![配图：无状态请求与网关控制层](imgs/section-02.png)

MCP 2026-07-28 changelog 的一个关键变化，是移除协议层的 session 和 `initialize/initialized` handshake。这里的“无状态”指协议核心不再依赖隐藏的传输层 session，并不意味着业务应用本身不能维护状态。每个请求通过 `_meta` 携带协议版本、客户端能力，以及客户端自报的软件信息 `clientInfo`。需要注意，`clientInfo` 不是经过协议验证的安全身份，规范明确不建议依赖它做安全决策；真正用于授权和审计的 principal_id，应来自 OAuth、IAM 或应用自身经过认证的身份上下文。对于 Streamable HTTP，请求必须携带标准的 `Mcp-Method`；对于 `tools/call`、`resources/read`、`prompts/get` 等具有工具名或资源标识的请求，还必须携带 `Mcp-Name`。这样网关、限流器或 WAF 可以直接根据请求头进行路由和计量，并在适合的场景下做前置授权判断，而不必先解析完整 JSON body。

这里要注意两层边界：MCP 2026-07-28 已经定义了可选的 HTTP 传输层 OAuth 授权能力，包括 access token、资源指示和 issuer 校验；但它不替企业决定“哪个 Agent 在什么业务任务下能调用 refund、金额上限是多少、是否必须经理审批”。细粒度的工具、参数和业务动作策略，仍然要由 Host、Gateway 或策略系统实现。

一个最小的请求审计记录，至少应包含：

```text
request_id          每次工具调用唯一
trace_id            贯穿同一任务/调用链
timestamp           决策与执行发生的时间
principal_id        经认证并绑定的真实主体；可附 tenant_id
agent_id            发起调用的 Agent 身份
tool_name/version   工具名与版本
resource             被访问的资源
arguments_redacted  脱敏后的参数，供审计阅读
arguments_digest    完整参数摘要，供完整性校验
policy_version      命中的策略版本
decision             allow / deny / require_approval
decision_reason      决策原因；可附 approval_id
execution_status     最终执行状态
result_digest        结果摘要
idempotency_key      幂等键
```

principal_id 不应直接从 `_meta.clientInfo` 推导。决策先落审计，再执行；执行结束后再补记实际结果。这是把协议边界转成生产边界的第一步。参数不应只保留一个不可读的 hash：审计人员需要脱敏视图，系统还需要摘要来校验完整性。

## 三、一次授权不够：连续动作需要“时间”和“历史”

很多权限设计只问一句：“这个 Agent 能不能调用工具 A？”但真实任务更像一串动作：先读取订单，再计算金额，再发起退款。单独看每一步可能都被允许，连起来却可能形成高风险操作。

Dogwood 官方指南提供了一个相邻但有价值的政策模式：授权决策可以读取累积的事件历史和时间条件，同时采用默认拒绝的 permit/forbid 语义。它不是 MCP 的内置授权模块，因此不能写成“MCP 已经支持 Dogwood”；它更适合作为策略层的设计参考。还要注意，Dogwood 当前仓库提供的是用于理解语言语义、验证策略模型的 reference interpreter，项目明确说明它**不是生产级实现**。本文借鉴的是策略表达思想，不建议直接把该解释器当作生产授权服务。

落地时可以把策略拆成三类条件：

- **对象条件**：调用的工具、资源、租户和数据范围。
- **时间条件**：授权有效期、冷却时间、工作时间窗口。
- **历史条件**：前一步是否成功、是否已经审批、同一任务是否超过次数上限。

例如，“允许退款工具”不应只是一个永久开关，而应表达为：“订单读取成功、金额低于阈值、同一任务没有重复退款、审批状态为 approved 时，允许执行一次”。这就是把权限从静态名单升级为动作序列治理。

## 四、显式许可：让工具调用先过一道看得见的门

![配图：允许列表、权限提示与拒绝路径](imgs/section-03.png)

Anthropic Claude Code 的 CLI 文档给出了一个清晰的实现例子：`--allowedTools` 让匹配的工具**无需再次弹出权限提示即可执行**；`--permission-prompt-tool` 可以在非交互模式下把权限请求交给指定 MCP 工具处理；`--disallowedTools` 用于声明拒绝规则，其中裸工具名还可以将匹配工具从 Claude 的上下文中移除。需要注意，`--tools` 只限制 Claude Code 的内置工具，并不直接限制 MCP 工具。因此，`--allowedTools` 不是严格的“唯一允许列表”，工具的可见性、拒绝规则和执行许可需要分别治理。这是 Claude Code 的产品实现，不代表所有 MCP 客户端都默认采用同样的参数；但它说明了一条通用原则：工具权限应当可声明、可审查、可拒绝。

在自己的 Agent 网关里，可以采用同样的三段式：

1. **默认拒绝**：没有出现在任务权限包里的工具，不进入模型可用列表。
2. **风险分级**：读取、写入、外发、删除分别设定不同的审批门槛。
3. **运行时提示**：策略要求人工确认时，返回结构化的 require_approval，而不是让模型猜测下一步。

不要只在系统提示词里写“请谨慎调用”。提示词是意图，策略引擎才是约束。

```python
def decide(tool_name, allowed_tools, risk_level, approved):
    if tool_name not in allowed_tools:
        return "deny"
    if risk_level in {"write", "external", "delete"} and not approved:
        return "require_approval"
    return "allow"
```

**协议能承载确认，不代表协议替你做审批。** MCP 2026-07-28 新增的 Multi Round-Trip Requests（MRTR）允许工具在执行过程中返回 resultType 为“input_required”的结果，要求客户端补充用户确认或缺失参数，再用 inputResponses 重试原请求。这给本文定义的“require_approval”提供了协议级交互通道；“require_approval”不是 MCP 标准字段，MCP 标准字段是“input_required”。但谁可以审批、什么金额必须审批、批准多长时间有效，仍由应用侧策略决定。

## 五、最小可复现实践：用三个工具跑通治理闭环

![配图：三工具五场景的最小验证矩阵](imgs/section-04.png)

如果要开始部署，不必先做一套庞大的平台。可以用三个工具和五个场景完成第一轮教程式验收：

**工具**：read_record（只读）、update_record（写入）、send_message（外发）。

**步骤 1：建立权限包。** 为每个工具登记参数 schema、数据范围、风险级别、可审批角色和补偿动作。

**步骤 2：设置三类授权决策和一类异常恢复路径。** allow 自动放行，deny 直接拒绝，require_approval 暂停等待审批；如果已经产生副作用后发生失败，则进入 compensate 补偿或回滚流程。前三个回答“现在能不能执行”，最后一个回答“已经执行或部分执行后如何修复”。

**步骤 3：跑五个场景。** 正常读取；越权读取；低金额更新；超阈值更新；外发消息前人工确认。每个场景都保存请求、策略版本、决策和最终结果。

**步骤 4：检查序列。** 先调用 update_record 再调用 send_message 时，策略应能读取前一步结果；如果更新失败，外发动作必须被阻断。

**步骤 5：制造一次失败。** 人为撤销策略或让工具返回错误，验证系统能否停止后续调用，并留下可读的失败原因。

这套小实验的价值，不是证明系统“绝对安全”，而是让权限、审批、审计和回滚都有可观察证据。

## 六、上线前验收清单：把“看起来能用”变成证据

上线前至少逐项回答：

- 工具清单是否有版本、负责人和风险级别？
- 每次调用是否有唯一 request_id，并通过统一的 trace_id 与上游任务及后续调用关联？如果使用 MCP 2026-07-28 的约定，是否正确传播 `traceparent`、`tracestate`、`baggage`？
- 审计记录是否包含 timestamp、principal_id/tenant_id、execution_status，并能关联 approval_id、result_digest 和幂等键？
- 参数中的密钥、个人信息是否经过脱敏或摘要化？
- 默认拒绝是否真的覆盖了未登记工具？
- 需要人工确认的动作，是否能在超时后自动拒绝？
- 策略版本变化后，系统是否明确定义版本固定、动态更新和紧急撤销语义，并能追溯每次调用实际采用的策略版本？
- 工具失败、网络重试、重复提交时，是否有幂等和补偿方案？
- 审计记录能否被第三方复核，而不是只有模型的一段解释？

如果其中任何一项只能回答“理论上可以”，就还没有完成生产验收。先把证据补齐，再扩大工具范围。

## 七、结语：治理的对象是下一步动作

![配图：从能力展示到可控行动的闭环](imgs/section-05.png)

MCP 解决的是模型与工具之间如何通信，并在 2026-07-28 版本中补充了无状态请求、传输层授权和 MRTR 等能力；生产治理仍要继续追问：下一步动作凭什么被允许，谁有权确认，出了问题谁能停下来，以及事后能不能还原现场。协议能力、时间与历史条件、显式工具许可，分别提供了可组合的观察角度，但它们必须经过本地策略、日志和回滚机制才能变成真正的上线能力。

关注 X超玩•未来智能，回复‘MCP治理’领取MCP工具调用生产治理权限与上线验收清单。如果你正在把MCP工具调用生产治理落到项目里，留言你的具体问题，我会继续补充实现与部署细节。

<!-- HYBRID-EVIDENCE-REFERENCES:START -->
## 参考资料

1. [MCP 2026-07-28 specification changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx)
2. [MCP 2026-07-28 transport authorization](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/authorization/index.mdx)
3. [MCP 2026-07-28 specification release notes and MRTR](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/blog/content/posts/2026-07-28-spec-ga/index.md)
4. [MCP 2026-07-28 schema clientInfo security boundary](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2026-07-28/schema.ts)
5. [MCP 2026-07-28 Streamable HTTP standard request headers](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/basic/transports/streamable-http.mdx)
6. [Dogwood authorization and temporal policy introduction](https://github.com/dogwood-policy/dogwood/blob/main/dogwood-docs/guide/00-introduction.md)
7. [Dogwood repository README and production-use limitation](https://github.com/dogwood-policy/dogwood/blob/main/README.md)
8. [Claude Code CLI reference](https://code.claude.com/docs/en/cli-usage)

<!-- HYBRID-EVIDENCE-REFERENCES:END -->
