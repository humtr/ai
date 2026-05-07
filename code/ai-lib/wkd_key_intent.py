#!/usr/bin/env python3
"""TUI-shaped workdir key intention recorder.

This app deliberately reuses ai_tui.App so the screen, focus model, and key
handling match the real wrapper. Provider execution is disabled; each key press
is captured with before/after state and a user memo.
"""

from __future__ import annotations

import argparse
import curses
import json
import os
import shlex
import sys
import termios
from datetime import datetime
from pathlib import Path
from typing import Any

import ai_tui


HOME = ai_tui.HOME
AI_BIN = ai_tui.AI_BIN
AI_HOME = Path(os.environ.get("AI_HOME", str(HOME / ".ai")))


def key_name(ch: int) -> str:
    names = {
        curses.KEY_UP: "Up",
        curses.KEY_DOWN: "Down",
        curses.KEY_LEFT: "Left",
        curses.KEY_RIGHT: "Right",
        curses.KEY_HOME: "Home",
        curses.KEY_END: "End",
        curses.KEY_NPAGE: "PageDown",
        curses.KEY_PPAGE: "PageUp",
        curses.KEY_BACKSPACE: "Backspace",
        curses.KEY_DC: "Delete",
        curses.KEY_BTAB: "Shift+Tab",
        curses.KEY_MOUSE: "Mouse",
        3: "Ctrl+C",
        8: "Backspace",
        9: "Tab",
        10: "Enter",
        13: "Enter",
        19: "Ctrl+S",
        21: "Ctrl+U",
        27: "Esc",
        127: "Backspace",
    }
    if ch in names:
        return names[ch]
    if 32 <= ch <= 126:
        return chr(ch)
    return f"Key({ch})"


def printable_key(ch: int) -> str | None:
    if 32 <= ch <= 126:
        return chr(ch)
    return None


def safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [safe(item) for item in value]
    if isinstance(value, dict):
        return {str(k): safe(v) for k, v in value.items()}
    return repr(value)


