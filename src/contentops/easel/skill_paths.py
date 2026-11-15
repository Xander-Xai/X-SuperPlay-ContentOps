"""Resolve Easel skills across upstream's v0.2/v0.3 layout transition."""

from pathlib import Path

#: Layer names upstream has used for bundled skills, in the order the
#: compatibility resolver tries them. A caller that knows which engine it is
#: talking to must pass `layout` instead of relying on this order.
LAYERS = ("openclaw", "builtin")


def resolve_skill_dir(runtime_root: Path, skill_name: str, *, layout: str | None = None) -> Path:
    """Return a skill directory from a known Easel layout, without escaping root.

    v0.2.x stores bundled skills under ``skills/openclaw``; v0.3.x moved them to
    ``skills/builtin``. Passing ``layout`` reads exactly that layer — which is
    what an engine-aware caller should do, because "try both and take the first
    hit" silently resolves against the wrong tree when a checkout happens to
    contain both. Omitting ``layout`` keeps the historical compatibility order
    so existing callers behave identically.
    """
    root = Path(runtime_root).resolve()
    if not skill_name or Path(skill_name).name != skill_name or skill_name in {".", ".."}:
        raise ValueError("invalid Easel skill name")
    if layout is not None and layout not in LAYERS:
        raise ValueError(f"unknown Easel skill layout {layout!r}; expected one of {LAYERS}")
    layers = (layout,) if layout else LAYERS
    for layer in layers:
        candidate = root / "skills" / layer / skill_name
        if candidate.is_dir() and candidate.resolve().is_relative_to(root):
            return candidate
    tried = ", ".join(f"skills/{layer}" for layer in layers)
    raise FileNotFoundError(f"Easel skill {skill_name!r} not found under {tried} in {root}")
