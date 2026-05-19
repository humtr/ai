#!/usr/bin/env python3
from __future__ import annotations
import json, os, shutil, subprocess, sys
from pathlib import Path
import ai_spec, ai_provider, ai_session, ai_store

def print_rows(rows):
    for r in rows: print("\t".join(str(x) for x in r))

def provider_cmd(argv:list[str]) -> int:
    sub=argv[0] if argv else "list"
    if sub=="list":
        print_rows([[n, ai_spec.provider_spec(n).get("label", n)] for n in ai_spec.provider_names()]); return 0
    if sub=="show" and len(argv)>=2:
        print(json.dumps(ai_spec.provider_spec(argv[1]), ensure_ascii=False, indent=2)); return 0
    if sub=="check" and len(argv)>=2:
        info=ai_provider.provider_check(argv[1]); info["binary_found"] = bool(shutil.which(info["binary"])); print(json.dumps(info, ensure_ascii=False, indent=2)); return 0
    print("Usage: ai provider list|show PROVIDER|check PROVIDER", file=sys.stderr); return 2

def profile_cmd(argv:list[str]) -> int:
    sub=argv[0] if argv else "list"
    if sub=="list":
        provider=argv[1] if len(argv)>1 else None
        providers=[provider] if provider else ai_spec.provider_names()
        for p in providers:
            for prof in ai_provider.list_profiles(p): print(f"{p}\t{prof}")
        return 0
    if sub=="show" and len(argv)>=3:
        p, prof=argv[1], argv[2]; base=ai_provider.profile_base_dir(p); path=(base/prof) if base and prof!="default" else None
        print(json.dumps({"provider":p,"profile":prof,"path":str(path or ""),"exists":bool(path and path.exists())}, ensure_ascii=False, indent=2)); return 0
    print("Usage: ai profile list [PROVIDER] | show PROVIDER PROFILE", file=sys.stderr); return 2

def session_cmd(argv:list[str]) -> int:
    sub=argv[0] if argv else "list"; rest=argv[1:]
    provider=profile=workdir=None; limit=20; ranking="strict"; i=0
    while i < len(rest):
        a=rest[i]
        if a=="--provider": provider=rest[i+1]; i+=2
        elif a=="--profile": profile=rest[i+1]; i+=2
        elif a in {"-d","--directory"}: workdir=rest[i+1]; i+=2
        elif a=="--limit": limit=int(rest[i+1]); i+=2
        elif a=="--rank": ranking=rest[i+1]; i+=2
        else: break
    tail=rest[i:]
    if sub=="refresh": data=ai_session.refresh_session_index(limit=limit); print(f"indexed sessions: {len(data.get('sessions', []))}"); print(str(ai_store.SESSION_INDEX_FILE)); return 0
    if sub=="list":
        rows=ai_session.recent_sessions(provider,profile,workdir,limit,ranking)
        for r in rows:
            print("\t".join([str(r.get("provider","")),str(r.get("profile","")),str(r.get("updated","")),str(r.get("workdir","")),str(r.get("native_session_ref","")),str(r.get("title",""))]))
        return 0
    if sub in {"show","resolve"} and tail:
        r=ai_session.resolve_session(tail[0], provider=provider, profile=profile, workdir=workdir)
        if not r: print(f"ERROR: session not found: {tail[0]}", file=sys.stderr); return 1
        print(json.dumps(r, ensure_ascii=False, indent=2)); return 0
    print("Usage: ai session refresh|list|show REF|resolve REF", file=sys.stderr); return 2

def workdir_cmd(argv:list[str]) -> int:
    sub=argv[0] if argv else "list"; data=ai_store.load_workdirs()
    if sub=="list":
        for w in data.get("workdirs",[]):
            if not w.get("archived"):
                print("\t".join([str(w.get("name","")),str(w.get("path","")),str(w.get("purpose",""))]))
        return 0
    if sub=="add" and len(argv)>=3:
        name,path=argv[1],str(Path(argv[2]).expanduser()); data.setdefault("workdirs",[]).append({"name":name,"path":path,"purpose":"","favorite":False,"archived":False}); ai_store.save_workdirs(data); print(f"added workdir: {name} -> {path}"); return 0
    if sub=="archive" and len(argv)>=2:
        for w in data.get("workdirs",[]):
            if w.get("name")==argv[1]: w["archived"]=True; ai_store.save_workdirs(data); print(f"archived workdir: {argv[1]}"); return 0
        print(f"ERROR: workdir not found: {argv[1]}", file=sys.stderr); return 1
    print("Usage: ai workdir list|add NAME PATH|archive NAME", file=sys.stderr); return 2

def _hgm_cmd(args:list[str]) -> int:
    cmd=["hgm", *args]
    if os.environ.get("AI_DRY_RUN"):
        print(" ".join(cmd))
        return 0
    return subprocess.call(cmd)

def bridge_cmd(argv:list[str]) -> int:
    sub=argv[0] if argv else "status"
    allowed={"start","stop","restart","status","logs","log","test","config","set"}
    if sub not in allowed:
        print("Usage: ai bridge start|stop|restart|status|logs|test|config|set ...", file=sys.stderr)
        return 2
    return _hgm_cmd(["bridge", *argv])

def _gateway_profile(gateway_id:str) -> str | None:
    for g in ai_store.load_gateways().get("gateways", []):
        if g.get("id") == gateway_id and g.get("kind") == "telegram-gateway":
            return str(g.get("hermes_profile") or gateway_id)
    return None

def gateway_cmd(argv:list[str]) -> int:
    sub=argv[0] if argv else "list"; data=ai_store.load_gateways()
    if sub=="list":
        for g in data.get("gateways",[]): print("\t".join([str(g.get("id","")),str(g.get("kind","")),str(g.get("hermes_profile") or ""),str(g.get("bridge") or ""),str(g.get("manager") or "hgm")]))
        return 0
    if sub=="show" and len(argv)>=2:
        for g in data.get("gateways",[]):
            if g.get("id")==argv[1]: print(json.dumps(g, ensure_ascii=False, indent=2)); return 0
        print(f"ERROR: gateway not found: {argv[1]}", file=sys.stderr); return 1
    if sub=="status":
        return _hgm_cmd(["status"])
    if sub in {"start","stop","restart"} and len(argv)>=2:
        target=argv[1]
        profile=target if target=="all" else _gateway_profile(target)
        if not profile:
            print(f"ERROR: gateway not found: {target}", file=sys.stderr); return 1
        action="run" if sub=="start" else sub
        return _hgm_cmd([action, profile])
    if sub in {"logs","view"} and len(argv)>=2:
        target=argv[1]
        profile=_gateway_profile(target)
        if not profile:
            print(f"ERROR: gateway not found: {target}", file=sys.stderr); return 1
        return _hgm_cmd([sub, profile, *argv[2:]])
    print("Usage: ai gateway list|show ID|status|start|stop|restart TARGET|logs TARGET|view TARGET", file=sys.stderr); return 2
