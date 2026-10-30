"""The routing catalog must cover every project track, not only Easel.

The failure this guards against: a vendored track (公众号) whose skills exist on
disk but are invisible to ``skill_route.py``, so Skill-First Routing cannot
route to them and the work falls back to hand-rolled steps.

Run: python tests/test_skill_route_catalogs.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_route import CATALOG_ROOTS, catalog, catalog_sources, rank  # noqa: E402

GZH_ROOT = ROOT / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills"


def test_gzh_track_is_declared():
    assert GZH_ROOT in CATALOG_ROOTS, "the 公众号 track is not a catalog root"


def test_sources_report_labels_every_root():
    sources = {item["label"]: item for item in catalog_sources()}
    assert {"easel-pinned", "easel-checkout", "gzh"} <= set(sources), sources
    for item in sources.values():
        if item["exists"]:
            assert item["skills"] > 0, f"{item['label']} exists but has no SKILL.md"


def test_names_are_unique_after_dedup():
    skills, root = catalog()
    if root is None:
        print("no project catalog on this checkout; skipping")
        return
    names = [skill["name"] for skill in skills]
    assert len(names) == len(set(names)), "a skill name was indexed twice"


def test_gzh_skill_is_indexed_when_present():
    if not GZH_ROOT.is_dir():
        print("gzh track absent on this checkout; skipping")
        return
    skills, _ = catalog()
    by_name = {skill["name"]: skill for skill in skills}
    assert "gzh-article-orchestrator" in by_name
    assert by_name["gzh-article-orchestrator"]["source"] == "gzh"


def test_cross_track_collision_is_reported_not_dropped():
    if not GZH_ROOT.is_dir():
        print("gzh track absent on this checkout; skipping")
        return
    skills, _ = catalog()
    by_name = {skill["name"]: skill for skill in skills}
    entry = by_name.get("gzh-design")
    if entry is None or not entry.get("shadowed"):
        print("no cross-track name collision on this checkout; skipping")
        return
    # The losing copy keeps a source and a path, so the shadowing is visible.
    for lost in entry["shadowed"]:
        assert lost["source"] and lost["path"], lost


def test_ranking_routes_a_wechat_request_to_the_gzh_track():
    if not GZH_ROOT.is_dir():
        print("gzh track absent on this checkout; skipping")
        return
    skills, _ = catalog()
    hits = rank(skills, "公众号 文章 排版")
    assert hits, "no skill matched a 公众号 request"
    assert any(hit["source"] == "gzh" for hit in hits[:5]), [
        (hit["name"], hit["source"]) for hit in hits[:5]
    ]


def main() -> int:
    failures = []
    tests = (
        test_gzh_track_is_declared,
        test_sources_report_labels_every_root,
        test_names_are_unique_after_dedup,
        test_gzh_skill_is_indexed_when_present,
        test_cross_track_collision_is_reported_not_dropped,
        test_ranking_routes_a_wechat_request_to_the_gzh_track,
    )
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
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll skill-route catalog tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
