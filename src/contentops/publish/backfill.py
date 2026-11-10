"""Recording that a person actually published, after the fact.

The publisher can only ever hand a person a package and stop at
``AWAITING_MANUAL_PUBLISH``. Publication happens outside this repository, on
the platform, by a human. This module is where that human act comes back into
the record — honestly, or not at all.

A backfill receipt binds, for one piece of content on one platform:

- the real post URL (validated per platform; on platforms whose URL encodes
  the account, a claimed ``account_handle`` must match the URL — somebody
  else's post is not evidence this account published),
- the observed publication time,
- the exact published version (artifact sha256 and/or source commit), so a
  later edit cannot silently replace what was reviewed,
- who confirmed it, and when,
- and, optionally, an independent readback: a later check that the URL is
  live and belongs to the account.

State machine: a record starts at ``PUBLISHED_RECORDED`` and only a readback
moves it to ``PUBLISHED_VERIFIED``. Neither state is produced by any code path
that touches the network — the readback is a human observation recorded here,
never an automated scrape.

X posts keep their existing ``scripts/x_post.py --mark-published`` flow, which
already demands a real status URL. This module is the platform-neutral layer
for every other track, and it exists because a publish count that cannot name
its URLs, times, versions and confirmer is marketing, not evidence.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.publish-backfill/v1"

#: A record exists because a person says so; a readback makes it independent.
STATUS_RECORDED = "PUBLISHED_RECORDED"
STATUS_VERIFIED = "PUBLISHED_VERIFIED"

#: Platforms with a post-URL shape strict enough to validate. A platform
#: without a rule here must be added to this table before its receipts exist,
#: not discovered missing after they do.
URL_RULES: Dict[str, re.Pattern] = {
    "x": re.compile(r"^https://x\.com/([A-Za-z0-9_]{1,15})/status/\d+$"),
    "bilibili": re.compile(r"^https://www\.bilibili\.com/video/[A-Za-z0-9]{8,14}(?:\?.*)?$"),
    "xiaohongshu": re.compile(
        r"^https://www\.xiaohongshu\.com/(?:explore|discovery/item)/[0-9a-f]{24}(?:\?.*)?$"),
    "douyin": re.compile(r"^https://www\.douyin\.com/video/\d+(?:\?.*)?$"),
    "gzh": re.compile(r"^https://mp\.weixin\.qq\.com/s(?:/|\?)[\w\-=&%]+"),
    "shipinhao": re.compile(r"^https://channels\.weixin\.qq\.com/[\w\-=&%/]+"),
}

#: Platforms whose URL encodes the posting account, so a claimed account can
#: be checked against the URL itself. Other platforms accept ``account_handle``
#: as prose; their handle binding happens at the account-DNA layer.
HANDLE_BINDING: Dict[str, int] = {"x": 1}

READBACK_METHODS = ("MANUAL_INSPECT", "SCREENSHOT", "PLATFORM_EXPORT")
READBACK_STATUSES = ("VERIFIED", "FAILED", "UNAVAILABLE")

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

REQUIRED_FIELDS = ("platform", "content_id", "post_url", "published_at", "confirmed_by")


class BackfillError(Exception):
    """A refusal with a code. Callers branch on the code, not the prose."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _now(now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise BackfillError("PUBLISHED_AT_INVALID", "empty timestamp")
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise BackfillError("PUBLISHED_AT_INVALID", f"{value!r} is not an ISO-8601 timestamp")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _receipt_path(receipts_dir: Path, platform: str, content_id: str) -> Path:
    stem = _SAFE_NAME.sub("_", f"{platform}-{content_id}")
    return Path(receipts_dir) / f"backfill-{stem}.json"


def _validate_readback(readback: Any, *, now: datetime) -> Dict[str, Any]:
    if not isinstance(readback, dict):
        raise BackfillError("READBACK_INVALID", "readback must be a mapping")
    status = str(readback.get("status") or "")
    if status not in READBACK_STATUSES:
        raise BackfillError(
            "READBACK_INVALID", f"readback.status must be one of {READBACK_STATUSES}")
    method = str(readback.get("method") or "")
    if method not in READBACK_METHODS:
        raise BackfillError(
            "READBACK_INVALID", f"readback.method must be one of {READBACK_METHODS}")
    checked = _parse_time(readback.get("checked_at"))
    if checked > now:
        raise BackfillError("READBACK_INVALID", "readback.checked_at is in the future")
    clean: Dict[str, Any] = {
        "status": status,
        "method": method,
        "checked_at": _now(checked),
    }
    evidence = str(readback.get("evidence_ref") or "").strip()
    if status == "VERIFIED" and not evidence:
        raise BackfillError(
            "READBACK_INVALID",
            "a VERIFIED readback needs evidence_ref (screenshot path, export file, ...)")
    if evidence:
        clean["evidence_ref"] = evidence
    note = str(readback.get("note") or "").strip()
    if note:
        clean["note"] = note
    return clean


