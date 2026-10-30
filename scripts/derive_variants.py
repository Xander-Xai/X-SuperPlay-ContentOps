#!/usr/bin/env python3
"""Derive the other platforms' cuts from one graded master, with receipts.

Why this exists
---------------
Douyin, Bilibili and Xiaohongshu do not want the same frame. The account DNA
declares 1080x1920 for Douyin, 1920x1080 for the Bilibili cut, and a 3:4 cover
for Xiaohongshu. Until now the pipeline produced exactly one vertical film and
``qc_video`` graded every project against the constant 1080x1920, so a 16:9 cut
could not even be reported as correct -- it was a "broken" vertical one.

This script turns the master into the other shapes with the pinned runtime's
``reframe.py`` (the tool that owns aspect conversion; a hand-rolled filter chain
is not allowed), then probes every output and writes a receipt that binds the
master, each derivative, the exact tool file that ran, and the target ratio.

What it does not claim
----------------------
A derivative is technically correct, not content-approved. It inherits the
master's approval and its problems alike, so an ungraded master is refused. The
receipt also records the tool's digest rather than asserting the runtime is
trusted: ``verify_easel_runtime.py`` is the thing that decides that, and while it
reports a mismatch no derivative may be called production-ready.

Usage
-----
    python scripts/derive_variants.py projects/easel-1024-proof --dry-run
    python scripts/derive_variants.py projects/easel-1024-proof
    python scripts/derive_variants.py projects/x --platforms bilibili

Exit codes: 0 derived, 1 failed, 4 blocked (nothing was written).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run, python_executable  # noqa: E402
#: ``parse_yaml`` is the repository's yaml-lite reader for project.yaml; reusing it
#: keeps one parsing rule instead of a fourth private copy.
from qc_video import ffprobe_meta, parse_yaml  # noqa: E402

SCHEMA = "contentops.variants/v1"

#: The frame each platform actually publishes, as the account DNAs and the
#: platform notes describe it. A platform absent from this table is not silently
#: given the master; it is reported and skipped.
PLATFORM_FRAME: Dict[str, Tuple[int, int]] = {
    "douyin": (1080, 1920),
    "bilibili": (1920, 1080),
    "xiaohongshu": (1080, 1920),
    "shipinhao": (1080, 1920),
    "kuaishou": (1080, 1920),
}

#: Pixel size used for each frame. Keeping the standard size rather than scaling
#: the master's area keeps the receipt predictable across projects.
STANDARD_SIZE: Dict[Tuple[int, int], Tuple[int, int]] = {
    (1080, 1920): (1080, 1920),
    (1920, 1080): (1920, 1080),
    (1080, 1080): (1080, 1080),
    (1080, 1440): (1080, 1440),
    (1080, 1350): (1080, 1350),
}

#: How to get there. Turning a vertical cut into a horizontal one by cropping
#: throws away most of the frame, so the DNA's own choice -- pad onto a blurred
#: copy of the frame -- is the default.
PLATFORM_MODE: Dict[str, str] = {"bilibili": "blur"}

#: Cover frame each platform publishes. A cover is *rendered*, not cropped: a 3:4
#: crop of a 9:16 card loses the type that was laid out for it. So this table is
#: used to report a missing or wrong-shaped cover, never to fabricate one.
PLATFORM_COVER: Dict[str, Tuple[int, int]] = {
    "douyin": (1080, 1440),
    "xiaohongshu": (1080, 1440),
    "bilibili": (1600, 900),
}

RUNTIME_TOOL = ROOT / ".runtime" / "easel" / "skills" / "shared" / "scripts" / "reframe.py"


def _fail(code: str, detail: str) -> None:
    print(json.dumps({"status": "BLOCKED", "code": code, "reason": detail},
                     ensure_ascii=False, indent=2))
    raise SystemExit(4)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def master_frame(meta: Dict[str, Any]) -> Tuple[int, int]:
    for stream in meta.get("streams") or []:
        if stream.get("codec_type") == "video":
            return int(stream.get("width") or 0), int(stream.get("height") or 0)
    return 0, 0


def plan_variants(master: Tuple[int, int],
                  platforms: Sequence[str]) -> List[Dict[str, Any]]:
    """Which frames still have to be produced. Pure: no filesystem, no ffmpeg.

    The master already satisfies the platform whose frame it is, so that platform
    gets no derivative -- re-encoding a film to the size it already has would
    produce a second file with the same content and a second thing to keep in
    sync for nothing.
    """
    planned: List[Dict[str, Any]] = []
    for platform in sorted(set(platforms)):
        if not platform:
            continue
        want = PLATFORM_FRAME.get(platform)
        if want is None:
            planned.append({"platform": platform, "action": "SKIP",
                            "reason": "no declared frame for this platform"})
            continue
        if master == want:
            planned.append({"platform": platform, "action": "SKIP",
                            "reason": f"the master is already {want[0]}x{want[1]}"})
            continue
        size = STANDARD_SIZE.get(want, want)
        planned.append({
            "platform": platform,
            "action": "DERIVE",
            "ratio": f"{want[0]}:{want[1]}",
            "width": size[0],
            "height": size[1],
            "mode": PLATFORM_MODE.get(platform, "blur"),
        })
    return planned


def _png_size(path: Path) -> Tuple[int, int]:
    """Width and height from the PNG header, without an imaging dependency."""
    try:
        header = path.read_bytes()[:24]
    except OSError:
        return 0, 0
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        return 0, 0
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def cover_status(project: Path, platforms: Sequence[str],
                 config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Which platforms still lack a cover at their own frame.

    A cover is designed at its platform's shape; cropping one into another shape
    cuts the type that was laid out for it, so this reports instead of converting.
    Candidate order: an explicit ``<platform>.png`` beside the covers, then the
    project's declared ``cover_png`` when its ``cover_platform`` matches.
    """
    declared = str(config.get("cover_png") or "")
    declared_platform = str(config.get("cover_platform") or "")
    rows: List[Dict[str, Any]] = []
    for platform in sorted(set(platforms)):
        want = PLATFORM_COVER.get(platform)
        if want is None:
            rows.append({"platform": platform, "status": "NO_DECLARED_COVER",
                         "reason": "no cover frame is declared for this platform"})
            continue
        candidates = [project / "assets" / "covers" / f"{platform}.png"]
        if declared and declared_platform == platform:
            candidates.append(project / declared)
        chosen = next((path for path in candidates if path.is_file()), None)
        if chosen is None:
            rows.append({"platform": platform, "status": "ABSENT",
                         "expected": f"{want[0]}x{want[1]}",
                         "reason": f"no cover at assets/covers/{platform}.png"})
            continue
        width, height = _png_size(chosen)
        ok = (width, height) == want
        rows.append({
            "platform": platform,
            "status": "PRESENT" if ok else "WRONG_FRAME",
            "path": f"project://{chosen.relative_to(project).as_posix()}",
            "width": width, "height": height,
            "expected": f"{want[0]}x{want[1]}",
        })
    return rows


