#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, time
from pathlib import Path
from typing import Any
import ai_store, ai_spec
HOME=ai_store.HOME
SESSION_SCAN_LIMIT=int(os.environ.get("AI_SESSION_SCAN_LIMIT","500"))
SESSION_RESOLVE_SCAN_LIMIT=int(os.environ.get("AI_SESSION_RESOLVE_SCAN_LIMIT","5000"))

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

def codex_profile_for_session_path(path: Path) -> str:
    try:
        wanted = Path(path).expanduser().resolve(strict=False)
    except OSError:
        wanted = Path(path).expanduser()
    roots = [("default", HOME / ".codex" / "sessions")]
    profiles = HOME / ".codex-profiles"
    if profiles.is_dir():
        roots.extend((ph.name, ph / "sessions") for ph in sorted(x for x in profiles.iterdir() if x.is_dir()))
    for profile, root in roots:
        try:
            root_resolved = root.expanduser().resolve(strict=False)
            if os.path.commonpath([str(wanted), str(root_resolved)]) == str(root_resolved):
                return profile
        except ValueError:
            continue
    return ""

def add_codex_session_record(records:list[dict[str,Any]], profile:str, path:Path) -> None:
    source_profile = profile
    source_path = path
    if path.is_symlink():
        try:
            source_path = path.resolve(strict=True)
        except OSError:
            return
        resolved_profile = codex_profile_for_session_path(source_path)
        if resolved_profile:
            source_profile = resolved_profile
    add_session_record(records, "codex", source_profile, source_path)

def hermes_session_id(path: Path) -> str:
    stem=path.stem; return stem[len("session_"):] if stem.startswith("session_") else stem

def gemini_project_root(path: Path) -> str:
    for parent in path.parents:
        if parent.name == "chats":
            pr=parent.parent/".project_root"
            if pr.exists(): return read_project_root(pr)
            break
    return ""

def agy_profile_for_session_path(path: Path) -> str:
    try:
        wanted = Path(path).expanduser().resolve(strict=False)
    except OSError:
        wanted = Path(path).expanduser()
    roots = [("default", HOME / ".gemini")]
    profiles = HOME / ".agy-profiles"
    if profiles.is_dir():
        roots.extend((ph.name, ph / ".gemini") for ph in sorted(x for x in profiles.iterdir() if x.is_dir()))
    for profile, root in roots:
        try:
            root_resolved = root.expanduser().resolve(strict=False)
            if os.path.commonpath([str(wanted), str(root_resolved)]) == str(root_resolved):
                return profile
        except ValueError:
            continue
    return ""

def add_agy_session_record(records:list[dict[str,Any]], profile:str, path:Path, workdir_hint:str="") -> None:
    source_profile = profile
    source_path = path
    if path.is_symlink():
        try:
            source_path = path.resolve(strict=True)
        except OSError:
            return
        resolved_profile = agy_profile_for_session_path(source_path)
        if resolved_profile:
            source_profile = resolved_profile
    add_session_record(records, "agy", source_profile, source_path, workdir_hint)

class SessionRecords(list):
    def __init__(self) -> None:
        super().__init__()
        self.seen_paths: set[tuple[str, str]] = set()

def add_session_record(records:list[dict[str,Any]], provider:str, profile:str, path:Path, workdir_hint:str="") -> None:
    st=safe_stat(path)
    if st is None or not path.is_file(): return
    try:
        resolved = str(path.resolve())
    except OSError:
        resolved = str(path)
    seen = getattr(records, "seen_paths", None)
    if seen is not None:
        key = (provider, resolved)
        if key in seen:
            return
        seen.add(key)
    records.append({"provider":provider,"profile":profile,"path":path,"workdir_hint":workdir_hint,"mtime":st.st_mtime,"size":st.st_size})

