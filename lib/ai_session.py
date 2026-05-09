#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from typing import Any
import ai_store, ai_spec
HOME=ai_store.HOME
SESSION_SCAN_LIMIT=int(os.environ.get("AI_SESSION_SCAN_LIMIT","500"))

def compact_text(value: Any) -> str:
    if value is None: return ""
    if isinstance(value, str): return re.sub(r"\s+"," ",value).strip()
    if isinstance(value, list): return compact_text(" ".join(compact_text(x) for x in value if x))
    if isinstance(value, dict):
        for k in ("text","content","message","value"):
            if k in value:
                t=compact_text(value.get(k))
                if t: return t
    return compact_text(str(value))

def text_summary(value: Any, limit:int=260) -> str:
    text=compact_text(value)
    if len(text)<=limit: return text
    return text[:max(1,limit-1)].rstrip()+"..."

def iso_from_mtime(path: Path) -> str: return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(path.stat().st_mtime))
def safe_stat(path: Path):
    try: return path.stat()
    except OSError: return None

def read_project_root(path: Path) -> str:
    try: v=path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError: return ""
    return str(Path(v).expanduser()) if v else ""

def codex_session_id(path: Path) -> str:
    stem=path.stem; return re.sub(r"^rollout-[0-9TZ:-]+-", "", stem) or stem

def hermes_session_id(path: Path) -> str:
    stem=path.stem; return stem[len("session_"):] if stem.startswith("session_") else stem

def gemini_project_root(path: Path) -> str:
    for parent in path.parents:
        if parent.name == "chats":
            pr=parent.parent/".project_root"
            if pr.exists(): return read_project_root(pr)
            break
    return ""

def add_session_record(records:list[dict[str,Any]], provider:str, profile:str, path:Path, workdir_hint:str="") -> None:
    st=safe_stat(path)
    if st is None or not path.is_file(): return
    records.append({"provider":provider,"profile":profile,"path":path,"workdir_hint":workdir_hint,"mtime":st.st_mtime,"size":st.st_size})

def discover_session_files(limit:int=SESSION_SCAN_LIMIT) -> list[dict[str,Any]]:
    records=[]
    codex_sessions=HOME/".codex"/"sessions"
    if codex_sessions.is_dir():
        for p in codex_sessions.rglob("*.jsonl"): add_session_record(records,"codex","default",p)
    codex_profiles=HOME/".codex-profiles"
    if codex_profiles.is_dir():
        for ph in sorted(x for x in codex_profiles.iterdir() if x.is_dir()):
            s=ph/"sessions"
            if s.is_dir():
                for p in s.rglob("*.jsonl"): add_session_record(records,"codex",ph.name,p)
    def scan_gemini(root: Path, profile: str):
        tmp=root/"tmp"
        if not tmp.is_dir(): return
        for project_dir in sorted(x for x in tmp.iterdir() if x.is_dir()):
            chats=project_dir/"chats"
            if not chats.is_dir(): continue
            workdir=read_project_root(project_dir/".project_root")
            for p in chats.rglob("*.jsonl"): add_session_record(records,"gemini",profile,p,workdir)
    scan_gemini(HOME/".gemini","default")
    gemini_profiles=HOME/".gemini-profiles"
    if gemini_profiles.is_dir():
        for ph in sorted(x for x in gemini_profiles.iterdir() if x.is_dir()): scan_gemini(ph, ph.name)
    hs=HOME/".hermes"/"sessions"
    if hs.is_dir():
        for p in hs.iterdir():
            if p.suffix in {".json",".jsonl"} and p.name != "sessions.json": add_session_record(records,"hermes","default",p)
    hp=HOME/".hermes"/"profiles"
    if hp.is_dir():
        for ph in sorted(x for x in hp.iterdir() if x.is_dir()):
            s=ph/"sessions"
            if not s.is_dir(): continue
            for p in s.iterdir():
                if p.name == "sessions.json" or p.name.startswith("request_dump_"): continue
                if p.suffix in {".json",".jsonl"}: add_session_record(records,"hermes",ph.name,p)
    records.sort(key=lambda r: float(r.get("mtime") or 0), reverse=True)
    return records[:limit]

def add_message(messages:list[dict[str,str]], role:str, content:Any, timestamp:str="") -> None:
    if role not in {"user","assistant"}: return
    t=text_summary(content)
    if t: messages.append({"role":role,"text":t,"timestamp":timestamp})

def stable_session_key(row: dict[str,Any]) -> str:
    return "|".join([str(row.get("provider") or ""), str(row.get("profile") or "default"), ai_store.normalize_path(str(row.get("workdir") or "")), str(row.get("native_session_ref") or row.get("session_id") or "")])

