"""The script stage: an approved brief plus collected material becomes an episode.

What this is
------------
``script/lines.json``, ``script/claim-map.json``, ``script/storyboard.json`` and
``script/master.md`` — the files the existing engine reads — built from the
brief and from an **evidence pack**: material that was actually fetched, saved
and hashed.

Three rules shape everything here.

**Provenance is stated, never implied.** A line is one of five things and says
which: a topic the user supplied, a title that came from a source, a source's
description, a factual claim bound to a document, or an editorial statement.
A user's topic is never dressed up as a source's own words — the earlier draft
did exactly that and it was wrong.

**Only collected material may be spoken.** The repository's claim contract
allows a ``SUPPORTED`` claim on narration; a ``SUPPORTED`` claim needs evidence;
and the only evidence this stage accepts is a document that was fetched and
hashed. So a script can only say things that are in the pack. When the pack is
too thin, the stage says ``DRAFT_CONTENT_INSUFFICIENT`` and names the gap
instead of padding the video with transitions.

**Duration follows the words.** A beat lasts as long as its narration takes at
a stated speaking rate, plus a pause, plus — for a shot that shows a real
artifact — enough time to read it. The total is whatever that adds up to. If it
falls short of the account's window, that is a content problem, not a reason to
slow the voice down.

What it still is not
--------------------
Not a writer. It assembles quoted material and structure; a person turns that
into speech, and the copy review approves it. No model is called.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ..evidence.claim_map import CLAIM_MAP_SCHEMA, SUPPORTED
from ..routing import handoff
from ..routing.account_profile import AccountProfile, load_profile
from .evidence import (  # noqa: F401
    PACK_FILE,
    EvidenceItem,
    EvidencePack,
    load_pack,
    quotes,
    sufficiency,
)

DRAFT_SCHEMA = "contentops.script-draft/v1"

#: The fields ``contentops.claim-map/v1`` accepts on a claim. Provenance and
#: source references are ours, so they live in the draft report rather than
#: being smuggled into a contract this stage does not own.
CLAIM_MAP_FIELDS = ("claim_id", "revision", "text", "kind", "assertion_about",
                    "support_status", "permission_scope", "limitation",
                    "evidence", "appearances")
LINES_SCHEMA = "contentops.audio-first-lines/v1"
REPORT_DIR = "00_brief"
REPORT_FILE = "script-report.json"

#: The provenance a line may carry. Every line says which one it is.
PROVENANCE = (
    "user_supplied_topic",
    "source_original_title",
    "source_description",
    "verified_factual_claim",
    "editorial_statement",
)

#: Speaking pace. Chinese narration is measured in characters per second,
#: English in words per second; both are stated so the arithmetic is checkable.
SPEAK_RATE_ZH = 4.5
SPEAK_RATE_EN = 2.6
PAUSE_S = 0.5
#: A shot that shows a real artifact needs time to be read, whatever the line.
CAPTURE_FLOOR_S = 5.0
#: How many quotes one episode may carry before it is a different video.
MAX_QUOTES = 16

CAPTURE_ROLES = ("screen_recording_evidence", "code_snapshot",
                 "ui_screenshot", "terminal_capture")


class ScriptBlocked(Exception):
    """The brief cannot become a script, and the reason is named."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass
class Draft:
    project: str
    brief_id: str
    account_id: str
    lines: Dict[str, Any]
    claim_map: Dict[str, Any]
    storyboard: Dict[str, Any]
    master: str
    report: Dict[str, Any]
    evidence_files: Dict[str, bytes] = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or url).replace("www.", "")
    except ValueError:
        return url


def language_of(text: str) -> str:
    """The language a line is written in, from its own characters."""
    cleaned = str(text or "")
    cjk = len(re.findall(r"[一-鿿]", cleaned))
    letters = sum(1 for char in cleaned if char.isalpha())
    return "zh" if cjk and cjk / max(letters, 1) > 0.3 else "en"


def line_seconds(text: str) -> float:
    """How long a line takes to say, from its own length."""
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return 0.0
    cjk = len(re.findall(r"[一-鿿]", cleaned))
    if cjk and cjk / max(len(cleaned), 1) > 0.2:
        seconds = cjk / SPEAK_RATE_ZH + (len(cleaned) - cjk) / (SPEAK_RATE_EN * 5)
    else:
        seconds = len(cleaned.split()) / SPEAK_RATE_EN
    return round(seconds + PAUSE_S, 1)


def _composition(profile: AccountProfile) -> List[Dict[str, Any]]:
    visual = (profile.dna or {}).get("visual") or {}
    segments = ((visual.get("composition") or {}).get("segments")) or []
    return [dict(segment) for segment in segments if segment.get("role")]