def discover_session_files(limit:int=SESSION_SCAN_LIMIT) -> list[dict[str,Any]]:
    records = SessionRecords()
    codex_sessions=HOME/".codex"/"sessions"
    if codex_sessions.is_dir():
        for p in codex_sessions.rglob("*.jsonl"): add_codex_session_record(records,"default",p)
    codex_profiles=HOME/".codex-profiles"
    if codex_profiles.is_dir():
        for ph in sorted(x for x in codex_profiles.iterdir() if x.is_dir()):
            s=ph/"sessions"
            if s.is_dir():
                for p in s.rglob("*.jsonl"): add_codex_session_record(records,ph.name,p)

    def scan_agy_tree(root: Path, profile: str):
        antigravity_dir = root / ".gemini" / "antigravity-cli"
        if not antigravity_dir.is_dir():
            antigravity_dir = root / "antigravity-cli"
        brain_dir = antigravity_dir / "brain"
        if brain_dir.is_dir():
            for conv_dir in sorted(x for x in brain_dir.iterdir() if x.is_dir()):
                transcript_file = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
                if transcript_file.is_file():
                    add_agy_session_record(records, profile, transcript_file)
        tmp = (root / ".gemini" / "tmp") if (root / ".gemini").is_dir() else (root / "tmp")
        if tmp.is_dir():
            for project_dir in sorted(x for x in tmp.iterdir() if x.is_dir()):
                chats = project_dir / "chats"
                if not chats.is_dir(): continue
                workdir = read_project_root(project_dir / ".project_root")
                for p in chats.rglob("*.jsonl"):
                    add_agy_session_record(records, profile, p, workdir)

    scan_agy_tree(HOME, "default")
    agy_profiles = HOME / ".agy-profiles"
    if agy_profiles.is_dir():
        for ph in sorted(x for x in agy_profiles.iterdir() if x.is_dir()):
            scan_agy_tree(ph, ph.name)

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
    return finalize({"provider":record["provider"],"profile":record["profile"],"session_id":sid,"native_session_ref":sid,"title":text_summary(title,120) or sid,"last_prompt_summary":text_summary(last_user,360),"last_response_summary":text_summary(last_assistant,360),"turns":len(users),"updated":str(meta.get("updated") or last.get("timestamp") or iso_from_mtime(path)),"workdir":str(meta.get("workdir") or record.get("workdir_hint") or ""),"source":"session-file","source_path":str(path),"path":str(path),"mtime":record["mtime"],"size":record["size"]})

def parse_codex_session(record:dict[str,Any]) -> dict[str,Any]:
    path=Path(record["path"]); meta={"session_id":codex_session_id(path),"workdir":"","updated":""}; messages=[]; fallback=[]; found_session_meta=False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try: item=json.loads(line)
                except json.JSONDecodeError: continue
                payload=item.get("payload") if isinstance(item.get("payload"), dict) else {}; ts=str(item.get("timestamp") or payload.get("timestamp") or "")
                if ts: meta["updated"]=ts
                if item.get("type")=="session_meta":
                    if not found_session_meta:
                        meta["session_id"]=str(payload.get("id") or meta["session_id"]); meta["workdir"]=str(payload.get("cwd") or meta["workdir"]); found_session_meta=True
                    continue
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

def parse_antigravity_session(record: dict[str, Any]) -> dict[str, Any]:
    path = Path(record["path"])
    conversation_id = path.parents[2].name
    meta = {
        "session_id": conversation_id,
        "workdir": "",
        "updated": iso_from_mtime(path)
    }
    messages = []
    
    try:
        if path.exists():
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    # Check tool calls for directory paths
                    if "tool_calls" in item:
                        for tc in item["tool_calls"] or []:
                            args = tc.get("args") or {}
                            # Look for common path arguments in tool_calls
                            for path_arg in ("Cwd", "DirectoryPath", "SearchPath", "TargetFile"):
                                if path_arg in args and isinstance(args[path_arg], str):
                                    val = args[path_arg].strip('"')
                                    if val:
                                        # Normalize / extract directory path
                                        try:
                                            p = Path(val)
                                            meta["workdir"] = str(p.parent if p.is_file() else p)
                                            break
                                        except Exception:
                                            pass
                            if meta["workdir"]:
                                break
                    
                    k = item.get("type")
                    if k == "USER_INPUT":
                        content = item.get("content") or ""
                        # strip tags if needed, but summary is fine
                        add_message(messages, "user", content)
                    elif k == "PLANNER_RESPONSE":
                        content = item.get("content") or ""
                        add_message(messages, "assistant", content)
    except OSError:
        pass
        
    entry = entry_from_messages(record, meta, messages)
    entry["session_id"] = conversation_id
    entry["native_session_ref"] = conversation_id
    if not entry.get("title") or entry["title"] == conversation_id:
        entry["title"] = f"Antigravity Chat ({conversation_id[:8]})"
    return entry

