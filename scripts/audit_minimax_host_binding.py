#!/usr/bin/env python3
"""Zero-fee audit of the MiniMax host and credential binding. Issue #34.

What it answers, from local facts plus an optional read-only probe
-----------------------------------------------------------------
The three refused first-activation attempts recorded one host for their balance
evidence and a *different* host for the synthesis itself, and they claimed a
credential class the transport may not have used. This script makes both facts
checkable:

- ``BALANCE_QUERY_HOST`` -- where :class:`BillingGuard` reads balances from
  (``CONTENTOPS_MINIMAX_BASE_URL``).
- ``CLI_ACTUAL_HOST`` -- where the official CLI sends its requests, derived
  from its own config (``region`` -> documented host, or a stored ``base_url``).
- ``HOSTS_MATCH`` -- whether those two are the same service.
- ``CREDENTIAL_BINDING`` -- what ContentOps injects versus what the CLI's
  request-auth resolver actually consults, for the installed CLI version.

The default run performs **no network I/O**: it reads environment variables,
``~/.mmx/config.json`` and asks the CLI two local questions (``--version`` and
``config show``). ``--probe-readonly`` additionally performs balance and quota
reads -- both documented as free, non-billable reads -- against each candidate
host so "is this host even able to see the account" is measured rather than
assumed.

What it never does: print a credential, spend anything, or write a request with
a generation endpoint. The probe only performs the two read-only reads whose
paths :mod:`contentops.media.billing_guard` already owns -- the account-balance
read and the plan-quota read -- via the paths it exports, so this script never
re-declares an endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from process_utils import hidden_run  # noqa: E402

from contentops.media.billing_guard import (  # noqa: E402
    BALANCE_PATH,
    REMAINS_PATH,
)
from contentops.media.minimax_native_tts import (  # noqa: E402
    DOCUMENTED_CN_HOSTS,
    MINIMAX_CN_HOST,
    host_is_documented_cn,
    normalize_host,
)

#: The CLI's own region -> host table, read from the bundled source of the
#: installed version (``mmx-cli`` 1.0.27). Recorded here so the audit can state
#: where the CLI *would* send without performing a request.
REGION_HOSTS: Dict[str, str] = {
    "global": "https://api.minimax.io",
    "cn": "https://api.minimax.cn",
}

#: The CLI version whose bundled auth resolver was analysed for Issue #34.
#: If the installed version differs, the "env key is not honoured" finding must
#: be re-measured before it is relied on, so the audit reports the mismatch.
ANALYSED_CLI_VERSION = "1.0.27"

#: Whether the analysed CLI honours ``MINIMAX_API_KEY`` from the environment for
#: request authentication. False: the resolver is flag -> OAuth -> config file;
#: the env var is read only by the interactive onboarding prompt.
CLI_ENV_KEY_HONOURED_FOR_AUTH = False

# The balance and quota paths are NOT redeclared here: they are imported from
# ``contentops.media.billing_guard``, the single module allowed to own the
# undocumented balance endpoint (asserted by
# ``tests/test_minimax_speech.py::test_balance_endpoint_lives_in_exactly_one_module``).

RunFn = Callable[[List[str]], Tuple[int, str, str]]


def _cli_prefix() -> Optional[List[str]]:
    """Resolve the official CLI the same way every other caller does.

    A bare ``mmx`` does not resolve through CreateProcess on Windows -- npm
    installs ``mmx.cmd`` shims -- so this goes through ``resolve_cli()``, the
    one sanctioned resolver.
    """
    from contentops.media.transport import resolve_cli

    resolved = resolve_cli()
    if not resolved:
        return None
    return list(resolved) if isinstance(resolved, (list, tuple)) else [str(resolved)]


def _default_run(argv: List[str]) -> Tuple[int, str, str]:
    result = hidden_run(argv, timeout=60)
    return result.returncode, result.stdout or "", result.stderr or ""


def _read_mmx_config(home: Path) -> Dict[str, Any]:
    """Read the CLI config for host/region facts. The key value is dropped here.

    Only presence and shape are kept; the credential itself never enters the
    audit. ``has_file_api_key`` is all the binding question needs.
    """
    path = home / ".mmx" / "config.json"
    if not path.is_file():
        return {"config_present": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"config_present": True, "config_readable": False}
    if not isinstance(payload, dict):
        return {"config_present": True, "config_readable": False}
    return {
        "config_present": True,
        "config_readable": True,
        "region": payload.get("region"),
        "file_base_url": payload.get("base_url"),
        "has_file_api_key": bool(payload.get("api_key")),
        "has_oauth": bool(payload.get("oauth")),
    }


def collect_local_facts(
    *,
    env: Optional[Dict[str, str]] = None,
    home: Optional[Path] = None,
    run: Optional[RunFn] = None,
    cli_prefix: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Gather every fact the audit reasons about. No network, no secrets."""
    environ = dict(os.environ if env is None else env)
    home_dir = Path.home() if home is None else Path(home)
    runner = run or _default_run

    config = _read_mmx_config(home_dir)

    cli_version = ""
    cli_config_show: Dict[str, Any] = {}
    prefix = list(cli_prefix) if cli_prefix is not None else _cli_prefix()
    cli_available = prefix is not None
    if cli_available:
        rc, out, _ = runner(prefix + ["--version"])
        if rc == 0:
            cli_version = out.strip()
        rc, out, _ = runner(prefix + ["config", "show"])
        if rc == 0:
            try:
                shown = json.loads(out)
                if isinstance(shown, dict):
                    # Never carry the key field, even in its redacted CLI form.
                    cli_config_show = {
                        key: value for key, value in shown.items() if key != "api_key"
                    }
            except json.JSONDecodeError:
                cli_config_show = {"parse_error": True}

    return {
        "env": {
            "contentops_base_url": (environ.get("CONTENTOPS_MINIMAX_BASE_URL") or "").strip(),
            "voice_clone_base_url": (environ.get("MINIMAX_VOICE_CLONE_BASE_URL") or "").strip(),
            "has_minimax_api_key_env": bool(environ.get("MINIMAX_API_KEY")),
            "has_minimax_clone_key_env": bool(environ.get("MINIMAX_CLONE_KEY")),
        },
        "cli": {
            "available": cli_available,
            "version": cli_version,
            "config_show": cli_config_show,
        },
        "mmx_config": config,
    }


