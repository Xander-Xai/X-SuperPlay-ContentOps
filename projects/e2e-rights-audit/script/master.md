# e2e-rights-audit — 脚本文本

由 `script/script.json` 生成；每条事实声明在 `script/claims.json` 中绑定到来源引文。

| # | 旁白 | 字幕 | 事实来源 | 素材 |
|---|---|---|---|---|
| l1 | 50 个 GZH Skill 里，有 45 个既没有许可声明，也没有 LICENSE 文件。权利没清之前，不进入生产。 | 45/50 无许可 | gzh_unlicensed | projects/easel-review/sources/screenshots/12-easel-version-evidence.png |
| l2 | 小红书这边先前的判断也说错了：根目录是 Apache-2.0，覆盖 40 个 Skill。 | 先纠正判断 | xhs_correction | projects/easel-review/sources/screenshots/13-easel-skill-layers.png |
| l3 | 公开 receipt 里没有裸 key，但有余额、voice_id 和 fingerprint，所以先轮换、再继续脱敏。 | 暴露的是数据 | no_raw_key | projects/easel-review/sources/screenshots/14-easel-skills-dir.png |
