#!/usr/bin/env python3
"""Create the structured content-review receipt after human/agent review.

This command refuses to mark a review as passed when the report still contains
pending/TODO/blocking markers or lacks the required review dimensions.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from article_integrity import sha256_file, stable_sha256_file


REQUIRED_MARKERS = {
    "content": ("内容审", "内容"),
    "facts": ("事实", "事实核验"),
    "sensitivity": ("合规", "敏感"),
    "spelling": ("错别字", "校对"),
    # Accept the workflow's documented review vocabulary instead of making a
    # semantically valid report fail on one exact wording choice.
    "humanizer": ("AI 味", "AI味", "人工修改", "人工化表达", "人性化表达", "去AI化"),
}

REVIEWER_TYPES = {"agent", "human"}
DIGEST_MODE = "stable-text-v1"
PASS_MARKERS = r"(?:通过|已通过|passed|完成|已完成|已修改|无问题|无异常|已人工修改|人工修改完成|已去\s*AI\s*味)"
BLOCKING_MARKERS = r"(?:pending|todo|待审核|待处理|未通过|不通过|blocked|阻断)"


def _report_check_passed(report: str, markers: tuple[str, ...]) -> bool:
    """Require an explicit local pass result instead of a keyword mention."""

    lines = report.splitlines()
    for marker in markers:
        match = re.search(
            rf"{re.escape(marker)}\s*(?:检查)?\s*[:：|]\s*([^\r\n。；;|]{{0,80}})",
            report,
            flags=re.IGNORECASE,
        )
        if match:
            result = match.group(1)
            if not re.search(BLOCKING_MARKERS, result, flags=re.IGNORECASE) and re.search(PASS_MARKERS, result, flags=re.IGNORECASE):
                return True

        # The canonical report template uses a section heading followed by
        # explicit ``- 通过`` bullets.  Inspect only the bounded section
        # window, so a keyword mentioned in unrelated prose cannot satisfy a
        # review dimension accidentally.
        for index, line in enumerate(lines):
            if not re.search(r"^\s*#{1,6}\s*", line):
                continue
            if marker not in line:
                continue
            section: list[str] = []
            for candidate in lines[index + 1:index + 13]:
                if re.match(r"^\s*#{1,6}\s*", candidate):
                    break
                section.append(candidate)
            # Only review-result rows are authoritative.  Do not let a later
            # prose conclusion such as “未发现阻断级问题” contaminate the
            # spelling/content section's own result window.
            result_rows = [candidate for candidate in section if re.match(r"^\s*(?:[-*|]|(?:status|状态)\b)", candidate, flags=re.IGNORECASE)]
            window = "\n".join(result_rows)
            if re.search(BLOCKING_MARKERS, window, flags=re.IGNORECASE):
                continue
            if re.search(PASS_MARKERS, window, flags=re.IGNORECASE):
                return True
    return False


def _has_unresolved_marker(report: str) -> bool:
    return bool(re.search(
        rf"(?im)(?:status|状态|内容审|事实核验|合规|敏感|错别字|校对|AI\s*味)\s*(?:检查)?\s*[:：|]\s*[^\r\n。；;|]*{BLOCKING_MARKERS}",
        report,
    ))


def _load_review_checks(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _structured_blockers(
    checks_doc: dict,
    article_digest: str = "",
    report_digest: str = "",
    legacy_article_digest: str = "",
    legacy_report_digest: str = "",
) -> list[str]:
    errors: list[str] = []
    if not checks_doc:
        return errors
    if checks_doc.get("status") != "passed":
        errors.append("review-checks.json status 不是 passed")
    if str(checks_doc.get("reviewer_type", "")).strip() not in REVIEWER_TYPES:
        errors.append("review-checks.json 缺少有效 reviewer_type（agent/human）")
    if not str(checks_doc.get("reviewer", "")).strip():
        errors.append("review-checks.json 缺少 reviewer")
    if not str(checks_doc.get("reviewed_at", "")).strip():
        errors.append("review-checks.json 缺少 reviewed_at")
    stable_mode = checks_doc.get("digest_mode") == DIGEST_MODE
    expected_article = article_digest if stable_mode else legacy_article_digest
    expected_report = report_digest if stable_mode else legacy_report_digest
    if checks_doc.get("article_digest") and checks_doc.get("article_digest") != expected_article:
        errors.append("review-checks.json 的 article_digest 与当前 article.md 不一致")
    if checks_doc.get("report_digest") and checks_doc.get("report_digest") != expected_report:
        errors.append("review-checks.json 的 report_digest 与当前 review-report.md 不一致")
    checks = checks_doc.get("checks")
    if not isinstance(checks, dict):
        errors.append("review-checks.json 缺少 checks 对象")
    else:
        for key in REQUIRED_MARKERS:
            if checks.get(key) != "passed":
                errors.append(f"review-checks.json 未通过 {key}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, help="文章目录")
    parser.add_argument("--approve", action="store_true", help="检查通过后写入 passed 回执")
    parser.add_argument("--reviewer-type", choices=sorted(REVIEWER_TYPES), default="agent")
    parser.add_argument("--reviewer", default="codex")
    args = parser.parse_args()
    article = Path(args.article).expanduser().resolve()
    report_path = article / "review-report.md"
    output = article / "review-evidence.json"
    report = report_path.read_text(encoding="utf-8", errors="replace") if report_path.is_file() else ""
    article_path = article / "article.md"
    if args.approve and not article_path.is_file():
        print("REVIEW EVIDENCE BLOCKED: 缺少 article.md，不能为不存在的定稿签发回执")
        return 1
    # Review and revision receipts must use the same platform-stable digest.
    # A no-op evidence append may normalize CRLF/LF without changing reviewed
    # content; raw byte hashes would incorrectly invalidate the review while
    # content-revision.json remains valid.
    article_digest = stable_sha256_file(article_path) if article_path.is_file() else ""
    report_digest = stable_sha256_file(report_path) if report_path.is_file() else ""
    legacy_article_digest = sha256_file(article_path) if article_path.is_file() else ""
    legacy_report_digest = sha256_file(report_path) if report_path.is_file() else ""
    checks = {
        key: "passed" if _report_check_passed(report, markers) else "missing"
        for key, markers in REQUIRED_MARKERS.items()
    }
    structured_path = article / "review-checks.json"
    structured = _load_review_checks(structured_path)
    if structured.get("status") in {"", "pending", "draft"}:
        # matrix_init creates a pending template; approval fills it from the
        # current report while preserving an explicit reviewer identity.
        structured = {}
    if structured:
        structured_errors = _structured_blockers(
            structured,
            article_digest,
            report_digest,
            legacy_article_digest,
            legacy_report_digest,
        )
        stale = any("digest 与当前" in error for error in structured_errors)
        needs_migration = structured.get("digest_mode") != DIGEST_MODE
        if args.approve and (stale or needs_migration):
            # A new explicit approval replaces an expired or legacy receipt
            # and binds it to the current report/article, without asking
            # callers to delete provenance manually.  Legacy raw receipts
            # remain readable by the gate, but an explicit re-approval
            # upgrades the real artifact to the stable digest contract.
            structured = {}
            blockers = False
        else:
            checks = structured.get("checks", checks) if isinstance(structured.get("checks"), dict) else checks
            blockers = bool(structured_errors)
    else:
        # Only treat explicit status lines as blocking.  Ordinary prose such
        # as “未发现待处理事项” must not invalidate an otherwise passed report.
        blockers = bool(re.search(r"(?im)^\s*[-*]\s*(?:🔴|阻断|BLOCKING)\b", report) or _has_unresolved_marker(report))
    # A previously passed structured review must not mask a newly edited
    # report that contains an explicit pending marker.
    if _has_unresolved_marker(report):
        blockers = True
    if blockers:
        for key in checks:
            if checks[key] == "passed":
                checks[key] = "blocked"
    status = "passed" if args.approve and report and not blockers and all(value == "passed" for value in checks.values()) else "pending"
    if args.approve and status == "passed" and not structured:
        structured = {
            "schema_version": 1,
            "status": "passed",
            "reviewer_type": args.reviewer_type,
            "reviewer": args.reviewer.strip() or "codex",
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "digest_mode": DIGEST_MODE,
            "article_digest": article_digest,
            "report_digest": report_digest,
            "checks": checks,
            "findings": [],
        }
    payload = {
        "schema_version": 1,
        "status": status,
        "checks": checks,
        "blocking_markers": blockers,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "digest_mode": DIGEST_MODE,
    }
    payload["article_digest"] = article_digest
    payload["report_digest"] = report_digest
    if args.approve and status != "passed":
        print("REVIEW EVIDENCE BLOCKED")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.approve and structured:
        structured_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"REVIEW EVIDENCE {'WRITTEN' if args.approve else 'CHECKED'}: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
