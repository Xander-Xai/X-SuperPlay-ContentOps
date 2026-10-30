#!/usr/bin/env python3
"""
校验 `.aws-article/config.yaml` 与仓库外层项目目录 `aws.env` 中的配置是否完整。

写作由当前 Agent 完成，不再调用外部写作模型，也不再读取写作模型 Key。

图片模型固定为 Agnes Image 2.1 Flash：
  - config.yaml → image_model：固定 provider/base_url/model
  - aws.env → AGNES_API_KEY

微信公众号（阻断级；**例外**：`config.yaml` 顶层 **`publish_method: none`** 时跳过本组）：
  - config.yaml：wechat_accounts（≥1）、wechat_api_base、wechat_{i}_name（i=1..N）
  - aws.env：WECHAT_{i}_APPID、WECHAT_{i}_APPSECRET

用法（仓库根）：
    python skills/gzh-article-orchestrator/scripts/validate_env.py
    python skills/gzh-article-orchestrator/scripts/validate_env.py
    python skills/gzh-article-orchestrator/scripts/validate_env.py --config .aws-article/config.yaml --env ../aws.env
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _parse_dotenv(content: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def _nonempty_str(val: object) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return True
    return False


def _parse_wechat_accounts(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return None
        try:
            n = int(s)
            return n if n >= 1 else None
        except ValueError:
            return None
    return None


def _image_ok(cfg: dict, env: dict[str, str]) -> bool:
    im = cfg.get("image_model")
    if not isinstance(im, dict):
        return False
    if not all(_nonempty_str(im.get(k)) for k in ("base_url", "model")):
        return False
    provider = str(im.get("provider") or "").strip().lower()
    base_url = str(im.get("base_url") or "").strip().rstrip("/")
    model = str(im.get("model") or "").strip()
    if provider != "agnes" or base_url != "https://apihub.agnes-ai.com/v1/images/generations" or model != "agnes-image-2.1-flash":
        return False
    if not _nonempty_str(env.get("AGNES_API_KEY")):
        return False
    return True


def _wechat_ok(cfg: dict, env: dict[str, str]) -> bool:
    n = _parse_wechat_accounts(cfg.get("wechat_accounts"))
    if n is None:
        return False
    if not _nonempty_str(cfg.get("wechat_api_base")):
        return False
    try:
        selected = int(cfg.get("wechat_publish_slot") or 1)
    except (TypeError, ValueError):
        return False
    if selected < 1 or selected > n:
        return False
    if not _nonempty_str(cfg.get(f"wechat_{selected}_name")):
        return False
    if not _nonempty_str(env.get(f"WECHAT_{selected}_APPID")):
        return False
    if not _nonempty_str(env.get(f"WECHAT_{selected}_APPSECRET")):
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验 config.yaml 与 aws.env 中的模型与微信配置"
    )
    project_env = Path(__file__).resolve().parents[4] / "aws.env"
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(".aws-article") / "config.yaml",
        help="默认 .aws-article/config.yaml",
    )
    parser.add_argument(
        "--env",
        type=Path,
        default=Path(os.environ.get("WECHAT_ENV_PATH") or project_env),
        help="默认读取 WECHAT_ENV_PATH，否则为仓库外层项目目录 aws.env",
    )
    args = parser.parse_args()
    config_path: Path = args.config
    env_path: Path = args.env

    if not config_path.is_file():
        print("failed", file=sys.stdout)
        print(f"未找到配置文件: {config_path.resolve()}", file=sys.stdout)
        return 1

    if not env_path.is_file():
        print("failed", file=sys.stdout)
        print(f"未找到环境文件: {env_path.resolve()}", file=sys.stdout)
        return 1

    try:
        import yaml
    except ImportError:
        print("failed", file=sys.stdout)
        print("需要 PyYAML：pip install pyyaml", file=sys.stdout)
        return 1

    try:
        cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as e:
        print("failed", file=sys.stdout)
        print(f"无法读取 config.yaml: {e}", file=sys.stdout)
        return 1
    except yaml.YAMLError as e:
        print("failed", file=sys.stdout)
        print(f"config.yaml 解析失败: {e}", file=sys.stdout)
        return 1

    if not isinstance(cfg, dict):
        print("failed", file=sys.stdout)
        print("config.yaml 须为 YAML 键值对象（映射）", file=sys.stdout)
        return 1

    try:
        env_map = _parse_dotenv(env_path.read_text(encoding="utf-8"))
    except OSError as e:
        print("failed", file=sys.stdout)
        print(f"无法读取 aws.env: {e}", file=sys.stdout)
        return 1

    bad: list[str] = []
    warnings: list[str] = []

    if not _image_ok(cfg, env_map):
        bad.append("Agnes Image 2.1 Flash 图片模型配置不完整")

    pm = str(cfg.get("publish_method") or "").strip().lower()
    skip_wechat = pm == "none"
    if not skip_wechat and not _wechat_ok(cfg, env_map):
        bad.append("微信公众号配置不完整")

    if bad:
        print("failed", file=sys.stdout)
        for line in bad:
            print(line, file=sys.stdout)
        for line in warnings:
            print(line, file=sys.stdout)
        return 1

    print("True", file=sys.stdout)
    if warnings:
        print(f"配置校验通过（{'；'.join(warnings)}）", file=sys.stdout)
    else:
        print("配置校验通过", file=sys.stdout)
    if skip_wechat:
        print(
            "（已跳过微信公众号校验：publish_method 为 none）",
            file=sys.stdout,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
