#!/usr/bin/env python3
from __future__ import annotations
import json, os, time
from pathlib import Path
from typing import Any
HOME = Path(os.environ.get("HOME", str(Path.home()))).expanduser()
AI_HOME = Path(os.environ.get("AI_HOME", str(HOME / ".ai"))).expanduser()
AI_CONFIG_DIR = Path(os.environ.get("AI_CONFIG_DIR", str(HOME / ".config" / "ai"))).expanduser()
WORKDIRS_FILE = AI_HOME / "workdirs.json"
SESSION_INDEX_DIR = AI_HOME / "session-index"
SESSION_INDEX_FILE = SESSION_INDEX_DIR / "sessions.json"
SESSION_INDEX_VERSION = 10
TUI_STATE_FILE = AI_HOME / "tui-state.json"

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

def ensure_store() -> None:
    if not WORKDIRS_FILE.exists(): write_json(WORKDIRS_FILE, default_workdirs())

def load_workdirs() -> dict[str, Any]:
    ensure_store(); data=read_json(WORKDIRS_FILE, default_workdirs()); data.setdefault("workdirs", []); return data

def save_workdirs(data: dict[str, Any]) -> None: write_json(WORKDIRS_FILE, data)
def load_tui_state() -> dict[str, Any]:
    data=read_json(TUI_STATE_FILE, {"version":1}); data.setdefault("version", 1); return data
def save_tui_state(data: dict[str, Any]) -> None: write_json(TUI_STATE_FILE, data)
