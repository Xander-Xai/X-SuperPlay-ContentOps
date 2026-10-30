#!/usr/bin/env python3
"""Agnes Image 2.1 Flash 公众号配图适配器。

所有需要外部模型的生图调用都统一走 Agnes Image 2.1 Flash；架构图、流程图和代码图
仍由上游视觉导演选择 Mermaid/SVG/HTML 等可编辑降级方案。该脚本只读取仓库外环境
中的 ``AGNES_API_KEY``，绝不读取、记录或打印密钥值。
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import mimetypes
import os
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml


ENDPOINT = "https://apihub.agnes-ai.com/v1/images/generations"
MODEL = "agnes-image-2.1-flash"
ASPECT_TO_SIZE = {
    "1:1": "1024x1024",
    "16:9": "1792x1024",
    "9:16": "1024x1792",
    "2.35:1": "1792x1024",
    "4:3": "1024x768",
    "3:4": "768x1024",
}


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass


_configure_stdio()


def _err(message: str, code: int = 1) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)
    raise SystemExit(code)


def _info(message: str) -> None:
    print(f"[INFO] {message}")


def _ok(message: str) -> None:
    print(f"[OK] {message}")


def _resolve_env_path() -> Path:
    raw = (os.environ.get("WECHAT_ENV_PATH") or os.environ.get("GZH_ENV_PATH") or "").strip()
    return Path(raw).expanduser() if raw else Path("aws.env")


def _parse_dotenv(content: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _load_env_map() -> dict[str, str]:
    values: dict[str, str] = {}
    path = _resolve_env_path()
    if path.is_file():
        try:
            values.update(_parse_dotenv(path.read_text(encoding="utf-8")))
        except OSError:
            pass
    if not values.get("AGNES_API_KEY") and os.environ.get("AGNES_API_KEY"):
        values["AGNES_API_KEY"] = os.environ["AGNES_API_KEY"]
    return values


def _load_config_yaml() -> dict | None:
    path = Path(".aws-article/config.yaml")
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _err(f"无法读取 .aws-article/config.yaml: {exc}")
    if data is None:
        return {}
    if not isinstance(data, dict):
        _err(".aws-article/config.yaml 须为 YAML 对象")
    return data


def _model_config_from_config_and_env(cfg: dict | None, env: dict[str, str]) -> dict | None:
    if not isinstance(cfg, dict) or not isinstance(cfg.get("image_model"), dict):
        return None
    image = cfg["image_model"]
    provider = str(image.get("provider") or "").strip().lower()
    endpoint = str(image.get("base_url") or "").strip().rstrip("/")
    model = str(image.get("model") or "").strip()
    key = str(env.get("AGNES_API_KEY") or "").strip()
    if provider != "agnes" or endpoint != ENDPOINT or model != MODEL or not key:
        return None
    return {
        "provider": provider,
        "base_url": endpoint,
        "model": model,
        "api_key": key,
        "default_size": str(image.get("default_size") or "2K").strip(),
        "default_quality": str(image.get("default_quality") or "high").strip(),
    }


def _resolve_model_config() -> dict | None:
    config = _model_config_from_config_and_env(_load_config_yaml(), _load_env_map())
    if config:
        _info("图片模型已解析（Agnes Image 2.1 Flash；密钥来自外部环境）")
    return config


def _detect_api_type(model_cfg: dict) -> str:
    """保持旧版测试接口，但只允许 Agnes。"""
    if (
        str(model_cfg.get("provider") or "").strip().lower() != "agnes"
        or str(model_cfg.get("base_url") or "").strip().rstrip("/") != ENDPOINT
        or str(model_cfg.get("model") or "").strip() != MODEL
    ):
        _err("图片模型已统一为 Agnes Image 2.1 Flash；请检查 image_model 配置。")
    return "agnes"


def _safe_download_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _err("模型返回的图片 URL 不是安全的 HTTP(S) 地址")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parsed.hostname, None)}
    except OSError as exc:
        _err(f"无法解析模型返回的图片地址: {exc}")
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            _err("模型返回的图片地址包含无效 IP")
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            _err("拒绝下载模型返回的内网或保留地址")


def _result_bytes(payload: dict) -> bytes:
    items = payload.get("data") or []
    if not items or not isinstance(items[0], dict):
        _err("Agnes API 未返回图片数据")
    first = items[0]
    encoded = first.get("b64_json")
    if encoded:
        try:
            return base64.b64decode(encoded)
        except (ValueError, TypeError):
            _err("Agnes API 返回的 b64_json 无法解析")
    url = str(first.get("url") or "")
    if url:
        _safe_download_url(url)
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return response.read()
        except urllib.error.URLError as exc:
            _err(f"下载 Agnes 图片失败: {exc}")
    _err("Agnes API 返回内容不含 b64_json 或 url")


def _generate_image_openai_compatible(
    model_cfg: dict,
    prompt: str,
    size: str | None = None,
    quality: str | None = None,
    api_type: str = "agnes",
    ratio: str | None = None,
    reference_images: list[str] | None = None,
) -> bytes:
    """向 Agnes Image 2.1 Flash 发送请求；保留旧函数名供离线测试使用。"""
    _detect_api_type(model_cfg)
    body: dict = {
        "model": MODEL,
        "prompt": prompt,
        "size": size or model_cfg.get("default_size") or "2K",
        "extra_body": {"response_format": "b64_json"},
    }
    if ratio:
        body["ratio"] = ratio
    if reference_images:
        body["extra_body"]["image"] = reference_images
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {model_cfg['api_key']}",
        },
    )
    _info(f"调用模型: {MODEL} @ Agnes Image 2.1 Flash")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code in {401, 403}:
            _err("Agnes 认证失败，请检查外部环境中的 AGNES_API_KEY 和生图权限")
        _err(f"Agnes API 调用失败（HTTP {exc.code}）: {detail}")
    except urllib.error.URLError as exc:
        _err(f"连接 Agnes API 失败（可重试）: {exc.reason}")
    return _result_bytes(result)


def generate_image(model_cfg: dict, prompt: str, size: str | None = None,
                   quality: str | None = None, ratio: str | None = None,
                   reference_images: list[str] | None = None) -> bytes:
    return _generate_image_openai_compatible(model_cfg, prompt, size, quality, "agnes", ratio, reference_images)


def _read_prompt_file(path: Path) -> tuple[str, dict]:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            metadata = yaml.safe_load(parts[1]) or {}
            return parts[2].strip(), metadata if isinstance(metadata, dict) else {}
    return text.strip(), {}


def _reference_image_values(raw_values: object, prompt_path: Path) -> list[str]:
    if not isinstance(raw_values, list):
        return []
    result: list[str] = []
    for raw in raw_values:
        value = str(raw or "").strip()
        if not value:
            continue
        if value.startswith("data:image/") or value.startswith("https://"):
            result.append(value)
            continue
        path = Path(value)
        if not path.is_absolute():
            path = (prompt_path.parent / path).resolve()
        if not path.is_file():
            _err(f"参考图不存在: {value}")
        mime = mimetypes.guess_type(path.name)[0] or "image/png"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        result.append(f"data:{mime};base64,{encoded}")
    return result


def _prompt_size(value: object) -> str | None:
    raw = str(value or "").strip()
    return ASPECT_TO_SIZE.get(raw, raw) if raw else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agnes Image 2.1 Flash 公众号配图适配器")
    sub = parser.add_subparsers(dest="command")
    generate = sub.add_parser("generate", help="从 prompt 文件生成一张图")
    generate.add_argument("prompt_file", type=Path)
    generate.add_argument("-o", "--output", type=Path)
    generate.add_argument("--size")
    generate.add_argument("--ratio")
    generate.add_argument("--quality")
    batch = sub.add_parser("batch", help="批量生成 prompt 目录中的图片")
    batch.add_argument("prompts_dir", type=Path)
    batch.add_argument("-o", "--output-dir", type=Path)
    batch.add_argument("--size")
    batch.add_argument("--quality")
    sub.add_parser("test", help="测试 Agnes API")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    config = _resolve_model_config()
    if config is None:
        print("[NO_MODEL] Agnes Image 2.1 Flash 未配置（image_model 或 AGNES_API_KEY 缺失）。", file=sys.stderr)
        return 2
    if args.command == "test":
        data = generate_image(config, "a simple blue circle on a white background", size="1024x1024")
        _ok(f"Agnes API 连通正常，收到 {len(data)} 字节图片数据")
        return 0
    if args.command == "generate":
        if not args.prompt_file.is_file():
            _err(f"prompt 文件不存在: {args.prompt_file}")
        prompt, metadata = _read_prompt_file(args.prompt_file)
        size = _prompt_size(args.size or metadata.get("size") or metadata.get("aspect"))
        refs = _reference_image_values(metadata.get("reference_images"), args.prompt_file)
        data = generate_image(config, prompt, size=size, quality=args.quality or metadata.get("quality"),
                              ratio=args.ratio or metadata.get("ratio"), reference_images=refs)
        output = args.output or args.prompt_file.with_suffix(".png")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(data)
        _ok(f"已生成: {output}")
        return 0
    prompt_files = sorted(p for p in args.prompts_dir.glob("*.md") if p.is_file())
    output_dir = args.output_dir or args.prompts_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for prompt_path in prompt_files:
        try:
            prompt, metadata = _read_prompt_file(prompt_path)
            data = generate_image(config, prompt, size=_prompt_size(args.size or metadata.get("size") or metadata.get("aspect")),
                                  quality=args.quality or metadata.get("quality"), ratio=metadata.get("ratio"),
                                  reference_images=_reference_image_values(metadata.get("reference_images"), prompt_path))
            output = output_dir / f"{prompt_path.stem}.png"
            output.write_bytes(data)
            _ok(f"已生成: {output}")
        except SystemExit:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