def _validate(payload: Dict[str, Any], *, now: datetime) -> Dict[str, Any]:
    declared = payload.get("schema")
    if declared is not None and declared != SCHEMA:
        raise BackfillError("BACKFILL_SCHEMA_UNKNOWN", f"expected {SCHEMA!r}, got {declared!r}")

    platform = str(payload.get("platform") or "").strip().lower()
    if platform not in URL_RULES:
        raise BackfillError(
            "PLATFORM_UNSUPPORTED",
            f"{platform!r} has no URL rule; add it to backfill.URL_RULES first")
    content_id = str(payload.get("content_id") or "").strip()
    if not content_id:
        raise BackfillError("CONTENT_ID_REQUIRED", "content_id identifies what was published")

    url = str(payload.get("post_url") or "").strip()
    if not url:
        raise BackfillError("POST_URL_REQUIRED", "a backfill without the real URL is not evidence")
    match = URL_RULES[platform].match(url)
    if not match:
        raise BackfillError("POST_URL_INVALID", f"{url!r} does not match the {platform} URL shape")

    account_handle = str(payload.get("account_handle") or "").strip()
    document_account: Dict[str, Any] = {}
    if account_handle:
        document_account["account_handle"] = account_handle
        group = HANDLE_BINDING.get(platform)
        if group is not None:
            url_handle = match.group(group)
            if url_handle.lower() != account_handle.lstrip("@").lower():
                raise BackfillError(
                    "POST_URL_HANDLE_MISMATCH",
                    f"URL belongs to @{url_handle}, not @{account_handle}; somebody "
                    "else's post is not evidence this account published")

    confirmed_by = str(payload.get("confirmed_by") or "").strip()
    if not confirmed_by:
        raise BackfillError(
            "CONFIRMED_BY_REQUIRED",
            "a person must put their name on the claim that publication happened")

    published_at = _parse_time(payload.get("published_at"))
    if published_at > now:
        raise BackfillError("PUBLISHED_AT_IN_FUTURE", str(payload.get("published_at")))
    confirmed_at_raw = payload.get("confirmed_at")
    confirmed_at = _parse_time(confirmed_at_raw) if confirmed_at_raw else now
    if confirmed_at > now:
        raise BackfillError("CONFIRMED_AT_IN_FUTURE", str(confirmed_at_raw))

    document: Dict[str, Any] = {
        "schema": SCHEMA,
        "platform": platform,
        "content_id": content_id,
        "post_url": url,
        "published_at": _now(published_at),
        "confirmed_by": confirmed_by,
        "confirmed_at": _now(confirmed_at),
        "status": STATUS_RECORDED,
        "recorded_at": _now(now),
    }
    document.update(document_account)

    version: Dict[str, Any] = {}
    sha = str(payload.get("artifact_sha256") or "").strip().lower()
    if sha:
        if not _SHA256.match(sha):
            raise BackfillError("VERSION_HASH_INVALID", f"{sha!r} is not a sha-256 hex digest")
        version["artifact_sha256"] = sha
    commit = str(payload.get("source_commit") or "").strip().lower()
    if commit:
        if not _COMMIT.match(commit):
            raise BackfillError("SOURCE_COMMIT_INVALID", f"{commit!r} is not a git commit hash")
        version["source_commit"] = commit
    if version:
        document["published_version"] = version

    receipt_ref = str(payload.get("package_receipt_ref") or "").strip()
    if receipt_ref:
        document["package_receipt_ref"] = receipt_ref

    readback = payload.get("readback")
    if readback is not None:
        document["readback"] = _validate_readback(readback, now=now)

    note = str(payload.get("note") or "").strip()
    if note:
        document["note"] = note
    return document


