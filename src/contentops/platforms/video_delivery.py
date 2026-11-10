"""Whether a packaged video may leave the repository, and in what argv.

Packing is local and reversible. Handing a package to a browser-automation
uploader is neither: it types into a logged-in session and produces a real post.
The two decisions used to live nowhere — ``pack`` wrote JSON and a human opened a
browser — so this module is the single answer to one question:

    may this package be handed to the uploader, and if so, what exactly runs?

The rules, in order of severity
-------------------------------
1. an unknown platform is refused — the spec file is the only list;
2. a package whose state is ``BLOCKED`` is refused — delivery consumes
   validation, it never replaces it;
3. a package asserting ``publish_authorized: true`` is refused — that flag is a
   founder decision recorded elsewhere, never something a package may assert;
4. without an explicit execution grant the answer is ``PACKAGE_ONLY``: a human
   gets the files and the argv, the uploader never runs;
5. Douyin additionally requires an explicit policy acknowledgement in the
   grant. Its official interface is limited to authorised subjects, requires
   user-initiated action and prohibits homogenised content; a generic grant does
   not cover that;
6. a missing uploader login cookie is a refusal with the exact expected path, so
   the operator sees what to create instead of a stack trace.

A refusal is not an error. It is the recorded answer, with reasons.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import video_specs

__all__ = [
    "ELIGIBLE",
    "PACKAGE_ONLY",
    "REFUSED",
    "URL_RECORDED",
    "Decision",
    "authorize",
    "build_command",
    "cookie_path",
    "cookie_present",
    "douyin_policy_ack",
    "load_grant",
    "record_publication",
    "resolve_category",
]

ELIGIBLE = "ELIGIBLE_TO_EXECUTE"
PACKAGE_ONLY = "PACKAGE_ONLY"
REFUSED = "REFUSED"

#: Platforms whose delegated publishing carries a policy condition that a
#: generic execution grant does not satisfy.
POLICY_GATED = {"douyin": "douyin_policy_ack"}

#: Where a real published work actually lives. A "published URL" is the only
#: thing that may move a work out of "uploaded", so the host is checked rather
#: than trusted: a typo or a screenshot link is not proof of publication.
PUBLISH_HOSTS = {
    "douyin": ("douyin.com", "iesdouyin.com"),
    "shipinhao": ("channels.weixin.qq.com", "weixin.qq.com"),
    "xiaohongshu_video": ("xiaohongshu.com", "xhslink.com"),
    "bilibili": ("bilibili.com", "b23.tv"),
    "kuaishou": ("kuaishou.com", "chenzhongtech.com"),
    "youtube": ("youtube.com", "youtu.be"),
}

#: State recorded when an operator supplies a real URL. Never "PUBLISHED":
#: a receipt cannot prove a person watched it, and the registry's top rung also
#: requires human review.
URL_RECORDED = "URL_RECORDED_BY_OPERATOR"


@dataclass(frozen=True)
class Decision:
    """The recorded answer, never a bare boolean."""

    platform_id: str
    outcome: str
    reasons: tuple[str, ...] = field(default_factory=tuple)
    required_conditions: tuple[str, ...] = field(default_factory=tuple)
    command: tuple[str, ...] = field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return self.outcome != REFUSED

    @property
    def executable(self) -> bool:
        return self.outcome == ELIGIBLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "outcome": self.outcome,
            "reasons": list(self.reasons),
            "required_conditions": list(self.required_conditions),
            "command": list(self.command),
        }


def load_grant(path: Path | None) -> dict[str, Any]:
    """Read an operator grant. Missing or unreadable means 'no grant', not 'all'."""
    if path is None or not Path(path).is_file():
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _grant_for(grant: dict[str, Any], platform_id: str) -> dict[str, Any]:
    platforms = grant.get("platforms") if isinstance(grant, dict) else None
    if not isinstance(platforms, dict):
        return {}
    entry = platforms.get(platform_id)
    return entry if isinstance(entry, dict) else {}


def douyin_policy_ack(grant: dict[str, Any]) -> bool:
    return bool(_grant_for(grant, "douyin").get("douyin_policy_ack"))


def cookie_path(sau_root: Path, platform_id: str, account: str) -> Path:
    """Where the uploader expects the login cookie for this platform+account."""
    pattern = str(video_specs.uploader(platform_id).get("cookie_glob") or "")
    if not pattern:
        return Path()
    return Path(sau_root) / pattern.format(account=account)


def cookie_present(sau_root: Path, platform_id: str, account: str) -> tuple[bool, Path]:
    path = cookie_path(sau_root, platform_id, account)
    return (bool(path) and path.is_file()), path


def _thumbnail_flags(platform_id: str, thumbnails: dict[str, str]) -> list[str]:
    """Attach each declared thumbnail flag to the best matching extracted ratio."""
    argv: list[str] = []
    used: set[str] = set()
    for row in video_specs.thumbnails(platform_id):
        flag = str(row["flag"])
        if flag in used:
            continue
        path = thumbnails.get(str(row["ratio"]))
        if path:
            argv.extend([flag, str(path)])
            used.add(flag)
    return argv


def build_command(
    platform_id: str,
    *,
    executable: str,
    account: str,
    video: str,
    metadata: dict[str, Any],
    thumbnails: dict[str, str] | None = None,
    supplied_args: dict[str, str] | None = None,
    draft: bool = False,
    headed: bool = False,
) -> list[str]:
    """Build the uploader argv for one platform.

    Returned as a list, never a shell string: a hashtag must not be able to
    become a comment and a title must not be able to become a command.

    ``headed`` selects the visible browser. The uploader defaults to headless,
    which needs Chrome's headless-shell build; the full Chromium build is what a
    login session and a first real upload actually exercise, so both are
    reachable instead of only the one whose binary happens to be installed.
    """
    row = video_specs.spec(platform_id)
    up = video_specs.uploader(platform_id)
    argv: list[str] = [executable, str(up["platform"]), str(up["action"])]
    argv += ["--account", account, "--file", video]
    argv += ["--title", str(metadata.get("title") or "")]
    argv += ["--desc", str(metadata.get("desc") or "")]
    rendered = str(metadata.get("tags_rendered") or "")
    if rendered:
        argv += ["--tags", rendered]

    argv += _thumbnail_flags(platform_id, thumbnails or {})

    supplied = supplied_args or {}
    for arg in row.get("required_args") or []:
        value = supplied.get(str(arg["field"]))
        if value:
            argv += [str(arg["flag"]), str(value)]

    if draft and row.get("supports_draft"):
        argv.append("--draft")
    if headed:
        argv.append("--headed")

    return argv


def authorize(
    platform_id: str,
    *,
    package_state: str,
    publish_authorized_claim: bool = False,
    execute_requested: bool = False,
    grant: dict[str, Any] | None = None,
    cookie_ready: bool = True,
    cookie_expected: str = "",
    command: list[str] | None = None,
) -> Decision:
    """Decide how far one packaged platform may go."""
    if platform_id not in video_specs.platform_ids():
        return Decision(platform_id, REFUSED, ("UNKNOWN_PLATFORM: 不在视频平台规格表内",))

    if str(package_state).upper() == "BLOCKED":
        return Decision(
            platform_id, REFUSED,
            ("PACKAGE_BLOCKED: 校验未通过，投递只消费校验结果，不会替它做判断",),
            ("resolve-reported-blockers",),
        )

    if publish_authorized_claim:
        return Decision(
            platform_id, REFUSED,
            ("PACKAGE_ASSERTS_AUTHORIZATION: publish_authorized 只能由创始人决定，包本身无权声明",),
        )

    entry = _grant_for(grant or {}, platform_id)
    if not execute_requested:
        return Decision(
            platform_id, PACKAGE_ONLY,
            ("EXECUTION_NOT_REQUESTED: 只出包与 argv，不运行上传器",),
            (),
            tuple(command or ()),
        )

    reasons: list[str] = []
    conditions: list[str] = []

    if not entry.get("execute"):
        reasons.append("NO_EXECUTION_GRANT: 授权文件未对本站点开启 execute")
        conditions.append("grant.platforms.%s.execute=true" % platform_id)

    ack_key = POLICY_GATED.get(platform_id)
    if ack_key and not entry.get(ack_key):
        reasons.append(
            "POLICY_ACK_MISSING: 该平台的委托发布带主体资质/用户主动触发/反同质化条件，"
            "通用授权不覆盖"
        )
        conditions.append("grant.platforms.%s.%s=true" % (platform_id, ack_key))

    if not cookie_ready:
        reasons.append("UPLOADER_LOGIN_MISSING: 上传器没有该平台登录态")
        conditions.append(f"cookie:{cookie_expected}")

    if reasons:
        return Decision(platform_id, REFUSED, tuple(reasons), tuple(conditions), tuple(command or ()))

    return Decision(platform_id, ELIGIBLE, ("GRANTED: 授权、登录态与校验齐备",), (), tuple(command or ()))


def resolve_category(
    platform_id: str,
    *,
    cli_value: str = "",
    project_value: str = "",
    dna_value: str = "",
) -> tuple[str, str]:
    """Resolve a required numeric category (Bilibili ``--tid``) without inventing one.

    A category id decides which section of the platform the work is filed under.
    Guessing it produces a video in the wrong section, which is worse than no
    upload, so the only acceptable sources are an explicit flag, the project
    record, or the account DNA. Precedence is most-specific-first and the answer
    reports where it came from, so a wrong id can be traced to the file that set it.
    """
    for value, source in (
        (cli_value, "cli"),
        (project_value, "project.yaml"),
        (dna_value, "account_dna"),
    ):
        if str(value or "").strip():
            return str(value).strip(), source
    return "", "unresolved"


def record_publication(
    platform_id: str,
    url: str,
    *,
    metrics: dict[str, Any] | None = None,
    checked_at: str = "",
) -> dict[str, Any]:
    """Record a real published URL and, optionally, a real metrics snapshot.

    The uploader never returns a URL, so this is the only path from "the tool
    exited 0" to "this work exists on the platform". It refuses a URL whose host
    is not the platform's, because a local path, a screenshot link or a typo
    would otherwise become a permanent false claim in a receipt.
    """
    if platform_id not in video_specs.platform_ids():
        return {"accepted": False, "state": REFUSED,
                "reasons": ["UNKNOWN_PLATFORM: 不在视频平台规格表内"]}

    candidate = str(url or "").strip()
    if not candidate.lower().startswith(("http://", "https://")):
        return {"accepted": False, "state": REFUSED,
                "reasons": ["URL_NOT_ABSOLUTE: 必须是 http(s) 的真实链接"]}

    host = ""
    try:
        without_scheme = candidate.split("://", 1)[1]
        host = without_scheme.split("/", 1)[0].split("?", 1)[0].lower()
        host = host.rsplit("@", 1)[-1].split(":", 1)[0]
    except IndexError:  # pragma: no cover - guarded by the scheme check above
        host = ""

    allowed = PUBLISH_HOSTS.get(platform_id) or ()
    if allowed and not any(host == item or host.endswith("." + item) for item in allowed):
        return {
            "accepted": False,
            "state": REFUSED,
            "reasons": [f"URL_HOST_MISMATCH: {host or '空'} 不属于 {platform_id}（应为 {'/'.join(allowed)}）"],
        }

    snapshot: dict[str, Any] = {}
    if metrics:
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                snapshot[str(key)] = value

    return {
        "accepted": True,
        "state": URL_RECORDED,
        "platform_id": platform_id,
        "url": candidate,
        "host": host,
        "metrics": snapshot,
        "metrics_note": (
            "只记录人工提供的数值；上传器与平台接口都不回传播放/互动数据"
            if not snapshot else "人工提供的数值快照，未经平台接口核对"
        ),
        "checked_at": str(checked_at or ""),
        "publish_note": "有真实 URL 才叫发布；本条不等于人工审核通过",
    }
