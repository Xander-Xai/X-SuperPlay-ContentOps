"""The X post record, and everything that refuses it.

One record per intended post, schema ``contentops.x-post/v1``. The record is the
unit of review: it carries the copy, the theses, the recovery fields, the review,
the image and the status, and :func:`validate_post` reports every way it is not
yet a publishable post.

Three rules from the vendored gate are the ones this module exists for:

- a post that says ``published`` without a real ``status/<digits>`` URL is a lie,
  and it is refused rather than corrected;
- an image has to be an actual raster file at the account's canvas, not a path
  with the right extension and not an SVG;
- a metric that nobody observed is ``null``. ``0`` means "observed, and it was
  zero". The two are never interchangeable.

Nothing here reads the network, and nothing here can publish. This module grades
a record; :mod:`contentops.publish.publisher` packages a passing one for a person.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from contentops.publish import x_editorial, x_image, x_prompts, x_text

#: The record's schema. One record, one intended post.
SCHEMA = "contentops.x-post/v1"

#: The vendor's post states.
POST_STATUSES = ("draft", "scheduled", "published", "failed")

#: The codes that mean "the record is sound; the picture is not there yet".
IMAGE_CODES = frozenset(
    {"IMAGE_ABSENT", "IMAGE_NOT_RASTER", "IMAGE_WRONG_ASPECT", "IMAGE_UNDECODABLE"})

#: A status link, parsed without `urllib`: `https://x.com/<handle>/status/<id>`.
#: Trailing segments (`/photo/1`) are allowed because X's own share links carry
#: them, and the vendored `valid_x_url` accepts them.
_STATUS_URL = re.compile(
    r"^https://(?P<host>[^/\s]+)/(?P<handle>[^/\s?#]+)/status/(?P<id>\d+)"
    r"(?:[/?#]\S*)?$", re.IGNORECASE)
_STATUS_HOSTS = frozenset({"x.com", "www.x.com", "twitter.com", "www.twitter.com"})

#: A URL anywhere in ALT text: the link belongs in the post, not the description.
_ANY_URL = re.compile(r"https?://\S+", re.IGNORECASE)

#: The repository root, for the repo-relative references a record carries.
REPO_ROOT = Path(__file__).resolve().parents[3]


def _check_prompt_ref(post: Dict[str, Any], account: Dict[str, Any]) -> List[Issue]:
    """The prompt a record names must be one this account declares, and be here.

    A prompt is a reference, not a source of copy: this gate never generates
    anything. What it refuses is a record that points at a prompt nobody
    declared, or at a file that is not in this tree.
    """
    name = str(post.get("prompt_ref") or "").strip()
    if not name:
        return []
    prompts = x_prompts.prompt_map(account)
    if name not in prompts:
        return [Issue("PROMPT_REF_UNKNOWN",
                      f"prompt_ref {name!r} is not one of the account's prompts "
                      f"{sorted(prompts)}")]
    path = x_prompts.prompt_path(account, name)
    if path is None or not path.is_file():
        return [Issue("PROMPT_REF_ABSENT",
                      f"prompt_ref {name!r} points at {prompts[name]!r}, which is not "
                      "a file in this tree")]
    return []


def _check_provenance(post: Dict[str, Any]) -> List[Issue]:
    """A record that says where it came from must point at something real.

    ``provenance.source`` is repo-relative (the vendored draft, or a copy of a
    draft imported from a branch). A URL source is accepted as-is: this gate
    does not fetch, so it can only refuse a path it can look at.
    """
    provenance = post.get("provenance")
    if provenance is None:
        return []
    if not isinstance(provenance, dict):
        return [Issue("PROVENANCE_INVALID",
                      f"provenance is a {type(provenance).__name__}, not an object")]
    source = str(provenance.get("source") or "").strip()
    if not source:
        return [Issue("PROVENANCE_INVALID",
                      "provenance has no 'source'; a record that says nothing about "
                      "where it came from cannot be checked against anything")]
    if source.lower().startswith(("http://", "https://")):
        return []
    if not (REPO_ROOT / source).exists():
        return [Issue("PROVENANCE_SOURCE_ABSENT",
                      f"provenance source {source!r} is not a path in this tree")]
    return []



class PostFormatError(ValueError):
    """The file is not a readable ``contentops.x-post/v1`` record."""


@dataclass(frozen=True)
class Issue:
    """One named refusal, in the vendor's code vocabulary."""

    code: str
    detail: str

    def as_dict(self) -> Dict[str, str]:
        return {"code": self.code, "detail": self.detail}

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def load_post(path: Path) -> Dict[str, Any]:
    """Read a record. A wrong schema is a format error, not a refusal."""
    path = Path(path)
    try:
        post = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PostFormatError(f"{path} does not exist") from exc
    except json.JSONDecodeError as exc:
        raise PostFormatError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(post, dict):
        raise PostFormatError(f"{path} is a {type(post).__name__}, not an object")
    if post.get("schema") != SCHEMA:
        raise PostFormatError(
            f"{path} declares schema {post.get('schema')!r}; this gate owns {SCHEMA!r}")
    return post


