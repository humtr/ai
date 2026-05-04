#!/usr/bin/env python3
"""Small registry helper for the ai wrapper.

This module intentionally uses only the Python standard library so it can run
inside Termux without extra packages.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", str(Path.home())))
AI_HOME = Path(os.environ.get("AI_HOME", str(HOME / ".ai")))
ACCOUNTS_FILE = AI_HOME / "accounts.json"
WORKDIRS_FILE = AI_HOME / "workdirs.json"
GATEWAYS_FILE = AI_HOME / "gateways.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def existing_provider_profiles(provider: str) -> list[str]:
    if provider == "codex":
        root = HOME / ".codex-homes"
    elif provider == "gemini":
        root = HOME / ".gemini-homes"
    elif provider == "hermes":
        root = HOME / ".hermes" / "profiles"
    else:
        return []
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def default_accounts() -> dict[str, Any]:
    accounts: list[dict[str, Any]] = [
        {
            "id": "default",
            "label": "native default",
            "aliases": ["native"],
            "native": True,
            "hidden": False,
            "provider_profiles": {
                "codex": "default",
                "gemini": "default",
                "hermes": "default",
            },
        }
    ]

    # Keep ambiguous historic names out of the default launch cycle. They remain
    # discoverable under provider profiles.
    hidden_names = {"main", "lab", "pro", "free", "tg", "codex-tg", "gemini-tg"}
    for provider in ("codex", "gemini", "hermes"):
        for name in existing_provider_profiles(provider):
            if name in hidden_names:
                continue
            found = next((a for a in accounts if a["id"] == name), None)
            if found is None:
                found = {
                    "id": name,
                    "label": name,
                    "aliases": [],
                    "native": False,
                    "hidden": False,
                    "provider_profiles": {},
                }
                accounts.append(found)
            found["provider_profiles"][provider] = name

    return {"version": 1, "accounts": accounts}


def default_workdirs() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    work_root = HOME / "work"
    if work_root.is_dir():
        for path in sorted(work_root.iterdir()):
            if path.is_dir():
                items.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "purpose": "",
                        "favorite": path.name in {"main", "test"},
                        "archived": False,
                    }
                )
    return {"version": 1, "workdirs": items}


def default_gateways() -> dict[str, Any]:
    return {
        "version": 1,
        "gateways": [
            {
                "id": "codex-tg",
                "kind": "telegram-gateway",
                "hermes_profile": "codex-tg",
                "bridge": None,
                "hidden": False,
            },
            {
                "id": "gemini-tg",
                "kind": "telegram-gateway",
                "hermes_profile": "gemini-tg",
                "bridge": "gemini-bridge",
                "hidden": False,
            },
            {
                "id": "gemini-bridge",
                "kind": "openai-compatible-bridge",
                "command": "hgb",
                "hidden": False,
            },
        ],
    }


def ensure_registry() -> None:
    if not ACCOUNTS_FILE.exists():
        write_json(ACCOUNTS_FILE, default_accounts())
    if not WORKDIRS_FILE.exists():
        write_json(WORKDIRS_FILE, default_workdirs())
    if not GATEWAYS_FILE.exists():
        write_json(GATEWAYS_FILE, default_gateways())


def load_accounts() -> dict[str, Any]:
    ensure_registry()
    data = read_json(ACCOUNTS_FILE, default_accounts())
    data.setdefault("version", 1)
    data.setdefault("accounts", [])
    return data


def save_accounts(data: dict[str, Any]) -> None:
    write_json(ACCOUNTS_FILE, data)


def load_workdirs() -> dict[str, Any]:
    ensure_registry()
    data = read_json(WORKDIRS_FILE, default_workdirs())
    data.setdefault("version", 1)
    data.setdefault("workdirs", [])
    return data


def save_workdirs(data: dict[str, Any]) -> None:
    write_json(WORKDIRS_FILE, data)


def load_gateways() -> dict[str, Any]:
    ensure_registry()
    data = read_json(GATEWAYS_FILE, default_gateways())
    data.setdefault("version", 1)
    data.setdefault("gateways", [])
    return data


def find_account(name: str) -> dict[str, Any] | None:
    data = load_accounts()
    for account in data["accounts"]:
        aliases = account.get("aliases") or []
        if account.get("id") == name or name in aliases:
            return account
    return None


def cmd_ensure(_: argparse.Namespace) -> int:
    ensure_registry()
    return 0


def cmd_resolve_account(args: argparse.Namespace) -> int:
    name = args.account or "default"
    if name in {"default", "native"}:
        print("default")
        return 0
    account = find_account(name)
    if not account:
        # Fall back to using the literal name as a provider profile. This keeps
        # legacy profile names usable before they are added to accounts.json.
        print(name)
        return 0
    mapped = (account.get("provider_profiles") or {}).get(args.provider)
    print(mapped or account.get("id") or name)
    return 0


def cmd_accounts_list(args: argparse.Namespace) -> int:
    data = load_accounts()
    for account in data["accounts"]:
        if account.get("hidden") and not args.all:
            continue
        aliases = ",".join(account.get("aliases") or [])
        mappings = account.get("provider_profiles") or {}
        print(
            "\t".join(
                [
                    str(account.get("id", "")),
                    str(account.get("label", "")),
                    aliases,
                    ",".join(f"{k}:{v}" for k, v in sorted(mappings.items())),
                ]
            )
        )
    return 0


def cmd_accounts_add(args: argparse.Namespace) -> int:
    data = load_accounts()
    if find_account(args.account_id):
        print(f"ERROR: account already exists: {args.account_id}", file=sys.stderr)
        return 2
    mappings: dict[str, str] = {}
    for item in args.map or []:
        if ":" not in item:
            print(f"ERROR: mapping must be provider:profile: {item}", file=sys.stderr)
            return 2
        provider, profile = item.split(":", 1)
        mappings[provider] = profile
    data["accounts"].append(
        {
            "id": args.account_id,
            "label": args.label or args.account_id,
            "aliases": args.alias or [],
            "native": False,
            "hidden": False,
            "provider_profiles": mappings,
        }
    )
    save_accounts(data)
    print(f"added account: {args.account_id}")
    return 0


def cmd_accounts_alias(args: argparse.Namespace) -> int:
    data = load_accounts()
    for account in data["accounts"]:
        if account.get("id") == args.account_id:
            aliases = list(account.get("aliases") or [])
            if args.alias not in aliases:
                aliases.append(args.alias)
            account["aliases"] = aliases
            save_accounts(data)
            print(f"added alias: {args.alias} -> {args.account_id}")
            return 0
    print(f"ERROR: account not found: {args.account_id}", file=sys.stderr)
    return 2


def cmd_workdirs_list(args: argparse.Namespace) -> int:
    data = load_workdirs()
    for item in data["workdirs"]:
        if item.get("archived") and not args.all:
            continue
        print(
            "\t".join(
                [
                    str(item.get("name", "")),
                    str(item.get("path", "")),
                    str(item.get("purpose", "")),
                    "archived" if item.get("archived") else "active",
                ]
            )
        )
    return 0


def cmd_workdirs_add(args: argparse.Namespace) -> int:
    data = load_workdirs()
    path = Path(args.path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    for item in data["workdirs"]:
        if item.get("name") == args.name:
            print(f"ERROR: workdir already exists: {args.name}", file=sys.stderr)
            return 2
    if args.create:
        path.mkdir(parents=True, exist_ok=True)
    data["workdirs"].append(
        {
            "name": args.name,
            "path": str(path),
            "purpose": args.purpose or "",
            "favorite": bool(args.favorite),
            "archived": False,
        }
    )
    save_workdirs(data)
    print(f"added workdir: {args.name} -> {path}")
    return 0


def cmd_workdirs_archive(args: argparse.Namespace) -> int:
    data = load_workdirs()
    for item in data["workdirs"]:
        if item.get("name") == args.name:
            item["archived"] = True
            save_workdirs(data)
            print(f"archived workdir: {args.name}")
            return 0
    print(f"ERROR: workdir not found: {args.name}", file=sys.stderr)
    return 2


def cmd_profiles_list(args: argparse.Namespace) -> int:
    providers = [args.provider] if args.provider else ["codex", "gemini", "hermes"]
    for provider in providers:
        print(f"== {provider} ==")
        print("default\tnative")
        for profile in existing_provider_profiles(provider):
            print(f"{profile}\tmanaged")
    return 0


def cmd_gateways_list(_: argparse.Namespace) -> int:
    data = load_gateways()
    for item in data["gateways"]:
        print(
            "\t".join(
                [
                    str(item.get("id", "")),
                    str(item.get("kind", "")),
                    str(item.get("hermes_profile") or ""),
                    str(item.get("bridge") or ""),
                ]
            )
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ai_registry")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ensure")
    s.set_defaults(fn=cmd_ensure)

    s = sub.add_parser("resolve-account")
    s.add_argument("provider", choices=["codex", "gemini", "hermes"])
    s.add_argument("account", nargs="?")
    s.set_defaults(fn=cmd_resolve_account)

    s = sub.add_parser("accounts-list")
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_accounts_list)

    s = sub.add_parser("accounts-add")
    s.add_argument("account_id")
    s.add_argument("--label")
    s.add_argument("--alias", action="append")
    s.add_argument("--map", action="append", help="provider:profile")
    s.set_defaults(fn=cmd_accounts_add)

    s = sub.add_parser("accounts-alias")
    s.add_argument("account_id")
    s.add_argument("alias")
    s.set_defaults(fn=cmd_accounts_alias)

    s = sub.add_parser("workdirs-list")
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_workdirs_list)

    s = sub.add_parser("workdirs-add")
    s.add_argument("name")
    s.add_argument("path")
    s.add_argument("--purpose")
    s.add_argument("--favorite", action="store_true")
    s.add_argument("--create", action="store_true")
    s.set_defaults(fn=cmd_workdirs_add)

    s = sub.add_parser("workdirs-archive")
    s.add_argument("name")
    s.set_defaults(fn=cmd_workdirs_archive)

    s = sub.add_parser("profiles-list")
    s.add_argument("provider", nargs="?", choices=["codex", "gemini", "hermes"])
    s.set_defaults(fn=cmd_profiles_list)

    s = sub.add_parser("gateways-list")
    s.set_defaults(fn=cmd_gateways_list)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
