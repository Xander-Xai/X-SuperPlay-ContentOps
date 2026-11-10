#!/usr/bin/env python3
"""Multi-platform graphic delivery runner (offline-first, no fake publication).

Commands
--------
  list       Show registry graphic rows and optional external delivery channels.
  self-test  Run the acceptance tests from docs/PLATFORM-ADAPTER-CONTRACT.md.
  pack       Map a reviewed graphic package into per-platform drafts + receipts.
  dispatch   Hand a packed draft to an external delivery CLI (operator-owned).
  status     Aggregate real platform readiness across all graphic channels.

This runner never edits config/registry/platforms.json, never upgrades a row,
never writes a published_url, and never claims a PUBLISHED state.  External
GPL/AGPL tools live in the gitignored .runtime/ tree and are invoked only via a
process boundary, never imported into the Apache-2.0 source tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.platforms import multichannel as mc  # noqa: E402
from contentops.platforms import graphic_specs  # noqa: E402
from contentops.platforms.registry import validate_registry  # noqa: E402

RUNTIME_TOOLS = ROOT / ".runtime" / "multichannel-tools"
CLI_ENTRY = RUNTIME_TOOLS / "node_modules" / "@wechatsync" / "cli" / "dist" / "index.js"
PLATFORMS_JSON = ROOT / "config" / "registry" / "platforms.json"
DEFAULT_PACKAGE = ROOT / "projects" / "bundle-dual-line-graphic" / "receipts" / "graphic-package.json"


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_package(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise SystemExit(f"PACKAGE_NOT_FOUND: {resolved}")
    doc = json.loads(resolved.read_text(encoding="utf-8"))
    # draft.path is relative to the project directory, not the receipts dir.
    doc["_package_root"] = str(resolved.parent.parent)
    return doc


def _no_network_guard():
    """Block any network attempt during offline adapter tests."""
    def blocked(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("offline adapter must not perform network calls")
    return (
        mock.patch("socket.socket.connect", blocked),
        mock.patch("urllib.request.urlopen", blocked),
    )


def cmd_list(args: argparse.Namespace) -> int:
    catalog = mc.channel_catalog()
    _emit({
        "schema": "contentops.multichannel-catalog/v1",
        "registry_rows": len(catalog["registry_rows"]),
        "video_delivery_platforms": len(catalog["video_delivery_platforms"]),
        "extra_delivery_channels": len(catalog["extra_delivery_channels"]),
        "platforms": catalog["registry_rows"],
        "video_platforms": catalog["video_delivery_platforms"],
        "extra_channels": catalog["extra_delivery_channels"],
        "note": catalog["note"],
        "generated_at": _stamp(),
    })
    return 0


def cmd_self_test(args: argparse.Namespace) -> int:
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "status": "passed" if ok else "blocked", "detail": detail})

    registry_hash_before = hashlib.sha256(PLATFORMS_JSON.read_bytes()).hexdigest()
    package = _load_package(Path(args.package))
    account = {"account_slug": str(package.get("account") or "explorer")}

    try:
        mc.MultiChannelAdapter("not_a_platform")
        record("unknown_platform_rejected", False, "未抛异常")
    except mc.UnknownPlatformError:
        record("unknown_platform_rejected", True, "UnknownPlatformError")

    registry_errors = validate_registry(ROOT)
    record("registry_validates", not registry_errors, str(registry_errors[:2]))

    guards = _no_network_guard()
    for guard in guards:
        guard.start()
    try:
        first = mc.build_all(package, account)
        second = mc.build_all(package, account)
        deterministic = [d.as_dict() for d, _, _ in first] == [d.as_dict() for d, _, _ in second]
        record("pack_deterministic", deterministic, f"{len(first)} platform drafts")
        record("pack_offline_no_network", True, "socket/urllib 被拦截且未触发")
        validations_ok = all(v.ok for _, v, _ in first)
        record("validate_all_drafts", validations_ok,
               str([(d.platform_id, v.errors) for d, v, _ in first if not v.ok]))
        handoff_ok = all(
            r.get("publication_state") == "AWAITING_MANUAL_PUBLISH"
            and "published_url" not in r
            and r.get("publish_authorized") is False
            and r.get("human_review") == "PENDING"
            and r.get("publish_mode") == "MANUAL_ONLY"
            for _, _, r in first
        )
        record("handoff_never_publishes", handoff_ok, "AWAITING_MANUAL_PUBLISH / no URL / no authorization")

        # --- platform spec checks -------------------------------------------
        # The spec file is now the single owner of "which platforms exist and
        # what shape they want". These checks fail loudly if the spec drifts
        # away from the registry or from its own provenance rules.
        spec_rows = graphic_specs.platform_ids()
        record("platform_spec_loads", bool(spec_rows), f"{len(spec_rows)} platforms: {list(spec_rows)}")

        registry_rows_raw = json.loads(PLATFORMS_JSON.read_text(encoding="utf-8")).get("platforms", [])
        # Classify by pipeline, not by an exclusion list: the registry also
        # carries VIDEO rows (douyin/bilibili/shipinhao/youtube) that the
        # graphic spec is not supposed to describe.
        graphic_pipelines = {"GZH_EDITORIAL", "X_EDITORIAL", "ARTICLE_EDITORIAL", "XHS_EDITORIAL"}
        graphic_registry = {
            r["platform_id"] for r in registry_rows_raw
            if r.get("pipeline") in graphic_pipelines
        }
        # xiaohongshu_image is a graphic-pipeline registry row that this spec
        # deliberately refuses to cover (operator instruction: video line). That
        # is a documented exclusion, so it must be present in `excluded` rather
        # than silently missing.
        excluded_ids = {e.get("platform_id") for e in graphic_specs.load_specs()["excluded"]}
        covered = {pid for pid in graphic_registry if pid in spec_rows or pid in excluded_ids}
        record("spec_covers_registry_graphic_rows", graphic_registry <= covered,
               f"missing={sorted(graphic_registry - covered)} excluded={sorted(excluded_ids)}")
        record("excluded_platforms_are_documented",
               all(e.get("reason") for e in graphic_specs.load_specs()["excluded"]),
               str([e.get("platform_id") for e in graphic_specs.load_specs()["excluded"]]))

        delivery_only = [pid for pid in spec_rows if not graphic_specs.is_registry_row(pid)]
        record("delivery_platforms_expanded", len(spec_rows) >= 7,
               f"{len(spec_rows)} total, {len(delivery_only)} delivery-only: {delivery_only}")

        basis_problems = []
        for pid in spec_rows:
            row = graphic_specs.spec(pid)
            for field in ("title_max_hard", "body_max_hard"):
                if field in row and f"{field}_basis" not in row:
                    basis_problems.append(f"{pid}.{field}")
            if row.get("title_max_soft") and "title_max_soft_basis" not in row:
                basis_problems.append(f"{pid}.title_max_soft")
        record("every_limit_has_a_basis", not basis_problems, str(basis_problems))

        tier_problems = [
            pid for pid in spec_rows
            if graphic_specs.rules(pid)["body_max_soft"]
            and graphic_specs.rules(pid)["body_max_hard"]
            and graphic_specs.rules(pid)["body_max_soft"] > graphic_specs.rules(pid)["body_max_hard"]
        ]
        record("soft_never_exceeds_hard", not tier_problems, str(tier_problems))

        record("x_counts_cjk_as_two", graphic_specs.weighted_len("中a", "x") == 3,
               f"'中a' -> {graphic_specs.weighted_len('中a', 'x')}")

        text_shaped = graphic_specs.shape("weibo", "标题在此", "正文内容")
        record("text_platform_folds_title_into_body",
               text_shaped["title"] == "" and "标题在此" in text_shaped["body"],
               f"title={text_shaped['title']!r}")

        truncation = graphic_specs.shape("x", "", "中" * 200)
        record("hard_limit_truncates_and_reports",
               "BODY_OVER_HARD" in " ".join(truncation["blockers"])
               and graphic_specs.weighted_len(truncation["body"], "x") <= 280,
               f"len={graphic_specs.weighted_len(truncation['body'], 'x')}")

        adapter = mc.MultiChannelAdapter("x")
        draft = next(d for d, _, _ in first if d.platform_id == "x")
        for label, auth in (
            ("publish_without_authorization", None),
            ("publish_with_incomplete_authorization", {"platform_id": "x"}),
            ("publish_with_full_authorization", {
                "platform_id": draft.platform_id, "account": "explorer",
                "package_id": draft.package_id, "bundle_sha256": draft.bundle_sha256,
                "reviewer": "operator", "expires_at": "2026-12-31T00:00:00Z",
                "scope": "draft_only", "publish_mode": "MANUAL_ONLY", "fresh": True,
            }),
        ):
            try:
                adapter.publish(draft, auth)
                record(label, False, "publish 未抛异常")
            except mc.PublishAuthorizationError:
                record(label, True, "PublishAuthorizationError")

        receipt_scan = json.dumps([r for _, _, r in first], ensure_ascii=False)
        record("receipt_no_secrets", not mc.SECRET_SHAPED_RE.search(receipt_scan), "no secret-shaped value")
        record("receipt_no_absolute_paths", not mc.ABSOLUTE_PATH_RE.search(receipt_scan), "logical refs only")

        bad_package = dict(package)
        bad_images = [dict(i) for i in (package.get("images") or [])]
        if bad_images:
            bad_images[0].pop("rights", None)
            bad_package["images"] = bad_images
            try:
                mc.MultiChannelAdapter("wechat_article").pack(bad_package, account)
                record("unlicensed_asset_refused", False, "未抛异常")
            except mc.RightsGateError:
                record("unlicensed_asset_refused", True, "RightsGateError")
        else:
            record("unlicensed_asset_refused", True, "样例包无图片，跳过（非失败）")

        changed = dict(package)
        changed["bundle_sha256"] = "0" * 64
        try:
            mc.MultiChannelAdapter("zhihu", expected_bundle_sha256=str(package["bundle_sha256"])).pack(changed, account)
            record("bundle_changed_refused", False, "未抛异常")
        except mc.BundleChangedError:
            record("bundle_changed_refused", True, "BUNDLE_CHANGED")
    finally:
        for guard in reversed(guards):
            guard.stop()

    registry_hash_after = hashlib.sha256(PLATFORMS_JSON.read_bytes()).hexdigest()
    record("registry_not_modified", registry_hash_before == registry_hash_after, registry_hash_before[:16])

    cli_ok = CLI_ENTRY.is_file()
    record("external_cli_installed", cli_ok, str(CLI_ENTRY) if cli_ok else "missing")
    if cli_ok:
        help_proc = subprocess.run(["node", str(CLI_ENTRY), "--help"], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=30)
        record("external_cli_help", help_proc.returncode == 0 and "sync" in help_proc.stdout,
               help_proc.stdout.splitlines()[0] if help_proc.stdout else "empty")
    try:
        import tweepy  # noqa: F401
        record("x_api_sdk_available", True, f"tweepy {tweepy.__version__}")
    except ImportError as exc:
        record("x_api_sdk_available", False, str(exc))

    blocked = [c for c in checks if c["status"] == "blocked"]
    payload = {
        "schema": "contentops.multichannel-self-test/v1",
        "network_called": False,
        "credentials_used": False,
        "checks": checks,
        "passed": len(checks) - len(blocked),
        "blocked": len(blocked),
        "status": "passed" if not blocked else "blocked",
        "generated_at": _stamp(),
    }
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _emit(payload)
    return 0 if not blocked else 1


def cmd_pack(args: argparse.Namespace) -> int:
    package = _load_package(Path(args.package))
    account = {"account_slug": str(package.get("account") or "explorer")}
    ids = [s.strip() for s in (args.platforms or "").split(",") if s.strip()] or list(mc.delivery_platform_ids())
    unknown = [p for p in ids if p not in mc.delivery_platform_ids()]
    if unknown:
        _emit({"status": "blocked", "reason": "UNKNOWN_PLATFORM_ID", "unknown": unknown})
        return 1
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for draft, validation, receipt in mc.build_all(package, account, ids):
        stem = draft.platform_id
        (out_dir / f"{stem}.draft.json").write_text(
            json.dumps(draft.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (out_dir / f"{stem}.receipt.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        entries.append({
            "platform_id": stem,
            "registry_row": draft.registry_row,
            "channel": draft.channel,
            "native_format": draft.native_format,
            "title_len": len(draft.title),
            "body_len": len(draft.body),
            "body_len_weighted": graphic_specs.weighted_len(draft.body, stem),
            "draft_sha256": draft.draft_sha256,
            "validation": validation.as_dict(),
            "publication_state": receipt["publication_state"],
            "blockers": receipt["blockers"],
            "warnings": receipt["warnings"],
        })
    index = {
        "schema": "contentops.multichannel-pack/v1",
        "package_id": package.get("bundle_id"),
        "bundle_sha256": package.get("bundle_sha256"),
        "platforms": entries,
        "network_called": False,
        "published": False,
        "generated_at": _stamp(),
    }
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _emit(index)
    return 0 if all(e["validation"]["ok"] for e in entries) else 1


def _derive_title(body: str, limit: int = 40) -> str:
    """Short-post platforms carry no title; the CLI still needs one.

    Derived from the first sentence rather than invented, so it cannot drift
    away from the delivered text. The caller records that this happened.
    """
    text = " ".join(str(body or "").split())
    for sep in ("。", "！", "？", "!", "?", "；", ";"):
        head, found, _ = text.partition(sep)
        if found and head.strip():
            text = head.strip()
            break
    text = text.strip("# ").strip()
    return text[:limit] if text else "未命名草稿"


def _resolve_cover(doc: dict[str, Any]) -> Path | None:
    """Resolve the first logical media ref back to a local file, if it exists.

    Drafts deliberately carry logical refs (``project://``), never absolute host
    paths. The cover argument is the one place a real path is needed, so it is
    resolved here, at the process boundary, and never written into a receipt.
    """
    for ref in doc.get("media_refs") or []:
        value = str(ref)
        if value.startswith("project://"):
            candidate = ROOT / value[len("project://"):]
        elif value.startswith("repo://"):
            candidate = ROOT / value[len("repo://"):]
        else:
            continue
        if candidate.is_file() and candidate.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"):
            return candidate
    return None


def _classify_failure(proc: subprocess.CompletedProcess) -> str:
    """Name the real blocker instead of collapsing everything to "not confirmed".

    The first real run of this command reported every failure as
    "外部通道未确认成功", which hid two completely different problems: a missing
    browser extension (a login-state problem) and a title-extraction refusal
    (an input-shape problem). Those need different fixes, so they get different
    names here.
    """
    blob = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    if "无法从文件提取标题" in blob:
        return "TITLE_EXTRACTION_FAILED: CLI 拒收无标题文件（已改为显式 --title，若仍出现即为回归）"
    if "需要安装 Chrome 扩展" in blob or "安装扩展" in blob:
        return "EXTENSION_MISSING: 未安装 Wechatsync 浏览器扩展，无法建立桥接"
    if "token" in blob.lower() or "Token" in blob:
        return "TOKEN_REQUIRED: 浏览器扩展未启用 MCP 连接或 WECHATSYNC_TOKEN 未配置"
    if "未登录" in blob or "not logged in" in blob.lower():
        return "NOT_LOGGED_IN: 目标平台未在浏览器中登录"
    return "外部通道未确认成功；不推断平台草稿已创建"


def cmd_dispatch(args: argparse.Namespace) -> int:
    """Hand a packed draft to the external CLI. Never fabricates success."""
    draft_path = Path(args.draft).expanduser().resolve()
    if not draft_path.is_file():
        _emit({"status": "blocked", "network_called": False, "reason": f"DRAFT_NOT_FOUND: {draft_path.name}"})
        return 1
    doc = json.loads(draft_path.read_text(encoding="utf-8"))
    # delivery_platform_ids() also populates the adapter's platform views; the
    # dict must not be read directly here or a fresh process would see it empty
    # and refuse every draft as UNKNOWN_PLATFORM_ID.
    if doc.get("platform_id") not in mc.delivery_platform_ids():
        _emit({"status": "blocked", "network_called": False, "reason": "UNKNOWN_PLATFORM_ID"})
        return 1
    if not CLI_ENTRY.is_file():
        _emit({"status": "blocked", "network_called": False, "reason": "EXTERNAL_CLI_NOT_INSTALLED"})
        return 1

    channel = str(args.channel or "").strip()
    if not channel:
        # The CLI only understands Wechatsync browser-bridge adapter ids. The
        # receipt's `channel` is the *intended* primary channel (which may be
        # an API path such as `wechatpy:draft` or `tweepy:api-v2`), so it must
        # not be reused here: splitting it produced channel="draft" and
        # channel="api-v2", both of which the CLI silently rejects.
        for ch in graphic_specs.channels(doc["platform_id"]):
            if ch["kind"] == "browser_bridge":
                channel = str(ch["id"]).split(":", 1)[1]
                break
        if not channel:
            _emit({
                "status": "blocked", "network_called": False,
                "platform_id": doc["platform_id"],
                "reason": "NO_BROWSER_BRIDGE_CHANNEL: 该平台没有 wechatsync 桥接适配器，"
                          "只能走 API 直连或人工投递",
                "published": False, "generated_at": _stamp(),
            })
            return 1

    work_dir = RUNTIME_TOOLS / "out"
    work_dir.mkdir(parents=True, exist_ok=True)
    article = work_dir / f"{doc['platform_id']}.md"
    title = str(doc.get("title") or doc.get("title_hint") or "").strip()
    body_text = str(doc.get("body") or "")
    if title:
        article.write_text(f"# {title}\n\n{body_text}", encoding="utf-8")
    else:
        # Short-post platforms have no title. The CLI refuses a file with no
        # heading and no front matter, so the body is written as-is and the
        # title is supplied explicitly on the command line instead of faking a
        # heading the platform would then display as content.
        article.write_text(body_text, encoding="utf-8")
        title = _derive_title(body_text)

    cmd = ["node", str(CLI_ENTRY), "sync", str(article), "-p", channel, "--title", title]
    cover = _resolve_cover(doc)
    cover_note = ""
    if cover:
        cmd.extend(["--cover", str(cover)])
    elif graphic_specs.rules(doc["platform_id"])["needs_cover"]:
        cover_note = "COVER_NOT_SUPPLIED: 该平台需要封面，草稿未携带可解析的本地图片"
    if args.dry_run:
        cmd.append("--dry-run")
    try:
        proc = subprocess.run(cmd, cwd=str(RUNTIME_TOOLS), capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=int(args.timeout))
    except subprocess.TimeoutExpired:
        _emit({
            "status": "blocked", "network_called": not args.dry_run,
            "platform_id": doc["platform_id"], "channel": channel,
            "delivered_title": title,
            "cover_used": bool(cover),
            "cover_note": cover_note,
            "reason": "EXTENSION_NOT_CONNECTED: CLI 等待浏览器扩展登录态超时；未创建任何平台草稿",
            "next_action": "安装 Wechatsync 浏览器扩展并在扩展设置中启用 MCP 连接，"
                           "然后在浏览器里登录该平台，再重跑本命令",
            "draft_sha256": doc.get("draft_sha256"),
            "published": False, "generated_at": _stamp(),
        })
        return 1
    stdout_lines = [l for l in (proc.stdout or "").splitlines() if l.strip()]
    if args.dry_run:
        # A dry run only prints a local preview; it starts no WebSocket bridge
        # and creates no platform draft. It must never be reported as delivery.
        payload = {
            "status": "dry_run_preview" if proc.returncode == 0 else "blocked",
            "network_called": False,
            "platform_id": doc["platform_id"],
            "channel": channel,
            "returncode": proc.returncode,
            "delivered_title": title,
            "cover_used": bool(cover),
            "cover_note": cover_note,
            "stdout_head": stdout_lines[:8],
            "publication_state": "NOT_PUBLISHED",
            "published": False,
            "reason": "本地干跑预览；未启动扩展桥接，未创建任何平台草稿",
            "generated_at": _stamp(),
        }
        _emit(payload)
        return 0 if proc.returncode == 0 else 1
    ok = proc.returncode == 0 and any(
        marker in (proc.stdout or "").lower() for marker in ("同步完成", "success", "草稿已创建")
    )
    payload = {
        "status": "handoff_submitted" if ok else "blocked",
        "network_called": True,
        "platform_id": doc["platform_id"],
        "channel": channel,
        "returncode": proc.returncode,
        "delivered_title": title,
        "cover_used": bool(cover),
        "cover_note": cover_note,
        "stdout_head": stdout_lines[:8],
        "stderr_head": (proc.stderr or "").splitlines()[:5],
        "published": False,
        "reason": "" if ok else _classify_failure(proc),
        "generated_at": _stamp(),
    }
    _emit(payload)
    return 0 if ok else 1


def cmd_status(args: argparse.Namespace) -> int:
    registry = json.loads(PLATFORMS_JSON.read_text(encoding="utf-8"))
    rows = registry["platforms"]
    graphic = [r for r in rows if r["pipeline"] in
               ("XHS_EDITORIAL", "GZH_EDITORIAL", "X_EDITORIAL", "ARTICLE_EDITORIAL")]
    workflows: dict[str, Any] = {}
    for wf in ("gzh", "xhs", "x"):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "graphic_workflow.py"),
                               "status", "--workflow", wf, "--json"],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
        try:
            workflows[wf] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            workflows[wf] = {"state": "UNPARSEABLE", "returncode": proc.returncode}
    payload = {
        "schema": "contentops.multichannel-status/v1",
        "registry": {
            "total_rows": len(rows),
            "graphic_rows": len(graphic),
            "rows": [{
                "platform_id": r["platform_id"], "strategy_platform": r["strategy_platform"],
                "pipeline": r["pipeline"], "status": r["status"],
                "publish_mode": r["publish_mode"],
                "adapter_row": bool(r.get("adapter")),
                "not_claimed": str(r.get("not_claimed") or "")[:160],
            } for r in graphic],
        },
        "workflows": workflows,
        "external_channels": {
            "wechatsync_cli": CLI_ENTRY.is_file(),
            "x_api_sdk": _tweepy_version(),
            "cli_requires_browser_extension": True,
        },
        "video_line": {
            "scope": "Xiaohongshu and the other video platforms per operator instruction 2026-11-09",
            "platforms": list(mc.VIDEO_DELIVERY_PLATFORMS),
            "external_tool": ".runtime/sau (dreammis/social-auto-upload, MIT)",
            "graphic_adapter_excludes": ["xiaohongshu_image"],
        },
        "adapter": {
            "module": "src/contentops/platforms/multichannel.py",
            "spec": "config/platforms/graphic-platforms.yaml",
            "runner": "scripts/platform_delivery.py",
            "registry_rows_implemented": list(mc.supported_platform_ids()),
            "delivery_platforms_implemented": list(mc.delivery_platform_ids()),
            "capability_matrix": graphic_specs.capability_matrix(),
            "extra_delivery_channels": len(mc.EXTRA_DELIVERY_CHANNELS),
            "registry_modified": False,
            "publish_authorized": False,
        },
        "generated_at": _stamp(),
    }
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _emit(payload)
    return 0


def _bridge_adapter(platform_id: str) -> str:
    for ch in graphic_specs.channels(platform_id):
        if ch["kind"] == "browser_bridge":
            return str(ch["id"]).split(":", 1)[1]
    return ""


def cmd_auth(args: argparse.Namespace) -> int:
    """Probe the browser-bridge login state for every graphic platform.

    This is a read-only probe. It starts the CLI, which starts a WebSocket
    bridge on 9527 and asks the installed extension about each platform's
    cookies. Nothing is published, no draft is created, and no credential is
    read by this script. When the extension is absent the CLI prints an install
    prompt; stdin is closed with ``N`` so it never blocks on interactive input.
    """
    ids = [s.strip() for s in (args.platforms or "").split(",") if s.strip()] \
        or list(mc.delivery_platform_ids())
    results: list[dict[str, Any]] = []
    for pid in ids:
        adapter_id = _bridge_adapter(pid)
        if not adapter_id:
            results.append({"platform_id": pid, "bridge_adapter": "", "state": "NO_BRIDGE_CHANNEL"})
            continue
        if not CLI_ENTRY.is_file():
            results.append({"platform_id": pid, "bridge_adapter": adapter_id,
                            "state": "EXTERNAL_CLI_NOT_INSTALLED"})
            continue
        cmd = ["node", str(CLI_ENTRY), "--timeout", str(args.timeout), "auth", adapter_id]
        try:
            proc = subprocess.run(cmd, cwd=str(RUNTIME_TOOLS), capture_output=True,
                                  text=True, encoding="utf-8", errors="replace",
                                  input="N\n", timeout=int(args.timeout) // 1000 + 20)
        except subprocess.TimeoutExpired:
            results.append({"platform_id": pid, "bridge_adapter": adapter_id,
                            "state": "PROBE_TIMEOUT"})
            continue
        blob = f"{proc.stdout or ''}\n{proc.stderr or ''}"
        if "需要安装 Chrome 扩展" in blob or "安装扩展" in blob:
            state = "EXTENSION_MISSING"
        elif proc.returncode == 0 and any(k in blob for k in ("已登录", "logged in", "OK")):
            state = "LOGGED_IN"
        elif "未登录" in blob or "login" in blob.lower():
            state = "NOT_LOGGED_IN"
        else:
            state = "UNKNOWN"
        results.append({
            "platform_id": pid,
            "bridge_adapter": adapter_id,
            "state": state,
            "returncode": proc.returncode,
            "stdout_head": [l for l in (proc.stdout or "").splitlines() if l.strip()][:6],
        })

    ready = [r for r in results if r["state"] == "LOGGED_IN"]
    payload = {
        "schema": "contentops.bridge-auth/v1",
        "network_called": False,
        "published": False,
        "probed": len(results),
        "logged_in": len(ready),
        "results": results,
        "conclusion": (
            "全部平台登录态就绪" if len(ready) == len(results)
            else "登录态未就绪：这是唯一挡在真实投递前的门，且必须由账号持有者本人完成"
        ),
        "generated_at": _stamp(),
    }
    if args.output:
        out = Path(args.output).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _emit(payload)
    return 0 if len(ready) == len(results) else 1


def _tweepy_version() -> str | bool:
    try:
        import tweepy  # noqa: F401
        return str(tweepy.__version__)
    except ImportError:
        return False


def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list")
    p_list.set_defaults(func=cmd_list)

    p_test = sub.add_parser("self-test")
    p_test.add_argument("--package", default=str(DEFAULT_PACKAGE))
    p_test.add_argument("--output")
    p_test.set_defaults(func=cmd_self_test)

    p_pack = sub.add_parser("pack")
    p_pack.add_argument("--package", default=str(DEFAULT_PACKAGE))
    p_pack.add_argument("--platforms", default="")
    p_pack.add_argument("--out", default=str(ROOT / ".runtime" / "multichannel-out"))
    p_pack.set_defaults(func=cmd_pack)

    p_dispatch = sub.add_parser("dispatch")
    p_dispatch.add_argument("--draft", required=True)
    p_dispatch.add_argument("--channel", default="")
    p_dispatch.add_argument("--dry-run", action="store_true")
    p_dispatch.add_argument("--timeout", default="20")
    p_dispatch.set_defaults(func=cmd_dispatch)

    p_status = sub.add_parser("status")
    p_status.add_argument("--output")
    p_status.set_defaults(func=cmd_status)

    p_auth = sub.add_parser("auth")
    p_auth.add_argument("--platforms", default="")
    p_auth.add_argument("--timeout", default="8000")
    p_auth.add_argument("--output")
    p_auth.set_defaults(func=cmd_auth)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
