#!/usr/bin/env python3
"""Fail-closed resolver for the repository skill registry.

The resolver is deliberately small and side-effect free.  It resolves a
canonical key or alias, rejects deprecated entries, verifies the path remains
inside the repository, and exposes the declared entrypoint/contract to
runtime callers.  It does not infer paths from slugs.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "skills" / "skill-registry.yaml"
ACTIVE_SECTIONS = ("canonical", "supporting", "optional_capabilities", "post_publish_adapters", "runtime_scripts")


@dataclass(frozen=True)
class ResolvedSkill:
    key: str
    section: str
    path: Path
    entrypoint: Path
    metadata: dict[str, Any]


class RegistryError(ValueError):
    pass


def load_registry(path: Path = REGISTRY) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RegistryError("PyYAML 不可用，无法解析 skill-registry.yaml") from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError(f"注册表无法解析：{path}") from exc
    if not isinstance(data, dict) or data.get("version") != 2:
        raise RegistryError("skill-registry.yaml 必须使用 version=2")
    schema = data.get("schema")
    if not isinstance(schema, dict) or schema.get("contract") != "skill-registry-v2":
        raise RegistryError("skill-registry.yaml 缺少 schema.contract=skill-registry-v2")
    return data


def _all_entries(data: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for section in ACTIVE_SECTIONS:
        block = data.get(section, {})
        if not isinstance(block, dict):
            raise RegistryError(f"registry section {section} 必须是对象")
        for key, value in block.items():
            if not isinstance(value, dict):
                raise RegistryError(f"registry entry {section}.{key} 必须是对象")
            entries.append((section, str(key), value))
    return entries


def _entry_aliases(key: str, meta: dict[str, Any]) -> set[str]:
    raw = meta.get("aliases", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise RegistryError(f"registry entry {key} aliases 必须是列表")
    return {key, *(str(item).strip() for item in raw if str(item).strip())}


def _safe_path(raw: str) -> Path:
    candidate = (ROOT / raw).resolve()
    try:
        candidate.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise RegistryError(f"registry path 越界：{raw}") from exc
    if not candidate.exists():
        raise RegistryError(f"registry path 不存在：{raw}")
    return candidate


def resolve(name: str, *, section: str | None = None, data: dict[str, Any] | None = None) -> ResolvedSkill:
    registry = data if data is not None else load_registry()
    wanted = str(name or "").strip()
    if not wanted:
        raise RegistryError("缺少 registry key/alias")
    deprecated = registry.get("deprecated", {})
    if isinstance(deprecated, dict) and wanted in deprecated:
        raise RegistryError(f"deprecated 条目不可 dispatch：{wanted}")
    matches: list[tuple[str, str, dict[str, Any]]] = []
    for current_section, key, meta in _all_entries(registry):
        if section and current_section != section:
            continue
        if wanted in _entry_aliases(key, meta):
            matches.append((current_section, key, meta))
    if len(matches) != 1:
        raise RegistryError(f"registry key/alias 不唯一或不存在：{wanted}（matches={len(matches)}）")
    current_section, key, meta = matches[0]
    if str(meta.get("execution_status", "active")).strip().lower() in {"deprecated", "deferred", "disabled"}:
        raise RegistryError(f"registry 条目不可 dispatch：{key}")
    raw_path = str(meta.get("path") or "").strip()
    if not raw_path:
        raise RegistryError(f"registry 条目缺少 path：{current_section}.{key}")
    path = _safe_path(raw_path)
    raw_entrypoint = str(meta.get("entrypoint") or raw_path).strip()
    entrypoint = _safe_path(raw_entrypoint)
    return ResolvedSkill(key=key, section=current_section, path=path, entrypoint=entrypoint, metadata=dict(meta))


def validate(path: Path = REGISTRY) -> list[str]:
    try:
        data = load_registry(path)
        entries = _all_entries(data)
    except RegistryError as exc:
        return [str(exc)]
    errors: list[str] = []
    aliases: dict[str, str] = {}
    for section, key, meta in entries:
        raw_path = str(meta.get("path") or "").strip()
        if not raw_path:
            errors.append(f"{section}.{key}: 缺少 path")
        else:
            try:
                _safe_path(raw_path)
            except RegistryError as exc:
                errors.append(f"{section}.{key}: {exc}")
        # Legacy skill/adapter records remain resolvable for compatibility;
        # executable runtime_scripts must satisfy the full v2 contract.
        if section == "runtime_scripts":
            for field in ("kind", "path", "entrypoint", "stage", "inputs", "outputs", "execution_status"):
                if field not in meta:
                    errors.append(f"{section}.{key}: 缺少 runtime field {field}")
            raw_entrypoint = str(meta.get("entrypoint") or "").strip()
            if raw_entrypoint:
                try:
                    entrypoint = _safe_path(raw_entrypoint)
                    if not entrypoint.is_file():
                        errors.append(f"{section}.{key}: entrypoint 必须是文件：{raw_entrypoint}")
                except RegistryError as exc:
                    errors.append(f"{section}.{key}: {exc}")
        try:
            entry_aliases = _entry_aliases(key, meta)
        except RegistryError as exc:
            errors.append(f"{section}.{key}: {exc}")
            continue
        for alias in entry_aliases:
            previous = aliases.get(alias)
            if previous and previous != f"{section}.{key}":
                errors.append(f"alias collision: {alias} -> {previous}, {section}.{key}")
            aliases[alias] = f"{section}.{key}"
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "resolve"))
    parser.add_argument("name", nargs="?")
    parser.add_argument("--section")
    args = parser.parse_args()
    if args.command == "validate":
        errors = validate()
        if errors:
            print("SKILL REGISTRY BLOCKED")
            for error in errors:
                print(f"- {error}")
            return 1
        print("SKILL REGISTRY VALIDATED")
        return 0
    try:
        item = resolve(args.name or "", section=args.section)
    except RegistryError as exc:
        print(f"SKILL RESOLVE BLOCKED: {exc}")
        return 1
    print(f"SKILL RESOLVED: {item.key} [{item.section}] -> {item.entrypoint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
