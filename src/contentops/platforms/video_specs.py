"""Per-platform video delivery specifications.

Loads ``config/platforms/video-platforms.yaml`` and turns it into deterministic
shaping and validation rules for the VIDEO line. Everything here is offline: no
network, no credential, no ffmpeg, no uploader. "Which platforms exist and what
shape each one wants" therefore has exactly one owner, mirroring
``graphic_specs.py`` on the GRAPHIC_TEXT line.

Accounting model
----------------
Every limit carries a ``*_basis`` field in the YAML:

* ``official``    - the platform states it in its own docs
* ``adapter_cli`` - the uploader's CLI contract demands it
* ``dna``         - this project's account DNA states it
* ``project``     - this repository's convention

A ``project`` basis is a shaping hint, never a platform SLA. This module makes
that distinction visible in every issue it returns so a warning is never read as
"the platform will accept this".

Status boundary
---------------
Nothing here publishes, uploads, upgrades a registry row or claims a platform
draft. A spec row may describe a platform that the registry still marks
``PLANNED``; the two are allowed to disagree because one is a claim about shape
and the other is a claim about evidence.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "ISSUE_BLOCKER",
    "ISSUE_WARNING",
    "SCHEMA",
    "SpecError",
    "capability_matrix",
    "check",
    "dna_limits",
    "is_registry_row",
    "load_specs",
    "platform_ids",
    "requirements",
    "rules",
    "spec",
    "spec_path",
    "tag_tokens",
    "thumbnails",
    "uploader",
]

SCHEMA = "contentops.video-platforms/v1"
SPEC_RELATIVE = Path("config") / "platforms" / "video-platforms.yaml"

ISSUE_BLOCKER = "blocker"
ISSUE_WARNING = "warning"

TAG_STYLES = ("space_hash", "comma")

REQUIRED_FIELDS = (
    "platform_id",
    "display_name",
    "registry_row",
    "pipeline",
    "native_format",
    "aspect_required",
    "uploader",
)


class SpecError(RuntimeError):
    """The video spec file is missing, malformed or internally inconsistent."""


def _project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "config" / "registry" / "platforms.json").is_file():
            return parent
    return here.parents[3]


def spec_path() -> Path:
    return _project_root() / SPEC_RELATIVE


@lru_cache(maxsize=1)
def load_specs() -> dict[str, Any]:
    """Read and sanity-check the video spec once per process."""
    try:
        import yaml  # noqa: PLC0415 - optional at import time, required at load
    except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
        raise SpecError(
            "PyYAML 未安装，无法读取视频平台规格表。请使用项目 venv 运行"
            "（.runtime/gzh-wf-venv/Scripts/python.exe）。"
        ) from exc

    path = spec_path()
    if not path.is_file():
        raise SpecError(f"视频平台规格表缺失：{path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SpecError("视频平台规格表根节点必须是映射")
    if raw.get("schema") != SCHEMA:
        raise SpecError(f"视频平台规格表 schema 必须是 {SCHEMA}，实际 {raw.get('schema')!r}")

    rows = raw.get("platforms")
    if not isinstance(rows, list) or not rows:
        raise SpecError("视频平台规格表 platforms 必须是非空列表")

    seen: set[str] = set()
    platforms: dict[str, dict[str, Any]] = {}
    for row in rows:
        for field in REQUIRED_FIELDS:
            if field not in row:
                raise SpecError(f"平台记录缺少字段 {field}：{row.get('platform_id')!r}")
        pid = str(row["platform_id"])
        if pid in seen:
            raise SpecError(f"平台记录重复：{pid}")
        seen.add(pid)

        up = row["uploader"]
        if not isinstance(up, dict) or not {"tool", "platform", "action"} <= set(up):
            raise SpecError(f"{pid} 的 uploader 必须声明 tool/platform/action")

        style = str(row.get("tag_style") or "")
        if style not in TAG_STYLES:
            raise SpecError(f"{pid} 的 tag_style 只能是 {'/'.join(TAG_STYLES)}，实际 {style!r}")

        for thumb in row.get("thumbnails") or []:
            if not thumb.get("flag") or not thumb.get("ratio"):
                raise SpecError(f"{pid} 的 thumbnail 缺少 flag/ratio")

        platforms[pid] = row

    return {
        "schema": raw["schema"],
        "limits_policy": raw.get("limits_policy") or {},
        "dna_policy": raw.get("dna_policy") or {},
        "platforms": platforms,
        "excluded": raw.get("excluded") or [],
    }


def platform_ids(*, registry_rows_only: bool = False) -> tuple[str, ...]:
    rows = load_specs()["platforms"]
    if registry_rows_only:
        return tuple(pid for pid, row in rows.items() if row["registry_row"])
    return tuple(rows)


def spec(platform_id: str) -> dict[str, Any]:
    rows = load_specs()["platforms"]
    if platform_id not in rows:
        raise KeyError(platform_id)
    return rows[platform_id]


def is_registry_row(platform_id: str) -> bool:
    return bool(spec(platform_id)["registry_row"])


def uploader(platform_id: str) -> dict[str, Any]:
    """The external uploader contract for one platform.

    Returned as data. This module never launches it; ``video_deliver.py`` builds
    an argv and hands it across a process boundary.
    """
    return dict(spec(platform_id)["uploader"])


def thumbnails(platform_id: str) -> list[dict[str, Any]]:
    return [dict(t) for t in (spec(platform_id).get("thumbnails") or [])]


def requirements(platform_id: str) -> list[str]:
    """Every external precondition named by the spec, deduplicated."""
    row = spec(platform_id)
    out: list[str] = []
    for arg in row.get("required_args") or []:
        token = f"arg:{arg.get('flag')}"
        if token not in out:
            out.append(token)
    for thumb in thumbnails(platform_id):
        if thumb.get("required"):
            token = f"thumbnail:{thumb['ratio']}"
            if token not in out:
                out.append(token)
    if row["uploader"].get("cookie_glob"):
        if "uploader_login" not in out:
            out.append("uploader_login")
    return out


def rules(platform_id: str) -> dict[str, Any]:
    """Normalised shaping rules, with defaults filled in."""
    row = spec(platform_id)
    return {
        "display_name": row["display_name"],
        "native_format": row["native_format"],
        "aspect_required": row["aspect_required"],
        "max_duration_s": int(row.get("max_duration_s") or 0),
        "max_file_mb": int(row.get("max_file_mb") or 0),
        "title_max_hard": int(row.get("title_max_hard") or 0),
        "title_max_soft": int(row.get("title_max_soft") or 0),
        "desc_max_hard": int(row.get("desc_max_hard") or 0),
        "tags_min": int(row.get("tags_min") or 0),
        "tags_max": int(row.get("tags_max") or 0),
        "tag_style": str(row.get("tag_style") or ""),
        "hook_max_s": int(row.get("hook_max_s") or 0),
        "supports_short_title": bool(row.get("supports_short_title")),
        "supports_draft": bool(row.get("supports_draft")),
    }


def dna_limits(dna: dict[str, Any]) -> dict[str, int]:
    """Account-level limits that the platform spec deliberately does not own."""
    retention = dna.get("retention") or {}
    return {
        "max_hook_s": int(retention.get("max_hook_s") or 0),
        "max_static_hold_s": int(retention.get("max_static_hold_s") or 0),
    }


def normalize_tags(tags: list[str]) -> list[str]:
    """Strip a leading ``#`` and surrounding blanks; drop empties, keep order."""
    out: list[str] = []
    for raw in tags or []:
        cleaned = str(raw).strip().lstrip("#").strip()
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def tag_tokens(platform_id: str, tags: list[str]) -> str:
    """Render tags in the format this platform's **uploader** accepts.

    ``comma``      - ``a,b``; what the pinned uploader's ``parse_tags`` splits on
                     (it strips a leading ``#`` itself, so adding one produces a
                     tag whose name starts with a space)
    ``space_hash`` - ``#a #b``; the shape a human types into the app UI

    Measured against ``sau <platform> upload-video --help`` and
    ``sau_commands/arguments.py::parse_tags``. Every row currently uses
    ``comma`` because every row goes through that uploader; ``space_hash`` stays
    available for a future API path that wants the display form.

    Percent-encoding is not applied: the argv is passed as a list, so the shell
    never sees the string and a ``#`` cannot become a comment.
    """
    clean = normalize_tags(tags)
    style = str(spec(platform_id).get("tag_style") or "")
    if style == "comma":
        return ",".join(clean)
    return " ".join(f"#{t}" for t in clean)


