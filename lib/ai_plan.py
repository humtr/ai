#!/usr/bin/env python3
from __future__ import annotations
import os, shlex
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import ai_spec, ai_provider, ai_session, ai_store
@dataclass(frozen=True)
class LaunchSpec:
    command: str
    provider: str
    profile: str = "default"
    directory: str | None = None
    session_ref: str | None = None
    prompt: str | None = None
    native_args: list[str] = field(default_factory=list)
    here: bool = False
    all_sessions: bool = False
    tmux: bool | str = False
@dataclass(frozen=True)
class ExecutionPlan:
    argv: list[str]
    env: dict[str,str]
    cwd: str
    display: str
    warnings: list[str]=field(default_factory=list)
    session: dict[str,Any]|None=None
    tmux_provider: str | None = None
    tmux_status: bool = False
    auth_recovery: bool = False
    env_unset: list[str] = field(default_factory=list)
    def as_dict(self): return asdict(self)

def _display(argv:list[str], cwd:str, env:dict[str,str], env_unset:list[str]|None=None) -> str:
    env_part=" ".join(f"{k}={shlex.quote(v)}" for k,v in sorted(env.items()))
    if env_unset:
        argv = ["env", *[part for key in env_unset for part in ("-u", key)],
                *[f"{key}={value}" for key,value in sorted(env.items())], *argv]
        env_part = ""
    cmd=shlex.join(argv)
    prefix=f"cd {shlex.quote(cwd)} && " if cwd else ""
    return prefix + ((env_part + " ") if env_part else "") + cmd

def _guard(command:str, prompt:str) -> str:
    if command in {"ask","chat"}:
        return "도구, 검색, 파일 탐색, 파일 읽기, 파일 쓰기, 셸 실행을 사용하지 말고 답해. 이 지시는 보안 경계가 아니라 응답 방식 요청이다.\n\n" + prompt
    return prompt

def _session_argv(provider:str, binary:str, profile_args:list[str], strategy:str, ref:str|None, all_sessions:bool, native_args:list[str]|None=None) -> list[str]:
    extra=list(native_args or [])
    if strategy == "codex_resume":
        argv=[binary, *profile_args, *extra, "resume"]
        if all_sessions: argv.append("--all")
        if ref: argv.append(ref)
        return argv
    if all_sessions: raise SystemExit(f"ERROR: --all is not supported for {provider}")
    if strategy == "agy_resume":
        return [binary, *profile_args, *extra, "--conversation"] + ([ref] if ref else [])
    if strategy == "hermes_resume":
        return [binary, *profile_args, *extra, "--resume"] + ([ref] if ref else [])
    if strategy == "opencode_resume":
        return [binary, *profile_args, *extra, "--session", ref] if ref else [binary, *profile_args, *extra, "--continue"]
    raise SystemExit(f"ERROR: provider {provider} does not support sessions")


def session_provider_warning(source_provider: str | None, target_provider: str | None) -> str:
    source = str(source_provider or "").strip()
    target = str(target_provider or "").strip()
    if not source or not target or source == target:
        return ""
    return (
        f"WARNING: refusing cross-provider session share: source provider '{source}', "
        f"target provider '{target}'. Select the same provider in ai tui; "
        "profile differences are shared by default within one provider."
    )


