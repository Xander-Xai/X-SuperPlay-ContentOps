"""Resolve the provider credential exactly once, and bind that one value.

The invariant this module exists to protect
------------------------------------------
```
THE CREDENTIAL AUTHORISED BY BILLINGGUARD
MUST BE
THE CREDENTIAL THE PROVIDER TRANSPORT ACTUALLY USES
```

The risk it closes
------------------
ContentOps and the official CLI each have their own credential discovery. If
ContentOps resolves ``MINIMAX_SUBSCRIPTION_KEY`` for the billing gate while the
``mmx`` child independently falls back to ``~/.mmx/config.json``, the gate can
authorise key **A** while the provider spends key **B**. Every balance check would
then pass while an unplanned credential did the work. "BillingGuard said SAFE, so
whatever mmx uses is probably fine" is exactly the reasoning this module forbids.

How it is enforced
------------------
1. :func:`resolve_credential` runs **once** per invocation and returns a
   :class:`ResolvedCredential`.
2. The same private value feeds both :class:`~contentops.media.billing_guard.BillingGuard`
   and the child transport.
3. The value is handed to the child through a **child-only environment**, never
   on argv, because argv is observable to anything on the host.
4. If the authorised credential cannot be bound into the child, generation
   **fails**. It never falls back to an ambient or stored credential.

The private value never leaves this module except as the ``key`` attribute, which
is deliberately excluded from ``__repr__``, ``__str__`` and serialisation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

__all__ = [
    "CLONE_CREDENTIAL_ENV",
    "CREDENTIAL_ABSENT",
    "CREDENTIAL_PAYG",
    "CREDENTIAL_SUBSCRIPTION",
    "CREDENTIAL_UNKNOWN",
    "CredentialBinding",
    "CredentialBindingError",
    "DuplicateCredentialError",
    "LOCAL_ENV_FILENAME",
    "load_local_env_file",
    "ResolvedCredential",
    "SOURCE_CLONE_ENV",
    "SOURCE_MMX_CONFIG",
    "SOURCE_NONE",
    "SOURCE_SUBSCRIPTION_ENV",
    "TwoKeyPair",
    "child_env_for",
    "classify_credential",
    "resolve_clone_credential",
    "resolve_credential",
    "resolve_subscription_credential",
    "resolve_two_key_pair",
]

CREDENTIAL_SUBSCRIPTION = "SUBSCRIPTION"
CREDENTIAL_PAYG = "PAYG"
CREDENTIAL_ABSENT = "ABSENT"
CREDENTIAL_UNKNOWN = "UNKNOWN"

SOURCE_SUBSCRIPTION_ENV = "MINIMAX_SUBSCRIPTION_KEY_ENV"
SOURCE_API_KEY_ENV = "MINIMAX_API_KEY_ENV"
SOURCE_MMX_CONFIG = "MMX_CONFIG"
SOURCE_NONE = "NONE"

#: The official CLI reads this one. The authorised key is injected here.
CHILD_CREDENTIAL_ENV = "MINIMAX_API_KEY"

#: The pay-as-you-go key that is allowed to create a clone. Deliberately a **separate**
#: variable with **no fallback chain**, which is the whole point of it.
CLONE_CREDENTIAL_ENV = "MINIMAX_CLONE_KEY"
SOURCE_CLONE_ENV = "MINIMAX_CLONE_KEY_ENV"


class DuplicateCredentialError(RuntimeError):
    """The two route keys resolved to the same value.

    The two-key route exists so the one billable step (clone) and the free step (TTS)
    are performed by different credentials with different billing sources. If both
    resolvers return the same secret then only one key is configured, and the route
    silently degrades into the single-key route that was already refused with 2061.

    Failing loudly is the only safe response: a degenerate configuration that looks
    like a working one is how a PAYG charge gets attributed to a Subscription Key.
    """


class CredentialBindingError(RuntimeError):
    """The authorised credential could not be bound to the transport.

    Raised instead of falling back to an ambient credential. A generation that
    cannot prove which key it used must not happen.
    """


def classify_credential(key: Optional[str]) -> str:
    """Classify a credential by prefix family without revealing it."""
    if not key:
        return CREDENTIAL_ABSENT
    if key.startswith("sk-cp-"):
        return CREDENTIAL_SUBSCRIPTION
    if key.startswith("sk-api-"):
        return CREDENTIAL_PAYG
    if key.startswith("sk-"):
        return CREDENTIAL_UNKNOWN
    return CREDENTIAL_UNKNOWN


@dataclass(frozen=True)
class ResolvedCredential:
    """One resolved credential: a private value plus safe metadata.

    ``key`` never appears in ``repr``, in ``str``, in a receipt, in an attempt
    record or in any exception message.
    """

    key: str = ""
    credential_class: str = CREDENTIAL_ABSENT
    source: str = SOURCE_NONE

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"ResolvedCredential(credential_class={self.credential_class!r}, "
            f"source={self.source!r}, key=<redacted>)"
        )

    __str__ = __repr__

    @property
    def usable(self) -> bool:
        return bool(self.key)

    def safe_metadata(self) -> Dict[str, str]:
        """Metadata that is safe to log, print or persist."""
        return {
            "credential_class": self.credential_class,
            "credential_source": self.source,
        }


def _from_mmx_config() -> tuple:
    config = Path.home() / ".mmx" / "config.json"
    if not config.is_file():
        return "", SOURCE_NONE
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return "", SOURCE_NONE
    if not isinstance(payload, dict):
        return "", SOURCE_NONE
    return str(payload.get("api_key") or ""), SOURCE_MMX_CONFIG


def resolve_credential(env: Optional[Dict[str, str]] = None) -> ResolvedCredential:
    """Resolve the credential once, in a fixed, documented order.

    Order: ``MINIMAX_SUBSCRIPTION_KEY``, then ``MINIMAX_API_KEY``, then the
    official CLI's own config file. Only the first two make ContentOps the
    authority; the config file is the last resort and is recorded as such,
    because a stored credential is the one most likely to drift from what the
    operator intended.

    Note the third step of that order is a *general* resolver used by paths that
    legitimately accept a pay-as-you-go key. Narration must not inherit it: the
    implicit fallback to ``MINIMAX_API_KEY`` (and, worse, a config file that
    could hold anything) is exactly the route the narration-v2 round closes.
    Narration callers use :func:`resolve_subscription_credential` instead.
    """
    environ = dict(os.environ if env is None else env)

    subscription = environ.get("MINIMAX_SUBSCRIPTION_KEY", "").strip()
    if subscription:
        return ResolvedCredential(
            key=subscription,
            credential_class=classify_credential(subscription),
            source=SOURCE_SUBSCRIPTION_ENV,
        )

    api_key = environ.get("MINIMAX_API_KEY", "").strip()
    if api_key:
        return ResolvedCredential(
            key=api_key,
            credential_class=classify_credential(api_key),
            source=SOURCE_API_KEY_ENV,
        )

    stored, source = _from_mmx_config()
    if stored:
        return ResolvedCredential(
            key=stored,
            credential_class=classify_credential(stored),
            source=source,
        )

    return ResolvedCredential(
        key="", credential_class=CREDENTIAL_ABSENT, source=SOURCE_NONE
    )


def resolve_subscription_credential(
    env: Optional[Dict[str, str]] = None,
) -> ResolvedCredential:
    """Resolve the credential narration may use, with no pay-as-you-go fallback.

    The narration route's default is ``MINIMAX_SUBSCRIPTION_KEY`` (Issue #34,
    narration v2). Two steps, and only these two:

    1. ``MINIMAX_SUBSCRIPTION_KEY``;
    2. the official CLI's stored config (``~/.mmx/config.json``), which on this
       account holds the same subscription credential the CLI itself uses.

    ``MINIMAX_API_KEY`` is deliberately absent from the chain. It is the
    pay-as-you-go fallback general resolution uses, and a narration request that
    silently borrows it would bill cash instead of plan quota -- the exact
    failure the fixed-billing requirement forbids. A machine without either
    subscription source therefore gets ``ABSENT`` and a refusal, not a key.
    The credential *class* is not rewritten here: a subscription-class check is
    the M Plan gate's job, and it must stay the single place that refuses.
    """
    environ = dict(os.environ if env is None else env)

    subscription = environ.get("MINIMAX_SUBSCRIPTION_KEY", "").strip()
    if subscription:
        return ResolvedCredential(
            key=subscription,
            credential_class=classify_credential(subscription),
            source=SOURCE_SUBSCRIPTION_ENV,
        )

    stored, source = _from_mmx_config()
    if stored:
        return ResolvedCredential(
            key=stored,
            credential_class=classify_credential(stored),
            source=source,
        )

    return ResolvedCredential(
        key="", credential_class=CREDENTIAL_ABSENT, source=SOURCE_NONE
    )


def resolve_clone_credential(env: Optional[Dict[str, str]] = None) -> ResolvedCredential:
    """Resolve the pay-as-you-go clone key, and *only* that key.

    No fallback chain, on purpose, and this is the single most important line in the
    two-key route. :func:`resolve_credential` walks Subscription Key -> API Key ->
    ``~/.mmx/config.json``, which is right for TTS and exactly wrong here: if this
    function inherited that chain, a machine with only a Subscription Key would
    "resolve" a clone credential from it and the clone would be sent on the plan
    that has already refused it once with ``2061``.

    Absence is therefore a first-class answer, not an error and not a fallback. An
    absent key means :data:`CREDENTIAL_ABSENT`, which callers surface as
    ``CLONE_KEY_REQUIRED`` so a human can provision one in the official console.
    """
    environ = dict(os.environ if env is None else env)
    clone_key = environ.get(CLONE_CREDENTIAL_ENV, "").strip()
    if not clone_key:
        return ResolvedCredential(
            key="", credential_class=CREDENTIAL_ABSENT, source=SOURCE_NONE
        )
    return ResolvedCredential(
        key=clone_key,
        credential_class=classify_credential(clone_key),
        source=SOURCE_CLONE_ENV,
    )


@dataclass(frozen=True)
class TwoKeyPair:
    """The clone credential and the TTS credential, proven distinct.

    Both private values are held here and never serialised; only the paired
    :meth:`safe_metadata` leaves. They are kept in one object precisely so the
    distinctness check happens once, at construction, rather than being remembered
    at each of the call sites that need it.
    """

    clone: ResolvedCredential
    tts: ResolvedCredential

    @property
    def clone_configured(self) -> bool:
        return self.clone.usable

    @property
    def tts_configured(self) -> bool:
        return self.tts.usable

    def require_distinct(self) -> None:
        """Raise unless both keys exist and differ.

        Raises:
            DuplicateCredentialError: both resolvers returned the same secret, so the
                route would collapse to a single key.
        """
        if not self.clone.usable or not self.tts.usable:
            return
        if self.clone.key == self.tts.key:
            raise DuplicateCredentialError(
                f"{CLONE_CREDENTIAL_ENV} and the TTS credential resolved to the same "
                f"secret (source {self.clone.source} vs {self.tts.source}). The "
                "two-key route needs two different keys: the clone is a pay-as-you-go "
                "step and the narration is a subscription step. Refusing rather than "
                "running a one-key route under a two-key name."
            )

    def safe_metadata(self) -> Dict[str, Dict[str, str]]:
        return {
            "clone": self.clone.safe_metadata(),
            "tts": self.tts.safe_metadata(),
            "keys_distinct": (
                self.clone.key != self.tts.key if self.clone.usable and self.tts.usable
                else None
            ),
        }


def resolve_two_key_pair(env: Optional[Dict[str, str]] = None) -> TwoKeyPair:
    """Resolve both route credentials and prove they are different secrets.

    :raises DuplicateCredentialError: both resolvers returned the same value.
    """
    pair = TwoKeyPair(clone=resolve_clone_credential(env), tts=resolve_credential(env))
    pair.require_distinct()
    return pair


#: The conventional local credential file. Gitignored (``.gitignore``) and listed in
#: ``scripts/check_repo_policy.py``'s local-only set, which is why it exists at all.
LOCAL_ENV_FILENAME = ".env"


def load_local_env_file(
    path: Optional[Path] = None,
    *,
    env: Optional[Dict[str, str]] = None,
) -> List[str]:
    """Populate ``os.environ`` from the local ``.env`` file. Returns *names* only.

    This exists because credential resolution reads ``os.environ`` and nothing else,
    and because there is deliberately no dotenv dependency in this repository. A
    pay-as-you-go clone key has no config-file fallback the way the Subscription Key
    has ``~/.mmx/config.json``, so without this the route is unusable in practice.

    Three properties are load-bearing, and each closes a way this file could quietly
    become a leak:

    1. **It returns variable *names*, never values.** A caller that logs the result to
       report "loaded 3 credentials" cannot accidentally report a secret.
    2. **It never overrides an existing environment variable.** A value already in the
       process wins, so a stale file cannot silently displace a deliberately set key.
    3. **It refuses to read a file Git tracks.** An untracked, ignored file is local
       state; a tracked one is a secret already in the repository's history, and
       reading it would normalise treating that as a supported configuration.

    Not called automatically anywhere. Loading a file that holds secrets is an action,
    and the caller decides when it happens.
    """
    from process_utils import hidden_run

    target = Path(path) if path is not None else Path.cwd() / LOCAL_ENV_FILENAME
    if not target.is_file():
        return []
    try:
        root = hidden_run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(target.parent), timeout=60
        )
        if root.returncode == 0:
            cwd = Path((root.stdout or "").strip())
            rel = target.resolve().relative_to(cwd.resolve()).as_posix()
            tracked = hidden_run(
                ["git", "ls-files", "--error-unmatch", "--", rel],
                cwd=str(cwd),
                timeout=60,
            )
            if tracked.returncode == 0:
                raise CredentialBindingError(
                    f"{rel} is tracked by Git. Reading it would treat a committed "
                    "secret as a supported configuration. Remove it from the index and "
                    "rotate the credential before continuing."
                )
    except CredentialBindingError:
        raise
    except Exception:  # noqa: BLE001 - not in a repository at all
        pass

    environ = os.environ if env is None else env
    loaded: List[str] = []
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if not name or not value:
            continue
        if environ.get(name):
            continue
        environ[name] = value
        loaded.append(name)
    return loaded


def child_env_for(
    resolved: ResolvedCredential, base_env: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Build the child-only environment that binds the authorised credential.

    Raises:
        CredentialBindingError: there is no authorised credential to bind. The
            caller must fail rather than let the child discover one on its own.
    """
    if not resolved.usable:
        raise CredentialBindingError(
            "no authorised credential to bind into the provider transport; "
            f"resolved source={resolved.source} class={resolved.credential_class}. "
            "Refusing to let the child fall back to an ambient credential."
        )
    child = dict(os.environ if base_env is None else base_env)
    child[CHILD_CREDENTIAL_ENV] = resolved.key
    # The subscription variable would otherwise shadow nothing but could mislead
    # a future reader into thinking it was the one in force.
    child.pop("MINIMAX_SUBSCRIPTION_KEY", None)
    return child


