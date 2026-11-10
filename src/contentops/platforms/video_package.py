"""Turn one finished film into per-platform delivery packages.

Why this exists
---------------
The VIDEO line ended every run with a single ``final/<slug>.mp4``. Seven
platforms accept that exact file, and each one still wanted a different title
length, a different tag syntax, a different thumbnail ratio and a different
uploader argument set. Every hand-off was therefore a human re-typing the same
description into a browser form and guessing the rules.

This module answers one question per platform: *what exactly would be handed
over, and what is wrong with it?* It is pure: it takes a media probe and an
account DNA, returns data. No ffmpeg, no uploader, no network, no writes.

Account DNA is the input, not decoration
----------------------------------------
``title`` / ``description`` / ``hashtags`` / ``platform_roles[*].cta`` /
``retention`` are read from the DNA, so a package carries the account's own voice
instead of a generic template. ``platform_note`` is free prose and is copied into
the package for the operator to read; it is deliberately **not** parsed into
rules, because pretending to understand prose is how silent drift starts.

Honesty rules
-------------
* A title that has to be shortened records ``title_original`` and an explicit
  ``TITLE_TRUNCATED`` issue. Nothing is silently reworded.
* A required uploader argument that nobody supplied is a blocker, not a default.
  Bilibili's ``--tid`` is the live example: inventing one files the video under
  an unrelated section.
* ``publish_authorized`` is always false and ``production_ready`` is always
  false. This module packages; it never authorises and never publishes.
"""

from __future__ import annotations

from typing import Any

from . import video_specs

__all__ = [
    "ALIASES",
    "PACKAGE_SCHEMA",
    "STATE_BLOCKED",
    "STATE_READY",
    "build",
    "canonical_platform",
    "shape_metadata",
    "targets",
]

PACKAGE_SCHEMA = "contentops.video-package/v1"

STATE_READY = "READY_FOR_HANDOFF"
STATE_BLOCKED = "BLOCKED"

#: Account DNA names platforms the way a founder talks, not the way the spec
#: file keys them. Xiaohongshu is one platform with two pipelines; the VIDEO line
#: only ever means its video side.
ALIASES = {
    "xiaohongshu": "xiaohongshu_video",
    "xhs": "xiaohongshu_video",
    "wechat_channels": "shipinhao",
    "video_account": "shipinhao",
    "b站": "bilibili",
    "抖音": "douyin",
    "快手": "kuaishou",
    "视频号": "shipinhao",
    "小红书": "xiaohongshu_video",
}


def canonical_platform(name: str) -> str | None:
    """Map a DNA platform name onto a spec key, or ``None`` if not video-shaped."""
    cleaned = str(name or "").strip()
    if not cleaned:
        return None
    candidate = ALIASES.get(cleaned, cleaned)
    if candidate in video_specs.platform_ids():
        return candidate
    return None


def targets(dna: dict[str, Any], *, include_derived: bool = True) -> list[str]:
    """Which video platforms this account actually publishes to, in DNA order.

    Primary ``platforms`` first, then ``derived_platforms``. Anything that is not
    a video platform (``gzh``, ``zhihu``, ``csdn`` ...) is skipped rather than
    forced into a video package, because a text platform has its own line.
    """
    ordered: list[str] = []
    sources: list[str] = list(dna.get("platforms") or [])
    if include_derived:
        sources.extend(dna.get("derived_platforms") or [])
    for name in sources:
        pid = canonical_platform(name)
        if pid and pid not in ordered:
            ordered.append(pid)
    return ordered


def _first_sentence(text: str, budget: int) -> str:
    if len(text) <= budget:
        return text
    head = text[:budget]
    for mark in ("。", "！", "？", "；", ".", "!", "?", ";"):
        cut = head.rfind(mark)
        if cut >= budget // 2:
            return head[: cut + 1]
    return head


def _shorten(text: str, budget: int) -> str:
    """Cut to a budget without inventing words; caller records the truncation."""
    if budget <= 0 or len(text) <= budget:
        return text
    if budget == 1:
        return "…"
    return text[: budget - 1].rstrip("，、,· ") + "…"


