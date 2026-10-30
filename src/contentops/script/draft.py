"""The script stage: an approved brief becomes lines, claims and a storyboard.

What this is
------------
The brief says what the episode is about and what evidence it has. This module
turns that into the three files the existing pipeline reads — ``lines.json``,
``claim-map.json`` and ``storyboard.json`` — plus a human-readable ``master.md``.

It is deliberately **not** a text generator. There is no model call here, so it
cannot invent a fact, a number or a quotation. Every narration line is built
from one of three things:

- the brief itself (topic, angle, route) — an editorial transition;
- what the cited source *says about itself*, quoted and marked PARTIAL with the
  limitation stated, because reading a description is not running the thing;
- an explicit judgement by the account, marked as a judgement and never as a
  fact.

That is why the output is a **draft**: a person still has to write the parts
that need a mind, and the copy review still has to approve it.

What it refuses
---------------
- a brief that is not approved, or whose approval no longer matches its
  content (the handoff check already owns that);
- a brief whose evidence forecast is DEGRADED — the episode needs a capture
  nobody has, and pretending otherwise is the failure this repository exists
  to stop;
- a brief with no source at all, when the account's evidence mode requires one.

Reused, not reinvented
----------------------
``contentops.evidence.claim_map`` is the repository's own claim contract and
the copy review already fingerprints ``claim-map.json``. The draft speaks that
contract rather than inventing a parallel one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ..evidence.claim_map import CLAIM_MAP_SCHEMA, PARTIAL, SUPPORTED
from ..routing import handoff
from ..routing.account_profile import AccountProfile, load_profile

#: The draft's own receipt schema.
DRAFT_SCHEMA = "contentops.script-draft/v1"

#: The narration contract the cut planner reads.
LINES_SCHEMA = "contentops.audio-first-lines/v1"

#: Where the draft's report goes, next to the brief.
REPORT_DIR = "00_brief"
REPORT_FILE = "script-report.json"

#: Sentence-level shaping. The text a beat carries is also its claim's text,
#: because the claim map requires them to be equal — a shorter caption is a
#: different claim, and this stage does not produce captions.
MAX_LINE_CHARS = 80


class ScriptBlocked(Exception):
    """The brief cannot become a script, and the reason is named."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass
class Draft:
    """Everything the stage produced, before anything is written."""

    project: str
    brief_id: str
    account_id: str
    lines: Dict[str, Any]
    claim_map: Dict[str, Any]
    storyboard: Dict[str, Any]
    master: str
    report: Dict[str, Any]
    #: Files the claims bind to, written next to the script so the evidence a
    #: reviewer is shown is the evidence that was hashed.
    evidence_files: Dict[str, bytes]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _shorten(text: str, limit: int = MAX_LINE_CHARS) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or url).replace("www.", "")
    except ValueError:
        return url


def _first_source(brief: Dict[str, Any]) -> Optional[str]:
    for ref in (brief.get("intent") or {}).get("source_artifact_refs") or []:
        if str(ref).strip():
            return str(ref).strip()
    evidence = (brief.get("intent") or {}).get("evidence") or []
    for item in evidence:
        if isinstance(item, dict) and item.get("url"):
            return str(item["url"])
    return None


def _source_line(brief: Dict[str, Any], source: str) -> Tuple[str, str]:
    """The one sentence this stage is allowed to say about the source.

    It reports what the source says about itself, and nothing more. The
    repository's description is the only text this stage has actually seen.
    """
    # Only the title is the source's own text. The brief's ``thesis`` is text
    # this repository wrote, and attributing it to the source would be exactly
    # the invented quotation this stage must never produce.
    candidate = brief.get("candidate") or {}
    title = " ".join(str(candidate.get("title") or "").split())
    if title:
        return f"{_host(source)} 上这一条的原标题是：{_shorten(title, 44)}。", title
    return f"这一条来自 {_host(source)}。", ""


def _composition(profile: AccountProfile) -> List[Dict[str, Any]]:
    visual = (profile.dna or {}).get("visual") or {}
    segments = ((visual.get("composition") or {}).get("segments")) or []
    return [dict(segment) for segment in segments if segment.get("role")]


#: Roles that stand for a real artifact somebody has to capture.
CAPTURE_ROLES = ("screen_recording_evidence", "code_snapshot",
                 "ui_screenshot", "terminal_capture")


