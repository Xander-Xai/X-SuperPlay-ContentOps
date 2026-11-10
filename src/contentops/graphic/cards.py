"""Render HTML cards to PNG and gate each one on the card-design audit.

Why this module exists
----------------------
The repository can already render a card (`render_card.py`) and audit one
(`card_audit.py`), but nothing turned "render the cards, then check every one of
them" into a single recorded step. A human doing it by hand produced an image
with no receipt, and a later reader could not tell whether the density gate had
run at all.

So this is an *orchestrator*, not a renderer. It adds no drawing code: the
upstream scripts under the pinned Easel runtime stay the only implementation.
What it adds is the thing they do not provide together — one receipt that binds
the source HTML, every produced file, and every audit verdict to digests.

What it deliberately does not do
--------------------------------
- It does not start the Easel host, call an agent, or touch a network provider.
- It does not approve, publish or set ``production_ready``. A PASS here means the
  cards are dense enough to review; the human review is a separate artifact.
- It does not delete pre-existing images in the output directory. A file this run
  did not produce is reported as ``ignored_existing`` rather than removed, because
  deleting an operator's file to tidy a receipt is not this tool's decision.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "CardRenderError",
    "DEFAULT_SELECTOR",
    "SCHEMA",
    "build_receipt",
    "parse_audit_output",
    "parse_render_output",
    "plan",
    "run",
    "write_receipt",
]

SCHEMA = "contentops.card-render/v1"
DEFAULT_SELECTOR = ".card"

#: ``render_card.py`` prints one line per saved file, prefixed with a check mark.
_SAVED_LINE = re.compile(r"^\s*✅\s+(.+?)\s+\(\s*[\d.]+\s*KB\s*\)\s*$")

#: The renderer's own message when the Playwright browser build it expects is
#: absent. Recognising it lets the refusal name the real remedy instead of
#: reporting a generic failure.
_BROWSER_MISSING = re.compile(
    r"Executable doesn't exist at|playwright install chromium", re.IGNORECASE)


class CardRenderError(ValueError):
    """The cards could not be rendered or audited, with a stable reason code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail

    def as_dict(self) -> Dict[str, str]:
        return {"state": "BLOCKED", "code": self.code, "detail": self.detail}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _inside(base: Path, candidate: Path, label: str) -> Path:
    """Resolve ``candidate`` and refuse anything outside ``base``."""
    resolved = Path(candidate).resolve()
    try:
        resolved.relative_to(Path(base).resolve())
    except ValueError:
        raise CardRenderError(
            "PATH_ESCAPES_PROJECT",
            f"{label} resolves outside the project: {resolved.as_posix()}") from None
    return resolved


@dataclass(frozen=True)
class CardPlan:
    """Every path and setting a run will use, resolved before anything runs."""

    project: Path
    html: Path
    out_dir: Path
    renderer: Path
    auditor: Path
    selector: str = DEFAULT_SELECTOR
    width: int = 1080
    height: int = 1440
    scale: int = 1


def plan(
    project: Path,
    *,
    runtime_root: Path,
    html: Optional[Path] = None,
    out_dir: Optional[Path] = None,
    selector: str = DEFAULT_SELECTOR,
    width: int = 1080,
    height: int = 1440,
    scale: int = 1,
) -> CardPlan:
    """Resolve and validate every input. Raises before any process starts."""
    project = Path(project).resolve()
    if not project.is_dir():
        raise CardRenderError("PROJECT_MISSING", project.as_posix())

    html_path = _inside(project, html or project / "assets" / "cards" / "cards.html", "html")
    if not html_path.is_file():
        raise CardRenderError("HTML_MISSING", html_path.as_posix())
    if html_path.suffix.lower() not in (".html", ".htm"):
        raise CardRenderError("HTML_INVALID", f"expected .html, got {html_path.suffix!r}")

    out_path = _inside(project, out_dir or project / "assets" / "cards", "out-dir")
    if not out_path.is_dir():
        raise CardRenderError("OUT_DIR_MISSING", out_path.as_posix())

    runtime_root = Path(runtime_root).resolve()
    renderer = runtime_root / "skills" / "shared" / "scripts" / "render_card.py"
    auditor = (runtime_root / "skills" / "openclaw" / "card-design"
               / "scripts" / "card_audit.py")
    for label, tool in (("renderer", renderer), ("auditor", auditor)):
        if not tool.is_file():
            raise CardRenderError(
                "UPSTREAM_TOOL_MISSING",
                f"{label} not found at {tool.as_posix()}; the pinned Easel runtime is "
                f"required and is never copied into this repository")

    if width <= 0 or height <= 0 or scale <= 0:
        raise CardRenderError("SPEC_INVALID",
                              f"width/height/scale must be positive, got "
                              f"{width}x{height}@{scale}")

    return CardPlan(project=project, html=html_path, out_dir=out_path,
                    renderer=renderer, auditor=auditor, selector=selector,
                    width=width, height=height, scale=scale)


def parse_render_output(text: str) -> List[str]:
    """Every saved path the renderer reported, in its own order."""
    saved: List[str] = []
    for line in (text or "").splitlines():
        match = _SAVED_LINE.match(line)
        if match:
            saved.append(match.group(1).strip())
    return saved