def shape_metadata(
    platform_id: str,
    dna: dict[str, Any],
    *,
    fallback_title: str = "",
    hook_s: float | None = None,
) -> dict[str, Any]:
    """Shape the account's own words into one platform's field set."""
    r = video_specs.rules(platform_id)
    source_title = str(dna.get("title") or fallback_title or "").strip()
    source_desc = str(dna.get("description") or "").strip()
    tags = video_specs.normalize_tags(list(dna.get("hashtags") or []))

    roles = dna.get("platform_roles") or {}
    role_key = video_specs.spec(platform_id).get("strategy_platform") or platform_id
    role = roles.get(role_key) or roles.get(platform_id) or {}
    cta = str((role or {}).get("cta") or "").strip()

    issues: list[dict[str, Any]] = []

    title = source_title
    if r["title_max_hard"] and len(source_title) > r["title_max_hard"]:
        title = _shorten(source_title, r["title_max_hard"])
        issues.append({
            "code": "TITLE_TRUNCATED",
            "severity": video_specs.ISSUE_WARNING,
            "field": "title",
            "detail": f"{len(source_title)} -> {len(title)} 字符，原文保留在 title_original",
        })

    desc = source_desc
    if cta and cta not in desc:
        desc = f"{desc}\n\n{cta}".strip() if desc else cta
    if r["desc_max_hard"] and len(desc) > r["desc_max_hard"]:
        desc = _first_sentence(desc, r["desc_max_hard"])
        issues.append({
            "code": "DESC_TRUNCATED",
            "severity": video_specs.ISSUE_WARNING,
            "field": "desc",
            "detail": f"按整句收敛到 {len(desc)} 字符（上限 {r['desc_max_hard']}）",
        })

    dropped: list[str] = []
    if r["tags_max"] and len(tags) > r["tags_max"]:
        dropped = tags[r["tags_max"]:][:]
        tags = tags[: r["tags_max"]]
        issues.append({
            "code": "TAGS_DROPPED",
            "severity": video_specs.ISSUE_WARNING,
            "field": "tags",
            "detail": f"超出 {r['tags_max']} 个上限，已丢弃：{'、'.join(dropped)}",
        })

    shaped = {
        "platform_id": platform_id,
        "display_name": r["display_name"],
        "title": title,
        "title_original": source_title if title != source_title else "",
        "desc": desc,
        "tags": tags,
        "tags_dropped": dropped,
        "tags_rendered": video_specs.tag_tokens(platform_id, tags),
        "tags_display": video_specs.tag_display(platform_id, tags),
        "cta": cta,
        "dna_role": str((role or {}).get("role") or ""),
        "dna_note": str(video_specs.spec(platform_id).get("note") or "").strip(),
        "issues": issues,
    }
    return shaped


def build(
    *,
    project_id: str,
    account: dict[str, Any],
    media: dict[str, Any],
    thumbnails: dict[str, str] | None = None,
    supplied_args: dict[str, str] | None = None,
    platforms: list[str] | None = None,
    hook_s: float | None = None,
) -> dict[str, Any]:
    """Assemble the full per-platform package from a probe + DNA.

    ``media`` must carry ``duration_s``, ``width``, ``height``, ``size_bytes`` and
    ``sha256`` as measured by the caller, so this function stays pure and its
    output stays auditable.
    """
    dna = account or {}
    present_thumbs = {k: True for k, v in (thumbnails or {}).items() if v}
    chosen = platforms or targets(dna)
    if not chosen:
        return {
            "schema": PACKAGE_SCHEMA,
            "project": project_id,
            "account": str(dna.get("slug") or ""),
            "state": STATE_BLOCKED,
            "publish_authorized": False,
            "production_ready": False,
            "blockers": ["NO_VIDEO_PLATFORM_DECLARED: 账号 DNA 没有声明任何视频平台"],
            "platforms": [],
        }

    duration = float(media.get("duration_s") or 0.0)
    width = int(media.get("width") or 0)
    height = int(media.get("height") or 0)
    size_mb = round(int(media.get("size_bytes") or 0) / (1024 * 1024), 2)
    aspect = ""
    if width and height:
        aspect = "9:16" if height > width else ("16:9" if width > height else "1:1")

    entries: list[dict[str, Any]] = []
    blockers: list[str] = []

    for pid in chosen:
        shaped = shape_metadata(pid, dna, hook_s=hook_s)
        issues = list(shaped["issues"])
        issues.extend(video_specs.check(
            pid,
            title=shaped["title"],
            desc=shaped["desc"],
            tags=shaped["tags"],
            duration_s=duration,
            size_mb=size_mb,
            aspect=aspect,
            hook_s=hook_s,
            present_thumbnails=present_thumbs,
            supplied_args=supplied_args,
        ))
        blocked = [i for i in issues if i["severity"] == video_specs.ISSUE_BLOCKER]
        if blocked:
            blockers.append(f"{pid}: " + "; ".join(i["code"] for i in blocked))
        entries.append({
            "platform_id": pid,
            "display_name": shaped["display_name"],
            "uploader": video_specs.uploader(pid),
            "metadata": {
                "title": shaped["title"],
                "title_original": shaped["title_original"],
                "desc": shaped["desc"],
                "tags": shaped["tags"],
                "tags_rendered": shaped["tags_rendered"],
                "tags_display": shaped["tags_display"],
                "cta": shaped["cta"],
                "dna_role": shaped["dna_role"],
            },
            "requirements": video_specs.requirements(pid),
            "issues": issues,
            "state": STATE_BLOCKED if blocked else STATE_READY,
        })

    return {
        "schema": PACKAGE_SCHEMA,
        "project": project_id,
        "account": str(dna.get("slug") or ""),
        "media": {
            "duration_s": round(duration, 2),
            "width": width,
            "height": height,
            "aspect": aspect,
            "size_mb": size_mb,
            "sha256": str(media.get("sha256") or ""),
        },
        "hook_s": None if hook_s is None else round(float(hook_s), 2),
        "dna_note": str(dna.get("platform_note") or ""),
        "dna_text_platforms": (dna.get("text_platforms") or {}).get("platforms") or [],
        "state": STATE_BLOCKED if blockers else STATE_READY,
        "publish_authorized": False,
        "production_ready": False,
        "blockers": blockers,
        "platforms": entries,
    }
