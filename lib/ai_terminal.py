"""Thin client of Termux's existing-terminal origin protocol; never create UI."""
import json
import os
import stat
import subprocess
from pathlib import Path

SCHEMA = "termux-terminal-origin-v1"
OPTION = "@termux_origin_v1"

def reference(value):
    if not isinstance(value, dict) or set(value) != {"handle", "pid", "start"}: return None
    import re
    if not isinstance(value["handle"], str) or not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", value["handle"]): return None
    if type(value["pid"]) is not int or not 0 < value["pid"] <= 2147483647: return None
    if type(value["start"]) is not int or not 0 < value["start"] <= 9223372036854775807: return None
    return value

def _request(operation, origin=None):
    prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
    endpoint = prefix.parent / "apps/com.termux/termux-am/am.sock"
    try:
        info = endpoint.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid(): return None
        words = ["termux-terminal-v1", operation]
        if origin is not None:
            if reference(origin) is None: return None
            words += [origin["handle"], str(origin["pid"]), str(origin["start"])]
        result = subprocess.run([str(prefix/"bin/termux-am-socket"), " ".join(words)], stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
        if result.returncode or result.stderr or len(result.stdout) > 4096: return None
        response = json.loads(result.stdout)
        if response.get("schema") != SCHEMA or response.get("result") != "ok": return None
        found = reference(response.get("origin"))
        return found if found is not None and (origin is None or origin == found) else None
    except (OSError, ValueError, TypeError, AttributeError, subprocess.TimeoutExpired): return None

def resolve(): return _request("origin")
def validate(origin): return _request("validate", origin) is not None
def focus(origin): return _request("focus", origin) is not None
