#!/usr/bin/env python3
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Any
COMMAND_TYPES={"launch","inline_prompt","native_passthrough"}
PROFILE_STRATEGIES={"none","env_home","temp_home_symlink","native_arg","profile_use"}
SESSION_STRATEGIES={"none","codex_resume","hermes_resume","agy_resume"}

def lib_dir() -> Path: return Path(__file__).resolve().parent
def repo_config_dir() -> Path: return lib_dir().parent / "config"
def user_config_dir() -> Path: return Path(os.environ.get("AI_CONFIG_DIR", str(Path.home()/".config"/"ai"))).expanduser()

def _load(path: Path) -> dict[str, Any] | None:
    try:
        if path.is_file(): return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"ERROR: failed to read {path}: {e}") from e
    return None

def _load_first(env: str, names: list[str], default: dict[str, Any]) -> dict[str, Any]:
    candidates=[]
    if os.environ.get(env): candidates.append(Path(os.environ[env]).expanduser())
    for name in names:
        candidates += [repo_config_dir()/name, user_config_dir()/name, user_config_dir()/"config"/name]
    for p in candidates:
        data=_load(p)
        if data is not None: return data
    return default
DEFAULT_COMMANDS={"commands":{"run":{"type":"launch","tui_visible":True},"ask":{"type":"inline_prompt","tui_visible":False},"chat":{"type":"inline_prompt","tui_visible":False},"raw":{"type":"native_passthrough","tui_visible":False}}}
DEFAULT_PROVIDERS={"providers":{"codex":{"label":"Codex","binary":"codex","profile":{"supported":True,"base_dir":"~/.codex-profiles","strategy":"env_home","env_var":"CODEX_HOME","default_uses_native_home":True},"session":{"supported":True,"strategy":"codex_resume","supports_all":True}},"agy":{"label":"Agy","binary":"agy","profile":{"supported":True,"base_dir":"~/.agy-profiles","strategy":"env_home","env_var":"HOME","default_uses_native_home":True},"session":{"supported":True,"strategy":"agy_resume","supports_all":False}},"hermes":{"label":"Hermes","binary":"hermes","profile":{"supported":True,"base_dir":"~/.hermes/profiles","strategy":"native_arg","arg":"--profile"},"session":{"supported":True,"strategy":"hermes_resume","supports_all":False}}}}

def load_command_specs() -> dict[str, Any]:
    data=_load_first("AI_COMMANDS_FILE", ["ai.commands.json"], DEFAULT_COMMANDS)
    commands=data.get("commands", {})
    if not isinstance(commands, dict) or not commands: raise SystemExit("ERROR: no commands configured")
    for n,s in commands.items():
        if s.get("type") not in COMMAND_TYPES: raise SystemExit(f"ERROR: unsupported command type for {n}: {s.get('type')}")
    return commands

def load_provider_specs() -> dict[str, Any]:
    data=_load_first("AI_PROVIDERS_FILE", ["ai.providers.json"], DEFAULT_PROVIDERS)
    providers=data.get("providers", {})
    if not isinstance(providers, dict) or not providers: raise SystemExit("ERROR: no providers configured")
    for n,s in providers.items():
        ps=(s.get("profile") or {}).get("strategy","none")
        ss=(s.get("session") or {}).get("strategy","none")
        if ps not in PROFILE_STRATEGIES: raise SystemExit(f"ERROR: unsupported profile strategy for {n}: {ps}")
        if ss not in SESSION_STRATEGIES: raise SystemExit(f"ERROR: unsupported session strategy for {n}: {ss}")
    return providers

def command_spec(name: str) -> dict[str, Any]:
    c=load_command_specs()
    if name not in c: raise KeyError(name)
    s=dict(c[name]); s["name"]=name; return s

def provider_spec(name: str) -> dict[str, Any]:
    p=load_provider_specs()
    if name not in p: raise KeyError(name)
    s=dict(p[name]); s["name"]=name; s["label"]=s.get("label") or name.title(); return s

def command_names(tui_visible: bool | None=None) -> list[str]:
    out=[]
    for name,s in load_command_specs().items():
        if tui_visible is not None and bool(s.get("tui_visible")) != tui_visible: continue
        out.append(name)
    return out

def provider_names() -> list[str]: return list(load_provider_specs().keys())
def is_provider(name: str) -> bool: return name in load_provider_specs()
def is_command(name: str) -> bool: return name in load_command_specs()
