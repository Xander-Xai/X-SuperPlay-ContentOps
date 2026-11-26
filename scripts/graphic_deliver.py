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
    python scripts/graphic_deliver.py --platforms csdn --confirm-draft-write
    python scripts/graphic_deliver.py --all --confirm-draft-write

Creating platform drafts is an external write. The command requires current signed
quality approval, an unchanged package and the explicit confirmation flag. It never
publishes; ambiguous CLI results are recorded as unknown and are not retried.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.graphic import (  # noqa: E402
    GraphicPackageError,
    verify_graphic_review,
    verify_package_current,
)
from contentops.platforms import delivery_gate  # noqa: E402
from contentops.platforms import graphic_specs  # noqa: E402
from contentops.platforms import multichannel as mc  # noqa: E402
from contentops.platforms.wcs_bridge import OUT_DIR, TOKEN_FILE, bridge_session, parse_sync_result, run_cli  # noqa: E402


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bridge_adapter(platform_id: str) -> str:
    for ch in graphic_specs.channels(platform_id):
        if ch["kind"] == "browser_bridge":
            return str(ch["id"]).split(":", 1)[1]
    return ""


def _cover_candidate(image: dict, project_root: Path) -> Path:
    """Resolve a package image only if it remains within its declared root."""
    ref = str(image.get("path") or "").replace("\\", "/")
    declared_scope = str(image.get("scope") or "")
    if ref.startswith("repo://"):
        base = ROOT.resolve()
        ref = ref[len("repo://"):]
        expected_scope = "repo"
    elif ref.startswith("project://"):
        base = project_root.resolve()
        ref = ref[len("project://"):]
        expected_scope = "project"
    else:
        base = project_root.resolve()
        expected_scope = "project"

    relative = Path(ref)
    if (not ref or relative.is_absolute() or ".." in relative.parts
            or (declared_scope and declared_scope != expected_scope)):
        raise GraphicPackageError("COVER_PATH_INVALID",
                                  "cover path or declared scope is not a safe package-relative reference")
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        raise GraphicPackageError("COVER_PATH_INVALID",
                                  "cover path resolves outside its declared root") from None
    return candidate


def _verify_cover_image(image: dict, cover: Path, project_root: Path) -> None:
    """Recheck scope and bytes for the cover selected from the reviewed package."""
    candidate = _cover_candidate(image, project_root)
    if candidate != cover.resolve() or not candidate.is_file():
        raise GraphicPackageError("COVER_ASSET_CHANGED",
                                  "cover path changed after package verification")
    expected = str(image.get("sha256") or "")
    try:
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    except OSError:
        raise GraphicPackageError("COVER_ASSET_CHANGED",
                                  "cover became unreadable after package verification") from None
    if not expected or actual != expected:
        raise GraphicPackageError("COVER_ASSET_CHANGED",
                                  "cover bytes no longer match the reviewed package digest")


def _resolve_cover(package: dict, project_root: Path) -> Path | None:
    for image in package.get("images") or []:
        ref = str(image.get("path") or "")
        if Path(ref.replace("\\", "/").removeprefix("repo://").removeprefix("project://")).suffix.lower() not in (
                ".png", ".jpg", ".jpeg", ".webp"):
            continue
        candidate = _cover_candidate(image, project_root)
        if not candidate.is_file():
            continue
        _verify_cover_image(image, candidate, project_root)
        return candidate
    return None