class CredentialBinding:
    """One resolved credential, bound once, for one provider.

    Both the speech and the image provider hold one of these. It exists so that
    the binding rule is enforced in exactly one place: a provider asks for
    :meth:`require_env` and either gets the child environment containing the
    authorised key, or gets a :class:`CredentialBindingError`. Neither provider
    can re-resolve a credential of its own, because neither has a resolver.

    Binding is **lazy**, and that is deliberate. Construction always succeeds so
    that ``--health`` still runs on an unauthenticated host: the first thing an
    operator does when generation fails is ask why, and a diagnostic command that
    itself crashes with a credential error is worse than useless. The refusal
    still happens before any child process is launched, which is the point at
    which it actually matters.
    """

    def __init__(self, resolved: Optional["ResolvedCredential"] = None) -> None:
        self._resolved = resolved
        self._child_env: Optional[Dict[str, str]] = None
        if resolved is not None and resolved.usable:
            self._child_env = child_env_for(resolved)

    @property
    def resolved(self) -> Optional["ResolvedCredential"]:
        return self._resolved

    @property
    def is_bound(self) -> bool:
        return self._child_env is not None

    def safe_metadata(self) -> Dict[str, str]:
        """Metadata that is safe to log, print or persist."""
        if self._resolved is None:
            return {
                "credential_class": CREDENTIAL_ABSENT,
                "credential_source": "UNBOUND",
            }
        return self._resolved.safe_metadata()

    def require_env(self) -> Dict[str, str]:
        """The child environment, or a refusal.

        Raises:
            CredentialBindingError: no credential was bound. The caller must not
                generate; letting the child discover its own credential is
                precisely the failure this prevents.
        """
        if self._child_env is None:
            raise CredentialBindingError(
                "no credential is bound to the provider transport. Resolve it "
                "once and pass it as transport_credential= so the billing gate "
                "and the child use the same key. Refusing to generate rather "
                "than let the child pick one itself."
            )
        return self._child_env

