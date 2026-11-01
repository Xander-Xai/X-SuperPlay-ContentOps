"""The prompt a record was written from: a reference, never a generator.

The vendored workflow keeps five mega-prompts under ``vendor/x-growth-os/prompts/``:
a daily-post brief, a GitHub-URL-to-post brief, a high-signal-to-post brief, a
tutorial-to-post brief and a visual brief. Each one states, in prose, what a post
must contain before it may be published.

This module resolves a *reference* to one of them and reads back that prompt's own
requirement headings as a checklist. It never calls a model and never writes copy.
The reason is the same as everywhere else on this track: a prompt is advice, and
advice that can be silently skipped is not a gate. What is checkable is the
reference itself — that the account declares the prompt, and that the file it
names is really in this tree.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

#: The repository root, so a prompt path can be repo-relative like the rest of
#: the vendored references (`unique_artifact_ref`, the account's own prompt file).
REPO_ROOT = Path(__file__).resolve().parents[3]

#: A markdown link, so its text is not mistaken for a requirement heading.
_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")

#: A requirement heading: a bold lead-in that names a rule. The vendored prompts
#: write the colon inside the bold ("**先研究再写：**") or right after it
#: ("**四大内容方向与路由**："), and both are the same kind of heading.
_BOLD = re.compile(r"\*\*([^*\n]{4,120}?)\*\*[ \t]*[：:]"
                   r"|\*\*([^*\n]{4,120}[：:])\*\*")

#: A requirement heading that is only punctuation carries no checklist.
_MEANINGLESS = re.compile(r"^[\W_]+$")


def prompt_map(account: Dict[str, Any]) -> Dict[str, str]:
    """The prompts this account declares, as ``{name: repo-relative path}``."""
    editorial = account.get("editorial") or {}
    raw = editorial.get("prompts") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value).strip()
            for key, value in raw.items()
            if isinstance(value, str) and value.strip()}


def prompt_path(account: Dict[str, Any], name: str) -> Optional[Path]:
    """The file a prompt name points at, or ``None`` when the name is unknown."""
    prompts = prompt_map(account)
    if name not in prompts:
        return None
    candidate = Path(prompts[name])
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


def prompt_checklist(path: Path) -> List[str]:
    """The requirement headings a prompt states, in the order it states them.

    The vendored prompts name each of their rules in a bold lead-in. Reading them
    back is how ``--new`` can show a person what a prompt will ask of them
    without inventing a checklist of our own.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    stripped = _LINK.sub(" ", text)
    seen: List[str] = []
    for match in _BOLD.finditer(stripped):
        item = (match.group(1) or match.group(2) or "").strip().rstrip(":：").strip()
        if not item or _MEANINGLESS.match(item):
            continue
        if item in seen:
            continue
        seen.append(item)
    return seen


def resolve(account: Dict[str, Any], name: str) -> Tuple[str, Optional[Path], Optional[str]]:
    """Resolve a prompt name to its path.

    Returns ``(name, path, code)``. ``code`` is ``PROMPT_REF_UNKNOWN`` when the
    account does not declare the name and ``PROMPT_REF_ABSENT`` when it declares
    it but the file is not in this tree. Both are refusals, not warnings.
    """
    prompts = prompt_map(account)
    if name not in prompts:
        return name, None, "PROMPT_REF_UNKNOWN"
    path = prompt_path(account, name)
    if path is None or not path.is_file():
        return name, path, "PROMPT_REF_ABSENT"
    return name, path, None
