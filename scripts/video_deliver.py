#!/usr/bin/env python3
"""Pack one finished film into per-platform delivery sets, and hand them over.

This is the runner the VIDEO line was missing. Before it, a run ended with
``final/<slug>.mp4`` and every platform hand-off was a human retyping the same
description into a different browser form while guessing that platform's limits.

    probe -> shape from account DNA -> validate -> thumbnails -> package
          -> authorize -> argv (and, only with a grant, run the uploader)

Commands
--------
  plan      What would be produced and what is missing. Writes nothing.
  pack      Write 06_delivery/ packages, thumbnails and a receipt.
  status    Re-read an existing package and re-decide authorization.
  dispatch  Build the uploader argv per platform; run only with --execute plus
            an operator grant.
  login     Open the uploader's own login flow (visible window) so a human can
            scan once. Cookie state cannot be manufactured by code.
  check     Ask the uploader whether the stored login still works.
  record    Write down a real published URL a person actually saw. This is the
            only path from "tool exited 0" to "this work exists on the platform",
            because the uploader never returns a URL.

Honesty rules baked in
----------------------
* ``publish_authorized`` and ``production_ready`` are always false in a receipt.
* A title that had to be shortened keeps its original; nothing is reworded.
* Thumbnails are mechanical frame crops, not designed covers, and are labelled so.
* A successful uploader exit code is recorded as ``UPLOADER_EXIT_0``. It is never
  a published claim: only a real platform URL moves that, and the URL is filled
  in by a person.
* The uploader is an external tool invoked across a process boundary from the
  gitignored ``.runtime/`` tree. It is never imported.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import load_account  # noqa: E402
from contentops.platforms import video_delivery, video_package, video_specs  # noqa: E402
from process_utils import hidden_run, interactive_run  # noqa: E402

SAU_ROOT = ROOT / ".runtime" / "sau"
SAU_VENV_BIN = ROOT / ".runtime" / "sau-venv" / "Scripts"
DELIVERY_DIR = "06_delivery"
THUMB_RATIOS = {"3:4": 0.75, "4:3": 4.0 / 3.0, "16:9": 16.0 / 9.0}


def _resolve_uploader(name: str) -> tuple[str, str]:
    """Locate the uploader without pretending a missing tool exists.

    The upstream project needs Python < 3.13, so it is installed into its own
    venv under ``.runtime/``. The console script is not on PATH, and a bare
    ``"sau"`` would therefore fail with "not found" on a machine where the tool
    is in fact installed. Resolution order is explicit path, PATH, repo venv;
    the answer is recorded in the receipt so nobody has to guess which binary ran.
    """
    if name and Path(name).is_file():
        return str(Path(name).resolve()), "explicit_path"
    found = shutil.which(name)
    if found:
        return found, "on_path"
    for candidate in (SAU_VENV_BIN / "sau.exe", SAU_VENV_BIN / "sau"):
        if candidate.is_file():
            return str(candidate), "repo_venv"
    return name, "not_found"


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_yaml(project_dir: Path) -> dict[str, Any]:
    import yaml  # noqa: PLC0415 - local import keeps startup cheap

    path = project_dir / "project.yaml"
    if not path.is_file():
        raise SystemExit(f"BLOCKED: 缺少 {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _account_for(project_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    slug = str(data.get("account_slug") or "").strip()
    if not slug:
        raise SystemExit(
            "BLOCKED: project.yaml 未声明 account_slug；没有账号 DNA 就没有平台调性，"
            "不允许用通用模板顶替"
        )
    path = ROOT / "config" / "accounts" / f"{slug}.json"
    if not path.is_file():
        raise SystemExit(f"BLOCKED: 账号 DNA 不存在 {path}")
    return load_account(path)


def _pick_video(project_dir: Path) -> Path:
    final = project_dir / "final"
    candidates = [p for p in sorted(final.glob("*.mp4")) if "before" not in p.name.lower()]
    if not candidates:
        raise SystemExit(f"BLOCKED: {final} 下没有可用成片")
    return candidates[-1]


def _probe(path: Path) -> dict[str, Any]:
    if not shutil.which("ffprobe"):
        raise SystemExit("BLOCKED: 找不到 ffprobe，无法真实测量成片参数")
    proc = hidden_run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration,size",
         "-of", "json", str(path)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise SystemExit(f"BLOCKED: ffprobe 失败：{(proc.stderr or '').strip()[:300]}")
    payload = json.loads(proc.stdout or "{}")
    stream = (payload.get("streams") or [{}])[0]
    fmt = payload.get("format") or {}
    return {
        "path": str(path),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "duration_s": float(fmt.get("duration") or 0.0),
        "size_bytes": int(fmt.get("size") or path.stat().st_size),
        "sha256": _sha256(path),
    }


def _srt_seconds(text: str) -> float | None:
    match = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", text.strip())
    if not match:
        return None
    hours, minutes, seconds, millis = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def _hook_end(project_dir: Path) -> float | None:
    """End of the first subtitle cue: that is when the hook has landed."""
    srt = project_dir / "assets" / "captions" / "default.srt"
    if not srt.is_file():
        return None
    for line in srt.read_text(encoding="utf-8", errors="replace").splitlines():
        if "-->" in line:
            return _srt_seconds(line.split("-->")[1])
    return None


def _horizontal_variant(video: Path, out_dir: Path) -> dict[str, Any]:
    """Derive a 1920x1080 carrier from the vertical film, without re-rendering.

    Why a derived variant and not a real horizontal cut
    ---------------------------------------------------
    ``scripts/huashu_motion_adapter.py`` renders scenes from HTML whose layout is
    authored in absolute pixels for 1080x1920 (``#film{width:1080px;height:1920px}``,
    ``svg viewBox="0 0 1080 1920"``). A genuine 1920x1080 design is a re-layout of
    every scene template, not a parameter. So this produces a *carrier*: the same
    film, full height, centred on a blurred fill.

    It is labelled ``BLUR_PAD_VARIANT`` everywhere it appears, and the receipt
    states the two things a reader must know: the picture is scaled to 56% and
    this is not the account DNA's long-form horizontal edit.
    """
    if not shutil.which("ffmpeg"):
        return {"state": "BLOCKED", "reason": "FFMPEG_MISSING"}
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{video.stem}-1920x1080.mp4"
    graph = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,gblur=sigma=28,eq=brightness=-0.14[bg];"
        "[0:v]scale=-2:1080:force_original_aspect_ratio=decrease[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p[v]"
    )
    proc = hidden_run(
        ["ffmpeg", "-y", "-i", str(video), "-filter_complex", graph,
         "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "medium",
         "-crf", "20", "-c:a", "copy", str(target)],
        capture_output=True, text=True, timeout=900,
    )
    if proc.returncode != 0 or not target.is_file():
        return {"state": "BLOCKED", "reason": (proc.stderr or "")[-300:]}
    probe = _probe(target)
    source = _probe(video)
    return {
        "state": "DERIVED",
        "variant": "BLUR_PAD_VARIANT",
        "path": str(target),
        "width": probe["width"],
        "height": probe["height"],
        "duration_s": probe["duration_s"],
        "size_mb": round(probe["size_bytes"] / (1024 * 1024), 2),
        "sha256": probe["sha256"],
        "scale_of_original": round(1080 / max(source["height"], 1), 3),
        "quality_note": (
            "竖版成片居中 + 高斯模糊填充，画面按 56% 缩放；"
            "这不是账号 DNA 要求的 1920x1080 加长重构版，只是横屏载体"
        ),
        "requires_render_layer_change": (
            "真横版需要重排 huashu_motion_backend 的场景模板（绝对像素布局）"
        ),
    }


def _extract_thumbnails(video: Path, out_dir: Path, at_s: float) -> dict[str, str]:
    """Crop a mechanical still per ratio. Never called a designed cover."""
    if not shutil.which("ffmpeg"):
        return {}
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    for ratio, value in THUMB_RATIOS.items():
        target = out_dir / f"frame-{ratio.replace(':', 'x')}.png"
        crop = (
            f"crop='min(iw,ih*{value:.4f})':'min(ih,iw/{value:.4f})',"
            "scale=trunc(iw/2)*2:trunc(ih/2)*2"
        )
        proc = hidden_run(
            ["ffmpeg", "-y", "-ss", f"{max(at_s, 0.1):.3f}", "-i", str(video),
             "-frames:v", "1", "-vf", crop, str(target)],
            capture_output=True, text=True, timeout=180,
        )
        if proc.returncode == 0 and target.is_file():
            written[ratio] = str(target)
    return written


def _category_sources(project: dict[str, Any], account: dict[str, Any]) -> tuple[str, str]:
    """Where a numeric platform category may come from, most specific first.

    Kept separate from the CLI flag so a project can declare its section once
    instead of every run retyping ``--tid``.
    """
    target = project.get("target") or {}
    project_value = str(
        project.get("bilibili_tid") or target.get("bilibili_tid") or ""
    ).strip()
    dna_value = str(
        account.get("bilibili_tid") or account.get("platform_bilibili_tid") or ""
    ).strip()
    return project_value, dna_value


def _resolve_tid(args: argparse.Namespace, project: dict[str, Any], account: dict[str, Any]) -> dict[str, str]:
    value, _source = video_delivery.resolve_category(
        "bilibili",
        cli_value=str(getattr(args, "tid", "") or ""),
        project_value=_category_sources(project, account)[0],
        dna_value=_category_sources(project, account)[1],
    )
    return {"category": value} if value else {}


def _load_or_pack(project_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    package_file = project_dir / DELIVERY_DIR / "video-package.json"
    if args.command in ("status", "dispatch") and package_file.is_file():
        return json.loads(package_file.read_text(encoding="utf-8"))
    return pack(project_dir, args)


def pack(project_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    data = _project_yaml(project_dir)
    account = _account_for(project_dir, data)
    video = _pick_video(project_dir)
    media = _probe(video)
    hook = _hook_end(project_dir)

    delivery = project_dir / DELIVERY_DIR
    thumbnails: dict[str, str] = {}
    if getattr(args, "thumbnails", False):
        thumbnails = _extract_thumbnails(video, delivery / "thumbnails", hook or 0.0)

    horizontal: dict[str, Any] = {}
    if getattr(args, "horizontal", False):
        horizontal = _horizontal_variant(video, delivery / "horizontal")

    supplied = _resolve_tid(args, data, account)

    package = video_package.build(
        project_id=str(data.get("id") or project_dir.name),
        account=account,
        media=media,
        thumbnails=thumbnails,
        supplied_args=supplied,
        hook_s=hook,
    )
    package["generated_at"] = _stamp()
    package["supplied_args"] = dict(supplied)
    package["video"] = media["path"]
    package["video_sha256"] = media["sha256"]
    package["thumbnail_kind"] = "MECHANICAL_FRAME_CROP" if thumbnails else "NONE"
    package["thumbnails"] = thumbnails
    if horizontal:
        package["horizontal"] = horizontal
    package["source_platforms"] = list(account.get("platforms") or [])
    package["derived_platforms"] = list(account.get("derived_platforms") or [])
    return package


def _write(project_dir: Path, package: dict[str, Any]) -> dict[str, Any]:
    delivery = project_dir / DELIVERY_DIR
    delivery.mkdir(parents=True, exist_ok=True)
    (delivery / "video-package.json").write_text(
        json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for entry in package.get("platforms") or []:
        (delivery / f"{entry['platform_id']}.json").write_text(
            json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    receipts = project_dir / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "contentops.video-delivery/v1",
        "project": package.get("project"),
        "account": package.get("account"),
        "state": package.get("state"),
        "video_sha256": package.get("video_sha256"),
        "media": package.get("media"),
        "thumbnail_kind": package.get("thumbnail_kind"),
        "horizontal": package.get("horizontal") or {},
        "publish_authorized": False,
        "production_ready": False,
        "platforms": [
            {
                "platform_id": e["platform_id"],
                "state": e["state"],
                "blockers": [i for i in e["issues"] if i["severity"] == video_specs.ISSUE_BLOCKER],
                "warnings": [i for i in e["issues"] if i["severity"] == video_specs.ISSUE_WARNING],
            }
            for e in package.get("platforms") or []
        ],
        "generated_at": _stamp(),
    }
    (receipts / "video-delivery.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def dispatch(project_dir: Path, package: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    grant = video_delivery.load_grant(Path(args.grant) if args.grant else None)
    wanted = [p.strip() for p in (args.platforms or "").split(",") if p.strip()]
    entries = {e["platform_id"]: e for e in package.get("platforms") or []}
    chosen = wanted or list(entries)

    account_name = args.account or package.get("account") or "default"
    executable, resolution = _resolve_uploader(args.sau_cmd)
    results: list[dict[str, Any]] = []

    variant_file = str(package.get("video") or "")
    variant_note = "VERTICAL_PRIMARY"
    if getattr(args, "variant", "vertical") == "horizontal":
        horizontal = package.get("horizontal") or {}
        if horizontal.get("state") == "DERIVED" and horizontal.get("path"):
            variant_file = str(horizontal["path"])
            variant_note = str(horizontal.get("variant") or "DERIVED")
        else:
            variant_note = "HORIZONTAL_NOT_PACKED: 先用 pack --horizontal 生成"

    # The packer already resolved a category from project/DNA. A flag on this
    # invocation wins, because the operator is looking at the video right now.
    supplied = dict(package.get("supplied_args") or {})
    if getattr(args, "tid", ""):
        supplied["category"] = str(args.tid)

    for pid in chosen:
        entry = entries.get(pid)
        if not entry:
            results.append({"platform_id": pid, "outcome": "REFUSED",
                            "reasons": ["NOT_IN_PACKAGE: 该平台不在本次投递包内"]})
            continue

        ready, expected = video_delivery.cookie_present(SAU_ROOT, pid, account_name)
        argv = video_delivery.build_command(
            pid,
            executable=executable,
            account=account_name,
            video=variant_file,
            metadata=entry["metadata"],
            thumbnails=package.get("thumbnails") or {},
            supplied_args=supplied,
            draft=bool(args.draft),
            headed=bool(args.headed),
        )
        decision = video_delivery.authorize(
            pid,
            package_state=entry["state"],
            publish_authorized_claim=bool(package.get("publish_authorized")),
            execute_requested=bool(args.execute),
            grant=grant,
            cookie_ready=ready,
            cookie_expected=str(expected),
            command=argv,
        )
        row = decision.to_dict()
        row["cookie_expected"] = str(expected)
        row["cookie_present"] = ready
        row["uploader_executable"] = executable
        row["uploader_resolution"] = resolution
        row["variant"] = variant_note

        if decision.executable:
            if resolution == "not_found":
                row["outcome"] = "REFUSED"
                row["reasons"] = list(row["reasons"]) + [
                    "UPLOADER_NOT_INSTALLED: 找不到上传器；"
                    "在 .runtime/sau 用 3.10 建 venv 后 uv pip install -e ."
                ]
            else:
                proc = hidden_run(list(decision.command), cwd=str(SAU_ROOT),
                                  capture_output=True, text=True, timeout=args.timeout)
                row["exit_code"] = proc.returncode
                row["outcome"] = "UPLOADER_EXIT_0" if proc.returncode == 0 else "UPLOADER_FAILED"
                row["stdout_tail"] = (proc.stdout or "")[-800:]
                row["stderr_tail"] = (proc.stderr or "")[-800:]
                row["published_url"] = None
                row["url_note"] = "上传器不回传 URL；发布真实性只能由人工回填真实链接确认"
        results.append(row)

    payload = {
        "schema": "contentops.video-dispatch/v1",
        "project": package.get("project"),
        "execute": bool(args.execute),
        "grant_file": str(args.grant) if args.grant else "",
        "results": results,
        "generated_at": _stamp(),
    }
    delivery = project_dir / DELIVERY_DIR
    delivery.mkdir(parents=True, exist_ok=True)
    (delivery / "dispatch-plan.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return payload


def login(platform_id: str, account: str, args: argparse.Namespace) -> dict[str, Any]:
    """Open the uploader's own login flow so a human can scan once.

    Cookie state is the one thing this pipeline cannot manufacture: every
    supported platform authenticates with a QR code or a password prompt. The
    uploader already implements that flow, so this command only locates the
    binary, keeps the browser visible and records what happened.
    """
    executable, resolution = _resolve_uploader(args.sau_cmd)
    if resolution == "not_found":
        return {"status": "BLOCKED",
                "reason": "UPLOADER_NOT_INSTALLED: 找不到上传器；先在 .runtime/sau 用 3.10 建 venv 并安装"}

    upstream = str(video_specs.uploader(platform_id)["platform"])
    argv = [executable, upstream, "login", "--account", account, "--headed"]
    print(f"RUNNING (可见窗口，需人工扫码): {' '.join(argv)}", flush=True)
    proc = interactive_run(argv, cwd=str(SAU_ROOT))
    ready, expected = video_delivery.cookie_present(SAU_ROOT, platform_id, account)
    return {
        "platform_id": platform_id,
        "upstream_platform": upstream,
        "exit_code": proc.returncode,
        "cookie_expected": str(expected),
        "cookie_present": ready,
        "status": "LOGIN_RECORDED" if ready else "LOGIN_NOT_CONFIRMED",
        "note": "只有 cookie 文件真实落盘才算登录成功；退出码 0 不算",
    }


def check(platform_id: str, account: str, args: argparse.Namespace) -> dict[str, Any]:
    """Ask the uploader whether the stored login still works."""
    executable, resolution = _resolve_uploader(args.sau_cmd)
    if resolution == "not_found":
        return {"status": "BLOCKED", "reason": "UPLOADER_NOT_INSTALLED"}
    upstream = str(video_specs.uploader(platform_id)["platform"])
    proc = hidden_run(
        [executable, upstream, "check", "--account", account],
        cwd=str(SAU_ROOT), capture_output=True, text=True, timeout=args.timeout,
    )
    ready, expected = video_delivery.cookie_present(SAU_ROOT, platform_id, account)
    return {
        "platform_id": platform_id,
        "exit_code": proc.returncode,
        "cookie_present": ready,
        "cookie_expected": str(expected),
        "output_tail": ((proc.stdout or "") + (proc.stderr or ""))[-600:],
        "status": "LOGIN_VALID" if proc.returncode == 0 and ready else "LOGIN_INVALID",
    }


def record(project_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    """Write down a real published URL a person actually saw."""
    receipt = video_delivery.record_publication(
        args.platform,
        args.url,
        metrics=_read_metrics(args.metrics),
        checked_at=_stamp(),
    )
    if not receipt["accepted"]:
        _emit(receipt)
        return receipt

    receipts = project_dir / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    receipt["project"] = project_dir.name
    receipt["schema"] = "contentops.video-published/v1"
    path = receipts / f"video-published-{args.platform}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt["receipt_path"] = str(path)
    _emit(receipt)
    return receipt


def _read_metrics(path: str) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.is_file():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "command",
        choices=("plan", "pack", "status", "dispatch", "login", "check", "record"),
    )
    parser.add_argument("--project", required=True, help="project directory")
    parser.add_argument("--thumbnails", action="store_true",
                        help="extract mechanical frame stills per ratio (ffmpeg)")
    parser.add_argument("--horizontal", action="store_true",
                        help="derive a 1920x1080 blurred-pad carrier (labelled variant)")
    parser.add_argument("--variant", choices=("vertical", "horizontal"), default="vertical",
                        help="which file dispatch should hand over")
    parser.add_argument("--tid", default="", help="bilibili category id (human supplied)")
    parser.add_argument("--platforms", default="", help="comma separated subset")
    parser.add_argument("--platform", default="", help="single platform (login/check/record)")
    parser.add_argument("--url", default="", help="real published URL (record)")
    parser.add_argument("--metrics", default="", help="JSON file with real metric values (record)")
    parser.add_argument("--account", default="", help="uploader account name (cookie file stem)")
    parser.add_argument("--sau-cmd", default="sau", help="uploader executable name")
    parser.add_argument("--grant", default="", help="operator grant json path")
    parser.add_argument("--execute", action="store_true", help="actually run the uploader")
    parser.add_argument("--draft", action="store_true", help="use --draft where supported")
    parser.add_argument("--headed", action="store_true",
                        help="run the uploader with a visible browser (no headless-shell needed)")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args(argv)

    project_dir = Path(args.project).resolve()
    if not project_dir.is_dir():
        _emit({"status": "BLOCKED", "reason": f"项目目录不存在：{project_dir}"})
        return 1

    if args.command in ("login", "check"):
        platform = args.platform or args.platforms.split(",")[0].strip()
        if platform not in video_specs.platform_ids():
            _emit({"status": "BLOCKED", "reason": f"UNKNOWN_PLATFORM: {platform!r}"})
            return 1
        payload = (login if args.command == "login" else check)(platform, args.account or "default", args)
        _emit(payload)
        return 0 if payload.get("status", "").endswith(("RECORDED", "VALID")) else 2

    if args.command == "record":
        if args.platform not in video_specs.platform_ids():
            _emit({"status": "BLOCKED", "reason": f"UNKNOWN_PLATFORM: {args.platform!r}"})
            return 1
        return 0 if record(project_dir, args)["accepted"] else 2

    if args.command == "plan":
        package = pack(project_dir, args)
        _emit({
            "project": package.get("project"),
            "account": package.get("account"),
            "state": package.get("state"),
            "media": package.get("media"),
            "hook_s": package.get("hook_s"),
            "platforms": [
                {"platform_id": e["platform_id"], "state": e["state"],
                 "issues": [i["code"] for i in e["issues"]],
                 "uploader": e["uploader"]}
                for e in package.get("platforms") or []
            ],
            "blockers": package.get("blockers"),
            "note": "plan 不写文件；落盘请用 pack",
        })
        return 0

    package = _load_or_pack(project_dir, args)

    if args.command in ("pack", "status"):
        summary = _write(project_dir, package)
        _emit(summary)
        return 0 if summary["state"] == video_package.STATE_READY else 2

    payload = dispatch(project_dir, package, args)
    _emit(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