def derive_cli_host(config: Dict[str, Any]) -> Dict[str, Any]:
    """Where the CLI will send, per its own resolution rules.

    Order from the CLI's bundled resolver: an explicit ``--base-url`` (not used
    here), ``MINIMAX_BASE_URL`` from the environment (not used here), a stored
    ``base_url``, an OAuth ``resource_url``, then the region table, then the
    global default. The audit only models what the config can express.
    """
    region = config.get("region") or "global"
    host = (
        config.get("file_base_url")
        or REGION_HOSTS.get(region)
        or REGION_HOSTS["global"]
    )
    return {
        "region": region,
        "host": normalize_host(str(host)),
        "resolved_from": (
            "config.base_url"
            if config.get("file_base_url")
            else f"region_table[{region}]"
        ),
    }


def evaluate(facts: Dict[str, Any]) -> Dict[str, Any]:
    """The audit verdict. Pure function over collected facts."""
    env = facts.get("env") or {}
    config = facts.get("mmx_config") or {}
    cli = facts.get("cli") or {}

    balance_query_host = normalize_host(env.get("contentops_base_url") or "")
    clone_env_host = normalize_host(env.get("voice_clone_base_url") or "")
    cli_host = derive_cli_host(config)

    # The activation path will use the native adapter, which pins this host.
    activation_host = MINIMAX_CN_HOST

    hosts_match = (
        balance_query_host == cli_host["host"] == activation_host
        if balance_query_host
        else False
    )

    version = str(cli.get("version") or "").strip()
    version_match = re.search(r"\d+(?:\.\d+)+", version)
    version_token = version_match.group(0) if version_match else version
    version_matches_analysis = version_token == ANALYSED_CLI_VERSION

    binding: Dict[str, Any] = {
        "contentops_injects_env_var": "MINIMAX_API_KEY",
        "contentops_removes_shadow_var": "MINIMAX_SUBSCRIPTION_KEY",
        "cli_installed_version": version or "UNKNOWN",
        "cli_version_token": version_token or "UNKNOWN",
        "cli_version_analysed": ANALYSED_CLI_VERSION,
        "cli_version_matches_analysis": version_matches_analysis,
        "cli_honours_env_key_for_auth": (
            CLI_ENV_KEY_HONOURED_FOR_AUTH if version_matches_analysis else "REANALYSE"
        ),
        "cli_auth_resolver_order": ["--api-key flag", "oauth token", "config.json api_key"],
        "file_api_key_present": bool(config.get("has_file_api_key")),
        "file_oauth_present": bool(config.get("has_oauth")),
        "credential_binding_verified": False,
        "why": (
            "ContentOps binds the authorised key through the child environment "
            "(MINIMAX_API_KEY), but the installed CLI resolves request auth from "
            "its flag, OAuth token or config file, in that order, and never from "
            "that environment variable. A request sent through the CLI therefore "
            "authenticates with the config-file credential regardless of what was "
            "injected. Until the transport is one this repository controls (the "
            "native adapter), the injected credential is a claim, not a fact."
        ),
    }
    if not version_matches_analysis:
        binding["why"] = (
            "The installed CLI version differs from the analysed version, so the "
            "resolver-order finding must be re-measured against the installed "
            "bundle before it is relied on. Treated as UNVERIFIED, not as fixed."
        )

    warnings = []
    if balance_query_host and balance_query_host != activation_host:
        warnings.append(
            f"balance queries addressed {balance_query_host} while the activation "
            f"call is pinned to {activation_host}; the billing evidence and the "
            "billed request would come from different services"
        )
    if clone_env_host and clone_env_host != activation_host:
        warnings.append(
            "MINIMAX_VOICE_CLONE_BASE_URL points at a different host than the "
            "documented CN service"
        )
    if not hosts_match:
        warnings.append("HOSTS_MATCH is false; see the two hosts above")

    return {
        "schema": "contentops.host-and-region-audit/v1",
        "issue": "#34",
        "BALANCE_QUERY_HOST": balance_query_host or None,
        "VOICE_CLONE_ENV_HOST": clone_env_host or None,
        "CLI_REGION": cli_host["region"],
        "CLI_ACTUAL_HOST": cli_host["host"],
        "CLI_HOST_RESOLVED_FROM": cli_host["resolved_from"],
        "ACTIVATION_ADAPTER_HOST": activation_host,
        "DOCUMENTED_CN_HOSTS": list(DOCUMENTED_CN_HOSTS),
        "HOSTS_MATCH": hosts_match,
        "CREDENTIAL_BINDING": binding,
        "CREDENTIAL_BINDING_VERIFIED": binding["credential_binding_verified"],
        "warnings": warnings,
        "money_spent_by_this_audit_cny": "0.00",
    }