def valid_status_url(url: Any, handle: Optional[str] = None) -> bool:
    """Is this a real X status link, and (when given it) the account's own?

    Agrees with the vendored ``valid_x_url`` on scheme, host, path shape and the
    numeric status id. When ``handle`` is given it must match, because a link to
    somebody else's post is not evidence that this account published.
    """
    text = str(url or "").strip()
    match = _STATUS_URL.match(text)
    if match is None:
        return False
    if match.group("host").lower() not in _STATUS_HOSTS:
        return False
    if handle:
        wanted = str(handle).strip().lstrip("@").lower()
        if wanted and match.group("handle").lower() != wanted:
            return False
    return True


def copy_parts(post: Dict[str, Any]) -> List[str]:
    """The post body as parts, from whichever shape the author used.

    ``post_copy.parts`` is canonical; a bare string is one part and a bare list
    is the parts. The gate refuses an empty body either way, so accepting the
    shorter shapes costs no rigour and spares an author a wrapper object.
    """
    copy = post.get("post_copy")
    if isinstance(copy, dict):
        parts = copy.get("parts")
    elif isinstance(copy, (list, tuple)):
        parts = list(copy)
    elif isinstance(copy, str):
        parts = [copy]
    else:
        parts = None
    if not isinstance(parts, (list, tuple)):
        return []
    return [str(part) for part in parts]


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()])


def _check_copy(post: Dict[str, Any], editorial: Dict[str, Any]) -> List[Issue]:
    issues: List[Issue] = []
    parts = copy_parts(post)
    if not parts or not any(part.strip() for part in parts):
        return [Issue("COPY_EMPTY", "the record has no post copy to publish")]
    if any(not part.strip() for part in parts):
        issues.append(
            Issue("COPY_EMPTY", "one part of the copy is blank; a thread with an "
                                "empty post in it is not a thread"))
    limit = editorial.get("max_chars_per_post")
    limit = limit if isinstance(limit, int) and limit > 0 else 280
    maximum = editorial.get("max_thread_posts")
    maximum = maximum if isinstance(maximum, int) and maximum > 0 else 3
    if len(parts) > maximum:
        issues.append(
            Issue("TOO_MANY_PARTS", f"the copy is {len(parts)} parts; the account "
                                    f"allows at most {maximum}"))
    for index, (part, length) in enumerate(zip(parts, x_text.parts_lengths(parts)), start=1):
        if length > limit:
            issues.append(
                Issue("COPY_TOO_LONG",
                      f"part {index} weighs {length} characters; the budget is {limit}"))
        foreign = x_text.foreign_scripts(part)
        if foreign:
            issues.append(
                Issue("LANGUAGE_NOT_EN",
                      f"part {index} contains non-Latin script ({', '.join(foreign[:4])}); "
                      "this account publishes in English"))
    return issues


