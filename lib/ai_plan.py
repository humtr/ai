#!/usr/bin/env python3
from __future__ import annotations
import os, shlex, subprocess
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

def _session_argv(provider:str, binary:str, profile_args:list[str], strategy:str, ref:str|None, all_sessions:bool) -> list[str]:
    if strategy == "codex_resume":
        argv=[binary, *profile_args, "resume"]
        if all_sessions: argv.append("--all")
        if ref: argv.append(ref)
        return argv
    if all_sessions: raise SystemExit(f"ERROR: --all is not supported for {provider}")
    if strategy == "gemini_resume":
        return [binary, *profile_args, "--resume"] + ([ref] if ref else [])
    if strategy == "hermes_resume":
        return [binary, *profile_args, "--resume"] + ([ref] if ref else [])
    raise SystemExit(f"ERROR: provider {provider} does not support sessions")

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
        found=ai_session.resolve_session(session_ref, provider=provider, profile=None if profile=="default" else profile)
        if found and found.get("ambiguous"):
            ids="\n".join(f"  {m.get('provider')}/{m.get('profile')} {m.get('workdir')} {m.get('native_session_ref')} {m.get('title')}" for m in found.get("matches",[])[:8])
            raise SystemExit(f"ERROR: ambiguous session ref: {session_ref}\n{ids}")
        if found:
            session_row=found
            session_ref=str(found.get("native_session_ref") or found.get("session_id") or session_ref)
            if not directory and found.get("workdir"): directory=str(found.get("workdir"))
            if profile == "default" and found.get("profile") and found.get("profile") != "default":
                # Keep explicit CLI provider/profile predictable; warn rather than silently switch.
                warnings.append(f"session belongs to profile {found.get('profile')}; pass -p {found.get('profile')} to use that profile")
        elif not directory and not spec.here:
            raise SystemExit("ERROR: session workdir is unknown. Use -d/--directory DIR or --here.")
    cwd=ai_store.normalize_path(directory) if directory else str(Path.cwd())
    if typ == "launch":
        if session_ref:
            strategy=(pspec.get("session") or {}).get("strategy","none")
            argv=_session_argv(provider,binary,profile_args,strategy,session_ref,spec.all_sessions)
        else:
            if spec.all_sessions: raise SystemExit("ERROR: --all requires a session/picker-capable command")
            argv=[binary,*profile_args]
    elif typ == "native_passthrough":
        argv=[binary,*profile_args,*spec.native_args]
    elif typ == "inline_prompt":
        prompt=_guard(spec.command, spec.prompt or "")
        if provider == "codex": argv=[binary,*profile_args,"exec","--skip-git-repo-check",prompt]
        elif provider == "gemini": argv=[binary,*profile_args,"--skip-trust","-p",prompt]
        elif provider == "hermes": argv=[binary,*profile_args,"-z",prompt]
        else: argv=[binary,*profile_args,prompt]
    else:
        raise SystemExit(f"ERROR: unsupported command type: {typ}")
    return ExecutionPlan(argv=argv, env=env, cwd=cwd, display=_display(argv,cwd,env), warnings=warnings, session=session_row)

def execute_plan(plan: ExecutionPlan) -> int:
    env=os.environ.copy(); env.update(plan.env)
    if os.environ.get("AI_DRY_RUN"):
        import json; print(json.dumps(plan.as_dict(), ensure_ascii=False, indent=2)); return 0
    return subprocess.call(plan.argv, cwd=plan.cwd, env=env)
