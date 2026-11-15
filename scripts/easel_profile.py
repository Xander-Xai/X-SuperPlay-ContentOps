#!/usr/bin/env python3
"""Project the account DNA into an Easel profile (六维画像).

Why this exists
---------------
Easel already has the right extension point for "微调": a profile. Upstream's
own ``profiles/_template/README.md`` maps six files onto the workflow layers,
and ``easel/persona.py`` reads them as the single source of truth for the
CLI, the Web workbench and the skill entry point alike.

The problem is that our account DNA already says everything a profile says,
in a different shape. Two copies of the same rules would drift, and the
drift would be invisible until a rendered frame looked wrong.

So the DNA stays the single source of truth and this script PROJECTS it. A
profile is generated output, not a second document to maintain. Regenerating
it is cheap; that is the point.

What lands where (upstream's own mapping)
------------------------------------------
| file        | DNA source                                          |
|-------------|-----------------------------------------------------|
| identity   | account / description / promise / mission / tagline |
| style      | visual (palette, caption, motion) + narrative pace   |
| audience   | core_audience + audience_layers                      |
| platforms  | platforms / platform_roles / platform_note          |
| preferences| forbidden / non_negotiable / not_doing / evidence     |
| memory     | acceptance_metrics + evidence_ladder (learned rules)  |

The projection includes the actual speech rate, duration and composition
values. They are derived from the DNA and bound by generated-file digests.

Usage
-----
    python scripts/easel_profile.py --list
    python scripts/easel_profile.py --account x-superplay-1024 --print
    python scripts/easel_profile.py --account x-superplay-1024 --write
    python scripts/easel_profile.py --account x-superplay-1024 --write --workbench D:\\Projects\\Easel-Workbench

Exit codes: 0 ok, 4 blocked (no account / no workbench), 2 usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.easel.path_safety import is_linklike as _path_is_linklike  # noqa: E402

ACCOUNTS_DIR = ROOT / "config" / "accounts"
OVERLAY_RECORD = ROOT / "runtime" / "easel-workbench-overlay.json"

#: The six files upstream's template defines, in the order upstream reads them
#: (``easel/persona.py::_FILE_ORDER``). The generated profile must not add or
#: remove files: an unknown file is ignored by upstream, which would make the
#: projection look complete while losing content.
PROFILE_FILES = ("identity.md", "style.md", "audience.md",
                 "platforms.md", "preferences.md", "memory.md")
ACCOUNT_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _validate_slug(slug: str) -> None:
    if not isinstance(slug, str) or not ACCOUNT_SLUG.fullmatch(slug):
        raise ValueError("account slug must contain only lowercase letters, digits and hyphens")


def load_account(slug: str) -> Dict[str, Any]:
    """Read one account DNA. A missing file is an error, not an empty profile:
    a profile with no DNA behind it would look like a designed account."""
    _validate_slug(slug)
    path = ACCOUNTS_DIR / f"{slug}.json"
    if not path.is_file():
        raise FileNotFoundError(f"no account DNA at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"account DNA at {path} is not an object")
    validate_profile_dna(slug, data)
    return data


def _bullets(values: Any, empty: str = "（DNA 未声明）") -> List[str]:
    if isinstance(values, str):
        return [values] if values.strip() else [empty]
    if isinstance(values, list):
        # Skip None explicitly: str(None) is "None", which is truthy and would
        # put a literal "None" in the profile instead of naming the gap.
        out = [str(v).strip() for v in values if v is not None and str(v).strip()]
        return out or [empty]
    if isinstance(values, dict):
        out = [f"{k}: {v}" for k, v in values.items()]
        return out or [empty]
    if values is None:
        return [empty]
    return [str(values)]


def _section(title: str, lines: List[str]) -> str:
    body = "\n".join(f"- {line}" for line in lines)
    return f"## {title}\n\n{body}\n"


def _quote(lines: List[str], quote: str = "> ") -> str:
    return "\n".join(f"{quote}{line}" for line in lines)


def validate_profile_dna(slug: str, dna: Dict[str, Any]) -> None:
    """Require all account facts used by the profile before writing or verifying it."""
    _validate_slug(slug)
    missing = []
    if dna.get("schema") != "contentops.account-dna/v2":
        missing.append("schema=contentops.account-dna/v2")
    if dna.get("slug") != slug:
        missing.append("slug matches selected account")
    for name in ("account", "role", "promise", "mission", "tagline", "core_audience",
                 "platforms", "forbidden", "non_negotiable"):
        if not dna.get(name):
            missing.append(name)
    narrative = dna.get("narrative") if isinstance(dna.get("narrative"), dict) else {}
    for name in ("mode", "opening", "speech_rate_cpm", "target_duration_s", "template", "cta"):
        if not narrative.get(name):
            missing.append(f"narrative.{name}")
    duration = narrative.get("target_duration_s")
    if (not isinstance(duration, list) or len(duration) != 2
            or any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                   for value in duration)
            or duration[0] > duration[1]):
        missing.append("narrative.target_duration_s must be a positive [min, max] pair")
    rate = narrative.get("speech_rate_cpm")
    if type(rate) not in (int, float) or not math.isfinite(rate) or rate <= 0:
        missing.append("narrative.speech_rate_cpm must be positive")
    if (not isinstance(narrative.get("template"), list)
            or not all(isinstance(item, str) and item.strip() for item in narrative["template"])):
        missing.append("narrative.template must be a list of nonempty text")
    visual = dna.get("visual") if isinstance(dna.get("visual"), dict) else {}
    if not visual.get("accent"):
        missing.append("visual.accent")
    composition = visual.get("composition")
    segments = composition.get("segments") if isinstance(composition, dict) else None
    if not isinstance(segments, list) or not segments:
        missing.append("visual.composition.segments")
    elif any(not isinstance(item, dict)
             or not isinstance(item.get("role"), str) or not item["role"].strip()
             or type(item.get("pct")) not in (int, float)
             or not math.isfinite(item["pct"]) or item["pct"] < 0
             for item in segments):
        missing.append("visual.composition.segments must contain roles and nonnegative percentages")
    elif not math.isclose(sum(item["pct"] for item in segments), 100.0, abs_tol=0.01):
        missing.append("visual.composition.segments percentages must total 100")
    caption = visual.get("caption_style")
    if not isinstance(caption, dict) or not all(caption.get(key) for key in
                                                ("font", "size_px", "primary", "highlight")):
        missing.append("visual.caption_style (font, size_px, primary, highlight)")
    motion = visual.get("motion")
    allowed_motion = motion.get("allowed") if isinstance(motion, dict) else None
    if not isinstance(allowed_motion, list) or not allowed_motion:
        missing.append("visual.motion.allowed")
    if missing:
        raise ValueError("account DNA is incomplete for Easel profile: " + ", ".join(missing))


def build_profile(slug: str, dna: Dict[str, Any]) -> Dict[str, str]:
    """Render the six profile files from one DNA.

    This is generated output, not a hand-maintained second source. The profile
    contains actual numeric and narrative values so Easel can use them without
    resolving ContentOps field names; rebuilding from DNA keeps the projection
    current and the snapshot verifier detects stale files.
    """
    narrative = dna.get("narrative") or {}
    visual = dna.get("visual") or {}
    brand = dna.get("brand") or {}
    evidence = dna.get("evidence") or {}
    ladder = dna.get("evidence_ladder") or {}

    # --- identity ------------------------------------------------------
    # NOTE: `title` and `description` are deliberately NOT projected. They
    # describe one episode ("Easel 实测：能跑，但 Web 工作台六项没过"), not the
    # account. A profile is permanent; an episode title projected into it would
    # pin the account to whichever video happened to be written last.
    identity = f"# 身份定位\n\n"
    identity += _section("我是谁", _bullets([
        dna.get("account"),
        f"角色：{dna.get('role')}" if dna.get("role") else None,
    ]))
    identity += _section("我承诺什么", _bullets([dna.get("promise")]))
    identity += _section("我做什么", _bullets([dna.get("mission")]))
    identity += _section("一句话", _bullets([dna.get("tagline")]))
    benchmarks = dna.get("benchmarks") if isinstance(dna.get("benchmarks"), dict) else {}
    benchmark_lines = []
    priority = benchmarks.get("priority")
    # Preserve the existing, verified snapshot bytes when its historic wording
    # accurately describes the current DNA. Other counts must not be invented.
    if (isinstance(priority, list) and len(priority) == 3 and benchmarks.get("primary")
            and any(isinstance(row, dict) and row.get("account") == benchmarks["primary"]
                    for row in priority)):
        benchmark_lines.append(f"对标优先级：{benchmarks['primary']} 等三个账号（见 DNA benchmarks.priority）")
    elif isinstance(priority, list):
        if benchmarks.get("primary"):
            benchmark_lines.append(f"主要对标：{benchmarks['primary']}")
        for row in priority:
            if isinstance(row, dict) and row.get("account"):
                label = str(row["account"])
                if row.get("rank") is not None:
                    label = f"{row['rank']}. {label}"
                if row.get("adopt"):
                    label += f"：{row['adopt']}"
                benchmark_lines.append(label)
    elif benchmarks.get("primary"):
        benchmark_lines.append(f"主要对标：{benchmarks['primary']}")
    identity += _section("差异化", _bullets([*benchmark_lines, dna.get("decision_question")]))

    # --- style ---------------------------------------------------------
    style = "# 内容风格\n\n"
    style += _section("语气", _bullets([
        f"账号语气与叙事模式：{narrative.get('mode', '未声明')}",
        f"开头结构：{narrative.get('opening', '未声明')}",
    ]))
    duration = narrative.get("target_duration_s")
    duration_text = (f"{duration[0]}–{duration[1]} 秒"
                     if isinstance(duration, list) and len(duration) == 2
                     else "未声明")
    template = narrative.get("template")
    style += _section("内容节奏", _bullets([
        f"目标时长：{duration_text}",
        f"目标语速：{narrative.get('speech_rate_cpm', '未声明')} 字/分钟",
        f"节奏档位：{narrative.get('pace', '未声明')}",
        "结构模板：" + " → ".join(template) if isinstance(template, list)
        else "结构模板：未声明",
    ]))
    composition = (visual.get("composition") or {}).get("segments")
    composition_lines = (
        [f"{segment.get('role')}：{segment.get('pct')}%"
         for segment in composition if isinstance(segment, dict)]
        if isinstance(composition, list) else []
    )
    caption = visual.get("caption_style") or {}
    safe_zone = caption.get("safe_zone") or {}
    cover = visual.get("cover") or {}
    style += _section("视觉风格", _bullets([
        f"品牌强调色：{visual.get('accent', '未声明')}",
        (f"字幕：{caption.get('font', '未声明')}，{caption.get('size_px', '未声明')} px，"
         f"主色 {caption.get('primary', '未声明')}，强调色 {caption.get('highlight', '未声明')}，"
         f"每行最多 {caption.get('max_chars_per_line', '未声明')} 字；"
         f"底部安全区 {safe_zone.get('margin_v_px', '未声明')} px，"
         f"侧边距 {safe_zone.get('side_margin_ratio', '未声明')}") ,
        *composition_lines,
        "动效白名单：" + ", ".join((visual.get("motion") or {}).get("allowed", [])),
        f"封面构图：{cover.get('composition', '未声明')}；标题 {cover.get('title_lines', '未声明')} 行",
    ]))
    style += _section("标志性元素", _bullets([
        f"栏目与固定结构：{dna.get('content_pillars', '未声明')}",
        f"品牌底线：{dna.get('non_negotiable', '未声明')}",
    ]))

    # --- audience ------------------------------------------------------
    audience = "# 核心受众\n\n"
    audience += _section("核心人群", _bullets(dna.get("core_audience")))
    layers = dna.get("audience_layers") or {}
    if isinstance(layers, dict) and layers:
        audience += _section("分层", [
            f"{name}：{value}" for name, value in layers.items()
        ])
    audience += _section("互动信号怎么读", _bullets([
        "信号强度顺序：浏览 < 点赞收藏 < 评论提问 < 私信咨询 < 付费",
        "低阶信号不能推断高阶结论",
    ]))

    # --- platforms -----------------------------------------------------
    platforms = "# 各平台账号与规则\n\n"
    roles = dna.get("platform_roles") or {}
    if isinstance(roles, dict) and roles:
        platforms += _section("平台角色", [
            f"{name}：{value}" for name, value in roles.items()
        ])
    platforms += _section("平台清单", _bullets(dna.get("platforms")))
    platforms += _section("平台说明", _bullets(dna.get("platform_note")))
    platforms += _section("本账号明确不做", _bullets(
        dna.get("excluded") or dna.get("not_doing")))

    # --- preferences ---------------------------------------------------
    preferences = "# 偏好与红线\n\n"
    preferences += _section("要做的", _bullets([
        f"证据模式见 DNA evidence（当前 {evidence.get('mode', '未声明')}）",
        f"证据阶梯见 DNA evidence_ladder",
        f"叙事模板见 DNA narrative.template",
    ]))
    preferences += _section("不做的", _bullets(dna.get("forbidden")))
    preferences += _section("不可违反的底线", _bullets(dna.get("non_negotiable")))
    if isinstance(ladder, dict) and ladder:
        preferences += _section("证据阶梯红线", [
            f"{name}：{value}" for name, value in ladder.items()
            if not isinstance(value, (dict, list))
        ])
    preferences += _section("CTA 锁定话术", _bullets([
        f"{narrative.get('cta')}（见 DNA narrative.cta）",
    ]))

    # --- memory --------------------------------------------------------
    # The pitfalls below are the brand-level ones every account shares. The
    # evidence rules and acceptance metrics differ per account, so they are
    # projected from the DNA rather than hardcoded — otherwise the two
    # accounts would get byte-identical memory files, which is the same as
    # giving them no account-specific memory at all.
    metrics = dna.get("acceptance_metrics") if isinstance(dna.get("acceptance_metrics"), dict) else {}
    memory = "# 学到了什么\n\n"
    memory += _section("先看哪些指标", _bullets(metrics.get("first_stage_priority")))
    memory += _section("验收口径", _bullets([
        f"{m.get('id')}：{m.get('how')}" for m in (metrics.get("metrics") or [])
        if isinstance(m, dict) and m.get("id")
    ] or None))
    memory += _section(f"证据规则（{evidence.get('mode', '未声明')}）", _bullets(
        evidence.get("rules")))
    memory += _section("这个账号禁止的证据做法", _bullets(evidence.get("forbidden")))
    memory += _section("踩过的坑", _bullets([
        "把代码写完等同于上线可用 —— 禁止，必须标注评估边界、风险与限制",
        "用生成内容冒充实测证据 —— 禁止",
        "没有真实 URL 不得宣称发布成功",
        "低阶信号被拔高为高阶结论 —— 禁止",
    ]))

    return {
        "identity.md": identity,
        "style.md": style,
        "audience.md": audience,
        "platforms.md": platforms,
        "preferences.md": preferences,
        "memory.md": memory,
    }


def _profile_directory(workbench: Path, slug: str, *, create: bool) -> Path:
    _validate_slug(slug)
    root = Path(workbench)
    if _path_is_linklike(root):
        raise ValueError("workbench root may not be a symlink or junction")
    root = root.resolve(strict=True)
    profiles = root / "profiles"
    if _path_is_linklike(profiles):
        raise ValueError("profiles directory may not be a symlink or junction")
    if create:
        profiles.mkdir(exist_ok=True)
    target = profiles / slug
    if _path_is_linklike(target):
        raise ValueError("account profile directory may not be a symlink or junction")
    if create:
        target.mkdir(exist_ok=True)
    if not target.exists():
        return target
    resolved_profiles = profiles.resolve(strict=True)
    resolved_target = target.resolve(strict=True)
    if resolved_target.parent != resolved_profiles:
        raise ValueError("account profile resolves outside the workbench profiles directory")
    return resolved_target


def write_profile(slug: str, files: Dict[str, str], workbench: Path) -> List[Path]:
    """Write the six files into ``<workbench>/profiles/<slug>/``.

    The target directory is inside the workbench repository, which is the
    overlay layer the overlay record names. Writing outside it would create a
    file the verifier reports as an unexpected extra.
    """
    root = Path(workbench).resolve(strict=True)
    if (root.name.casefold() == "easel" and root.parent.name.casefold() == ".runtime") or root == (ROOT / "Easel").resolve():
        raise ValueError("production runtime and legacy Easel checkout are read-only")
    try:
        overlay = json.loads(OVERLAY_RECORD.read_text(encoding="utf-8"))
        previous = (overlay.get("previous_instance_snapshot") or {}).get("path")
        if previous and root == Path(previous).resolve():
            raise ValueError("original workbench instance is read-only")
    except (OSError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise ValueError("workbench protection record is unavailable") from exc
    target = _profile_directory(workbench, slug, create=True)
    if set(files) != set(PROFILE_FILES):
        raise ValueError("profile must contain exactly the six declared files")
    # Never replace locally tuned content. Identical generated files are safe to
    # reuse; a changed file requires a new isolated rebuild and explicit review.
    for name in PROFILE_FILES:
        path = target / name
        if _path_is_linklike(path):
            raise ValueError(f"profile file may not be a symlink or junction: {name}")
        if path.exists() and (not path.is_file() or path.read_bytes() != files[name].encode("utf-8")):
            raise ValueError(f"profile file already exists with different content: {name}")
    written = []
    for name in PROFILE_FILES:
        path = target / name
        if not path.exists():
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(files[name])
        written.append(path)
    return written


def verify_profile(slug: str, dna: Dict[str, Any], workbench: Path) -> Dict[str, Any]:
    """Reject stale, linked or undeclared profile content against account DNA."""
    validate_profile_dna(slug, dna)
    expected = build_profile(slug, dna)
    try:
        target = _profile_directory(workbench, slug, create=False)
    except (OSError, ValueError) as exc:
        return {"status": "BLOCKED", "account": slug,
                "reason": f"unsafe profile path: {exc}"}
    unsafe = sorted(name for name in PROFILE_FILES if _path_is_linklike(target / name))
    missing = sorted(name for name in PROFILE_FILES
                     if name not in unsafe and not (target / name).is_file())
    try:
        # Upstream appends other Markdown files to the profile context. Reject
        # every unplanned directory entry, including links and subdirectories,
        # so a successful check describes the entire six-file snapshot.
        extra = sorted(path.name for path in target.iterdir()
                       if path.name not in PROFILE_FILES) if target.exists() else []
    except OSError:
        return {"status": "BLOCKED", "account": slug,
                "reason": "profile directory could not be listed"}
    actual_hashes = {}
    mismatched = []
    for name in PROFILE_FILES:
        if name in unsafe or name in missing:
            continue
        try:
            content = (target / name).read_bytes()
        except OSError:
            unsafe.append(name)
            continue
        actual_hashes[name] = hashlib.sha256(content).hexdigest()
        try:
            matches = content.decode("utf-8") == expected[name]
        except UnicodeDecodeError:
            matches = False
        if not matches:
            mismatched.append(name)
    canonical_dna = json.dumps(dna, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
    return {
        "status": "VERIFIED" if not missing and not mismatched and not unsafe and not extra else "STALE",
        "account": slug,
        "dna_sha256": hashlib.sha256(canonical_dna).hexdigest(),
        "profile_sha256": {
            name: hashlib.sha256(expected[name].encode("utf-8")).hexdigest()
            for name in PROFILE_FILES
        },
        "actual_profile_sha256": actual_hashes,
        "missing": missing,
        "mismatched": mismatched,
        "unsafe": unsafe,
        "extra": extra,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="list the account slugs")
    p.add_argument("--account", help="account slug, e.g. x-superplay-1024")
    p.add_argument("--print", dest="print_only", action="store_true",
                   help="print the profile instead of writing it")
    p.add_argument("--write", action="store_true",
                   help="write the profile into the workbench instance")
    p.add_argument("--verify", action="store_true",
                   help="reject missing or stale files against current account DNA")
    p.add_argument("--workbench", help="workbench path (default: from the overlay record)")
    args = p.parse_args()

    if args.list:
        for path in sorted(ACCOUNTS_DIR.glob("*.json")):
            print(path.stem)
        return 0

    if not args.account:
        p.error("one of --list or --account is required")

    try:
        dna = load_account(args.account)
    except (FileNotFoundError, ValueError) as e:
        print(f"BLOCKED: {e}", file=sys.stderr)
        return 4

    files = build_profile(args.account, dna)

    if args.print_only:
        for name in PROFILE_FILES:
            print(f"===== {name} =====")
            print(files[name])
        return 0

    if args.write and args.verify:
        p.error("--write and --verify are mutually exclusive")
    if not args.write and not args.verify:
        p.error("one of --print, --write or --verify is required")

    workbench = Path(args.workbench) if args.workbench else None
    if workbench is None:
        try:
            import verify_easel_runtime
            record = verify_easel_runtime.load_overlay(OVERLAY_RECORD)
            workbench = verify_easel_runtime.workbench_path(record)
        except (OSError, ValueError, TypeError) as exc:
            print(f"BLOCKED: invalid workbench configuration: {exc}", file=sys.stderr)
            return 4
    if not workbench.is_absolute() or not workbench.is_dir():
        print(f"BLOCKED: no workbench instance at {workbench}", file=sys.stderr)
        return 4

    if args.verify:
        result = verify_profile(args.account, dna, workbench)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["status"] == "VERIFIED" else 1

    try:
        written = write_profile(args.account, files, workbench)
    except (OSError, ValueError) as exc:
        print(f"BLOCKED: profile not written: {exc}", file=sys.stderr)
        return 4
    print(json.dumps({
        "account": args.account,
        "workbench": str(workbench),
        "written": [str(p) for p in written],
        "verification": verify_profile(args.account, dna, workbench),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
