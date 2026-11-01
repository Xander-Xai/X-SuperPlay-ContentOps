"""The one place that says what a platform is and which account may use it.

Before this module, platform facts were spread across account DNA files, a
publish-policy constant, a producer table inside ``scripts/account_route.py``
and per-project frames. Adding a platform meant editing several of them and
hoping none disagreed.

The registry is data. A platform declares its content types, the pipeline that
produces them, the accounts allowed to use it, how a draft is delivered, and
how honest its current state is. A status is a claim about evidence, not about
configuration: ``PLANNED`` means no code, ``INTEGRATED`` means code and offline
tests, ``TESTED`` means a real local run, ``PILOT_READY`` means a real platform
draft, and ``PRODUCTION_ACCEPTED`` means a published work with a receipt.

Nothing here publishes, renders or spends. It answers questions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REGISTRY_DIR = Path("config") / "registry"
ACCOUNT_SCHEMA = "contentops.account-registry/v1"
PLATFORM_SCHEMA = "contentops.platform-registry/v1"

STATUS_VALUES: Tuple[str, ...] = (
    "PLANNED",
    "INTEGRATED",
    "TESTED",
    "PILOT_READY",
    "PRODUCTION_ACCEPTED",
)
DRAFT_SUPPORT_VALUES: Tuple[str, ...] = (
    "NONE",
    "MANUAL_PACKAGE",
    "WEIGHT_PLATFORM_DRAFT",
)
PUBLISH_MODES: Tuple[str, ...] = (
    "NOT_IMPLEMENTED",
    "MANUAL_ONLY",
    "DRAFT_ONLY",
)
METRIC_MODES: Tuple[str, ...] = ("NONE", "MANUAL_RECORD", "API")


class RegistryError(Exception):
    """A refusal with a code. Callers branch on the code, not the prose."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class AccountIdentity:
    account_slug: str
    internal_ids: Tuple[str, ...]
    display_name: str
    aliases: Tuple[str, ...]
    role: str
    dna: str
    platform_accounts: Dict[str, str]
    note: str = ""

    def identifiers(self) -> Tuple[str, ...]:
        return (self.account_slug, *self.internal_ids, self.display_name, *self.aliases)


@dataclass(frozen=True)
class PlatformEntry:
    platform_id: str
    strategy_platform: str
    content_types: Tuple[str, ...]
    pipeline: str
    accounts: Tuple[str, ...]
    draft_support: str
    publish_mode: str
    manual_review: bool
    metrics: str
    status: str
    owner: str
    evidence: Tuple[str, ...]
    not_claimed: str = ""

    def allows(self, account_slug: str) -> bool:
        return account_slug in self.accounts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "platform_id": self.platform_id,
            "strategy_platform": self.strategy_platform,
            "content_types": list(self.content_types),
            "pipeline": self.pipeline,
            "accounts": list(self.accounts),
            "draft_support": self.draft_support,
            "publish_mode": self.publish_mode,
            "manual_review": self.manual_review,
            "metrics": self.metrics,
            "status": self.status,
            "owner": self.owner,
            "evidence": list(self.evidence),
            "not_claimed": self.not_claimed,
        }