def _role_for(profile: AccountProfile, kind: str) -> str:
    segments = _composition(profile)
    if not segments:
        return "vector_animation"
    if kind == "source" or kind == "verified_factual_claim":
        for segment in segments:
            if str(segment["role"]) in CAPTURE_ROLES:
                return str(segment["role"])
    return str(segments[0]["role"])


def topic_provenance(brief: Dict[str, Any]) -> str:
    """Where the topic came from — the difference this stage must not blur."""
    context = (brief.get("intent") or {}).get("route_context") or {}
    origin = str(context.get("topic_origin") or "")
    mode = str((brief.get("intent") or {}).get("route_mode") or "")
    if origin in ("USER_INPUT", "USER_TOPIC") or mode == "USER_TOPIC":
        return "user_supplied_topic"
    return "source_original_title"


def build(project: Path, *, root: Optional[Path] = None,
          pack_path: Optional[Path] = None) -> Draft:
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
    profile = load_profile(Path(root) if root else Path(__file__).resolve().parents[3],
                           account_id)

    pack_file = Path(pack_path) if pack_path else project / PACK_FILE
    pack: Optional[EvidencePack] = None
    if pack_file.is_file():
        try:
            pack = load_pack(pack_file)
        except (OSError, ValueError) as exc:
            raise ScriptBlocked("EVIDENCE_PACK_INVALID", str(exc)) from None

    if pack is not None:
        _bind_documents(project, pack)
    enough = sufficiency(pack)
    if not enough["ok"]:
        raise ScriptBlocked(
            "DRAFT_CONTENT_INSUFFICIENT",
            "这份 Brief 还没有足够的可引用材料：" + "；".join(enough["missing"])
            + "。请先用 scripts/evidence_pack.py 采集官方文档、源码或数据，"
              "而不是用转场和 CTA 填满时长。")

    topic = " ".join(str(intent.get("topic") or "").split())
    provenance = topic_provenance(brief)
    claims, beats = _claims_and_beats(profile, topic, provenance, pack,
                                      target_seconds=float(profile.target_duration_s[0])
                                      if profile.target_duration_s else 0.0)
    storyboard = _storyboard(profile, beats, claims)
    seconds = sum(shot["duration"] for shot in storyboard["shots"])
    low, high = (profile.target_duration_s or (0.0, 0.0))
    length_note = ""
    if low and seconds < low:
        raise ScriptBlocked(
            "DRAFT_CONTENT_INSUFFICIENT",
            f"按实际讲解语速只有 {seconds:.1f} 秒，低于 {profile.account_id} 的 "
            f"{low:.0f}–{high:.0f} 秒窗口。缺的是内容，不是时长：再补约 "
            f"{max(0, int((low - seconds) * SPEAK_RATE_ZH))} 字可引用材料。")
    if high and seconds > high:
        length_note = (f"预计 {seconds:.1f} 秒，超过 {profile.account_id} 的 "
                       f"{low:.0f}–{high:.0f} 秒窗口，复制评审时需要删减")

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
        "claims": [{key: claim[key] for key in CLAIM_MAP_FIELDS if key in claim}
                   for claim in claims],
    }
    report = {
        "schema": DRAFT_SCHEMA,
        "generated_at": _now(),
        "project": str(project),
        "brief_id": brief.get("brief_id"),
        "content_digest": verdict.get("content_digest"),
        "account_id": account_id,
        "route_mode": intent.get("route_mode"),
        "topic": topic,
        "topic_provenance": provenance,
        "source_refs": list(intent.get("source_artifact_refs") or []),
        "evidence": {
            "items": len(pack.items) if pack else 0,
            "characters": pack.characters if pack else 0,
            "sources": [{"evidence_id": item.evidence_id, "title": item.title,
                         "url": item.url, "kind": item.kind,
                         "sha256": item.sha256}
                        for item in (pack.items if pack else [])],
        },
        "claims": [
            {"claim_id": claim["claim_id"], "text": claim["text"],
             "kind": claim["kind"], "provenance": claim["provenance"],
             "language": language_of(claim["text"]),
             "support_status": claim["support_status"],
             "limitation": claim.get("limitation") or "",
             "source_refs": claim.get("source_refs") or []}
            for claim in claims
        ],
        "language_mix": {lang: sum(1 for shot in storyboard["shots"]
                                   if shot["language"] == lang)
                         for lang in {shot["language"] for shot in storyboard["shots"]}},
        "needs_rewrite": sum(1 for shot in storyboard["shots"] if shot["needs_rewrite"]),
        "storyboard": {"shots": len(storyboard["shots"]),
                       "duration_s": round(seconds, 1),
                       "needs_capture": sum(1 for shot in storyboard["shots"]
                                            if shot["needs_capture"]),
                       "length_note": length_note},
        "gates": {"copy_review": "required before any narration is synthesised",
                  "evidence": "every spoken fact is bound to a collected, hashed document"},
    }
    return Draft(project=str(project), brief_id=str(brief.get("brief_id") or ""),
                 account_id=account_id, lines=lines_doc, claim_map=claim_map,
                 storyboard=storyboard,
                 master=_master(profile, brief, beats, claims, report),
                 report=report)


