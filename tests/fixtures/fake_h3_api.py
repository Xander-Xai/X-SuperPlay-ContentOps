#!/usr/bin/env python3
"""In-process stand-in for the documented MiniMax H3 public API.

Lets the whole video pipeline — validation, fingerprint, cache, billing gate, the
one-task rule, polling, download, QC, receipt, registration — be exercised with **no
network and no quota**.

It models the parts that matter and refuses to hide the parts that do:

- ``create_count`` increments on create only, so a test can prove that a poll
  timeout, a temporary 5xx, a process restart or a download failure never causes a
  second billable task.
- ``polled_task_ids`` records every id asked about, so "poll the SAME task" is
  checkable rather than assumed.
- ``downloaded_task_refs`` records every URL fetched, so "download the SAME result"
  is checkable.
- ``poll_error_plan`` makes a given poll raise, and ``download_error_plan`` makes a
  given download fail, so recovery paths are reachable without a real outage.

Deliberate modes
----------------
``poll_error_plan``   dict of poll-index -> "timeout" | "http_500" | "malformed"
``download_error_plan``  dict of download-index -> failure count for that attempt
``fail_after_polls``  succeed on the Nth poll instead of the first
``final_state``       "succeeded" | "failed" | "cancelled" | "bogus_state"
``omit_download_url`` succeed while returning no content.url
``fail_create``       refuse the create call

Environment
-----------
``FAKE_H3_STATE``  path to a JSON file used to resume task state across processes,
                   mirroring the provider's private task-state file.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# The fake raises the REAL transport error types. If it defined its own, the
# provider's ``except UnknownTaskState`` would not catch it and the fail-closed
# path would go untested.
from contentops.media.h3_transport import (  # noqa: E402
    TransportError as FakeH3TransportError,
    UnknownTaskState as FakeH3UnknownState,
)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))


class FakeH3Transport:
    """A controllable, in-memory H3 transport.

    Implements the same three-method shape as the real transport, so the provider
    cannot tell the difference, and so a test can inject failures precisely.
    """

    def __init__(
        self,
        *,
        fail_after_polls: int = 0,
        final_state: str = "succeeded",
        omit_download_url: bool = False,
        fail_create: bool = False,
        poll_error_plan: Optional[Dict[int, str]] = None,
        download_error_plan: Optional[Dict[int, int]] = None,
        download_bytes: Optional[bytes] = None,
        task_id: str = "424010985738629",
        credential: str = "",
        state_file: Optional[str] = None,
    ) -> None:
        self.fail_after_polls = fail_after_polls
        self.final_state = final_state
        self.omit_download_url = omit_download_url
        self.fail_create = fail_create
        self.poll_error_plan = dict(poll_error_plan or {})
        self.download_error_plan = dict(download_error_plan or {})
        self._download_bytes = download_bytes
        self.task_id = task_id
        self.credential = credential
        self.state_file = state_file

        # Observable counters. These are the evidence for the one-task rule.
        self.create_count = 0
        self.poll_count = 0
        self.download_count = 0
        self.polled_task_ids: List[str] = []
        self.downloaded_task_refs: List[str] = []
        self.created_task_ids: List[str] = []
        self.authorizations: List[str] = []

    # -- the billable call -------------------------------------------------

    def create_task(
        self,
        *,
        model: str,
        content: List[Dict[str, Any]],
        duration_s: int,
        resolution: str,
        ratio: Optional[str],
        extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        if self.fail_create:
            raise FakeH3TransportError("fake: create refused by configuration")
        self.create_count += 1
        self.created_task_ids.append(self.task_id)
        # Record what was asked for, so a test can assert the content[] mapping.
        self.last_request = {
            "model": model,
            "duration": duration_s,
            "resolution": resolution,
            "ratio": ratio,
            "extra": extra,
            "content": content,
        }
        if self.state_file:
            Path(self.state_file).parent.mkdir(parents=True, exist_ok=True)
            Path(self.state_file).write_text(
                json.dumps({"task_id": self.task_id}, indent=2), encoding="utf-8"
            )
        return self.task_id

    # -- free calls --------------------------------------------------------

    def poll_task(self, task_id: str) -> Any:
        self.poll_count += 1
        self.polled_task_ids.append(task_id)
        if self.credential:
            self.authorizations.append(self.credential)

        planned = self.poll_error_plan.get(self.poll_count)
        if planned == "timeout":
            raise FakeH3TransportError("fake: poll timed out")
        if planned == "http_500":
            raise FakeH3TransportError("fake: HTTP 500 while polling")
        if planned == "malformed":
            raise FakeH3TransportError("fake: malformed poll response")

        if self.poll_count <= self.fail_after_polls:
            state = "running"
        else:
            state = self.final_state

        if state == "bogus_state":
            # The real client must refuse a state it does not know rather than
            # treat it as permission to try again.
            raise FakeH3UnknownState(
                "fake: provider reported an unrecognised task state"
            )

        from contentops.media.h3_transport import TaskPollResult

        return TaskPollResult(
            task_id=task_id,
            state=state,
            download_url=(
                None
                if (self.omit_download_url or state != "succeeded")
                else f"https://fake.invalid/{task_id}.mp4"
            ),
            model="MiniMax-H3",
            resolution="768P",
            duration_s=4,
            ratio="9:16",
            task_type="generation",
            modality="video",
            usage={"total_seconds": 4, "input_seconds": 0, "output_seconds": 4,
                   "input_image_count": 0},
            error="fake: model refused" if state == "failed" else None,
        )

    def download_result(self, url: str, destination: Path) -> Path:
        self.download_count += 1
        self.downloaded_task_refs.append(url)
        failures = self.download_error_plan.get(self.download_count, 0)
        if failures > 0:
            self.download_error_plan[self.download_count] = failures - 1
            raise FakeH3TransportError(
                f"fake: download attempt {self.download_count} failed"
            )
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = self._download_bytes
        if payload is None:
            payload = _default_clip_bytes()
        destination.write_bytes(payload)
        return destination


def _default_clip_bytes() -> bytes:
    """Build a small but real MP4 so QC has genuine frames to measure.

    Uses ffmpeg through process_utils, because a fixture may not spawn a process
    directly without flashing a console on Windows.
    """
    from process_utils import hidden_run

    target = Path(os.environ.get("FAKE_H3_CLIP_TARGET", "")) if os.environ.get(
        "FAKE_H3_CLIP_TARGET"
    ) else None
    if target and target.is_file():
        return target.read_bytes()
    return _synthesise_clip()


def _synthesise_clip() -> bytes:
    """Render a 1-frame-differing clip in memory via a temp file."""
    import subprocess
    import tempfile

    from process_utils import hidden_run

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "clip.mp4"
        result = hidden_run(
            [
                "ffmpeg", "-y", "-v", "error", "-nostdin",
                "-f", "lavfi", "-i", "testsrc=size=320x568:rate=24:duration=4",
                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
                str(out),
            ],
            timeout=300,
        )
        if result.returncode != 0 or not out.is_file():
            raise FakeH3TransportError(
                "fake: could not synthesise a clip; ffmpeg is required for the "
                f"video fixture. {(result.stderr or '')[:200]}"
            )
        return out.read_bytes()


def main() -> int:
    """Tiny CLI so the fixture can also be exercised as a script."""
    print(json.dumps({"fixture": "fake_h3_api", "note": "use from tests"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())