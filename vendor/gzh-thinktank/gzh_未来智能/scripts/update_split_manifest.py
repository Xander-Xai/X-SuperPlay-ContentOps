#!/usr/bin/env python3
"""Compatibility entry point for refreshing the clean-room manifest."""
from __future__ import annotations

from workspace_hygiene import main


if __name__ == "__main__":
    raise SystemExit(main())