def _check_image(post: Dict[str, Any], account: Dict[str, Any],
                 root: Optional[Path]) -> List[Issue]:
    visual = account.get("visual") or {}
    formats = tuple(str(item).lower() for item in visual.get("formats") or ("png", "jpeg"))
    target = str(visual.get("target") or "1600x900").lower()
    try:
        width, height = (int(piece) for piece in target.split("x", 1))
    except ValueError:
        width, height = 1600, 900

    image = post.get("image")
    if not isinstance(image, dict) or not str(image.get("path") or "").strip():
        return [Issue("IMAGE_ABSENT", "the record names no image; a post without its "
                                      "1600x900 card is not ready")]

    path = Path(str(image["path"]))
    if root is not None and not path.is_absolute():
        path = Path(root) / path
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "svg":
        return [Issue("IMAGE_NOT_RASTER",
                      f"{path.name} is an SVG; X needs a raster upload, and every "
                      "reference card in this repository ships as PNG")]
    if suffix and suffix not in formats:
        return [Issue("IMAGE_NOT_RASTER",
                      f"{path.name} has extension {suffix!r}; the account accepts "
                      f"{', '.join(formats)}")]
    if not path.is_file():
        return [Issue("IMAGE_ABSENT", f"the record points at {path}, which does not exist")]
    try:
        facts = x_image.image_facts(path)
    except x_image.UndecodableImage as exc:
        return [Issue("IMAGE_UNDECODABLE", str(exc))]
    if facts.format not in formats:
        return [Issue("IMAGE_NOT_RASTER",
                      f"{path.name} is {facts.format}; the account accepts "
                      f"{', '.join(formats)}")]
    if (facts.width, facts.height) != (width, height):
        return [Issue("IMAGE_WRONG_ASPECT",
                      f"{path.name} is {facts.width}x{facts.height}; the account "
                      f"canvas is {width}x{height}")]
    return []


def _check_alt(post: Dict[str, Any], account: Dict[str, Any]) -> List[Issue]:
    visual = account.get("visual") or {}
    alt = post.get("alt_text")
    if not str(alt or "").strip():
        return [Issue("ALT_MISSING", "the record has no ALT text; a card nobody can "
                                     "describe is a card screen readers cannot carry")]
    text = str(alt).strip()
    bounds = visual.get("alt_sentences") or [1, 2]
    maximum = int(bounds[-1]) if isinstance(bounds, (list, tuple)) and bounds else 2
    issues: List[Issue] = []
    count = _sentence_count(text)
    if count > maximum:
        issues.append(
            Issue("ALT_TOO_LONG", f"the ALT text is {count} sentences; the account "
                                  f"allows at most {maximum}"))
    if _ANY_URL.search(text):
        issues.append(
            Issue("ALT_CONTAINS_URL", "the ALT text contains a URL; the link belongs "
                                      "in the post body, where it is clickable"))
    return issues


def _check_mode(post: Dict[str, Any], account: Dict[str, Any]) -> List[Issue]:
    """A post belongs to one of the account's pillars, or to nothing."""
    pillars = [str(pillar.get("name")) for pillar in account.get("content_pillars") or []
               if isinstance(pillar, dict) and pillar.get("name")]
    mode = str(post.get("mode") or "")
    if not mode:
        return [Issue("MODE_UNKNOWN",
                      f"the record declares no mode; this account publishes "
                      f"{pillars or 'no declared pillars'}")]
    if pillars and mode not in pillars:
        return [Issue("MODE_UNKNOWN",
                      f"mode {mode!r} is not one of the account's pillars {pillars}")]
    return []


def _check_image_status(post: Dict[str, Any], account: Dict[str, Any]) -> List[Issue]:
    enum = [str(item) for item in (account.get("visual") or {}).get("image_status_enum") or []]
    value = post.get("image_status")
    if value is None or not enum:
        return []
    if str(value) not in enum:
        return [Issue("IMAGE_STATUS_INVALID",
                      f"image_status is {value!r}; expected one of {enum}")]
    return []


def _check_metrics(post: Dict[str, Any]) -> List[Issue]:
    """`null` means unobserved. A blank string or a bare zero does not."""
    metrics = post.get("metrics")
    if metrics is None:
        return []
    if not isinstance(metrics, dict):
        return [Issue("METRIC_NOT_OBSERVED",
                      "metrics is not an object; every metric is either a number or null")]
    issues: List[Issue] = []
    for name, value in metrics.items():
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(
                Issue("METRIC_NOT_OBSERVED",
                      f"metric {name!r} is {value!r}; an unobserved metric is null, "
                      "never a blank or a string, and 0 means an observed zero"))
        elif value < 0:
            issues.append(
                Issue("METRIC_NOT_OBSERVED", f"metric {name!r} is negative ({value})"))
    return issues