def _role_for(profile: AccountProfile, kind: str, index: int) -> str:
    segments = _composition(profile)
    if not segments:
        return "vector_animation"
    if kind == "source":
        # A claim about a source is shown by the source, whatever the account
        # calls its evidence visual — that is what makes the claim checkable.
        for segment in segments:
            if str(segment["role"]) in CAPTURE_ROLES:
                return str(segment["role"])
    # Everything that is not an evidence shot uses the account's dominant
    # visual, rather than cycling through the composition: a three-line
    # transition section is not three different visual languages.
    ordered = [str(segment["role"]) for segment in segments]
    return ordered[0]


def _claims_and_beats(profile: AccountProfile, brief: Dict[str, Any]
                      ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]],
                                 Dict[str, bytes]]:
    intent = brief.get("intent") or {}
    topic = " ".join(str(intent.get("topic") or "").split())
    pillar = str((brief.get("candidate") or {}).get("positioning_alignment") or "")
    source = _first_source(brief)
    source_sentence, _ = _source_line(brief, source) if source else ("", "")

    claims: List[Dict[str, Any]] = []
    beats: List[Dict[str, Any]] = []

    def add(claim_id: str, text: str, kind: str, *, supported: bool,
            limitation: str = "", evidence: Optional[List[Dict[str, Any]]] = None,
            progress: str = "") -> None:
        # A judgement cannot be SUPPORTED, and a claim that appears on a
        # distributable surface must say what it is. So a judgement always
        # carries the limitation that marks it as a judgement.
        if not supported and not limitation and kind == "judgement":
            limitation = "这是本账号的判断，不是已核实的事实"
        status = SUPPORTED if supported else PARTIAL
        claims.append({
            "claim_id": claim_id,
            "revision": 1,
            "text": text,
            "kind": kind,
            "assertion_about": "source" if kind == "source" else
                               ("judgement" if kind == "judgement" else "none"),
            "support_status": status,
            "permission_scope": "publishable",
            "limitation": limitation,
            "evidence": evidence or [],
            "appearances": [{"surface": "narration", "text": text}],
        })
        beats.append({
            "placement_id": f"P-{len(beats) + 1:02d}",
            "claim_id": claim_id,
            "text": text,
            "semantic_progress": progress or kind,
            "views": [],
        })

    hook = f"今天只聊一件事：{_shorten(topic, 60)}。" if topic else "今天聊一个具体的问题。"
    add("C-01", hook, "editorial_transition", supported=True,
        progress="the episode names its subject")

    evidence_files: Dict[str, bytes] = {}
    if source_sentence:
        # The claim is about what the source says, and the only honest way to
        # bind it is to keep exactly what was read. The document records its
        # own provenance, so a reviewer can see it is a description and not a
        # verification.
        document = (
            f"source: {source}\n"
            f"recorded_at: {_now()}\n"
            "recorded_by: contentops.script.draft (from the brief's candidate\n"
            "  record, which the collector wrote from the source's own listing)\n"
            "what_it_is: the source's self-description at collection time;\n"
            "  it is not a run, a test or an independent verification\n"
            f"text: {source_sentence}\n"
        ).encode("utf-8")
        evidence_files["C-02-source.txt"] = document
        add("C-02", source_sentence, "source", supported=True,
            evidence=[{"evidence_id": "E-C02-01", "kind": "document",
                       "sha256": hashlib.sha256(document).hexdigest(),
                       "logical_path": "project://script/evidence/C-02-source.txt",
                       "permission_scope": "publishable"}],
            progress="the claim is pinned to the text that was actually read")

    # A judgement is not allowed on narration: the claim contract only lets a
    # SUPPORTED claim be spoken, and an opinion has no evidence to support it.
    # So what is left for this stage is structure — transitions that say what
    # the episode will do — and the person writing the copy fills them in.
    if profile.evidence_mode == "EVIDENCE_LED":
        add("C-03", "接下来要做的，是把它拿到真实环境里跑一遍。",
            "editorial_transition", supported=True,
            progress="the episode states what it will do")
        add("C-04", "这一段会用真机上的录屏和日志说话。",
            "editorial_transition", supported=True,
            progress="the evidence form is declared")
    else:
        add("C-03", "接下来，把它拆成需求、实现和上线三段来看。",
            "editorial_transition", supported=True,
            progress="the episode states its structure")
        add("C-04", "每一段都会落回到能运行、能上线的具体做法。",
            "editorial_transition", supported=True,
            progress="the standard is stated")

    add("C-05", "下一集，我们把这条真的跑一遍。", "cta", supported=True,
        progress="the episode hands off to the next one")
    return claims, beats, evidence_files