def _platforms_for(config: Dict[str, Any], account: Dict[str, Any],
                   override: Sequence[str] | None) -> List[str]:
    if override:
        return [p.strip() for p in override if p.strip()]
    declared = config.get("platforms")
    if isinstance(declared, list):
        platforms = [str(p).strip() for p in declared]
    else:
        platforms = []
    roles = account.get("platform_roles") or {}
    for platform, role in roles.items():
        if str((role or {}).get("status") or "").upper() == "ACTIVE":
            platforms.append(platform)
    return sorted({p for p in platforms if p})


def _account(project: Path) -> Dict[str, Any]:
    from account_route import RouteBlocked, declared_account_slug, load_dna
    slug = declared_account_slug(project)
    if not slug:
        _fail("ACCOUNT_SLUG_MISSING",
              "project.yaml names no account_slug, so no publication frame resolves")
    try:
        return load_dna(slug)
    except RouteBlocked as blocked:
        _fail(blocked.code, blocked.detail)
    return {}


def _graded(project: Path, master: Path) -> Dict[str, Any]:
    """A derivative inherits the master's verdict, so the master has to have one.

    A fresh receipt is not enough: a receipt that says FAIL is the master being
    wrong, and re-framing a failing cut into three shapes only multiplies it.
    """
    receipts = project / "receipts"
    candidates = [receipts / f"qc-report-{master.stem}.json", receipts / "qc-report.json"]
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        _fail("MASTER_NOT_GRADED",
              f"no QC receipt for {master.name}; derive only from a graded master")
    fresh = [path for path in existing if path.stat().st_mtime >= master.stat().st_mtime]
    if not fresh:
        _fail("MASTER_QC_STALE",
              f"every QC receipt predates {master.name}; regrade before deriving")
    verdicts: Dict[str, str] = {}
    for path in fresh:
        try:
            verdict = str(json.loads(path.read_text(encoding="utf-8")).get("overall") or "")
        except (OSError, ValueError):
            _fail("MASTER_QC_UNREADABLE",
                  f"{path.relative_to(project).as_posix()} is not a readable report")
        if not verdict:
            _fail("MASTER_QC_UNREADABLE",
                  f"{path.relative_to(project).as_posix()} records no overall verdict")
        verdicts[path.relative_to(project).as_posix()] = verdict
    # One FAIL is a FAIL. A newer PASS from a different gate does not override an
    # older FAIL from another: the two gates check different things, so "the
    # master is fine" requires every fresh receipt to say so.
    failed = sorted(name for name, verdict in verdicts.items() if verdict.upper() == "FAIL")
    if failed:
        _fail("MASTER_QC_FAILED",
              f"the master's own QC says FAIL ({', '.join(failed)}); fix the cut before "
              "deriving other platforms from it")
    return {
        "verdicts": verdicts,
        "receipts": [str(path.relative_to(project).as_posix()) for path in existing],
    }


