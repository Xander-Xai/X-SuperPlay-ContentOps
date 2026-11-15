"""One account, several platforms: what each one needs before it will accept the cut.

Why this module exists
----------------------
The repository already knew two things separately. `video_specs` knows what shape a
platform accepts (aspect, duration ceiling, title length, tag count, uploader). The
account DNA knows which platforms an account actually runs, what each one is for, and —
the part that matters most here — whether the account may use manual screen recording at
all.

Nothing joined them. So "adapt this film to the platform" was a human reading two
documents and remembering which account they were in, and the failure mode was silent:
the 16:9 long cut that Bilibili wants was never requested, or a recording-led account's
film was packed against a no-recording account's rules.

This module produces one plan per project: one row per platform, each stating the shape
required, whether the master can satisfy it or a second render is needed, why, and which
recording policy governs it. It plans; it does not render, upload or authorise anything.

Fail-closed rules, in order:

* no `account_slug` → the plan is `BLOCKED`, because there is no default account;
* an account platform with no spec row → `BLOCKED`, not skipped: a platform we cannot
  describe is a platform we cannot pack for;
* a platform the account never declared → refused before it is planned.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from contentops.accounts import account_kind, load_account
from contentops.paths import trusted_project_root
from contentops.platforms import video_specs

__all__ = [
    "BLOCKED",
    "PLANNED",
    "RECEIPT",
    "SCHEMA",
    "AdaptationError",
    "plan",
    "write_receipt",
]

SCHEMA = "contentops.platform-adaptation/v1"
RECEIPT = Path("receipts") / "platform-adaptation.json"

PLANNED = "PLANNED"
BLOCKED = "BLOCKED"

#: Account DNA names a platform the way the operator says it; the delivery specs name it
#: the way the uploader does. One place to translate, so a rename cannot silently drop a
#: platform from a plan.
PLATFORM_ALIASES = {
    "xiaohongshu": "xiaohongshu_video",
    "xhs": "xiaohongshu_video",
    "b站": "bilibili",
    "公众号": "gzh",
    "gzh": "gzh",
}

#: Platforms whose delivery is a written piece, not a video. They appear in the plan as
#: `requires_variant` with a text reason, so nobody packs a nine-by-sixteen film for a
#: platform that wants an article.
TEXT_PLATFORMS = {"gzh", "zhihu", "csdn", "x"}


class AdaptationError(ValueError):
    """The request is malformed (not a verdict about the account or platform)."""


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _project_scalar(project: Path, key: str) -> str:
    path = project / "project.yaml"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip().strip("'\"")
    return ""


def _canvas(dna: Mapping[str, Any]) -> Dict[str, Any]:
    render = dna.get("render") if isinstance(dna.get("render"), dict) else {}
    canvas = render.get("canvas") if isinstance(render.get("canvas"), dict) else {}
    width = canvas.get("width")
    height = canvas.get("height")
    if isinstance(width, int) and isinstance(height, int):
        orientation = "vertical" if height > width else "horizontal"
        return {"width": width, "height": height, "orientation": orientation}
    # An account that declares no canvas is not given one here: the master's shape is a
    # fact about the account, and inventing 1080x1920 would hide the declaration gap.
    return {}


def _derivative(dna: Mapping[str, Any], platform_id: str) -> Optional[Dict[str, Any]]:
    """The account's own second cut for this platform, wherever the DNA declares it.

    Two accounts in this repository put it in two places — one at ``render.derivative``,
    the other nested under ``render.canvas.derivative``. Reading only one of them made
    the long-cut platform claim it needed no variant, which is the exact silent failure
    this module exists to prevent.
    """
    render = dna.get("render") if isinstance(dna.get("render"), dict) else {}
    canvas = render.get("canvas") if isinstance(render.get("canvas"), dict) else {}
    candidates = [render.get("derivative"), canvas.get("derivative")]
    derivative = next((item for item in candidates if isinstance(item, dict) and item), {})
    if not derivative:
        return None
    if str(derivative.get("platform") or "") != platform_id:
        return None
    width, height = derivative.get("width"), derivative.get("height")
    if not (isinstance(width, int) and isinstance(height, int)):
        return None
    return {"width": width, "height": height,
            "orientation": str(derivative.get("orientation") or
                               ("vertical" if height > width else "horizontal")),
            "mode": str(derivative.get("mode") or "")}


def _aspect(width: int, height: int) -> str:
    from math import gcd

    divisor = gcd(width, height) or 1
    return f"{width // divisor}:{height // divisor}"


def _recording_policy(dna: Mapping[str, Any]) -> Dict[str, str]:
    evidence = dna.get("evidence") if isinstance(dna.get("evidence"), dict) else {}
    permission = str(evidence.get("manual_recording") or "")
    note = ""
    if permission == "FORBIDDEN":
        note = ("本账号禁止手动录屏：该平台的成片必须由矢量/代码画面构成，"
                "录屏素材入场会在 intake 阶段被拒绝。")
    elif permission == "ALLOWED_CROPPED":
        note = ("本账号允许裁切后的录屏作证据：每个录屏片段在 intake 阶段必须给裁切矩形，"
                "并在人审时确认桌面/弹窗/凭据已移除。")
    elif permission:
        note = f"manual_recording={permission} 不在已知取值内，入场阶段会 BLOCKED。"
    else:
        note = "账号未声明 manual_recording，录屏入场会被 BLOCKED。"
    return {"manual_recording": permission or "UNDECLARED", "note": note}


def _row(platform_id: str, *, dna: Mapping[str, Any], master: Mapping[str, Any],
         declared: bool, role: Any, role_status: str) -> Dict[str, Any]:
    """One platform's requirements, or a refusal that says why there is none."""
    spec_id = PLATFORM_ALIASES.get(platform_id, platform_id)
    if spec_id in TEXT_PLATFORMS:
        return {
            "platform_id": platform_id,
            "spec_id": None,
            "declared": declared,
            "role": role,
            "role_status": role_status,
            "kind": "TEXT",
            "requires_variant": True,
            "variant_reason": "该平台收图文，不收这条竖版成片；需要按同一叙事骨架改写。",
            "requirements": ["article-or-graphic"],
            "limits": {},
            "uploader": None,
        }
    if spec_id not in video_specs.platform_ids():
        return {
            "platform_id": platform_id,
            "spec_id": spec_id,
            "declared": declared,
            "role": role,
            "role_status": role_status,
            "kind": "VIDEO",
            "requires_variant": True,
            "variant_reason": f"没有 {spec_id} 的交付规格：无法描述形状就不能打包。",
            "requirements": [],
            "limits": {},
            "uploader": None,
            "blocked": "NO_SPEC",
        }

    rules = video_specs.rules(spec_id)
    requirements = video_specs.requirements(spec_id)
    uploader = video_specs.uploader(spec_id)
    derivative = _derivative(dna, spec_id)
    master_aspect = _aspect(master["width"], master["height"]) if master else ""
    required_aspect = str(rules.get("aspect_required") or "")

    requires_variant = False
    reason = ""
    if derivative:
        requires_variant = True
        reason = (f"账号声明该平台用 {derivative['width']}×{derivative['height']} "
                  f"{derivative['orientation']} 派生版（{derivative['mode'] or 'reshaped'}）；"
                  f"主成片 {master_aspect} 不是这一版。")
    elif master_aspect and required_aspect and master_aspect != required_aspect:
        requires_variant = True
        reason = f"主成片 {master_aspect} 与平台要求的 {required_aspect} 不一致。"

    return {
        "platform_id": platform_id,
        "spec_id": spec_id,
        "declared": declared,
        "role": role,
        "role_status": role_status,
        "kind": "VIDEO",
        "requires_variant": requires_variant,
        "variant_reason": reason,
        "canvas": derivative or dict(master),
        "requirements": requirements,
        "limits": {
            "aspect_required": required_aspect,
            "max_duration_s": rules.get("max_duration_s"),
            "max_file_mb": rules.get("max_file_mb"),
            "title_max_hard": rules.get("title_max_hard"),
            "title_max_soft": rules.get("title_max_soft"),
            "desc_max_hard": rules.get("desc_max_hard"),
            "tags_min": rules.get("tags_min"),
            "tags_max": rules.get("tags_max"),
            "hook_max_s": rules.get("hook_max_s"),
            "supports_draft": rules.get("supports_draft"),
        },
        "uploader": {
            "tool": uploader.get("tool"),
            "draft_support": "su" if rules.get("supports_draft") else "NONE",
        },
    }


