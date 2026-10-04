"""Narrow HTTP transport for the documented MiniMax H3 API.

Why a transport abstraction
---------------------------
The provider orchestration must be testable without a network and without quota,
and the HTTP mechanics must not leak into the prompt compiler, the planner or the
QC code. This module is that boundary: three methods, one of which costs money.

The one expensive call
----------------------
::

    create_task()   <- the only call that creates a new paid generation
    poll_task()     <- free; asks about an existing task
    download_result <- free; fetches an existing result

Keeping them as three separate methods is what makes "at most one task per
attempt" expressible. A combined ``generate()`` would hide the expensive step
inside a retry loop, which is exactly how a poll timeout turns into a second bill.

Not used for generation
-----------------------
The official ``mmx`` CLI is **not** the H3 generation transport. It cannot reliably
express the required resolution behaviour, while the documented public API
produced verified 768P output for this account. The CLI remains useful for
``auth``, ``status``, ``quota``, research and diagnostics.

Endpoints used, all documented
------------------------------
``POST /v2/video_generation``
    create; returns ``{"task_id": "..."}``
``GET /v2/query/video_generation/{task_id}``
    poll; returns the task with ``status`` and, on success, ``content.url``

There is no ``file_id`` exchange on this path: the download URL comes back from
the poll itself.

Credential handling
-------------------
The API key arrives as ``Authorization: Bearer <key>`` and is supplied by the
caller from a bound :class:`~contentops.media.credentials.ResolvedCredential`. This
module never resolves, reads from ambient config, logs, or persists it, and never
places it in a URL or query string.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from contentops.media.video_contract import VideoTaskState

__all__ = [
    "CREATE_TASK_PATH",
    "DEFAULT_BASE_URL",
    "H3Transport",
    "HttpH3Transport",
    "POLL_TASK_PATH_TEMPLATE",
    "REFERENCE_MIME_TYPES",
    "TaskPollResult",
    "TransportError",
    "UnknownTaskState",
    "build_content_array",
    "encoded_reference_bytes",
]

DEFAULT_BASE_URL = "https://api.minimax.io"
CREATE_TASK_PATH = "/v2/video_generation"
POLL_TASK_PATH_TEMPLATE = "/v2/query/video_generation/{task_id}"

#: Documented recommended poll interval.
RECOMMENDED_POLL_INTERVAL_SECONDS = 10


class TransportError(RuntimeError):
    """The transport could not complete a call.

    Deliberately says nothing about *why a generation might need retrying*, because
    a transport failure is never a reason to create another task.
    """


class UnknownTaskState(TransportError):
    """The provider reported a state this client does not recognise.

    Fails closed. An unknown state is not a failure, not a success, and above all
    not permission to create another task.
    """


@dataclass
class TaskPollResult:
    """One poll result. ``download_url`` is present only on success."""

    task_id: str
    state: str
    download_url: Optional[str] = None
    model: Optional[str] = None
    resolution: Optional[str] = None
    duration_s: Optional[int] = None
    ratio: Optional[str] = None
    task_type: Optional[str] = None
    modality: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def is_terminal(self) -> bool:
        return VideoTaskState.is_terminal(self.state)

    @property
    def is_success(self) -> bool:
        return VideoTaskState.is_success(self.state)

    @property
    def is_failure(self) -> bool:
        return VideoTaskState.is_failure(self.state)


class H3Transport:
    """What a video transport must offer. Three methods, one of them billable."""

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
        """Create one generation task and return its raw ``task_id``.

        This is the **only** billable call. Implementations must not retry it.
        """
        raise NotImplementedError

    def poll_task(self, task_id: str) -> TaskPollResult:
        """Ask about an existing task. Never creates anything."""
        raise NotImplementedError

    def download_result(self, url: str, destination: Path) -> Path:
        """Fetch an existing result. Never creates anything."""
        raise NotImplementedError


#: Documented data-URI subtypes, keyed by the file extension the operator supplied.
#: The API matches the declared subtype against the bytes, so declaring ``image/png``
#: for a JPEG is a request that can be refused for a reason the caller never saw.
REFERENCE_MIME_TYPES: Dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
}


def _encode_reference(path: Path) -> Dict[str, Any]:
    """Represent a local reference file for the API.

    The documented forms are a public URL, ``mm_file://{file_id}`` or a ``data:``
    URI. ContentOps holds local files, and the request body cap is 64 MB while
    Base64 inflates by roughly a third, so a data URI is only used when the caller
    has provided no URL and the encoded body still fits.

    The subtype is derived from the file extension rather than assumed, because the
    documented form is ``data:<type>/<format>`` and a mismatched format is a
    rejection the operator would read as a generation problem rather than an
    encoding problem.
    """
    mime = REFERENCE_MIME_TYPES.get(path.suffix.lower())
    if mime is None:
        raise TransportError(
            f"reference {path.name} has no documented media subtype, so no "
            f"valid data URI can be built for it; supported: "
            f"{', '.join(sorted(REFERENCE_MIME_TYPES))}"
        )
    override = os.environ.get("CONTENTOPS_H3_REFERENCE_BASE_URL", "").strip()
    if override:
        return {"url": f"{override.rstrip('/')}/{path.name}"}
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"url": f"data:{mime};base64,{encoded}"}


def build_content_array(
    *,
    prompt: str,
    first_frame: Optional[Path] = None,
    last_frame: Optional[Path] = None,
    reference_images: Optional[List[Path]] = None,
    reference_videos: Optional[List[Path]] = None,
    reference_audio: Optional[List[Path]] = None,
) -> List[Dict[str, Any]]:
    """Map a validated request into the documented ``content[]`` structure.

    This is the only place provider vocabulary appears. Business logic upstream
    deals in :class:`~contentops.media.video_contract.VideoRequest` and never sees
    ``content[]`` or ``role=``.
    """
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    if first_frame is not None:
        content.append({
            "type": "image_url",
            "image_url": _encode_reference(first_frame),
            "role": "first_frame",
        })
    if last_frame is not None:
        content.append({
            "type": "image_url",
            "image_url": _encode_reference(last_frame),
            "role": "last_frame",
        })
    for candidate in reference_images or []:
        content.append({
            "type": "image_url",
            "image_url": _encode_reference(candidate),
            "role": "reference_image",
        })
    for candidate in reference_videos or []:
        content.append({
            "type": "video_url",
            "video_url": _encode_reference(candidate),
            "role": "reference_video",
        })
    for candidate in reference_audio or []:
        content.append({
            "type": "audio_url",
            "audio_url": _encode_reference(candidate),
            "role": "reference_audio",
        })
    return content


def encoded_reference_bytes(content: List[Dict[str, Any]]) -> int:
    """Total bytes the reference portion of a request will occupy.

    Measured against the documented body cap. Base64 inflates by roughly a third,
    so a set of individually legal inputs can still exceed the 64 MB request cap;
    catching that here means the refusal costs nothing instead of arriving as a
    400 after the billing gate has already been consulted.
    """
    total = 0
    for item in content:
        if not isinstance(item, dict):
            continue
        for value in item.values():
            if isinstance(value, dict) and isinstance(value.get("url"), str):
                total += len(value["url"])
    return total


class HttpH3Transport(H3Transport):
    """The documented public API over HTTPS, using the standard library only.

    A third-party HTTP client would be a new dependency for three calls, and the
    standard library keeps the no-popup, no-shell property that
    :mod:`process_utils` guarantees for the CLI paths.

    ``base_url`` is not a formality. The same account family is reachable at both
    ``api.minimax.io`` and the regional mirror ``api.minimax.cn``, and a key
    authorised against one is not evidence about the other. Callers pass the same
    resolved base URL they gave :class:`~contentops.media.billing_guard.BillingGuard`
    so the billing proof and the billable call address the same service.
    """

    def __init__(
        self,
        *,
        credential: str,
        base_url: Optional[str] = None,
        timeout: int = 300,
        download_retries: int = 3,
    ) -> None:
        if not credential:
            raise TransportError(
                "no credential bound to the transport. Resolve one and pass it; "
                "refusing to fall back to an ambient key."
            )
        self._credential = credential
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._timeout = timeout
        self._download_retries = max(1, download_retries)
        #: Observable counters, so tests can prove a task was created only once.
        self.create_count = 0
        self.poll_count = 0
        self.download_count = 0
        self.polled_task_ids: List[str] = []
        self.downloaded_task_refs: List[str] = []

    # -- helpers -----------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        # The key goes in the Authorization header only: never a query string,
        # never a log line, never a receipt.
        return {
            "Authorization": f"Bearer {self._credential}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:  # noqa: BLE001
                detail = ""
            raise TransportError(
                f"{method} {path} failed with HTTP {exc.code}: {detail[:200]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"{method} {path} could not reach the provider: {exc.reason}") from exc
        try:
            parsed = json.loads(body or "{}")
        except json.JSONDecodeError as exc:
            raise TransportError(f"{method} {path} returned unparsable JSON") from exc
        if not isinstance(parsed, dict):
            raise TransportError(f"{method} {path} returned an unexpected shape")
        return parsed

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
        """Create exactly one task. Never retried by this method."""
        payload: Dict[str, Any] = {
            "model": model,
            "content": content,
            "resolution": resolution,
            "duration": int(duration_s),
        }
        if ratio:
            payload["ratio"] = ratio
        if extra:
            payload["extra"] = extra
        self.create_count += 1
        response = self._request("POST", CREATE_TASK_PATH, payload)
        task_id = response.get("task_id")
        if not task_id:
            raise TransportError(
                "the create response carried no task_id, so the generation cannot "
                "be tracked. Not retrying: a second create is a second bill."
            )
        return str(task_id)

    # -- free calls --------------------------------------------------------

    def poll_task(self, task_id: str) -> TaskPollResult:
        self.poll_count += 1
        self.polled_task_ids.append(task_id)
        payload = self._request(
            "GET", POLL_TASK_PATH_TEMPLATE.format(task_id=task_id)
        )
        task = payload.get("task")
        if not isinstance(task, dict):
            raise TransportError("the poll response carried no task object")
        state = str(task.get("status") or "").strip().lower()
        if state not in VideoTaskState.ALL:
            raise UnknownTaskState(
                f"the provider reported task state {state!r}, which this client "
                f"does not recognise. Failing closed: an unknown state is not "
                f"permission to create another task. Known states: "
                f"{', '.join(VideoTaskState.ALL)}."
            )
        content = task.get("content") or {}
        return TaskPollResult(
            task_id=str(task.get("id") or task_id),
            state=state,
            download_url=content.get("url") if isinstance(content, dict) else None,
            model=task.get("model"),
            resolution=task.get("resolution"),
            duration_s=task.get("duration"),
            ratio=task.get("ratio"),
            task_type=task.get("task_type"),
            modality=task.get("modality"),
            usage=task.get("usage") or {},
            error=task.get("error"),
        )

    def download_result(self, url: str, destination: Path) -> Path:
        """Fetch an existing result, retrying the **same URL** on failure.

        A failed download is a transport problem, never a reason to create a new
        generation, so the retry here re-fetches the same bytes.
        """
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        last_error: Optional[Exception] = None
        for attempt in range(self._download_retries):
            self.download_count += 1
            self.downloaded_task_refs.append(url)
            request = urllib.request.Request(url, headers={"User-Agent": "contentops/1"})
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    payload = response.read()
                if not payload:
                    raise TransportError("the download returned no bytes")
                destination.write_bytes(payload)
                return destination
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        raise TransportError(
            f"downloading the existing result failed after "
            f"{self._download_retries} attempts: {last_error}. Not creating "
            f"another task: the generation already happened."
        ) from last_error