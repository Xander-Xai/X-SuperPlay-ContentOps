"""The production entries refuse a dirty main checkout, and only that.

What is pinned here
-------------------
1. A clean main checkout still runs. The rule must not become "never produce".
2. A dirty main checkout is refused, the message names the paths, and the guard
   itself writes nothing -- it is a refusal, not a cleanup.
3. ``projects/_local/`` is exempt even when the checkout is dirty, because that
   directory is gitignored and cannot dirty anything.
4. A linked worktree is not the main checkout, and a project outside the repo
   cannot dirty it, so neither is refused.
5. The two production entry points call the guard: ``produce_video.produce()``
   refuses before it writes its first receipt, and ``m5_production.build()``
   refuses before its first stage.
6. The decision is taken once per process. Without that, ``produce_video``
   writing its own receipt and then delegating to M5 would block itself.

Every fixture is a throwaway ``git init`` repository under a temp directory. No
test touches this working tree, and nothing here runs ffmpeg or a render.
"""

from __future__ import annotations

import ast
import contextlib
import io
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.media.checkout_guard import (  # noqa: E402
    DirtyCheckoutError,
    checkout_state,
    ensure_writable_checkout,
    reset_cache,
)
from process_utils import hidden_run  # noqa: E402

import check_untracked_projects  # noqa: E402
import m5_production  # noqa: E402
import produce_video  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def _git(repo: Path, *args: str) -> None:
    result = hidden_run(["git", "-C", str(repo), *args], timeout=60)
    if result.returncode != 0:
        raise AssertionError(f"git {args} failed: {result.stderr or result.stdout}")


def _make_repo(base: Path, *, name: str = "repo") -> Path:
    """A committed repository with one project, ready to be dirtied on purpose."""
    repo = base / name
    (repo / "projects" / "demo").mkdir(parents=True)
    (repo / "projects" / "demo" / "project.yaml").write_text(
        "slug: demo\naccount_slug: demo-account\n", encoding="utf-8")
    (repo / "projects" / "_local").mkdir(parents=True)
    (repo / "projects" / "_local" / ".keep").write_text("", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=test",
         "commit", "-q", "-m", "fixture")
    return repo


def _dirty(repo: Path, relative: str = "projects/demo/receipts/qc-report.json") -> Path:
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{}\n", encoding="utf-8")
    return target


def _snapshot(repo: Path) -> list[tuple[str, int, int]]:
    rows = []
    for path in sorted(repo.rglob("*")):
        if ".git" in path.parts or not path.is_file():
            continue
        stat = path.stat()
        rows.append((path.relative_to(repo).as_posix(), stat.st_size,
                     int(stat.st_mtime_ns)))
    return rows


@test
def test_a_clean_checkout_still_runs():
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        state = ensure_writable_checkout(repo / "projects" / "demo", repo_root=repo)
        assert state["allowed"] is True, state
        assert state["reason"] == "CLEAN", state
        assert state["checkout"] == "MAIN", state


@test
def test_a_dirty_checkout_is_refused_and_nothing_is_touched():
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        dirty = _dirty(repo)
        before = _snapshot(repo)
        try:
            ensure_writable_checkout(repo / "projects" / "demo", repo_root=repo)
        except DirtyCheckoutError as exc:
            message = str(exc)
            state = exc.state
        else:  # pragma: no cover - the assertion message is the point
            raise AssertionError("a dirty main checkout was allowed to write")
        assert state["reason"] == "DIRTY_MAIN_CHECKOUT", state
        assert state["dirty_count"] >= 1, state
        assert "projects/demo" in message, message
        assert "projects/_local/" in message, (
            "the refusal must tell the operator where the experiment belongs")
        assert dirty.exists(), "the guard must not delete untracked work"
        assert _snapshot(repo) == before, "the guard wrote to the checkout"
        print("[ok] 1. a dirty main checkout is refused without touching a file")


