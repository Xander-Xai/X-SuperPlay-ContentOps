# 首次环境引导

公众号主流程只需要两类外部能力：Agnes Image 2.1 Flash 生图，以及用户明确选定的
微信公众号槽位。写稿由当前 Agent 本地完成，不配置或调用外部写作模型。

## 1. 准备公开配置

复制 `config.example.yaml` 到 `.aws-article/config.yaml`，确认：

- `publish_method` 为 `draft`（默认只进草稿箱）；
- `image_model.provider` 为 `agnes`；
- `image_model.base_url` 为 `https://apihub.agnes-ai.com/v1/images/generations`；
- `image_model.model` 为 `agnes-image-2.1-flash`；
- `wechat_publish_slot` 与账号名称指向本次目标账号。

真实凭证放在仓库外的环境文件，不进入 Git：

```env
AGNES_API_KEY=...
WECHAT_1_APPID=...
WECHAT_1_APPSECRET=...
```

本工作流固定发布到第 1 槽位，不支持在文章流程中切换到其他槽位。不要在 profile、文章、日志或审计产物中写入凭证值。

## 2. 环境校验

```powershell
python skills/gzh-article-orchestrator/scripts/validate_env.py `
  --config .aws-article/config.yaml `
  --env D:/path/to/external.env
```

退出码 0 才能继续。脚本严格检查 Agnes 固定端点、模型名、`AGNES_API_KEY` 和所选
微信槽位；`publish_method: none` 只在用户明确不接微信时使用，并会跳过微信校验。

## 3. 初始化与写作

```powershell
python scripts/bootstrap_article_environment.py
python scripts/route_content.py --interactive
python scripts/matrix_init.py --route <GZH_ARTIFACT_ROOT>/registry/routes/<routing>.yaml
python skills/gzh-article-writing/scripts/write.py prompt draft <article>/topic-card.md
```

Agent 依据提示词和研究证据直接写入 `draft.md`，再运行 `record_revision.py` 并推进
`draft_complete`。不得跳过路由、研究或修订登记。

## 4. 发布前检查

```powershell
python scripts/publish_preflight.py --article <article> --env D:/path/to/external.env `
  --approve --draft-permission-confirmed --ip-whitelist-confirmed
```

预检通过后才允许调用 `publish.py full <article> --env ...`。草稿创建后必须执行
`verify_draft_submission.py` 回读；默认不会群发。