def build_execution_plan(spec: LaunchSpec) -> ExecutionPlan:
    if spec.tmux not in (False, True, "hidden", "status"):
        raise SystemExit("ERROR: invalid tmux mode")
    cmdspec=ai_spec.command_spec(spec.command); typ=cmdspec.get("type")
    provider=spec.provider or ""
    if provider not in ai_spec.provider_names(): raise SystemExit(f"ERROR: unknown provider: {provider}")
    pspec=ai_spec.provider_spec(provider); binary=str(pspec.get("binary") or provider); profile=spec.profile or "default"
    profile_args, env = ai_provider.apply_profile(provider, profile)
    session_row=None; session_ref=spec.session_ref
    directory=spec.directory
    warnings=[]
    if typ == "launch" and session_ref:
        found=ai_session.resolve_session(session_ref, provider=provider, profile=None)
        if not found:
            found=ai_session.resolve_session(session_ref, provider=None, profile=None)
        if found and found.get("ambiguous"):
            ids="\n".join(f"  {m.get('provider')}/{m.get('profile')} {m.get('workdir')} {m.get('native_session_ref')} {m.get('title')}" for m in found.get("matches",[])[:8])
            raise SystemExit(f"ERROR: ambiguous session ref: {session_ref}\n{ids}")
        if found:
            session_row=found
            session_ref=str(found.get("native_session_ref") or found.get("session_id") or session_ref)
            source_provider = str(found.get("provider") or provider)
            provider_warning = session_provider_warning(source_provider, provider)
            if provider_warning:
                raise SystemExit(provider_warning)
            if not directory and found.get("workdir"):
                found_workdir=str(found.get("workdir"))
                if Path(found_workdir).expanduser().is_dir():
                    directory=found_workdir
                else:
                    warnings.append(f"session workdir is missing; using current directory: {found_workdir}")

        elif not directory and not spec.here:
            raise SystemExit("ERROR: session workdir is unknown. Use -d/--directory DIR or --here.")
    if directory:
        p = Path(directory).expanduser()
        if not p.is_dir():
            raise SystemExit(f"ERROR: directory not found: {directory}")
        cwd = ai_store.normalize_path(directory)
    else:
        cwd = str(Path.cwd())
    if typ == "launch":
        if session_ref:
            strategy=(pspec.get("session") or {}).get("strategy","none")
            argv=_session_argv(provider,binary,profile_args,strategy,session_ref,spec.all_sessions,spec.native_args)
        else:
            if spec.all_sessions: raise SystemExit("ERROR: --all requires a session/picker-capable command")
            argv=[binary,*profile_args,*spec.native_args]
    elif typ == "native_passthrough":
        argv=[binary,*profile_args,*spec.native_args]
    elif typ == "inline_prompt":
        prompt=_guard(spec.command, spec.prompt or "")
        if provider == "codex": argv=[binary,*profile_args,"exec","--skip-git-repo-check",prompt]
        elif provider == "agy": argv=[binary,*profile_args,"--dangerously-skip-permissions","-p",prompt]
        elif provider == "hermes": argv=[binary,*profile_args,"-z",prompt]
        elif provider == "opencode": argv=[binary,*profile_args,"run",prompt]
        else: argv=[binary,*profile_args,prompt]
    else:
        raise SystemExit(f"ERROR: unsupported command type: {typ}")
    env_unset = []
    if provider == "codex" and not profile_args:
        _, env_unset = ai_provider.ai_codex_manager.launch_profile(profile)
        warnings.append("using existing legacy Codex profile home" if env.get("CODEX_HOME", "").startswith(str(Path.home() / ".codex-profiles") + "/") else "codex manager unavailable; using its local profile contract")
    return ExecutionPlan(env_unset=env_unset, argv=argv, env=env, cwd=cwd, display=_display(argv,cwd,env,env_unset), warnings=warnings, session=session_row, tmux_provider=provider if spec.tmux else None, tmux_status=spec.tmux == "status", auth_recovery=provider == "codex" and typ == "launch")

def execute_plan(plan: ExecutionPlan) -> int:
    env=os.environ.copy()
    for key in plan.env_unset:
        env.pop(key, None)
    env.update(plan.env)
    if os.environ.get("AI_DRY_RUN"):
        import json; print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2)); return 0
    for warning in plan.warnings:
        print(f"ai: {warning}", file=sys.stderr)
    if plan.tmux_provider:
        import ai_tmux
        try:
            return ai_tmux.launch(plan, plan.tmux_provider)
        except (OSError, ValueError, RuntimeError) as error:
            raise SystemExit("ERROR: tmux launch failed") from error
    try:
        os.chdir(plan.cwd)
    except OSError as e:
        raise SystemExit(f"ERROR: cannot change directory to {plan.cwd}: {e}")
    if (plan.auth_recovery or managed_codex_plan(plan)) and sys.stdin.isatty():
        return execute_codex_with_recovery(plan, env)
    if managed_codex_plan(plan):
        return execute_managed_codex(plan, env)
    os.execvpe(plan.argv[0], plan.argv, env)



def managed_codex_plan(plan: ExecutionPlan) -> bool:
    return len(plan.argv) >= 6 and plan.argv[1:4] == ["termux", "profile", "use"] and plan.argv[5] == "--"


def manager_launch_failed(output: str, status: int) -> bool:
    import re
    text = re.sub(r"\x1b\[[0-9;]*m", "", output).lower().replace("\r", "")
    if text.strip() == "codex termux manager is unavailable.":
        return True  # Core reports an absent optional Manager with status zero.
    if status not in {1, 2}:
        return False
    return bool(re.search(
        r"(?m)^codex termux: (?:core handoff is invalid|core launch failed|invalid command|"
        r"profile is unavailable|manager path is unsafe|home is invalid)\s*$", text,
    ))


