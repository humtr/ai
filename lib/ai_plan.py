#!/usr/bin/env python3
from __future__ import annotations
import base64, json, os, shlex
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
    if strategy == "agy_resume":
        return [binary, *profile_args, "--conversation"] + ([ref] if ref else [])
    if strategy == "hermes_resume":
        return [binary, *profile_args, "--resume"] + ([ref] if ref else [])
    if strategy == "opencode_resume":
        return [binary, *profile_args, "--session", ref] if ref else [binary, *profile_args, "--continue"]
    raise SystemExit(f"ERROR: provider {provider} does not support sessions")

def _decode_jwt_claims(token: str) -> dict[str, Any]:
    if token.count(".") < 2: return {}
    payload = token.split(".", 2)[1]
    payload += "=" * ((4 - len(payload) % 4) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return {}
    return claims if isinstance(claims, dict) else {}

def _codex_profile_home(profile: str) -> Path:
    return ai_store.HOME / ".codex" if profile == "default" else ai_store.HOME / ".codex-profiles" / profile

def _codex_auth_identity(profile: str) -> dict[str, str]:
    path = _codex_profile_home(profile) / "auth.json"
    if not path.is_file(): return {"mode": "none"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"mode": "invalid"}
    mode = str(data.get("auth_mode") or "unknown")
    if mode == "chatgpt":
        tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else {}
        id_claims = _decode_jwt_claims(str(tokens.get("id_token") or ""))
        access_claims = _decode_jwt_claims(str(tokens.get("access_token") or ""))
        return {
            "mode": mode,
            "subject": str(id_claims.get("sub") or access_claims.get("sub") or ""),
            "account_id": str(tokens.get("account_id") or ""),
        }
    if mode == "apikey":
        return {"mode": mode, "api_key": str(data.get("OPENAI_API_KEY") or "")}
    return {"mode": mode}

def _codex_session_boundary_reason(source_profile: str, target_profile: str) -> str:
    if source_profile == target_profile: return ""
    if os.environ.get("CODEX_SESSION_ALLOW_CROSS_AUTH", "").lower() in {"1", "true", "yes"}: return ""
    source = _codex_auth_identity(source_profile)
    target = _codex_auth_identity(target_profile)
    if source.get("mode") in {"none", "invalid"} or target.get("mode") in {"none", "invalid"}: return ""
    if source.get("mode") != target.get("mode"):
        return f"source auth mode {source.get('mode')!r} differs from target auth mode {target.get('mode')!r}"
    if source.get("mode") == "chatgpt":
        if source.get("subject") and target.get("subject") and source.get("subject") != target.get("subject"):
            return "source ChatGPT user differs from target profile"
        if source.get("account_id") and target.get("account_id") and source.get("account_id") != target.get("account_id"):
            return "source ChatGPT account/workspace differs from target profile"
    if source.get("mode") == "apikey":
        if source.get("api_key") and target.get("api_key") and source.get("api_key") != target.get("api_key"):
            return "source API key differs from target profile"
    return ""

def _require_session_boundary(provider: str, source_profile: str, target_profile: str) -> None:
    if provider != "codex": return
    reason = _codex_session_boundary_reason(source_profile, target_profile)
    if not reason:
        return

    # Check if we can prompt the user interactively
    is_interactive = False
    try:
        import sys
        is_interactive = (
            sys.stdin
            and hasattr(sys.stdin, "isatty")
            and sys.stdin.isatty()
            and sys.stdout
            and hasattr(sys.stdout, "isatty")
            and sys.stdout.isatty()
        )
    except Exception:
        pass

    if is_interactive:
        import sys
        sys.stderr.write(
            f"\nWARNING: Refusing cross-profile Codex session resume/share: {source_profile} -> {target_profile}: {reason}.\n"
            f"To override this check manually, you can set CODEX_SESSION_ALLOW_CROSS_AUTH=1.\n\n"
            f"Choose an option:\n"
            f"  1) Reset authentication on target profile '{target_profile}' (forces re-login on next start) [Recommended]\n"
            f"  2) Proceed anyway (override this check for this action)\n"
            f"  3) Abort execution\n"
        )
        sys.stderr.flush()
        
        try:
            sys.stderr.write("Enter choice [1-3] (default 3): ")
            sys.stderr.flush()
            choice = sys.stdin.readline().strip()
        except (KeyboardInterrupt, EOFError):
            sys.stderr.write("\n")
            sys.stderr.flush()
            choice = "3"

        if choice == "1":
            auth_path = _codex_profile_home(target_profile) / "auth.json"
            if auth_path.is_file():
                try:
                    auth_path.unlink()
                    sys.stderr.write(f"Successfully reset authentication on profile '{target_profile}'.\n")
                    sys.stderr.flush()
                    # Re-verify the boundary after deletion
                    reason = _codex_session_boundary_reason(source_profile, target_profile)
                    if not reason:
                        return
                except OSError as e:
                    sys.stderr.write(f"Error resetting authentication: {e}\n")
                    sys.stderr.flush()
            else:
                sys.stderr.write(f"No authentication file found for profile '{target_profile}'.\n")
                sys.stderr.flush()
                reason = _codex_session_boundary_reason(source_profile, target_profile)
                if not reason:
                    return
        elif choice == "2":
            sys.stderr.write("Overriding check and proceeding...\n")
            sys.stderr.flush()
            return

    raise SystemExit(
        "ERROR: refusing cross-profile Codex session resume/share: "
        f"{source_profile} -> {target_profile}: {reason}. "
        "Set CODEX_SESSION_ALLOW_CROSS_AUTH=1 to override explicitly."
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
        if found and found.get("ambiguous"):
            ids="\n".join(f"  {m.get('provider')}/{m.get('profile')} {m.get('workdir')} {m.get('native_session_ref')} {m.get('title')}" for m in found.get("matches",[])[:8])
            raise SystemExit(f"ERROR: ambiguous session ref: {session_ref}\n{ids}")
        if found:
            session_row=found
            session_ref=str(found.get("native_session_ref") or found.get("session_id") or session_ref)
            session_profile = found.get("profile") or "default"
            if not directory and found.get("workdir"):
                found_workdir=str(found.get("workdir"))
                if Path(found_workdir).expanduser().is_dir():
                    directory=found_workdir
                else:
                    warnings.append(f"session workdir is missing; using current directory: {found_workdir}")
            
            # Cross-profile session auto-sharing/symlinking
            if session_profile != profile:
                _require_session_boundary(provider, str(session_profile), str(profile))
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
    os.chdir(plan.cwd)
    os.execvpe(plan.argv[0], plan.argv, env)
