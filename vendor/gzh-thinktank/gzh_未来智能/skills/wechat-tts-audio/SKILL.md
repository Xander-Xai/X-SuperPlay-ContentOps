---
name: wechat-tts-audio
display_name: "微信公众号文章语音朗读生成器"
display_name_en: "WeChat Article TTS Audio Generator"
description: "将微信公众号文章 Markdown 正文转化为高清自然语音（MP3 格式），并生成微信顶部带播放样式的 HTML 挂载区块。适用于为公众号文章增加语音朗读功能（听文章）。触发词：公众号朗读、生成语音、TTS朗读、听文章。"
category: audio-creation
version: 1.0.0
author: WeChat Matrix Team
visibility: "public"
---

# 微信公众号文章语音朗读生成器 (wechat-tts-audio)

本 Skill 用于将公众号 Markdown 正文自动提取纯文本，调用高品质神经语音模型生成 MP3 音频文件，并生成微信公众号兼容的音频卡片 HTML。

---

## 🛠️ 使用方法

运行语音生成脚本：

```bash
python skills/wechat-tts-audio/scripts/generate_tts.py article.md --voice zh-CN-YunxiNeural --output article_audio.mp3 --optional
```

---

## 📋 输出组件结构

脚本成功时会输出音频文件、`audio-card.html` 和 `tts-report.json`。音频是公众号图文的可选附件；推荐使用 `--optional`，这样网络或供应商失败时会留下 `status: degraded` 回执，不会阻断图文草稿，也不得宣称音频已生成。

成功时可使用以下 HTML 卡片：

```html
<section style="margin: 15px 0; padding: 12px 16px; background-color: #f7f9fa; border-radius: 8px; border: 1px solid #e1e4e8; display: flex; align-items: center; justify-content: space-between; font-family: -apple-system, BlinkMacSystemFont, sans-serif;">
  <div style="display: flex; align-items: center; gap: 10px;">
    <span style="font-size: 20px;">🎧</span>
    <div>
      <div style="font-size: 14px; font-weight: bold; color: #1a202c;"><span leaf="">语音朗读本篇内容</span></div>
      <div style="font-size: 12px; color: #718096;"><span leaf="">点击播放按键听完整音轨 (时长约 3 分钟)</span></div>
    </div>
  </div>
</section>
```
