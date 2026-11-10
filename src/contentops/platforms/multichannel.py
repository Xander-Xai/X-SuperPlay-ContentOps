"""Offline multi-channel delivery adapter for the GRAPHIC_TEXT line.

Implements the proposed ``PlatformAdapter`` protocol from
``docs/PLATFORM-ADAPTER-CONTRACT.md`` without modifying the platform registry,
without adding a registry row, and without upgrading any row's status.

Design boundaries (from the contract):
  * ``pack`` / ``validate`` are offline and deterministic. No network, no
    credential, no dependency installation, no host startup.
  * ``prepare_handoff`` ends at ``AWAITING_MANUAL_PUBLISH``; it never publishes
    and never records a URL.
  * ``publish`` raises unless a fully verified ``PublishAuthorization`` is
    supplied. This implementation is manual-only and has no PUBLISHED branch.
  * ``read_metrics`` returns None (missing metrics are NONE, never zero).
  * Receipts follow ``contentops.platform-delivery/v1``: no secrets, no
    absolute host paths, ``publish_authorized: false`` by default.

The external delivery channels (Wechatsync CLI, tweepy) are never imported or
invoked from this module. A separate operator-level runner owns that process
boundary, keeping GPL/AGPL-licensed tools out of this Apache-2.0 source tree.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from contentops.platforms import graphic_specs, platform_audit

ADAPTER_VERSION = "contentops.multichannel/1.0.0"
DELIVERY_SCHEMA = "contentops.platform-delivery/v1"

# Platform records come from config/platforms/graphic-platforms.yaml via
# contentops.platforms.graphic_specs. Two views are derived from that one file:
#
#   REGISTRY_GRAPHIC_PLATFORMS - platforms that also exist as rows in
#       config/registry/platforms.json. This module still may not add a row or
#       upgrade a row's status.
#   DELIVERY_GRAPHIC_PLATFORMS - every platform the graphic line can shape and
#       hand off, including delivery-only channels with no registry row.
#
# xiaohongshu is absent from both by operator instruction (2026-11-09): the
# whole Xiaohongshu platform belongs to the VIDEO line. It stays listed in the
# spec file under `excluded` so the exclusion is auditable, not implicit.
REGISTRY_GRAPHIC_PLATFORMS: dict[str, dict[str, str]] = {}
DELIVERY_GRAPHIC_PLATFORMS: dict[str, dict[str, str]] = {}


def _refresh_platform_views() -> None:
    registry: dict[str, dict[str, str]] = {}
    delivery: dict[str, dict[str, str]] = {}
    for pid in graphic_specs.platform_ids():
        row = graphic_specs.spec(pid)
        entry = {
            "strategy_platform": str(row["strategy_platform"]),
            "pipeline": str(row["pipeline"]),
            "production_line": str(row.get("production_line") or "GRAPHIC_TEXT"),
            "channel": graphic_specs.primary_channel(pid),
            "native_format": str(row["native_format"]),
            "registry_row": "true" if row["registry_row"] else "false",
        }
        delivery[pid] = entry
        if row["registry_row"]:
            registry[pid] = entry
    REGISTRY_GRAPHIC_PLATFORMS.clear()
    REGISTRY_GRAPHIC_PLATFORMS.update(registry)
    DELIVERY_GRAPHIC_PLATFORMS.clear()
    DELIVERY_GRAPHIC_PLATFORMS.update(delivery)

# VIDEO line. Xiaohongshu lives here, together with the other video platforms
# from config/registry/platforms.json. The external tool is
# dreammis/social-auto-upload (MIT), installed in the gitignored .runtime/sau.
VIDEO_DELIVERY_PLATFORMS: dict[str, dict[str, str]] = {
    "xiaohongshu_video": {
        "strategy_platform": "xiaohongshu",
        "pipeline": "VIDEO",
        "channel": "sau:xiaohongshu upload-video",
        "note": "operator instruction 2026-11-09: Xiaohongshu is a video platform",
    },
    "douyin": {"strategy_platform": "douyin", "pipeline": "VIDEO",
               "channel": "sau:douyin upload-video", "note": ""},
    "bilibili": {"strategy_platform": "bilibili", "pipeline": "VIDEO",
                 "channel": "sau:bilibili upload-video", "note": ""},
    "shipinhao": {"strategy_platform": "wechat_channels", "pipeline": "VIDEO",
                  "channel": "sau:tencent upload-video", "note": ""},
    "youtube": {"strategy_platform": "youtube", "pipeline": "VIDEO",
                "channel": "sau:youtube upload-video", "note": ""},
}

# Optional delivery targets exposed by the external tools. These are NOT
# registry rows: the registry remains the only local execution truth source.
EXTRA_DELIVERY_CHANNELS: dict[str, str] = {
    "weibo": "wechatsync:weibo",
    "juejin": "wechatsync:juejin",
    "toutiao": "wechatsync:toutiao",
    "jianshu": "wechatsync:jianshu",
    "baijiahao": "wechatsync:baijiahao",
    "bilibili_article": "wechatsync:bilibili",
    "douyin_image": "wechatsync:douyin",
    "wordpress": "wechatsync:wordpress",
    "typecho": "wechatsync:typecho",
    "51cto": "wechatsync:51cto",
    "oschina": "wechatsync:oschina",
    "segmentfault": "wechatsync:segmentfault",
    "cnblogs": "wechatsync:cnblogs",
    "yuque": "wechatsync:yuque",
    "medium": "cose:medium",
    "devto": "cose:dev-to",
    "threads": "postiz:threads",
    "linkedin": "postiz:linkedin",
    "instagram": "postiz:instagram",
    "bluesky": "postiz:bluesky",
    "mastodon": "postiz:mastodon",
    "reddit": "postiz:reddit",
}

# Offline, deterministic platform shaping rules now live in
# config/platforms/graphic-platforms.yaml (see contentops.platforms.graphic_specs).
# The old four-entry tuple below was replaced because it compared a project
# editorial convention (25-character WeChat title) against a platform hard limit
# (50000-character body) as though both carried the same authority. The spec file
# keeps hard and soft tiers separate and records a `basis` for every number.
def platform_rules(platform_id: str) -> dict[str, Any]:
    """Normalised shaping rules for one platform (hard/soft tiers kept apart)."""
    return graphic_specs.rules(platform_id)


PLATFORM_RULES: dict[str, dict[str, Any]] = {}


def _ensure_views() -> None:
    """Populate the platform views on first use, with a clear failure message.

    The spec file needs PyYAML, which the project declares as a runtime
    dependency but a bare system interpreter may not have. Importing this module
    must not explode on a machine that only wants ``capabilities()``, so loading
    is deferred to the first call that actually needs a platform record.
    """
    if DELIVERY_GRAPHIC_PLATFORMS and PLATFORM_RULES:
        return
    _refresh_platform_views()
    for pid in DELIVERY_GRAPHIC_PLATFORMS:
        PLATFORM_RULES[pid] = graphic_specs.rules(pid)

# Match a real Windows drive path (C:/..., C:\\...) but NOT logical refs such
# as project:// or repo:// — the negative lookahead rejects the double slash.
ABSOLUTE_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/](?![\\/])|/home/|/Users/|\\\\\\\\)")
SECRET_SHAPED_RE = re.compile(
    r"(?:APPSECRET|API_KEY|ACCESS_TOKEN|BEARER|PASSWORD|COOKIE|WECHATSYNC_TOKEN|MCP_TOKEN)\s*[=:]\s*\S+",
    re.I,
)


class AdapterError(ValueError):
    """Base class for deterministic adapter refusals."""


class UnknownPlatformError(AdapterError):
    pass


class BundleChangedError(AdapterError):
    pass


class PublishAuthorizationError(AdapterError):
    pass


class RightsGateError(AdapterError):
    pass


@dataclass(frozen=True)
class AdapterCapabilities:
    draft: bool = True
    prepare_handoff: bool = True
    publish: bool = False
    metrics: str = "NONE"
    media_upload: bool = False
    draft_support: str = "LOCAL_OFFLINE"
    publish_mode: str = "MANUAL_ONLY"
    adapter_version: str = ADAPTER_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "draft": self.draft,
            "prepare_handoff": self.prepare_handoff,
            "publish": self.publish,
            "metrics": self.metrics,
            "media_upload": self.media_upload,
            "draft_support": self.draft_support,
            "publish_mode": self.publish_mode,
            "adapter_version": self.adapter_version,
        }


@dataclass(frozen=True)
class PlatformDraft:
    platform_id: str
    strategy_platform: str
    pipeline: str
    channel: str
    native_format: str
    title: str
    body: str
    media_refs: tuple[str, ...]
    package_id: str
    bundle_sha256: str
    draft_sha256: str = ""
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    registry_row: bool = True
    # Short-post platforms have no title field, so `title` is empty after
    # shaping. The headline still has to reach the delivery CLI, which refuses a
    # file without one, so the pre-shaping title is carried separately instead of
    # being re-derived from the body (re-deriving produced a title made of the
    # first two sentences).
    title_hint: str = ""
    # Produced by platform_audit: every platform in the spec recommends 2-6 tags
    # and wants a short digest, and before this they were simply absent.
    suggested_tags: tuple[str, ...] = ()
    digest: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "strategy_platform": self.strategy_platform,
            "pipeline": self.pipeline,
            "channel": self.channel,
            "native_format": self.native_format,
            "title": self.title,
            "title_hint": self.title_hint,
            "body": self.body,
            "media_refs": list(self.media_refs),
            "package_id": self.package_id,
            "bundle_sha256": self.bundle_sha256,
            "draft_sha256": self.draft_sha256,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "registry_row": self.registry_row,
            "suggested_tags": list(self.suggested_tags),
            "digest": self.digest,
        }


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors)}


@dataclass
class MultiChannelAdapter:
    """One adapter instance per registry row; all methods are offline."""

    platform_id: str
    strategy_platform: str = ""
    pipeline: str = ""
    content_types: tuple[str, ...] = ("GRAPHIC_TEXT",)
    expected_bundle_sha256: str = ""
    _spec: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        _ensure_views()
        if self.platform_id not in DELIVERY_GRAPHIC_PLATFORMS:
            raise UnknownPlatformError(f"未知 platform_id：{self.platform_id}")
        self._spec = dict(DELIVERY_GRAPHIC_PLATFORMS[self.platform_id])
        self.strategy_platform = self._spec["strategy_platform"]
        self.pipeline = self._spec["pipeline"]

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities()

    @staticmethod
    def _sha256_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _logical_ref(raw: str) -> str:
        """Never emit an absolute host path into a receipt."""
        value = str(raw).replace("\\", "/")
        if value.startswith("repo://") or value.startswith("project://"):
            return value
        if ABSOLUTE_PATH_RE.search(value):
            return "project://unresolved-asset/" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return "project://" + value.lstrip("./")

    def pack(self, package: dict[str, Any], account: dict[str, Any]) -> PlatformDraft:
        """Offline, deterministic mapping of a reviewed package to a native draft."""
        if package.get("schema") != "contentops.graphic-package/v1":
            raise AdapterError("输入必须是 contentops.graphic-package/v1")
        bundle_sha = str(package.get("bundle_sha256") or "")
        if self.expected_bundle_sha256 and bundle_sha != self.expected_bundle_sha256:
            raise BundleChangedError("BUNDLE_CHANGED：Bundle 摘要与交付绑定不一致")
        if not bundle_sha:
            raise AdapterError("缺少 bundle_sha256")
        if package.get("publish_authorized") is True:
            raise AdapterError("输入包已声明 publish_authorized；适配器只接受人工复核包")

        # Rights gate: an unlicensed asset is refused, never silently downgraded.
        for image in package.get("images", []) or []:
            rights = image.get("rights") or {}
            if not rights or not str(rights.get("license_id") or "").strip():
                raise RightsGateError("UNLICENSED_ASSET：图片缺少 rights.license_id")

        title = str(package.get("title") or "").strip()
        draft_info = package.get("draft") or {}
        if not title or not draft_info:
            raise AdapterError("缺少 title 或 draft 契约")

        package_root = Path(str(package.get("_package_root") or "."))
        draft_rel = str(draft_info.get("path") or "")
        draft_path = package_root / draft_rel
        body = draft_path.read_text(encoding="utf-8") if draft_path.is_file() else ""
        if not body.strip():
            raise AdapterError(f"草稿不可读或为空：{draft_rel}")

        rules = platform_rules(self.platform_id)
        title_original = title
        shaped = graphic_specs.shape(self.platform_id, title, body)
        title = shaped["title"]
        body = shaped["body"]
        blockers: list[str] = list(shaped["blockers"])
        warnings: list[str] = list(shaped["warnings"])

        if rules["needs_cover"] and not (package.get("images") or []):
            blockers.append("COVER_REQUIRED")

        tags = [str(t) for t in (package.get("tags") or []) if str(t).strip()]
        if rules["recommended_tags"] and len(tags) < rules["recommended_tags"]:
            warnings.append(
                f"TAGS_BELOW_RECOMMENDED:{len(tags)}<{rules['recommended_tags']}"
            )

        # Content-level per-platform audit. Length rules alone let four platforms
        # receive byte-identical bodies with zero tags; this adds the checks that
        # actually differ by platform (topic coverage, tag extraction, digest,
        # code-fence labelling).
        content = platform_audit.audit(
            self.platform_id, title_original, body, rules=rules
        )
        blockers.extend(content["blockers"])
        warnings.extend(content["warnings"])

        if package.get("status") != "AWAITING_MANUAL_REVIEW":
            blockers.append("PACKAGE_NOT_IN_MANUAL_REVIEW")
        if package.get("human_review") != "NOT_STARTED":
            blockers.append("HUMAN_REVIEW_STATE_UNEXPECTED")

        media_refs = tuple(self._logical_ref(str(i.get("path") or "")) for i in (package.get("images") or []))
        payload = json.dumps(
            {"p": self.platform_id, "t": title, "b": body, "m": media_refs, "s": bundle_sha},
            ensure_ascii=False, sort_keys=True,
        )
        return PlatformDraft(
            platform_id=self.platform_id,
            strategy_platform=self.strategy_platform,
            pipeline=self.pipeline,
            channel=self._spec["channel"],
            native_format=self._spec["native_format"],
            title=title,
            body=body,
            media_refs=media_refs,
            package_id=str(package.get("bundle_id") or ""),
            bundle_sha256=bundle_sha,
            draft_sha256=self._sha256_text(payload),
            blockers=tuple(blockers),
            warnings=tuple(warnings),
            registry_row=self._spec.get("registry_row") == "true",
            title_hint=title_original,
            suggested_tags=tuple(content["suggested_tags"]),
            digest=content["digest"],
        )

    def validate(self, draft: PlatformDraft) -> ValidationResult:
        errors: list[str] = []
        if draft.platform_id != self.platform_id:
            errors.append("PLATFORM_MISMATCH")
        if not draft.draft_sha256 or not draft.bundle_sha256:
            errors.append("MISSING_DIGEST")
        if not draft.body.strip():
            errors.append("EMPTY_BODY")
        if draft.native_format == "text" and draft.title:
            errors.append("X_POST_MUST_NOT_HAVE_TITLE")
        for ref in draft.media_refs:
            if ABSOLUTE_PATH_RE.search(ref) or not ref.startswith(("repo://", "project://")):
                errors.append(f"NON_LOGICAL_REF:{ref[:48]}")
        scan = json.dumps(draft.as_dict(), ensure_ascii=False)
        if SECRET_SHAPED_RE.search(scan):
            errors.append("SECRET_SHAPED_VALUE_IN_DRAFT")
        if ABSOLUTE_PATH_RE.search(scan):
            errors.append("ABSOLUTE_HOST_PATH_IN_DRAFT")
        return ValidationResult(ok=not errors, errors=tuple(errors))

    def prepare_handoff(self, draft: PlatformDraft) -> dict[str, Any]:
        """Terminal state of a manual-only adapter. Never publishes, no URL."""
        receipt: dict[str, Any] = {
            "schema": DELIVERY_SCHEMA,
            "platform_id": draft.platform_id,
            "strategy_platform": draft.strategy_platform,
            "pipeline": draft.pipeline,
            "package_id": draft.package_id,
            "bundle_sha256": draft.bundle_sha256,
            "adapter_version": ADAPTER_VERSION,
            "adapter_channel": draft.channel,
            "draft_ref": f"project://delivery/{draft.platform_id}/{draft.draft_sha256[:16]}.json",
            "draft_sha256": draft.draft_sha256,
            "publish_mode": "MANUAL_ONLY",
            "publication_state": "AWAITING_MANUAL_PUBLISH",
            "publish_authorized": False,
            "human_review": "PENDING",
            "metric_snapshot_ref": None,
            "media_refs": list(draft.media_refs),
            "blockers": list(draft.blockers),
            "warnings": list(draft.warnings),
            "registry_row": draft.registry_row,
            "suggested_tags": list(draft.suggested_tags),
            "suggested_digest": draft.digest,
            "rights_note": "delivery channel requires the operator's own logged-in browser session",
        }
        # Contract: no secrets and no absolute host paths in a receipt.
        scan = json.dumps(receipt, ensure_ascii=False)
        if SECRET_SHAPED_RE.search(scan) or ABSOLUTE_PATH_RE.search(scan):
            raise AdapterError("回执包含密钥形态或绝对路径")
        return receipt

    @staticmethod
    def verify_authorization(authorization: dict[str, Any], draft: PlatformDraft) -> tuple[bool, list[str]]:
        required = ("platform_id", "account", "package_id", "bundle_sha256",
                    "reviewer", "expires_at", "scope", "publish_mode", "fresh")
        missing = [k for k in required if not authorization.get(k)]
        if missing:
            return False, ["AUTHORIZATION_MISSING:" + ",".join(missing)]
        errors: list[str] = []
        if authorization.get("platform_id") != draft.platform_id:
            errors.append("AUTHORIZATION_PLATFORM_MISMATCH")
        if authorization.get("package_id") != draft.package_id:
            errors.append("AUTHORIZATION_PACKAGE_MISMATCH")
        if authorization.get("bundle_sha256") != draft.bundle_sha256:
            errors.append("AUTHORIZATION_BUNDLE_MISMATCH")
        if authorization.get("fresh") is not True:
            errors.append("AUTHORIZATION_ALREADY_CONSUMED")
        if authorization.get("publish_mode") != "MANUAL_ONLY":
            errors.append("AUTHORIZATION_MODE_NOT_IMPLEMENTED")
        return not errors, errors

    def publish(self, draft: PlatformDraft, authorization: dict[str, Any] | None = None) -> dict[str, Any]:
        """Manual-only adapter: publication is never performed here."""
        ok, errors = self.verify_authorization(authorization or {}, draft)
        if not ok:
            raise PublishAuthorizationError("PUBLISH_REFUSED:" + ";".join(errors))
        # Even a fully verified authorization cannot publish from this adapter:
        # the contract requires a separately approved platform adapter.
        raise PublishAuthorizationError(
            "PUBLISH_REFUSED:NO_APPROVED_PLATFORM_ADAPTER — manual-only adapter has no PUBLISHED branch"
        )

    def read_metrics(self, receipt: dict[str, Any]) -> None:
        return None


def supported_platform_ids() -> tuple[str, ...]:
    """Registry-row graphic platforms only (the conservative default)."""
    _ensure_views()
    return tuple(REGISTRY_GRAPHIC_PLATFORMS)


def delivery_platform_ids() -> tuple[str, ...]:
    """Every graphic platform this adapter can shape, registry row or not."""
    _ensure_views()
    return tuple(DELIVERY_GRAPHIC_PLATFORMS)


def channel_catalog() -> dict[str, Any]:
    _ensure_views()
    return {
        "registry_rows": dict(REGISTRY_GRAPHIC_PLATFORMS),
        "delivery_only_rows": {
            pid: row for pid, row in DELIVERY_GRAPHIC_PLATFORMS.items()
            if row.get("registry_row") != "true"
        },
        "capability_matrix": graphic_specs.capability_matrix(),
        "excluded_platforms": graphic_specs.load_specs()["excluded"],
        "video_delivery_platforms": dict(VIDEO_DELIVERY_PLATFORMS),
        "extra_delivery_channels": dict(EXTRA_DELIVERY_CHANNELS),
        "note": "Xiaohongshu belongs to the VIDEO line; extra_delivery_channels are delivery targets only, never registry rows",
    }


def build_all(package: dict[str, Any], account: dict[str, Any],
              platform_ids: Iterable[str] | None = None) -> list[tuple[PlatformDraft, ValidationResult, dict[str, Any]]]:
    results = []
    for pid in platform_ids or delivery_platform_ids():
        adapter = MultiChannelAdapter(pid, expected_bundle_sha256=str(package.get("bundle_sha256") or ""))
        draft = adapter.pack(package, account)
        validation = adapter.validate(draft)
        receipt = adapter.prepare_handoff(draft)
        results.append((draft, validation, receipt))
    return results