def _read(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise RegistryError("REGISTRY_MISSING", path.as_posix())
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryError("REGISTRY_MALFORMED", f"{path.as_posix()}: {exc}") from None
    if not isinstance(payload, dict):
        raise RegistryError("REGISTRY_MALFORMED", f"{path.as_posix()} must be an object")
    return payload


def _strings(value: Any, field: str, where: str) -> Tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise RegistryError("REGISTRY_MALFORMED", f"{where}.{field} must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise RegistryError("REGISTRY_MALFORMED", f"{where}.{field} must contain non-empty strings")
    return tuple(item.strip() for item in value)


def load_accounts(root: Path) -> Dict[str, AccountIdentity]:
    payload = _read(Path(root) / REGISTRY_DIR / "accounts.json")
    if payload.get("schema") != ACCOUNT_SCHEMA:
        raise RegistryError("REGISTRY_MALFORMED",
                            f"accounts.json schema must be {ACCOUNT_SCHEMA!r}")
    raw = payload.get("accounts")
    if not isinstance(raw, list) or not raw:
        raise RegistryError("REGISTRY_MALFORMED", "accounts.json has no accounts")
    accounts: Dict[str, AccountIdentity] = {}
    seen_ids: Dict[str, str] = {}
    for index, item in enumerate(raw, start=1):
        where = f"accounts[{index}]"
        if not isinstance(item, dict):
            raise RegistryError("REGISTRY_MALFORMED", f"{where} must be an object")
        slug = str(item.get("account_slug") or "").strip()
        if not slug:
            raise RegistryError("REGISTRY_MALFORMED", f"{where}.account_slug is empty")
        if slug in accounts:
            raise RegistryError("ACCOUNT_DUPLICATE", slug)
        internal = _strings(item.get("internal_ids"), "internal_ids", where)
        aliases = tuple(str(alias).strip() for alias in item.get("aliases") or []
                        if str(alias).strip())
        display = str(item.get("display_name") or "").strip()
        if not display:
            raise RegistryError("REGISTRY_MALFORMED", f"{where}.display_name is empty")
        for identifier in (slug, display, *internal, *aliases):
            owner = seen_ids.get(identifier)
            if owner is not None and owner != slug:
                raise RegistryError(
                    "ACCOUNT_IDENTIFIER_AMBIGUOUS",
                    f"{identifier!r} names both {owner!r} and {slug!r}; identity is "
                    f"recorded explicitly and is never resolved by similarity")
            seen_ids[identifier] = slug
        platform_accounts = item.get("platform_accounts") or {}
        if not isinstance(platform_accounts, dict):
            raise RegistryError("REGISTRY_MALFORMED",
                                f"{where}.platform_accounts must be an object")
        accounts[slug] = AccountIdentity(
            account_slug=slug,
            internal_ids=internal,
            display_name=display,
            aliases=aliases,
            role=str(item.get("role") or ""),
            dna=str(item.get("dna") or ""),
            platform_accounts={str(k): str(v) for k, v in platform_accounts.items()},
            note=str(item.get("note") or ""),
        )
    return accounts


def load_platforms(root: Path, *, accounts: Optional[Dict[str, AccountIdentity]] = None
                   ) -> Dict[str, PlatformEntry]:
    payload = _read(Path(root) / REGISTRY_DIR / "platforms.json")
    if payload.get("schema") != PLATFORM_SCHEMA:
        raise RegistryError("REGISTRY_MALFORMED",
                            f"platforms.json schema must be {PLATFORM_SCHEMA!r}")
    declared_statuses = tuple(payload.get("status_values") or STATUS_VALUES)
    if set(declared_statuses) != set(STATUS_VALUES):
        raise RegistryError("REGISTRY_MALFORMED",
                            f"status_values must be exactly {list(STATUS_VALUES)}")
    raw = payload.get("platforms")
    if not isinstance(raw, list) or not raw:
        raise RegistryError("REGISTRY_MALFORMED", "platforms.json has no platforms")
    accounts = accounts if accounts is not None else load_accounts(root)
    platforms: Dict[str, PlatformEntry] = {}
    for index, item in enumerate(raw, start=1):
        where = f"platforms[{index}]"
        if not isinstance(item, dict):
            raise RegistryError("REGISTRY_MALFORMED", f"{where} must be an object")
        platform_id = str(item.get("platform_id") or "").strip()
        if not platform_id:
            raise RegistryError("REGISTRY_MALFORMED", f"{where}.platform_id is empty")
        if platform_id in platforms:
            raise RegistryError("PLATFORM_DUPLICATE", platform_id)
        status = str(item.get("status") or "")
        if status not in STATUS_VALUES:
            raise RegistryError("PLATFORM_STATUS_INVALID",
                                f"{platform_id}: {status!r} not in {list(STATUS_VALUES)}")
        draft_support = str(item.get("draft_support") or "")
        if draft_support not in DRAFT_SUPPORT_VALUES:
            raise RegistryError("PLATFORM_FIELD_INVALID",
                                f"{platform_id}.draft_support={draft_support!r}")
        publish_mode = str(item.get("publish_mode") or "")
        if publish_mode not in PUBLISH_MODES:
            raise RegistryError("PLATFORM_FIELD_INVALID",
                                f"{platform_id}.publish_mode={publish_mode!r}")
        metrics = str(item.get("metrics") or "")
        if metrics not in METRIC_MODES:
            raise RegistryError("PLATFORM_FIELD_INVALID",
                                f"{platform_id}.metrics={metrics!r}")
        if item.get("manual_review") is not True:
            raise RegistryError("PLATFORM_MANUAL_REVIEW_DISABLED",
                                f"{platform_id} must keep manual_review=true")
        account_slugs = tuple(str(value).strip() for value in item.get("accounts") or [])
        missing = [slug for slug in account_slugs if slug not in accounts]
        if missing:
            raise RegistryError("PLATFORM_ACCOUNT_UNKNOWN",
                                f"{platform_id} names unknown accounts: {missing}")
        if status != "PLANNED" and not account_slugs:
            raise RegistryError("PLATFORM_ACCOUNT_MISSING",
                                f"{platform_id} is {status} but names no account")
        strategy_platform = str(item.get("strategy_platform") or "").strip()
        if not strategy_platform:
            raise RegistryError(
                "PLATFORM_FIELD_INVALID",
                f"{platform_id}.strategy_platform is empty; every local entry must name "
                f"the strategy platform it belongs to, so a split entry cannot become "
                f"a second platform")
        platforms[platform_id] = PlatformEntry(
            platform_id=platform_id,
            strategy_platform=strategy_platform,
            content_types=_strings(item.get("content_types"), "content_types", where),
            pipeline=str(item.get("pipeline") or ""),
            accounts=account_slugs,
            draft_support=draft_support,
            publish_mode=publish_mode,
            manual_review=True,
            metrics=metrics,
            status=status,
            owner=str(item.get("owner") or ""),
            evidence=tuple(str(value) for value in item.get("evidence") or []),
            not_claimed=str(item.get("not_claimed") or ""),
        )
        if not platforms[platform_id].pipeline:
            raise RegistryError("PLATFORM_FIELD_INVALID",
                                f"{platform_id}.pipeline is empty")
    return platforms


def resolve_account(root: Path, identifier: str) -> AccountIdentity:
    """Resolve exactly, never by similarity. An alias is recorded, not guessed."""
    needle = (identifier or "").strip()
    if not needle:
        raise RegistryError("ACCOUNT_REQUIRED", "no account identifier was given")
    for account in load_accounts(root).values():
        if needle in account.identifiers():
            return account
    raise RegistryError("ACCOUNT_UNKNOWN",
                        f"{needle!r} is not a recorded account identifier")


def account_for_display(root: Path, display_name: str) -> AccountIdentity:
    return resolve_account(root, display_name)


def entries_for_format(root: Path, content_format: str) -> List[PlatformEntry]:
    fmt = (content_format or "").strip()
    if not fmt:
        raise RegistryError("CONTENT_FORMAT_REQUIRED", "no content format was given")
    entries = [entry for entry in load_platforms(root).values()
               if entry.pipeline == fmt]
    if not entries:
        raise RegistryError(
            "CONTENT_FORMAT_UNKNOWN",
            f"{fmt!r} is not a pipeline any platform registers")
    return entries


def account_allows_format(root: Path, account_slug: str, content_format: str,
                          *, require_available: bool = True) -> PlatformEntry:
    """The platform entry that lets this account use this content format.

    A format may be served by several platforms (VIDEO by douyin, bilibili and
    xiaohongshu video). The format chooses the *pipeline*; the delivery platform
    is a later choice. This function only proves the account is declared for at
    least one available platform of that format.
    """
    candidates = [entry for entry in entries_for_format(root, content_format)
                  if entry.allows(account_slug)]
    if not candidates:
        raise RegistryError(
            "CONTENT_FORMAT_NOT_ALLOWED",
            f"{account_slug!r} is not declared for content format {content_format!r}")
    available = [entry for entry in candidates if entry.status != "PLANNED"]
    if require_available and not available:
        raise RegistryError(
            "CONTENT_FORMAT_NOT_AVAILABLE",
            f"content format {content_format!r} is only {candidates[0].status} for "
            f"{account_slug!r}; configuration alone is not an implementation")
    return (available or candidates)[0]


def formats_for_account(root: Path, account_slug: str) -> Tuple[str, ...]:
    formats: List[str] = []
    for entry in load_platforms(root).values():
        if entry.allows(account_slug) and entry.pipeline not in formats:
            formats.append(entry.pipeline)
    return tuple(formats)


def validate_registry(root: Path) -> List[str]:
    """Structural failures. Empty means the two registries agree."""
    failures: List[str] = []
    try:
        accounts = load_accounts(root)
    except RegistryError as exc:
        return [f"accounts: {exc.detail}"]
    for slug, account in accounts.items():
        dna = Path(root) / account.dna
        if account.dna and not dna.is_file():
            failures.append(f"accounts[{slug}].dna does not exist: {account.dna}")
    try:
        platforms = load_platforms(root, accounts=accounts)
    except RegistryError as exc:
        return failures + [f"platforms: {exc.detail}"]
    for entry in platforms.values():
        for account_slug in entry.accounts:
            label = accounts[account_slug].platform_accounts.get(entry.platform_id)
            if not label:
                failures.append(
                    f"{entry.platform_id}: account {account_slug} has no "
                    f"platform_accounts label")
        for path in entry.evidence:
            if path.startswith(("projects/", "scripts/", "tests/", "src/", "vendor/",
                                "config/", "docs/")) and not (Path(root) / path).exists():
                failures.append(f"{entry.platform_id}: evidence path missing: {path}")
    return failures


def summarise(root: Path) -> Dict[str, Any]:
    accounts = load_accounts(root)
    platforms = load_platforms(root, accounts=accounts)
    return {
        "schema": "contentops.registry-summary/v1",
        "accounts": [
            {
                "account_slug": account.account_slug,
                "internal_ids": list(account.internal_ids),
                "display_name": account.display_name,
                "role": account.role,
                "content_formats": list(formats_for_account(root, account.account_slug)),
            }
            for account in accounts.values()
        ],
        "platforms": [entry.to_dict() for entry in platforms.values()],
    }
