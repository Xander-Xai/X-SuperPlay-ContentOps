"""Resolve Easel skills across upstream's v0.2/v0.3 layout transition."""

from pathlib import Path


def resolve_skill_dir(runtime_root: Path, skill_name: str) -> Path:
    """Return a skill directory from a known Easel layout, without escaping root.

    v0.2.x stores bundled skills under ``skills/openclaw``; v0.3.x moved them
    to ``skills/builtin``. Prefer the legacy location so the production pin
    keeps identical resolution when both happen to exist.
    """
    root = Path(runtime_root).resolve()
    if not skill_name or Path(skill_name).name != skill_name or skill_name in {".", ".."}:
        raise ValueError("invalid Easel skill name")
    for layer in ("openclaw", "builtin"):
        candidate = root / "skills" / layer / skill_name
        if candidate.is_dir() and candidate.resolve().is_relative_to(root):
            return candidate
    raise FileNotFoundError(f"Easel skill {skill_name!r} not found under {root / 'skills'}")
