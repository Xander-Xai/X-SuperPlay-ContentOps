#!/usr/bin/env python3
"""Create the local workflow receipt trust root outside the repositories."""

from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT.parent.parent / "workflow-receipt-signing.key"


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an external HMAC key for production receipts")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    target = args.path.expanduser().resolve()
    try:
        target.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise SystemExit("拒绝：签名密钥必须位于工作流仓库之外")
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(str(target), flags, 0o600)
    except FileExistsError:
        raise SystemExit(f"签名密钥已存在，未覆盖：{target}")
    with os.fdopen(fd, "wb") as handle:
        handle.write(secrets.token_bytes(32))
    print(f"RECEIPT SIGNING KEY CREATED: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