@test
def test_local_sandbox_is_exempt_even_when_dirty():
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        _dirty(repo)  # some other unreviewed work
        local = repo / "projects" / "_local" / "experiment"
        local.mkdir(parents=True)
        state = ensure_writable_checkout(local, repo_root=repo)
        assert state["allowed"] is True, state
        assert state["reason"] == "LOCAL_SANDBOX", state
        assert state["local_sandbox"] is True, state


@test
def test_project_outside_the_repository_is_not_judged():
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        _dirty(repo)
        outside = Path(tmp) / "elsewhere"
        outside.mkdir()
        state = checkout_state(outside, repo_root=repo)
        assert state["allowed"] is True, state
        assert state["reason"] == "PROJECT_OUTSIDE_REPO", state


@test
def test_a_directory_that_is_not_a_checkout_is_not_judged():
    """Fixtures run entry points against temp projects; there is no index there."""
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        plain = Path(tmp) / "plain"
        (plain / "projects" / "demo").mkdir(parents=True)
        state = checkout_state(plain / "projects" / "demo", repo_root=plain)
        assert state["allowed"] is True, state
        assert state["reason"] == "NOT_A_CHECKOUT", state
        del repo


@test
def test_a_linked_worktree_is_not_the_main_checkout():
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        worktree = Path(tmp) / "wt"
        result = hidden_run(["git", "-C", str(repo), "worktree", "add", "-q",
                             str(worktree), "-b", "wt-branch"], timeout=120)
        if result.returncode != 0:
            print("[skip] linked worktree could not be created here")
            return
        _dirty(repo)
        state = checkout_state(worktree / "projects" / "demo", repo_root=worktree)
        assert state["allowed"] is True, state
        assert state["reason"] == "NOT_MAIN_CHECKOUT", state
        assert state["checkout"] == "WORKTREE", state


@test
def test_both_entry_points_call_the_guard():
    """Structural: the call is inside produce() and build(), not beside them."""
    checks = ((produce_video.__file__, "produce"),
              (m5_production.__file__, "build"))
    for filename, function_name in checks:
        tree = ast.parse(Path(filename).read_text(encoding="utf-8"))
        function = next((node for node in ast.walk(tree)
                         if isinstance(node, ast.FunctionDef) and node.name == function_name),
                        None)
        assert function is not None, f"{function_name} not found in {filename}"
        called = [node for node in ast.walk(function)
                  if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Name)
                  and node.func.id == "_guard_checkout"]
        assert called, f"{function_name}() does not call _guard_checkout"
    print("[ok] 2. produce() and build() both refuse through the guard")


@test
def test_entry_wrappers_refuse_and_allow_the_same_way():
    """The wrapper each entry calls resolves against that entry's own ROOT."""
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        _dirty(repo)
        local = repo / "projects" / "_local" / "experiment"
        local.mkdir(parents=True)
        saved = (produce_video.ROOT, m5_production.ROOT)
        produce_video.ROOT = repo
        m5_production.ROOT = repo
        try:
            for module in (produce_video, m5_production):
                try:
                    module._guard_checkout(repo / "projects" / "demo")
                except DirtyCheckoutError:
                    pass
                else:
                    raise AssertionError(f"{module.__name__}._guard_checkout allowed a dirty tree")
                module._guard_checkout(local)  # must not raise
        finally:
            produce_video.ROOT, m5_production.ROOT = saved
            reset_cache()
    print("[ok] 3. both wrappers refuse the dirty project and allow projects/_local/")


@test
def test_produce_refuses_before_writing_its_first_receipt():
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        # Dirty somewhere else: the point is that produce() writes nothing of its
        # own before the guard stops it.
        _dirty(repo, "notes/scratch.txt")
        project = repo / "projects" / "demo"
        saved = produce_video.ROOT
        produce_video.ROOT = repo
        try:
            try:
                produce_video.produce(project)
            except DirtyCheckoutError as exc:
                assert exc.state["reason"] == "DIRTY_MAIN_CHECKOUT", exc.state
            else:
                raise AssertionError("produce() ran on a dirty checkout")
        finally:
            produce_video.ROOT = saved
            reset_cache()
        assert not (project / "receipts").exists(), (
            "produce() wrote a receipt before refusing")
    print("[ok] 4. produce() refuses before the first receipt exists")


