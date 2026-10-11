#!/usr/bin/env python3
"""Run the recovery path in a real PTY without credentials or network access."""
from __future__ import annotations
import errno
import json
import os
from pathlib import Path
import pty
import select
import signal
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))
import ai_plan


def run_case(error: str, answer: str, expected: list[str], login_failure: bool = False) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        log = root / "calls.jsonl"
        provider = root / "codex-fixture"
        provider.write_text("#!" + sys.executable + "\n" + f'''
import json,sys
from pathlib import Path
log = Path({str(log)!r})
args = sys.argv[1:]
assert args[:5] == ["termux", "profile", "use", "account", "--"]
assert sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()
previous = log.read_text() if log.exists() else ""
with log.open("a") as stream: stream.write(json.dumps(args) + "\\n")
if args[-1] == "login" and {login_failure!r}: sys.exit(2)
if args[-1] in {{"logout", "login"}}: sys.exit(0)
assert args[5:] == ["resume", "thread"]
if not previous:
    print({error!r}, file=sys.stderr)
    sys.exit(1)
sys.exit(0)
''')
        provider.chmod(0o700)
        plan = ai_plan.ExecutionPlan(
            argv=[str(provider), "termux", "profile", "use", "account", "--", "resume", "thread"],
            env={}, cwd=directory, display="", auth_recovery=True,
        )
        pid, master = pty.fork()
        if pid == 0:
            os.chdir(directory)
            try:
                status = ai_plan.execute_codex_with_recovery(plan, os.environ.copy())
            except BaseException:
                import traceback
                traceback.print_exc()
                os._exit(99)
            os._exit(status)
        output = b""
        answered = False
        deadline = time.monotonic() + 15
        try:
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.2)[0]:
                    try:
                        chunk = os.read(master, 8192)
                    except OSError as exc:
                        if exc.errno == errno.EIO:
                            break
                        raise
                    if not chunk:
                        break
                    output += chunk
                    if b"[y/N]" in output and not answered:
                        os.write(master, (answer + "\n").encode())
                        answered = True
            else:
                os.kill(pid, signal.SIGKILL)
                raise AssertionError("recovery timed out")
        finally:
            os.close(master)
            _, status = os.waitpid(pid, 0)
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        assert [args[-1] for args in calls] == expected, (calls, output)
        assert os.waitstatus_to_exitcode(status) == (2 if login_failure else 0 if answer == "y" and len(expected) == 4 else 1), output
        assert answered == (len(expected) > 1 or answer == "n"), output


def main() -> None:
    assert ai_plan.authentication_failed("unexpected status 401 Unauthorized")
    assert not ai_plan.authentication_failed("workspace routing discovery timed out (code -32603)")
    run_case("unexpected status 401 Unauthorized", "y", ["thread", "logout", "login", "thread"])
    run_case("refresh_token_expired", "n", ["thread"])
    run_case("refresh_token_expired", "y", ["thread", "logout", "login"], login_failure=True)
    run_case("workspace routing discovery timed out (code -32603)", "", ["thread"])
    print("PASS recovery acceptance, decline, timeout, PTY preservation, and same-account retry")


if __name__ == "__main__":
    main()
