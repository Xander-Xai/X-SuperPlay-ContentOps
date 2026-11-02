#!/usr/bin/env python3
"""Read and check the account and platform registries.

The registries are data. This CLI is the operational way to ask what exists,
which account a name means, and whether the two files still agree. It never
renders, publishes or spends.

Usage
-----
    python scripts/platforms.py list
    python scripts/platforms.py accounts
    python scripts/platforms.py resolve --account thinktank
    python scripts/platforms.py check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.platforms.registry import (  # noqa: E402
    RegistryError,
    formats_for_account,
    load_accounts,
    load_platforms,
    resolve_account,
    summarise,
    validate_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    def _sub(name: str, help_text: str):
        # Accept --json on either side of the subcommand. SUPPRESS keeps the
        # subparser from overwriting a --json given before the subcommand.
        child = sub.add_parser(name, help=help_text)
        child.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        return child

    _sub("list", "list platforms")
    _sub("accounts", "list account identities")
    _sub("check", "validate both registries")
    resolve = _sub("resolve", "resolve an account identifier")
    resolve.add_argument("--account", required=True)
    args = parser.parse_args()

    try:
        if args.command == "list":
            platforms = load_platforms(ROOT)
            payload = [entry.to_dict() for entry in platforms.values()]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                print(f"{'platform':<22} {'status':<20} {'pipeline':<18} "
                      f"{'publish':<16} accounts")
                print("-" * 110)
                for entry in payload:
                    print(f"{entry['platform_id']:<22} {entry['status']:<20} "
                          f"{entry['pipeline']:<18} {entry['publish_mode']:<16} "
                          f"{', '.join(entry['accounts']) or '-'}")
                    if entry["not_claimed"]:
                        print(f"  not claimed: {entry['not_claimed']}")
        elif args.command == "accounts":
            accounts = load_accounts(ROOT)
            payload = [
                {
                    "account_slug": account.account_slug,
                    "internal_ids": list(account.internal_ids),
                    "display_name": account.display_name,
                    "aliases": list(account.aliases),
                    "role": account.role,
                    "platform_accounts": dict(account.platform_accounts),
                    "content_formats": list(formats_for_account(ROOT,
                                                                account.account_slug)),
                }
                for account in accounts.values()
            ]
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            else:
                for entry in payload:
                    print(f"{entry['account_slug']}  ({entry['display_name']}, "
                          f"{entry['role']})")
                    print(f"  internal  {', '.join(entry['internal_ids'])}")
                    print(f"  aliases   {', '.join(entry['aliases']) or '-'}")
                    print(f"  formats   {', '.join(entry['content_formats']) or '-'}")
                    for platform, label in entry["platform_accounts"].items():
                        print(f"  {platform:<22} {label}")
        elif args.command == "resolve":
            account = resolve_account(ROOT, args.account)
            payload = {
                "account_slug": account.account_slug,
                "internal_ids": list(account.internal_ids),
                "display_name": account.display_name,
                "aliases": list(account.aliases),
                "content_formats": list(formats_for_account(ROOT,
                                                            account.account_slug)),
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        elif args.command == "check":
            failures = validate_registry(ROOT)
            payload = summarise(ROOT) if not failures else {}
            if args.json:
                print(json.dumps({"ok": not failures, "failures": failures,
                                  "summary": payload}, ensure_ascii=False, indent=2))
            elif failures:
                print("FAILED")
                for failure in failures:
                    print(f"  - {failure}")
            else:
                print("OK: account and platform registries agree")
            return 0 if not failures else 1
    except RegistryError as exc:
        print(f"BLOCKED {exc.code}: {exc.detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