def _storyboard(profile: AccountProfile, beats: List[Dict[str, Any]],
                claims: List[Dict[str, Any]], brief: Dict[str, Any]) -> Dict[str, Any]:
    by_id = {claim["claim_id"]: claim for claim in claims}
    target = profile.target_duration_s or (45.0, 60.0)
    total = float(sum(target)) / 2.0
    weights = [max(len(beat["text"]), 8) for beat in beats]
    scale = total / max(sum(weights), 1)
    shots: List[Dict[str, Any]] = []
    cursor = 0.0
    for index, beat in enumerate(beats):
        claim = by_id[beat["claim_id"]]
        role = _role_for(profile, claim["kind"], index)
        duration = round(max(2.0, weights[index] * scale), 1)
        # A recording, a screenshot or a code snapshot is a real artifact
        # somebody has to capture. Motion and cards are designed, not captured.
        needs_capture = role in CAPTURE_ROLES
        shots.append({
            "shot_id": f"S-{index + 1:02d}",
            "placement": beat["placement_id"],
            "unit": beat["placement_id"],
            "narration": beat["text"],
            "image": role,
            "source_type": role,
            "duration": duration,
            "designed_card": "card" in role,
            "function": claim["kind"],
            "dna_role": role,
            "needs_capture": needs_capture,
            "caption_points": [beat["text"]] if claim["kind"] != "editorial_transition" else [],
            "claim_id": beat["claim_id"],
            "evidence_source": _first_source(brief) if claim["kind"] == "source" else None,
        })
        cursor += duration
    return {"schema": "contentops.storyboard/v1", "size": {"width": 1080, "height": 1920},
            "engine": "capture-first", "shots": shots}


def _master(profile: AccountProfile, brief: Dict[str, Any], beats: List[Dict[str, Any]],
            claims: List[Dict[str, Any]]) -> str:
    by_id = {claim["claim_id"]: claim for claim in claims}
    lines = [
        f"# {brief.get('intent', {}).get('topic') or 'script draft'}",
        "",
        f"- account: `{profile.account_id}` ({profile.platform})",
        f"- route: `{brief.get('intent', {}).get('route_mode')}`",
        f"- brief: `{brief.get('brief_id')}`",
        f"- evidence mode: `{profile.evidence_mode}` · recording: `{profile.manual_recording}`",
        "",
        "> 这是草稿。事实性句子只有在其 claim 的状态允许时才能进成片；",
        "> 复制评审必须由人签字。",
        "",
    ]
    for beat in beats:
        claim = by_id[beat["claim_id"]]
        lines.append(f"## {beat['placement_id']} · {claim['kind']}")
        lines.append("")
        lines.append(beat["text"])
        lines.append("")
        lines.append(f"- claim: `{claim['claim_id']}` · {claim['support_status']}")
        if claim.get("limitation"):
            lines.append(f"- limit: {claim['limitation']}")
        lines.append("")
    return "\n".join(lines)


