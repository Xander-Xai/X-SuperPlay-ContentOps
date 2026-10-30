"""Bridge ContentOps -> one OpenClaw agent turn (profile ``easel``).

The pipeline used to reach Easel by running its skill scripts directly, so the
harness layer (model choice, tool loop, skill selection, self-repair) was inert.
This is the one place that runs a real agent turn.

Invariants
----------
- Every path leaves a receipt, including a bad account slug or a missing CLI.
- A receipt never contains an absolute path: committed receipts use
  ``repo://`` / ``project://`` refs, matching every other builder here.
- ``skill_route`` is copied from the account DNA, never guessed.
- An agent turn is never a human approval: ``human_review`` stays ``required``.

Two Windows behaviours are load-bearing:

- ``agent exec`` deletes a temp state dir on exit and fails with
  ``EBUSY: openclaw.sqlite-shm``; ``--state-dir`` keeps one per project.
- The CLI interleaves ANSI log lines around the JSON envelope, so the envelope
  is located with ``raw_decode`` rather than ``json.loads(stdout)``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from process_utils import hidden_run  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PROFILE = os.environ.get("OPENCLAW_PROFILE", "easel")
SCHEMA = "contentops.openclaw-agent/v1"
ACCOUNT_DIR = ROOT / "config" / "accounts"

try:  # contract ids are the repository's single source of truth for stage names
    from contentops.workflow.contract import CONTRACT_ID, STAGE_IDS  # noqa: E402
except Exception:  # noqa: BLE001 - the bridge stays usable without src on the path
    CONTRACT_ID, STAGE_IDS = "", ()


def load_account(slug: str) -> dict:
    """The account DNA for ``slug``; its rules override every upstream default."""
    path = ACCOUNT_DIR / f"{slug}.json"
    if not path.is_file():
        raise FileNotFoundError(f"account DNA not found: {path.relative_to(ROOT).as_posix()}")
    return json.loads(path.read_text(encoding="utf-8"))


def _route_bases() -> dict:
    """Resolve the ``path_base`` values a DNA entry may declare.

    Asks the same helpers ``check_account_dna.py`` uses, so the bridge and the
    DNA checker cannot disagree about whether a declared script exists.
    """
    from skill_route import CATALOG_ROOTS, SHARED_SKILL_ROOT

    # ``catalog()`` returns the first existing root, which may be the gzh
    # vendor. A ``catalog`` path base means the Easel catalog, so find an
    # actual ``openclaw`` root instead of treating any vendor as Easel.
    easel_root = None
    for root in CATALOG_ROOTS:
        if root.name == "openclaw" and root.is_dir():
            easel_root = root.parent.parent
            break
    return {"catalog": easel_root, "shared": SHARED_SKILL_ROOT, "repo": ROOT}


def declared_route(slug: str, step: str) -> dict | None:
    """The DNA's declared skill for ``step``, resolved against its declared base.

    Returns ``None`` when the account declares no route for that step. A declared
    route that does not resolve comes back with ``resolved: False`` and a remedy
    rather than falling back to an upstream default.
    """
    dna = load_account(slug)
    entry = next((e for e in dna.get("skill_route", []) if e.get("step") == step), None)
    if entry is None:
        return None

    base_name = entry.get("path_base", "catalog")
    base = _route_bases().get(base_name)
    rel = entry.get("script", "")
    resolved = (base / rel) if base and rel else None
    exists = bool(resolved and resolved.exists())
    return {
        "step": entry.get("step"),
        "skill": entry.get("skill"),
        "script": rel,
        "path_base": base_name,
        "resolved": exists,
        "why": entry.get("why", ""),
        "remedy": None if exists else (
            f"declared script for step {step!r} does not exist under path_base "
            f"{base_name!r}: {rel}"
        ),
    }


def _receipt_route(route: dict | None, reason: str | None) -> dict:
    """The receipt's ``skill_route`` block: the documented ``{name, script, why}``.

    ``step``/``path_base``/``resolved`` are kept so a reviewer can re-check the
    declaration without opening the DNA.
    """
    if route is None:
        return {"name": None, "script": None,
                "why": reason or "no account DNA supplied to the bridge"}
    return {
        "name": route.get("skill"),
        "script": route.get("script"),
        "why": route.get("why", ""),
        "step": route.get("step"),
        "path_base": route.get("path_base"),
        "resolved": route.get("resolved"),
    }


def _logical(path: Path | str | None, project_dir: Path | None = None) -> str | None:
    """A commit-safe reference for ``path``: ``project://``, ``repo://`` or the name.

    Committed receipts here carry no absolute paths; the project QC report states
    that rule and every existing receipt follows it.
    """
    if path is None:
        return None
    p = Path(path).resolve()
    for base, prefix in ((project_dir, "project://"), (ROOT, "repo://")):
        if base is None:
            continue
        try:
            rel = p.relative_to(Path(base).resolve()).as_posix()
        except ValueError:
            continue
        return prefix + ("" if rel == "." else rel)
    return "external://" + p.name


def _redact_argv(argv: Sequence[str], known: dict[str, str]) -> list[str]:
    """Replace run-specific absolute paths with stable placeholders."""
    out = []
    for arg in argv:
        out.append(known.get(arg, arg))
    return out


def _openclaw_cmd() -> list[str]:
    """argv prefix for the openclaw CLI.

    Windows `openclaw` on PATH is a ``.cmd`` shim that CreateProcess cannot run,
    and a ``cmd /c`` wrapper truncates messages at newlines. Running
    ``openclaw.mjs`` through node avoids both.
    """
    node = shutil.which("node")
    oc = shutil.which("openclaw")
    if node and oc:
        resolved = Path(oc).resolve()
        if resolved.suffix == ".mjs" and resolved.is_file():
            return [node, str(resolved)]
    if node:
        candidates = [
            Path(node).resolve().parent.parent / "lib" / "node_modules" / "openclaw" / "openclaw.mjs",
            Path(node).resolve().parent / "node_modules" / "openclaw" / "openclaw.mjs",
            Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "openclaw" / "openclaw.mjs",
        ]
        for cand in candidates:
            if cand.is_file():
                return [node, str(cand)]
    if oc:
        return [oc]
    raise FileNotFoundError("openclaw CLI not found: no 'node'+openclaw.mjs and no 'openclaw' on PATH")


def _parse_envelope(stdout: str) -> dict | None:
    """Locate the JSON envelope among the CLI's interleaved log lines."""
    decoder = json.JSONDecoder()
    for idx in range(len(stdout) - 1, -1, -1):
        if stdout[idx] != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stdout, idx)
        except ValueError:
            continue
        if isinstance(obj, dict) and "status" in obj:
            return obj
    return None