def _check_account(post: Dict[str, Any], account: Dict[str, Any]) -> List[Issue]:
    """A record may only claim the account its project resolved.

    ``validate_post`` is called with one DNA. If the record names a different
    slug, the two disagree about whose post this is, and grading it against this
    account would silently lend one account's review to another's copy.
    """
    declared = str(post.get("account_slug") or "").strip()
    expected = str(account.get("slug") or "").strip()
    if declared and expected and declared != expected:
        return [Issue("ACCOUNT_MISMATCH",
                      f"record account_slug is {declared!r} but the project's account "
                      f"is {expected!r}; one record cannot borrow another account's gate")]
    return []


def _check_status(post: Dict[str, Any], account: Dict[str, Any]) -> List[Issue]:
    publication = account.get("publication") or {}
    issues: List[Issue] = []
    status = str(post.get("status") or "")
    if status not in POST_STATUSES:
        return [Issue("STATUS_INVALID",
                      f"status is {status!r}; expected one of {list(POST_STATUSES)}")]

    url = post.get("status_url")
    if status == "published":
        if publication.get("requires_status_url", True) and not str(url or "").strip():
            issues.append(
                Issue("PUBLISHED_WITHOUT_URL",
                      "status is 'published' but the record has no status URL; a "
                      "post is published when the real link exists, not when the "
                      "author intended it"))
        if str(url or "").strip():
            known = publication.get("handle")
            handle = known if publication.get("handle_status") == "CONFIRMED" else None
            if not valid_status_url(url):
                issues.append(
                    Issue("PUBLISHED_URL_INVALID",
                          f"status_url {url!r} is not an https://x.com/<handle>/status/<id> link"))
            elif handle and not valid_status_url(url, handle=handle):
                issues.append(
                    Issue("HANDLE_MISMATCH",
                          f"status_url {url!r} is not posted by @{handle}; the account "
                          "owns neither the post nor the evidence"))
    return issues


def validate_post(post: Dict[str, Any], account: Dict[str, Any],
                  root: Optional[Path] = None) -> List[Issue]:
    """Every reason this record is not publishable, in a stable order."""
    editorial = x_editorial.editorial_rules(account)
    issues: List[Issue] = []
    issues.extend(_check_account(post, account))
    issues.extend(_check_mode(post, account))
    issues.extend(_check_copy(post, editorial))
    issues.extend(_check_status(post, account))
    issues.extend(_check_alt(post, account))
    issues.extend(_check_image(post, account, root))
    issues.extend(_check_image_status(post, account))
    issues.extend(_check_prompt_ref(post, account))
    issues.extend(_check_provenance(post))
    # `x_editorial` reports `(code, detail)` pairs; the record's surface is `Issue`.
    issues.extend(Issue(code, detail) for code, detail in x_editorial.validate_editorial(
        post, account, "\n".join(copy_parts(post))))
    issues.extend(_check_metrics(post))
    return issues


def post_verdict(post: Dict[str, Any], account: Dict[str, Any],
                 root: Optional[Path] = None) -> str:
    """One word for the record's state, derived from the same issues.

    ``DRAFT``        nothing is reviewed yet, so nothing is being claimed
    ``IMAGE_MISSING`` reviewed and sound; the 1600x900 card does not exist yet
    ``READY``        every gate passed and the post is waiting for a person
    ``PUBLISHED``    published, with a real status URL to prove it
    ``BLOCKED``      something is wrong that a person has to fix
    """
    issues = validate_post(post, account, root=root)
    if not issues:
        return "PUBLISHED" if post.get("status") == "published" else "READY"
    codes = {issue.code for issue in issues}
    if codes & {"PUBLISHED_WITHOUT_URL", "PUBLISHED_URL_INVALID", "HANDLE_MISMATCH",
                "STATUS_INVALID"}:
        return "BLOCKED"
    if codes <= IMAGE_CODES:
        return "IMAGE_MISSING"
    if codes <= IMAGE_CODES | {"REVIEW_MISSING"}:
        return "DRAFT"
    return "BLOCKED"
