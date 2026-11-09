"""Platform status reconciliation tests.

Strategy's ``Active`` and this repository's ``PLANNED`` are allowed to
disagree — that is the whole point of the split. What is not allowed is for
the disagreement to be invisible, or for the mirror of Strategy's matrix to
silently rot. These tests pin both.

Run: python tests/test_platform_status_sync.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import check_platform_status_sync as sync  # noqa: E402

parse_matrix = sync.parse_matrix
reconcile = sync.reconcile
SyncError = sync.SyncError

FIXTURE_MATRIX = ROOT / "tests" / "fixtures" / "strategy_platform_matrix_sample.md"


def test_fixture_matrix_parses_to_the_full_vocabulary():
    statuses = parse_matrix(FIXTURE_MATRIX.read_text(encoding="utf-8"))
    assert statuses == {
        "douyin": "Active",
        "xiaohongshu": "Active",
        "bilibili": "Active",
        "shipinhao": "Derived",
        "gzh": "Derived",
        "zhihu": "Derived",
        "csdn": "Derived",
        "youtube": "Experiment",
        "x": "Experiment",
        "github": "Infrastructure",
    }


def test_matrix_rows_outside_the_main_table_are_ignored():
    text = (
        "# matrix\n"
        "| 平台 | 系统角色 | 原生内容入口 | 主要观察信号 | 典型 CTA | 状态 | 执行事实源 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 抖音 | Discovery | demo | 停留 | 提交问题 | Active | repo |\n"
        "```yaml\nopening: result_or_conflict\n```\n"
    )
    assert parse_matrix(text) == {"douyin": "Active"}


def test_unknown_matrix_platform_fails_loudly():
    text = (
        "| 平台 | 系统角色 | 原生内容入口 | 主要观察信号 | 典型 CTA | 状态 | 执行事实源 |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 新平台 | Any | any | any | any | Active | repo |\n"
    )
    try:
        parse_matrix(text)
    except SyncError as exc:
        assert exc.code == "MATRIX_UNKNOWN_PLATFORM", exc.code
    else:
        raise AssertionError("an unmapped platform row was silently dropped")


def _write_strategy_root(tmp: Path, matrix_text: str) -> Path:
    root = Path(tmp) / "X-SuperPlay-Strategy"
    (root / "03-Execution").mkdir(parents=True)
    (root / "03-Execution" / "Platform-Operating-Matrix.md").write_text(
        matrix_text, encoding="utf-8")
    return root


def test_shipped_mirror_matches_the_strategy_fixture():
    with tempfile.TemporaryDirectory() as tmp:
        strategy_root = _write_strategy_root(
            tmp, FIXTURE_MATRIX.read_text(encoding="utf-8"))
        report = reconcile(strategy_root, ROOT)
    assert report["mirror_matches_strategy"] is True, report["mirror_drift"]
    assert report["mirror_drift"] == []


def test_mirror_drift_is_detected_and_strict_fails(tmp_root: Path) -> None:
    drifted = FIXTURE_MATRIX.read_text(encoding="utf-8").replace(
        "| B站 | Trust / Deep Proof | 完整实验、教程、失败复盘、Coding | 点击、留存、回访、收藏、技术提问 | GitHub/复现/问题 | Active |",
        "| B站 | Trust / Deep Proof | 完整实验、教程、失败复盘、Coding | 点击、留存、回访、收藏、技术提问 | GitHub/复现/问题 | Derived |")
    assert "| B站" in drifted, "drift edit did not apply to the fixture"
    strategy_root = _write_strategy_root(tmp_root, drifted)
    report = reconcile(strategy_root, ROOT)
    assert report["mirror_matches_strategy"] is False
    assert any(row["platform"] == "bilibili" and row["strategy"] == "Derived"
               for row in report["mirror_drift"])
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_platform_status_sync.py"),
         "--strategy-root", str(strategy_root), "--strict", "--json"],
        capture_output=True, text=True)
    assert done.returncode == 1, done.stderr
    assert json.loads(done.stdout)["mirror_matches_strategy"] is False


def test_strategy_active_vs_runtime_gap_is_reported_not_resolved():
    report = reconcile(None, ROOT)
    gaps = {row["platform"]: row for row in report["strategy_vs_runtime"]}
    assert "douyin" in gaps, gaps
    assert gaps["douyin"]["strategy_status"] == "Active"
    assert gaps["douyin"]["runtime_status"] in ("PLANNED", "INTEGRATED", "TESTED")
    assert "runtime not accepted" in gaps["douyin"]["reading"]
    assert gaps["bilibili"]["runtime_status"] == "PLANNED"
    assert gaps["xiaohongshu"]["runtime_status"] == "PLANNED"


def test_runtime_product_names_reconcile_through_aliases():
    report = reconcile(None, ROOT)
    mirrored = {row["platform"] for row in report["strategy_vs_runtime"]}
    mirrored.update({"shipinhao", "gzh"})  # aliases resolve; see RUNTIME_ALIASES
    # no raw product-level name survives reconciliation
    assert "wechat_channels" not in mirrored
    assert "wechat_official_account" not in mirrored
    # and coverage is complete only because the aliases resolved
    assert report["mirror_coverage_gaps"] == []


def test_shipped_mirror_covers_every_runtime_strategy_platform():
    report = reconcile(None, ROOT)
    assert report["mirror_coverage_gaps"] == [], report["mirror_coverage_gaps"]


def test_cli_passes_on_consistent_mirror() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        strategy_root = _write_strategy_root(
            tmp, FIXTURE_MATRIX.read_text(encoding="utf-8"))
        done = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_platform_status_sync.py"),
             "--strategy-root", str(strategy_root)],
            capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert "mirror matches Strategy: True" in done.stdout


def main() -> int:
    tests = (
        test_fixture_matrix_parses_to_the_full_vocabulary,
        test_matrix_rows_outside_the_main_table_are_ignored,
        test_unknown_matrix_platform_fails_loudly,
        test_shipped_mirror_matches_the_strategy_fixture,
        test_strategy_active_vs_runtime_gap_is_reported_not_resolved,
        test_runtime_product_names_reconcile_through_aliases,
        test_shipped_mirror_covers_every_runtime_strategy_platform,
        test_cli_passes_on_consistent_mirror,
    )
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            test_mirror_drift_is_detected_and_strict_fails(Path(tmp))
        print("[ok] test_mirror_drift_is_detected_and_strict_fails")
    except AssertionError as exc:
        failures.append(("test_mirror_drift_is_detected_and_strict_fails", str(exc)))
        print(f"[FAIL] test_mirror_drift_is_detected_and_strict_fails: {exc}")
    except Exception as exc:  # noqa: BLE001
        failures.append(("test_mirror_drift_is_detected_and_strict_fails", repr(exc)))
        print(f"[ERR ] test_mirror_drift_is_detected_and_strict_fails: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll platform status sync tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