def scan_opencode_sessions(limit:int=SESSION_SCAN_LIMIT) -> list[dict[str,Any]]:
    import sqlite3
    roots = [("default", HOME / ".local" / "share" / "opencode" / "opencode.db")]
    profiles = HOME / ".opencode-profiles"
    if profiles.is_dir():
        for ph in sorted(x for x in profiles.iterdir() if x.is_dir()):
            db = ph / ".local" / "share" / "opencode" / "opencode.db"
            if not db.is_file():
                db = ph / "opencode.db"
            if db.is_file():
                roots.append((ph.name, db))
    entries = []
    for profile, db_path in roots:
        if not db_path.is_file(): continue
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            cur = conn.cursor()
            sessions = cur.execute(
                "SELECT id, slug, directory, title, time_created, time_updated, time_archived FROM session ORDER BY time_updated DESC LIMIT ?",
                (limit,)
            ).fetchall()
            for sid, slug, directory, title, t_created, t_updated, t_archived in sessions:
                if t_archived: continue
                parts = cur.execute(
                    "SELECT data FROM part WHERE session_id = ? ORDER BY time_created ASC", (sid,)
                ).fetchall()
                messages = []
                for (data_raw,) in parts:
                    try:
                        data = json.loads(data_raw) if isinstance(data_raw, str) else {}
                        t = data.get("type")
                        if t == "text":
                            add_message(messages, "user", data.get("text", ""))
                        elif t in {"reasoning", "response"}:
                            add_message(messages, "assistant", data.get("text", ""))
                    except Exception:
                        continue
                mtime = (t_updated or t_created or 0) / 1000.0
                iso_time = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(mtime)) if mtime else ""
                users = [m for m in messages if m.get("role") == "user"]
                assistants = [m for m in messages if m.get("role") == "assistant"]
                last_user = users[-1].get("text", "") if users else ""
                last_assistant = assistants[-1].get("text", "") if assistants else ""
                session_title = title or (users[0].get("text", "") if users else slug or sid)
                entry = finalize({
                    "provider": "opencode",
                    "profile": profile,
                    "session_id": sid,
                    "native_session_ref": sid,
                    "slug": slug or "",
                    "title": text_summary(session_title, 120) or sid,
                    "last_prompt_summary": text_summary(last_user, 360),
                    "last_response_summary": text_summary(last_assistant, 360),
                    "turns": len(users),
                    "updated": iso_time,
                    "workdir": directory or "",
                    "source": "session-db",
                    "source_path": str(db_path),
                    "path": str(db_path),
                    "mtime": mtime,
                    "size": db_path.stat().st_size if db_path.exists() else 0
                })
                entries.append(entry)
            conn.close()
        except Exception:
            pass
    return entries

def parse_session_record(record:dict[str,Any]) -> dict[str,Any]:
    path_str = str(record.get("path") or "")
    if "antigravity-cli" in path_str:
        return parse_antigravity_session(record)
    if record.get("provider")=="agy": return parse_gemini_session(record)
    if record.get("provider")=="codex": return parse_codex_session(record)
    if record.get("provider")=="hermes": return parse_hermes_session(record)
    return entry_from_messages(record,{"session_id":Path(record["path"]).stem},[])

def load_session_index() -> dict[str,Any]:
    data=ai_store.read_json(ai_store.SESSION_INDEX_FILE,{"version":ai_store.SESSION_INDEX_VERSION,"sessions":[]}); data.setdefault("sessions",[]); return data

def save_session_index(data:dict[str,Any]) -> None: ai_store.write_json(ai_store.SESSION_INDEX_FILE,data)

_SESSION_INDEX_CACHE: dict[str, Any] | None = None

def refresh_session_index(limit:int=SESSION_SCAN_LIMIT) -> dict[str,Any]:
    global _SESSION_INDEX_CACHE
    old=load_session_index(); reusable=old.get("version")==ai_store.SESSION_INDEX_VERSION
    old_by_key={f"{x.get('provider')}:{x.get('path') or x.get('source_path')}":x for x in old.get("sessions",[])}
    entries=[]
    for rec in discover_session_files(limit):
        key=f"{rec['provider']}:{rec['path']}"; prev=old_by_key.get(key)
        if reusable and prev and prev.get("mtime")==rec.get("mtime") and prev.get("size")==rec.get("size"): entries.append(finalize(dict(prev)))
        else: entries.append(parse_session_record(rec))
    entries.extend(scan_opencode_sessions(limit))
    entries.sort(key=lambda x: float(x.get("mtime") or 0), reverse=True)
    data={"version":ai_store.SESSION_INDEX_VERSION,"generated_at":ai_store.now_iso(),"sessions":entries}; save_session_index(data)
    _SESSION_INDEX_CACHE = data
    return data