def _bind_documents(project: Path, pack: EvidencePack) -> None:
    """Point every evidence item at the file that exists, and check its digest.

    A pack is written by the collector with project-relative paths; the claim
    contract wants ``project://``. The digest is re-computed here so a pack
    whose document changed after collection is refused rather than quoted.
    """
    import hashlib

    for item in pack.items:
        if not item.document:
            continue
        relative = item.document.replace("\\", "/")
        if relative.startswith("project://"):
            relative = relative[len("project://"):]
        path = Path(project) / relative
        if not path.is_file():
            raise ScriptBlocked("EVIDENCE_PACK_INVALID",
                                f"{item.evidence_id}: 证据文件 {relative} 不存在，"
                                f"请重新采集")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if item.sha256 and digest != item.sha256:
            raise ScriptBlocked("EVIDENCE_PACK_INVALID",
                                f"{item.evidence_id}: {relative} 的内容与记录摘要不符，"
                                f"请重新采集后再生成本稿")
        item.document = f"project://{relative}"
        item.sha256 = digest


def _claims_and_beats(profile: AccountProfile, topic: str, provenance: str,
                      pack: EvidencePack, *, target_seconds: float = 0.0
                      ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    claims: List[Dict[str, Any]] = []
    beats: List[Dict[str, Any]] = []

    def add(claim_id: str, text: str, kind: str, claim_provenance: str, *,
            evidence: Optional[List[Dict[str, Any]]] = None,
            source_refs: Optional[List[str]] = None,
            limitation: str = "", progress: str = "") -> None:
        # Transitions and CTAs assert no fact about the world, so they need no
        # evidence; everything else must name the document it came from.
        supported = bool(evidence) or kind in ("editorial_transition", "cta")
        claims.append({
            "claim_id": claim_id,
            "revision": 1,
            "text": text,
            "kind": kind,
            "assertion_about": "source" if kind == "source" else "none",
            "support_status": SUPPORTED if supported else "PARTIAL",
            "permission_scope": "publishable",
            "limitation": limitation,
            "evidence": evidence or [],
            "appearances": [{"surface": "narration", "text": text}],
            "provenance": claim_provenance,
            "source_refs": source_refs or [],
        })
        beats.append({
            "placement_id": f"P-{len(beats) + 1:02d}",
            "claim_id": claim_id,
            "text": text,
            "semantic_progress": progress or kind,
            "views": [],
        })

    # The opening names the subject and says where it came from. A topic the
    # user supplied is stated as theirs; only a title that came from a source
    # is called a source's title.
    if provenance == "user_supplied_topic":
        opening = f"这一期讲你提的问题：{topic}。"
    else:
        opening = f"这一期讲这条来源标题里的问题：{topic}。"
    add("C-01", opening, "editorial_transition", provenance,
        progress="the episode names its subject and who chose it")

    # Quote material until the account's window is plausibly filled, and stop
    # when the pack runs out. Nothing is stretched: if the material ends before
    # the window does, the caller is told the episode is too thin.
    spoken = line_seconds(opening)
    index = 1
    for item, sentence in quotes(pack):
        if index > MAX_QUOTES:
            break
        if target_seconds and spoken >= target_seconds * 0.95:
            break
        claim_id = f"C-{index + 1:02d}"
        add(claim_id, sentence, "source", "verified_factual_claim",
            evidence=[{
                "evidence_id": f"E-{claim_id}-01",
                "kind": "document",
                "sha256": item.sha256,
                "logical_path": item.document,
                "permission_scope": "publishable",
            }],
            source_refs=[item.url],
            progress=f"quoted from {_host(item.url)}")
        spoken += line_seconds(sentence)
        index += 1

    cta_index = len(claims) + 1
    add(f"C-{cta_index:02d}", "以上内容都能在文末的来源里逐条核对。",
        "cta", "editorial_statement", progress="the episode points back at its sources")
    return claims, beats


def _storyboard(profile: AccountProfile, beats: List[Dict[str, Any]],
                claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_id = {claim["claim_id"]: claim for claim in claims}
    shots: List[Dict[str, Any]] = []
    # One capture per source, not one per sentence: an operator captures the
    # page once and the following lines are spoken over it.
    captured: set = set()
    for index, beat in enumerate(beats):
        claim = by_id[beat["claim_id"]]
        role = _role_for(profile, claim["kind"])
        language = language_of(beat["text"])
        source_key = (claim.get("source_refs") or [None])[0]
        needs_capture = role in CAPTURE_ROLES and source_key not in captured
        if needs_capture:
            captured.add(source_key)
        spoken = line_seconds(beat["text"])
        duration = round(max(spoken, CAPTURE_FLOOR_S) if needs_capture else spoken, 1)
        source = (claim.get("source_refs") or [None])[0]
        shots.append({
            "shot_id": f"S-{index + 1:02d}",
            "placement": beat["placement_id"],
            "unit": beat["placement_id"],
            "narration": beat["text"],
            "image": role,
            "source_type": role,
            "duration": duration,
            "duration_basis": "speech" if duration == spoken else "capture_floor",
            "designed_card": "card" in role,
            "function": claim["kind"],
            "dna_role": role,
            "needs_capture": needs_capture,
            "capture_task": (f"截取 {source} 中与这句引文对应的段落" if needs_capture
                             else None),
            "caption_points": [beat["text"]] if claim["kind"] != "editorial_transition" else [],
            # A quoted English sentence in a Chinese episode is real material
            # that a person has to render into spoken Chinese; the cut must not
            # pretend otherwise, so the shot says it needs a rewrite.
            "language": language,
            "needs_rewrite": language != "zh" and "zh" in (profile.language or ("zh",)),
            "claim_id": beat["claim_id"],
            "evidence_source": source,
        })
    return {"schema": "contentops.storyboard/v1", "size": {"width": 1080, "height": 1920},
            "engine": "capture-first", "shots": shots}


def _master(profile: AccountProfile, brief: Dict[str, Any], beats: List[Dict[str, Any]],
            claims: List[Dict[str, Any]], report: Dict[str, Any]) -> str:
    by_id = {claim["claim_id"]: claim for claim in claims}
    lines = [
        f"# {brief.get('intent', {}).get('topic') or 'script draft'}",
        "",
        f"- account: `{profile.account_id}` ({profile.platform})",
        f"- route: `{brief.get('intent', {}).get('route_mode')}`"
        f" · topic provenance: `{report['topic_provenance']}`",
        f"- brief: `{brief.get('brief_id')}`",
        f"- evidence: {report['evidence']['items']} 条 · "
        f"{report['evidence']['characters']} 字可引用正文",
        f"- estimated length: {report['storyboard']['duration_s']} s at "
        f"{SPEAK_RATE_ZH} 字/秒",
        "",
        "> 这是草稿：每一句事实都绑定到采集并哈希过的文档；",
        "> 复制评审必须由人签字。",
        "",
    ]
    for beat in beats:
        claim = by_id[beat["claim_id"]]
        lines.append(f"## {beat['placement_id']} · {claim['kind']} · {claim['provenance']}")
        lines.append("")
        lines.append(beat["text"])
        lines.append("")
        lines.append(f"- claim: `{claim['claim_id']}` · {claim['support_status']}")
        for ref in claim.get("source_refs") or []:
            lines.append(f"- source: {ref}")
        if claim.get("limitation"):
            lines.append(f"- limit: {claim['limitation']}")
        lines.append("")
    return "\n".join(lines)


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


def check(project: Path, *, root: Optional[Path] = None) -> Dict[str, Any]:
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
            continue
        claim = claim_map.by_id(str(beat.get("claim_id")))
        if claim.text != beat.get("text"):
            failures.append(f"{beat.get('placement_id')} narration is not the text of "
                            f"its claim; a paraphrase is a different claim")

    # Provenance: a user's topic may never be presented as a source's title.
    brief = handoff.read_brief(project)
    report_path = project / REPORT_DIR / REPORT_FILE
    reported = {}
    if report_path.is_file():
        try:
            reported = json.loads(report_path.read_text(encoding="utf-8"))
        except ValueError:
            reported = {}
    if brief is not None:
        route = str((brief.get("intent") or {}).get("route_mode") or "")
        for claim in reported.get("claims") or []:
            if claim.get("provenance") == "source_original_title" and route == "USER_TOPIC":
                failures.append(f"{claim.get('claim_id')} claims a source original title "
                                f"in a USER_TOPIC run; the topic came from the user")

    gate = copy_review.status(project)
    return {"ok": not failures, "reason": "OK" if not failures else "CLAIM_MISMATCH",
            "failures": failures, "copy_review": gate}
