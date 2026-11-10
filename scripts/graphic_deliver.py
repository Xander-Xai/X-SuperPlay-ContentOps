#!/usr/bin/env python3
"""Deliver one reviewed graphic package to every platform, through one bridge.

This is the runner that finally closes the loop the whole line was missing:

    pack (offline)  ->  boot bridge once  ->  sync per platform  ->  receipts

Why one process: the browser must stay alive for the entire batch. Spawning the
CLI seven times from seven shells cannot work, because each spawn finds no bridge
and reports ``EXTENSION_NOT_CONNECTED`` even when the extension is installed.

Honesty rules baked in here
---------------------------
* A platform counts as delivered only when the CLI printed ``✓`` for it **and** a
  URL came back. Everything else is recorded as failed with the CLI's own words.
* ``wechatsync auth`` is *not* trusted as the source of truth. The first real run
  showed ``auth`` claiming WeChat was logged in while the actual sync returned
  "登录态超时，请重新登录". Only a real sync decides.
* Nothing is published. Every call is a platform **draft**.

Usage
-----
    python scripts/graphic_deliver.py --platforms zhihu,csdn
    python scripts/graphic_deliver.py --all
    python scripts/graphic_deliver.py --all --login-hold 600   # 顺便留窗口给人工登录
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.platforms import delivery_gate  # noqa: E402
from contentops.platforms import graphic_specs  # noqa: E402
from contentops.platforms import multichannel as mc  # noqa: E402
from contentops.platforms.wcs_bridge import OUT_DIR, TOKEN_FILE, bridge_session, parse_sync_result, run_cli  # noqa: E402

DEFAULT_PACKAGE = ROOT / "projects" / "bundle-dual-line-graphic" / "receipts" / "graphic-package.json"


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bridge_adapter(platform_id: str) -> str:
    for ch in graphic_specs.channels(platform_id):
        if ch["kind"] == "browser_bridge":
            return str(ch["id"]).split(":", 1)[1]
    return ""


def _resolve_cover(package: dict) -> Path | None:
    for image in package.get("images") or []:
        ref = str(image.get("path") or "")
        for prefix in ("repo://", "project://"):
            if ref.startswith(prefix):
                candidate = ROOT / ref[len(prefix):]
                if candidate.is_file():
                    return candidate
    return None


def _prepare_article(draft, work_dir: Path) -> Path:
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"{draft.platform_id}.md"
    title = draft.title or draft.title_hint
    if draft.title:
        path.write_text(f"# {draft.title}\n\n{draft.body}", encoding="utf-8")
    else:
        path.write_text(draft.body, encoding="utf-8")
    return path


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] in {"login", "bridge"}:
        command = sys.argv.pop(1)
        if command == "login":
            from contentops.platforms.wcs_login import main as login_main
            return login_main()
        from contentops.platforms.wcs_bridge_run import main as bridge_main
        return bridge_main()

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--package", default=str(DEFAULT_PACKAGE))
    parser.add_argument("--platforms", default="",
                        help="逗号分隔；默认全部图文平台（或 --all）")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output", default=str(ROOT / ".runtime" / "graphic-deliver.json"))
    parser.add_argument("--timeout", default="60000", help="每平台 CLI 超时（毫秒）")
    parser.add_argument("--login-hold", type=int, default=0,
                        help="投递结束后保持浏览器 N 秒，方便人工登录后再复跑")
    parser.add_argument("--attach", action="store_true",
                        help="不启动浏览器，直接复用已运行窗口里的桥接（登录窗口开着时用）")
    parser.add_argument("--no-cover", action="store_true", help="完全不传封面")
    args = parser.parse_args()

    package_file = Path(args.package).expanduser().resolve()
    if not package_file.is_file():
        print(json.dumps({"status": "blocked", "reason": f"PACKAGE_NOT_FOUND: {package_file}"},
                         ensure_ascii=False, indent=2))
        return 1
    package = json.loads(package_file.read_text(encoding="utf-8"))
    # draft.path is relative to the project directory, not to the receipts dir
    # that holds the package file. Same rule as scripts/platform_delivery.py.
    package["_package_root"] = str(package_file.parent.parent)
    account = {"account_slug": str(package.get("account") or "explorer")}

    if args.platforms:
        ids = [p.strip() for p in args.platforms.split(",") if p.strip()]
    else:
        ids = list(mc.delivery_platform_ids())

    unknown = [p for p in ids if p not in mc.delivery_platform_ids()]
    if unknown:
        print(json.dumps({"status": "blocked", "reason": "UNKNOWN_PLATFORM_ID", "unknown": unknown},
                         ensure_ascii=False, indent=2))
        return 1

    # Offline pass first: shape + audit + receipts. A platform that cannot even be
    # packed is not worth a network attempt.
    drafts = {}
    for draft, validation, receipt in mc.build_all(package, account, ids):
        drafts[draft.platform_id] = (draft, validation, receipt)

    blockers = {pid: list(v[0].blockers) for pid, v in drafts.items() if v[0].blockers}
    if blockers:
        # Delivery consumes validation; it does not replace it. A platform with a
        # hard blocker is recorded below as refused_by_gate instead of being sent
        # to the bridge on the theory that the platform might accept it anyway.
        print(f"BLOCKERS present, those platforms will be refused: {blockers}", flush=True)

    cover = _resolve_cover(package)
    print(f"COVER {cover.name if cover else 'none'}", flush=True)

    results: list[dict] = []
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("BLOCKED: Playwright 未安装", file=sys.stderr)
        return 1

    import contextlib as _ctx

    @_ctx.contextmanager
    def _session(pw):
        if args.attach:
            cached = TOKEN_FILE.read_text(encoding="utf-8").strip() if TOKEN_FILE.is_file() else ""
            print("ATTACH: 复用已运行窗口的桥接，不启动新浏览器", flush=True)
            yield {"token": cached, "ext_id": "", "context": None}
        else:
            with bridge_session(pw) as session:
                yield session

    with sync_playwright() as pw:
        with _session(pw) as session:
            token = session["token"]
            for pid in ids:
                draft, _validation, _receipt = drafts[pid]
                adapter = _bridge_adapter(pid)
                entry: dict = {
                    "platform_id": pid,
                    "bridge_adapter": adapter,
                    "registry_row": draft.registry_row,
                    "native_format": draft.native_format,
                    "body_len_weighted": graphic_specs.weighted_len(draft.body, pid),
                    "suggested_tags": list(draft.suggested_tags),
                    "digest_len": len(draft.digest),
                    "blockers": list(draft.blockers),
                    "warnings": list(draft.warnings),
                }
                if not adapter:
                    entry.update({"status": "no_bridge_channel", "ok": False,
                                  "reason": "该平台没有 wechatsync 桥接适配器"})
                    results.append(entry)
                    print(f"[SKIP] {pid}: no bridge channel", flush=True)
                    continue

                gate = delivery_gate.authorize_delivery(
                    pid,
                    blockers=entry["blockers"],
                    publish_authorized_claim=bool(package.get("publish_authorized")),
                    mode="draft",
                )
                entry["gate"] = gate.to_dict()
                if not gate.allowed:
                    entry.update({"status": "refused_by_gate", "ok": False,
                                  "reason": "; ".join(gate.reasons)})
                    results.append(entry)
                    print(f"[GATE] {pid}: {entry['reason']}", flush=True)
                    continue

                article = _prepare_article(draft, OUT_DIR)
                argv = ["sync", str(article.resolve()), "-p", adapter,
                        "--title", draft.title or draft.title_hint]
                if cover and not args.no_cover:
                    argv += ["--cover", str(cover.resolve())]

                out = run_cli(argv, timeout_ms=int(args.timeout), token=token)
                parsed = parse_sync_result(out["stdout"])
                retried = False
                if not parsed["ok"]:
                    # Retry the *same* command once. Measured 2026-11-09: CSDN
                    # answered "请登录后操作！" on the first attempt right after a
                    # manual login, then the identical command with the same
                    # cover succeeded seconds later. That is session propagation,
                    # not a cover problem — an earlier version of this code
                    # wrongly dropped --cover on retry, which would have shipped
                    # articles without their cover and blamed the wrong thing.
                    time.sleep(2)
                    out = run_cli(argv, timeout_ms=int(args.timeout), token=token)
                    parsed = parse_sync_result(out["stdout"])
                    retried = True
                entry.update({
                    "status": "draft_created" if parsed["ok"] and parsed["url"] else "failed",
                    "ok": bool(parsed["ok"] and parsed["url"]),
                    "url": parsed["url"],
                    "cli_summary": parsed["summary"],
                    "reason": parsed["reason"],
                    "bridge_connected": out["bridge_connected"],
                    "cover_sent": bool(cover) and not args.no_cover,
                    "retried_once": retried,
                    "cli_returncode": out["returncode"],
                    "stdout_tail": out["stdout"].strip().splitlines()[-6:],
                })
                results.append(entry)
                mark = "OK  " if entry["ok"] else "FAIL"
                print(f"[{mark}] {pid}: {entry['url'] or entry['reason'] or 'no detail'}", flush=True)

            if args.login_hold:
                print(f"HOLDING {args.login_hold}s — 在这个窗口里登录需要的平台，然后复跑", flush=True)
                time.sleep(args.login_hold)

    ok = [r for r in results if r["ok"]]
    payload = {
        "schema": "contentops.graphic-deliver/v1",
        "generated_at": _stamp(),
        "package_id": package.get("bundle_id"),
        "bundle_sha256": package.get("bundle_sha256"),
        "attempted": len(results),
        "delivered": len(ok),
        "failed": len(results) - len(ok),
        "published": False,
        "note": "全部为平台草稿；未执行任何发布动作",
        "results": results,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"attempted": len(results), "delivered": len(ok),
                      "failed": len(results) - len(ok), "output": str(out_path)},
                     ensure_ascii=False, indent=2), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
