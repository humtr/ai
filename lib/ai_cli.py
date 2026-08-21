#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from pathlib import Path
import ai_spec, ai_plan, ai_resource

def usage() -> None:
    print("""ai = config-driven AI launcher

Common command model:
  ai run <provider> --cwd DIR -- native args
  --cwd DIR, --cd DIR, -C DIR set the working directory.
  No --profile uses the provider's official default home.
  Profile names "default" and "native" are reserved and rejected.

Core:
  ai run <provider> [-p PROFILE] [--cwd DIRECTORY] [-s SESSION]
  ai ask <provider> [-p PROFILE] -- "prompt"
  ai chat <provider> [-p PROFILE] -- "prompt"
  ai raw <provider> [-p PROFILE] -- <native args>

Resources:
  ai provider list|show|check
  ai profile list|show|add|delete
  ai session refresh|list|show|resolve
  ai workdir list|add|archive
  ai tui

Removed:
  legacy wrappers and bridges (use ai run -s / clip instead)
""")

def _require_value(args:list[str], i:int, option:str) -> str:
    if i + 1 >= len(args) or args[i + 1] == "--":
        raise SystemExit(f"{option} requires a value")
    return args[i + 1]

def parse_common(args:list[str]):
    profile="default"; directory=None; session=None; here=False; all_sessions=False; out=[]; i=0
    while i < len(args):
        a=args[i]
        if a in {"-p","--profile"}:
            value=_require_value(args, i, a)
            if value in {"default", "native"}:
                raise SystemExit(f"invalid or reserved profile name: {value}")
            profile=value; i+=2
        elif a in {"-s","--session"}:
            session=_require_value(args, i, a); i+=2
        elif a in {"-d","--directory","--cwd","--cd","-C"}:
            directory=_require_value(args, i, a); i+=2
        elif a=="--account": raise SystemExit("--account was removed; use --profile NAME")
        elif a=="--home": raise SystemExit("--home was removed; use --profile NAME")
        elif a=="--here": here=True; i+=1
        elif a=="--all": all_sessions=True; i+=1
        elif a=="--": out.extend(args[i+1:]); break
        else: out.append(a); i+=1
    return profile,directory,session,here,all_sessions,out

def run_command(command:str, argv:list[str]) -> int:
    if not argv: print(f"Usage: ai {command} <provider> ...", file=sys.stderr); return 2
    provider=argv[0]
    if not ai_spec.is_provider(provider): print(f"ERROR: unknown provider: {provider}", file=sys.stderr); return 2
    try:
        profile,directory,session,here,all_sessions,rest=parse_common(argv[1:])
    except SystemExit as e:
        msg=str(e)
        if msg and msg != "0": print(msg, file=sys.stderr)
        return int(e.code) if isinstance(e.code,int) else 2
    prompt=None; native_args=[]
    typ=ai_spec.command_spec(command).get("type")
    if typ=="inline_prompt": prompt=" ".join(rest).strip();
    elif typ=="native_passthrough": native_args=rest
    elif rest: print(f"ERROR: unexpected arguments for {command}: {' '.join(rest)}", file=sys.stderr); return 2
    try:
        spec=ai_plan.LaunchSpec(command=command, provider=provider, profile=profile, directory=directory, session_ref=session, prompt=prompt, native_args=native_args, here=here, all_sessions=all_sessions)
        plan=ai_plan.build_execution_plan(spec)
        return ai_plan.execute_plan(plan)
    except SystemExit as e:
        msg=str(e)
        if msg and msg != "0": print(msg, file=sys.stderr)
        return int(e.code) if isinstance(e.code,int) else 2

def json_cmd(argv:list[str]) -> int:
    sub=argv[0] if argv else ""
    if sub=="providers": print(json.dumps(ai_spec.provider_names(), ensure_ascii=False)); return 0
    if sub=="profiles": import ai_provider; print(json.dumps(ai_provider.list_profiles(argv[1]), ensure_ascii=False)); return 0
    if sub=="commands": print(json.dumps(ai_spec.command_names(tui_visible=True), ensure_ascii=False)); return 0
    if sub=="sessions": import ai_session; provider=argv[1] if len(argv)>1 and argv[1] else None; profile=argv[2] if len(argv)>2 and argv[2] else None; scope=argv[3] if len(argv)>3 else "profile"; p=provider if scope in {"profile","provider"} else None; pr=profile if scope=="profile" else None; print(json.dumps(ai_session.recent_sessions(p, pr, None, 80, "strict"), ensure_ascii=False)); return 0
    if sub=="plan":
        command,provider,profile,directory,session=argv[1],argv[2],argv[3],argv[4] or None,argv[5] or None
        plan=ai_plan.build_execution_plan(ai_plan.LaunchSpec(command=command,provider=provider,profile=profile,directory=directory,session_ref=session)); print(json.dumps(plan.as_dict(), ensure_ascii=False)); return 0
    return 2

def main(argv:list[str]|None=None) -> int:
    argv=list(sys.argv[1:] if argv is None else argv)
    if not argv:
        if sys.stdin.isatty() and sys.stdout.isatty(): return tui_cmd([])
        usage(); return 0
    cmd=argv.pop(0)
    if cmd in {"-h","--help","help"}: usage(); return 0
    if cmd=="__json": return json_cmd(argv)
    if ai_spec.is_provider(cmd): print(f"ERROR: provider-first syntax is not supported: ai {cmd}\nUse: ai run {cmd} ...", file=sys.stderr); return 2
    if cmd=="resume": print("ERROR: subcommand 'resume' is not available.\nUse: ai run <provider> -s <session-ref>", file=sys.stderr); return 2
    if cmd in {"cm","gm","hm"}: print(f"ERROR: ai {cmd} is disabled to avoid double wrapping.", file=sys.stderr); return 2
    if cmd in {"run","ask","chat","raw"}: return run_command(cmd, argv)
    if cmd=="provider": return ai_resource.provider_cmd(argv)
    if cmd=="profile": return ai_resource.profile_cmd(argv)
    if cmd=="session": return ai_resource.session_cmd(argv)
    if cmd=="workdir": return ai_resource.workdir_cmd(argv)
    if cmd in {"bridge", "gateway", "gw"}:
        print(f"ERROR: ai {cmd} was moved to clip proxy suite. Use: clip ...", file=sys.stderr); return 2
    if cmd=="tui": return tui_cmd(argv)
    if cmd=="status":
        ai_resource.provider_cmd(["list"]); return 0
    print(f"ERROR: unknown ai command: {cmd}", file=sys.stderr); return 2

def tui_cmd(argv:list[str]) -> int:
    lib=Path(__file__).resolve().parent; tui=lib/"ai_tui.py"
    os.execv(sys.executable, [sys.executable, str(tui), *argv])
if __name__ == "__main__": raise SystemExit(main())