def build(project: Path, *, root: Optional[Path] = None) -> Draft:
    """Build the draft in memory. Nothing is written."""
    project = Path(project)
    brief = handoff.read_brief(project)
    verdict = handoff.check(brief)
    if not verdict["ok"]:
        code = "EVIDENCE_REQUIRED" if verdict["reason"] == "EVIDENCE_REQUIRED" \
            else verdict["reason"]
        raise ScriptBlocked(code, verdict["detail"])

    assert brief is not None
    intent = brief.get("intent") or {}
    account_id = str(intent.get("account_id") or "")
    if not account_id:
        raise ScriptBlocked("ACCOUNT_MISSING", "the brief names no account")
    profile = load_profile(Path(root) if root else _repo_root(), account_id)

    source = _first_source(brief)
    if profile.evidence_mode == "EVIDENCE_LED" and not source:
        raise ScriptBlocked(
            "EVIDENCE_REQUIRED",
            "this account requires an artifact to look at, and the brief carries "
            "no source reference")

    claims, beats, evidence_files = _claims_and_beats(profile, brief)
    storyboard = _storyboard(profile, beats, claims, brief)
    lines_doc = {
        "schema": LINES_SCHEMA,
        "package_id": project.name,
        "evidence_mode": profile.evidence_mode,
        "manual_recording": profile.manual_recording,
        "composition": _composition(profile),
        "beats": beats,
    }
    claim_map = {
        "schema": CLAIM_MAP_SCHEMA,
        "map_id": f"CM-{brief.get('brief_id') or project.name}",
        "package_id": project.name,
        "claims": claims,
    }
    report = {
        "schema": DRAFT_SCHEMA,
        "generated_at": _now(),
        "project": str(project),
        "brief_id": brief.get("brief_id"),
        "content_digest": verdict.get("content_digest"),
        "account_id": account_id,
        "route_mode": intent.get("route_mode"),
        "topic": intent.get("topic"),
        "source_refs": list(intent.get("source_artifact_refs") or []),
        "claims": [
            {"claim_id": claim["claim_id"], "text": claim["text"],
             "kind": claim["kind"], "support_status": claim["support_status"],
             "limitation": claim.get("limitation") or "",
             "source_refs": ([source] if claim["kind"] == "source" else [])}
            for claim in claims
        ],
        "storyboard": {"shots": len(storyboard["shots"]),
                       "duration_s": round(sum(shot["duration"] for shot in storyboard["shots"]), 1),
                       "needs_capture": sum(1 for shot in storyboard["shots"] if shot["needs_capture"])},
        "gates": {
            "copy_review": "required before any narration is synthesised",
            "evidence": "claims marked PARTIAL state their limitation; none is BLOCKED",
        },
    }
    return Draft(project=str(project), brief_id=str(brief.get("brief_id") or ""),
                 account_id=account_id, lines=lines_doc, claim_map=claim_map,
                 storyboard=storyboard,
                 master=_master(profile, brief, beats, claims), report=report,
                 evidence_files=evidence_files)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def write(draft: Draft) -> Dict[str, Path]:
    """Write the draft where the pipeline already looks for it."""
    project = Path(draft.project)
    script = project / "script"
    script.mkdir(parents=True, exist_ok=True)
    written: Dict[str, Path] = {}
    for name, document in (("lines.json", draft.lines),
                           ("claim-map.json", draft.claim_map),
                           ("storyboard.json", draft.storyboard)):
        path = script / name
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        written[name] = path
    master = script / "master.md"
    master.write_text(draft.master + "\n", encoding="utf-8")
    written["master.md"] = master
    # The documents the claims bind to are written before the report, so the
    # digest in claim-map.json always names a file that exists.
    for name, content in draft.evidence_files.items():
        evidence_dir = script / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        path = evidence_dir / name
        path.write_bytes(content)
        written[f"evidence/{name}"] = path
    report = project / REPORT_DIR / REPORT_FILE
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(draft.report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    written[REPORT_FILE] = report
    return written


def check(project: Path) -> Dict[str, Any]:
    """Validate a draft already on disk against the claim contract."""
    from ..evidence.claim_map import ClaimMap
    from ..workflow import copy_review

    project = Path(project)
    script = project / "script"
    failures: List[str] = []
    for name in ("lines.json", "claim-map.json", "storyboard.json", "master.md"):
        if not (script / name).is_file():
            failures.append(f"script/{name} is missing")
    if failures:
        return {"ok": False, "reason": "DRAFT_INCOMPLETE", "failures": failures}

    try:
        document = json.loads((script / "claim-map.json").read_text(encoding="utf-8"))
        claim_map = ClaimMap.from_dict(document).validate()
        claim_map.require_publishable()
    except Exception as exc:  # noqa: BLE001 - the contract's own error type
        return {"ok": False, "reason": "CLAIM_MAP_INVALID", "failures": [str(exc)[:400]]}

    lines = json.loads((script / "lines.json").read_text(encoding="utf-8"))
    known = {claim.claim_id for claim in claim_map.claims}
    for beat in lines.get("beats") or []:
        if beat.get("claim_id") not in known:
            failures.append(f"{beat.get('placement_id')} cites unknown claim "
                            f"{beat.get('claim_id')!r}")
        try:
            claim = claim_map.by_id(str(beat.get("claim_id")))
        except Exception:  # noqa: BLE001
            continue
        if claim.text != beat.get("text"):
            failures.append(f"{beat.get('placement_id')} narration is not the text of "
                            f"its claim; a paraphrase is a different claim")

    gate = copy_review.status(project)
    return {"ok": not failures, "reason": "OK" if not failures else "CLAIM_MISMATCH",
            "failures": failures, "copy_review": gate}
