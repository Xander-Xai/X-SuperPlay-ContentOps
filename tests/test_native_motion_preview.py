from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import native_motion_preview as preview  # noqa: E402


class NativeMotionProfilesTests(unittest.TestCase):
    def test_future_intelligence_uses_its_scoped_explanatory_profile(self) -> None:
        profile = preview.profile_for_project(
            "x-superplay-future-intelligence-motion-20261107")
        self.assertEqual(profile["account"], "x-superplay-future-intelligence")
        self.assertEqual(profile["duration_s"], 8.0)
        self.assertEqual(profile["role"], "EXPLANATORY_SUPPORT_NOT_EVIDENCE")
        self.assertEqual(profile["story_beats"], [
            "found_but_not_authorized", "request_grant_gate_runner",
            "blocked_vs_theoretical_authorized_executed",
        ])

    def test_1024_uses_an_auxiliary_profile_without_fabricating_resolver_output(self) -> None:
        profile = preview.profile_for_project("x-superplay-1024-motion-20261107")
        self.assertEqual(profile["account"], "x-superplay-1024")
        self.assertEqual(profile["duration_s"], 6.0)
        self.assertEqual(profile["role"], "AUXILIARY_EXPLANATION_NOT_REAL_CAPTURE")
        self.assertFalse(profile["claims_current_resolver_result"])

    def test_unknown_project_is_refused(self) -> None:
        with self.assertRaises(preview.PreviewError):
            preview.profile_for_project("another-project")


class NativeMotionFrameTests(unittest.TestCase):
    def test_frames_are_portrait_and_deterministic_for_the_same_timestamp(self) -> None:
        project = "x-superplay-future-intelligence-motion-20261107"
        first = preview.render_frame(project, 2.4)
        repeated = preview.render_frame(project, 2.4)
        self.assertEqual(first.size, (1080, 1920))
        self.assertEqual(first.mode, "RGB")
        self.assertEqual(first.tobytes(), repeated.tobytes())

    def test_motion_changes_pixels_across_time_without_changing_canvas(self) -> None:
        project = "x-superplay-future-intelligence-motion-20261107"
        frame_a = preview.render_frame(project, 1.0)
        frame_b = preview.render_frame(project, 5.0)
        self.assertEqual(frame_a.size, frame_b.size)
        self.assertNotEqual(frame_a.tobytes(), frame_b.tobytes())

    def test_1024_frame_is_also_original_explanatory_art_not_a_fake_terminal(self) -> None:
        project = "x-superplay-1024-motion-20261107"
        frame = preview.render_frame(project, 3.0)
        self.assertEqual(frame.size, (1080, 1920))
        self.assertEqual(frame.mode, "RGB")


class NativeMotionRouteTests(unittest.TestCase):
    def test_route_is_real_but_does_not_claim_contentops_grant(self) -> None:
        for project in (
            "x-superplay-future-intelligence-motion-20261107",
            "x-superplay-1024-motion-20261107",
        ):
            route = preview.resolve_project_route(project)
            self.assertEqual(route["verdict"], "RESOLVABLE", route)
            self.assertEqual(route["capability_id"], "contentops-native-motion")
            self.assertFalse(route["execution_authorized"])
            self.assertFalse(route["contentops_grant_present"])
            self.assertTrue(route["user_task_scope_authorized"])
            self.assertTrue(route["runtime_dependencies"])


if __name__ == "__main__":
    unittest.main()
