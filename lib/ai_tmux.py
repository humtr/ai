"""Optional native tmux launch and bounded focus of existing Codex panes."""
from __future__ import annotations
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import tomllib
from pathlib import Path

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
TITLE_ID = re.compile(r"^(?:● )?(?:\[ [!.] \] Action Required \| )?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{5})\.\.\.(?![0-9a-f])")


def _tmux(socket: str | None, *args: str) -> str:
    command = ["tmux"] + (["-S", socket] if socket else []) + list(args)
    result = subprocess.run(command, capture_output=True, text=True, timeout=1)
    if result.returncode:
        raise RuntimeError("tmux command failed")
    return result.stdout.strip()


def prepare_title(home: Path) -> None:
    """Preserve config bytes outside the one native title preference."""
    path = home / "config.toml"
    if path.is_symlink():
        raise ValueError("Codex config must be a regular file")
    before = path.read_text() if path.exists() else ""
    data = tomllib.loads(before)
    tui = data.get("tui", {})
    if not isinstance(tui, dict):
        raise ValueError("invalid Codex TUI config")
    items = tui.get("terminal_title", ["activity", "thread-name", "project-name"])
    if not isinstance(items, list) or any(not isinstance(x, str) for x in items):
        raise ValueError("invalid Codex title config")
    desired = ["thread-id"] + [x for x in items if x not in {"thread-id", "session-id"}]
    if items == desired:
        return
    line = "terminal_title = " + json.dumps(desired, ensure_ascii=False) + "\n"
    section = re.search(r"(?m)^\[tui\][ \t]*(?:#[^\n]*)?\n", before)
    if section:
        start = section.end()
        following = re.search(r"(?m)^\s*\[", before[start:])
        end = start + following.start() if following else len(before)
        body = before[start:end]
        assignment = re.search(r"(?ms)^[ \t]*terminal_title\s*=\s*\[.*?\]", body)
        if assignment:
            after = before[:start] + body[:assignment.start()] + line.rstrip() + body[assignment.end():] + before[end:]
        elif "terminal_title" not in tui:
            after = before[:start] + line + before[start:]
        else:
            raise ValueError("unsupported Codex title syntax")
    elif "tui" not in data:
        after = before + ("\n" if before and not before.endswith("\n") else "") + "\n[tui]\n" + line
    else:
        raise ValueError("unsupported Codex TUI syntax")
    expected = dict(data)
    expected["tui"] = dict(tui, terminal_title=desired)
    if tomllib.loads(after) != expected:
        raise ValueError("Codex config preservation failed")
    home.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix=".ai-title-", dir=home)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream:
            stream.write(after)
            stream.flush()
            os.fsync(stream.fileno())
        if (path.read_text() if path.exists() else "") != before:
            raise ValueError("Codex config changed concurrently")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _registry() -> Path:
    return Path.home() / ".local/share/ai/tmux"


def _socket_identity(socket: str) -> tuple[int, int]:
    info = os.stat(socket)
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("unsafe tmux socket")
    return info.st_dev, info.st_ino


