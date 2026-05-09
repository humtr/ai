#!/usr/bin/env python3
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any
HOME = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
AI_HOME = Path(os.environ.get("AI_HOME", str(HOME / ".ai"))).expanduser()
AI_CONFIG_DIR = Path(os.environ.get("AI_CONFIG_DIR", str(HOME / ".config" / "ai"))).expanduser()
WORKDIRS_FILE = AI_HOME / "workdirs.json"
GATEWAYS_FILE = AI_HOME / "gateways.json"
SESSION_INDEX_DIR = AI_HOME / "session-index"
SESSION_INDEX_FILE = SESSION_INDEX_DIR / "sessions.json"
SESSION_INDEX_VERSION = 7

def read_json(path: Path, default: Any) -> Any:
    if not path.exists(): return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default

def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    tmp.replace(path)

def normalize_path(value: str | None) -> str:
    if not value: return ""
    try: return str(Path(value).expanduser().resolve())
    except OSError: return str(Path(value).expanduser())

def short_path(value: str) -> str:
    home = str(HOME)
    if value == home: return "~"
    if value.startswith(home + "/"): return "~/" + value[len(home)+1:]
    return value

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())

def default_workdirs() -> dict[str, Any]:
    items=[]; root=HOME/"work"
    if root.is_dir():
        for p in sorted(root.iterdir()):
            if p.is_dir(): items.append({"name":p.name,"path":str(p),"purpose":"","favorite":p.name in {"main","test"},"archived":False})
    return {"version":1,"workdirs":items}

def default_gateways() -> dict[str, Any]:
    return {"version":2,"gateways":[
        {"id":"codex-tg","kind":"telegram-gateway","hermes_profile":"codex-tg","bridge":None,"hidden":False},
        {"id":"gemini-tg","kind":"telegram-gateway","hermes_profile":"gemini-tg","bridge":"gemini-bridge","hidden":False},
        {"id":"gemini-bridge","kind":"openai-compatible-bridge","command":"hgb","manager":"hgm","hidden":False},
    ]}

def ensure_store() -> None:
    if not WORKDIRS_FILE.exists(): write_json(WORKDIRS_FILE, default_workdirs())
    if not GATEWAYS_FILE.exists(): write_json(GATEWAYS_FILE, default_gateways())

def load_workdirs() -> dict[str, Any]:
    ensure_store(); data=read_json(WORKDIRS_FILE, default_workdirs()); data.setdefault("workdirs", []); return data

def save_workdirs(data: dict[str, Any]) -> None: write_json(WORKDIRS_FILE, data)
def load_gateways() -> dict[str, Any]:
    ensure_store(); data=read_json(GATEWAYS_FILE, default_gateways()); data.setdefault("gateways", []); return data