def derive(project: Path, *, video: str = "", only: Sequence[str] | None = None,
           dry_run: bool = False) -> Dict[str, Any]:
    project = project.resolve()
    config_path = project / "project.yaml"
    config = parse_yaml(config_path) if config_path.is_file() else {}
    account = _account(project)

    master = project / "final" / (video or "easel.mp4")
    if not master.is_file():
        _fail("MASTER_MISSING", str(master))
    meta = ffprobe_meta(master)
    master_size = master_frame(meta)
    if 0 in master_size:
        _fail("MASTER_UNREADABLE", f"no video stream in {master.name}")

    grade = _graded(project, master)
    platforms = _platforms_for(config, account, only)
    planned = plan_variants(master_size, platforms)
    covers = cover_status(project, platforms, config)
    todo = [item for item in planned if item["action"] == "DERIVE"]

    if todo and not RUNTIME_TOOL.is_file():
        _fail("RUNTIME_TOOL_MISSING",
              f"{RUNTIME_TOOL.relative_to(ROOT)} is absent; the aspect converter "
              "belongs to the pinned runtime, and this script does not reimplement it")

    out_dir = project / "final" / "variants"
    results: List[Dict[str, Any]] = []
    for item in todo:
        target = out_dir / f"{item['platform']}-{item['width']}x{item['height']}.mp4"
        command = [
            python_executable(), str(RUNTIME_TOOL), "reframe",
            "-i", str(master), "-o", str(target),
            "--ratio", item["ratio"], "--mode", item["mode"],
        ]
        if dry_run:
            results.append({**item, "action": "WOULD_DERIVE", "path":
                            f"project://{target.relative_to(project).as_posix()}",
                            "command": " ".join(command)})
            continue
        out_dir.mkdir(parents=True, exist_ok=True)
        outcome = hidden_run(command, cwd=str(ROOT), timeout=1800)
        if outcome.returncode != 0 or not target.is_file():
            results.append({**item, "action": "FAILED",
                            "error": (outcome.stderr or outcome.stdout or "")[-400:]})
            continue
        produced = ffprobe_meta(target)
        frame = master_frame(produced)
        duration = float((produced.get("format") or {}).get("duration") or 0)
        master_duration = float((meta.get("format") or {}).get("duration") or 0)
        ok = frame == (item["width"], item["height"]) and abs(duration - master_duration) <= 0.25
        results.append({
            **item, "action": "DERIVED" if ok else "WRONG_FRAME",
            "path": f"project://{target.relative_to(project).as_posix()}",
            "sha256": _sha256(target),
            "width": frame[0], "height": frame[1],
            "duration_s": round(duration, 3),
        })
        item["action"] = "DERIVED" if ok else "WRONG_FRAME"

    receipt = {
        "schema": SCHEMA,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project": project.name,
        "account_slug": account.get("slug"),
        "master": {
            "path": f"project://{master.relative_to(project).as_posix()}",
            "sha256": _sha256(master),
            "width": master_size[0], "height": master_size[1],
            "qc_verdicts": grade["verdicts"],
            "qc_receipts": grade["receipts"],
        },
        "tool": {
            "path": ".runtime/easel/skills/shared/scripts/reframe.py",
            "sha256": _sha256(RUNTIME_TOOL) if RUNTIME_TOOL.is_file() else "",
            "note": "the tool file that ran is bound here; whether the runtime is "
                    "trusted is decided by verify_easel_runtime.py, not by this receipt",
        },
        "variants": results,
        "covers": covers,
        "planned": planned,
        "production_ready": False,
    }
    if not dry_run:
        receipts = project / "receipts"
        receipts.mkdir(parents=True, exist_ok=True)
        (receipts / "variants.json").write_text(
            json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Derive per-platform frames from a graded master.")
    parser.add_argument("project", help="project directory")
    parser.add_argument("--video", default="", help="master file under final/ (default easel.mp4)")
    parser.add_argument("--platforms", default="",
                        help="comma-separated platforms to derive (default: the project's/account's)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, write nothing")
    args = parser.parse_args()

    only = [p for p in args.platforms.split(",") if p.strip()] or None
    receipt = derive(Path(args.project), video=args.video, only=only, dry_run=args.dry_run)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 1 if any(v["action"] in ("FAILED", "WRONG_FRAME") for v in receipt["variants"]) else 0


if __name__ == "__main__":
    sys.exit(main())