def parse_audit_output(text: str) -> Dict[str, Any]:
    """The JSON object ``card_audit.py audit --json`` prints for one file."""
    body = (text or "").strip()
    if not body:
        raise CardRenderError("AUDIT_OUTPUT_EMPTY",
                              "the auditor printed nothing; a silent audit is not a pass")
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise CardRenderError("AUDIT_OUTPUT_UNPARSABLE",
                              f"the auditor output was not JSON: {exc}") from None
    if not isinstance(payload, dict) or "pass" not in payload:
        raise CardRenderError("AUDIT_OUTPUT_INVALID",
                              "the auditor output carries no 'pass' verdict")
    return payload


def _renderer_argv(card_python: str, p: CardPlan) -> List[str]:
    return [card_python, str(p.renderer), "--html", str(p.html),
            "--out-dir", str(p.out_dir), "--all", p.selector,
            "--width", str(p.width), "--height", str(p.height),
            "--scale", str(p.scale)]


def _auditor_argv(card_python: str, p: CardPlan, image: Path) -> List[str]:
    return [card_python, str(p.auditor), "audit", "-f", str(image), "--json"]


def run(
    p: CardPlan,
    *,
    card_python: str,
    runner: Any,
    timeout: int = 300,
) -> Dict[str, Any]:
    """Render the cards, audit every produced file, and return the receipt body.

    ``runner`` is required and injected: this module starts no process itself, so
    the Windows hidden-window policy stays in ``scripts/`` where the repository
    enforces it. The runner is called as ``runner(argv, timeout=...)`` and must
    return an object with ``returncode``, ``stdout`` and ``stderr``.

    The child inherits the operator's environment. That matters: the renderer
    needs ``PLAYWRIGHT_BROWSERS_PATH`` and ``PATH``, and replacing the environment
    with a two-variable dict is exactly how a working renderer turns into an
    ImportError.
    """
    rendered = runner(_renderer_argv(card_python, p), timeout=timeout)
    render_text = (rendered.stdout or "") + (rendered.stderr or "")
    if rendered.returncode != 0:
        if _BROWSER_MISSING.search(render_text):
            raise CardRenderError(
                "PLAYWRIGHT_BROWSER_MISSING",
                "the renderer could not launch Chromium. Point CONTENTOPS_CARD_PYTHON "
                "at an interpreter whose Playwright matches an installed browser build, "
                "and set PLAYWRIGHT_BROWSERS_PATH. Installing a browser is a separate, "
                "authorised step. Renderer said: " + render_text.strip()[-400:])
        raise CardRenderError("RENDER_FAILED", render_text.strip()[-600:])

    saved = parse_render_output(render_text)
    if not saved:
        raise CardRenderError(
            "NO_CARDS_RENDERED",
            "the renderer reported no saved files; a selector that matches nothing "
            "is not an empty success. Renderer said: " + render_text.strip()[-400:])

    audits: List[Dict[str, Any]] = []
    for path_text in saved:
        image = Path(path_text)
        if not image.is_file():
            raise CardRenderError("RENDER_OUTPUT_MISSING",
                                  f"the renderer reported {image.as_posix()} but it is absent")
        audit_run = runner(_auditor_argv(card_python, p, image), timeout=timeout)
        verdict = parse_audit_output((audit_run.stdout or ""))
        audits.append({
            "path": image.name,
            "sha256": _sha256(image),
            "bytes": image.stat().st_size,
            "size": verdict.get("size"),
            "pass": bool(verdict.get("pass")),
            "span": verdict.get("span"),
            "bottom_dead": verdict.get("bottom_dead"),
            "max_gap": verdict.get("max_gap"),
            "fill": verdict.get("fill"),
            "bands": verdict.get("bands"),
            "problems": list(verdict.get("problems") or []),
        })

    produced = {Path(item["path"]).name for item in audits}
    existing = sorted(
        path.name for path in p.out_dir.glob("*.png") if path.name not in produced)

    return build_receipt(p, audits=audits, ignored_existing=existing,
                         card_python=card_python)


def build_receipt(p: CardPlan, *, audits: Sequence[Dict[str, Any]],
                  ignored_existing: Sequence[str], card_python: str) -> Dict[str, Any]:
    """Assemble the receipt. Never records approval; only measurements."""
    all_pass = bool(audits) and all(item["pass"] for item in audits)
    receipt: Dict[str, Any] = {
        "schema": SCHEMA,
        "project": p.project.name,
        "html": {
            "path": "project://" + p.html.relative_to(p.project).as_posix(),
            "sha256": _sha256(p.html),
        },
        "spec": {"width": p.width, "height": p.height, "scale": p.scale,
                 "selector": p.selector},
        "tools": {
            "renderer": "repo-relative runtime tool; see runtime/easel.lock.json",
            "renderer_file": p.renderer.name,
            "auditor_file": p.auditor.name,
            "interpreter": Path(card_python).name,
        },
        "cards": list(audits),
        "card_count": len(audits),
        "ignored_existing": list(ignored_existing),
        "audit_status": "PASS" if all_pass else "FAIL",
        "status": "AWAITING_MANUAL_REVIEW" if all_pass else "BLOCKED",
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "NOT_STARTED",
        "cannot": [
            "a density PASS is not a readability judgement, a fact check or an approval",
            "these cards are illustration, never evidence for any claim",
            "this receipt grants no publication authority for any platform",
        ],
    }
    fingerprint = hashlib.sha256(json.dumps(
        {"html": receipt["html"], "spec": receipt["spec"],
         "cards": [{k: item[k] for k in ("path", "sha256", "pass")} for item in audits]},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    receipt["render_fingerprint"] = fingerprint
    return receipt


def write_receipt(project: Path, receipt: Dict[str, Any]) -> Path:
    """Write ``receipts/card-render.json`` under the project."""
    target = Path(project).resolve() / "receipts" / "card-render.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target
