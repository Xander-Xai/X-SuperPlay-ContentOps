"""Basic tests for scripts. Uses stdlib only (no pytest required).

Each test calls the script as a subprocess and checks exit code + key output.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run(args: list[str], cwd: Path = ROOT, env_extra: dict = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=300,
        env={**__import__("os").environ, **(env_extra or {})},
    )


def test_doctor_runs():
    p = run(["scripts/doctor.py"])
    assert p.returncode in (0, 1), p.stderr
    print("[ok] doctor.py executes")


def test_doctor_json():
    p = run(["scripts/doctor.py", "--json"])
    assert p.returncode in (0, 1)
    try:
        data = json.loads(p.stdout)
    except Exception as e:
        raise AssertionError(f"doctor --json output not valid JSON: {e}\n{p.stdout}")
    assert "checks" in data and isinstance(data["checks"], list)
    print("[ok] doctor.py --json parses")


def test_new_project_creates_and_refuses_overwrite():
    slug = "tmp-test-slug"
    cmd1 = ["scripts/new_project.py", "--slug", slug, "--title", "Tmp Test"]
    p1 = run(cmd1)  # uses ROOT as cwd
    assert p1.returncode == 0, f"first call failed: {p1.stderr}\n{p1.stdout}"
    project_dir = ROOT / "projects" / slug
    assert project_dir.exists(), "project dir not created"
    yaml = project_dir / "project.yaml"
    assert yaml.exists(), "project.yaml not written"
    text = yaml.read_text(encoding="utf-8")
    assert f"id: {slug}" in text

    # second call must refuse
    p2 = run(cmd1)
    assert p2.returncode != 0, "second call should have refused"
    assert "already exists" in p2.stderr

    import shutil
    shutil.rmtree(project_dir, ignore_errors=True)
    print("[ok] new_project.py idempotent + creates structure")


def test_qc_on_missing_final_returns_fail():
    slug = "tmp-qc-no-final"
    import shutil
    proj = ROOT / "projects" / slug
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "project.yaml").write_text(
        "id: tmp-qc-no-final\ntitle: 'x'\nsource_refs: []\n",
        encoding="utf-8",
    )
    try:
        p = run(["scripts/qc_video.py", str(proj)])
        # non-zero exit AND FAIL in output confirms blocked correctly
        assert p.returncode == 1, f"qc should FAIL when final.mp4 missing, got rc={p.returncode}\n{p.stdout}"
        assert "FAIL" in p.stdout, "FAIL should appear in output"
        print("[ok] qc_video.py reports FAIL when final.mp4 missing")
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def _scripts_imports():
    sys.path.insert(0, str(ROOT / "scripts"))
    import resolve_easel, verify_easel_runtime  # noqa: F401
    return resolve_easel, verify_easel_runtime


def _fake_easel_tree(base: Path) -> Path:
    easel = base / ".runtime" / "easel"
    (easel / "skills" / "openclaw" / "auto-short-video" / "scripts").mkdir(parents=True)
    (easel / "skills" / "shared" / "scripts").mkdir(parents=True)
    (easel / "pyproject.toml").write_text('[project]\nversion = "0.2.1"\n', encoding="utf-8")
    (easel / "skills" / "openclaw" / "auto-short-video" / "scripts" / "assemble.py").write_text("# stub\n", encoding="utf-8")
    (easel / "skills" / "shared" / "scripts" / "tts.py").write_text("# stub\n", encoding="utf-8")
    return easel


def test_verify_blob_sha1_matches_git():
    rez, ver = _scripts_imports()
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "empty.bin"
        f.write_bytes(b"")
        # git's well-known empty-blob id
        assert ver.blob_sha1(f) == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
        f.write_bytes(b"hello\n")
        assert ver.blob_sha1(f) == "ce013625030ba8dba906f756967f9e9ca394464a"
    print("[ok] verify_easel_runtime.blob_sha1 matches git object ids")


def test_verify_generated_exclusion():
    rez, ver = _scripts_imports()
    assert ver._is_generated("outputs/foo/final.mp4")
    assert ver._is_generated(".git/config")
    assert not ver._is_generated("easel/__init__.py")
    assert not ver._is_generated("pyproject.toml")
    print("[ok] generated-path exclusions are symmetric")


def test_resolver_rejects_foreign_remote():
    """§3: a .runtime/easel whose origin is not ZJU-REAL/Easel is refused."""
    rez, ver = _scripts_imports()
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        easel = _fake_easel_tree(fake_root)
        run_git = lambda *a: subprocess.run(["git", "-C", str(easel), *a],
                                            capture_output=True, text=True, timeout=30)
        assert run_git("init").returncode == 0
        assert run_git("remote", "add", "origin", "https://example.com/not-easel.git").returncode == 0
        res = rez.resolve_easel(root=fake_root, live=False)
        assert res["status"] == "BLOCKED", res
        assert res.get("rejected_foreign_checkout") is True, res
        assert any("not ZJU-REAL/Easel" in r for r in res["reasons"]), res["reasons"]
    print("[ok] resolver rejects a foreign remote at .runtime/easel")


def test_resolver_accepts_archive_with_recorded_provenance():
    """§2: a .git-less archive is accepted via recorded verification, not .git HEAD."""
    rez, ver = _scripts_imports()
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        _fake_easel_tree(fake_root)
        (fake_root / "runtime").mkdir(parents=True)
        pin = rez.load_pin(ROOT)
        (fake_root / "runtime" / "easel-runtime.json").write_text(json.dumps({
            "repo": "ZJU-REAL/Easel", "release": pin["tag"],
            "expected_commit": pin["commit"], "acquisition": "release_archive",
            "verified": True, "verified_at": "2026-10-02",
        }), encoding="utf-8")
        res = rez.resolve_easel(root=fake_root, live=False)
        assert res["status"] == "OK", res
        assert res["acquisition"] == "release_archive"
        assert res["verification"] == "recorded"
    print("[ok] resolver accepts archive layout via recorded provenance")


def test_resolver_blocks_archive_without_provenance():
    """An unverifiable archive must BLOCK, never silently render."""
    rez, ver = _scripts_imports()
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        _fake_easel_tree(fake_root)
        res = rez.resolve_easel(root=fake_root, live=False)
        assert res["status"] == "BLOCKED", res
    print("[ok] resolver blocks an archive with no verification record")


if __name__ == "__main__":
    failures = []
    for fn in (test_doctor_runs, test_doctor_json,
               test_new_project_creates_and_refuses_overwrite,
               test_qc_on_missing_final_returns_fail,
               test_verify_blob_sha1_matches_git,
               test_verify_generated_exclusion,
               test_resolver_rejects_foreign_remote,
               test_resolver_accepts_archive_with_recorded_provenance,
               test_resolver_blocks_archive_without_provenance):
        try:
            fn()
        except AssertionError as e:
            failures.append((fn.__name__, str(e)))
            print(f"[FAIL] {fn.__name__}: {e}")
        except Exception as e:
            failures.append((fn.__name__, repr(e)))
            print(f"[ERR ] {fn.__name__}: {e!r}")

    if failures:
        print(f"\n{len(failures)} test(s) failed")
        sys.exit(1)
    print("\nAll tests passed.")