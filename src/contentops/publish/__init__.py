"""Producing an X post as a package, never as a published thing.

The X track differs from every other producer in this repository in one way that
matters here: **it does not submit anything**. There is no API call, no token and
no scheduler. What this package does is take a post record, check it against the
delivery and editorial gates this repository states in prose, and assemble
the copy, the image and the ALT text into something a person can post by hand.

The modules:

- :mod:`contentops.publish.x_account` — the X account DNA contract
- :mod:`contentops.publish.x_text`   — the 280-weighted-character budget
- :mod:`contentops.publish.x_image`  — is this actually a 1600x900 PNG or JPEG
- :mod:`contentops.publish.x_editorial` — the theses, recovery fields and review
- :mod:`contentops.publish.x_prompts` — the prompt a record names, as a reference
- :mod:`contentops.publish.x_post`   — the record, its validators and its verdict
- :mod:`contentops.publish.publisher` — the package, and the refused API mode

`MANUAL_ONLY` is not a placeholder for an API. It is the current status, stated
honestly, and `publisher.PublishMode.API` raises rather than pretending.
"""

# Imported in dependency order, so no module sees a half-built package.
from contentops.publish import (  # noqa: F401
    publisher,
    x_account,
    x_growth_bridge,
    x_editorial,
    x_image,
    x_prompts,
    x_post,
    x_text,
)
from contentops.publish.publisher import (  # noqa: F401
    AWAITING,
    PACKAGE_SCHEMA,
    PackageBlocked,
    PublishMode,
    PublisherUnavailable,
    build_package,
    publish,
)
from contentops.publish.x_post import (  # noqa: F401
    SCHEMA,
    Issue,
    PostFormatError,
    load_post,
    post_verdict,
    valid_status_url,
    validate_post,
)

__all__ = [
    "AWAITING",
    "Issue",
    "PACKAGE_SCHEMA",
    "PackageBlocked",
    "PostFormatError",
    "PublishMode",
    "PublisherUnavailable",
    "SCHEMA",
    "build_package",
    "load_post",
    "post_verdict",
    "publish",
    "valid_status_url",
    "validate_post",
]
