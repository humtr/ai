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
    if sub=="add" and len(argv)>=3:
        p, prof=argv[1], argv[2]
        try:
            ai_provider.validate_profile_name(prof)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr); return 1
        if not ai_spec.provider_spec(p).get("profile", {}).get("supported", False):
            print(f"ERROR: provider {p} does not support profiles", file=sys.stderr); return 1
        base=ai_provider.profile_base_dir(p)
        if not base:
            print(f"ERROR: provider {p} has no profile base directory configured", file=sys.stderr); return 1
        path=base/prof
        try:
            path.mkdir(parents=True, exist_ok=True)
            print(f"added profile: {p}/{prof} -> {path}")
        except Exception as e:
            print(f"ERROR: failed to create profile directory: {e}", file=sys.stderr); return 1
        return 0
    if sub in {"delete", "remove"} and len(argv)>=3:
        p, prof=argv[1], argv[2]
        if prof == "default":
            print("ERROR: cannot delete 'default' profile", file=sys.stderr); return 1
        base=ai_provider.profile_base_dir(p)
        if not base:
            print(f"ERROR: provider {p} has no profile base directory configured", file=sys.stderr); return 1
        path=base/prof
        if path.is_dir():
            try:
                shutil.rmtree(path)
                print(f"deleted profile: {p}/{prof}")
            except Exception as e:
                print(f"ERROR: failed to delete profile directory: {e}", file=sys.stderr); return 1
        else:
            print(f"ERROR: profile not found: {p}/{prof}", file=sys.stderr); return 1
        return 0
    print("Usage: ai profile list [PROVIDER] | show PROVIDER PROFILE | add PROVIDER PROFILE | delete PROVIDER PROFILE", file=sys.stderr); return 2

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

