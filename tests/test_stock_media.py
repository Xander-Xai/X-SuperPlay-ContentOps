"""Offline contract tests for the Pexels/Pixabay B-roll layer.

CI runs this file directly: ``python tests/test_stock_media.py``. No API key,
no network, no paid call. Every provider response is injected through the
transport so parsing, ranking, 429 handling, cache reuse, URL refusal and the
rights gate are all exercised for real.
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media import stock_media as sm  # noqa: E402

PEXELS_PHOTO = {
    "photos": [{
        "id": 101, "width": 1080, "height": 1920,
        "url": "https://www.pexels.com/photo/101/",
        "photographer": "Ada", "alt": "server rack network cables",
        "src": {"original": "https://images.pexels.com/photos/101/photo.jpeg",
                "portrait": "https://images.pexels.com/photos/101/photo.jpeg?w=400"},
    }],
}
PEXELS_VIDEO = {
    "videos": [{
        "id": 202, "url": "https://www.pexels.com/video/202/",
        "image": "https://images.pexels.com/videos/202/preview.jpg",
        "duration": 12, "user": {"name": "Bo"},
        "video_files": [{"file_type": "video/mp4", "width": 1080, "height": 1920,
                         "link": "https://videos.pexels.com/video-files/202/202-hd.mp4"}],
    }],
}
PIXABAY_PHOTO = {
    "hits": [{
        "id": 303, "pageURL": "https://pixabay.com/images/303/", "user": "Cy",
        "tags": "server,rack,network", "imageWidth": 1080, "imageHeight": 1920,
        "largeImageURL": "https://cdn.pixabay.com/photo/303.jpg",
        "previewURL": "https://cdn.pixabay.com/photo/303-150.jpg",
    }],
}
PIXABAY_VIDEO = {
    "hits": [{
        "id": 404, "pageURL": "https://pixabay.com/videos/404/", "user": "Di",
        "tags": "network,datacenter", "duration": 9,
        "videos": {"large": {"url": "https://cdn.pixabay.com/video/404/large.mp4",
                             "width": 1080, "height": 1920}},
    }],
}

GRANT = sm.StockAuthorization(granted_by="founder", granted_at="2026-11-09",
                             scope="search_only")
DOWNLOAD_GRANT = sm.StockAuthorization(granted_by="founder", granted_at="2026-11-09",
                                      scope="search_and_download", max_downloads=1)


def _payload_for(url: str):
    if "v1/videos/search" in url:
        return PEXELS_VIDEO
    if "v1/search" in url:
        return PEXELS_PHOTO
    if "/api/videos/" in url:
        return PIXABAY_VIDEO
    if "/api/" in url:
        return PIXABAY_PHOTO
    return {}


def _ok_transport(calls=None):
    def transport(request):
        if calls is not None:
            calls.append(request.full_url)
        return 200, {}, json.dumps(_payload_for(request.full_url)).encode("utf-8")
    return transport


def _public_resolver(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class ParseTests(unittest.TestCase):
    def test_all_four_provider_responses_parse(self):
        cases = [("pexels_photos", PEXELS_PHOTO, "image", "Ada", "Pexels-License"),
                 ("pexels_videos", PEXELS_VIDEO, "video", "Bo", "Pexels-License"),
                 ("pixabay_photos", PIXABAY_PHOTO, "image", "Cy", "Pixabay-Content-License"),
                 ("pixabay_videos", PIXABAY_VIDEO, "video", "Di", "Pixabay-Content-License")]
        for provider, payload, kind, author, license_id in cases:
            with self.subTest(provider=provider):
                rows = sm.parse_response(provider, payload)
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row.kind, kind)
                self.assertEqual(row.author, author)
                self.assertEqual(row.license_id, license_id)
                self.assertTrue(row.download_url.startswith("https://"))
                self.assertFalse(row.as_dict()["evidence_capable"])
                self.assertEqual(row.as_dict()["visual_role_allowlist"], ["context", "transition"])

    def test_malformed_payload_is_skipped_not_fatal(self):
        self.assertEqual(sm.parse_response("pexels_photos", {"photos": [None, 3, {}]}), [])
        with self.assertRaises(sm.StockMediaError):
            sm.parse_response("unknown-provider", {})


class RankTests(unittest.TestCase):
    def test_portrait_relevant_candidate_accepted(self):
        query = sm.StockQuery(keyword="server rack", kind="image")
        rows = sm.rank_candidates(sm.parse_response("pexels_photos", PEXELS_PHOTO), query)
        self.assertTrue(rows[0].accepted, rows[0].reasons)
        self.assertGreater(rows[0].score, 0)

    def test_wrong_ratio_duration_and_bad_url_are_rejected_with_reasons(self):
        bad_ratio = {"photos": [{"id": 9, "width": 1920, "height": 1080,
                                 "photographer": "E", "alt": "server rack",
                                 "src": {"original": "https://images.pexels.com/x.jpg"}}]}
        rows = sm.rank_candidates(sm.parse_response("pexels_photos", bad_ratio),
                                  sm.StockQuery(keyword="server rack", kind="image"))
        self.assertFalse(rows[0].accepted)
        self.assertTrue(any("aspect ratio" in r for r in rows[0].reasons))
        too_short = {"hits": [{"id": 8, "pageURL": "https://pixabay.com/videos/8/",
                               "user": "F", "tags": "network", "duration": 120,
                               "videos": {"large": {"url": "https://cdn.pixabay.com/v/8.mp4",
                                                    "width": 1080, "height": 1920}}}]}
        rows = sm.rank_candidates(sm.parse_response("pixabay_videos", too_short),
                                  sm.StockQuery(keyword="network", kind="video"))
        self.assertFalse(rows[0].accepted)
        self.assertTrue(any("duration" in r for r in rows[0].reasons))
        evil = sm.Candidate("pexels_photos", "image", "x", "http://127.0.0.1/a.jpg",
                            "", "", "Pexels-License", 1080, 1920,
                            description="server rack")
        rows = sm.rank_candidates([evil], sm.StockQuery(keyword="server rack"))
        self.assertFalse(rows[0].accepted)


class SearchPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "cache"

    def test_no_explicit_authorization_means_no_network(self):
        calls = []
        result = sm.search(sm.StockQuery(keyword="server rack"), authorization=None,
                           cache_root=self.cache, transport=_ok_transport(calls),
                           env={"PEXELS_API_KEY": "k"})
        self.assertEqual(result.state, sm.STATE_NOT_AUTHORIZED)
        self.assertEqual(calls, [])
        self.assertEqual(result.requests, 0)

    def test_missing_key_is_a_normal_state_and_main_flow_can_continue_locally(self):
        calls = []
        result = sm.search(sm.StockQuery(keyword="server rack"), authorization=GRANT,
                           cache_root=self.cache, transport=_ok_transport(calls), env={})
        self.assertEqual(result.state, sm.STATE_NO_CREDENTIALS)
        self.assertEqual(calls, [])
        self.assertIn("PEXELS_API_KEY", result.errors[0]["missing_env"])

    def test_429_reports_retry_after_without_resubmitting(self):
        calls = []
        def limited(request):
            calls.append(request.full_url)
            return 429, {"Retry-After": "120"}, b""
        result = sm.search(sm.StockQuery(keyword="server rack"), authorization=GRANT,
                           cache_root=self.cache, transport=limited,
                           env={"PEXELS_API_KEY": "k"})
        self.assertEqual(result.state, sm.STATE_RATE_LIMITED)
        self.assertEqual(result.retry_after_s, 120)
        self.assertEqual(len(calls), 1)
        self.assertIn("no automatic re-submit", result.errors[0]["reason"])

    def test_search_response_is_cached_for_at_least_24h_and_then_expires(self):
        clock = {"now": datetime(2026, 11, 9, tzinfo=timezone.utc)}
        now = lambda: clock["now"]
        calls = []
        args = dict(authorization=GRANT, cache_root=self.cache,
                    transport=_ok_transport(calls), env={"PEXELS_API_KEY": "k"}, clock=now)
        first = sm.search(sm.StockQuery(keyword="server rack"), **args)
        self.assertEqual(first.state, sm.STATE_READY)
        self.assertEqual(first.requests, 1)
        clock["now"] = clock["now"] + timedelta(hours=23, minutes=59)
        second = sm.search(sm.StockQuery(keyword="server rack"), **args)
        self.assertEqual(second.cache_hits, 1)
        self.assertEqual(second.requests, 0)
        self.assertEqual(len(calls), 1)
        clock["now"] = clock["now"] + timedelta(hours=1)
        third = sm.search(sm.StockQuery(keyword="server rack"), **args)
        self.assertEqual(third.cache_hits, 0)
        self.assertEqual(third.requests, 1)
        self.assertEqual(len(calls), 2)

    def test_bad_provider_response_is_not_cached_as_success(self):
        def broken(_request):
            return 200, {}, b"<html>not json</html>"
        result = sm.search(sm.StockQuery(keyword="server rack"), authorization=GRANT,
                           cache_root=self.cache, transport=broken,
                           env={"PEXELS_API_KEY": "k"})
        self.assertEqual(result.state, sm.STATE_PROVIDER_ERROR)
        self.assertIn("unparseable", result.errors[0]["reason"])
        self.assertEqual(list(self.cache.glob("*.json")), [],
                         "a failed response must never be cached as a success")

    def test_preview_rows_keep_accept_and_reject_reasons(self):
        result = sm.search(sm.StockQuery(keyword="server rack"), authorization=GRANT,
                           cache_root=self.cache, transport=_ok_transport(),
                           env={"PEXELS_API_KEY": "k"})
        rows = sm.preview_candidates(result)
        self.assertTrue(rows)
        self.assertTrue(all("reasons" in row for row in rows))


class DownloadAndRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name) / "repo" / "projects" / "p1"
        self.project.mkdir(parents=True)
        self.candidate = sm.parse_response("pexels_photos", PEXELS_PHOTO)[0]
        self.candidate.accepted = True

    def test_download_requires_a_separate_download_grant(self):
        row = sm.download(self.candidate, authorization=GRANT, project_dir=self.project,
                          transport=_ok_transport(), resolver=_public_resolver)
        self.assertEqual(row["state"], "BLOCKED")

    def test_private_dns_answer_and_non_https_are_refused(self):
        def private(*_a, **_k):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]
        row = sm.download(self.candidate, authorization=DOWNLOAD_GRANT,
                          project_dir=self.project, transport=_ok_transport(),
                          resolver=private)
        self.assertEqual(row["state"], "INVALID_ASSET")
        self.assertIn("non-public", row["reason"])

    def test_wrong_magic_bytes_and_oversize_are_refused(self):
        def wrong_bytes(_request):
            return 200, {}, b"MZ\x90\x00not-an-image"
        row = sm.download(self.candidate, authorization=DOWNLOAD_GRANT,
                          project_dir=self.project, transport=wrong_bytes,
                          resolver=_public_resolver)
        self.assertEqual(row["state"], "INVALID_ASSET")
        def oversized(_request):
            return 200, {"Content-Length": str(sm.MAX_DOWNLOAD_BYTES + 1)}, b"\xff\xd8\xff"
        row = sm.download(self.candidate, authorization=DOWNLOAD_GRANT,
                          project_dir=self.project, transport=oversized,
                          resolver=_public_resolver)
        self.assertEqual(row["state"], "INVALID_ASSET")

    def test_register_never_fabricates_a_human_rights_review(self):
        jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64
        def serve(_request):
            return 200, {}, jpeg
        row = sm.download(self.candidate, authorization=DOWNLOAD_GRANT,
                          project_dir=self.project, transport=serve,
                          resolver=_public_resolver)
        self.assertIn(row["state"], ("DOWNLOADED", "REUSED"))
        result = sm.register(row, project_dir=self.project, downloaded_at="2026-11-09")
        self.assertEqual(result["state"], "RIGHTS_REVIEW_REQUIRED")
        self.assertEqual(result["human_rights_review"], "PENDING")
        self.assertFalse(result["distribution_authorized"])
        self.assertFalse(result["evidence_capable"])
        review = json.loads((self.project / result["rights_review"]).read_text(encoding="utf-8"))
        self.assertEqual(review["reviewed_by"], "")
        self.assertEqual(review["state"], "PENDING_HUMAN_REVIEW")
        manifest = json.loads((self.project / "sources" / "assets.json").read_text(encoding="utf-8"))
        asset = manifest["assets"][0]
        self.assertFalse(asset["evidence_capable"])
        self.assertFalse(asset["distribution_authorized"])
        self.assertEqual(asset["usage_scope"], "LOCAL_PREVIEW_ONLY")
        provenance = json.loads((self.project / asset["source_provenance"]).read_text(encoding="utf-8"))
        self.assertEqual(provenance["sha256"], row["sha256"])
        self.assertEqual(provenance["downloaded_at"], "2026-11-09")

    def test_reuse_avoids_a_second_download(self):
        jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 64
        row = sm.download(self.candidate, authorization=DOWNLOAD_GRANT,
                          project_dir=self.project,
                          transport=lambda _r: (200, {}, jpeg),
                          resolver=_public_resolver)
        sm.register(row, project_dir=self.project, downloaded_at="2026-11-09")
        reused = sm.find_reusable(row, self.project)
        self.assertIsNotNone(reused)
        self.assertEqual(reused["state"], "REUSED")
        self.assertEqual(reused["sha256"], row["sha256"])

    def test_registration_refuses_when_bytes_were_tampered_with(self):
        result = sm.register({"state": "DOWNLOADED", "sha256": "0" * 64,
                              "path": "missing.jpg", "kind": "image"},
                             project_dir=self.project)
        self.assertEqual(result["state"], "REGISTRATION_REFUSED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
