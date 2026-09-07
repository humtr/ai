#!/usr/bin/env python3
from __future__ import annotations
import os, shlex
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
@dataclass(frozen=True)
class ExecutionPlan:
    argv: list[str]
    env: dict[str,str]
    cwd: str
    display: str
    warnings: list[str]=field(default_factory=list)
    session: dict[str,Any]|None=None
    def as_dict(self): return asdict(self)

def _display(argv:list[str], cwd:str, env:dict[str,str]) -> str:
    env_part=" ".join(f"{k}={shlex.quote(v)}" for k,v in sorted(env.items()))
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
    cmdspec=ai_spec.command_spec(spec.command); typ=cmdspec.get("type")
    provider=spec.provider or ""
    if provider not in ai_spec.provider_names(): raise SystemExit(f"ERROR: unknown provider: {provider}")
    pspec=ai_spec.provider_spec(provider); binary=str(pspec.get("binary") or provider); profile=spec.profile or "default"
    profile_args, env = ai_provider.apply_profile(provider, profile)
    session_row=None; session_ref=spec.session_ref
    directory=spec.directory
    warnings=[]
    if typ == "launch" and session_ref:
        found=ai_session.resolve_session(session_ref, provider=provider, profile=profile)
        if not found:
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
            session_profile = str(found.get("profile") or "default")
            if not directory and found.get("workdir"):
                found_workdir=str(found.get("workdir"))
                if Path(found_workdir).expanduser().is_dir():
                    directory=found_workdir
                else:
                    warnings.append(f"session workdir is missing; using current directory: {found_workdir}")
            
            # Cross-profile session auto-sharing/symlinking
            if session_profile != profile:
                try:
                    src_path = Path(found["path"])
                    if provider == "codex":
                        base_A = Path("~/.codex/sessions").expanduser() if session_profile == "default" else Path(f"~/.codex-profiles/{session_profile}/sessions").expanduser()
                        base_B = Path("~/.codex/sessions").expanduser() if profile == "default" else Path(f"~/.codex-profiles/{profile}/sessions").expanduser()
                    elif provider == "agy":
                        base_A = Path("~/.gemini").expanduser() if session_profile == "default" else Path(f"~/.agy-profiles/{session_profile}/.gemini").expanduser()
                        base_B = Path("~/.gemini").expanduser() if profile == "default" else Path(f"~/.agy-profiles/{profile}/.gemini").expanduser()
                    elif provider == "hermes":
                        base_A = Path("~/.hermes/sessions").expanduser() if session_profile == "default" else Path(f"~/.hermes/profiles/{session_profile}/sessions").expanduser()
                        base_B = Path("~/.hermes/sessions").expanduser() if profile == "default" else Path(f"~/.hermes/profiles/{profile}/sessions").expanduser()
                    elif provider == "opencode":
                        base_A = Path("~/.local/share/opencode").expanduser() if session_profile == "default" else Path(f"~/.opencode-profiles/{session_profile}/.local/share/opencode").expanduser()
                        base_B = Path("~/.local/share/opencode").expanduser() if profile == "default" else Path(f"~/.opencode-profiles/{profile}/.local/share/opencode").expanduser()
                    else:
                        base_A = None
                        base_B = None

                    if base_A and base_B:
                        if provider == "agy":
                            conv_id = str(found.get("native_session_ref") or found.get("session_id") or "")
                            agy_A = base_A / "antigravity-cli"
                            agy_B = base_B / "antigravity-cli"
                            if conv_id:
                                db_A = agy_A / "conversations" / f"{conv_id}.db"
                                db_B = agy_B / "conversations" / f"{conv_id}.db"
                                if db_A.exists() and not db_B.exists():
                                    db_B.parent.mkdir(parents=True, exist_ok=True)
                                    try:
                                        db_B.symlink_to(db_A)
                                    except Exception:
                                        import shutil
                                        shutil.copy2(db_A, db_B)
                                brain_A = agy_A / "brain" / conv_id
                                brain_B = agy_B / "brain" / conv_id
                                if brain_A.exists() and not brain_B.exists():
                                    brain_B.parent.mkdir(parents=True, exist_ok=True)
                                    try:
                                        brain_B.symlink_to(brain_A)
                                    except Exception:
                                        import shutil
                                        shutil.copytree(brain_A, brain_B)
                        try:
                            rel_path = src_path.relative_to(base_A)
                        except ValueError:
                            rel_path = Path(src_path.name)
                        dst_path = base_B / rel_path
                        if not dst_path.exists():
                            dst_path.parent.mkdir(parents=True, exist_ok=True)
                            try:
                                dst_path.symlink_to(src_path)
                            except Exception:
                                import shutil
                                shutil.copy2(src_path, dst_path)
                except Exception as e:
                    warnings.append(f"failed to share session between profiles: {e}")

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
    return ExecutionPlan(argv=argv, env=env, cwd=cwd, display=_display(argv,cwd,env), warnings=warnings, session=session_row)

def execute_plan(plan: ExecutionPlan) -> int:
    env=os.environ.copy(); env.update(plan.env)
    if os.environ.get("AI_DRY_RUN"):
        import json; print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2)); return 0
    try:
        os.chdir(plan.cwd)
    except OSError as e:
        raise SystemExit(f"ERROR: cannot change directory to {plan.cwd}: {e}")
    os.execvpe(plan.argv[0], plan.argv, env)
