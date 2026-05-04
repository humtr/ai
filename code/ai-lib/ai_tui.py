#!/usr/bin/env python3
"""Curses launcher/editor for the ai wrapper."""

from __future__ import annotations

import curses
import os
import subprocess
import sys
from pathlib import Path

import ai_registry


HOME = Path(os.environ.get("HOME", str(Path.home())))
AI_BIN = os.environ.get("AI_BIN", str(HOME / "bin" / "ai"))


def short(path: str) -> str:
    home = str(HOME)
    if path == home:
        return "~"
    if path.startswith(home + "/"):
        return "~/" + path[len(home) + 1 :]
    return path


class App:
    def __init__(self, stdscr: "curses._CursesWindow") -> None:
        self.stdscr = stdscr
        self.panel = 0
        self.indices = [0, 0, 0]
        self.providers = ["codex", "gemini", "hermes"]
        self.mode = "task"
        self.message = ""
        self.reload()

    def reload(self) -> None:
        ai_registry.ensure_registry()
        self.accounts = [
            a
            for a in ai_registry.load_accounts().get("accounts", [])
            if not a.get("hidden")
        ]
        self.workdirs = [
            w
            for w in ai_registry.load_workdirs().get("workdirs", [])
            if not w.get("archived")
        ]
        current = {
            "name": "current",
            "path": str(Path.cwd()),
            "purpose": "current shell directory",
            "favorite": True,
            "archived": False,
        }
        if not any(Path(w.get("path", "")).resolve() == Path.cwd() for w in self.workdirs):
            self.workdirs.insert(0, current)
        if not self.accounts:
            self.accounts = [{"id": "default", "label": "native default", "aliases": []}]
        if not self.workdirs:
            self.workdirs = [current]
        for n, items in enumerate([self.workdirs, self.accounts, self.providers]):
            self.indices[n] = max(0, min(self.indices[n], len(items) - 1))

    def current_workdir(self) -> dict:
        return self.workdirs[self.indices[0]]

    def current_account(self) -> dict:
        return self.accounts[self.indices[1]]

    def current_provider(self) -> str:
        return self.providers[self.indices[2]]

    def prompt(self, label: str, default: str = "") -> str | None:
        curses.echo()
        h, _ = self.stdscr.getmaxyx()
        self.stdscr.move(h - 2, 0)
        self.stdscr.clrtoeol()
        self.stdscr.addstr(h - 2, 0, f"{label} [{default}]: ")
        value = self.stdscr.getstr(h - 2, len(label) + len(default) + 5).decode()
        curses.noecho()
        value = value.strip()
        if not value:
            value = default
        return value or None

    def shell(self, args: list[str]) -> None:
        curses.def_prog_mode()
        curses.endwin()
        try:
            subprocess.run(args)
            input("\nPress Enter to return to ai tui...")
        finally:
            curses.reset_prog_mode()
            curses.curs_set(0)
            self.reload()

    def open_file(self, path: Path) -> None:
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "nano"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text("{}\n", encoding="utf-8")
        self.shell([editor, str(path)])

    def add_workdir(self) -> None:
        name = self.prompt("workdir name")
        if not name:
            return
        default_path = str(HOME / "work" / name)
        path = self.prompt("path", default_path)
        if not path:
            return
        purpose = self.prompt("purpose", "") or ""
        rc = ai_registry.cmd_workdirs_add(
            type(
                "Args",
                (),
                {
                    "name": name,
                    "path": path,
                    "purpose": purpose,
                    "favorite": False,
                    "create": True,
                },
            )()
        )
        self.message = "added workdir" if rc == 0 else "failed to add workdir"
        self.reload()

    def add_account(self) -> None:
        account_id = self.prompt("account id")
        if not account_id:
            return
        alias = self.prompt("alias", "") or ""
        label = self.prompt("label", account_id) or account_id
        data = ai_registry.load_accounts()
        if ai_registry.find_account(account_id):
            self.message = f"account exists: {account_id}"
            return
        data["accounts"].append(
            {
                "id": account_id,
                "label": label,
                "aliases": [alias] if alias else [],
                "native": False,
                "hidden": False,
                "provider_profiles": {},
            }
        )
        ai_registry.save_accounts(data)
        self.message = "added account"
        self.reload()

    def launch(self) -> None:
        prompt = ""
        if self.mode in {"ask", "task", "plan"}:
            prompt = self.prompt(f"{self.mode} prompt")
            if not prompt:
                self.message = "cancelled"
                return
        provider = self.current_provider()
        account = self.current_account().get("id", "default")
        workdir = self.current_workdir().get("path", str(Path.cwd()))
        cmd = [AI_BIN, self.mode, provider, "--account", account, "--cwd", workdir]
        if prompt:
            cmd.append(prompt)
        curses.def_prog_mode()
        curses.endwin()
        os.execvp(cmd[0], cmd)

    def sessions(self) -> None:
        provider = self.current_provider()
        account = self.current_account().get("id", "default")
        workdir = self.current_workdir().get("path", str(Path.cwd()))
        self.shell([AI_BIN, "list", provider, "--account", account, "--cwd", workdir])

    def draw_list(self, y: int, x: int, w: int, title: str, items: list[str], idx: int, active: bool) -> None:
        attr = curses.A_BOLD | (curses.A_REVERSE if active else 0)
        self.stdscr.addnstr(y, x, title, w - 1, attr)
        for n in range(0, min(len(items), 10)):
            line = items[n]
            row_attr = curses.A_REVERSE if active and n == idx else 0
            self.stdscr.addnstr(y + 1 + n, x, line.ljust(w - 1), w - 1, row_attr)

    def draw(self) -> None:
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        work_items = [
            f"{i.get('name','')}  {short(i.get('path',''))}" for i in self.workdirs
        ]
        account_items = [
            f"{a.get('id','')}  {','.join(a.get('aliases') or [])}" for a in self.accounts
        ]
        provider_items = [p for p in self.providers]
        col = max(24, w // 3)
        self.stdscr.addnstr(0, 0, "ai launcher", w - 1, curses.A_BOLD)
        self.stdscr.addnstr(
            1,
            0,
            f"CWD {short(str(Path.cwd()))} | mode {self.mode}",
            w - 1,
        )
        self.draw_list(3, 0, col, "Workdirs", work_items, self.indices[0], self.panel == 0)
        self.draw_list(3, col, col, "Accounts", account_items, self.indices[1], self.panel == 1)
        self.draw_list(3, col * 2, w - col * 2, "Providers", provider_items, self.indices[2], self.panel == 2)
        selected = (
            f"{self.mode} {self.current_provider()} --account "
            f"{self.current_account().get('id','default')} --cwd "
            f"{short(self.current_workdir().get('path', str(Path.cwd())))}"
        )
        self.stdscr.addnstr(h - 5, 0, selected, w - 1, curses.A_BOLD)
        self.stdscr.addnstr(
            h - 4,
            0,
            "Enter launch | Tab panel | j/k move | m mode | s sessions | w add workdir | a add account",
            w - 1,
        )
        self.stdscr.addnstr(
            h - 3,
            0,
            "A edit accounts | W edit workdirs | G gateways | B bridge | q quit",
            w - 1,
        )
        self.stdscr.addnstr(h - 1, 0, self.message, w - 1)
        self.stdscr.refresh()

    def run(self) -> int:
        curses.curs_set(0)
        self.stdscr.keypad(True)
        while True:
            self.draw()
            ch = self.stdscr.getch()
            items = [self.workdirs, self.accounts, self.providers][self.panel]
            if ch in (ord("q"), 27):
                return 0
            if ch in (9, curses.KEY_BTAB):
                self.panel = (self.panel + 1) % 3
            elif ch in (curses.KEY_DOWN, ord("j")):
                self.indices[self.panel] = min(self.indices[self.panel] + 1, len(items) - 1)
            elif ch in (curses.KEY_UP, ord("k")):
                self.indices[self.panel] = max(self.indices[self.panel] - 1, 0)
            elif ch in (10, 13):
                self.launch()
            elif ch == ord("m"):
                modes = ["task", "ask", "plan", "run"]
                self.mode = modes[(modes.index(self.mode) + 1) % len(modes)]
            elif ch == ord("s"):
                self.sessions()
            elif ch == ord("w"):
                self.add_workdir()
            elif ch == ord("a"):
                self.add_account()
            elif ch == ord("A"):
                self.open_file(ai_registry.ACCOUNTS_FILE)
            elif ch == ord("W"):
                self.open_file(ai_registry.WORKDIRS_FILE)
            elif ch == ord("G"):
                self.shell([AI_BIN, "gateway", "status"])
            elif ch == ord("B"):
                self.shell([AI_BIN, "bridge", "status"])


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("ai tui requires a TTY", file=sys.stderr)
        return 2
    return curses.wrapper(lambda stdscr: App(stdscr).run())


if __name__ == "__main__":
    raise SystemExit(main())
