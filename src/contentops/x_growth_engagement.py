"""Create evidence-bound writing briefs, not simulated language-model analysis."""
from __future__ import annotations

import re
from urllib.parse import urlsplit


def _words(text):
    return set(re.findall(r"[\w一-鿿]{3,}", text.casefold()))


def _reference(url):
    if not isinstance(url, str):
        return False
    try:
        p = urlsplit(url)
        return p.scheme == "https" and bool(p.hostname) and not p.username and not p.password
    except ValueError:
        return False


def brief(candidate):
    """Return extracted inputs and prompts; never assert semantic understanding."""
    if not isinstance(candidate, dict):
        return {"status": "DATA_UNAVAILABLE", "reason": "INVALID_CANDIDATE"}
    text, audience = candidate.get("text"), candidate.get("audience")
    if not isinstance(text, str) or not text.strip() or not isinstance(audience, str) or not audience.strip():
        return {"status": "DATA_UNAVAILABLE", "reason": "POST_TEXT_AND_AUDIENCE_REQUIRED"}
    evidence = candidate.get("evidence", [])
    if not isinstance(evidence, list) or any(not isinstance(e, dict) or not _reference(e.get("url")) or not isinstance(e.get("quote"), str) or not e["quote"].strip() for e in evidence):
        return {"status": "BLOCKED", "reason": "INVALID_EVIDENCE"}
    drafts = candidate.get("drafts", [])
    if not isinstance(drafts, list) or any(not isinstance(d, str) or not d.strip() for d in drafts):
        return {"status": "BLOCKED", "reason": "INVALID_DRAFTS"}
    warnings = []
    normalized = [" ".join(d.casefold().split()) for d in drafts]
    if len(normalized) != len(set(normalized)) or any(d in {"nice post!", "great post!", "great insights!"} for d in normalized):
        warnings.append("DUPLICATE_OR_TEMPLATE")
    if any(not (_words(text) & _words(d)) for d in drafts):
        warnings.append("POSSIBLY_UNRELATED")
    if not evidence:
        warnings.append("EVIDENCE_NOT_PROVIDED")
    return {
        "status": "REVIEW_REQUIRED", "source_excerpt": text, "audience_supplied": audience,
        "context_supplied": candidate.get("context", ""),
        "interpretation": "No semantic inference performed; an agent or human must identify the claim and audience fit.",
        "participation_decision": "HUMAN_REVIEW_REQUIRED",
        "evidence": [{"url": e["url"], "quote": e["quote"], "verification": "USER_SUPPLIED_UNVERIFIED"} for e in evidence],
        "writing_angles": [
            {"purpose": "concrete evidence", "instruction": "Add a relevant, independently verified fact; omit claims not supported by the supplied source."},
            {"purpose": "limitation or alternative", "instruction": "Offer a contextual limitation or thoughtful question; do not invent a counterexample."},
        ],
        "draft_generation": "AGENT_REQUIRED", "drafts_supplied": drafts, "warnings": warnings,
        "review_checklist": ["Confirm source and context", "Check audience fit and incremental value", "Verify each claim and source", "Check relevance, originality, privacy and platform rules", "A human decides whether and how to reply"],
        "limitations": "Lexical warnings are incomplete and do not determine relevance, truth or originality.",
    }