def finalize(row: dict[str,Any]) -> dict[str,Any]:
    row["profile"] = str(row.get("profile") or "default")
    row["session_id"] = str(row.get("session_id") or row.get("native_session_ref") or "")
    row["native_session_ref"] = str(row.get("native_session_ref") or row.get("session_id") or "")
    row["workdir"] = ai_store.normalize_path(str(row.get("workdir") or ""))
    row["source_path"] = str(row.get("source_path") or row.get("path") or "")
    row["source"] = str(row.get("source") or row.get("source_path") or "")
    row["can_resume"] = bool(row.get("native_session_ref"))
    row["stable_session_key"] = stable_session_key(row)
    row["stable_key"] = row["stable_session_key"]
    return row

def entry_from_messages(record:dict[str,Any], meta:dict[str,Any], messages:list[dict[str,str]]) -> dict[str,Any]:
    path=Path(record["path"]); users=[m for m in messages if m.get("role")=="user"]; assistants=[m for m in messages if m.get("role")=="assistant"]; last=messages[-1] if messages else {}
    sid=str(meta.get("session_id") or path.stem); last_user=users[-1].get("text","") if users else ""; last_assistant=assistants[-1].get("text","") if assistants else ""; title=users[0].get("text","") if users else last_user or sid
    return finalize({"provider":record["provider"],"profile":record["profile"],"session_id":sid,"native_session_ref":sid,"title":text_summary(title,120) or sid,"last_prompt_summary":text_summary(last_user,360),"last_response_summary":text_summary(last_assistant,360),"updated":str(meta.get("updated") or last.get("timestamp") or iso_from_mtime(path)),"workdir":str(meta.get("workdir") or record.get("workdir_hint") or ""),"source":"session-file","source_path":str(path),"path":str(path),"mtime":record["mtime"],"size":record["size"]})

def parse_codex_session(record:dict[str,Any]) -> dict[str,Any]:
    path=Path(record["path"]); meta={"session_id":codex_session_id(path),"workdir":"","updated":""}; messages=[]; fallback=[]
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try: item=json.loads(line)
            except json.JSONDecodeError: continue
            payload=item.get("payload") if isinstance(item.get("payload"), dict) else {}; ts=str(item.get("timestamp") or payload.get("timestamp") or "")
            if ts: meta["updated"]=ts
            if item.get("type")=="session_meta": meta["session_id"]=str(payload.get("id") or meta["session_id"]); meta["workdir"]=str(payload.get("cwd") or meta["workdir"]); continue
            if item.get("type")=="response_item" and payload.get("type")=="message": add_message(messages, str(payload.get("role") or ""), payload.get("content"), ts); continue
            if item.get("type")=="event_msg":
                if payload.get("type")=="user_message": add_message(fallback,"user",payload.get("message"),ts)
                elif payload.get("type")=="agent_message": add_message(fallback,"assistant",payload.get("message"),ts)
    except OSError: pass
    return entry_from_messages(record, meta, messages or fallback)

def parse_gemini_session(record:dict[str,Any]) -> dict[str,Any]:
    path=Path(record["path"]); meta={"session_id":path.stem,"workdir":record.get("workdir_hint") or gemini_project_root(path),"updated":""}; messages=[]
    try:
        with path.open("r",encoding="utf-8",errors="replace") as f:
            for n,line in enumerate(f):
                try: item=json.loads(line)
                except json.JSONDecodeError: continue
                if n==0: meta["session_id"]=str(item.get("sessionId") or meta["session_id"]); meta["updated"]=str(item.get("lastUpdated") or item.get("startTime") or meta["updated"]); continue
                ts=str(item.get("timestamp") or "")
                if ts: meta["updated"]=ts
                k=item.get("type")
                if k=="user": add_message(messages,"user",item.get("content"),ts)
                elif k in {"gemini","assistant","model"}: add_message(messages,"assistant",item.get("content"),ts)
    except OSError: pass
    return entry_from_messages(record, meta, messages)

def parse_hermes_session(record:dict[str,Any]) -> dict[str,Any]:
    path=Path(record["path"]); meta={"session_id":hermes_session_id(path),"workdir":"","updated":""}; messages=[]
    try:
        if path.suffix==".jsonl":
            for line in path.read_text(encoding="utf-8",errors="replace").splitlines():
                try: item=json.loads(line)
                except json.JSONDecodeError: continue
                ts=str(item.get("timestamp") or "")
                if ts: meta["updated"]=ts
                role=str(item.get("role") or "")
                if role=="session_meta": meta["session_id"]=str(item.get("session_id") or meta["session_id"]); meta["workdir"]=str(item.get("cwd") or item.get("workdir") or meta["workdir"]); continue
                add_message(messages,role,item.get("content"),ts)
        else:
            item=ai_store.read_json(path,{})
            meta["session_id"]=str(item.get("session_id") or meta["session_id"]); meta["updated"]=str(item.get("last_updated") or item.get("session_start") or ""); meta["workdir"]=str(item.get("cwd") or item.get("workdir") or item.get("working_directory") or "")
            for m in item.get("messages") or []: add_message(messages,str(m.get("role") or ""),m.get("content"))
    except OSError: pass
    return entry_from_messages(record, meta, messages)

