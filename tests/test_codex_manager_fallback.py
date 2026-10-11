#!/usr/bin/env python3
"""Exercise manager absence and runtime handoff failure with isolated accounts."""
from __future__ import annotations
import errno
import json
import os
from pathlib import Path
import pty
import select
import signal
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ai_codex_manager
import ai_plan


def run_case(case: str, profile: str, *, terminal: bool = False) -> None:
    with tempfile.TemporaryDirectory() as directory:
        home = Path(directory)
        with patch.dict(os.environ, {"HOME": directory}):
            account = ai_codex_manager.create_profile("account")
        log = home / "native.json"
        binary = home / "codex"
        binary.write_text("#!" + sys.executable + "\n" + f'''
import json,os,sys
from pathlib import Path
args = sys.argv[1:]
case = {case!r}
if args[:3] == ["termux", "profile", "list"]:
    if case == "probe":
        print("Codex Termux Manager is unavailable.")
        sys.exit(0)
    print("default\\naccount")
    sys.exit(0)
if args[:3] == ["termux", "profile", "use"]:
    if case == "auth":
        print("unexpected status 401 Unauthorized", file=sys.stderr)
    else:
        print("codex termux: Core handoff is invalid", file=sys.stderr)
    sys.exit(1)
Path({str(log)!r}).write_text(json.dumps({{
    "argv": args, "cwd": os.getcwd(),
    "env": {{key: os.environ.get(key) for key in ["CODEX_HOME", "CODEX_SQLITE_HOME", "CODEX_TERMUX_CORE_API", "CODEX_TERMUX_CORE_ENTRYPOINT"]}},
    "tty": [os.isatty(fd) for fd in (0,1,2)],
}}))
print("native launch")
''')
        binary.chmod(0o700)
        config = home / "providers.json"
        config.write_text(json.dumps({"providers": {"codex": {
            "binary": str(binary), "profile": {"supported": True, "strategy": "codex_manager"},
            "session": {"strategy": "codex_resume"},
        }}}))
        env = os.environ.copy()
        env.update(HOME=directory, AI_PROVIDERS_FILE=str(config), CODEX_HOME="/wrong-account",
                   CODEX_SQLITE_HOME="/wrong-store", CODEX_TERMUX_CORE_API="stale", CODEX_TERMUX_CORE_ENTRYPOINT="/stale")
        argv = [sys.executable, str(ROOT / "lib/ai_cli.py"), "run", "codex",
                *(["-p", profile] if profile != "default" else []),
                "-d", directory, "--", "--model", "fixture"]
        if not terminal:
            result = subprocess.run(argv, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
            status = result.returncode
            output = result.stdout + result.stderr
        else:
            pid, master = pty.fork()
            if pid == 0:
                os.execvpe(argv[0], argv, env)
            output_bytes = b""
            deadline = time.monotonic() + 15
            try:
                while time.monotonic() < deadline:
                    if select.select([master], [], [], 0.2)[0]:
                        try:
                            chunk = os.read(master, 8192)
                        except OSError as error:
                            if error.errno == errno.EIO:
                                break
                            raise
                        if not chunk:
                            break
                        output_bytes += chunk
                else:
                    os.kill(pid, signal.SIGKILL)
                    raise AssertionError("fallback PTY timed out")
            finally:
                os.close(master)
                _, child_status = os.waitpid(pid, 0)
            status = os.waitstatus_to_exitcode(child_status)
            output = output_bytes.decode(errors="replace")
        if case == "auth":
            assert status == 1 and not log.exists(), output
            return
        assert status == 0, output
        recorded = json.loads(log.read_text())
        assert recorded["argv"] == ["--model", "fixture"]
        assert recorded["cwd"] == directory
        expected_home = str(account) if profile == "account" else None
        assert recorded["env"] == {
            "CODEX_HOME": expected_home, "CODEX_SQLITE_HOME": None,
            "CODEX_TERMUX_CORE_API": None, "CODEX_TERMUX_CORE_ENTRYPOINT": None,
        }, recorded
        assert not (account / "sessions").exists()  # Core owns topology preparation.
        if terminal:
            assert recorded["tty"] == [True, True, True]


def main() -> None:
    assert not ai_plan.manager_launch_failed("codex termux: Core handoff is invalid", 0)
    assert not ai_plan.manager_launch_failed("unexpected status 401 Unauthorized", 1)
    assert ai_plan.manager_launch_failed("Codex Termux Manager is unavailable.\n", 0)
    run_case("probe", "account")
    run_case("probe", "default")
    run_case("handoff", "account")
    run_case("handoff", "default")
    run_case("handoff", "account", terminal=True)
    run_case("auth", "account")
    print("PASS manager fallback: probe, handoff, default environment, PTY, and no auth retry")


if __name__ == "__main__":
    main()