def _decode(raw: bytes | None) -> str:
    """Decode CLI output that is UTF-8 on one launch and the OEM codepage on another.

    Decoding CP936 bytes as UTF-8 with replacement turned Chinese replies into
    ``Ŀ¼��``. Strict UTF-8 is tried first because it is unambiguous when it
    succeeds; GBK is the fallback for bytes that cannot be UTF-8.
    """
    if not raw:
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _git_state(cwd: Path) -> set[str]:
    """Paths dirty in the working tree, for before/after comparison."""
    try:
        proc = hidden_run(["git", "status", "--porcelain"], cwd=str(cwd), timeout=60)
    except Exception:  # noqa: BLE001 - no git / not a repo: no snapshot, not a failure
        return set()
    if proc.returncode != 0:
        return set()
    out = set()
    for line in (proc.stdout or "").splitlines():
        if len(line) <= 3:
            continue
        path = line[3:].strip()
        if " -> " in path:  # a rename reports "old -> new"; the new path is the change
            path = path.split(" -> ")[-1]
        out.add(path.strip().strip('"'))
    return out


def run_agent(
    prompt: str,
    *,
    stage: str,
    project: Path | str | None = None,
    cwd: Path | str | None = None,
    timeout: int = 600,
    read_only: bool = False,
    model: str | None = None,
    config: Path | str | None = None,
    account: str | None = None,
    step: str | None = None,
) -> dict:
    """Run one isolated agent turn and return a receipted result.

    ``project`` anchors the persistent state dir and the receipt location; without
    it, receipts go under the gitignored state dir so the repo root stays clean.
    ``account``/``step`` copy the declared skill route into the receipt.
    ``read_only`` is advisory: the agent can still write, and whatever it touches
    is listed in ``changed_files``.
    """
    work_cwd = Path(cwd).resolve() if cwd else ROOT
    project_dir = Path(project).resolve() if project else None
    anchor = project_dir or work_cwd

    state_dir = anchor / ".openclaw" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    receipts = (project_dir / "receipts") if project_dir else (anchor / ".openclaw" / "receipts")
    receipts.mkdir(parents=True, exist_ok=True)

    # A broken DNA must cost no model call and must still leave evidence.
    route = None
    route_error = None
    if account:
        try:
            route = declared_route(account, step or stage)
            if route is None:
                route_error = (f"account {account!r} declares no skill_route for step "
                               f"{step or stage!r}")
        except FileNotFoundError as exc:
            route_error = str(exc)
        except (OSError, ValueError) as exc:
            route_error = f"account DNA unreadable: {type(exc).__name__}: {exc}"
    route_doc = _receipt_route(route, route_error)

    wrapped = prompt
    if read_only:
        wrapped = ("READ-ONLY TASK. Do not create, modify, move or delete any file. "
                   "Do not run any command with side effects. Investigate and report only.\n\n"
                   + prompt)

    prompt_path = state_dir / f"prompt-{stage}.md"
    prompt_path.write_text(wrapped, encoding="utf-8")
    prompt_sha = hashlib.sha256(wrapped.encode("utf-8")).hexdigest()

    contract = CONTRACT_ID if stage in STAGE_IDS else None

    if route_error:
        result = {"status": "BLOCKED", "stage": stage, "reason": route_error,
                  "remedy": "declare the step in config/accounts/<slug>.json skill_route",
                  "skill_route": route_doc, "contract": contract}
        _write_receipt(receipts, stage, result, prompt_sha, argv=[], project_dir=project_dir,
                       changed=[], duration_s=0.0, usage={})
        return result

    try:
        base = _openclaw_cmd()
    except FileNotFoundError as exc:
        result = {"status": "BLOCKED", "stage": stage, "reason": str(exc),
                  "remedy": "install OpenClaw (npm i -g openclaw) or put it on PATH",
                  "skill_route": route_doc, "contract": contract}
        _write_receipt(receipts, stage, result, prompt_sha, argv=[], project_dir=project_dir,
                       changed=[], duration_s=0.0, usage={})
        return result

    argv = base + ["--profile", PROFILE, "agent", "exec", "--json",
                   "--timeout", str(timeout),
                   "--state-dir", str(state_dir),
                   "--cwd", str(work_cwd),
                   "--message-file", str(prompt_path)]
    if model:
        argv += ["--model", model]
    if config:
        argv += ["--config", str(Path(config).resolve())]

    before = _git_state(work_cwd)
    started = time.time()
    proc = None
    timed_out = False
    spawn_error = ""
    try:
        proc = hidden_run(argv, cwd=str(work_cwd), timeout=timeout + 120, text=False,
                          env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
    except Exception as exc:  # noqa: BLE001 - TimeoutExpired and spawn errors alike
        timed_out = True
        spawn_error = f"{type(exc).__name__}: {exc}"
    duration = round(time.time() - started, 1)
    after = _git_state(work_cwd)
    changed = sorted(p for p in (after - before) if not p.replace("\\", "/").startswith(".openclaw/"))

    stdout = _decode(proc.stdout if proc is not None else None)
    stderr = _decode(proc.stderr if proc is not None else None)
    envelope = _parse_envelope(stdout) if stdout else None

    if timed_out:
        result = {"status": "BLOCKED", "stage": stage, "reason": spawn_error,
                  "duration_s": duration, "changed_files": changed}
    elif envelope is None:
        result = {"status": "BLOCKED", "stage": stage,
                  "reason": "no agent JSON envelope in stdout",
                  "returncode": proc.returncode if proc else None,
                  "stderr_tail": stderr[-800:], "duration_s": duration,
                  "changed_files": changed}
    elif envelope.get("ok") and envelope.get("status") == "ok":
        result = {
            "status": "OK", "stage": stage,
            "final": envelope.get("final", ""),
            "session_id": envelope.get("sessionId"),
            "model": envelope.get("model"),
            "provider": envelope.get("provider"),
            "usage": envelope.get("usage", {}),
            "tools": (envelope.get("toolSummary") or {}),
            "assistant_turns": envelope.get("assistantTurns"),
            "duration_s": duration,
            "changed_files": changed,
            # An agent turn is never a human approval.
            "state": "READY_FOR_HUMAN_REVIEW",
        }
    else:
        err = envelope.get("error")
        if isinstance(err, dict):
            err = err.get("message")
        result = {"status": "BLOCKED", "stage": stage,
                  "reason": err or f"agent reported status={envelope.get('status')}",
                  "final": envelope.get("final", ""),
                  "session_id": envelope.get("sessionId"),
                  "usage": envelope.get("usage", {}),
                  "duration_s": duration, "changed_files": changed}

    result["skill_route"] = route_doc
    result["contract"] = contract

    _write_receipt(receipts, stage, result, prompt_sha,
                   argv=_redact_argv(argv, {str(state_dir): "{state_dir}",
                                            str(prompt_path): "{prompt_file}",
                                            str(work_cwd): "{cwd}"}),
                   project_dir=project_dir, changed=changed, duration_s=duration,
                   usage=result.get("usage", {}))
    return result


def _write_receipt(receipts: Path, stage: str, result: dict, prompt_sha: str, *,
                   argv: Sequence[str], project_dir: Path | None,
                   changed: Sequence[str], duration_s: float, usage: dict) -> Path:
    receipt = {
        "schema": SCHEMA,
        "stage": stage,
        "contract": result.get("contract"),
        "skill_route": result.get("skill_route") or _receipt_route(None, None),
        "harness": {"name": "openclaw", "profile": PROFILE},
        "prompt_sha256": prompt_sha,
        "argv": list(argv),
        "project": _logical(project_dir, project_dir),
        "duration_s": duration_s,
        "usage": usage,
        "result": result,
        "agent_changed_files": list(changed),
        "human_review": "required",
    }
    path = receipts / f"openclaw-{stage}.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    import argparse
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Run one OpenClaw agent turn with a receipt.")
    p.add_argument("prompt", nargs="?", help="prompt text (omit to use --prompt-file)")
    p.add_argument("--prompt-file")
    p.add_argument("--stage", required=True)
    p.add_argument("--project")
    p.add_argument("--cwd")
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--read-only", action="store_true")
    p.add_argument("--model")
    p.add_argument("--account", help="account slug under config/accounts/, e.g. x-superplay-1024")
    p.add_argument("--step", help="declared skill_route step to cite (defaults to --stage)")
    p.add_argument("--show-route", action="store_true",
                   help="print the declared route for --account/--step and exit")
    args = p.parse_args()

    if args.show_route:
        if not args.account:
            p.error("--show-route requires --account")
        try:
            route = declared_route(args.account, args.step or args.stage)
        except FileNotFoundError as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            return 4
        print(json.dumps(route, ensure_ascii=False, indent=2))
        return 0 if route and route.get("resolved") else 4

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    if not prompt:
        p.error("provide a prompt argument or --prompt-file")

    res = run_agent(prompt, stage=args.stage, project=args.project, cwd=args.cwd,
                    timeout=args.timeout, read_only=args.read_only, model=args.model,
                    account=args.account, step=args.step)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("status") == "OK" else 4


if __name__ == "__main__":
    sys.exit(main())