def fallback_codex_plan(plan: ExecutionPlan) -> ExecutionPlan:
    from dataclasses import replace
    selected = plan.argv[4]
    profile_env, unset = ai_provider.ai_codex_manager.launch_profile(selected)
    env = dict(plan.env)
    for key in unset:
        env.pop(key, None)
    env.update(profile_env)
    argv = [plan.argv[0], *plan.argv[6:]]
    print(f"ai: codex manager unavailable; using local manager profile {selected}", file=sys.stderr)
    return replace(plan, argv=argv, env=env, env_unset=list(dict.fromkeys([*plan.env_unset, *unset])),
                   display=_display(argv, plan.cwd, env, unset))


def execute_managed_codex(plan: ExecutionPlan, env: dict[str, str]) -> int:
    # No terminal in this path. Stream both channels, keeping only a bounded tail.
    import selectors
    process = subprocess.Popen(plan.argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    tail = b""
    with selectors.DefaultSelector() as selector:
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, sys.stdout.buffer)
        selector.register(process.stderr, selectors.EVENT_READ, sys.stderr.buffer)
        while selector.get_map():
            for key, _ in selector.select():
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                key.data.write(chunk)
                key.data.flush()
                tail = (tail + chunk)[-32768:]
    status = process.wait()
    if manager_launch_failed(tail.decode("utf-8", errors="replace"), status):
        return execute_plan(fallback_codex_plan(plan))
    return status

def authentication_failed(output: str) -> bool:
    text = output.lower()
    return any(marker in text for marker in (
        "401 unauthorized", "http 401", "status code 401", "status: 401",
        "refresh_token_expired", "refresh_token_reused", "refresh_token_invalid",
        "token has expired", "authentication token is expired",
    ))


def execute_codex_with_recovery(plan: ExecutionPlan, env: dict[str, str]) -> int:
    # A PTY preserves upstream TUI terminal checks and captures errors drawn on
    # either output stream. pty.spawn restores the caller's terminal on exit.
    import pty
    import signal
    import termios

    def launch() -> tuple[int, str]:
        tail = b""
        master_fd: int | None = None

        def resize(*_args) -> None:
            if master_fd is not None and sys.stdin.isatty():
                try:
                    termios.tcsetwinsize(master_fd, termios.tcgetwinsize(sys.stdin.fileno()))
                except OSError:
                    pass

        def read_output(fd: int) -> bytes:
            nonlocal tail, master_fd
            master_fd = fd
            resize()
            chunk = os.read(fd, 4096)
            tail = (tail + chunk)[-32768:]
            return chunk

        size = termios.tcgetwinsize(sys.stdin.fileno()) if sys.stdin.isatty() else (24, 80)
        child_code = (
            "import os,sys,termios; "
            "termios.tcsetwinsize(0,(int(sys.argv[1]),int(sys.argv[2]))); "
            "os.execvpe(sys.argv[3],sys.argv[3:],os.environ)"
        )
        old_values = {key: os.environ.get(key) for key in {*plan.env, *plan.env_unset}}
        old_resize = signal.signal(signal.SIGWINCH, resize)
        for key in plan.env_unset:
            os.environ.pop(key, None)
        os.environ.update(plan.env)
        try:
            status = pty.spawn(
                [sys.executable, "-c", child_code, str(size[0]), str(size[1]), *plan.argv],
                master_read=read_output,
            )
            return os.waitstatus_to_exitcode(status), tail.decode("utf-8", errors="replace")
        finally:
            for key, value in old_values.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            signal.signal(signal.SIGWINCH, old_resize)
    status, errors = launch()
    if managed_codex_plan(plan) and manager_launch_failed(errors, status):
        return execute_plan(fallback_codex_plan(plan))
    if not status:
        return status
    if not plan.auth_recovery or not authentication_failed(errors) or not sys.stdin.isatty():
        if "workspace routing discovery timed out" in errors.lower():
            print("ai: workspace routing discovery timed out; this does not establish token expiry. Check the codex shared server/routing layer.", file=sys.stderr)
        return status
    print("ai: 인증을 사용할 수 없습니다. 선택한 계정에서 로그아웃 후 다시 로그인하고 세션을 재개할까요? [y/N] ", end="", file=sys.stderr, flush=True)
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        return status
    if answer not in {"y", "yes", "예"}:
        return status
    prefix = plan.argv[:6] if plan.argv[1:4] == ["termux", "profile", "use"] else plan.argv[:1]
    for action in ("logout", "login"):
        result = subprocess.run([*prefix, action], env=env)
        if result.returncode:
            return result.returncode
    return launch()[0]