def _platforms_for(dna: Mapping[str, Any]) -> List[str]:
    """Every platform this account delivers to, declared first.

    Roles marked INFRASTRUCTURE are excluded deliberately: GitHub is where the proof
    lives, not somewhere a film is published, and a delivery plan that listed it would
    block on a spec that should not exist.
    """
    roles = dna.get("platform_roles") if isinstance(dna.get("platform_roles"), dict) else {}
    infrastructure = {
        str(name) for name, role in roles.items()
        if isinstance(role, dict) and str(role.get("status") or "") == "INFRASTRUCTURE"
    }
    seen: List[str] = []
    for name in list(dna.get("platforms") or []) + list(dna.get("derived_platforms") or []) \
            + list(roles.keys()):
        text = str(name or "").strip()
        if text and text not in seen and text not in infrastructure:
            seen.append(text)
    return seen


def plan(project_dir: Path, *, repo_root: Optional[Path] = None,
         platforms: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Build the per-platform adaptation plan for one project.

    The result is always a receipt payload: a refusal is `BLOCKED` with a reason code,
    never an exception, so a caller cannot mistake "no plan" for "nothing to do".
    """
    project = Path(project_dir).expanduser().resolve()
    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[3]
    if trusted_project_root(project, root) is None:
        raise AdaptationError(
            "project directory must stay inside the repository or the configured output root")

    slug = _project_scalar(project, "account_slug")
    base: Dict[str, Any] = {
        "schema": SCHEMA,
        "generated_at": _now(),
        "project": project.as_posix(),
        "account": {"slug": slug, "kind": ""},
        "status": BLOCKED,
        "reason_code": "",
        "reason": "",
        "master_canvas": {},
        "recording": {},
        "platforms": [],
        # Planning is never production readiness and never distribution authority.
        "production_ready": False,
        "publish_authorized": False,
        "does_not_claim": "This plan describes what each platform requires. It does not "
                          "render, upload, approve a cut, or authorise publication.",
    }
    if not slug:
        base.update(reason_code="ACCOUNT_UNANNOUNCED",
                    reason="project.yaml 未声明 account_slug；没有账号 DNA 就没有平台清单。")
        return base

    dna_path = root / "config" / "accounts" / f"{slug}.json"
    if not dna_path.is_file():
        base.update(reason_code="ACCOUNT_UNKNOWN", reason=f"账号 DNA 不存在：{dna_path.name}")
        return base
    dna = load_account(dna_path)
    kind = account_kind(dna)
    base["account"] = {"slug": slug, "kind": kind}
    master = _canvas(dna)
    base["master_canvas"] = master
    base["recording"] = _recording_policy(dna)

    if kind == "x":
        base.update(status=PLANNED, reason_code="TEXT_ACCOUNT",
                    reason="该账号只发 X：一条英文帖 + 一张 16:9 真图，不走视频线。",
                    platforms=[_row("x", dna=dna, master=master, declared=True,
                                    role=(dna.get("platform_roles") or {}).get("x"),
                                    role_status="ACTIVE")])
        return base

    named = _platforms_for(dna)
    requested = [str(item).strip() for item in (platforms or named) if str(item).strip()]
    undeclared = [item for item in requested if item not in named]
    if undeclared:
        base.update(reason_code="PLATFORM_NOT_DECLARED",
                    reason=f"这些平台不在账号 {slug} 的声明里：{undeclared}")
        return base

    roles = dna.get("platform_roles") if isinstance(dna.get("platform_roles"), dict) else {}
    rows: List[Dict[str, Any]] = []
    blocked: List[str] = []
    for platform_id in requested:
        role = roles.get(platform_id)
        status = ""
        if isinstance(role, dict):
            status = str(role.get("status") or "")
            role = role.get("role")
        elif isinstance(role, str):
            status = "DECLARED"
        row = _row(platform_id, dna=dna, master=master,
                   declared=platform_id in (dna.get("platforms") or []),
                   role=role, role_status=status)
        if row.get("blocked"):
            blocked.append(f"{platform_id}: {row['blocked']}")
        rows.append(row)

    base["platforms"] = rows
    if blocked:
        base.update(reason_code="PLATFORM_UNSUPPORTED", reason="；".join(blocked),
                    status=BLOCKED)
        return base
    base.update(status=PLANNED, reason_code="PLANNED",
                reason=f"账号 {slug} 的 {len(rows)} 个平台各有规格；"
                       f"{sum(1 for r in rows if r['requires_variant'])} 个需要与主成片不同的版本。")
    return base


def write_receipt(project_dir: Path, payload: Mapping[str, Any]) -> Path:
    """Write the plan where a reviewer will look for it. Overwrites the previous plan."""
    project = Path(project_dir)
    target = project / RECEIPT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target
