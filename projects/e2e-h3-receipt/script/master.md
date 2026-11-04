# e2e-h3-receipt — 脚本文本

由 `script/script.json` 生成；每条事实声明在 `script/claims.json` 中绑定到来源引文。

| # | 旁白 | 字幕 | 事实来源 | 素材 |
|---|---|---|---|---|
| l1 | H3 走的是官方文档的公开 API v2，不是官方 CLI，也不是旧版 v1 接口。 | 公开 API，不是 CLI | h3_transport | projects/easel-review/sources/screenshots/12-easel-version-evidence.png |
| l2 | 这次请求是 4 秒、768P 的 I2VA 参考图任务，只创建了一次任务。 | 4 秒 / 768P / I2VA | h3_request | projects/easel-review/sources/screenshots/13-easel-skill-layers.png |
| l3 | 提示词仓库没有被 vendored 进来，所以回执只证明这一次调用，不证明能力已经稳定，只记录这一次的输入和输出，并附上回执。 | 不 vendored，只证明这一次 | h3_not_vendored | projects/easel-review/sources/screenshots/14-easel-skills-dir.png |
