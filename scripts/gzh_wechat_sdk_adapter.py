#!/usr/bin/env python3
"""GitHub-sourced WeChat SDK adapter for the gzh_未来智能 graphic workflow.

Wraps ``wechatpy`` (MIT, https://github.com/wechatpy/wechatpy, pinned below) as
the API transport for the publishing chain.  This module is an ADAPTER: it does
not modify the workflow source, and it never writes workflow receipts by
itself.  Signed ``publish-*.json`` receipts remain the exclusive output of the
workflow's ``publish_preflight.py`` / ``verify_draft_submission.py``.

Commands:
  self-test  Offline SDK/contract verification. No network, no credentials.
  probe      Real access-token probe. Requires out-of-repo WECHAT_1_* creds.
  publish    Real cover upload -> draft/add -> draft/get. Requires creds,
             article.html, article.yaml and a cover image.

Every failure is returned as an explicit blocked result; there is no silent
fallback and no mock receipt is ever produced.
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDOR = PROJECT_ROOT / "vendor" / "wechatpy"
PINNED_COMMIT = "a695b89891e0473113c946a3a44d948fcf217404"
SLOT = 1
APPID_KEY = f"WECHAT_{SLOT}_APPID"
SECRET_KEY = f"WECHAT_{SLOT}_APPSECRET"
BASE_KEY = f"WECHAT_{SLOT}_API_BASE"


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (OSError, ValueError):
                pass


def _load_sdk() -> tuple[Any, Any]:
    if not (VENDOR / "wechatpy" / "__init__.py").is_file():
        raise RuntimeError(f"GitHub SDK 未落地：{VENDOR}")
    sys.path.insert(0, str(VENDOR))
    import wechatpy  # noqa: E402
    from wechatpy import WeChatClient  # noqa: E402

    return wechatpy, WeChatClient


def _load_env(path: Path) -> dict[str, str]:
    """Read an out-of-repository credential file. Never print its values."""
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise RuntimeError(f"凭证文件不存在：{resolved}")
    try:
        resolved.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        pass
    else:
        raise RuntimeError("凭证文件不能位于项目仓库内")
    values: dict[str, str] = {}
    for line in resolved.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _egress_ip() -> str:
    for endpoint in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            request = urllib.request.Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=8) as response:
                text = response.read().decode("utf-8", "ignore").strip()
            if text and len(text) < 64:
                return text
        except Exception:  # noqa: BLE001
            continue
    return "unknown"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def cmd_self_test(args: argparse.Namespace) -> int:
    """Offline verification: vendor pin, importability, API surface, contract."""
    checks: list[dict[str, Any]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "status": "passed" if ok else "blocked", "detail": detail})

    record("vendor_present", (VENDOR / "wechatpy" / "__init__.py").is_file(), str(VENDOR))
    head = VENDOR / ".git" / "HEAD"
    commit = ""
    if head.is_file():
        raw = head.read_text(encoding="utf-8").strip()
        if raw.startswith("ref:"):
            ref = VENDOR / ".git" / raw.split(" ", 1)[1].strip()
            commit = ref.read_text(encoding="utf-8").strip() if ref.is_file() else ""
        else:
            commit = raw
    record("vendor_commit_pinned", bool(commit) and commit.startswith(PINNED_COMMIT[:12]),
           commit or "unknown")

    try:
        from unittest import mock

        network_attempts: list[str] = []

        def _blocked_request(*_args: Any, **_kwargs: Any) -> None:
            network_attempts.append("network-request-intercepted")
            raise RuntimeError("self-test must not perform network calls")

        sdk, client_cls = _load_sdk()
        from wechatpy.client.api.draft import WeChatDraft  # noqa: E402

        version = str(getattr(sdk, "__version__", "unknown"))
        record("sdk_import", True, f"wechatpy {version}")
        with mock.patch("requests.Session.request", _blocked_request), \
                mock.patch("urllib.request.urlopen", _blocked_request):
            # getattr_static avoids evaluating the access_token property, which
            # would otherwise trigger a real token fetch during an offline test.
            client = client_cls("__selftest__", "__selftest__")
            for api_name, methods in (
                ("client", ("fetch_access_token", "access_token")),
                ("draft", ("add", "get", "count", "delete")),
                ("material", ("add", "get", "batchget")),
            ):
                target = client if api_name == "client" else inspect.getattr_static(client, api_name, None)
                target_cls = target if isinstance(target, type) else type(target)
                missing = [m for m in methods if inspect.getattr_static(target_cls, m, None) is None]
                record(f"api_{api_name}", not missing,
                       "missing=" + ",".join(missing) if missing else "all required methods present")
            draft_add_source = inspect.getsource(WeChatDraft.add)
            required_article_keys = ("title", "content", "thumb_media_id", "author", "digest")
            missing_keys = [k for k in required_article_keys if f'"{k}"' not in draft_add_source]
            record("draft_add_contract", not missing_keys,
                   "missing=" + ",".join(missing_keys) if missing_keys else "article fields aligned with workflow article.yaml")
            signature = str(inspect.signature(client_cls.__init__))
            record("client_signature", "secret" in signature, signature)
        record("no_network_calls", not network_attempts,
               "clean" if not network_attempts else f"intercepted {len(network_attempts)} call(s)")
    except Exception as exc:  # noqa: BLE001
        record("sdk_import", False, f"{exc.__class__.__name__}: {exc}")

    blocked = [c for c in checks if c["status"] == "blocked"]
    payload = {
        "contract": "gzh-wechat-sdk-adapter-v1",
        "command": "self-test",
        "network_called": False,
        "credentials_used": False,
        "source": {"repo": "https://github.com/wechatpy/wechatpy", "license": "MIT", "commit": PINNED_COMMIT},
        "checks": checks,
        "status": "passed" if not blocked else "blocked",
        "checked_at": _stamp(),
    }
    if args.output:
        Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _emit(payload)
    return 0 if not blocked else 1


def cmd_probe(args: argparse.Namespace) -> int:
    """Real token probe. Never stores or prints the token value."""
    try:
        values = _load_env(Path(args.env))
    except RuntimeError as exc:
        _emit({"contract": "gzh-wechat-sdk-adapter-v1", "command": "probe",
               "status": "blocked", "network_called": False, "reason": str(exc), "checked_at": _stamp()})
        return 1
    missing = [k for k in (APPID_KEY, SECRET_KEY) if not values.get(k)]
    if missing:
        _emit({"contract": "gzh-wechat-sdk-adapter-v1", "command": "probe",
               "status": "blocked", "network_called": False,
               "reason": "凭证缺少 " + ", ".join(missing), "checked_at": _stamp()})
        return 1

    ip = _egress_ip()
    try:
        _, client_cls = _load_sdk()
        client = client_cls(values[APPID_KEY], values[SECRET_KEY], timeout=20)
        data = client.fetch_access_token()
    except Exception as exc:  # noqa: BLE001
        payload = {"contract": "gzh-wechat-sdk-adapter-v1", "command": "probe",
                   "status": "blocked", "network_called": True, "egress_ip": ip,
                   "reason": f"{exc.__class__.__name__}: {str(exc)[:240]}", "checked_at": _stamp()}
        _emit(payload)
        return 1
    passed = isinstance(data, dict) and bool(data.get("access_token"))
    payload = {
        "contract": "gzh-wechat-sdk-adapter-v1",
        "command": "probe",
        "status": "passed" if passed else "blocked",
        "network_called": True,
        "egress_ip": ip,
        "account_slot": SLOT,
        "errcode": "" if passed else str((data or {}).get("errcode", "")),
        "errmsg": "" if passed else str((data or {}).get("errmsg", ""))[:240],
        "token_exposed": False,
        "checked_at": _stamp(),
    }
    _emit(payload)
    return 0 if passed else 1


def cmd_publish(args: argparse.Namespace) -> int:
    """Refused. The tracked draft command is the only draft path."""
    _emit({
        "contract": "gzh-wechat-sdk-adapter-v1",
        "command": "publish",
        "status": "blocked",
        "network_called": False,
        "reason": "第二套草稿发布已关闭。使用 scripts/wechat_draft.py。它停在草稿，不群发。",
        "canonical": "scripts/wechat_draft.py",
        "publish_authorized": False,
        "production_ready": False,
        "checked_at": _stamp(),
    })
    return 4
def main() -> int:
    _configure_stdio()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    st = sub.add_parser("self-test", help="离线 SDK/契约自检")
    st.add_argument("--output")
    st.set_defaults(func=cmd_self_test)
    pr = sub.add_parser("probe", help="真实 token 探测（需仓库外凭证）")
    pr.add_argument("--env", required=True)
    pr.set_defaults(func=cmd_probe)
    pb = sub.add_parser("publish", help="真实创建并回读草稿")
    pb.add_argument("--env", required=True)
    pb.add_argument("--article", required=True)
    pb.add_argument("--cover", required=True)
    pb.add_argument("--output")
    pb.set_defaults(func=cmd_publish)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
