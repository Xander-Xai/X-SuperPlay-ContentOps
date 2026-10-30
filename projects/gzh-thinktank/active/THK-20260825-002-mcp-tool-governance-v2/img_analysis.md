# 图片质量报告

- 检查时间：2026-08-24T23:09:54.535009+00:00
- 图片文件：6
- HTML 图片引用：5
- 尺寸：cover.png=1880x800, section-01.png=1200x720, section-02.png=1200x720, section-03.png=720x320, section-04.png=1200x720, section-05.png=1200x720
- 正文画布背景：#F4F0E8（封面独立策略）
- 几何拓扑：由 visual_semantic_qa.py 调用 visual_geometry_qa.py；关系图无合同则阻断
- 视觉合同审计：visual-contract-audit.json
- 审美旁路审计：visual-taste-review.json（机器检查与人眼审美分离）
- 重复提示：生成素材 imgs/cover.png 可能含有可读文字/伪造标签（连通域数=47，阈值=45）；Agnes 图应画面无文字，请确认是插画纹理而非鬼画文字

## 结果

- 错误：0
- 警告：1
- 移动端预览：请在 `final_reviewed` 门禁中确认 390px 宽度截图。