class IntentRecorderApp(ai_tui.App):
    def __init__(self, stdscr: Any, output: Path | None = None) -> None:
        self.intent_records: list[dict[str, Any]] = []
        self.intent_saved = False
        self.replay_keys: list[int] = []
        self.replay_memos: list[str] = []
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.intent_output = output or (AI_HOME / "wkd-key-intentions" / f"{stamp}.json")
        super().__init__(stdscr)
        self.message = "intent recorder: Ctrl+S save, Esc exit; execution disabled"

    def refresh_sessions(self, silent: bool = False) -> None:
        if not silent:
            self.message = "intent recorder: session refresh skipped"

    def shell(self, args: list[str]) -> None:
        self.message = "intent recorder: would open shell command " + " ".join(shlex.quote(part) for part in args)

    def exec_or_preview(self, cmd: list[str]) -> None:
        self.message = "intent recorder: would run " + " ".join(shlex.quote(part) for part in cmd)

    def open_file(self, path: Path) -> None:
        self.message = f"intent recorder: would open file {path}"

    def add_workdir(self) -> None:
        self.message = "intent recorder: add workdir skipped"

    def launch(self) -> None:
        if not self.commit_workdir_text_if_present():
            return
        cmd = [AI_BIN, self.current_mode(), *self.common_args(display=False)]
        self.exec_or_preview(cmd)

    def resume_selected(self) -> None:
        item = self.selected_session()
        if not item:
            self.message = "intent recorder: no selected session"
            return
        if item.get("_kind") == "new":
            self.launch()
            return
        if not self.commit_workdir_text_if_present():
            return
        cmd = [AI_BIN, "resume", *self.common_args(display=False), str(item.get("session_id") or "")]
        self.exec_or_preview(cmd)

    def selected_session_snapshot(self) -> dict[str, Any] | None:
        try:
            selected = self.selected_session()
        except Exception as exc:  # pragma: no cover - defensive recorder boundary
            return {"error": repr(exc)}
        if not selected:
            return None
        return {
            "kind": selected.get("_kind"),
            "session_id": selected.get("session_id"),
            "title": selected.get("title"),
            "updated": selected.get("updated"),
        }

    def snapshot(self) -> dict[str, Any]:
        focused_child = None
        try:
            child = self.selected_workdir_child()
            focused_child = str(child) if child is not None else None
        except Exception as exc:  # pragma: no cover - defensive recorder boundary
            focused_child = f"error: {exc!r}"

        children: list[str] = []
        try:
            children = [str(path) for path in self.filtered_workdir_children()[:30]]
        except Exception as exc:  # pragma: no cover - defensive recorder boundary
            children = [f"error: {exc!r}"]

        def call(name: str, default: Any = None) -> Any:
            try:
                return getattr(self, name)()
            except Exception as exc:  # pragma: no cover - defensive recorder boundary
                return {"error": repr(exc)}

        return safe(
            {
                "view": getattr(self, "view", None),
                "panel": "sessions" if getattr(self, "panel", None) == 1 else "command_builder",
                "section": call("active_section"),
                "mode": call("current_mode"),
                "provider": call("current_provider"),
                "profile": call("current_profile"),
                "workdir_layer": getattr(self, "workdir_layer", None),
                "workdir_text": getattr(self, "workdir_text", None),
                "workdir_child_index": getattr(self, "workdir_child_index", None),
                "current_workdir_path": call("current_workdir_path"),
                "effective_workdir_path": call("effective_workdir_path"),
                "focused_workdir_child": focused_child,
                "visible_workdir_children": children,
                "session_index": getattr(self, "session_index", None),
                "session_scroll": getattr(self, "session_scroll", None),
                "selected_session": self.selected_session_snapshot(),
                "command_line": call("command_line"),
                "selected_session_command_line": call("selected_session_command_line"),
                "message": getattr(self, "message", ""),
            }
        )

    def behavior_summary(self, before: dict[str, Any], after: dict[str, Any]) -> str:
        watched = [
            "view",
            "panel",
            "section",
            "mode",
            "provider",
            "profile",
            "workdir_layer",
            "workdir_text",
            "workdir_child_index",
            "current_workdir_path",
            "effective_workdir_path",
            "focused_workdir_child",
            "session_index",
            "session_scroll",
            "selected_session",
            "command_line",
            "selected_session_command_line",
            "message",
        ]
        changes = []
        for key in watched:
            if before.get(key) != after.get(key):
                changes.append(f"{key}: {before.get(key)!r} -> {after.get(key)!r}")
        return "; ".join(changes) if changes else "no visible state change"

    def memo_prompt(self, key: str, actual: str) -> str:
        if self.replay_memos:
            return self.replay_memos.pop(0)
        h, w = self.stdscr.getmaxyx()
        label = f"wanted for {key} (Enter skip): "
        summary = "actual: " + actual
        curses.echo()
        try:
            self.stdscr.move(max(0, h - 3), 0)
            self.stdscr.clrtoeol()
            self.stdscr.addnstr(max(0, h - 3), 0, summary, max(1, w - 1))
            self.stdscr.move(max(0, h - 2), 0)
            self.stdscr.clrtoeol()
            self.stdscr.addnstr(max(0, h - 2), 0, label, max(1, w - 1))
            self.stdscr.refresh()
            value = self.stdscr.getstr(max(0, h - 2), min(len(label), max(0, w - 1)), max(1, w - len(label) - 1))
            return value.decode(errors="replace")
        finally:
            curses.noecho()

    def record_key(self, ch: int, before: dict[str, Any], after: dict[str, Any], actual: str, wanted: str) -> None:
        self.intent_records.append(
            {
                "index": len(self.intent_records) + 1,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "key": {
                    "code": ch,
                    "name": key_name(ch),
                    "text": printable_key(ch),
                },
                "before": before,
                "after": after,
                "actual": actual,
                "wanted": wanted,
                "wanted_skipped": wanted == "",
            }
        )
        self.intent_saved = False

    def save_records(self) -> None:
        self.intent_output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "app": "ai wkd-intent",
            "purpose": "workdir key binding and behavior intention capture",
            "records": self.intent_records,
            "final_state": self.snapshot(),
        }
        self.intent_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.intent_saved = True
        self.message = f"intent recorder: saved {len(self.intent_records)} records to {self.intent_output}"

    def apply_recorded_key(self, ch: int) -> int | None:
        if ch == ord("q"):
            self.message = "intent recorder: q would quit the real TUI"
            return None
        if ch == 3:
            self.message = "intent recorder: Ctrl+C exits without saving"
            return 130
        return self.handle_manage_key(ch) if self.view == "manage" else self.handle_main_key(ch)

    def disable_flow_control(self) -> list[Any] | None:
        if not sys.stdin.isatty():
            return None
        try:
            fd = sys.stdin.fileno()
            attrs = termios.tcgetattr(fd)
            updated = list(attrs)
            updated[0] &= ~termios.IXON
            if hasattr(termios, "IXOFF"):
                updated[0] &= ~termios.IXOFF
            termios.tcsetattr(fd, termios.TCSANOW, updated)
            return attrs
        except termios.error:
            return None

    def read_key(self) -> int:
        if self.replay_keys:
            return self.replay_keys.pop(0)
        return self.stdscr.getch()

    def run(self) -> int:
        saved_termios = self.disable_flow_control()
        curses.curs_set(0)
        self.stdscr.keypad(True)
        try:
            mouse_events = getattr(curses, "BUTTON4_PRESSED", 0) | getattr(curses, "BUTTON5_PRESSED", 0)
            mouse_events |= getattr(curses, "BUTTON1_PRESSED", 0) | getattr(curses, "BUTTON1_RELEASED", 0)
            curses.mousemask(mouse_events)
            curses.mouseinterval(0)
        except curses.error:
            pass
        try:
            while True:
                self.draw()
                try:
                    ch = self.read_key()
                except KeyboardInterrupt:
                    return 130
                if ch == 19:
                    self.save_records()
                    continue
                if ch == 27:
                    return 0
                before = self.snapshot()
                result = self.apply_recorded_key(ch)
                after = self.snapshot()
                actual = self.behavior_summary(before, after)
                if result is not None:
                    actual = f"{actual}; real TUI would exit with {result}"
                self.draw()
                wanted = self.memo_prompt(key_name(ch), actual)
                self.record_key(ch, before, after, actual, wanted)
                if result == 130:
                    return result
        finally:
            if saved_termios is not None:
                try:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSANOW, saved_termios)
                except termios.error:
                    pass


