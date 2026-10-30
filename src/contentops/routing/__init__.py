"""Account-aware content routing: one entrance, two routes, one brief.

The package is four things:

- :mod:`account_profile` reads the account DNA and refuses to guess.
- :mod:`models` holds the unified content contract and the one state machine.
- :mod:`hotspot_route` and :mod:`user_topic_route` are the two entrances.
- :mod:`router` is the entry point both of them are reached through.

The brief package is built in :mod:`brief`, and the candidate pool is stored
in :mod:`contentops.hotspots.storage`.
"""

from .account_profile import (
    AccountProfile,
    Keyword,
    load_all_profiles,
    load_profile,
    list_account_slugs,
    profile_video_capable,
    target_pipeline_for,
    verify_origin,
)
from .models import (
    CONTENT_INTENT_SCHEMA,
    ROUTE_MODES,
    STATES,
    TRANSITIONS,
    ContentIntent,
    RouteContext,
    RoutingError,
    can_transition,
    assert_transition,
    utcnow,
    validate_intent,
)
from .router import ContentRouter, RunResult
from .user_topic_route import UserTopicInput

__all__ = [
    "CONTENT_INTENT_SCHEMA",
    "ROUTE_MODES",
    "STATES",
    "TRANSITIONS",
    "AccountProfile",
    "ContentIntent",
    "ContentRouter",
    "Keyword",
    "RouteContext",
    "RoutingError",
    "RunResult",
    "UserTopicInput",
    "assert_transition",
    "can_transition",
    "load_all_profiles",
    "load_profile",
    "list_account_slugs",
    "profile_video_capable",
    "target_pipeline_for",
    "utcnow",
    "validate_intent",
    "verify_origin",
]
