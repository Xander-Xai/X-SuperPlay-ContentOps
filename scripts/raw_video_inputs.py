#!/usr/bin/env python3
"""Materialize a source-bound draft project from a topic and GitHub source.

This module wires the existing Content Router, repository snapshot adapter,
evidence pack, script bridge, and M5 input contracts. It does not approve the
brief, copy, skill execution, or publication. Motion rendering remains subject
to the managed Huashu grant in the normal M5 stage.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT / "src", ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from contentops.evidence.repo_source import RepoSourceAdapter, RepoSourceError  # noqa: E402
from contentops.routing import ContentRouter, RoutingError, UserTopicInput  # noqa: E402
from contentops.routing import brief as brief_module  # noqa: E402
from contentops.routing.models import digest  # noqa: E402
from new_project import create_project  # noqa: E402

RECEIPT = Path("receipts") / "raw-inputs.json"
EVIDENCE_PACK = Path("00_brief") / "evidence-pack.json"
GITHUB_REPO = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$", re.I)
SUPPORTED_TEXT = {".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml"}

# The topic router can return a useful repository lead while the README itself
# is hundreds of lines long. Keep the source bytes intact, but select literal
# topical passages for the draft evidence pack instead of blindly taking the
# file preamble. These common Chinese technical phrases also appear in English
# source repositories.
_TOPIC_TRANSLATIONS = {
    "混合检索": ("hybrid search", "hybrid retrieval", "hybrid",
                "bm25 and tf-idf", "bm25 + tf-idf"),
    "检索增强生成": ("retrieval augmented generation", "retrieval-augmented generation"),
    "检索": ("retrieval", "retriever", "search"),
    "向量": ("vector", "embedding"),
    "分块": ("chunk", "chunking", "split"),
    "重排": ("rerank", "reranking", "re-rank"),
    "工作原理": ("how it works", "architecture", "pipeline", "mechanism"),
}
_PASSAGE_SPLIT = re.compile(r"\n\s*\n")
_LATIN_TERM = re.compile(r"[a-z][a-z0-9_+#.-]{1,}", re.I)


def _topical_excerpt(content: str, topic: str, *, max_chars: int = 1800) -> tuple[str, float]:
    """Return verbatim, highest-relevance passage blocks and their score."""
    terms = {term.casefold() for term in _LATIN_TERM.findall(topic)}
    phrases: set[str] = set()
    specific_phrases: set[str] = set()
    required_groups: list[tuple[str, ...]] = []
    for chinese, translations in _TOPIC_TRANSLATIONS.items():
        if chinese in topic:
            lowered_translations = tuple(term.casefold() for term in translations)
            phrases.update(lowered_translations)
            if chinese != "工作原理":
                required_groups.append(lowered_translations)
            if chinese not in {"检索", "工作原理"}:
                specific_phrases.update(lowered_translations)
    if not terms and not phrases:
        return "", 0.0

    ranked: list[tuple[float, int, str]] = []
    for index, block in enumerate(_PASSAGE_SPLIT.split(content)):
        block = block.strip()
        if len(block) < 24:
            continue
        lowered = block.casefold()
        term_hits = sum(1 for term in terms if re.search(
            rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lowered))
        phrase_hits = sum(1 for phrase in phrases if phrase in lowered)
        specific_hits = sum(1 for phrase in specific_phrases if phrase in lowered)
        # Exact topic terms carry more weight than broad translated concepts.
        score = term_hits * 2.0 + phrase_hits
        # Generic matches such as "search" should not pull unrelated API tables,
        # release metadata, or documentation setup into the script evidence.
        if score and (term_hits or specific_hits):
            ranked.append((score, index, block))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[tuple[int, str]] = []
    size = 0
    for _, index, block in ranked:
        if size + len(block) > max_chars:
            continue
        selected.append((index, block))
        size += len(block) + 2
    excerpt = "\n\n".join(block for _, block in sorted(selected))
    excerpt_lowered = excerpt.casefold()
    # A repository mention of the acronym or a broad word such as "search" is
    # not enough to establish relevance. Require a topic term and each specific
    # Chinese technical concept to be represented in the selected passages.
    if terms and not any(re.search(
            rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", excerpt_lowered)
            for term in terms):
        return "", 0.0
    if any(not any(phrase in excerpt_lowered for phrase in group)
           for group in required_groups):
        return "", 0.0
    relevance = sum(score for score, index, _ in ranked
                    if any(index == picked_index for picked_index, _ in selected))
    # Avoid passing a lone keyword mention as substantive evidence.
    return (excerpt, relevance) if len(excerpt) >= 80 else ("", 0.0)


_MATCH_STOP_WORDS = {"the", "and", "for", "with", "from", "this", "that",
                     "into", "your", "how", "what", "when", "where", "then",
                     "about", "source", "repository", "project", "version",
                     "on", "to", "as", "is", "was", "are", "were", "of",
                     "in", "at", "by", "not", "but", "or", "it", "its",
                     "still", "today", "then", "than", "also", "only"}


def _visual_terms(text: str) -> set[str]:
    compounds = [match.casefold().lstrip("v") for match in
                 re.findall(r"\bv?\d+(?:[._/-]\d+)+\b", text, flags=re.I)]
    without_compounds = re.sub(r"\bv?\d+(?:[._/-]\d+)+\b", " ", text, flags=re.I)
    terms = {token.casefold() for token in _LATIN_TERM.findall(without_compounds)
             if token.casefold() not in _MATCH_STOP_WORDS}
    cjk = re.findall(r"[\u3400-\u9fff]+", text)
    for phrase in cjk:
        terms.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    terms.update(compounds)
    terms.update(re.findall(r"\b\d{2,}\b", without_compounds))
    return terms


def _asset_match_score(narration: str, recognized_text: str) -> float:
    """Score OCR text against a beat; filenames are intentionally excluded."""
    beat_terms = _visual_terms(narration)
    image_terms = _visual_terms(recognized_text)
    if not beat_terms or not image_terms:
        return 0.0
    overlap = beat_terms & image_terms
    return len(overlap) / len(beat_terms)


def _normalized_ocr_regions(result: Any, width: int, height: int) -> list[dict[str, Any]]:
    """Keep OCR text and normalized boxes so motion can target real UI details."""
    if width <= 0 or height <= 0:
        return []
    regions = []
    for row in result or []:
        if len(row) < 3 or not str(row[1]).strip():
            continue
        try:
            points = [(float(point[0]), float(point[1])) for point in row[0]]
            confidence = float(row[2])
        except (TypeError, ValueError, IndexError):
            continue
        if not points:
            continue
        left = max(0.0, min(x for x, _ in points) / width)
        top = max(0.0, min(y for _, y in points) / height)
        right = max(0.0, min(1.0, max(x for x, _ in points) / width))
        bottom = max(0.0, min(1.0, max(y for _, y in points) / height))
        if right <= left or bottom <= top:
            continue
        regions.append({
            "text": str(row[1]).strip(),
            "confidence": round(max(0.0, min(1.0, confidence)), 4),
            "rect": [round(left, 6), round(top, 6),
                     round(right - left, 6), round(bottom - top, 6)],
        })
    return regions


def _topical_source_lines(lines: list[str], queries: list[str], limit: int = 42
                         ) -> list[tuple[int, str]]:
    """Select verbatim source lines that visibly support the related claims."""
    query_terms = set().union(*(_visual_terms(value) for value in queries)) if queries else set()
    ranked = []
    for index, line in enumerate(lines):
        overlap = query_terms & _visual_terms(line)
        if overlap:
            ranked.append((len(overlap), index))
    selected: set[int] = set()
    for _, index in sorted(ranked, key=lambda item: (-item[0], item[1])):
        for candidate in (index - 1, index, index + 1):
            if 0 <= candidate < len(lines):
                selected.add(candidate)
                if len(selected) >= limit:
                    break
        if len(selected) >= limit:
            break
    if not selected:
        selected.update(range(min(limit, len(lines))))
    return [(index + 1, lines[index]) for index in sorted(selected)][:limit]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_slug(account: str, topic: str, source_url: str) -> str:
    topic_part = re.sub(r"[^a-z0-9]+", "-", topic.casefold()).strip("-")[:28]
    if not topic_part:
        match = GITHUB_REPO.fullmatch(source_url)
        topic_part = (match.group(2).removesuffix(".git") if match else "source")[:28]
    identity = hashlib.sha256(
        f"{account}\n{topic}\n{source_url}\n{_now()}".encode("utf-8")).hexdigest()[:8]
    return f"raw-{topic_part or 'episode'}-{identity}"


def _repo_candidates(result: Any) -> list[str]:
    intent = (result.detail.get("intent") or {}) if isinstance(result.detail, dict) else {}
    route_context = intent.get("route_context") or {}
    detail = route_context.get("detail") or {}
    candidates = detail.get("discovered_candidates") or []
    urls: list[str] = []
    for candidate in candidates:
        url = str(candidate.get("url") or "").rstrip("/")
        if GITHUB_REPO.fullmatch(url) and url.casefold() not in {
                item.casefold() for item in urls}:
            urls.append(url)
    return urls


def _evidence_items(project: Path, snapshot: Any, topic: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    authority: dict[str, dict[str, Any]] = {}
    rows = sorted(snapshot.files, key=lambda row: (
        Path(str(row.get("path") or "")).name.casefold() not in {"readme.md", "readme.txt"},
        str(row.get("path") or "").casefold()))
    for row in rows:
        source_path = str(row.get("path") or "")
        absolute = ROOT / source_path
        suffix = absolute.suffix.casefold()
        name = absolute.name.casefold()
        if (suffix not in SUPPORTED_TEXT
                or name.startswith(("license", "copying"))
                or not absolute.is_file()):
            continue
        try:
            content = absolute.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        excerpt, relevance = _topical_excerpt(content, topic)
        if len(excerpt) < 80:
            continue
        relative_to_project = absolute.resolve().relative_to(project.resolve()).as_posix()
        evidence_id = f"EV-{len(items) + 1:02d}"
        items.append({
            "evidence_id": evidence_id,
            "kind": "repository_source",
            "title": str(row.get("title") or absolute.name),
            "url": str(row.get("source_url") or snapshot.source_url),
            "excerpt": excerpt,
            "topic_relevance": relevance,
            "document": relative_to_project,
            "sha256": str(row.get("sha256") or _sha(absolute)),
            "retrieved_at": _now(),
            "note": (f"Pinned at {snapshot.commit}; SPDX {snapshot.spdx_license}; "
                     "repository bytes retained verbatim."),
        })
        authority[evidence_id] = {
            "permission": snapshot.license_permission,
            "title": str(row.get("title") or absolute.name),
            "source_url": str(row.get("source_url") or snapshot.source_url),
            "repository": snapshot.repository,
            "commit": snapshot.commit,
            "spdx_license": snapshot.spdx_license,
            "document": relative_to_project,
            "sha256": str(row.get("sha256") or _sha(absolute)),
        }
    return items, authority


def _bind_repository_analysis_scope(package: dict[str, Any], *, commit: str,
                                    evidence_items: int) -> None:
    """Limit this brief to inspectable source claims, not runtime claims.

    A licensed, pinned source snapshot can support what files declare. It
    cannot support performance, successful execution, or test-result claims.
    Those still require an actual recording/capture in a separate episode.
    """
    forecast = package.get("forecast")
    rows = forecast.get("evidence") if isinstance(forecast, dict) else None
    if not isinstance(rows, list):
        raise ValueError("the raw repository brief has no forecast evidence list")
    source_evidence = next((row for row in rows
                            if isinstance(row, dict)
                            and row.get("kind") == "authoritative_source"), None)
    if not source_evidence:
        raise ValueError("the raw repository brief has no authoritative-source forecast row")
    source_evidence.update(required=True, owner="automated", available=True)
    source_snapshot = next((row for row in rows
                            if isinstance(row, dict)
                            and row.get("kind") == "code_snapshot"), None)
    if source_snapshot is None:
        rows.append({"kind": "code_snapshot", "required": True,
                     "owner": "automated", "available": evidence_items > 0})
    else:
        source_snapshot.update(required=True, owner="automated",
                               available=evidence_items > 0)
    for row in rows:
        if isinstance(row, dict) and row.get("kind") in (
                "screen_recording", "terminal_capture"):
            row["required"] = False
    forecast["assessment_basis"] = (
        f"This episode is limited to implementation details visible in the licensed "
        f"repository snapshot at {commit}. It makes no runtime, test, or performance "
        "claim; those require a real terminal capture or recording.")
    forecast["failure_plan"] = "change_claim"
    forecast.pop("degrade_note", None)
    package["source_scope"] = "repository_code_analysis"
    from contentops.workflow.human_forecast import forecast_verdict
    package["forecast_verdict"] = forecast_verdict(forecast)


def bind_existing_source_scope(project: Path) -> bool:
    """Re-validate and bind the scope for a previously fetched raw project."""
    project = Path(project).resolve()
    receipt_path = project / RECEIPT
    if not receipt_path.is_file():
        return False
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("state") not in ("SOURCE_SNAPSHOT_READY", "M5_INPUTS_PREPARED"):
        return False
    source = receipt.get("source") or {}
    commit = str(source.get("commit") or "")
    if not commit or source.get("permission") != "LICENSED":
        raise ValueError("raw source receipt lacks a licensed pinned commit")
    authority_path = project / "00_brief" / "source-authority.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    if authority.get("commit") != commit or authority.get("spdx_license") != source.get("spdx_license"):
        raise ValueError("raw source authority does not match its receipt")
    permitted = [row for row in (authority.get("permissions") or {}).values()
                 if isinstance(row, dict) and row.get("permission") == "LICENSED"
                 and row.get("commit") == commit]
    if len(permitted) < 3:
        raise ValueError("raw source authority has fewer than three licensed documents")
    for row in permitted:
        path = (project / str(row.get("document") or "")).resolve()
        try:
            path.relative_to(project)
        except ValueError:
            raise ValueError("raw source authority points outside its project") from None
        if not path.is_file() or _sha(path) != row.get("sha256"):
            raise ValueError("raw source bytes no longer match their authority receipt")

    evidence_items: list[dict[str, Any]] = []
    permissions = authority.get("permissions") or {}
    for evidence_id, row in sorted(permissions.items()):
        if row not in permitted:
            continue
        path = project / str(row["document"])
        excerpt, relevance = _topical_excerpt(
            path.read_text(encoding="utf-8"), str(receipt.get("topic") or ""))
        if len(excerpt.strip()) < 80:
            continue
        evidence_items.append({
            "evidence_id": evidence_id,
            "kind": "repository_source",
            "title": str(row.get("title") or path.name),
            "url": str(row.get("source_url") or source.get("source_url") or ""),
            "excerpt": excerpt,
            "topic_relevance": relevance,
            "document": str(row["document"]),
            "sha256": str(row["sha256"]),
            "retrieved_at": str(receipt.get("created_at") or _now()),
            "note": (f"Pinned at {commit}; SPDX {source.get('spdx_license')}; "
                     "repository bytes retained verbatim."),
        })
    if len(evidence_items) < 3:
        raise ValueError("raw source snapshot has fewer than three topic-relevant documents")
    pack = {"schema": "contentops.evidence-pack/v1",
            "topic": str(receipt.get("topic") or ""), "items": evidence_items}
    pack_path = project / EVIDENCE_PACK
    pack_path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    pack_digest = _sha(pack_path)

    brief_path = project / "00_brief" / "brief.json"
    package = json.loads(brief_path.read_text(encoding="utf-8"))
    _bind_repository_analysis_scope(package, commit=commit,
                                    evidence_items=len(evidence_items))
    package["source_pack_sha256"] = pack_digest
    selected = {
        "source_url": str(source.get("source_url") or ""),
        "repository": str(source.get("repository") or ""),
        "commit": commit,
        "spdx_license": str(source.get("spdx_license") or ""),
        "discovery_is_not_evidence": True,
    }
    package["selected_research_source"] = selected
    package.pop("brief_id", None)
    package["brief_id"] = "BRIEF-" + digest(package)[:16].upper()
    failures = brief_module.validate_brief_package(package)
    if failures:
        raise ValueError("raw brief failed validation after source binding: "
                         + "; ".join(failures[:5]))
    brief_module.write_brief_package(project, package)
    receipt["source_scope"] = "repository_code_analysis"
    receipt["runtime_claims_allowed"] = False
    receipt["source"]["evidence_items"] = len(evidence_items)
    receipt["source_pack_sha256"] = pack_digest
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
    return True


def prepare_raw_project(*, account: str, topic: str = "",
                        source_urls: list[str] | None = None) -> Path:
    """Create a fresh pending-preview project from a topic and a licensed repo.

    With no URL, the Content Router discovers a GitHub repository from the
    account's allowlisted native-search sources. Search results are only leads;
    the selected repository is fetched and pinned before its files become
    evidence. Unlicensed or non-GitHub candidates stop this route.
    """
    urls = list(source_urls or [])
    if len(urls) > 1:
        raise ValueError("one --source-url is currently supported per production run")
    if urls and not GITHUB_REPO.fullmatch(urls[0].rstrip("/")):
        raise ValueError("--source-url must be https://github.com/<owner>/<repo>")
    if not topic.strip() and not urls:
        raise ValueError("raw production needs --topic or --source-url")
    if not topic.strip():
        topic = f"GitHub 仓库 {GITHUB_REPO.fullmatch(urls[0].rstrip('/')).group(2)} 的技术实现"

    router = ContentRouter(ROOT)
    result = router.start(
        account, "USER_TOPIC",
        UserTopicInput(topic=topic, urls=urls),
        fetch_evidence=not bool(urls),
    )
    if not result.ok:
        raise RoutingError("RAW_TOPIC_REJECTED", str(result.detail.get("message") or
                                                       result.detail.get("alignment") or
                                                       result.state))
    if urls:
        candidates = [urls[0].rstrip("/")]
    else:
        candidates = _repo_candidates(result)
        if not candidates:
            raise RoutingError(
                "RAW_RESEARCH_SOURCE_MISSING",
                "the account's allowed topic search returned no GitHub repository to pin; "
                "supply a licensed --source-url")
    selected_url = candidates[0]

    package = router.read_brief(result.run_id)
    if not package:
        raise RoutingError("RAW_BRIEF_MISSING", "the Content Router did not write a brief")

    project = create_project(ROOT, _safe_slug(account, topic, selected_url),
                             title=topic, account_slug=account)
    receipt_path = project / RECEIPT
    try:
        failures: list[str] = []
        snapshot = None
        for candidate_index, candidate_url in enumerate(candidates, start=1):
            snapshots = (project / "sources" / "repo-snapshot" if len(candidates) == 1
                         else project / "sources" / "research-candidates"
                         / f"candidate-{candidate_index:02d}")
            try:
                candidate_snapshot = RepoSourceAdapter().fetch(
                    candidate_url, output_dir=snapshots, repo_root=ROOT)
            except RepoSourceError as exc:
                failures.append(f"{candidate_url}: {exc}")
                continue
            if candidate_snapshot.license_permission != "LICENSED":
                failures.append(
                    f"{candidate_url}: SPDX {candidate_snapshot.spdx_license or 'unknown'} "
                    "does not permit automatic factual-claim evidence")
                continue
            candidate_items, candidate_authority = _evidence_items(
                project, candidate_snapshot, topic)
            if len(candidate_items) < 3:
                failures.append(
                    f"{candidate_url}: only {len(candidate_items)} topic-relevant documents; "
                    "the script contract needs at least three")
                continue
            selected_url, snapshot = candidate_url, candidate_snapshot
            items, authority = candidate_items, candidate_authority
            break
        if snapshot is None:
            raise RepoSourceError(
                "no discovered repository had a recognized license and fetchable source: "
                + "; ".join(failures[:6]))
        _bind_repository_analysis_scope(package, commit=snapshot.commit,
                                        evidence_items=len(items))

        intent = package.get("intent") or {}
        intent["source_artifact_refs"] = [snapshot.source_url]
        package["intent"] = intent
        package["selected_research_source"] = {
            "source_url": snapshot.source_url,
            "repository": snapshot.repository,
            "commit": snapshot.commit,
            "spdx_license": snapshot.spdx_license,
            "discovery_is_not_evidence": True,
        }
        package.pop("brief_id", None)
        package["brief_id"] = "BRIEF-" + digest(package)[:16].upper()
        failures = brief_module.validate_brief_package(package)
        if failures:
            raise RoutingError("RAW_BRIEF_INVALID", "; ".join(failures[:5]))
        brief_module.write_brief_package(project, package)

        evidence_pack = {
            "schema": "contentops.evidence-pack/v1",
            "topic": topic,
            "items": items,
        }
        (project / EVIDENCE_PACK).write_text(
            json.dumps(evidence_pack, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        package["source_pack_sha256"] = _sha(project / EVIDENCE_PACK)
        package.pop("brief_id", None)
        package["brief_id"] = "BRIEF-" + digest(package)[:16].upper()
        failures = brief_module.validate_brief_package(package)
        if failures:
            raise RoutingError("RAW_BRIEF_INVALID", "; ".join(failures[:5]))
        brief_module.write_brief_package(project, package)
        (project / "00_brief" / "source-authority.json").write_text(
            json.dumps({"schema": "contentops.source-authority/v1",
                        "source_url": snapshot.source_url,
                        "repository": snapshot.repository,
                        "commit": snapshot.commit,
                        "spdx_license": snapshot.spdx_license,
                        "permissions": authority},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        assets_path = project / "sources" / "assets.json"
        assets_path.write_text(json.dumps({"schema": "contentops.m5-assets/v1",
                                           "assets": []},
                                          ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        payload = {
            "schema": "contentops.raw-inputs/v1",
            "state": "SOURCE_SNAPSHOT_READY",
            "created_at": _now(),
            "project": project.relative_to(ROOT).as_posix(),
            "account_id": account,
            "topic": topic,
            "route_run_id": result.run_id,
            "brief_id": package.get("brief_id"),
            "brief_approval": "PENDING",
            "preview_only": True,
            "source": {
                "repository": snapshot.repository,
                "source_url": snapshot.source_url,
                "commit": snapshot.commit,
                "spdx_license": snapshot.spdx_license,
                "permission": snapshot.license_permission,
                "manifest": snapshot.manifest_path,
                "files": len(snapshot.files),
                "evidence_items": len(items),
            },
            "production_ready": False,
            "publish_authorized": False,
        }
        receipt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    except Exception as exc:
        payload = {
            "schema": "contentops.raw-inputs/v1",
            "state": "BLOCKED",
            "created_at": _now(),
            "project": project.relative_to(ROOT).as_posix(),
            "account_id": account,
            "topic": topic,
            "route_run_id": result.run_id,
            "selected_source_url": selected_url,
            "failure_type": type(exc).__name__,
            "failure_reason": str(exc)[:1000],
            "production_ready": False,
            "publish_authorized": False,
        }
        receipt_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        raise
    return project


def prepare_m5_contracts(project: Path) -> dict[str, Any]:
    """Bind pending draft claims to source permissions and motion anchors.

    The anchor images are deterministic presentations of source text or the
    exact draft line. The Huashu motion stage must replace them before M5 can
    compose a final video; an anchor image is never a fallback render.
    """
    from PIL import Image, ImageDraw, ImageFont

    project = Path(project).resolve()
    root_relative = project.relative_to(ROOT).as_posix()
    authority_path = project / "00_brief" / "source-authority.json"
    lines_path = project / "script" / "lines.json"
    claims_path = project / "script" / "claim-map.json"
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    lines_doc = json.loads(lines_path.read_text(encoding="utf-8"))
    claims_doc = json.loads(claims_path.read_text(encoding="utf-8"))
    raw_receipt_path = project / RECEIPT
    raw_receipt = json.loads(raw_receipt_path.read_text(encoding="utf-8"))
    account_id = str(raw_receipt.get("account_id") or "")
    dna_path = ROOT / "config" / "accounts" / f"{account_id}.json"
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    profile = ((dna.get("visual") or {}).get("motion") or {}).get("motion_profile") or \
        (dna.get("visual") or {}).get("motion_profile") or {}
    palette = profile.get("palette") or {
        "bg": "#0F1117", "surface": "#161A22", "ink": "#F5F7FA",
        "sub": "#8B95A5", "accent": "#38BDF8", "accent2": "#F07167",
    }

    def font(size: int, *, mono: bool = False):
        candidates = ([
            Path("C:/Windows/Fonts/consola.ttf"),
            Path("C:/Windows/Fonts/lucon.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf"),
        ] if mono else [
            Path("C:/Windows/Fonts/msyh.ttc"),
            Path("C:/Windows/Fonts/segoeui.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
        ])
        for candidate in candidates:
            if candidate.is_file():
                try:
                    return ImageFont.truetype(str(candidate), size=size)
                except OSError:
                    continue
        return ImageFont.load_default()

    title_font, body_font, code_font = font(36), font(30), font(20, mono=True)
    evidence_by_path: dict[str, dict[str, Any]] = {}
    source_permissions: dict[str, dict[str, Any]] = {}
    source_visual_queries: dict[str, list[str]] = {}
    for claim in claims_doc.get("claims") or []:
        for evidence in claim.get("evidence") or []:
            evidence_id = str(evidence.get("evidence_id") or "")
            logical = str(evidence.get("logical_path") or "")
            if logical.startswith("project://"):
                relative = logical[len("project://"):].lstrip("/")
            else:
                continue
            origin = next((row for row in (authority.get("permissions") or {}).values()
                           if row.get("document") == relative), None)
            if not origin or origin.get("permission") != "LICENSED":
                raise ValueError(f"no licensed source authority for {relative}")
            source_visual_queries.setdefault(relative, []).extend(
                [str(claim.get("text") or "")]
                + [str(item.get("text") or "")
                   for item in (claim.get("appearances") or [])
                   if isinstance(item, dict)])
            source_permissions[evidence_id] = {
                "permission": "LICENSED",
                "title": origin["title"],
                "note": (f"SPDX {origin['spdx_license']}; repository "
                         f"{origin['repository']} pinned at {origin['commit']}; "
                         f"source {origin['source_url']}"),
            }
            evidence_by_path[relative] = origin
    if not source_permissions:
        raise ValueError("the source-bound draft contains no licensed factual evidence")

    (project / "00_brief" / "source-permissions.json").write_text(
        json.dumps({"schema": "contentops.source-permissions/v1",
                    "permissions": source_permissions}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    entries: list[dict[str, Any]] = []
    image_by_source: dict[str, str] = {}
    generated_dir = project / "assets" / "generated" / "source-anchors"
    generated_dir.mkdir(parents=True, exist_ok=True)
    for index, (relative, origin) in enumerate(sorted(evidence_by_path.items()), start=1):
        source = project / relative
        if not source.is_file() or _sha(source) != origin["sha256"]:
            raise ValueError(f"source anchor bytes changed: {relative}")
        lines = source.read_text(encoding="utf-8").splitlines()
        filename = source.name
        asset_id = f"source-anchor-{index:02d}"
        target = generated_dir / f"{asset_id}.png"
        image = Image.new("RGB", (1080, 1920), str(palette.get("bg") or "#0F1117"))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((48, 54, 1032, 1866), radius=32,
                               fill=str(palette.get("surface") or "#161A22"))
        draw.text((92, 96), "PINNED SOURCE SNAPSHOT", font=title_font,
                  fill=str(palette.get("accent") or "#38BDF8"))
        draw.text((92, 160), f"{origin['repository']} · {origin['commit'][:12]}",
                  font=body_font, fill=str(palette.get("ink") or "#F5F7FA"))
        draw.text((92, 210), filename, font=code_font,
                  fill=str(palette.get("sub") or "#8B95A5"))
        y = 278
        shown = _topical_source_lines(lines, source_visual_queries.get(relative, []))
        for line_number, source_line in shown:
            line = source_line.expandtabs(4)
            if len(line) > 70:
                line = line[:67] + "…"
            draw.text((92, y), f"{line_number:03d}  {line}", font=code_font,
                      fill=str(palette.get("ink") or "#F5F7FA"))
            y += 31
        draw.line((92, 1770, 988, 1770), fill=str(palette.get("accent") or "#38BDF8"), width=2)
        draw.text((92, 1790), "SOURCE TEXT · NOT A LIVE RUNTIME RESULT", font=font(21, mono=True),
                  fill=str(palette.get("sub") or "#8B95A5"))
        image.save(target, format="PNG", optimize=True)
        asset_path = target.relative_to(ROOT).as_posix()
        entries.append({
            "id": asset_id,
            "type": "CODE_SNAPSHOT",
            "repo_path": asset_path,
            "sha256": _sha(target),
            "permission": "CREATED_BY_OWNER",
            "usage_scope": "VISUAL_SUPPORT_ONLY",
            "origin": "Deterministic rendering of pinned repository source bytes",
            "source_url": origin["source_url"],
            "source_commit": origin["commit"],
            "source_spdx_license": origin["spdx_license"],
            "source_document": relative,
            "source_document_sha256": origin["sha256"],
            "evidence_capable": False,
        })
        image_by_source[relative] = asset_id

    assets_path = project / "sources" / "assets.json"
    existing = json.loads(assets_path.read_text(encoding="utf-8"))
    user_assets = [row for row in existing.get("assets", [])
                   if isinstance(row, dict)
                   and row.get("permission") == "USER_PROVIDED_LOCAL"
                   and row.get("type") == "USER_PROVIDED_IMAGE"]
    ocr_rows: list[dict[str, Any]] = []
    asset_text: dict[str, str] = {}
    asset_regions: dict[str, list[dict[str, Any]]] = {}
    ocr_engine_name = "rapidocr_onnxruntime"
    if user_assets:
        try:
            from rapidocr_onnxruntime import RapidOCR
            from contentops.media.local_assets import is_valid_local_preview_asset
            ocr = RapidOCR()
            for asset in user_assets:
                if not is_valid_local_preview_asset(asset, project, ROOT):
                    raise ValueError(f"local asset receipt/hash failed: {asset.get('id')}")
                asset_path = (ROOT / str(asset.get("repo_path") or "")).resolve()
                result, _ = ocr(str(asset_path))
                recognized = " ".join(str(row[1]) for row in (result or [])
                                       if len(row) > 1 and str(row[1]).strip())
                from PIL import Image
                with Image.open(asset_path) as opened:
                    image_width, image_height = opened.size
                regions = _normalized_ocr_regions(result, image_width, image_height)
                asset_id = str(asset.get("id") or "")
                asset_text[asset_id] = recognized
                asset_regions[asset_id] = regions
                ocr_rows.append({"asset_id": asset_id,
                                 "source_name": str(asset.get("source_name") or ""),
                                 "sha256": str(asset.get("sha256") or ""),
                                 "image_size": [image_width, image_height],
                                 "recognized_text": recognized,
                                 "regions": regions})
        except ImportError:
            ocr_engine_name = "unavailable"
        except Exception as exc:
            raise ValueError(f"local asset OCR failed: {type(exc).__name__}: {exc}") from None

    claim_path_by_id: dict[str, str] = {}
    for claim in claims_doc.get("claims") or []:
        evidence = claim.get("evidence") or []
        for item in evidence:
            logical = str(item.get("logical_path") or "")
            if logical.startswith("project://"):
                claim_path_by_id[str(claim.get("claim_id") or "")] = \
                    logical[len("project://"):].lstrip("/")
                break
    fallback_asset = next(iter(image_by_source.values()))
    mapping: dict[str, str] = {}
    local_matches: list[dict[str, Any]] = []
    for beat in lines_doc.get("beats") or []:
        placement = str(beat.get("placement_id") or "")
        claim_id = str(beat.get("claim_id") or "")
        relative = claim_path_by_id.get(claim_id, "")
        narration = str(beat.get("text") or "")
        ranked_local = sorted(
            ((_asset_match_score(narration,
                                 asset_text.get(str(asset.get("id") or ""), "")),
              asset) for asset in user_assets),
            key=lambda item: (-item[0], str(item[1].get("id") or "")))
        matched_terms = (_visual_terms(narration)
                         & _visual_terms(asset_text.get(str(ranked_local[0][1].get("id") or ""), ""))) \
            if ranked_local else set()
        if ranked_local and ranked_local[0][0] >= 0.4 and len(matched_terms) >= 2:
            score, asset = ranked_local[0]
            mapping[placement] = str(asset["id"])
            local_matches.append({"placement_id": placement, "asset_id": str(asset["id"]),
                                  "score": round(score, 4),
                                  "matched_terms": sorted(matched_terms),
                                  "ocr_text": asset_text.get(str(asset["id"]), "")})
        else:
            mapping[placement] = image_by_source.get(relative, fallback_asset)
    if not mapping or len(mapping) != len(lines_doc.get("beats") or []):
        raise ValueError("not every generated narration beat has a visual source anchor")

    current = [row for row in existing.get("assets", [])
               if isinstance(row, dict) and row.get("permission") == "USER_PROVIDED_LOCAL"]
    for asset in current:
        asset_id = str(asset.get("id") or "")
        if asset_id in asset_regions:
            asset["ocr_regions"] = asset_regions[asset_id]
    existing["assets"] = current + entries
    assets_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    (project / "script" / "asset-map.json").write_text(
        json.dumps({"schema": "contentops.asset-map/v1", "mapping": mapping},
                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if user_assets:
        (project / "receipts" / "local-asset-semantic-map.json").write_text(
            json.dumps({"schema": "contentops.local-asset-semantic-map/v1",
                        "state": "OCR_MATCHED" if ocr_engine_name != "unavailable"
                        else "OCR_UNAVAILABLE",
                        "ocr_engine": ocr_engine_name, "assets": ocr_rows,
                        "matches": local_matches,
                        "local_only": True}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")

    raw_receipt = json.loads(raw_receipt_path.read_text(encoding="utf-8"))
    raw_receipt.update({
        "state": "M5_INPUTS_PREPARED",
        "source_permissions": len(source_permissions),
        "visual_anchor_assets": len(entries),
        "visual_anchor_policy": "motion backend must replace anchors; no static fallback",
        "local_visual_matches": len(local_matches),
        "placements": len(mapping),
        "production_ready": False,
        "publish_authorized": False,
    })
    raw_receipt_path.write_text(json.dumps(raw_receipt, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
    return {"state": "M5_INPUTS_PREPARED", "source_permissions": len(source_permissions),
            "visual_anchor_assets": len(entries), "placements": len(mapping)}


__all__ = ["prepare_m5_contracts", "prepare_raw_project"]
