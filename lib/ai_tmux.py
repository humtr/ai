"""Optional native tmux launch and bounded focus of existing Codex panes."""
from __future__ import annotations
import json
import hashlib
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
COLOR_ENVIRONMENT = ("NO_COLOR", "FORCE_COLOR", "CLICOLOR", "CLICOLOR_FORCE", "COLORTERM", "COLORFGBG")
TITLE_ID = re.compile(r"^(?:● )?(?:\[ [!.] \] Action Required \| )?([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{5})\.\.\.(?![0-9a-f])")


def _tmux(socket: str | None, *args: str) -> str:
    command = ["tmux", "-u"] + (["-S", socket] if socket else []) + list(args)
    result = subprocess.run(command, capture_output=True, text=True, timeout=1)
    if result.returncode:
        raise RuntimeError("tmux command failed")
    return result.stdout.rstrip("\n")


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
    destination = root / (hashlib.sha256(socket.encode()).hexdigest() + ".json")
    fd, temporary = tempfile.mkstemp(prefix=".server-", dir=root)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump({"socket": socket, "identity": _socket_identity(socket)}, stream)
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _native_identity(plan) -> bool:
    """Ask the qualified Core/Manager path; never inspect its manifests."""
    environment = dict(os.environ)
    for key in getattr(plan, "env_unset", ()):
        environment.pop(key, None)
    environment.update(plan.env)
    try:
        result = subprocess.run([plan.argv[0], "termux", "__terminal-capabilities-v1", "--", *plan.argv[1:]],
                                env=environment, cwd=plan.cwd, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=2)
        return result.returncode == 0 and result.stdout == b"codex-terminal-capabilities-v1\nidentity=native\n" and not result.stderr
    except (OSError, subprocess.TimeoutExpired):
        return False