def _verify_cover_current(package: dict, cover: Path, project_root: Path) -> None:
    """Revalidate the exact package image immediately before external CLI use."""
    for image in package.get("images") or []:
        ref = str(image.get("path") or "")
        if Path(ref.replace("\\", "/").removeprefix("repo://").removeprefix("project://")).suffix.lower() not in (
                ".png", ".jpg", ".jpeg", ".webp"):
            continue
        candidate = _cover_candidate(image, project_root)
        if candidate == cover.resolve():
            _verify_cover_image(image, cover, project_root)
            return
    raise GraphicPackageError("COVER_ASSET_CHANGED",
                              "selected cover is no longer a package image")


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
    parser.add_argument("--package", required=True,
                        help="已审核图文包的 receipts/graphic-package.json 路径")
    parser.add_argument("--platforms", default="",
                        help="逗号分隔；默认全部图文平台（或 --all）")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--confirm-draft-write", action="store_true",
                        help="明确授权为已审核的合格包创建平台草稿；不会发布")
    parser.add_argument("--output", default=str(ROOT / ".runtime" / "graphic-deliver.json"))
    parser.add_argument("--timeout", default="60000", help="每平台 CLI 超时（毫秒）")
    parser.add_argument("--login-hold", type=int, default=0,
                        help="投递结束后保持浏览器 N 秒，方便人工登录后再复跑")
    parser.add_argument("--attach", action="store_true",
                        help="不启动浏览器，直接复用已运行窗口里的桥接（登录窗口开着时用）")
    parser.add_argument("--no-cover", action="store_true", help="完全不传封面")
    args = parser.parse_args()

    if not args.platforms and not args.all:
        print(json.dumps({"status": "blocked", "reason": "PLATFORM_SELECTION_REQUIRED",
                          "next_action": "用 --platforms 明确选择目标，或显式传 --all"},
                         ensure_ascii=False, indent=2))
        return 4

    package_file = Path(args.package).expanduser().resolve()
    if not package_file.is_file():
        print(json.dumps({"status": "blocked", "reason": f"PACKAGE_NOT_FOUND: {package_file.name}"},
                         ensure_ascii=False, indent=2))
        return 1
    package = json.loads(package_file.read_text(encoding="utf-8"))
    # Package paths are relative to the project directory, not its receipts directory.
    project_root = package_file.parent.parent.resolve()
    package["_package_root"] = str(project_root)
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

    try:
        verify_package_current(package, project_root, ROOT)
        review = verify_graphic_review(project_root, package)
        cover = _resolve_cover(package, project_root)
    except GraphicPackageError as exc:
        print(json.dumps({"status": "blocked", "reason": exc.code, "detail": exc.detail,
                          "network_called": False, "published": False},
                         ensure_ascii=False, indent=2))
        return 1

    # Offline pass first: package integrity, human review, platform shaping and every
    # validation result are authoritative before a browser bridge is started.
    drafts = {}
    ready_ids = []
    refused = []
    for draft, validation, receipt in mc.build_all(package, account, ids):
        draft_blockers = list(draft.blockers)
        if graphic_specs.rules(draft.platform_id)["needs_cover"] and (cover is None or args.no_cover):
            draft_blockers.append("COVER_REQUIRED: no verified cover will be sent")
        gate = delivery_gate.authorize_adapted_draft(
            draft.platform_id,
            package_blockers=package.get("blockers") or [],
            draft_blockers=draft_blockers,
            validation_errors=validation.errors,
            publish_authorized_claim=bool(package.get("publish_authorized")),
            mode="draft",
            channel_id=f"wechatsync:{_bridge_adapter(draft.platform_id)}" if _bridge_adapter(draft.platform_id) else "",
        )
        drafts[draft.platform_id] = (draft, validation, receipt, gate)
        if gate.allowed:
            ready_ids.append(draft.platform_id)
        else:
            refused.append({"platform_id": draft.platform_id, "status": "refused_by_gate",
                            "gate": gate.to_dict(), "ok": False})

    if not ready_ids:
        print(json.dumps({"status": "blocked", "reason": "NO_DRAFT_TARGET_PASSED_PREFLIGHT",
                          "reviewer": review["reviewer"], "results": refused,
                          "network_called": False, "published": False},
                         ensure_ascii=False, indent=2))
        return 1
    if not args.confirm_draft_write:
        print(json.dumps({"status": "awaiting_user_authorization",
                          "reason": "DRAFT_WRITE_CONFIRMATION_REQUIRED",
                          "eligible_platforms": ready_ids,
                          "reviewer": review["reviewer"],
                          "network_called": False, "published": False},
                         ensure_ascii=False, indent=2))
        return 4
    ids = ready_ids
    print(f"COVER {cover.name if cover else 'none'}", flush=True)

    results: list[dict] = list(refused)
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
                draft, validation, _receipt, gate = drafts[pid]
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
                    "validation_errors": list(validation.errors),
                    "warnings": list(draft.warnings),
                }
                if not adapter:
                    entry.update({"status": "no_bridge_channel", "ok": False,
                                  "reason": "该平台没有 wechatsync 桥接适配器"})
                    results.append(entry)
                    print(f"[SKIP] {pid}: no bridge channel", flush=True)
                    continue

                entry["gate"] = gate.to_dict()

                article = _prepare_article(draft, OUT_DIR)
                argv = ["sync", str(article.resolve()), "-p", adapter,
                        "--title", draft.title or draft.title_hint]
                if cover and not args.no_cover:
                    argv += ["--cover", str(cover.resolve())]

                if cover and not args.no_cover:
                    try:
                        _verify_cover_current(package, cover, project_root)
                    except GraphicPackageError as exc:
                        entry.update({"status": "refused_by_gate", "ok": False,
                                      "reason": exc.code, "detail": exc.detail,
                                      "cover_sent": False})
                        results.append(entry)
                        print(f"[FAIL] {pid}: {exc.code}", flush=True)
                        continue

                out = run_cli(argv, timeout_ms=int(args.timeout), token=token)
                parsed = parse_sync_result(out["stdout"])
                entry.update({
                    "status": "draft_created" if parsed["ok"] and parsed["url"] else "unknown",
                    "ok": bool(parsed["ok"] and parsed["url"]),
                    "url": parsed["url"],
                    "cli_summary": parsed["summary"],
                    "reason": (parsed["reason"] if parsed["ok"] and parsed["url"]
                               else "SYNC_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY"),
                    "bridge_connected": out["bridge_connected"],
                    "cover_sent": bool(cover) and not args.no_cover,
                    "retried_once": False,
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
