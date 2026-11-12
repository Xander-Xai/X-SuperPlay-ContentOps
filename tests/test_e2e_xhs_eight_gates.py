"""End-to-end acceptance of the XHS eight-gate pre-publication pipeline.

Why this file exists
--------------------
The eight gates were only ever exercised by hand: a 468-line one-off script ran
a real bundle through ``pipeline_gate.py`` and left 60-odd log files behind, but
nothing in ``tests/`` proved that a bundle can still reach step 8 or that an
empty bundle is refused at step 1. Two failures were therefore possible and
invisible — a gate that silently accepts a missing artifact, and a gate that
cannot be advanced at all.

What this proves, and what it does not
--------------------------------------
It proves, with real files on disk and the workflow's own CLIs as the only
implementation:

- an empty bundle is refused at step 1 and recorded as ``blocked``;
- a fully seeded bundle advances all eight steps, and the final state reports
  every step ``passed`` with ``current_step: null``;
- each image receipt is bound to its asset by digest, which step 7 re-checks.

It does not prove anything about a platform. No account is logged in, no draft
box is written, no post is published, and nothing here is a content approval.

Running it
----------
``python tests/test_e2e_xhs_eight_gates.py``

The suite self-skips when the runtime workflow is absent, because
``.runtime/`` is gitignored by design: a clean checkout has no workflow to
drive, and a green run must never be manufactured from nothing. CI therefore
runs this file and reports SKIP on a clean checkout — that is the honest
outcome, not a gap to paper over.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402

WORKFLOW = ROOT / ".runtime" / "workflows" / "xhs_未来智能"
GATE = WORKFLOW / "scripts" / "pipeline_gate.py"
WINDOWS_VENV = ROOT / ".runtime" / "gzh-wf-venv" / "Scripts" / "python.exe"

STEPS = 8
CARDS = 6


def _skip_reason() -> str | None:
    if not WORKFLOW.is_dir():
        return f"runtime workflow absent at {WORKFLOW} (.runtime/ is gitignored)"
    if not GATE.is_file():
        return "pipeline_gate.py absent from the runtime workflow"
    try:
        import PIL  # noqa: F401
    except ImportError:
        return "Pillow absent; the card normalizer needs it"
    return None


SKIP = _skip_reason()


def _interpreters() -> list[Path]:
    """The workflow venv when it exists, this interpreter otherwise."""
    if WINDOWS_VENV.is_file():
        return [WINDOWS_VENV, Path(sys.executable)]
    return [Path(sys.executable)]


def _account() -> str:
    manifest = json.loads(
        (WORKFLOW / "contracts" / "artifact-manifest.json").read_text(encoding="utf-8"))
    return str(manifest["account"])


def _weighted(text: str) -> int:
    return sum(2 if ord(char) > 127 else 1 for char in text)


def _title_candidates(titles: list[str]) -> list[dict]:
    return [
        {"text": title, "weighted_length": _weighted(title), "score": 90 - index * 3}
        for index, title in enumerate(titles)
    ]


@unittest.skipIf(SKIP, SKIP or "")
class EightGateTest(unittest.TestCase):
    """Drive the real gate machine against a temporary bundle."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.bundle = Path(self._tmp.name) / "bundle"
        self.bundle.mkdir(parents=True)
        self.account = _account()
        self.python = next((p for p in _interpreters() if p.is_file()), Path(sys.executable))

    # ------------------------------------------------------------------ helpers

    def _env(self) -> dict:
        env = os.environ.copy()
        # The gate refuses output paths outside production/ unless this is set.
        # A test bundle in a temp directory is exactly that case.
        env["WORKFLOW_TEST_MODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def _run(self, script: str, *args: str) -> tuple[int, str]:
        result = hidden_run(
            [str(self.python), str(WORKFLOW / "scripts" / script), *args],
            cwd=str(WORKFLOW), timeout=180, env=self._env(),
        )
        return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()

    def _gate(self, *args: str) -> tuple[int, str]:
        return self._run("pipeline_gate.py", *args)

    def _write(self, name: str, payload) -> None:
        path = self.bundle / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    def _init(self) -> None:
        code, out = self._gate("init", str(self.bundle), "--force")
        self.assertEqual(code, 0, out)

    def _state(self) -> dict:
        return json.loads((self.bundle / "pipeline-state.json").read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ seeding

    def _seed_through_step_two(self) -> None:
        self._write("handoff.json", {
            "schema_version": 1,
            "handoff_id": "E2E-HANDOFF-0001",
            "opportunity_id": "E2E-OPP-0001",
            "source_urls": ["https://example.com/reference-doc"],
            "user_questions": ["这套门禁究竟拦住了什么", "空产物会被哪一道门拒绝"],
            "sentinel_verdict": "recommend",
            "evidence_status": "verified",
            "next_owner": self.account,
        })
        self._write("evidence.json", [            {
                "claim": "官方文档说明了该机制的适用边界",
                "type": "official",
                "source_url": "https://example.com/reference-doc",
                "checked_at": "2026-11-12",
                "version": "docs-latest",
                "confidence": "high",
                "context": "端到端测试使用的静态证据，不代表任何真实产品结论",
            },
            {
                "claim": "本机确定性脚本输出了可重放的结果文件",
                "type": "tested",
                "source_url": "https://example.com/reference-doc",
                "checked_at": "2026-11-12",
                "version": "local-sim-v1",
                "confidence": "high",
                "context": "确定性脚本，不涉及真实性能测量",
            },
        ])
        self._write("platform-research.json", {
            "status": "verified",
            "queries": ["端到端门禁验收"],
            "checked_at": "2026-11-12",
            "platform": "xiaohongshu",
            "notes": ["平台侧热度未采集：本机没有登录态，不伪造"],
        })

    def _seed_test_run(self) -> None:
        self._write("test-run.md", "\n".join([
            "# 本机测试记录",
            "",
            "- 环境：Windows / 本机解释器",
            "- 命令：确定性验收脚本",
            "- 退出码：0",
            "- 观察结果：门禁按预期拒绝空产物、接受完整产物",
            "",
        ]))

    def _seed_through_step_six(self) -> None:
        self._write("reproduction.md", "\n".join([
            "# 本机复现",
            "",
            "## 环境",
            "- Windows / Python 3.13",
            "",
            "## 安装",
            "- 无需额外依赖",
            "",
            "## 预期输出",
            "- 输出一个含关键字段的 JSON，退出码为 0",
            "",
            "## 实际输出",
            "- 退出码 0，字段齐全",
            "",
            "## 限制",
            "- 这是算法模型，不是真实性能基准，比例不可外推",
            "",
        ]))

        score_dims = ("conflict", "relevance", "evidence", "readability",
                      "interaction", "seriesability")

        def angle(name: str, values: list[int]) -> dict:
            score = dict(zip(score_dims, values))
            score["total"] = sum(values)
            return {
                "name": name,
                "benefit": "让读者能自己复算",
                "tension": "结论容易被外推成性能承诺",
                "evidence": "官方资料 + 本机静态证据",
                "adaptation_reason": "账号定位是证据链，先结果后步骤",
                "risks": "不能把比例说成真实收益",
                "validation": "复现脚本退出码 0 且结果可重放",
                "score": score,
            }

        titles = ["门禁验收清单", "八道门怎么拦", "空产物会被拒", "逐步推进记录",
                  "验收证据链", "端到端跑通"]
        self._write("copywriting-plan.json", {
            "schema_version": 1,
            "skill": "cn-platform-copywriting",
            "platform": "xiaohongshu",
            "account_type": "personal",
            "topic": "八门门禁的端到端验收",
            "audience": "维护这条内容管线的工程师",
            "goal": "证明空产物被拦、完整产物可推进到第八步",
            "claims": [
                {"text": "门禁在产物缺失时拒绝推进", "state": "tested",
                 "validation": "空 bundle 在第一步被拒绝", "source_url": "https://example.com/reference-doc"},
                {"text": "官方文档说明了机制边界", "state": "official",
                 "validation": "核对官方文档", "source_url": "https://example.com/reference-doc"},
                {"text": "比例不可外推成真实性能", "state": "editorial_inference",
                 "validation": "在正文限制段落显式声明边界"},
            ],
            "angle_candidates": [
                angle("先讲失败", [4, 5, 5, 4, 4, 5]),
                angle("按门拆解", [4, 4, 5, 4, 3, 4]),
                angle("证据链视角", [5, 4, 4, 4, 4, 3]),
            ],
            "copy": {
                "title_options": titles[:3],
                "title": titles[0],
                "hook": "一条流水线最容易坏在哪一步？",
                "body": [
                    "空产物在第一步就被拒绝，这是门禁存在的意义。",
                    "完整产物可以一路推进到第八步，每一步都留记录。",
                    "个人判断：先把门禁跑通，再谈内容质量。",
                ],
                "visual": f"{CARDS} 张 1080x1440 卡片",
                "cta": "收藏这份验收清单",
                "comment_question": "你那条流水线卡在第几步？",
            },
            "risks_and_sources": {
                "platform_rules": [{
                    "source_url": "https://example.com/reference-doc",
                    "checked_at": "2026-11-12",
                    "scope": "机制描述",
                    "fact": "官方文档说明了机制",
                    "inference": "门禁应fail-closed",
                    "test": "空 bundle 被拒绝",
                }],
                "fact_checks": ["证据来自静态文件", "复现脚本可重放"],
                "rights_checks": ["图卡由本机脚本绘制", "未使用第三方素材"],
            },
            "test_plan": {
                "variable": "产物完整度",
                "control": "固定产物集合",
                "window": "单次运行",
                "metrics": ["推进步数", "拒绝次数"],
                "failure_conditions": ["空产物被接受", "完整产物无法推进"],
            },
            "series_extensions": ["下一期：发布后复盘", "下一期：跨平台改写"],
        })

        body = (
            "结果先行：一套门禁最容易坏在两处，一是空产物被默默放行，二是完整产物走到一半推不动。"
            "官方资料：门禁应当 fail-closed，缺失即拒绝。"
            "本机验收：空产物在第一步被拒绝并记录为 blocked；完整产物八步全部推进，最终 current_step 为 null。"
            "个人判断：先把门禁跑通，再谈内容质量。"
            "待验证：真实平台侧的发布链路——本验收不涉及任何账号。"
        )
        self._write("draft.json", {
            "account": self.account,
            "handoff_id": "E2E-HANDOFF-0001",
            "idempotency_key": "E2E-IDEMP-0001",
            "platform_research": {"status": "verified"},
            "evidence": json.loads((self.bundle / "evidence.json").read_text(encoding="utf-8")),
            "test_run": {"status": "passed", "exit_code": 0, "observed_output": "policy=ok"},
            "title_candidates": _title_candidates(titles),
            "title": titles[0],
            "body": body,
            "cta": "收藏这份验收清单",
            "humanizer_score": 45,
            "tags": ["工程验收", "内容管线"],
            "visual_brief": {"status": "planned"},
            "verdict": "recommend",
            "evidence_level": "tested",
            "preflight": {"status": "blocked"},
            "publish_mode": "draft",
        })

        self._write("series.json", {
            "schema_version": 1,
            "account": self.account,
            "pages": [
                {"page": index, "message": f"第 {index} 页：门禁验收要点",
                 "source": "pipeline-gate"}
                for index in range(1, CARDS + 1)
            ],
        })
        self._write("visual-brief.md", "\n".join([
            "# 视觉简报",
            "",
            f"- 规格：{CARDS} 张 1080x1440 PNG",
            "- 生成方式：本机 Pillow 绘制原图 → 工作流 normalize_xhs_image.py 规范化并生成 SHA-256 回执",
            "",
        ]))

    def _route_images(self) -> None:
        code, out = self._run("image_generation_router.py", "--bundle", str(self.bundle),
                              "--mode", "codex", "--confirm")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.bundle / "image-generation-route.json").is_file())

    def _draw_and_normalize(self) -> None:
        from PIL import Image, ImageDraw

        cards_dir = self.bundle / "cards"
        raw_dir = self.bundle / "raw" / "codex"
        receipts_dir = self.bundle / "receipts"
        for directory in (cards_dir, raw_dir, receipts_dir):
            directory.mkdir(parents=True, exist_ok=True)

        assets, receipts = [], []
        for index in range(1, CARDS + 1):
            raw = raw_dir / f"e2e-card-{index:02d}-raw.png"
            card = cards_dir / f"e2e-card-{index:02d}-1080x1440.png"
            receipt = receipts_dir / f"image-{index:02d}.json"

            image = Image.new("RGB", (1080, 1440), "#f5f5f5")
            draw = ImageDraw.Draw(image)
            draw.rectangle([0, 0, 1080, 12], fill="#b23a2e")
            draw.text((70, 90), f"门禁验收 {index}/{CARDS}", fill="#1a1a1a")
            draw.text((70, 200), "端到端 suite 生成的验收卡", fill="#555555")
            image.save(raw, format="PNG")

            code, out = self._run("normalize_xhs_image.py", str(raw), str(card),
                                  "--receipt", str(receipt), "--mode", "codex")
            self.assertEqual(code, 0, out)
            assets.append(f"cards/{card.name}")
            receipts.append(f"receipts/{receipt.name}")

        self._write("visual-assets.json", {
            "schema_version": 1,
            "status": "generated",
            "account": self.account,
            "mode": "codex",
            "normalized_size": "1080x1440",
            "assets": assets,
            "receipts": receipts,
        })

    def _seed_preflight(self) -> None:
        self._write("preflight.json", {
            "schema_version": 1,
            "status": "passed",
            "checked_at": "2026-11-12",
            "manual_approval": {"status": "pending"},
            "checks": [
                "handoff / evidence / platform-research 契约校验通过",
                "复现脚本退出码 0，结果可重放",
                f"{CARDS} 张 1080x1440 PNG 真实生成且 SHA-256 回执逐张匹配",
                "文案区分官方资料、本机实测、个人判断、待验证",
                "单一 CTA，无夸大收益或跨账号导流",
            ],
            "publish_mode": "manual_upload_only",
        })

    # ------------------------------------------------------------------ tests

    def test_empty_bundle_is_refused_at_step_one(self):
        self._init()
        code, out = self._gate("check", str(self.bundle), "--step", "1")

        self.assertNotEqual(code, 0, "an empty bundle must not pass step 1")
        self.assertIn("handoff.json", out)

        state = self._state()
        self.assertEqual(state["steps"][0]["status"], "blocked")
        self.assertEqual(state["current_step"], 1)
        self.assertTrue(state["steps"][0]["error"])
        self.assertEqual(
            [record["status"] for record in state["steps"][1:]],
            ["pending"] * (STEPS - 1),
            "a refused step must not advance its successors",
        )

    def test_all_eight_gates_advance_to_completion(self):
        self._init()
        self._seed_through_step_two()
        self._seed_test_run()
        self._seed_through_step_six()
        self._route_images()
        self._draw_and_normalize()
        self._seed_preflight()

        for step in range(1, STEPS + 1):
            if step == STEPS:
                code, out = self._run("publication_package.py", "--bundle", str(self.bundle))
                self.assertEqual(code, 0, f"publication package failed: {out}")

            code, out = self._gate("check", str(self.bundle), "--step", str(step))
            self.assertEqual(code, 0, f"step {step} check failed: {out}")
            self.assertIn(f"PASS: step {step}", out)

            code, out = self._gate("advance", str(self.bundle), "--step", str(step))
            self.assertEqual(code, 0, f"step {step} advance failed: {out}")
            self.assertIn(f"ADVANCED: step {step}", out)

        state = self._state()
        self.assertIsNone(state["current_step"], "a finished pipeline has no current step")
        self.assertEqual(
            [record["status"] for record in state["steps"]],
            ["passed"] * STEPS,
        )
        self.assertEqual(
            [event["event"] for event in state["history"]].count("passed"), STEPS)

    def test_a_tampered_card_blocks_step_seven(self):
        self._init()
        self._seed_through_step_two()
        self._seed_test_run()
        self._seed_through_step_six()
        self._route_images()
        self._draw_and_normalize()

        # Step 7 re-derives every digest; a card that changed on disk is a
        # different card, so the receipt no longer describes it.
        assets = json.loads((self.bundle / "visual-assets.json").read_text(encoding="utf-8"))
        victim = self.bundle / assets["assets"][0]
        victim.write_bytes(victim.read_bytes() + b"\x00")

        for step in range(1, 7):
            code, out = self._gate("advance", str(self.bundle), "--step", str(step))
            self.assertEqual(code, 0, f"step {step} advance failed: {out}")

        code, out = self._gate("check", str(self.bundle), "--step", str(STEPS - 1))
        self.assertNotEqual(code, 0, "a tampered card must not pass the visual-asset gate")
        self.assertIn("sha256", out.lower())
        self.assertEqual(self._state()["steps"][STEPS - 2]["status"], "blocked")


if __name__ == "__main__":
    unittest.main(verbosity=2)