@test
def test_the_decision_is_taken_once_per_process():
    """A run writes receipts, then delegates to M5. Both must see one verdict."""
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        project = repo / "projects" / "demo"
        first = ensure_writable_checkout(project, repo_root=repo)
        assert first["allowed"] is True, first
        _dirty(repo)  # this run's own output, or another window's edit
        second = ensure_writable_checkout(project, repo_root=repo)
        assert second["allowed"] is True, (
            "the state observed at the start of the run must govern the whole run")
        reset_cache()
        try:
            ensure_writable_checkout(project, repo_root=repo)
        except DirtyCheckoutError:
            pass
        else:
            raise AssertionError("a fresh process did not re-read the checkout")
    print("[ok] 5. one verdict per run, re-read only on the next process")


@test
def test_the_untracked_project_check_fails_on_a_new_directory():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _make_repo(Path(tmp))
        scratch = repo / "projects" / "scratch-20260101"
        (scratch / "receipts").mkdir(parents=True)
        (scratch / "receipts" / "qc-report.json").write_text("{}\n", encoding="utf-8")
        saved = (check_untracked_projects.ROOT, check_untracked_projects.BASELINE)
        check_untracked_projects.ROOT = repo
        check_untracked_projects.BASELINE = repo / "baseline.txt"
        check_untracked_projects.BASELINE.write_text("", encoding="utf-8")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                assert check_untracked_projects.main([]) == 1, (
                    "a new directory must fail the check")
                check_untracked_projects.BASELINE.write_text(
                    "projects/scratch-20260101\n", encoding="utf-8")
                assert check_untracked_projects.main([]) == 0, (
                    "a baselined directory must not fail the check")
                # A tracked project with new output is work in progress, not a
                # stray experiment directory: it is reported, not failed.
                (repo / "projects" / "demo" / "receipts").mkdir()
                (repo / "projects" / "demo" / "receipts" / "new.json").write_text(
                    "{}\n", encoding="utf-8")
                assert check_untracked_projects.main([]) == 0, (
                    "a tracked project's new receipt must not fail the check")
        finally:
            check_untracked_projects.ROOT, check_untracked_projects.BASELINE = saved
    print("[ok] 6. the read-only check fails only on a new untracked project")


@test
def test_a_staged_rename_reports_both_paths_undamaged():
    """Git splits a staged rename into "R  new\\0old" -- the second chunk has
    no status prefix, so a naive [3:] slice corrupts the reported old path."""
    with tempfile.TemporaryDirectory() as tmp:
        reset_cache()
        repo = _make_repo(Path(tmp))
        receipt = repo / "projects" / "demo" / "receipts" / "qc-report.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text("{}\n", encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=test",
             "commit", "-q", "-m", "receipt")
        renamed = receipt.with_name("qc-report-final.json")
        receipt.rename(renamed)
        _git(repo, "add", "-A")
        state = checkout_state(repo / "projects" / "demo", repo_root=repo)
        assert state["allowed"] is False, state
        assert state["reason"] == "DIRTY_MAIN_CHECKOUT", state
        paths = state["dirty_paths"]
        assert f"projects/demo/receipts/{renamed.name}" in paths, paths
        assert f"projects/demo/receipts/{receipt.name}" in paths, (
            f"rename original path must be intact, got {paths}")
        assert not any(p.startswith("jects/") for p in paths), (
            f"[3:] slice leaked into a rename's original path: {paths}")
    print("[ok] 7. a staged rename reports both paths undamaged")


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} checkout guard tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