def parse_session_record(record:dict[str,Any]) -> dict[str,Any]:
    if record.get("provider")=="codex": return parse_codex_session(record)
    if record.get("provider")=="gemini": return parse_gemini_session(record)
    if record.get("provider")=="hermes": return parse_hermes_session(record)
    return entry_from_messages(record,{"session_id":Path(record["path"]).stem},[])

def load_session_index() -> dict[str,Any]:
    data=ai_store.read_json(ai_store.SESSION_INDEX_FILE,{"version":ai_store.SESSION_INDEX_VERSION,"sessions":[]}); data.setdefault("sessions",[]); return data

def save_session_index(data:dict[str,Any]) -> None: ai_store.write_json(ai_store.SESSION_INDEX_FILE,data)

def refresh_session_index(limit:int=SESSION_SCAN_LIMIT) -> dict[str,Any]:
    old=load_session_index(); reusable=old.get("version")==ai_store.SESSION_INDEX_VERSION; old_by_path={str(x.get("path") or x.get("source_path")):x for x in old.get("sessions",[])}; entries=[]
    for rec in discover_session_files(limit):
        key=str(rec["path"]); prev=old_by_path.get(key)
        if reusable and prev and prev.get("mtime")==rec.get("mtime") and prev.get("size")==rec.get("size"): entries.append(finalize(dict(prev)))
        else: entries.append(parse_session_record(rec))
    entries.sort(key=lambda x: float(x.get("mtime") or 0), reverse=True)
    data={"version":ai_store.SESSION_INDEX_VERSION,"generated_at":ai_store.now_iso(),"sessions":entries}; save_session_index(data); return data

def _matches(item:dict[str,Any], provider:str|None=None, profile:str|None=None, workdir:str|None=None) -> bool:
    if provider and item.get("provider") != provider: return False
    if profile and item.get("profile") != profile: return False
    if workdir and ai_store.normalize_path(str(item.get("workdir") or "")) != ai_store.normalize_path(workdir): return False
    return True

def recent_sessions(provider:str|None=None, profile:str|None=None, workdir:str|None=None, limit:int=20, ranking:str="strict") -> list[dict[str,Any]]:
    data=load_session_index(); rows=[finalize(dict(x)) for x in data.get("sessions",[]) if x.get("last_prompt_summary") or x.get("last_response_summary") or x.get("title")]
    if ranking=="strict":
        rows=[r for r in rows if _matches(r, provider, profile, workdir)]
        rows.sort(key=lambda r: float(r.get("mtime") or 0), reverse=True)
    else:
        target=ai_store.normalize_path(workdir); ranked=[]
        for r in rows:
            if provider and r.get("provider") != provider: continue
            score=0
            if profile and r.get("profile")==profile: score+=4
            if target and ai_store.normalize_path(str(r.get("workdir") or ""))==target: score+=2
            ranked.append((score,float(r.get("mtime") or 0),r))
        ranked.sort(key=lambda x:(x[0],x[1]), reverse=True); rows=[r for _,__,r in ranked]
    return rows[:limit]

def resolve_session(session_ref:str, provider:str|None=None, profile:str|None=None, workdir:str|None=None) -> dict[str,Any]|None:
    rows=[finalize(dict(x)) for x in load_session_index().get("sessions",[])]
    if not rows:
        try: rows=[finalize(dict(x)) for x in refresh_session_index().get("sessions",[])]
        except Exception: rows=[]
    matches=[]
    for r in rows:
        if provider and r.get("provider") != provider: continue
        if profile and r.get("profile") != profile: continue
        if workdir and ai_store.normalize_path(str(r.get("workdir") or "")) != ai_store.normalize_path(workdir): continue
        candidates={str(r.get("session_id") or ""), str(r.get("native_session_ref") or ""), str(r.get("stable_session_key") or ""), str(r.get("stable_key") or "")}
        if session_ref in candidates: matches.append(r)
    if not matches: return None
    # Prefer exact provider/profile/workdir narrowing and latest mtime.
    matches.sort(key=lambda r: float(r.get("mtime") or 0), reverse=True)
    if len(matches)>1:
        # Return sentinel with ambiguity details; CLI surfaces this.
        return {"ambiguous": True, "matches": matches[:20], "session_ref": session_ref}
    return matches[0]