def fresh_session_index() -> dict[str,Any]:
    global _SESSION_INDEX_CACHE
    if _SESSION_INDEX_CACHE is not None:
        return _SESSION_INDEX_CACHE
    try:
        old = load_session_index()
        if old.get("version") == ai_store.SESSION_INDEX_VERSION and old.get("sessions"):
            _SESSION_INDEX_CACHE = old
            return old
        _SESSION_INDEX_CACHE = refresh_session_index()
        return _SESSION_INDEX_CACHE
    except Exception:
        return load_session_index()

def _matches(item:dict[str,Any], provider:str|None=None, profile:str|None=None, workdir:str|None=None) -> bool:
    if provider and item.get("provider") != provider: return False
    if profile and item.get("profile") != profile: return False
    if workdir and ai_store.normalize_path(str(item.get("workdir") or "")) != ai_store.normalize_path(workdir): return False
    return True

def source_identity(row:dict[str,Any]) -> str:
    source=str(row.get("source_path") or row.get("path") or "")
    if not source:
        return str(row.get("stable_session_key") or row.get("stable_key") or "")
    provider=str(row.get("provider") or "")
    try:
        return f"{provider}:{Path(source).expanduser().resolve()}"
    except OSError:
        return f"{provider}:{source}"

def source_is_symlink(row:dict[str,Any]) -> bool:
    source=str(row.get("source_path") or row.get("path") or "")
    try:
        return bool(source and Path(source).expanduser().is_symlink())
    except OSError:
        return False

def dedupe_session_rows(rows:list[dict[str,Any]]) -> list[dict[str,Any]]:
    by_source:dict[str,dict[str,Any]]={}
    for row in rows:
        key=source_identity(row)
        if not key:
            key=str(row.get("stable_session_key") or row.get("stable_key") or id(row))
        previous=by_source.get(key)
        if previous is None or (source_is_symlink(previous) and not source_is_symlink(row)):
            by_source[key]=row
    return list(by_source.values())

def recent_sessions(provider:str|None=None, profile:str|None=None, workdir:str|None=None, limit:int=20, ranking:str="strict") -> list[dict[str,Any]]:
    data=fresh_session_index(); rows=[finalize(dict(x)) for x in data.get("sessions",[]) if x.get("last_prompt_summary") or x.get("last_response_summary") or x.get("title")]
    if ranking=="strict":
        rows=[r for r in rows if _matches(r, provider, profile, workdir)]
        rows=dedupe_session_rows(rows)
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
    rows=[finalize(dict(x)) for x in fresh_session_index().get("sessions",[])]

    def collect(source_rows:list[dict[str,Any]]) -> list[dict[str,Any]]:
        found=[]
        for r in source_rows:
            if provider and r.get("provider") != provider: continue
            if profile and r.get("profile") != profile: continue
            if workdir and ai_store.normalize_path(str(r.get("workdir") or "")) != ai_store.normalize_path(workdir): continue
            candidates={str(r.get("session_id") or ""), str(r.get("native_session_ref") or ""), str(r.get("slug") or ""), str(r.get("stable_session_key") or ""), str(r.get("stable_key") or "")}
            if session_ref in candidates: found.append(r)
        return found

    matches=collect(rows)
    if not matches:
        try:
            rows=[finalize(dict(x)) for x in refresh_session_index(SESSION_RESOLVE_SCAN_LIMIT).get("sessions",[])]
            matches=collect(rows)
        except Exception:
            matches=[]
    if not matches: return None
    matches=dedupe_session_rows(matches)
    # Prefer exact provider/profile/workdir narrowing and latest mtime.
    matches.sort(key=lambda r: float(r.get("mtime") or 0), reverse=True)
    if len(matches)>1:
        # Return sentinel with ambiguity details; CLI surfaces this.
        return {"ambiguous": True, "matches": matches[:20], "session_ref": session_ref}
    return matches[0]
