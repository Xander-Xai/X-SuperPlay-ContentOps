# 发布脚本用法

脚本路径：**`skills/gzh-draft-publisher/scripts/publish.py`**（在**仓库根**执行）。

- **微信凭证**来自仓库外层项目目录的 **`aws.env`**：当前单账号固定使用 `WECHAT_1_APPID`、`WECHAT_1_APPSECRET`、可选 `WECHAT_1_API_BASE`。也可用全局 `--env <项目外层凭证文件>` 显式指定，优先于 `WECHAT_ENV_PATH`。凭证文件不进入源码仓库。
- **`publish_method`** 在 **`config.yaml`**：**`draft`**（默认）= **`full`** 只进**草稿箱**；**`published`** 也先创建草稿，必须完成回读和外部 `external_publish` 审批后，再单独提交；**`none`** = **`full`** **不调接口**。`full --publish` 只兼容旧参数，创建草稿后会安全阻断，不会直接公开发布。

## `publish_method` 检查

```bash
python skills/gzh-draft-publisher/scripts/publish.py check-screening
python skills/gzh-draft-publisher/scripts/publish.py check-screening --config .aws-article/config.yaml
```

## 微信槽位检查

```bash
python skills/gzh-draft-publisher/scripts/publish.py check-wechat-env
python skills/gzh-draft-publisher/scripts/publish.py accounts
```

## 一键全流程

```bash
python skills/gzh-draft-publisher/scripts/publish.py full path/to/article-dir/

python skills/gzh-draft-publisher/scripts/publish.py full path/to/article-dir/ --publish  # 创建草稿后安全阻断，需走审批

python skills/gzh-draft-publisher/scripts/publish.py --account 2 full path/to/article-dir/

python skills/gzh-draft-publisher/scripts/publish.py --env D:/Projects/gzh_x未来智能/aws.env full path/to/article-dir/
```

## 正式文章读取（`getdraft.py`）

与 **`publish.py` 独立**，用于 **`freepublish/batchget`** / **`freepublish/get`** / **`freepublish/getarticle`**（仓库根执行）：

```bash
python skills/gzh-draft-publisher/scripts/getdraft.py published-fields
python skills/gzh-draft-publisher/scripts/getdraft.py publish-get <publish_id>
python skills/gzh-draft-publisher/scripts/getdraft.py article-get <article_id>
```

## 分步操作

```bash
python skills/gzh-draft-publisher/scripts/publish.py token
python skills/gzh-draft-publisher/scripts/publish.py upload-thumb cover.jpg --article <外部active/THK-...>
python skills/gzh-draft-publisher/scripts/publish.py upload-content-image imgs/img.png --article <外部active/THK-...>
python skills/gzh-draft-publisher/scripts/publish.py create-draft path/to/article.yaml
python scripts/verify_draft_submission.py --article <外部active/THK-...> --media-id <media_id> --env D:/secrets/wechat.env
# 在独立环境记录 external_publish 审批并配置外部签名后：
python skills/gzh-draft-publisher/scripts/publish.py publish <media_id> --article <外部active/THK-...>
```