def launch(plan, provider: str) -> int:
    if not shutil.which("tmux"):
        raise SystemExit("ERROR: tmux is not installed")
    if provider == "codex":
        if not _native_identity(plan):
            prepare_title(Path(plan.env.get("CODEX_HOME") or os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")))
    # tmux executes one shell command; quote every argv/environment field.
    environment = {key: os.environ[key] for key in ("HOME", "PATH", "CODEX_HOME", "AI_CONFIG_DIR", "AI_LIB_DIR", *COLOR_ENVIRONMENT) if key in os.environ}
    environment.update(plan.env)
    assignments = [f"{key}={value}" for key, value in environment.items()]
    # A reused server may retain NO_COLOR from a prior noninteractive client.
    # Explicit absence is part of the caller preference; TERM stays tmux-owned.
    unset = [argument for key in ("CODEX_HOME", *COLOR_ENVIRONMENT) if key not in environment for argument in ("-u", key)]
    command = "exec " + shlex.join(["env", *unset, *assignments, *plan.argv])
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
    if _tmux(socket, "display-message", "-p", "-t", pane, "#{@humtr_ai_session}") == "1":
        _tmux(socket, "set-option", "-t", pane, "set-titles", "on")
        _tmux(socket, "set-option", "-t", pane, "set-titles-string", "#{pane_title}")
        _tmux(socket, "set-option", "-t", pane, "status", "on" if plan.tmux_status else "off")
        if plan.tmux_status:
            _tmux(socket, "set-option", "-t", pane, "mouse", "on")
    _tmux(socket, "set-option", "-p", "-t", pane, "@humtr_ai_provider", provider)
    register(socket)
    _tmux(socket, "select-window", "-t", pane)
    _tmux(socket, "select-pane", "-t", pane)
    if not inside:
        session = _tmux(socket, "display-message", "-p", "-t", pane, "#{session_id}")
        terminal = terminal_name(socket, session, provider)
        _tmux(socket, "set-option", "-t", session, "@humtr_ai_terminal_name", terminal)
        if _attach_terminal(socket, session, terminal) == 0:
            return 0
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


PROC = Path("/proc")


def _process_identity(process: Path) -> tuple[int, int]:
    fields = (process / "stat").read_text().rpartition(")")[2].split()
    return int(fields[1]), int(fields[19])  # PPid and kernel start time.


def _native_runtime(executable: str) -> bool:
    root = Path.home() / ".local/lib/codex"
    return bool(re.fullmatch(re.escape(str(root / "core/generations")) + r"/[^/]+/(?:runtime|helpers/2)", executable)) or executable == str(root / "profile-tui-preview/direct-selection-v1/native")


def _runtime(pid: str, tty: str, native_binding: tuple[int, int] | None = None) -> bool:
    if not pid.isdecimal():
        return False
    try:
        import sys
        process = PROC / pid
        identity = _process_identity(process)
        if process.stat().st_uid != os.getuid() or os.stat(process / "fd/0").st_rdev != os.stat(tty).st_rdev:
            return False
        executable = os.readlink(process / "exe")
        if _native_runtime(executable):
            return identity == _process_identity(process) and (native_binding is None or native_binding == (int(pid), identity[1]))
        # The auth-recovery launcher bridges the pane to a child PTY. Its PID
        # is tmux's pane_pid; the native frontend is its direct child.
        if executable != str(Path(sys.executable).resolve()):
            return False
        argv = (process / "cmdline").read_bytes()
        if len(argv) > 65536:
            return False
        argv = argv.rstrip(b"\0").split(b"\0")
        if len(argv) != 3 or Path(os.fsdecode(argv[1])).resolve() != Path(__file__).with_name("ai_run.py").resolve():
            return False
        plan = json.loads(argv[2])
        prefix = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")
        if plan.get("auth_recovery") is not True or not isinstance(plan.get("argv"), list) or not plan['argv'] or plan['argv'][0] not in {"codex", str(Path(prefix) / "bin/codex")}:
            return False
        candidates = []
        # Android may expose empty task/children; PPid is the actual parent proof.
        for child in PROC.glob("[0-9]*"):
            try:
                child_identity = _process_identity(child)
                if child.stat().st_uid != os.getuid() or child_identity[0] != int(pid) or not _native_runtime(os.readlink(child / "exe")):
                    continue
                if not re.fullmatch(r"/dev/pts/[0-9]+", os.readlink(child / "fd/0")):
                    continue
                if child_identity == _process_identity(child):
                    candidates.append((child, child_identity))
            except (OSError, ValueError, IndexError):
                continue
        return len(candidates) == 1 and identity == _process_identity(process) and _process_identity(candidates[0][0]) == candidates[0][1] and (native_binding is None or native_binding == (int(candidates[0][0].name), candidates[0][1][1]))
    except (OSError, ValueError, IndexError, TypeError, AttributeError):
        return False


def _bound_thread(binding: str, pid: str, tty: str) -> str | None:
    """Read current foreground identity from a qualified native identity slot."""
    try:
        parts = binding.split(":")
        if len(parts) != 5 or not all(x.isdecimal() for x in parts):
            return None
        native_pid, native_start, root_pid, root_start, descriptor = map(int, parts)
        if str(root_pid) != pid or descriptor > 1048576 or _process_identity(PROC / pid)[1] != root_start:
            return None
        if not _runtime(pid, tty, (native_pid, native_start)):
            return None
        slot = PROC / str(native_pid) / 'fd' / str(descriptor)
        name = Path(os.readlink(slot)).name
        prefix = f'.codex-terminal-thread-v1-{native_pid}-'
        if not name.startswith(prefix) or not name.endswith(' (deleted)'):
            return None
        nonce = name[len(prefix):-len(' (deleted)')]
        if not nonce or not re.fullmatch(r'[A-Za-z0-9-]+', nonce):
            return None
        metadata = slot.stat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 36:
            return None
        with slot.open('rb') as stream:
            content = stream.read(37).decode('ascii')
        if _process_identity(PROC / str(native_pid))[1] != native_start or _process_identity(PROC / pid)[1] != root_start:
            return None
        return content if UUID.fullmatch(content) else None
    except (OSError, ValueError, IndexError):
        return None



def _activity_manager() -> str | None:
    """Choose transport before dispatch; never replay an execution-service request."""
    prefix = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr"))
    socket = prefix.parent / "apps/com.termux/termux-am/am.sock"
    try:
        info = socket.lstat()
        if stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid():
            client = shutil.which("termux-am")
            if client:
                return client
    except OSError:
        pass
    return shutil.which("am")


def terminal_name(socket: str, session: str, provider: str = "ai") -> str:
    """Stable presentation identity; live socket/runtime checks remain separate."""
    binding = _tmux(socket, "show-options", "-qv", "-t", session, "@humtr_ai_terminal_name")
    if binding:
        if not re.fullmatch(r"(?:ai-tmux-(?:[0-9a-f]{16}|[0-9a-f]{64})|[a-z][a-z0-9]{0,23}-[0-9a-f]{8})", binding):
            raise ValueError("invalid native terminal binding")
        return binding
    name = _tmux(socket, "display-message", "-p", "-t", session, "#{session_name}")
    if not name:
        raise ValueError("missing native session name")
    if not re.fullmatch(r"[a-z][a-z0-9]{0,23}", provider):
        raise ValueError("invalid native terminal CLI prefix")
    return provider + "-" + hashlib.sha256(
        json.dumps([socket, name], separators=(",", ":")).encode()
    ).hexdigest()[:8]


def focus(session_id: str) -> int:
    """Select one qualified pane and reuse its named native tmux terminal."""
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
                rows = _tmux(socket, "list-panes", "-a", "-F", "#{pane_id}\t#{pane_pid}\t#{pane_tty}\t#{pane_dead}\t#{@humtr_ai_provider}\t#{@codex_terminal_binding_v1}\t#{pane_title}")
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired):
                continue
            for row in rows.splitlines():
                fields = row.split("\t", 6)
                if len(fields) != 7:
                    continue
                pane, pid, tty, dead, provider, binding, title = fields
                if dead != "0":
                    continue
                if binding:
                    # Native lifecycle metadata owns identity. A stale binding
                    # must never downgrade to title matching.
                    if _bound_thread(binding, pid, tty) != session_id:
                        continue
                else:
                    matches = TITLE_ID.findall(title)
                    if provider != "codex" or len(matches) != 1 or matches[0] != session_id[:29]:
                        continue
                    if _local_id(matches[0]) != session_id or not _runtime(pid, tty):
                        continue
                targets.append((socket, pane, pid, tty, binding, data["identity"]))
        if len(targets) != 1 or time.monotonic() > deadline:
            return 1
        socket, pane, pid, tty, binding, identity = targets[0]
        # Android am string-array arguments cannot represent these socket paths.
        if any(c in socket for c in (",", "\\")) or list(_socket_identity(socket)) != identity:
            return 1
        # Recheck current identity at the actual native UI command boundary.
        if binding:
            identity_test = "#{==:#{@codex_terminal_binding_v1}," + binding + "}"
        else:
            identity_test = "#{&&:#{==:#{@humtr_ai_provider},codex},#{m/r:^(● )?(\\[ [!.] \\] Action Required \\| )?" + session_id[:29] + "\\.\\.\\.([^0-9a-f]|$),#{pane_title}}}"
        predicate = "#{&&:#{==:#{pane_pid}," + pid + "},#{&&:#{==:#{pane_dead},0}," + identity_test + "}}"
        target = _tmux(socket, "if-shell", "-F", "-t", pane, predicate,
              "select-window -t " + pane + " ; select-pane -t " + pane
              + " ; display-message -p -t " + pane + " '#{session_id}'")
        if not re.fullmatch(r"\$[0-9]+", target) or time.monotonic() >= deadline:
            return 1
        if binding and _bound_thread(binding, pid, tty) != session_id:
            return 1
        return _attach_terminal(socket, target, terminal_name(socket, target))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.TimeoutExpired):
        return 1


