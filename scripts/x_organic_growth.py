#!/usr/bin/env python3
"""Run offline advisory checks on an explicitly supplied JSON file."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from contentops.x_organic_growth import process  # noqa: E402


def safe_input_path(path):
    """Accept only explicit JSON fixtures or project source data, not links or secrets."""
    path = Path(path)
    if ".." in path.parts or path.suffix.lower() != ".json":
        return False
    if any(part.lower().startswith((".", "auth", "secret", "credential", "token", "key")) for part in path.parts if part not in (".", "..")):
        return False
    try:
        absolute = path.absolute()
        resolved = absolute.resolve()
        if absolute != resolved or any(p.is_symlink() for p in (absolute, *absolute.parents)):
            return False
        relative = resolved.relative_to(ROOT.resolve())
    except (OSError, ValueError, RuntimeError):
        return False
    parts = relative.parts
    return (len(parts) >= 3 and parts[:2] == ("tests", "fixtures")) or (
        len(parts) >= 4 and parts[0] == "projects" and parts[2] == "sources"
    )


def make_receipt(raw, result):
    return {"schema": "contentops.x-organic-growth-receipt/v1",
            "input_sha256": hashlib.sha256(raw).hexdigest() if raw and result.get("status") != "BLOCKED" else None,
            "status": result["status"], "external_action": "none",
            "network_used": False, "human_review_required": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="local JSON request; no credentials or private data")
    args = parser.parse_args()
    try:
        if not safe_input_path(args.input):
            raise ValueError("unsafe input path")
        raw = args.input.read_bytes()
        data = json.loads(raw.decode("utf-8"))
        result = process(data)
    except (OSError, UnicodeError, ValueError):
        result = {"schema": "contentops.x-organic-growth/v1", "status": "BLOCKED",
                  "reasons": ["INPUT_UNAVAILABLE_OR_INVALID"], "network_used": False,
                  "external_action": "none", "execution_authorized": False,
                  "requires_human_review": True}
        raw = b""
    result["receipt"] = make_receipt(raw, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    sys.exit(main())
