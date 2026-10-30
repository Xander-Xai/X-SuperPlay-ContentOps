#!/usr/bin/env python3
"""Offline regression tests for the Agnes image-provider adapter."""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMAGE_CREATE = ROOT / "skills" / "gzh-visual-assets" / "scripts" / "image_create.py"


def load_module():
    spec = importlib.util.spec_from_file_location("gzh_image_create", IMAGE_CREATE)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载图片生成模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps({"data": [{"b64_json": base64.b64encode(b"fake-png").decode()}]}).encode()


def main() -> int:
    module = load_module()
    cfg = {
        "image_model": {
            "provider": "agnes",
            "base_url": "https://apihub.agnes-ai.com/v1/images/generations",
            "model": "agnes-image-2.1-flash",
            "default_size": "1024x768",
        }
    }
    resolved = module._model_config_from_config_and_env(cfg, {"AGNES_API_KEY": "test-key"})
    assert resolved and resolved["api_key"] == "test-key"
    assert module._detect_api_type(resolved) == "agnes"

    captured = {}
    original = module.urllib.request.urlopen

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["authorization"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return FakeResponse()

    module.urllib.request.urlopen = fake_urlopen
    try:
        output = module._generate_image_openai_compatible(
            resolved, "an abstract AI architecture diagram", "1024x768", "high", "agnes"
        )
    finally:
        module.urllib.request.urlopen = original

    assert output == b"fake-png"
    assert captured["url"].endswith("/v1/images/generations")
    assert captured["authorization"] == "Bearer test-key"
    assert captured["body"] == {
        "model": "agnes-image-2.1-flash",
        "prompt": "an abstract AI architecture diagram",
        "size": "1024x768",
        "extra_body": {"response_format": "b64_json"},
    }
    module.urllib.request.urlopen = fake_urlopen
    try:
        output = module._generate_image_openai_compatible(
            resolved,
            "preserve the reference composition and add a soft editorial light",
            "1K",
            "high",
            "agnes",
            "4:3",
            ["data:image/png;base64,ZmFrZQ=="],
        )
    finally:
        module.urllib.request.urlopen = original
    assert output == b"fake-png"
    assert captured["body"]["size"] == "1K"
    assert captured["body"]["ratio"] == "4:3"
    assert captured["body"]["extra_body"]["response_format"] == "b64_json"
    assert captured["body"]["extra_body"]["image"] == ["data:image/png;base64,ZmFrZQ=="]
    assert captured["timeout"] == 120
    print("AGNES IMAGE PROVIDER TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
