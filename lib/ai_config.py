#!/usr/bin/env python3
"""Safe TSV config helper for the ai wrapper.

The runtime shell reads config.tsv as data with a small whitelist parser. This
helper is used for validated `ai config set/show` without requiring the shell to
source executable config code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULTS: dict[str, str] = {
    "AI_DEFAULT_PROVIDER": "hermes",
    "AI_FALLBACK_ENABLED": "false",
    "AI_FALLBACK_PROVIDERS": "hermes gemini codex",
    "AI_EXPLICIT_FALLBACK": "false",
    "AI_ASK_TIMEOUT": "180",
    "AI_AUTO_START_BRIDGE": "false",
}

ALIASES: dict[str, str] = {
    "default-provider": "AI_DEFAULT_PROVIDER",
    "fallback-enabled": "AI_FALLBACK_ENABLED",
    "fallback-providers": "AI_FALLBACK_PROVIDERS",
    "explicit-fallback": "AI_EXPLICIT_FALLBACK",
    "ask-timeout": "AI_ASK_TIMEOUT",
    "auto-start-bridge": "AI_AUTO_START_BRIDGE",
}

PROVIDERS = {"codex", "gemini", "hermes"}
BOOLS = {"true", "false"}


def normalize_key(key: str) -> str:
    return ALIASES.get(key, key)


def validate(key: str, value: str) -> None:
    if "\n" in value or "\r" in value or "\t" in value:
        raise SystemExit("config values must be single-line strings without tabs")
    if key == "AI_DEFAULT_PROVIDER":
        if value not in PROVIDERS:
            raise SystemExit(f"invalid provider: {value}")
    elif key == "AI_FALLBACK_PROVIDERS":
        parts = value.split()
        if not parts or any(part not in PROVIDERS for part in parts):
            raise SystemExit(f"invalid fallback provider list: {value}")
    elif key in {
        "AI_FALLBACK_ENABLED",
        "AI_EXPLICIT_FALLBACK",
        "AI_AUTO_START_BRIDGE",
    }:
        if value not in BOOLS:
            raise SystemExit(f"invalid boolean for {key}: {value}")
    elif key == "AI_ASK_TIMEOUT":
        if not value.isdigit() or int(value) <= 0:
            raise SystemExit(f"invalid positive integer timeout: {value}")
    elif key not in DEFAULTS:
        raise SystemExit(f"unknown config key: {key}")


def load(path: Path) -> dict[str, str]:
    cfg = dict(DEFAULTS)
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if "\t" not in line:
            raise SystemExit(f"invalid config line, expected KEY<TAB>VALUE: {line!r}")
        key, value = line.split("\t", 1)
        key = normalize_key(key)
        validate(key, value)
        cfg[key] = value
    return cfg


def save(path: Path, cfg: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}\t{cfg[key]}" for key in DEFAULTS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def export(path: Path) -> int:
    for key, value in load(path).items():
        print(f"{key}\t{value}")
    return 0


def show(path: Path) -> int:
    print(json.dumps(load(path), ensure_ascii=False, indent=2))
    return 0


def set_value(path: Path, key: str, value: str) -> int:
    key = normalize_key(key)
    validate(key, value)
    cfg = load(path)
    cfg[key] = value
    save(path, cfg)
    print(f"set {key}={value}")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        raise SystemExit("usage: ai_config.py CONFIG_PATH [export|show|set KEY VALUE]")
    path = Path(argv[1])
    cmd = argv[2] if len(argv) > 2 else "export"
    if cmd == "export":
        return export(path)
    if cmd == "show":
        return show(path)
    if cmd == "set":
        if len(argv) != 5:
            raise SystemExit("usage: ai_config.py CONFIG_PATH set KEY VALUE")
        return set_value(path, argv[3], argv[4])
    if cmd == "path":
        print(path)
        return 0
    raise SystemExit(f"unknown config helper command: {cmd}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