def write_self_test(output: Path) -> None:
    payload = {
        "version": 1,
        "saved_at": "self-test",
        "app": "ai wkd-intent",
        "purpose": "workdir key binding and behavior intention capture",
        "records": [
            {
                "index": 1,
                "timestamp": "self-test",
                "key": {"code": curses.KEY_DOWN, "name": "Down", "text": None},
                "before": {"section": "workdir", "workdir_text": "~/wo", "workdir_layer": "inline"},
                "after": {"section": "workdir", "workdir_text": "~/wo", "workdir_layer": "children"},
                "actual": "workdir_layer: 'inline' -> 'children'",
                "wanted": "fixture wanted behavior",
            }
        ],
        "final_state": {"section": "workdir"},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_loop_self_test(stdscr: Any, output: Path) -> int:
    app = IntentRecorderApp(stdscr, output)
    app.replay_keys = [ord("w"), ord("x"), 19, 27]
    app.replay_memos = ["wanted live behavior", ""]
    return app.run()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record workdir key intentions in the real ai TUI shape.")
    parser.add_argument("--output", type=Path, help="JSON output path")
    parser.add_argument("--self-test", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--run-loop-self-test", type=Path, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    if args.self_test:
        write_self_test(args.self_test)
        return 0
    if args.run_loop_self_test:
        return curses.wrapper(lambda stdscr: run_loop_self_test(stdscr, args.run_loop_self_test))
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("ai wkd-intent requires a TTY", file=sys.stderr)
        return 2
    return curses.wrapper(lambda stdscr: IntentRecorderApp(stdscr, args.output).run())


if __name__ == "__main__":
    raise SystemExit(main())
