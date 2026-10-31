"""Offline mapping from operator drafts to the observed X post record shape.

This small compatibility boundary does not validate upstream readiness, approve,
or publish. The upstream track is unmerged; this mapping is not an integration.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from urllib.parse import urlsplit

X_POST_SCHEMA = "contentops.x-post/v1"
SUPPORTED_ACCOUNTS = frozenset({"x-superplay-english"})
_REQUIRED = frozenset({"account_id", "draft", "source_url"})
_ALLOWED = _REQUIRED | {"schema", "review_status", "publication_status"}


def _valid_source(source):
    try:
        value = urlsplit(source)
        return value.scheme == "https" and bool(value.hostname) and not value.username and not value.password and not any(c.isspace() for c in source)
    except (ValueError, TypeError):
        return False


class ContractError(ValueError):
    """Input cannot be mapped without losing or inventing meaning."""


def map_draft_to_x_post(draft: dict[str, Any]) -> dict[str, Any]:
    """Return an unreviewed x-post/v1 record, preserving the complete source draft."""
    if not isinstance(draft, dict):
        raise ContractError("draft must be an object")
    unknown = set(draft) - _ALLOWED
    if unknown:
        raise ContractError(f"unknown fields: {', '.join(sorted(unknown))}")
    missing = _REQUIRED - set(draft)
    if missing:
        raise ContractError(f"missing required fields: {', '.join(sorted(missing))}")
    if draft.get("schema") not in (None, "contentops.x-organic-growth/v1"):
        raise ContractError("unsupported operator draft schema")
    account = draft["account_id"]
    if not isinstance(account, str) or account not in SUPPORTED_ACCOUNTS:
        raise ContractError("unknown account_id")
    text = draft["draft"]
    if not isinstance(text, str) or not text.strip():
        raise ContractError("draft must be non-empty text")
    source = draft["source_url"]
    if not isinstance(source, str) or not _valid_source(source):
        raise ContractError("source_url must be an https URL")
    if draft.get("review_status", "UNREVIEWED") != "UNREVIEWED":
        raise ContractError("only UNREVIEWED drafts can be mapped")
    if draft.get("publication_status", "NOT_PUBLISHED") != "NOT_PUBLISHED":
        raise ContractError("mapping cannot claim publication")

    return {
        "schema": X_POST_SCHEMA,
        "account_slug": account,
        "post_copy": {"parts": [text]},
        "status": "draft",
        "status_url": None,
        "review_status": "UNREVIEWED",
        "provenance": {"source": source},
        "source_draft": deepcopy(draft),
    }