def _http_get_json(
    url: str, credential: str, timeout_s: float = 60.0
) -> Dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + credential}, method="GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return {"http_status": int(response.status),
                    "body": json.loads(response.read().decode("utf-8"))}
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            body = None
        return {"http_status": int(exc.code), "body": body}
    except Exception as exc:  # noqa: BLE001
        return {"http_status": None, "error": type(exc).__name__}


def _summarise_probe(host: str, path: str, result: Dict[str, Any]) -> Dict[str, Any]:
    body = result.get("body") or {}
    base = body.get("base_resp") or {}
    summary: Dict[str, Any] = {
        "host": host,
        "path": path,
        "http_status": result.get("http_status"),
        "base_resp": {
            "status_code": base.get("status_code"),
            "status_msg": base.get("status_msg"),
        },
    }
    if "error" in result:
        summary["error"] = result["error"]
    if path == BALANCE_PATH and isinstance(body, dict):
        summary["balances"] = {
            key: body.get(key)
            for key in (
                "cash_balance",
                "voucher_balance",
                "credit_balance",
                "owed_amount",
                "available_amount",
            )
            if key in body
        }
    if path == REMAINS_PATH and isinstance(body, dict):
        rows = body.get("model_remains") or []
        summary["quota"] = [
            {
                "model_name": row.get("model_name"),
                "interval_remaining_percent": row.get("current_interval_remaining_percent"),
                "weekly_remaining_percent": row.get("current_weekly_remaining_percent"),
            }
            for row in rows[:2]
            if isinstance(row, dict)
        ]
    return summary


def probe_readonly(
    *,
    hosts: Tuple[str, ...],
    payg_key: str,
    subscription_key: str,
    http_get: Callable[[str, str], Dict[str, Any]] = _http_get_json,
) -> Dict[str, Any]:
    """Read-only, non-billable reads against each host. No generation call.

    Both endpoints are documented as plain reads. This exists to answer one
    question per host: *can this host see this account at all?* -- which is what
    makes "the balance was read from a different service than the one that
    billed" a measurement instead of a suspicion.
    """
    out: Dict[str, Any] = {"payg": [], "subscription": []}
    for host in hosts:
        if payg_key:
            out["payg"].append(
                _summarise_probe(host, BALANCE_PATH, http_get(host + BALANCE_PATH, payg_key))
            )
        if subscription_key:
            out["subscription"].append(
                _summarise_probe(host, REMAINS_PATH, http_get(host + REMAINS_PATH, subscription_key))
            )
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--probe-readonly",
        action="store_true",
        help=(
            "also perform read-only balance/quota reads against each candidate "
            "host. These endpoints do not bill. Without this flag the audit is "
            "fully offline."
        ),
    )
    parser.add_argument("--out", type=Path, default=None,
                        help="write the audit JSON here as well as to stdout")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    from contentops.media.credentials import (
        load_local_env_file,
        resolve_clone_credential,
        resolve_credential,
    )

    load_local_env_file(ROOT / ".env")
    facts = collect_local_facts()
    audit = evaluate(facts)
    audit["facts"] = {
        "env": facts["env"],
        "mmx_config": facts["mmx_config"],
        "cli_version": facts["cli"]["version"] or "UNKNOWN",
    }

    if args.probe_readonly:
        payg = resolve_clone_credential()
        sub = resolve_credential()
        hosts = tuple(
            dict.fromkeys(
                [
                    host
                    for host in (
                        audit["BALANCE_QUERY_HOST"],
                        audit["CLI_ACTUAL_HOST"],
                        audit["ACTIVATION_ADAPTER_HOST"],
                    )
                    if host
                ]
            )
        )
        audit["readonly_probe"] = {
            "hosts": list(hosts),
            "note": (
                "balance and quota reads only; both are documented as free reads "
                "and neither generates or activates anything"
            ),
            "results": probe_readonly(
                hosts=hosts,
                payg_key=payg.key if payg.usable else "",
                subscription_key=sub.key if sub.usable else "",
            ),
        }

    blob = json.dumps(audit, indent=2, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to emit an audit containing {banned!r}")
    print(blob)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(blob + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
