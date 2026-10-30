"""The X post gate: every refusal named, and no path that publishes.

The vendored workflow states its delivery and editorial rules in prose. These
tests are the enforcement: they drive one record through each way it can be
wrong, and prove that the four statuses mean what they say — a draft is a draft,
a post with no card stops at IMAGE_MISSING, a package stops at
AWAITING_MANUAL_PUBLISH, and nothing here can call an API.

Two tests defend absences rather than behaviours: the publish package imports no
network module, and the API publisher raises. An absence that is not tested is a
plan, not a property.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.publish import (  # noqa: E402
    AWAITING,
    SCHEMA,
    PackageBlocked,
    PublishMode,
    PublisherUnavailable,
    build_package,
    post_verdict,
    publish,
    valid_status_url,
    validate_post,
)
from contentops.publish.x_image import UndecodableImage, image_facts  # noqa: E402
from contentops.publish.x_text import (  # noqa: E402
    foreign_scripts,
    parts_lengths,
    x_weighted_length,
)
from process_utils import hidden_run  # noqa: E402

TESTS: List[Any] = []

ACCOUNT_PATH = ROOT / "config" / "accounts" / "x-superplay-english.json"
PACKAGE_DIR = ROOT / "src" / "contentops" / "publish"

#: Host-local warnings are not this gate's to fix; they belong to the account checker.
HOST_LOCAL = ("prompt", "skill_route")


def test(fn):
    TESTS.append(fn)
    return fn


def _codes(issues) -> set:
    return {issue.code for issue in issues}


def _account() -> Dict[str, Any]:
    return json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))


def _png(width: int, height: int) -> bytes:
    """A real PNG, generated with the stdlib, so no fixture binary is committed."""
    row = b"\x00" + b"\x00" * (width * 3)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * height))
            + chunk(b"IEND", b""))


def _jpeg(width: int, height: int) -> bytes:
    """SOI + APP0 + SOF0 + EOI: the smallest file the frame reader can measure."""
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof = (b"\xff\xc0" + struct.pack(">H", 17) + bytes([8])
           + struct.pack(">HH", height, width)
           + bytes([3, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1]))
    return b"\xff\xd8" + app0 + sof + b"\xff\xd9"


def _project(temp: str, image: bool = True) -> Path:
    project = Path(temp) / "x-growth-en"
    (project / "posts").mkdir(parents=True)
    (project / "assets").mkdir()
    (project / "project.yaml").write_text(
        "slug: x-growth-en\naccount_slug: x-superplay-english\nplatform: x\n"
        "language: en\nformat: 1600x900\n", encoding="utf-8")
    if image:
        (project / "assets" / "20261030-001.png").write_bytes(_png(1600, 900))
    return project


def _post(**overrides: Any) -> Dict[str, Any]:
    post: Dict[str, Any] = {
        "schema": SCHEMA,
        "content_id": "20261030-001",
        "account_slug": "x-superplay-english",
        "mode": "workflow_artifact",
        "topic": "verification before completion",
        "sources": ["https://github.com/obra/superpowers"],
        "audience_job": "decide whether an agent's fix claim can be trusted before merging",
        "proof_grade": "P1",
        "unique_artifact_ref": "receipt 2026-10-30 x_post gate run",
        "experiment_variable": "opening hook",
        "label": "WORKFLOW_ARTIFACT",
        "theses": [
            {"thesis": "A fix claim is unverified until a fresh command output and "
                       "exit code exist",
             "evidence": "the upstream skill requires the exact command and its exit status",
             "counterexample": "a passing suite that never reproduced the original "
                               "failure proves nothing about the bug",
             "reader_action": "paste the command and the exit code into the pull "
                              "request before merging"},
            {"thesis": "Agent summaries compress away the failures that make them wrong",
             "evidence": "the same summary dropped stack traces and retries in the trial",
             "counterexample": "a short diff plus a log can be complete when nothing failed",
             "reader_action": "require the raw log next to any prose summary"},
            {"thesis": "Reviewing one fix costs less than re-debugging a false one",
             "evidence": "each false claim reopened the same ticket a second time",
             "counterexample": "a trivial typo correction does not justify a full re-run",
             "reader_action": "budget one verification pass for every merged fix"},
        ],
        "red_team": [
            "This is obvious: reviewers already ask for output.",
            "A screenshot of the run is enough for most teams.",
            "The advice fails when the test suite is flaky, so it is unusable there.",
        ],
        "post_copy": {"parts": [
            'Agent: "Fixed."\nProof?\n\nBefore merging, check:\n'
            "1) exact command\n2) fresh output + exit code\n"
            "3) the original failure now passes\n\nNo run = unverified fix.\n\n"
            "Artifact: https://example.com/receipt",
        ]},
        "image_brief": "dark card, FIXED IS NOT PROOF, two rules",
        "image": {"path": "assets/20261030-001.png"},
        "image_status": "generated",
        "alt_text": "A dark card titled FIXED IS NOT PROOF. Two lines: fresh output, "
                    "exit code.",
        "review": {
            "reviewer": "Xander",
            "reviewed_at": "2026-10-30",
            "dimensions": {"novelty": 4, "evidence": 4, "mechanism": 5,
                           "audience_decision": 4, "falsifiable": 4, "tension": 5},
            "score": 26,
            "opinion": "the third thesis is weaker than the first two; keep it as "
                       "the counterweight",
        },
        "status": "draft",
        "status_url": None,
        "metrics": None,
        "notes": "",
    }
    post.update(overrides)
    return post


def _mutated(**paths: Any) -> Dict[str, Any]:
    """A valid record with dotted paths replaced."""
    post = _post()
    for path, value in paths.items():
        keys = path.split("__")
        target = post
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return post


def _vendored_valid_x_url():
    path = ROOT / "vendor" / "x-growth-os" / "scripts" / "x_growth_report.py"
    spec = importlib.util.spec_from_file_location("x_growth_report_vendored", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.valid_x_url


# ------------------------------------------------------------------ the numbers


@test
def test_the_weighted_count_weighs_urls_and_wide_code_points():
    assert x_weighted_length("hello") == 5
    assert x_weighted_length("https://example.com/a/very/long/path?with=query") == 23
    # A URL is 23 whatever its real length, so an over-long part is refused on what
    # X will actually count, not on the raw string.
    assert x_weighted_length("a https://example.com/x") == 25
    assert x_weighted_length("中文") == 4
    assert parts_lengths(["ab", "cd"]) == [2, 2]
    print("[ok] 1. the weighted count weighs URLs at 23 and wide code points at 2")


@test
def test_a_non_latin_script_is_refused_and_not_silently_counted():
    assert foreign_scripts("plain english") == []
    assert foreign_scripts("中文") == ["U+4E2D", "U+6587"]
    issues = validate_post(_mutated(post_copy__parts=["This account writes in English only"]),
                           _account())
    assert "LANGUAGE_NOT_EN" not in _codes(issues)
    print("[ok] 2. a non-Latin script is detected, and clean English is not refused")


# ------------------------------------------------------------------- the picture


@test
def test_the_image_probe_reads_real_png_and_jpeg_headers():
    with tempfile.TemporaryDirectory() as temp:
        png = Path(temp) / "a.png"
        png.write_bytes(_png(1600, 900))
        facts = image_facts(png)
        assert (facts.format, facts.width, facts.height) == ("png", 1600, 900), facts

        jpeg = Path(temp) / "b.jpeg"
        jpeg.write_bytes(_jpeg(1200, 675))
        facts = image_facts(jpeg)
        assert (facts.format, facts.width, facts.height) == ("jpeg", 1200, 675), facts

        fake = Path(temp) / "c.png"
        fake.write_bytes(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")
        try:
            image_facts(fake)
        except UndecodableImage:
            pass
        else:
            raise AssertionError("a file named .png with SVG content was accepted")
    print("[ok] 3. the probe reads PNG IHDR and JPEG SOF, and refuses a mislabelled file")


@test
def test_an_svg_or_a_wrong_canvas_never_counts_as_the_card():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, image=False)
        (project / "assets" / "card.svg").write_text("<svg/>", encoding="utf-8")
        (project / "assets" / "small.png").write_bytes(_png(800, 600))

        svg = validate_post(_mutated(image={"path": "assets/card.svg"}), account, root=project)
        assert "IMAGE_NOT_RASTER" in _codes(svg), _codes(svg)

        small = validate_post(_mutated(image={"path": "assets/small.png"}), account,
                              root=project)
        assert "IMAGE_WRONG_ASPECT" in _codes(small), _codes(small)
        assert "800x600" in " ".join(issue.detail for issue in small)

        absent = validate_post(_mutated(image=None), account, root=project)
        assert "IMAGE_ABSENT" in _codes(absent), _codes(absent)
    print("[ok] 4. an SVG, a wrong canvas and a missing file are three different refusals")


@test
def test_alt_text_is_required_short_and_free_of_links():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        assert "ALT_MISSING" in _codes(validate_post(_mutated(alt_text=""), account,
                                                     root=project))
        too_long = _mutated(alt_text="One. Two. Three. Four.")
        assert "ALT_TOO_LONG" in _codes(validate_post(too_long, account, root=project))
        linked = _mutated(alt_text="A card linking https://example.com for details.")
        assert "ALT_CONTAINS_URL" in _codes(validate_post(linked, account, root=project))
    print("[ok] 5. ALT is required, at most two sentences, and carries no URL")


# ---------------------------------------------------------------------- editorial


@test
def test_three_theses_must_be_three_judgments_not_one_written_twice():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        two = _post()
        two["theses"] = two["theses"][:2]
        assert "THESES_INSUFFICIENT" in _codes(validate_post(two, account, root=project))

        for field in ("thesis", "evidence", "counterexample", "reader_action"):
            missing = _post()
            missing["theses"][0][field] = ""
            assert "THESES_INSUFFICIENT" in _codes(
                validate_post(missing, account, root=project)), field

        same = _post()
        same["theses"][1]["thesis"] = same["theses"][0]["thesis"]
        issues = validate_post(same, account, root=project)
        assert "THESES_INSUFFICIENT" in _codes(issues)
        assert "written twice" in " ".join(issue.detail for issue in issues)
    print("[ok] 6. two theses, an incomplete thesis and a duplicate are all refused")


@test
def test_the_four_recovery_fields_and_one_experiment_variable():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        for field in ("audience_job", "proof_grade", "unique_artifact_ref",
                      "experiment_variable"):
            issues = validate_post(_mutated(**{field: ""}), account, root=project)
            assert "RECOVERY_FIELD_MISSING" in _codes(issues), field
        two_variables = _mutated(experiment_variable="hook and image")
        issues = validate_post(two_variables, account, root=project)
        assert "RECOVERY_FIELD_MISSING" in _codes(issues)
        assert "one variable" in " ".join(issue.detail for issue in issues)
        bad_grade = _mutated(proof_grade="P9")
        assert "RECOVERY_FIELD_MISSING" in _codes(
            validate_post(bad_grade, account, root=project))
    print("[ok] 7. the four recovery fields are required and the variable stays single")


@test
def test_the_review_is_a_persons_and_is_scored_against_the_account_floor():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        assert "REVIEW_MISSING" in _codes(validate_post(_mutated(review=None), account,
                                                        root=project))

        low = _post()
        low["review"]["dimensions"]["novelty"] = 2
        low["review"]["score"] = 24
        issues = validate_post(low, account, root=project)
        assert "REVIEW_DIMENSION_LOW" in _codes(issues), _codes(issues)

        below = _post()
        below["review"]["dimensions"] = {"novelty": 3, "evidence": 4, "mechanism": 4,
                                         "audience_decision": 4, "falsifiable": 4,
                                         "tension": 4}
        below["review"]["score"] = 23
        issues = validate_post(below, account, root=project)
        assert "REVIEW_SCORE_LOW" in _codes(issues), _codes(issues)

        # A total that does not equal its six parts is a guessed number, not a review.
        inconsistent = _post()
        inconsistent["review"]["score"] = 30
        issues = validate_post(inconsistent, account, root=project)
        assert "REVIEW_SCORE_INCONSISTENT" in _codes(issues), _codes(issues)
    print("[ok] 8. a missing, low, or arithmetically impossible review is refused")


@test
def test_a_source_only_post_may_not_claim_a_run():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        unlabelled = _mutated(proof_grade="P0", label="WORKFLOW_ARTIFACT")
        issues = validate_post(unlabelled, account, root=project)
        assert "RECOVERY_FIELD_MISSING" in _codes(issues), _codes(issues)
        assert "SOURCE_ANALYSIS" in " ".join(issue.detail for issue in issues)

        claimed = _mutated(proof_grade="P0", label="SOURCE_ANALYSIS",
                           post_copy={"parts": [
                               "I tested this on three repos and the gate caught a "
                               "false fix every time, which is the whole claim here."]})
        issues = validate_post(claimed, account, root=project)
        assert "FIRSTHAND_CLAIM_UNSUPPORTED" in _codes(issues), _codes(issues)
    print("[ok] 9. P0 must say SOURCE_ANALYSIS and may not describe a run")


@test
def test_the_red_team_answers_are_the_third_of_the_gate():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        short = _mutated(red_team=["only one objection"])
        issues = validate_post(short, account, root=project)
        assert "THESES_INSUFFICIENT" in _codes(issues)
        assert "red-team" in " ".join(issue.detail for issue in issues)
    print("[ok] 10. the red-team answers are counted, not assumed")


# ------------------------------------------------------------------------- copy


@test
def test_copy_is_bounded_by_the_accounts_own_budget():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        assert "COPY_EMPTY" in _codes(validate_post(_mutated(post_copy={"parts": []}),
                                                    account, root=project))
        long_part = "x" * 281
        issues = validate_post(_mutated(post_copy={"parts": [long_part]}), account,
                               root=project)
        assert "COPY_TOO_LONG" in _codes(issues), _codes(issues)

        parts = {"parts": ["first part is fine", "second too", "third", "fourth"]}
        issues = validate_post(_mutated(post_copy=parts), account, root=project)
        assert "TOO_MANY_PARTS" in _codes(issues), _codes(issues)

        # Exactly at the budget is allowed; the composer is the final authority.
        at_limit = _mutated(post_copy={"parts": ["y" * 280]})
        assert "COPY_TOO_LONG" not in _codes(validate_post(at_limit, account, root=project))
    print("[ok] 11. copy is refused empty, over-budget and past the thread limit")


# ----------------------------------------------------------------------- status


@test
def test_a_post_is_published_only_when_a_real_status_url_exists():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        liar = _mutated(status="published")
        issues = validate_post(liar, account, root=project)
        assert "PUBLISHED_WITHOUT_URL" in _codes(issues), _codes(issues)
        assert post_verdict(liar, account, root=project) == "BLOCKED"

        bad = _mutated(status="published", status_url="https://x.com/someone/status/")
        assert "PUBLISHED_URL_INVALID" in _codes(validate_post(bad, account, root=project))

        unknown = _mutated(status="publishd")
        assert "STATUS_INVALID" in _codes(validate_post(unknown, account, root=project))
    print("[ok] 12. published without a real link is a refusal, not a correction")


@test
def test_a_status_url_agrees_with_the_vendored_validator():
    vendored = _vendored_valid_x_url()
    fixtures = [
        "https://x.com/handle/status/123",
        "https://twitter.com/handle/status/123",
        "https://www.x.com/handle/status/123",
        "https://x.com/handle/status/123/photo/1",
        "https://x.com/handle/status/123?s=20",
        "https://x.com/handle/status/12a3",
        "http://x.com/handle/status/123",
        "https://example.com/handle/status/123",
        "https://x.com/handle",
        "https://x.com/handle/status/",
        "",
    ]
    disagreements = [(url, vendored(url), valid_status_url(url))
                     for url in fixtures if vendored(url) != valid_status_url(url)]
    assert not disagreements, disagreements
    assert valid_status_url("https://x.com/handle/status/123", handle="handle")
    assert not valid_status_url("https://x.com/handle/status/123", handle="other")
    print("[ok] 13. the gate's URL rule and the vendored one agree on every fixture")


@test
def test_a_handle_mismatch_is_refused_once_the_account_knows_its_handle():
    account = json.loads(ACCOUNT_PATH.read_text(encoding="utf-8"))
    confirmed = json.loads(json.dumps(account))
    confirmed["publication"]["handle"] = "superplay_en"
    confirmed["publication"]["handle_status"] = "CONFIRMED"
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        wrong = _mutated(status="published",
                         status_url="https://x.com/somebody/status/123")
        issues = validate_post(wrong, confirmed, root=project)
        assert "HANDLE_MISMATCH" in _codes(issues), _codes(issues)
        right = _mutated(status="published",
                         status_url="https://x.com/superplay_en/status/123")
        assert "HANDLE_MISMATCH" not in _codes(
            validate_post(right, confirmed, root=project))
    print("[ok] 14. a link posted by somebody else is not this account's evidence")


@test
def test_an_unobserved_metric_is_null_and_never_a_blank():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        observed_zero = _mutated(metrics={"impressions": 0, "likes": None})
        assert "METRIC_NOT_OBSERVED" not in _codes(
            validate_post(observed_zero, account, root=project))

        blank = _mutated(metrics={"impressions": ""})
        assert "METRIC_NOT_OBSERVED" in _codes(validate_post(blank, account, root=project))
        text = _mutated(metrics={"impressions": "0"})
        assert "METRIC_NOT_OBSERVED" in _codes(validate_post(text, account, root=project))
    print("[ok] 15. 0 is an observed zero; a blank or a string is not a measurement")


# ---------------------------------------------------------------------- verdicts


@test
def test_the_four_verdicts_are_derived_from_the_same_issues():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        draft = _mutated(review=None, image=None)
        assert post_verdict(draft, account, root=project) == "DRAFT"

        no_image = _mutated(image=None)
        assert post_verdict(no_image, account, root=project) == "IMAGE_MISSING"

        ready = _post()
        assert post_verdict(ready, account, root=project) == "READY", _codes(
            validate_post(ready, account, root=project))

        published = _mutated(status="published",
                             status_url="https://x.com/superplay_en/status/123")
        assert post_verdict(published, account, root=project) == "PUBLISHED"
    print("[ok] 16. DRAFT, IMAGE_MISSING, READY and PUBLISHED each mean one thing")


@test
def test_a_text_only_draft_stops_at_the_image_and_not_before():
    """The dry run the plan promises: good copy, no card, one named refusal."""
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, image=False)
        post = _post()
        issues = validate_post(post, account, root=project)
        assert _codes(issues) == {"IMAGE_ABSENT"}, _codes(issues)
        assert post_verdict(post, account, root=project) == "IMAGE_MISSING"
    print("[ok] 17. a reviewed post with no card is refused by exactly one code")


# --------------------------------------------------------------------- packaging


@test
def test_the_package_stops_at_awaiting_and_carries_the_real_digest():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        post = _post()
        package = build_package(post, account, project)
        assert package["status"] == AWAITING, package["status"]
        assert package["publication_mode"] == "MANUAL_ONLY"
        assert package["image"]["width"] == 1600
        assert len(package["image"]["sha256"]) == 64
        assert package["copy"]["budget"] == 280
        assert package["copy"]["parts"][0]["weighted_length"] > 0
        assert package["alt_text"].startswith("A dark card")
        assert any("x.com/compose/post" in step for step in package["manual_steps"])
        receipt = project / package["receipt"]
        assert receipt.is_file(), package["receipt"]
        stored = json.loads(receipt.read_text(encoding="utf-8"))
        assert stored["status"] == AWAITING
        assert "PUBLISHED" not in json.dumps(stored["status"])
    print("[ok] 18. the package is AWAITING_MANUAL_PUBLISH, with the image digest")


@test
def test_packaging_an_unready_post_is_refused_rather_than_packaged():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp, image=False)
        try:
            build_package(_post(), account, project)
        except PackageBlocked as blocked:
            assert "IMAGE_MISSING" in str(blocked), str(blocked)
        else:
            raise AssertionError("an image-less post produced a package")
    print("[ok] 19. a package cannot be built from a post the gate refused")


@test
def test_the_api_mode_raises_and_the_package_imports_no_network_module():
    account = _account()
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        try:
            publish(_post(), account, project, mode=PublishMode.API)
        except PublisherUnavailable as unavailable:
            assert "capability spike" in str(unavailable), str(unavailable)
        else:
            raise AssertionError("the API publisher did not refuse")

    banned = {"socket", "ssl", "http", "urllib", "requests", "ftplib", "smtplib"}
    found = []
    for source in sorted(PACKAGE_DIR.glob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name in banned:
                    found.append((source.name, name))
    assert not found, found
    print("[ok] 20. API publication raises, and the package imports no network module")


# --------------------------------------------------------------------- the CLI


def _run(args: List[str]):
    return hidden_run([sys.executable, str(ROOT / "scripts" / "x_post.py")] + args,
                      cwd=str(ROOT), timeout=180)


@test
def test_the_cli_walks_a_record_from_draft_to_a_recorded_url():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        project_arg = str(project)

        created = _run([project_arg, "--new", "--id", "20261030-002",
                        "--topic", "verification before completion", "--json"])
        assert created.returncode == 0, (created.stdout or "") + (created.stderr or "")
        record = json.loads(created.stdout)
        assert record["verdict"] != "READY"
        draft_path = project / "posts" / "20261030-002.json"
        assert draft_path.is_file()
        assert (project / "templates" / "posts.csv").is_file()

        checked = _run([project_arg, "--check", "--id", "20261030-002"])
        assert checked.returncode == 1, checked.stdout
        assert "COPY_EMPTY" in (checked.stdout + checked.stderr)

        # The text-only draft is refused at the image, by name.
        (project / "posts" / "20261030-001.json").write_text(
            json.dumps(_post(), indent=2), encoding="utf-8")
        (project / "assets" / "20261030-001.png").unlink()
        missing = _run([project_arg, "--check", "--id", "20261030-001", "--json"])
        assert missing.returncode == 1, missing.stdout
        payload = json.loads(missing.stdout)
        assert payload["verdict"] == "IMAGE_MISSING", payload
        assert {item["code"] for item in payload["issues"]} == {"IMAGE_ABSENT"}

        blocked = _run([project_arg, "--package", "--id", "20261030-001"])
        assert blocked.returncode == 1, blocked.stdout

        # With the card in place the same record packages, then records a URL.
        (project / "assets" / "20261030-001.png").write_bytes(_png(1600, 900))
        ready = _run([project_arg, "--check", "--id", "20261030-001"])
        assert ready.returncode == 0, (ready.stdout or "") + (ready.stderr or "")
        assert "READY" in ready.stdout

        packaged = _run([project_arg, "--package", "--id", "20261030-001", "--json"])
        assert packaged.returncode == 0, (packaged.stdout or "") + (packaged.stderr or "")
        package = json.loads(packaged.stdout)["package"]
        assert package["status"] == AWAITING
        assert (project / "receipts" / "x-package-20261030-001.json").is_file()

        fake = _run([project_arg, "--mark-published", "--id", "20261030-001",
                     "--url", "https://example.com/nope/status/1"])
        assert fake.returncode == 1, fake.stdout

        marked = _run([project_arg, "--mark-published", "--id", "20261030-001",
                       "--url", "https://x.com/superplay_en/status/1799",
                       "--reviewer", "Xander", "--json"])
        assert marked.returncode == 0, (marked.stdout or "") + (marked.stderr or "")
        assert (project / "receipts" / "x-publish-20261030-001.json").is_file()

        final = _run([project_arg, "--check", "--id", "20261030-001", "--json"])
        assert final.returncode == 0, (final.stdout or "") + (final.stderr or "")
        assert json.loads(final.stdout)["verdict"] == "PUBLISHED"

        log = _run([project_arg, "--verify-log", "--json"])
        assert log.returncode == 0, (log.stdout or "") + (log.stderr or "")
        assert json.loads(log.stdout)["drift"] == []
    print("[ok] 21. the CLI carries a record from draft through IMAGE_MISSING to a URL")


@test
def test_the_cli_refuses_to_record_a_publication_the_log_would_disagree_with():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        (project / "posts" / "20261030-001.json").write_text(
            json.dumps(_post(), indent=2), encoding="utf-8")
        marked = _run([str(project), "--mark-published", "--id", "20261030-001",
                       "--url", "https://x.com/superplay_en/status/1799"])
        assert marked.returncode == 0, (marked.stdout or "") + (marked.stderr or "")

        csv_path = project / "templates" / "posts.csv"
        csv_path.write_text(csv_path.read_text(encoding="utf-8").replace(
            "1799", "1800"), encoding="utf-8")
        log = _run([str(project), "--verify-log"])
        assert log.returncode == 1, log.stdout
        assert "CSV_URL_DRIFT" in (log.stdout + log.stderr)
    print("[ok] 22. a drifted CSV row is reported, not silently reconciled")


@test
def test_the_cli_refuses_a_film_account_and_a_missing_one():
    with tempfile.TemporaryDirectory() as temp:
        video = Path(temp) / "video"
        video.mkdir()
        (video / "project.yaml").write_text(
            "slug: v\naccount_slug: x-superplay-1024\n", encoding="utf-8")
        refused = _run([str(video), "--check", "--id", "x"])
        assert refused.returncode == 1, refused.stdout
        assert "ACCOUNT_NOT_X" in (refused.stdout + refused.stderr)

        nameless = Path(temp) / "nameless"
        nameless.mkdir()
        (nameless / "project.yaml").write_text("slug: n\n", encoding="utf-8")
        refused = _run([str(nameless), "--check", "--id", "x"])
        assert refused.returncode == 1, refused.stdout
        assert "ACCOUNT_SLUG_MISSING" in (refused.stdout + refused.stderr)
    print("[ok] 23. the X gate refuses a film account and a project with no account")


@test
def test_the_shipped_account_is_the_only_one_this_gate_accepts():
    account = _account()
    assert account["schema"] == "contentops.x-account/v1"
    assert account["publication"]["mode"] == "MANUAL_ONLY"
    assert account["publication"]["api"] == "not_implemented"
    assert account["visual"]["target"] == "1600x900"
    assert account["editorial"]["max_chars_per_post"] == 280
    with tempfile.TemporaryDirectory() as temp:
        project = _project(temp)
        assert post_verdict(_post(), account, root=project) == "READY"
    print("[ok] 24. the shipped English account accepts a valid record")


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
    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} X post gate tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
