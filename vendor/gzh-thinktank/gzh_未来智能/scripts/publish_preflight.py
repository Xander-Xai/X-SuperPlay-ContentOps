#!/usr/bin/env python3
"""Record a credential/permission preflight without exposing secret values."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from receipt_integrity import ROOT as WORKFLOW_ROOT, external_key_path, stamp


ROOT = Path(__file__).resolve().parents[1]


def _yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore

        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, ValueError):
        return {}


def _env_names(path: Path) -> set[str]:
    return {
        match.group(1)
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if (match := re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", line.strip()))
    }


def _env_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _probe_token(config: dict, values: dict[str, str], slot: int) -> dict[str, str]:
    appid = values.get(f"WECHAT_{slot}_APPID", "").strip()
    secret = values.get(f"WECHAT_{slot}_APPSECRET", "").strip()
    base = values.get(f"WECHAT_{slot}_API_BASE", "").strip() or str(
        config.get("wechat_api_base") or "https://api.weixin.qq.com"
    ).strip()
    base = base.rstrip("/")
    if base.endswith("/cgi-bin"):
        base = base[:-8].rstrip("/")
    url = f"{base}/cgi-bin/token?" + urllib.parse.urlencode({
        "grant_type": "client_credential",
        "appid": appid,
        "secret": secret,
    })
    try:
        request = urllib.request.Request(url)
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read())
    except Exception as exc:  # noqa: BLE001
        return {"status": "blocked", "error": f"network: {exc.__class__.__name__}"}
    if data.get("access_token"):
        return {"status": "passed", "api_base": base}
    return {
        "status": "blocked",
        "errcode": str(data.get("errcode", "")),
        "errmsg": str(data.get("errmsg", ""))[:240],
    }


def _current_public_ip() -> str:
    """Best-effort lookup of the machine's public egress IP (for IP whitelist)."""
    for endpoint in (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
        "https://ip.cn/api/index?type=0",
    ):
        try:
            request = urllib.request.Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=8) as response:
                text = response.read().decode("utf-8", "ignore").strip()
            if not text:
                continue
            try:
                obj = json.loads(text)
                if isinstance(obj, dict) and obj.get("ip"):
                    return str(obj["ip"]).strip()
            except Exception:
                pass
            return text[:64]
        except Exception:
            continue
    return "unknown"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--env", type=Path, help="仓库外凭证文件；只读取变量名")
    parser.add_argument("--account-slot", type=int, help="微信凭证槽位；默认读取 config.yaml")
    parser.add_argument("--approve", action="store_true", help="写入 passed 预检回执")
    parser.add_argument("--draft-permission-confirmed", action="store_true")
    parser.add_argument("--ip-whitelist-confirmed", action="store_true")
    parser.add_argument("--probe", action="store_true", help="实际调用 token 接口验证凭证/IP 白名单；不保存 token")
    parser.add_argument("--operator", default="human-review")
    args = parser.parse_args()

    article_dir = args.article.expanduser().resolve()
    config = _yaml(ROOT / ".aws-article" / "config.yaml")
    slot = args.account_slot or int(config.get("wechat_publish_slot", 1) or 1)
    env_value = args.env or (Path(os.environ["WECHAT_ENV_PATH"]) if os.environ.get("WECHAT_ENV_PATH") else None)
    errors: list[str] = []
    names: set[str] = set()
    values: dict[str, str] = {}
    if env_value is not None:
        try:
            env_value = env_value.expanduser().resolve()
            env_value.relative_to(WORKFLOW_ROOT.resolve())
            errors.append("凭证文件必须位于仓库外；禁止使用仓库内 aws.env/.env")
        except ValueError:
            pass
    if env_value is None or not env_value.is_file():
        errors.append("缺少 --env/WECHAT_ENV_PATH 凭证文件")
    else:
        names = _env_names(env_value)
        values = _env_values(env_value)
        for suffix in ("APPID", "APPSECRET"):
            if f"WECHAT_{slot}_{suffix}" not in names:
                errors.append(f"凭证文件缺少 WECHAT_{slot}_{suffix}")
    if args.approve and not args.draft_permission_confirmed:
        errors.append("--approve 必须同时确认 --draft-permission-confirmed")
    if args.approve and not args.ip_whitelist_confirmed:
        errors.append("--approve 必须同时确认 --ip-whitelist-confirmed")
    state_path = article_dir / "matrix-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        state = {}
    try:
        structured_workspace = int(state.get("schema_version", 0) or 0) >= 3
    except (TypeError, ValueError):
        structured_workspace = False
    if args.approve and structured_workspace and not args.probe and os.environ.get("WORKFLOW_TEST_MODE") != "1":
        errors.append("schema v3+ 工作区使用 --approve 时必须同时使用 --probe 完成实际 token 探测")

    probe: dict[str, str] = {"status": "not_requested"}
    if args.probe and not errors:
        probe = _probe_token(config, values, slot)
        if probe.get("status") != "passed":
            detail = str(probe.get("errcode") or probe.get("error") or probe.get("errmsg") or "unknown")
            errmsg = probe.get("errmsg") or ""
            hint = ""
            if detail == "40164":
                ip = _current_public_ip()
                hint = (
                    f" —— IP白名单错误：请到公众号后台「设置与开发 → 基本配置 → IP白名单」"
                    f"添加本机出口IP {ip}，再重跑"
                )
            errors.append("微信 token 探测未通过：" + detail + (f" {errmsg}" if errmsg else "") + hint)

    if args.approve and os.environ.get("WORKFLOW_TEST_MODE") != "1":
        if os.environ.get("WORKFLOW_RECEIPT_SIGNING_KEY", "").strip():
            errors.append("生产预检禁止使用 WORKFLOW_RECEIPT_SIGNING_KEY；请改用仓库外 WORKFLOW_RECEIPT_SIGNING_KEY_PATH")
        if external_key_path() is None:
            errors.append(
                "缺少外部回执签名密钥；请设置 WORKFLOW_RECEIPT_SIGNING_KEY_PATH，"
                "或在 D:\\Projects\\workflow-receipt-signing.key 放置至少32字节密钥"
            )

    payload = {
        "schema_version": 1,
        "status": "passed" if args.approve and not errors else "pending",
        "account_slot": slot,
        "appid_key": f"WECHAT_{slot}_APPID",
        "appsecret_key": f"WECHAT_{slot}_APPSECRET",
        "draft_permission": bool(args.draft_permission_confirmed),
        "ip_whitelist_checked": bool(args.ip_whitelist_confirmed),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "operator": args.operator.strip() or "human-review",
        "credential_names_found": sorted(name for name in names if name.startswith(f"WECHAT_{slot}_")),
        "errors": errors,
        "probe": probe,
    }
    payload = stamp(
        payload,
        article_dir,
        receipt_kind="publish-preflight",
        account_slot=slot,
        env_path=env_value if env_value and env_value.is_file() else None,
    )
    article_dir.mkdir(parents=True, exist_ok=True)
    (article_dir / "publish-preflight.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if errors or not args.approve:
        print("PUBLISH PREFLIGHT BLOCKED")
        for error in errors or ["未使用 --approve；权限和 IP 白名单仍未确认"]:
            print(f"- {error}")
        return 1
    print("PUBLISH PREFLIGHT PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