def _check_against_package(document: Dict[str, Any], project: Optional[Path]) -> None:
    """Where the package receipt is readable, the backfill must agree with it."""
    ref = document.get("package_receipt_ref")
    if not ref or project is None:
        return
    package_path = Path(ref)
    if not package_path.is_absolute():
        package_path = Path(project) / package_path
    if not package_path.is_file():
        return
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if str(package.get("content_id") or "") != document["content_id"]:
        raise BackfillError(
            "PACKAGE_CONTENT_ID_MISMATCH",
            f"package {ref!r} is for {package.get('content_id')!r}, "
            f"not {document['content_id']!r}")
    built_at = package.get("built_at")
    if built_at:
        try:
            built = datetime.fromisoformat(str(built_at).replace("Z", "+00:00"))
        except ValueError:
            return
        if _parse_time(document["published_at"]) < built:
            raise BackfillError(
                "PUBLISHED_BEFORE_PACKAGE",
                f"published_at {document['published_at']} precedes package built_at {built_at}")


def record_backfill(payload: Dict[str, Any], receipts_dir: Path, *,
                    project: Optional[Path] = None,
                    now: Optional[datetime] = None) -> Dict[str, Any]:
    """Validate a human publication claim and write its receipt.

    Raises :class:`BackfillError` on any missing or contradictory field, and
    refuses to write a second receipt for the same (platform, content_id).
    """
    receipts_dir = Path(receipts_dir)
    moment = now or datetime.now(timezone.utc)
    document = _validate(payload, now=moment)
    _check_against_package(document, project)

    target = _receipt_path(receipts_dir, document["platform"], document["content_id"])
    if target.exists():
        raise BackfillError(
            "BACKFILL_DUPLICATE",
            f"{target.name} already exists; a platform publishes a piece of content once")
    receipts_dir.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    document["receipt"] = target
    return document


def verify_readback(receipt_path: Path, *, method: str, evidence_ref: str = "",
                    note: str = "", now: Optional[datetime] = None) -> Dict[str, Any]:
    """Record an independent later check that the URL is live, and verify."""
    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise BackfillError("BACKFILL_MISSING", receipt_path.as_posix())
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    if document.get("status") == STATUS_VERIFIED:
        return document
    moment = now or datetime.now(timezone.utc)
    readback = _validate_readback(
        {"status": "VERIFIED", "method": method, "checked_at": _now(moment),
         "evidence_ref": evidence_ref, "note": note},
        now=moment)
    document["readback"] = readback
    document["status"] = STATUS_VERIFIED
    receipt_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return document


def mark_readback_failed(receipt_path: Path, *, method: str, note: str,
                         now: Optional[datetime] = None) -> Dict[str, Any]:
    """Record that the readback could not confirm the post. Status stays RECORDED.

    A failed readback is information, not a deletion: the receipt keeps saying
    a person recorded the publication, and now also says the independent check
    disagreed. ``PUBLISHED_VERIFIED`` is only ever reached by a later successful
    readback.
    """
    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise BackfillError("BACKFILL_MISSING", receipt_path.as_posix())
    document = json.loads(receipt_path.read_text(encoding="utf-8"))
    moment = now or datetime.now(timezone.utc)
    readback = _validate_readback(
        {"status": "FAILED", "method": method, "checked_at": _now(moment), "note": note},
        now=moment)
    if not note:
        raise BackfillError(
            "READBACK_INVALID", "a failed readback must say what was actually observed")
    document["readback"] = readback
    receipt_path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return document


def load_backfill(receipt_path: Path) -> Dict[str, Any]:
    receipt_path = Path(receipt_path)
    if not receipt_path.is_file():
        raise BackfillError("BACKFILL_MISSING", receipt_path.as_posix())
    return json.loads(receipt_path.read_text(encoding="utf-8"))


def iter_backfills(receipts_dir: Path) -> List[Dict[str, Any]]:
    """Every backfill receipt in a directory, newest recorded first."""
    receipts_dir = Path(receipts_dir)
    if not receipts_dir.is_dir():
        return []
    documents = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(receipts_dir.glob("backfill-*.json"))
    ]
    return sorted(documents, key=lambda doc: str(doc.get("recorded_at") or ""), reverse=True)


def summary(receipts_dir: Path) -> Dict[str, Any]:
    """Publish counts that can survive an audit: per platform, per state."""
    documents = iter_backfills(receipts_dir)
    by_platform: Dict[str, Dict[str, int]] = {}
    for document in documents:
        platform = str(document.get("platform") or "unknown")
        bucket = by_platform.setdefault(platform, {STATUS_RECORDED: 0, STATUS_VERIFIED: 0})
        status = document.get("status")
        if status in bucket:
            bucket[status] += 1
    return {
        "schema": SCHEMA,
        "total": len(documents),
        "published_recorded": sum(1 for d in documents if d.get("status") == STATUS_RECORDED),
        "published_verified": sum(1 for d in documents if d.get("status") == STATUS_VERIFIED),
        "by_platform": by_platform,
    }
