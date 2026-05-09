#!/usr/bin/env python3
"""Curses frontend for Stage 6 ai run/session model."""
from __future__ import annotations
import curses, json, os, subprocess, sys
from pathlib import Path
from typing import Any
os.environ.setdefault("ESCDELAY", "50")
HOME=Path(os.environ.get("HOME", str(Path.home())))
LIB_DIR=Path(__file__).resolve().parent
AI_CLI=str(LIB_DIR/"ai_cli.py")
SCOPES=["profile","provider","all","new"]
SECTIONS=["provider","profile","scope","directory","sessions"]

def short(path:str)->str:
    h=str(HOME)
    if path==h: return "~"
    if path.startswith(h+"/"): return "~/"+path[len(h)+1:]
    return path

def model_json(*args:str):
    cp=subprocess.run([sys.executable, AI_CLI, "__json", *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if cp.returncode: raise RuntimeError(cp.stderr.strip() or cp.stdout.strip())
    return json.loads(cp.stdout or "null")

def stable_key(row:dict[str,Any])->str:
    return str(row.get("stable_session_key") or row.get("stable_key") or "|".join([str(row.get("provider") or ""),str(row.get("profile") or "default"),str(row.get("workdir") or ""),str(row.get("native_session_ref") or row.get("session_id") or "")]))

class App:
    def __init__(self,stdscr):
        self.stdscr=stdscr; self.section=0; self.provider_index=0; self.profile_index=0; self.scope_index=0; self.session_index=0; self.session_scroll=0; self.message=""; self.memory={}; self.directory=str(Path.cwd())
        self.providers=model_json("providers") or ["codex","gemini","hermes"]; self.reload_profiles()
    def provider(self): return self.providers[self.provider_index] if self.providers else "codex"
    def profile(self): return self.profiles[self.profile_index] if self.profiles else "default"
    def scope(self): return SCOPES[self.scope_index]
    def reload_profiles(self):
        try: self.profiles=model_json("profiles", self.provider()) or ["default"]
        except Exception: self.profiles=["default"]
        self.profile_index=min(self.profile_index, max(0,len(self.profiles)-1))
    def sessions(self):
        if self.scope()=="new": return []
        try: return model_json("sessions", self.provider(), self.profile(), self.scope()) or []
        except Exception as e: self.message=str(e); return []
    def save_selection(self):
        rows=self.sessions()
        if rows and 0<=self.session_index<len(rows): self.memory[(self.provider(),self.profile(),self.scope())]=stable_key(rows[self.session_index])
    def restore_selection(self):
        rows=self.sessions(); key=self.memory.get((self.provider(),self.profile(),self.scope()))
        self.session_index=0; self.session_scroll=0
        if key:
            for i,r in enumerate(rows):
                if stable_key(r)==key: self.session_index=i; break
    def selected_session(self):
        rows=self.sessions(); return rows[self.session_index] if rows and 0<=self.session_index<len(rows) else None
    def plan_args(self):
        row=self.selected_session(); directory=self.directory; session=""
        if row:
            directory=str(row.get("workdir") or directory); session=str(row.get("native_session_ref") or row.get("session_id") or "")
        return ["plan","run",self.provider(),self.profile(),directory,session]
    def plan(self):
        cp=subprocess.run([sys.executable, AI_CLI, "__json", *self.plan_args()], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if cp.returncode: return {"display":cp.stderr.strip(),"argv":[]}
        return json.loads(cp.stdout)
    def line(self,y,x,text,w,attr=0):
        try: self.stdscr.addnstr(y,x,(text+" "*w)[:w],w,attr)
        except curses.error: pass
    def draw(self):
        self.stdscr.erase(); h,w=self.stdscr.getmaxyx()
        if h<12 or w<50: self.line(0,0,"ai tui: terminal too small",w-1,curses.A_BOLD); self.stdscr.refresh(); return
        self.line(0,0," ai run launcher",w-1,curses.A_REVERSE|curses.A_BOLD)
        rows=[("Provider",self.provider()),("Profile",self.profile()),("Scope",self.scope()),("Directory",short(self.directory))]
        for i,(k,v) in enumerate(rows): self.line(2+i,0,("> " if self.section==i else "  ")+f"{k:<10} {v}",w-1,curses.A_BOLD if self.section==i else 0)
        y=7; self.line(y,0,"Sessions",w-1,curses.A_BOLD); y+=1
        rows_s=self.sessions(); visible=max(1,h-y-5); self.session_index=max(0,min(self.session_index,max(0,len(rows_s)-1)))
        if self.session_index<self.session_scroll: self.session_scroll=self.session_index
        if self.session_index>=self.session_scroll+visible: self.session_scroll=self.session_index-visible+1
        for n,r in enumerate(rows_s[self.session_scroll:self.session_scroll+visible]):
            idx=self.session_scroll+n; sel=(self.section==4 and idx==self.session_index); self.line(y+n,0,("> " if sel else "  ")+f"{str(r.get('updated') or '')[:16]:<16} {short(str(r.get('workdir') or '')):<24} {r.get('title') or r.get('native_session_ref') or ''}",w-1,curses.A_REVERSE if sel else 0)
        p=self.plan(); self.line(h-3,0,"Launch: "+str(p.get("display") or ""),w-1,curses.A_DIM); self.line(h-2,0,"Tab move | Left/Right change | Up/Down select | Enter run | r refresh | Esc quit",w-1,curses.A_DIM); self.line(h-1,0,self.message,w-1)
        self.stdscr.refresh()
    def change(self,delta):
        if self.section==0: self.save_selection(); self.provider_index=(self.provider_index+delta)%len(self.providers); self.reload_profiles(); self.restore_selection()
        elif self.section==1: self.save_selection(); self.profile_index=(self.profile_index+delta)%len(self.profiles); self.restore_selection()
        elif self.section==2: self.save_selection(); self.scope_index=(self.scope_index+delta)%len(SCOPES); self.restore_selection()
    def run(self):
        curses.curs_set(0); self.stdscr.keypad(True)
        while True:
            self.draw(); ch=self.stdscr.getch()
            if ch in (27,3): return 0
            if ch==9: self.section=(self.section+1)%len(SECTIONS)
            elif ch==curses.KEY_BTAB: self.section=(self.section-1)%len(SECTIONS)
            elif ch==curses.KEY_RIGHT: self.change(1)
            elif ch==curses.KEY_LEFT: self.change(-1)
            elif ch==curses.KEY_DOWN:
                if self.section==4: self.session_index=min(self.session_index+1,max(0,len(self.sessions())-1))
                else: self.section=min(self.section+1,len(SECTIONS)-1)
            elif ch==curses.KEY_UP:
                if self.section==4: self.session_index=max(self.session_index-1,0)
                else: self.section=max(self.section-1,0)
            elif ch in (ord('r'),ord('R')): subprocess.run([sys.executable, AI_CLI, "session", "refresh"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); self.restore_selection(); self.message="refreshed"
            elif ch in (10,13):
                p=self.plan(); argv=p.get("argv") or []
                if not argv: self.message="no command"; continue
                curses.def_prog_mode(); curses.endwin()
                try: os.execvpe(argv[0], argv, {**os.environ, **(p.get('env') or {})})
                except OSError as e: curses.reset_prog_mode(); self.message=f"exec failed: {e}"

def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty(): print("ai tui requires a TTY", file=sys.stderr); return 2
    return curses.wrapper(lambda stdscr: App(stdscr).run())
if __name__=="__main__": raise SystemExit(main())
