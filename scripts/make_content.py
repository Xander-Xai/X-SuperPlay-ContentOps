#!/usr/bin/env python3
"""The single stable entry point for content production.

Every conditional capability in this repository (account DNA, voice clone,
digital-human bookends, Huashu motion, evidence-bound copy, copy review) is
already implemented, but each one fires only when the operator remembers the
right flag or ``project.yaml`` block. This CLI makes the six decisions explicit,
records them, writes the load-bearing ``account_slug`` block, and refuses to
invoke a producer until every gate passes.

    python scripts/make_content.py answer --project projects/my-video --interactive
    python scripts/make_content.py check --project projects/my-video
    python scripts/make_content.py run   --project projects/my-video --mode STRICT

Directly running ``produce_video.py`` or ``m5_production.py`` remains a
diagnostic path; it is not gate-checked. Use this entry for real production.

Exit codes: 0 ok, 2 usage, 4 blocked by a gate or the producer, 1 unexpected.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import production_gates as gates  # noqa: E402

BLOCKED_EXIT = 4
RUN_RECEIPT = Path("receipts") / "make-content.json"


def _project(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    if not resolved.is_dir():
        raise gates.GateError("PROJECT_MISSING", f"project directory not found: {resolved}")
    return resolved


def _ask(prompt: str, choices, default: str = "") -> str:
    suffix = "/".join(choices)
    hint = f" [{default}]" if default else ""
    if not sys.stdin.isatty():
        if not default:
            raise gates.GateError("NON_INTERACTIVE_GATE",
                                  f"no TTY to ask {prompt!r}; pass the flag explicitly")
        return default
    answer = input(f"{prompt} ({suffix}){hint}: ").strip().casefold()
    return answer or default


def _answers_from_args(args, project: Path) -> Dict[str, Any]:
    interactive = bool(args.interactive)
    account = args.account or (_ask("为哪个账号制作内容",
                                    ("explorer", "thinktank"), "") if interactive else "")
    policy = args.asset_policy or (_ask(
        "本次素材不足，是否采用 MiniMax 生成额外图片/视频？"
        "（supplement=补采证据 / local-free=本地免费素材 / minimax-authorized=授权生成）",
        gates.ASSET_POLICIES, "supplement") if interactive else "")
    intro = args.avatar_intro or (_ask("是否加入数字人片头", gates.YES_NO, "no")
                                  if interactive else "")
    outro = args.avatar_outro or (_ask("是否加入数字人片尾", gates.YES_NO, "no")
                                  if interactive else "")
    narration = args.narration or (_ask("旁白音色", gates.NARRATION_CHOICES,
                                        "minimax-clone") if interactive else "")
    motion = args.motion or (_ask("动效后端", gates.MOTION_CHOICES,
                                  "huashu-art-motion") if interactive else "")
    bgm = args.bgm or (_ask("是否加入本地 BGM（需 media-use runtime lock）",
                            gates.BGM_POLICIES, "none") if interactive else "none")
    reviewer = args.reviewer or (_ask("本次 gate 由谁确认（具名）", (), "")
                                 if interactive else "")
    opinion = args.opinion or (_ask("确认理由（书面）", (), "") if interactive else "")
    quota = args.avatar_quota_budget
    if not quota and (intro == "yes" or outro == "yes"):
        quota = _ask("H3 配额预算（每片 7pp，两片 14pp）", (), "14") if interactive else ""
    return {
        "account": account, "asset_policy": policy,
        "avatar_intro": intro, "avatar_outro": outro,
        "avatar_quota_budget": quota or None,
        "narration": narration, "motion_backend": motion,
        "bgm_policy": bgm,
        "reviewer": reviewer, "opinion": opinion,
    }


def cmd_answer(args) -> int:
    project = _project(args.project)
    answers = _answers_from_args(args, project)
    intent = gates.write_intent(
        project,
        account=answers["account"],
        asset_policy=answers["asset_policy"],
        avatar_intro=answers["avatar_intro"],
        avatar_outro=answers["avatar_outro"],
        avatar_quota_budget=answers["avatar_quota_budget"],
        narration=answers["narration"],
        motion_backend=answers["motion_backend"],
        reviewer=answers["reviewer"],
        opinion=answers["opinion"],
        bgm_policy=answers["bgm_policy"],
        root=ROOT,
    )
    config = gates.apply_project_config(project, intent)
    # Materialise the two derived contracts a human should not have to hand-write:
    # the evidence pack (what the copy cites) and source-refs (what motion needs).
    inputs = gates.ensure_inputs(project, ROOT)
    payload = {"state": "INTENT_RECORDED", "project": project.name,
               "intent": str(gates.INTENT_FILE), "config": config, "inputs": inputs,
               "production_ready": False, "publish_authorized": False,
               "note": "Copy review is signed separately with scripts/copy_review.py --approve."}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_check(args) -> int:
    project = _project(args.project)
    report = gates.check(project, root=ROOT)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else BLOCKED_EXIT


def cmd_status(args) -> int:
    project = _project(args.project)
    intent = gates.load_intent(project)
    report = gates.check(project, root=ROOT, intent=intent)
    print(json.dumps({"intent": intent, "check": report}, ensure_ascii=False, indent=2))
    return 0


def _render_article(project: Path, html: Path) -> str:
    """Validate the WeChat article through the pinned runtime; never publishes."""
    import os

    from contentops.graphic.articles import (ArticleError, plan, run,
                                             write_receipt)
    from process_utils import hidden_run

    def runner(argv, *, timeout: int = 120):
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return hidden_run(argv, timeout=timeout, check=False, env=env)

    try:
        p = plan(project, html_path=html, runtime_root=ROOT / ".runtime" / "easel")
        receipt = run(p, runner=runner, article_python=sys.executable)
        write_receipt(receipt, project)
        return str(receipt.get("status"))
    except ArticleError as exc:
        return f"BLOCKED: {exc}"


def _produce_graphic(project: Path, intent: Dict[str, Any]) -> Dict[str, Any]:
    """The gated producer for a GRAPHIC_TEXT project.

    Calling produce_video here (the 2026-11-12 acceptance bug) blocked the run
    at M5's brief gate even though all five graphic gates were green.
    """
    handoff = project / "receipts" / "bundle-handoff-graphic_text.json"
    if not handoff.is_file():
        raise gates.GateError(
            "HANDOFF_MISSING",
            "no receipts/bundle-handoff-graphic_text.json; create it with "
            "scripts/bundle_handoff.py ... --format GRAPHIC_TEXT first")
    from contentops.graphic import (GraphicPackageError, build_package,
                                    write_package)

    try:
        package = build_package(project, handoff,
                                project / "graphic-input.json", ROOT, ROOT,
                                bundle_root=ROOT)
        write_package(project, package, ROOT)
    except GraphicPackageError as exc:
        raise gates.GateError("GRAPHIC_PACKAGE_BLOCKED", f"{exc.code}: {exc.detail}")

    result: Dict[str, Any] = {"state": package.get("status"),
                              "package": "receipts/graphic-package.json"}
    article = project / "assets" / "article" / "article-gzh.html"
    if article.is_file():
        result["article"] = _render_article(project, article)
    return result


def cmd_run(args) -> int:
    project = _project(args.project)
    try:
        gates.ensure_inputs(project, ROOT)
        report = gates.require(project, root=ROOT)
        intent = gates.load_intent(project)
        if args.dry_run:
            print(json.dumps({"state": "PREFLIGHT_PASS_DRY_RUN", "check": report},
                             ensure_ascii=False, indent=2))
            return 0
        if gates._is_graphic_line(project):
            result = _produce_graphic(project, intent)
        else:
            import produce_video

            kwargs: Dict[str, Any] = {"mode": args.mode.upper()}
            if intent["narration"] == "minimax-clone":
                kwargs["narration_provider"] = "minimax"
                kwargs["narration_voice"] = "founder_primary_v1"
            else:
                kwargs["narration_provider"] = "sapi"
            if intent["avatar_intro"] == "yes" or intent["avatar_outro"] == "yes":
                kwargs["avatar_provider"] = "minimax-h3"
                kwargs["avatar_quota_budget"] = intent.get("avatar_quota_budget")
                kwargs["avatar_generation_choice"] = "ask"
            result = produce_video.produce(project, **kwargs)
    except gates.GateError as exc:
        print(json.dumps({"state": "BLOCKED", "code": exc.code,
                          "reason": exc.detail,
                          "check": exc.report}, ensure_ascii=False, indent=2))
        return BLOCKED_EXIT
    except Exception as exc:
        # M5Blocked and DirtyCheckoutError both mean "stop, do not degrade".
        print(json.dumps({"state": "BLOCKED", "failure_type": type(exc).__name__,
                          "reason": str(exc)[:1000]}, ensure_ascii=False, indent=2))
        return BLOCKED_EXIT

    receipt = {
        "schema": "contentops.make-content-run/v1",
        "project": project.name,
        "mode": args.mode.upper(),
        "intent_sha256": report.get("intent_sha256"),
        "gates": report["gates"],
        "producer_state": result.get("state"),
        "article": result.get("article"),
        "human_review": result.get("human_review", "PENDING_FOUNDER_REVIEW"),
        "production_ready": False,
        "publish_authorized": False,
        "note": "Producer completion is not publication or founder approval.",
    }
    gates._write_json(project / RUN_RECEIPT, receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if result.get("state") == "QC_PASSED" else 1


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--project", required=True)

    answer = sub.add_parser("answer", help="record the six human gate decisions")
    common(answer)
    answer.add_argument("--interactive", action="store_true",
                        help="ask each gate on the terminal")
    answer.add_argument("--account", help="explorer | thinktank | DNA slug")
    answer.add_argument("--asset-policy", choices=gates.ASSET_POLICIES)
    answer.add_argument("--avatar-intro", choices=gates.YES_NO)
    answer.add_argument("--avatar-outro", choices=gates.YES_NO)
    answer.add_argument("--avatar-quota-budget")
    answer.add_argument("--narration", choices=gates.NARRATION_CHOICES)
    answer.add_argument("--motion", choices=gates.MOTION_CHOICES)
    answer.add_argument("--bgm", choices=gates.BGM_POLICIES)
    answer.add_argument("--reviewer", help="named person answering the gates")
    answer.add_argument("--opinion", help="written rationale")
    answer.set_defaults(func=cmd_answer)

    check = sub.add_parser("check", help="verify all six gates")
    common(check)
    check.set_defaults(func=cmd_check)

    status = sub.add_parser("status", help="show intent and gate state")
    common(status)
    status.set_defaults(func=cmd_status)

    run = sub.add_parser("run", help="check gates, then produce")
    common(run)
    run.add_argument("--mode", default="STRICT", choices=("AUTO", "REVIEW", "STRICT"))
    run.add_argument("--dry-run", action="store_true", help="check only, do not produce")
    run.set_defaults(func=cmd_run)
    return parser


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # The repository has no dotenv dependency, but it does have this loader:
    # it injects .env values into os.environ, returns names only, never
    # overrides an existing variable and refuses a Git-tracked file.
    from contentops.media.credentials import load_local_env_file

    load_local_env_file(ROOT / ".env")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except gates.GateError as exc:
        print(json.dumps({"state": "BLOCKED", "code": exc.code, "reason": exc.detail},
                         ensure_ascii=False, indent=2))
        return BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
