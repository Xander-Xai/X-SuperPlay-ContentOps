"""Where the build products live.

A checkout holds code, evidence and receipts. What a run *produces* -- a
render, a draft, a card, a log, scratch state -- is product: disposable by
construction, large by nature, and useless to anyone reviewing a diff.

The default keeps products in the repository, because that is where every
script and every historical receipt expects them. Set
``CONTENTOPS_OUTPUT_ROOT`` to move them out:

    CONTENTOPS_OUTPUT_ROOT=D:\\AI-Outputs\\X-SuperPlay-ContentOps\\2026-11-12

and the three product roots become ``<root>/workspace``,
``<root>/deliverables`` and ``<root>/tmp``. Nothing else moves: the tracked
baseline projects stay under ``projects/`` because they are evidence, not
product, and a receipt that points at one must keep pointing at it.

The variable is read from the process environment. The repository's ``.env``
loader injects it, so an operator sets it once in ``.env`` (gitignored)
instead of in every shell, and CI -- which does not set it -- keeps the
in-repository layout byte for byte.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

OUTPUT_ROOT_ENV = "CONTENTOPS_OUTPUT_ROOT"

#: The repository root, derived from this file's location
#: (``src/contentops/paths.py`` -> three levels up).
REPO_ROOT = Path(__file__).resolve().parents[2]


def output_root() -> Optional[Path]:
    """The configured external output root, or None when unset."""
    load_repo_env()
    raw = os.environ.get(OUTPUT_ROOT_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def is_external() -> bool:
    """True when products live outside the checkout."""
    return output_root() is not None


def workspace_root(repo_root: Optional[Path] = None) -> Path:
    """Where experiments live."""
    base = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    root = output_root()
    if root is None:
        return base / "projects" / "_local"
    return root / "workspace"


def deliverables_root() -> Path:
    """Where finished products are promoted to."""
    root = output_root()
    if root is None:
        return REPO_ROOT / "outputs"
    return root / "deliverables"


def tmp_root() -> Path:
    """Where scratch and verification state lives."""
    root = output_root()
    if root is None:
        return REPO_ROOT / ".verify-tmp"
    return root / "_tmp"


_env_loaded = False


def _is_ignored(rel: str) -> bool:
    """Whether Git ignores this path -- i.e. it is local, untracked state."""
    try:
        proc = subprocess.run(["git", "check-ignore", "-q", "--", rel],
                              cwd=REPO_ROOT, capture_output=True)
    except Exception:  # pragma: no cover - no git, no judgement
        return False
    return proc.returncode == 0


def load_repo_env() -> None:
    """Inject the repository's gitignored ``.env`` into the environment.

    ``CONTENTOPS_OUTPUT_ROOT`` is an operator setting, so it belongs in the
    same place as the provider keys rather than in every shell.

    The three properties of the repository's own loader are kept here: a
    Git-tracked ``.env`` is refused (reading it would treat a committed
    secret as configuration), an existing environment variable always wins,
    and the file is parsed without expanding anything.

    ``output_root`` calls this once, before it reads the variable, so a
    script does not have to remember to. It is idempotent, and a test can
    set ``_env_loaded`` to keep the file out of the picture.
    """
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return
    if not _is_ignored(".env"):
        return
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if not name or not value:
            continue
        if os.environ.get(name):
            continue
        os.environ[name] = value


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def resolve_project(value: str) -> Path:
    """Resolve a ``--project`` argument to the directory that holds it.

    Accepts an absolute path, a path relative to the repository, or the
    short ``projects/_local/<slug>`` form. The short form is redirected to
    the external workspace when one is configured and the slug exists there,
    so the command line a run already uses keeps working after the products
    move out of the checkout.

    The short form is recognised *before* the path is resolved, because
    ``Path.resolve()`` follows a directory junction on Windows: once the
    experiment sandbox is a link, the resolved path already points at the
    archive and the comparison would be made against the wrong root.
    """
    raw = Path(value)
    candidate = raw if raw.is_absolute() else REPO_ROOT / raw
    try:
        parts = candidate.relative_to(REPO_ROOT).parts
    except ValueError:
        parts = ()
    if parts[:2] == ("projects", "_local"):
        slug = Path(*parts[2:]) if len(parts) > 2 else Path()
        external = workspace_root() / slug
        if external.is_dir():
            return external.resolve()
    return candidate.resolve()


def project_roots(repo_root: Optional[Path] = None) -> list[Path]:
    """The roots a project directory may legitimately live under.

    Two of them, and both are operator-controlled:

    * the repository's own ``projects/`` -- tracked baselines, whose evidence
      and receipts other machines re-verify;
    * the configured workspace -- experiments, whose products live outside
      the checkout.

    A guard that only knew about the first would refuse every experiment
    once the sandbox moves out, which is the whole point of moving it out.
    """
    base = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    return [base / "projects", workspace_root(base)]


def trusted_project_root(path: Path,
                         repo_root: Optional[Path] = None) -> Optional[Path]:
    """The trusted project root ``path`` belongs to, or None.

    Membership is by containment, so the caller decides what shape it wants
    below the root: a baseline is one level down, the experiment sandbox is
    two. The roots are checked in order, and the repository's ``projects/``
    comes first, so a sandbox path is reported against the root that owns
    the nesting rather than against the workspace that happens to contain it.
    """
    resolved = Path(path).resolve()
    for root in project_roots(repo_root):
        root = Path(root).resolve()
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return root
    return None


def relative_label(path: Path, repo_root: Optional[Path] = None) -> str:
    """How a path is written into a receipt.

    Inside the repository the historical relative form is kept. Outside it,
    the path is written relative to the output root when possible, so a
    receipt stays readable and does not hard-code one machine's layout.
    """
    base = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    resolved = Path(path).resolve()
    root = output_root()
    if root is not None and _within(resolved, root):
        return resolved.relative_to(root).as_posix()
    if _within(resolved, base):
        return resolved.relative_to(base).as_posix()
    return resolved.as_posix()


def resolve_label(label: str, repo_root: Optional[Path] = None) -> Path:
    """Turn a stored path label back into a path on this machine.

    A label is written relative to the repository root, or -- when the
    products live outside it -- relative to the output root. This resolves
    both, so a stored path keeps meaning the same thing wherever the
    products were written.
    """
    base = Path(repo_root).resolve() if repo_root is not None else REPO_ROOT
    candidate = Path(label)
    if candidate.is_absolute():
        return candidate
    repo_side = base / candidate
    if repo_side.exists():
        return repo_side
    root = output_root()
    if root is not None:
        external_side = root / candidate
        if external_side.exists():
            return external_side
    return repo_side


def scratch_candidates(rel: str) -> list[str]:
    """Every place a scratch file may live.

    A historical script that probed ``.verify-tmp/<rel>`` has to keep finding
    that file after the scratch root moves out of the checkout. The
    in-repository spelling is kept first, because it is what the receipts
    and the historical reports name; the configured scratch root is added as
    a second candidate.
    """
    candidates = [f".verify-tmp/{rel}"]
    root = output_root()
    if root is not None:
        candidates.append((root / "_tmp" / rel).as_posix())
    return candidates
