# e2e-voice-entitlement — 脚本文本

由 `script/script.json` 生成；每条事实声明在 `script/claims.json` 中绑定到来源引文。

| # | 旁白 | 字幕 | 事实来源 | 素材 |
|---|---|---|---|---|
| l1 | 这次 voice clone 请求只发了一次，被 2061 拒绝，没有自动重试。 | 一次请求，2061 拒绝 | voice_refused | projects/easel-review/sources/screenshots/12-easel-version-evidence.png |
| l2 | 2061 是套餐覆盖问题，不是权限或验证问题，也不是账号被封。 | 套餐覆盖，不是权限 | plan_coverage | projects/easel-review/sources/screenshots/13-easel-skill-layers.png |
| l3 | 当前没有权利清晰的人声样本，所以没有自动重试，也没有把原始 voice_id 写进回执，后续要重新走一次人工授权，并附上回执。 | 没有清权样本，不重试 | no_rights_sample | projects/easel-review/sources/screenshots/14-easel-skills-dir.png |