def register(socket: str) -> None:
    root = _registry()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or stat.S_IMODE(root.stat().st_mode) != 0o700:
        raise ValueError("unsafe tmux registry")
    for record in root.glob("*.json"):
        try:
            data = json.loads(record.read_text())
            if list(_socket_identity(data["socket"])) != data["identity"]:
                record.unlink()
        except (OSError, ValueError, KeyError, TypeError):
            record.unlink(missing_ok=True)
    import hashlib
    destination = root / (hashlib.sha256(socket.encode()).hexdigest() + ".json")
    fd, temporary = tempfile.mkstemp(prefix=".server-", dir=root)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"socket": socket, "identity": _socket_identity(socket)}, stream)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def launch(plan, provider: str) -> int:
    if not shutil.which("tmux"):
        raise SystemExit("ERROR: tmux is not installed")
    if provider == "codex":
        prepare_title(Path(plan.env.get("CODEX_HOME") or os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")))
    # tmux executes one shell command; quote every argv/environment field.
    environment = {key: os.environ[key] for key in ("HOME", "PATH", "CODEX_HOME", "AI_CONFIG_DIR", "AI_LIB_DIR") if key in os.environ}
    environment.update(plan.env)
    assignments = [f"{key}={value}" for key, value in environment.items()]
    command = "exec " + shlex.join(["env", *(["-u", "CODEX_HOME"] if "CODEX_HOME" not in environment else []), *assignments, *plan.argv])
    inside = bool(os.environ.get("TMUX"))
    if inside:
        socket = _tmux(None, "display-message", "-p", "#{socket_path}")
        pane = _tmux(socket, "new-window", "-d", "-P", "-F", "#{pane_id}", "-n", "ai-" + provider, "-c", plan.cwd, command)
    else:
        try:
            _tmux(None, "has-session", "-t", "=humtr-ai")
        except RuntimeError:
            pane = _tmux(None, "new-session", "-d", "-P", "-F", "#{pane_id}", "-s", "humtr-ai", "-n", "ai-" + provider, "-c", plan.cwd, command)
            _tmux(None, "set-option", "-t", pane, "@humtr_ai_session", "1")
        else:
            if _tmux(None, "show-options", "-v", "-t", "humtr-ai", "@humtr_ai_session") != "1":
                raise ValueError("humtr-ai session is not managed by AI")
            pane = _tmux(None, "new-window", "-d", "-P", "-F", "#{pane_id}", "-t", "=humtr-ai", "-n", "ai-" + provider, "-c", plan.cwd, command)
        socket = _tmux(None, "display-message", "-p", "-t", pane, "#{socket_path}")
    _tmux(socket, "set-option", "-p", "-t", pane, "@humtr_ai_provider", provider)
    register(socket)
    _tmux(socket, "select-window", "-t", pane)
    _tmux(socket, "select-pane", "-t", pane)
    if not inside:
        session = _tmux(socket, "display-message", "-p", "-t", pane, "#{session_id}")
        os.execvp("tmux", ["tmux", "-S", socket, "attach-session", "-t", session])
    return 0


def _local_id(prefix: str) -> str | None:
    ids = set()
    root = Path.home() / ".codex"
    for directory in (root / "sessions", root / "archived_sessions"):
        for path in directory.rglob("rollout-*" + prefix + "*.jsonl"):
            candidate = path.name[-42:-6]
            if not UUID.fullmatch(candidate) or not candidate.startswith(prefix):
                continue
            try:
                with path.open("rb") as stream:
                    line = stream.readline(65537)
                if len(line) > 65536:
                    continue
                meta = json.loads(line)
                if meta.get("type") == "session_meta" and meta.get("payload", {}).get("id") == candidate:
                    ids.add(candidate)
            except (OSError, ValueError, AttributeError):
                continue
    return next(iter(ids)) if len(ids) == 1 else None


def _runtime(pid: str, tty: str) -> bool:
    if not pid.isdecimal():
        return False
    try:
        process = Path("/proc") / pid
        executable = os.readlink(process / "exe")
        return bool(re.fullmatch(re.escape(str(Path.home() / ".local/lib/codex/core/generations")) + r"/[^/]+/runtime", executable)) and os.stat(process / "fd/0").st_rdev == os.stat(tty).st_rdev
    except OSError:
        return False


def focus(session_id: str) -> int:
    """No output, no process launch except bounded tmux commands, no guessing."""
    if not UUID.fullmatch(session_id):
        return 1
    deadline = time.monotonic() + 2
    targets = []
    root = _registry()
    if root.is_symlink() or not root.is_dir() or stat.S_IMODE(root.stat().st_mode) != 0o700:
        return 1
    try:
        for record in root.glob("*.json"):
            if time.monotonic() > deadline or record.is_symlink() or stat.S_IMODE(record.stat().st_mode) != 0o600:
                continue
            try:
                data = json.loads(record.read_text())
                socket = data["socket"]
                if list(_socket_identity(socket)) != data["identity"]:
                    continue
                rows = _tmux(socket, "list-panes", "-a", "-F", "#{pane_id}\t#{pane_pid}\t#{pane_tty}\t#{pane_dead}\t#{@humtr_ai_provider}\t#{pane_title}")
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired):
                continue
            for row in rows.splitlines():
                fields = row.split("\t", 5)
                if len(fields) != 6:
                    continue
                pane, pid, tty, dead, provider, title = fields
                matches = TITLE_ID.findall(title)
                if dead != "0" or provider != "codex" or len(matches) != 1 or matches[0] != session_id[:29]:
                    continue
                if _local_id(matches[0]) == session_id and _runtime(pid, tty):
                    targets.append((socket, pane, pid))
        if len(targets) != 1 or time.monotonic() > deadline:
            return 1
        socket, pane, pid = targets[0]
        # Recheck current identity at the actual native UI command boundary.
        predicate = "#{&&:#{==:#{pane_pid}," + pid + "},#{&&:#{==:#{pane_dead},0},#{&&:#{==:#{@humtr_ai_provider},codex},#{m/r:^(● )?(\\[ [!.] \\] Action Required \\| )?" + session_id[:29] + "\\.\\.\\.,#{pane_title}}}}}"
        _tmux(socket, "if-shell", "-F", "-t", pane, predicate,
              "select-window -t " + pane + " ; select-pane -t " + pane)
        return 0
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired):
        return 1
