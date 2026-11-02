"""Platform, account and pipeline registries.

The registry answers which platform a content format belongs to, which account
may use it, how a draft is delivered and how honest its current status is. It
does not render, publish or spend.
"""

from .registry import (  # noqa: F401
    ACCOUNT_SCHEMA,
    PLATFORM_SCHEMA,
    AccountIdentity,
    PlatformEntry,
    RegistryError,
    account_allows_format,
    account_for_display,
    entries_for_format,
    formats_for_account,
    load_accounts,
    load_platforms,
    resolve_account,
    summarise,
    validate_registry,
)

__all__ = [
    "ACCOUNT_SCHEMA",
    "PLATFORM_SCHEMA",
    "AccountIdentity",
    "PlatformEntry",
    "RegistryError",
    "account_allows_format",
    "account_for_display",
    "entries_for_format",
    "formats_for_account",
    "load_accounts",
    "load_platforms",
    "resolve_account",
    "summarise",
    "validate_registry",
]
