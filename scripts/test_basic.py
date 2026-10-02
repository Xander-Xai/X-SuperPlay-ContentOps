"""Basic tests for scripts. Uses stdlib only (no pytest required).

Each test calls the script as a subprocess and checks exit code + key output.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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


if __name__ == "__main__":
    failures = []
    for fn in (test_doctor_runs, test_doctor_json, test_new_project_creates_and_refuses_overwrite, test_qc_on_missing_final_returns_fail):
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