def _attach_terminal(socket: str, target: str, terminal: str) -> int:
    """One bounded service request, shared by initial launch and notification return."""
    if any(c in socket for c in (",", "\\")) or not re.fullmatch(r"\$[0-9]+", target):
        return 1
    am = _activity_manager()
    tmux = shutil.which("tmux")
    if not am or not tmux:
        return 1
    try:
        result = subprocess.run([
            am, "startservice", "--user", "0", "-n", "com.termux/.app.RunCommandService",
            "-a", "com.termux.RUN_COMMAND", "--es", "com.termux.RUN_COMMAND_PATH", tmux,
            "--esa", "com.termux.RUN_COMMAND_ARGUMENTS", "-S," + socket + ",attach-session,-t," + target,
            "--ez", "com.termux.RUN_COMMAND_BACKGROUND", "false",
            "--es", "com.termux.RUN_COMMAND_SHELL_NAME", terminal,
            "--es", "com.termux.RUN_COMMAND_SHELL_CREATE_MODE", "no-shell-with-name",
            "--es", "com.termux.RUN_COMMAND_SESSION_ACTION", "0",
        ], capture_output=True, text=True, timeout=15)
        return 0 if result.returncode == 0 else 1
    except (OSError, subprocess.TimeoutExpired):
        return 1