def tag_display(platform_id: str, tags: list[str]) -> str:
    """The string a human would paste into the platform's own editor."""
    return " ".join(f"#{t}" for t in normalize_tags(tags))


def _issue(code: str, severity: str, field: str, detail: str, basis: str = "") -> dict[str, str]:
    payload = {"code": code, "severity": severity, "field": field, "detail": detail}
    if basis:
        payload["basis"] = basis
    return payload


def check(
    platform_id: str,
    *,
    title: str,
    desc: str,
    tags: list[str],
    duration_s: float | None = None,
    size_mb: float | None = None,
    aspect: str | None = None,
    hook_s: float | None = None,
    present_thumbnails: dict[str, bool] | None = None,
    supplied_args: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    """Validate one shaped package against one platform.

    Returns issues, never raises for content problems: a blocker is the recorded
    answer, so an operator can see which limit was exceeded and by how much.
    Structural errors (unknown platform, malformed spec) still raise.
    """
    row = spec(platform_id)
    r = rules(platform_id)
    issues: list[dict[str, str]] = []

    title_len = len(title or "")
    if r["title_max_hard"] and title_len > r["title_max_hard"]:
        issues.append(_issue(
            "TITLE_OVER_HARD_LIMIT", ISSUE_BLOCKER, "title",
            f"{title_len} > {r['title_max_hard']} 字符", str(row.get("title_max_hard_basis") or ""),
        ))
    elif r["title_max_soft"] and title_len > r["title_max_soft"]:
        issues.append(_issue(
            "TITLE_OVER_SOFT_LIMIT", ISSUE_WARNING, "title",
            f"{title_len} > {r['title_max_soft']} 字符（约定值，不是平台硬限）",
            str(row.get("title_max_soft_basis") or ""),
        ))

    desc_len = len(desc or "")
    if r["desc_max_hard"] and desc_len > r["desc_max_hard"]:
        issues.append(_issue(
            "DESC_OVER_HARD_LIMIT", ISSUE_BLOCKER, "desc",
            f"{desc_len} > {r['desc_max_hard']} 字符", str(row.get("desc_max_hard_basis") or ""),
        ))

    tag_count = len(normalize_tags(tags))
    if r["tags_min"] and tag_count < r["tags_min"]:
        issues.append(_issue(
            "TAGS_BELOW_MINIMUM", ISSUE_WARNING, "tags",
            f"{tag_count} < {r['tags_min']} 个", str(row.get("tags_basis") or ""),
        ))
    if r["tags_max"] and tag_count > r["tags_max"]:
        issues.append(_issue(
            "TAGS_OVER_MAXIMUM", ISSUE_BLOCKER, "tags",
            f"{tag_count} > {r['tags_max']} 个", str(row.get("tags_basis") or ""),
        ))

    if duration_s is not None and r["max_duration_s"] and float(duration_s) > r["max_duration_s"]:
        issues.append(_issue(
            "DURATION_OVER_LIMIT", ISSUE_BLOCKER, "duration",
            f"{float(duration_s):.1f}s > {r['max_duration_s']}s", str(row.get("max_duration_basis") or ""),
        ))

    if size_mb is not None and r["max_file_mb"] and float(size_mb) > r["max_file_mb"]:
        issues.append(_issue(
            "FILE_SIZE_OVER_LIMIT", ISSUE_BLOCKER, "file",
            f"{float(size_mb):.1f}MB > {r['max_file_mb']}MB", str(row.get("max_file_mb_basis") or ""),
        ))

    if aspect and str(aspect) != r["aspect_required"]:
        issues.append(_issue(
            "ASPECT_MISMATCH", ISSUE_BLOCKER, "aspect",
            f"{aspect} != {r['aspect_required']}；本平台线只接受竖版成片",
            str(row.get("aspect_basis") or ""),
        ))

    if hook_s is not None and r["hook_max_s"] and float(hook_s) > r["hook_max_s"]:
        issues.append(_issue(
            "HOOK_MISSES_DEADLINE", ISSUE_WARNING, "hook",
            f"钩子落在 {float(hook_s):.1f}s，超过 {r['hook_max_s']}s",
            str(row.get("hook_basis") or ""),
        ))

    present = present_thumbnails or {}
    for thumb in thumbnails(platform_id):
        if not thumb.get("required"):
            continue
        if not present.get(thumb["ratio"]):
            issues.append(_issue(
                "THUMBNAIL_MISSING", ISSUE_BLOCKER, thumb["flag"],
                f"{thumb['ratio']} 缩略图缺失（上传器要求必填）", str(thumb.get("basis") or ""),
            ))

    supplied = supplied_args or {}
    for arg in row.get("required_args") or []:
        value = supplied.get(arg["field"])
        if not value:
            issues.append(_issue(
                "REQUIRED_ARG_MISSING", ISSUE_BLOCKER, str(arg["field"]),
                f"{arg['flag']} 未提供（{arg.get('resolution') or 'required'}）",
                str(arg.get("basis") or ""),
            ))

    return issues


def worst_severity(issues: list[dict[str, str]]) -> str:
    if any(i["severity"] == ISSUE_BLOCKER for i in issues):
        return ISSUE_BLOCKER
    if issues:
        return ISSUE_WARNING
    return "ok"


def capability_matrix() -> list[dict[str, Any]]:
    """One row per platform: what it accepts and through which uploader."""
    out: list[dict[str, Any]] = []
    for pid in platform_ids():
        r = rules(pid)
        up = uploader(pid)
        out.append({
            "platform_id": pid,
            "display_name": r["display_name"],
            "registry_row": is_registry_row(pid),
            "aspect": r["aspect_required"],
            "title_hard": r["title_max_hard"],
            "tags": f"{r['tags_min']}-{r['tags_max']}",
            "tag_style": r["tag_style"],
            "max_duration_s": r["max_duration_s"],
            "thumbnail_required": [t["ratio"] for t in thumbnails(pid) if t.get("required")],
            "uploader": f"{up['tool']}:{up['platform']}:{up['action']}",
            "requirements": requirements(pid),
        })
    return out
