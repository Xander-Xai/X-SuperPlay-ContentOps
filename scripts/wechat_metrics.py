#!/usr/bin/env python3
"""Fetch WeChat Official Account statistics through the official data cube.

This is the transport for the ``api_official`` channel declared for
``wechat_article``. It uses the vendored ``wechatpy`` data cube client,
imported lazily and only under ``--execute`` — the same dependency the draft
channel already uses, so no new upstream enters the tree.

    preflight   credential shape only. Offline. Never echoes a value.
    plan        endpoint listing + range validation. Offline.
    fetch       token -> data cube -> receipt. Requires --execute.

What this script will not do
----------------------------
* It will not guess whether the caller's IP is whitelisted. WeChat answers
  ``40164`` for that; the script surfaces the real error code and writes no
  metrics.
* It will not widen a range past the official ceiling (7 days for the user
  summary, 1 day for the article summary). A wider range is refused, not
  silently split into chunks that pretend to be one answer.
* It will not zero-fill a day the cube has not aggregated.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts", ROOT / "vendor" / "wechatpy"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import load_account  # noqa: E402
from contentops.platforms import wechat_metrics as wm  # noqa: E402

#: WeChat answers this for an IP that is not on the account's whitelist.
IP_NOT_WHITELISTED = "40164"
#: Wrong or missing credential.
BAD_CREDENTIALS = "40001"


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_env(path: Path) -> Dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"BLOCKED: 凭证文件不存在 {path}")
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_values(args: argparse.Namespace) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if args.env:
        env.update(_parse_env(Path(args.env)))
    import os

    for key in wm.CREDENTIAL_KEYS:
        if not env.get(key) and os.environ.get(key):
            env[key] = os.environ[key]
    return env


def _receipt_path(project_dir: Path | None, out: Path | None) -> Path:
    if out is not None:
        return Path(out)
    if project_dir is None:
        raise SystemExit("BLOCKED: --project or --out is required so the receipt lands somewhere real")
    return project_dir / "receipts" / "metrics-wechat.json"


def cmd_preflight(args: argparse.Namespace) -> int:
    report = wm.preflight(_env_values(args))
    report["state"] = "PREFLIGHT_PASS" if report.get("ok") else "PREFLIGHT_FAIL"
    _emit(report)
    return 0 if report.get("ok") else 4


def cmd_plan(args: argparse.Namespace) -> int:
    problems = wm.validate_range(args.begin_date, args.end_date, wm.MAX_USER_SUMMARY_DAYS)
    payload: Dict[str, Any] = {
        "state": "PLAN",
        "schema": wm.RECEIPT_SCHEMA,
        "begin_date": args.begin_date,
        "end_date": args.end_date,
        "endpoints": wm.DATA_CUBE_ENDPOINTS,
        "execute_required": True,
    }
    if problems:
        payload["state"] = "BLOCKED"
        payload["problems"] = problems
    _emit(payload)
    return 4 if problems else 0


def cmd_fetch(args: argparse.Namespace) -> int:
    if not args.execute:
        raise SystemExit("BLOCKED: fetch touches the network; pass --execute")
    env = _env_values(args)
    report = wm.preflight(env)
    if not report.get("ok"):
        report["state"] = "PREFLIGHT_FAIL"
        _emit(report)
        return 4
    problems = wm.validate_range(args.begin_date, args.end_date, wm.MAX_USER_SUMMARY_DAYS)
    if problems:
        _emit({"state": "BLOCKED", "problems": problems})
        return 4

    try:
        from wechatpy import WeChatClient  # lazy: vendored, only under --execute
    except ImportError as exc:
        raise SystemExit(
            "BLOCKED: the vendored wechatpy client needs its runtime deps "
            f"(optionaldict, xmltodict): {exc}"
        ) from None

    client = WeChatClient(env[wm.CREDENTIAL_KEYS[0]], env[wm.CREDENTIAL_KEYS[1]])
    data: Dict[str, Any] = {}
    issues: List[str] = []
    endpoints_used: List[str] = []

    def _call(name: str, fn, *call_args):
        try:
            rows = fn(*call_args)
            endpoints_used.append(name)
            return rows
        except Exception as exc:  # noqa: BLE001 - real API failures surface verbatim
            code = getattr(exc, "errcode", None)
            detail = f"{name}: {type(exc).__name__} errcode={code} msg={getattr(exc, 'errmsg', exc)}"
            if code is not None and str(code) == IP_NOT_WHITELISTED:
                detail += " (IP not whitelisted: add the egress IP in the MP console)"
            issues.append(detail)
            return None

    user_rows = _call("user_summary", client.datacube.get_user_summary, args.begin_date, args.end_date)
    if user_rows is not None:
        data["user_summary"] = wm.normalise_metric_rows(
            user_rows, day_fields=("cumulate_user", "new_user")
        )
    article_rows = _call(
        "article_summary", client.datacube.get_article_summary, args.begin_date, args.begin_date
    )
    if article_rows is not None:
        data["article_summary"] = wm.normalise_metric_rows(
            article_rows, day_fields=("int_page_read_count", "int_page_read_user")
        )

    if not endpoints_used:
        _emit({"state": "BLOCKED", "issues": issues})
        return 4
    receipt = wm.build_receipt(
        account_slug=args.account_slug or "",
        begin_date=args.begin_date,
        end_date=args.end_date,
        endpoints=endpoints_used,
        data=data,
        fetched_at=_stamp(),
        problems=issues or None,
    )
    target = _receipt_path(Path(args.project) if args.project else None, args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit({"state": "FETCHED" if not issues else "PARTIAL", "receipt": str(target), "issues": issues})
    return 0 if not issues else 5


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("preflight", "plan", "fetch"))
    parser.add_argument("--env", default=None, help="credential env file (KEY=VALUE lines)")
    parser.add_argument("--account", default=None, help="account DNA JSON (for account_slug in the receipt)")
    parser.add_argument("--account-slug", default=None)
    parser.add_argument("--begin-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--project", default=None, help="project directory (writes receipts/)")
    parser.add_argument("--out", default=None, help="receipt path override")
    parser.add_argument("--execute", action="store_true", help="allow the real network call")
    args = parser.parse_args(argv)
    _configure_stdio()

    if args.command == "preflight":
        return cmd_preflight(args)
    if args.command == "plan":
        if not (args.begin_date and args.end_date):
            raise SystemExit("BLOCKED: --begin-date and --end-date are required (YYYY-MM-DD)")
        return cmd_plan(args)
    if not (args.begin_date and args.end_date):
        raise SystemExit("BLOCKED: --begin-date and --end-date are required (YYYY-MM-DD)")
    if args.account and not args.account_slug:
        args.account_slug = load_account(Path(args.account)).get("slug", "")
    return cmd_fetch(args)


if __name__ == "__main__":
    raise SystemExit(main())
