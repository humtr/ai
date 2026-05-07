#!/usr/bin/env python3
"""Curses launcher/editor for the ai wrapper."""

from __future__ import annotations

import curses
import os
import shlex
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

import ai_registry


HOME = Path(os.environ.get("HOME", str(Path.home())))
AI_BIN = os.environ.get("AI_BIN", str(HOME / "bin" / "ai"))
MODES = ["run", "task", "ask", "plan"]
PROVIDERS = ["codex", "gemini", "hermes"]
BUILDER_SECTIONS = ["mode", "provider", "profile", "workdir"]
SECTIONS = BUILDER_SECTIONS + ["sessions"]


def env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes", "on"}


def short(path: str) -> str:
    home = str(HOME)
    if path == home:
        return "~/"
    if path.startswith(home + "/"):
        return "~/" + path[len(home) + 1 :]
    return path


def short_time(value: str) -> str:
    if not value:
        return ""
    return value.replace("T", " ")[:16]


def expand_workdir(value: str) -> Path:
    if value == "~":
        path = HOME
    elif value.startswith("~/"):
        path = HOME / value[2:]
    else:
        path = Path(value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def clip_middle(value: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width <= 3:
        return value[:width]
    left = max(1, (width - 3) // 2)
    right = max(1, width - 3 - left)
    return value[:left] + "..." + value[-right:]


def cell_width(value: str) -> int:
    total = 0
    for ch in value:
        if unicodedata.combining(ch):
            continue
        total += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return total


def fit_cells(value: str, width: int) -> str:
    if width <= 0:
        return ""
    total = 0
    out = []
    for ch in value:
        ch_width = 0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
        if total + ch_width > width:
            break
        out.append(ch)
        total += ch_width
    return "".join(out)


def tail_fit_cells(value: str, width: int) -> str:
    if width <= 0:
        return ""
    total = 0
    out = []
    for ch in reversed(value):
        ch_width = 0 if unicodedata.combining(ch) else 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
        if total + ch_width > width:
            break
        out.append(ch)
        total += ch_width
    return "".join(reversed(out))


def pad_cells(value: str, width: int) -> str:
    value = fit_cells(value, width)
    return value + " " * max(0, width - cell_width(value))


def wrap_cell_text(value: str, width: int) -> list[str]:
    if width <= 0:
        return [""]
    words = value.split(" ")
    lines: list[str] = []
    current = ""

    def append_piece(piece: str) -> None:
        nonlocal current
        if not piece:
            return
        if cell_width(piece) > width:
            if current:
                lines.append(current)
                current = ""
            rest = piece
            while rest:
                part = fit_cells(rest, width)
                if not part:
                    break
                lines.append(part)
                rest = rest[len(part) :]
            return
        candidate = piece if not current else current + " " + piece
        if cell_width(candidate) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = piece

    for word in words:
        append_piece(word)
    if current:
        lines.append(current)
    return lines or [""]


class App:
    def __init__(self, stdscr: "curses._CursesWindow") -> None:
        self.stdscr = stdscr
        self.view = "main"
        self.section = 0
        self.indices = {"mode": 0, "provider": 0, "profile": 0, "workdir": 0}
        self.scroll_offsets = {section: 0 for section in SECTIONS}
        self.list_meta: dict[str, dict[str, int]] = {}
        self.custom_workdir: str | None = None
        self.workdir_child_index = -1
        self.workdir_text: str | None = None
        self.workdir_layer = "inline"
        self.workdir_dropdown_base: str | None = None
        self.workdir_cursor: tuple[int, int] | None = None
        self.workdir_child_memory: dict[str, str] = {}
        self.last_builder_section = 0
        self.session_index = -1
        self.session_scroll = 0
        self.pending_action: str | None = None
        self.pending_cmd: list[str] | None = None
        self.workdir_override = env_truthy("AI_TUI_WORKDIR_OVERRIDE")
        self.mouse_drag_y: int | None = None
        self.natural_scroll = os.environ.get("AI_TUI_NATURAL_SCROLL", "1").lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        self.message = ""
        self.profiles: list[str] = []
        self.profile_memory: dict[str, str] = {}
        self.workdirs: list[dict[str, Any]] = []
        self.reload()
        self.refresh_sessions(silent=True)

    def reload(self) -> None:
        ai_registry.ensure_registry()
        self.profiles = self.discover_profiles(self.current_provider())
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
        cwd = Path.cwd()
        if not any(self.same_path(str(w.get("path", "")), str(cwd)) for w in self.workdirs):
            self.workdirs.insert(0, current)
        if not self.profiles:
            self.profiles = ["default"]
        if not self.workdirs:
            self.workdirs = [current]
        self.clamp_indices()

    def same_path(self, left: str, right: str) -> bool:
        try:
            return Path(left).expanduser().resolve() == Path(right).expanduser().resolve()
        except OSError:
            return str(Path(left).expanduser()) == str(Path(right).expanduser())

    def home_path(self) -> Path:
        try:
            return HOME.expanduser().resolve()
        except OSError:
            return HOME.expanduser()

    def path_inside_home(self, path: Path) -> bool:
        try:
            path.expanduser().resolve().relative_to(self.home_path())
            return True
        except (OSError, ValueError):
            return False

    def normalize_workdir_path(self, path: Path) -> Path:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            resolved = path.expanduser()
        if getattr(self, "workdir_override", False) or self.path_inside_home(resolved):
            return resolved
        return self.home_path()

    def visible_workdir_child(self, path: Path) -> bool:
        if getattr(self, "workdir_override", False):
            return True
        name = path.name
        if name.startswith(".") or name.startswith("__") or name == "node_modules":
            return False
        return self.path_inside_home(path)

    def clamp_indices(self) -> None:
        self.indices["mode"] = max(0, min(self.indices["mode"], len(MODES) - 1))
        self.indices["provider"] = max(0, min(self.indices["provider"], len(PROVIDERS) - 1))
        self.indices["profile"] = max(0, min(self.indices["profile"], len(self.profiles) - 1))
        self.indices["workdir"] = max(0, min(self.indices["workdir"], len(self.workdirs) - 1))
        for section in SECTIONS:
            self.scroll_offsets[section] = max(0, self.scroll_offsets.get(section, 0))

    def current_mode(self) -> str:
        return MODES[self.indices["mode"]]

    def current_provider(self) -> str:
        return PROVIDERS[self.indices["provider"]]

    def discover_profiles(self, provider: str) -> list[str]:
        return ["default", *ai_registry.existing_provider_profiles(provider)]

    def current_profile_label(self) -> str:
        return self.profiles[self.indices["profile"]] if self.profiles else "default"

    def current_profile_arg(self) -> str:
        profile = self.current_profile_label()
        return "" if profile == "default" else profile

    def current_workdir(self) -> dict[str, Any]:
        custom_workdir = getattr(self, "custom_workdir", None)
        if custom_workdir:
            return {
                "name": "typed",
                "path": custom_workdir,
                "purpose": "typed work directory",
                "favorite": False,
                "archived": False,
            }
        workdirs = getattr(self, "workdirs", [])
        indices = getattr(self, "indices", {"workdir": 0})
        if workdirs:
            return workdirs[indices.get("workdir", 0)]
        return {
            "name": "current",
            "path": str(Path.cwd()),
            "purpose": "current shell directory",
            "favorite": True,
            "archived": False,
        }

    def current_workdir_path(self) -> str:
        return str(self.current_workdir().get("path") or Path.cwd())

    def effective_workdir_path(self) -> str:
        if getattr(self, "workdir_layer", "inline") == "children":
            child = self.selected_workdir_child()
            if child is not None:
                return str(child)
        return str(self.current_workdir().get("path") or Path.cwd())

    def current_profile(self) -> str:
        return self.current_profile_label()

    def remember_current_profile(self) -> None:
        if self.profiles:
            self.profile_memory[self.current_provider()] = self.current_profile_label()

    def restore_profile_for_provider(self) -> None:
        provider = self.current_provider()
        preferred = self.profile_memory.get(provider, "default")
        if preferred in self.profiles:
            self.indices["profile"] = self.profiles.index(preferred)
        else:
            self.indices["profile"] = 0

    def reset_sessions(self) -> None:
        self.session_index = -1
        self.session_scroll = 0

    def selected_workdir_is_cwd(self) -> bool:
        return self.same_path(self.effective_workdir_path(), str(Path.cwd()))

    def commit_workdir_text_if_present(self) -> bool:
        text = getattr(self, "workdir_text", None)
        if text is None:
            return True
        if not text:
            self.message = "workdir is empty"
            return False
        try:
            path = expand_workdir(text)
        except (OSError, RuntimeError, ValueError):
            self.message = "invalid workdir"
            return False
        if not path.is_dir():
            self.message = "workdir is not a directory"
            return False
        self.set_custom_workdir(path, "set")
        return True

    def common_args(self, display: bool = False) -> list[str]:
        args = [self.current_provider()]
        profile = self.current_profile_arg()
        if profile:
            args.extend(["--profile", profile])
        if not self.selected_workdir_is_cwd():
            workdir = short(self.effective_workdir_path()) if display else self.effective_workdir_path()
            args.extend(["--cwd", workdir])
        return args

    def command_line(self) -> str:
        return " ".join(["ai", self.current_mode(), *self.common_args(display=True)])

    def resume_command_line(self, session_id: str) -> str:
        return " ".join(["ai", "resume", *self.common_args(display=True), session_id])

    def selected_session_command_line(self) -> str:
        selected = self.selected_session()
        if not selected or selected.get("_kind") == "new":
            return self.command_line()
        session_id = str(selected.get("session_id") or "")
        return self.resume_command_line(session_id)

    def refresh_sessions(self, silent: bool = False) -> None:
        try:
            data = ai_registry.refresh_session_index()
        except Exception as exc:  # pragma: no cover - defensive TUI boundary
            if not silent:
                self.message = f"session index failed: {exc}"
            return
        if not silent:
            self.message = f"session summaries indexed: {len(data.get('sessions', []))}"

    def prompt(self, label: str, default: str = "") -> str | None:
        curses.echo()
        h, _ = self.stdscr.getmaxyx()
        self.stdscr.move(h - 2, 0)
        self.stdscr.clrtoeol()
        prompt = f"{label} [{default}]: "
        self.stdscr.addstr(h - 2, 0, prompt)
        value = self.stdscr.getstr(h - 2, len(prompt)).decode(errors="replace")
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

    def exec_or_preview(self, cmd: list[str]) -> None:
        if os.environ.get("AI_TUI_DRY_RUN"):
            self.message = "dry-run: " + " ".join(shlex.quote(part) for part in cmd)
            return
        curses.def_prog_mode()
        curses.endwin()
        os.execvp(cmd[0], cmd)

    def confirm_exec_or_preview(self, cmd: list[str]) -> None:
        self.pending_action = "exec"
        self.pending_cmd = cmd
        self.message = "Press Enter again to run; Esc cancels"

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

    def workdir_suggestions(self, text: str, limit: int = 8) -> list[str]:
        raw = text.strip()
        needle = raw.lower()
        suggestions: list[str] = []

        def add(value: str) -> None:
            if value and value not in suggestions:
                suggestions.append(value)

        for item in self.workdirs:
            name = str(item.get("name") or "")
            path = str(item.get("path") or "")
            haystack = f"{name} {short(path)} {path}".lower()
            if not needle or needle in haystack:
                add(path)

        if raw.endswith("/"):
            base = expand_workdir(raw)
            prefix = ""
        elif raw:
            path = expand_workdir(raw)
            base = path.parent
            prefix = path.name
        else:
            base = Path.cwd()
            prefix = ""

        try:
            if base.is_dir():
                for child in sorted(base.iterdir(), key=lambda p: p.name.lower()):
                    if len(suggestions) >= limit:
                        break
                    if child.is_dir() and self.visible_workdir_child(child) and child.name.startswith(prefix):
                        add(str(child))
        except OSError:
            pass

        return suggestions[:limit]

    def resolve_workdir_entry(self, text: str, suggestions: list[str], selected: int) -> str:
        raw = text.strip()
        if suggestions and 0 <= selected < len(suggestions):
            if not raw:
                return suggestions[selected]
            lowered = raw.lower()
            chosen = suggestions[selected]
            for item in self.workdirs:
                name = str(item.get("name") or "")
                path = str(item.get("path") or "")
                if chosen == path and lowered in {name.lower(), short(path).lower(), path.lower()}:
                    return chosen
            if raw in {short(chosen), chosen}:
                return chosen
        for item in self.workdirs:
            name = str(item.get("name") or "")
            path = str(item.get("path") or "")
            if raw and raw.lower() == name.lower():
                return path
        return raw

    def set_custom_workdir(self, path: Path, verb: str = "set", announce: bool = False, text: str = None, layer: str = "inline") -> None:
        self.custom_workdir = str(self.normalize_workdir_path(path))
        self.workdir_child_index = -1
        self.workdir_text = text
        self.workdir_layer = layer
        if layer != "children":
            self.workdir_dropdown_base = None
        self.reset_sessions()
        if announce:
            self.message = f"workdir {verb}: {short(self.custom_workdir)}"

    def focus_workdir_path(self) -> None:
        self.set_custom_workdir(Path(self.current_workdir_path()), "set", text=short(self.current_workdir_path()), layer="path")
        self.workdir_modified = False

    def commit_focused_workdir(self) -> None:
        child = self.selected_workdir_child()
        if child is not None:
            self.remember_workdir_child(child.parent, child.name)
            self.set_custom_workdir(child, "set", text=short(str(child)), layer="path")
        else:
            self.focus_workdir_path()

    def open_workdir_dropdown(self, base: Path | None = None, selected: Path | None = None, restore: bool = True) -> None:
        base = self.normalize_workdir_path(base or Path(self.current_workdir_path()))
        children = self.workdir_children(base)
        if not children:
            self.workdir_layer = "path"
            self.workdir_child_index = -1
            self.workdir_text = short(str(base))
            self.workdir_dropdown_base = None
            self.message = "no child directory"
            return
        self.workdir_text = short(str(base))
        self.workdir_layer = "children"
        self.workdir_dropdown_base = str(base)
        self.workdir_child_index = -1
        if selected is not None:
            selected_name = selected.name
            for idx, child in enumerate(children):
                if child.name == selected_name:
                    self.workdir_child_index = idx
                    break
        if restore and self.workdir_child_index < 0:
            self.restore_workdir_child_selection(base)
        if restore and self.workdir_child_index < 0:
            self.workdir_child_index = 0

    def remember_workdir_child(self, parent: Path, child_name: str) -> None:
        if child_name:
            if not hasattr(self, "workdir_child_memory"):
                self.workdir_child_memory = {}
            self.workdir_child_memory[str(self.normalize_workdir_path(parent))] = child_name

    def restore_workdir_child_selection(self, parent: Path | None = None) -> None:
        base = self.normalize_workdir_path(parent or Path(self.current_workdir_path()))
        remembered = getattr(self, "workdir_child_memory", {}).get(str(base), "")
        self.workdir_child_index = -1
        if not remembered:
            return
        for idx, child in enumerate(self.filtered_workdir_children()):
            if child.name == remembered:
                self.workdir_child_index = idx
                return

    def workdir_text_base_and_prefix(self) -> tuple[Path, str]:
        text = getattr(self, "workdir_text", None)
        if text is None:
            return self.normalize_workdir_path(Path(self.current_workdir_path())), ""
        if text == "":
            return Path.cwd(), ""
        if text in {"~", "~/"}:
            return self.home_path(), ""
        try:
            if text.endswith("/"):
                return self.normalize_workdir_path(expand_workdir(text)), ""
            head, sep, tail = text.rpartition("/")
            if sep:
                base_text = head + "/" if head else "/"
                return self.normalize_workdir_path(expand_workdir(base_text)), tail
            return Path.cwd(), text
        except (OSError, RuntimeError, ValueError):
            return self.normalize_workdir_path(Path(self.current_workdir_path())), ""

    def ensure_workdir_text(self) -> None:
        if getattr(self, "workdir_text", None) is None:
            self.workdir_text = short(self.current_workdir_path())

    def workdir_children(self, path: Path | None = None) -> list[Path]:
        if path is None:
            path, _ = self.workdir_text_base_and_prefix()
        try:
            children = [child for child in path.iterdir() if child.is_dir() and self.visible_workdir_child(child)]
        except OSError:
            return []
        return sorted(children, key=lambda p: p.name.lower())

    def workdir_has_visible_children(self, path: Path) -> bool:
        return bool(self.workdir_children(path))

    def workdir_text_for_child(self, child: Path) -> str:
        text = short(str(child))
        if self.workdir_has_visible_children(child) and not text.endswith("/"):
            text += "/"
        return text

    def filtered_workdir_children(self) -> list[Path]:
        text = getattr(self, "workdir_text", None)
        if getattr(self, "workdir_layer", "inline") == "children":
            base_text = getattr(self, "workdir_dropdown_base", None)
            base = self.normalize_workdir_path(Path(base_text)) if base_text else self.normalize_workdir_path(Path(self.current_workdir_path()))
            return self.workdir_children(base)
        path, filter_text = self.workdir_text_base_and_prefix()
        if text == "":
            return []
        children = self.workdir_children(path)
        if not filter_text:
            return children
            
        needle = filter_text.lower()
        return [child for child in children if child.name.lower().startswith(needle)]

    def workdir_best_match(self) -> Path | None:
        _, filter_text = self.workdir_text_base_and_prefix()
        if not filter_text:
            return None
        children = self.filtered_workdir_children()
        if not children:
            return None
        needle = filter_text.lower()
        for child in children:
            if child.name.lower() == needle:
                return child
        return children[0]

    def workdir_text_with_child(self, child: Path) -> str:
        text = getattr(self, "workdir_text", "") or ""
        head, sep, _ = text.rpartition("/")
        if sep:
            return head + sep + child.name
        return child.name

    def workdir_completion_suffix(self) -> str:
        text = getattr(self, "workdir_text", None)
        if text is None or not getattr(self, "workdir_modified", False):
            return ""
        _, filter_text = self.workdir_text_base_and_prefix()
        if not filter_text:
            return ""
        child = self.workdir_best_match()
        if child is None:
            return ""
        name = child.name
        if not name.lower().startswith(filter_text.lower()):
            return ""
        if len(name) == len(filter_text):
            return "/" if self.workdir_has_visible_children(child) and not text.endswith("/") else ""
        suffix = name[len(filter_text) :]
        if self.workdir_has_visible_children(child):
            suffix += "/"
        return suffix

    def workdir_inline_segment_offset(self) -> int:
        text = getattr(self, "workdir_text", "") or ""
        if text.endswith("/"):
            return cell_width(text)
        head, sep, _ = text.rpartition("/")
        if sep:
            return cell_width(head + sep)
        return 0

    def reset_workdir_child_selection_after_text_change(self) -> None:
        self.workdir_child_index = -1
        self.workdir_layer = "inline"

    def selected_workdir_child(self) -> Path | None:
        if getattr(self, "workdir_layer", "path") != "children":
            return None
        children = self.filtered_workdir_children()
        if not children or self.workdir_child_index < 0:
            return None
        self.workdir_child_index = min(self.workdir_child_index, len(children) - 1)
        return children[self.workdir_child_index]

    def materialize_workdir_child_for_text(self) -> None:
        if getattr(self, "workdir_layer", "inline") != "children":
            return
        child = self.selected_workdir_child()
        if child is None:
            return
        self.remember_workdir_child(child.parent, child.name)
        self.workdir_text = short(str(child))
        self.workdir_child_index = -1

    def remember_focused_workdir_child(self) -> None:
        child = self.selected_workdir_child()
        if child is not None:
            self.remember_workdir_child(child.parent, child.name)

    def cycle_workdir_child(self, direction: int) -> None:
        children = self.filtered_workdir_children()
        if not children:
            self.workdir_child_index = -1
            self.message = "no directory"
            return
        if self.workdir_child_index < 0:
            self.workdir_child_index = 0 if direction > 0 else len(children) - 1
        else:
            self.workdir_child_index = (self.workdir_child_index + direction) % len(children)
        self.remember_focused_workdir_child()
        self.message = f"child {self.workdir_child_index + 1}/{len(children)}: {children[self.workdir_child_index].name}"

    def select_workdir_child_for_inline_down(self) -> None:
        base, prefix = self.workdir_text_base_and_prefix()
        children = self.workdir_children(base)
        if prefix:
            needle = prefix.lower()
            self.workdir_child_index = -1
            for idx, child in enumerate(children):
                if child.name.lower().startswith(needle):
                    self.workdir_child_index = idx
                    return
            return
        remembered = getattr(self, "workdir_child_memory", {}).get(str(self.normalize_workdir_path(base)), "")
        self.workdir_child_index = -1
        if remembered:
            for idx, child in enumerate(children):
                if child.name == remembered:
                    self.workdir_child_index = idx
                    return
        if children:
            self.workdir_child_index = 0

    def enter_workdir_child(self) -> None:
        child = self.selected_workdir_child()
        if child is None:
            self.message = "select a child directory"
            return
        self.remember_workdir_child(child.parent, child.name)
        
        self.set_custom_workdir(child, "entered", text=self.workdir_text_for_child(child), layer="children")
        self.restore_workdir_child_selection()
        
        # If still no selection after restore, select the first item to allow fast Right-arrow chains
        if self.workdir_child_index < 0:
            children = self.filtered_workdir_children()
            if children:
                self.workdir_child_index = 0
                
        self.workdir_modified = True

    def can_enter_focused_workdir_child(self) -> bool:
        child = self.selected_workdir_child()
        return child is not None and self.workdir_has_visible_children(child)

    def current_workdir_browser_path(self) -> Path:
        if getattr(self, "workdir_text", None) is not None:
            if getattr(self, "workdir_layer", "inline") == "children":
                try:
                    path = self.normalize_workdir_path(expand_workdir(self.workdir_text or ""))
                    if path.is_dir():
                        return path
                except (OSError, RuntimeError, ValueError):
                    pass
            base, _ = self.workdir_text_base_and_prefix()
            return base
        return self.normalize_workdir_path(Path(self.current_workdir_path()))

    def enter_workdir_parent(self) -> None:
        focused_child = self.selected_workdir_child()
        if focused_child is not None:
            resolved = self.normalize_workdir_path(focused_child)
        else:
            resolved = self.normalize_workdir_path(Path(self.current_workdir_path()))
        home = self.home_path()
        self.remember_focused_workdir_child()
        if not getattr(self, "workdir_override", False) and resolved == home:
            self.set_custom_workdir(home, "set", text=short(str(home)), layer="path")
            self.workdir_modified = True
            return
        previous_child_name = resolved.name
        parent = resolved.parent
        if parent == resolved:
            self.message = "already at filesystem root"
            return
        if not getattr(self, "workdir_override", False) and not self.path_inside_home(parent):
            parent = home
            
        self.remember_workdir_child(parent, previous_child_name)
        self.set_custom_workdir(parent, "parent", text=short(str(parent)), layer="path")
        if not getattr(self, "workdir_override", False) and parent == home:
            self.workdir_modified = True
            return
        self.open_workdir_dropdown(parent.parent, parent, restore=False)
        self.workdir_modified = True

    def edit_workdir(self) -> None:
        current = self.current_workdir_path()
        text = ""
        selected = 0
        curses.curs_set(1)
        try:
            while True:
                h, w = self.stdscr.getmaxyx()
                top = max(3, h - 11)
                suggestion_rows = max(3, min(8, h - top - 5))
                suggestions = self.workdir_suggestions(text, limit=suggestion_rows + 3)
                selected = max(0, min(selected, max(0, len(suggestions) - 1)))
                for row in range(top, h):
                    self.add_line(row, 0, "", w - 1)
                self.add_line(top, 0, "Workdir entry", w - 1, curses.A_BOLD | curses.A_REVERSE)
                self.add_line(
                    top + 1,
                    0,
                    "Type a name, ~/path, /path, or relative path. Tab completes; enter accepts.",
                    w - 1,
                )
                self.add_line(top + 2, 0, f"current: {short(current)}", w - 1)
                prompt = "cwd> "
                self.add_line(top + 3, 0, prompt + text, w - 1, curses.A_BOLD)
                start = max(0, min(selected - suggestion_rows + 1, max(0, len(suggestions) - suggestion_rows)))
                for n, suggestion in enumerate(suggestions[start : start + suggestion_rows]):
                    item_idx = start + n
                    attr = curses.A_REVERSE if n == selected else 0
                    prefix = "^ " if n == 0 and start > 0 else "v " if n == suggestion_rows - 1 and start + suggestion_rows < len(suggestions) else "  "
                    attr = curses.A_REVERSE if item_idx == selected else 0
                    self.add_line(top + 4 + n, 2, prefix + short(suggestion), w - 3, attr)
                self.stdscr.move(top + 3, min(w - 2, len(prompt) + len(text)))
                self.stdscr.refresh()
                ch = self.stdscr.getch()
                if ch in (27,):
                    self.message = "workdir entry cancelled"
                    return
                if ch in (10, 13):
                    value = self.resolve_workdir_entry(text, suggestions, selected) or current
                    path = expand_workdir(value)
                    if not path.is_dir():
                        self.message = f"not a directory: {short(str(path))}"
                        return
                    self.set_custom_workdir(path, "set")
                    return
                if ch == 9:
                    if suggestions:
                        text = suggestions[selected]
                    continue
                if ch == curses.KEY_DOWN:
                    selected = min(selected + 1, max(0, len(suggestions) - 1))
                    continue
                if ch == curses.KEY_UP:
                    selected = max(selected - 1, 0)
                    continue
                if ch == curses.KEY_NPAGE:
                    selected = min(selected + suggestion_rows, max(0, len(suggestions) - 1))
                    continue
                if ch == curses.KEY_PPAGE:
                    selected = max(selected - suggestion_rows, 0)
                    continue
                if ch in (curses.KEY_BACKSPACE, 127, 8):
                    text = text[:-1]
                    selected = 0
                    continue
                if ch in (curses.KEY_DC, 21):
                    text = ""
                    selected = 0
                    continue
                if 32 <= ch <= 126:
                    text += chr(ch)
                    selected = 0
        finally:
            curses.curs_set(0)

    def launch(self) -> None:
        if not self.commit_workdir_text_if_present():
            return
        prompt = ""
        mode = self.current_mode()
        if mode in {"ask", "task", "plan"}:
            prompt = self.prompt(f"{mode} prompt")
            if not prompt:
                self.message = "cancelled"
                return
        cmd = [
            AI_BIN,
            mode,
            *self.common_args(display=False),
        ]
        if prompt:
            cmd.append(prompt)
        self.confirm_exec_or_preview(cmd)

    def current_sessions(self) -> list[dict[str, Any]]:
        try:
            sessions = ai_registry.recent_sessions(
                self.current_provider(),
                self.current_profile(),
                self.effective_workdir_path(),
                limit=60,
            )
        except Exception as exc:  # pragma: no cover - defensive TUI boundary
            self.message = f"session list failed: {exc}"
            return []
        return [s for s in sessions if s.get("profile") == self.current_profile()]

    def session_rows(self) -> list[dict[str, Any]]:
        sessions = self.current_sessions()
        rows: list[dict[str, Any]] = []
        if sessions:
            latest = dict(sessions[0])
            latest["_kind"] = "last"
            latest["session_id"] = "last"
            latest["title"] = f"Last session: {latest.get('title') or short_time(str(latest.get('updated') or ''))}"
            rows.append(latest)
        rows.append(
            {
                "_kind": "new",
                "session_id": "",
                "title": "New session",
                "last_prompt_summary": "Start with the current command builder values.",
                "last_response_summary": "",
            }
        )
        rows.extend(dict(session, _kind="session") for session in sessions)
        self.session_index = max(-1, min(self.session_index, len(rows) - 1))
        return rows

    def selected_session(self) -> dict[str, Any] | None:
        sessions = self.session_rows()
        if not sessions or self.session_index < 0:
            return None
        return sessions[self.session_index]

    def resume_selected(self) -> None:
        item = self.selected_session()
        if not item:
            self.message = "no selected session"
            return
        if item.get("_kind") == "new":
            self.launch()
            return
        if not self.commit_workdir_text_if_present():
            return
        session_id = str(item.get("session_id") or "")
        if not session_id:
            self.message = "selected session has no id"
            return
        cmd = [
            AI_BIN,
            "resume",
            *self.common_args(display=False),
            session_id,
        ]
        self.confirm_exec_or_preview(cmd)

    def add_line(self, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
        h, _ = self.stdscr.getmaxyx()
        if y < 0 or y >= h or width <= 0:
            return
        try:
            self.stdscr.addnstr(y, x, pad_cells(text, width), width, attr)
        except curses.error:
            pass

    def add_text(self, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
        h, _ = self.stdscr.getmaxyx()
        if y < 0 or y >= h or width <= 0:
            return
        try:
            self.stdscr.addnstr(y, x, fit_cells(text, width), width, attr)
        except curses.error:
            pass

    def selection_attr(self, focused: bool) -> int:
        return curses.A_REVERSE | (curses.A_BOLD if focused else curses.A_DIM)

    def workdir_child_focused(self) -> bool:
        return self.active_section() == "workdir" and getattr(self, "workdir_layer", "path") in {"path", "children"}

    def workdir_inline_focused(self) -> bool:
        return self.active_section() == "workdir" and getattr(self, "workdir_layer", "inline") == "inline"

    def add_segments(self, y: int, x: int, segments: list[tuple[str, int]], width: int) -> int:
        used = 0
        for text, attr in segments:
            remaining = width - used
            if remaining <= 0:
                break
            visible = fit_cells(text, remaining)
            if not visible:
                continue
            self.add_text(y, x + used, visible, remaining, attr)
            used += cell_width(visible)
        return used

    def wrap_lines(self, prefix: str, text: str, width: int, max_lines: int) -> list[str]:
        value = text or "-"
        initial = f"{prefix}: "
        indent = " " * len(initial)
        max_lines = max(1, max_lines)
        first_width = max(8, width - cell_width(initial))
        next_width = max(8, width - cell_width(indent))
        lines: list[str] = []
        for n, raw in enumerate(wrap_cell_text(value, first_width)):
            if n == 0:
                lines.append(initial + raw)
            else:
                for extra in wrap_cell_text(raw, next_width):
                    lines.append(indent + extra)
        if len(lines) > max_lines:
            clipped = lines[:max_lines]
            clipped[-1] = fit_cells(clipped[-1], max(0, width - 3)) + "..."
            return clipped
        return lines

    def draw_header(self, width: int) -> None:
        command = self.command_line()
        if self.active_section() == "sessions":
            command = self.selected_session_command_line()
        self.add_line(0, 0, " " + command, width - 1, curses.A_BOLD | curses.A_REVERSE)
        self.add_line(
            1,
            0,
            f"Provider {self.current_provider().title()} | Profile {self.current_profile()} | Cwd {short(self.effective_workdir_path())}",
            width - 1,
        )

    def draw_choice_row(self, y: int, width: int, section: str, label: str, items: list[str], idx: int) -> None:
        active = self.active_section() == section
        marker = "> " if active else "  "
        label_width = 10
        prefix = f"{marker}{label:<{label_width}}  "
        self.add_line(y, 0, "", width - 1)
        self.add_text(y, 0, prefix, min(width - 1, len(prefix)), curses.A_BOLD if active else 0)

        start_x = len(prefix)
        remaining = max(0, width - start_x - 1)
        if not items or remaining <= 0:
            return

        gap = 3
        full_width = sum(cell_width(item) for item in items) + gap * max(0, len(items) - 1)
        if full_width <= remaining:
            visible_start = 0
            visible_items = items
        else:
            visible_start = idx
            while visible_start > 0:
                trial = items[visible_start - 1 : idx + 1]
                trial_width = sum(cell_width(item) for item in trial) + gap * max(0, len(trial) - 1)
                if trial_width + 4 > remaining:
                    break
                visible_start -= 1
            visible_end = idx + 1
            while visible_end < len(items):
                trial = items[visible_start : visible_end + 1]
                trial_width = sum(cell_width(item) for item in trial) + gap * max(0, len(trial) - 1)
                if trial_width + (4 if visible_start > 0 else 0) + (3 if visible_end + 1 < len(items) else 0) > remaining:
                    break
                visible_end += 1
            visible_items = items[visible_start:visible_end]

        x = start_x
        if visible_start > 0 and remaining >= 4:
            self.add_text(y, x, "... ", min(4, remaining), curses.A_DIM)
            x += 4
        for offset, item in enumerate(visible_items):
            item_idx = visible_start + offset
            if x >= width - 1:
                break
            item_width = min(cell_width(item), max(0, width - 1 - x))
            attr = self.selection_attr(active) if item_idx == idx else curses.A_BOLD if active else 0
            self.add_text(y, x, item, item_width, attr)
            x += item_width
            if offset + 1 < len(visible_items) and x < width - 1:
                self.add_text(y, x, " " * gap, min(gap, width - 1 - x), curses.A_BOLD if active else 0)
                x += gap
        if visible_start + len(visible_items) < len(items) and x < width - 1:
            self.add_text(y, x, "...", min(3, width - 1 - x), curses.A_DIM)

        if not hasattr(self, "list_meta"):
            self.list_meta = {}
        self.list_meta[section] = {
            "y": y,
            "x": 0,
            "w": width,
            "rows": 1,
            "start": visible_start,
            "count": max(1, len(items)),
            "kind": "field",
            "top": y,
            "height": 1,
        }

    def selected_workdir_path(self) -> tuple[str, str, str]:
        child = self.selected_workdir_child()
        if child is not None:
            return short(str(child)), child.name, ""
        self.ensure_workdir_text()
        text = self.workdir_text or ""
        path = self.normalize_workdir_path(Path(self.current_workdir_path()))
        segment = "~" if path == self.home_path() else path.name or short(str(path))
        return text, segment, ""

    def path_segments(self, display_path: str, selected_segment: str, width: int, base_attr: int) -> list[tuple[str, int]]:
        if width <= 0:
            return []
        if not selected_segment:
            return [(fit_cells(display_path, width), base_attr)]
        start = display_path.rfind(selected_segment)
        if start < 0:
            return [(clip_middle(display_path, width), base_attr)]
        end = start + len(selected_segment)
        if start > 0 and display_path[start - 1] != "/":
            return [(clip_middle(display_path, width), base_attr)]

        prefix = display_path[:start]
        selected = display_path[start:end]
        suffix = display_path[end:]
        highlight_attr = self.selection_attr(self.workdir_child_focused())
        full_width = cell_width(display_path)
        if full_width <= width:
            return [(prefix, base_attr), (selected, highlight_attr), (suffix, base_attr)]

        selected_width = cell_width(selected)
        suffix_width = cell_width(suffix)
        if selected_width + suffix_width >= width:
            return [(fit_cells(selected + suffix, width), highlight_attr)]

        prefix_width = width - selected_width - suffix_width
        if prefix_width <= 3:
            clipped_prefix = tail_fit_cells(prefix, prefix_width)
        else:
            clipped_prefix = "..." + tail_fit_cells(prefix, prefix_width - 3)
        return [(clipped_prefix, base_attr), (selected, highlight_attr), (suffix, base_attr)]

    def draw_workdir_children(self, y: int, width: int, rows: int) -> int:
        if rows <= 0:
            return y
        x0 = getattr(self, "workdir_child_x", 2)
        x0 = max(2, min(x0, max(2, width - 12)))
        children = self.filtered_workdir_children()
        if not children:
            self.add_line(y, x0, "", width - x0 - 1, curses.A_DIM)
            for n in range(1, rows):
                self.add_line(y + n, x0, "", width - x0 - 1)
            return y + rows

        children_active = getattr(self, "workdir_layer", "path") == "children"
        
        if not children_active:
            self.workdir_child_index = -1
        if self.workdir_child_index >= len(children):
            self.workdir_child_index = len(children) - 1
        center = rows // 2
        selected_for_window = max(0, self.workdir_child_index if children_active else 0)
        start = max(0, min(selected_for_window - center, max(0, len(children) - rows)))
        visible = children[start : start + rows]
        for n, child in enumerate(visible):
            item_idx = start + n
            selected = children_active and item_idx == self.workdir_child_index
            marker = "> " if selected else "  "
            self.add_line(y + n, x0, "", width - x0 - 1)
            self.add_text(y + n, x0, marker, 2, curses.A_BOLD if selected else 0)
            attr = self.selection_attr(True) if selected else curses.A_DIM
            self.add_text(y + n, x0 + 2, child.name, max(1, width - x0 - 3), attr)
        for n in range(len(visible), rows):
            self.add_line(y + n, x0, "", width - x0 - 1)
        return y + rows

    def draw_workdir_row(self, y: int, width: int) -> None:
        active = self.active_section() == "workdir"
        marker = "> " if active else "  "
        label_width = 10
        prefix = f"{marker}{'Workdir':<{label_width}}  "
        self.add_line(y, 0, "", width - 1)
        self.add_text(y, 0, prefix, min(width - 1, len(prefix)), curses.A_BOLD if active else 0)
        x = len(prefix)
        base_attr = curses.A_BOLD if active else 0

        display_path, selected_segment, status = self.selected_workdir_path()
        right_hint = f" {status}"
        if False and self.workdir_inline_focused() and getattr(self, "workdir_text", None) is not None:
            text = self.workdir_text or ""
            _, typed = self.workdir_text_base_and_prefix()
            suffix = self.workdir_completion_suffix() if typed and self.workdir_inline_focused() else ""
            available = max(1, width - x - 1)
            visible_text = fit_cells(text, available)
            self.add_text(y, x, visible_text, max(1, width - x - 1), base_attr)
            used = cell_width(visible_text)
            if suffix and used < available:
                self.add_text(y, x + used, suffix, min(cell_width(suffix), width - x - used - 1), curses.A_DIM)
            segment_x = x + self.workdir_inline_segment_offset()
            self.workdir_child_x = max(2, segment_x - 2)
            self.workdir_cursor = (y, min(width - 2, x + used))
            self.list_meta["workdir"] = {
                "y": y,
                "x": 0,
                "w": width,
                "rows": 1,
                "start": 0,
                "count": max(1, len(self.filtered_workdir_children())),
                "kind": "field",
                "top": y,
                "height": 1,
            }
            return
        available = max(1, width - x - 1)
        status_width = min(cell_width(right_hint), max(0, available // 4)) if right_hint.strip() else 0
        path_width = max(1, available - status_width)
        segments = self.path_segments(display_path, selected_segment, path_width, base_attr)
        used = self.add_segments(y, x, segments, path_width)
        sx = x + used
        if status_width and sx < width - 1:
            self.add_text(y, sx, right_hint, min(status_width, width - 1 - sx), curses.A_DIM)

        if getattr(self, "workdir_layer", "inline") == "children":
            base_text = getattr(self, "workdir_dropdown_base", None) or self.current_workdir_path()
            base_path_str = short(base_text)
            if not base_path_str.endswith("/"):
                base_path_str += "/"
            self.workdir_child_x = max(2, x + cell_width(base_path_str) - 2)
        else:
            selected_x = x
            for text, attr in segments:
                if attr & curses.A_REVERSE:
                    break
                selected_x += cell_width(text)
            self.workdir_child_x = max(2, selected_x - 2)

        self.list_meta["workdir"] = {
            "y": y,
            "x": 0,
            "w": width,
            "rows": 1,
            "start": 0,
            "count": max(1, len(self.filtered_workdir_children())),
            "kind": "field",
            "top": y,
            "height": 1,
        }

    def draw_controls(self, y: int, width: int, rows: int) -> int:
        child_rows = max(0, rows)
        self.add_line(y, 0, "Command builder", width - 1, curses.A_BOLD)
        self.draw_choice_row(y + 1, width, "mode", "Mode", MODES, self.indices["mode"])
        self.draw_choice_row(y + 2, width, "provider", "Provider", [p.title() for p in PROVIDERS], self.indices["provider"])
        profiles = getattr(self, "profiles", ["default"])
        self.draw_choice_row(y + 3, width, "profile", "Profile", profiles, self.indices["profile"])
        self.draw_workdir_row(y + 4, width)
        next_y = y + 5
        show_dropdown = self.active_section() == "workdir" and getattr(self, "workdir_layer", "path") == "children"
        if show_dropdown:
            next_y = self.draw_workdir_children(next_y, width, child_rows)
        else:
            for n in range(child_rows):
                self.add_line(next_y + n, 2, "", width - 3)
            next_y += child_rows
        return next_y

    def draw_sessions(self, y: int, width: int, rows: int) -> None:
        if rows <= 2:
            return
        real_sessions = self.current_sessions()
        sessions = self.session_rows()
        active = self.active_section() == "sessions"
        title = f"Sessions: {self.current_provider().title()}/{self.current_profile()} ({len(real_sessions)})"
        self.add_line(y, 0, title, width - 1, curses.A_BOLD)
        if not sessions:
            self.add_line(y + 1, 0, "No summaries yet.", width - 1)
            return

        list_y = y + 1
        list_rows = 2 if rows <= 7 else max(3, min(10, rows - 9))
        self.list_meta["sessions"] = {
            "y": list_y,
            "x": 0,
            "w": width,
            "rows": list_rows,
            "start": self.session_scroll,
            "count": len(sessions),
            "top": y,
            "height": list_rows + 2,
        }
        self.session_scroll = max(
            0,
            min(self.session_scroll, max(0, len(sessions) - list_rows)),
        )
        if self.session_index >= 0 and self.session_index < self.session_scroll:
            self.session_scroll = self.session_index
        if self.session_index >= 0 and self.session_index >= self.session_scroll + list_rows:
            self.session_scroll = self.session_index - list_rows + 1
        self.list_meta["sessions"]["start"] = self.session_scroll

        for n in range(list_rows):
            item_idx = self.session_scroll + n
            if item_idx >= len(sessions):
                self.add_line(list_y + n, 0, "", width - 1)
                continue
            item = sessions[item_idx]
            selected_row = self.session_index >= 0 and item_idx == self.session_index
            marker = "> " if selected_row else "  "
            if item.get("_kind") == "new":
                line = f"{marker}New session"
            elif item.get("_kind") == "last":
                line = f"{marker}Last session {short_time(str(item.get('updated') or ''))} {item.get('title','')}"
            else:
                where = short(str(item.get("workdir") or ""))
                line = (
                    f"{marker}{short_time(str(item.get('updated') or ''))} "
                    f"{item.get('profile','')} {where} {item.get('title','')}"
                )
            attr = self.selection_attr(active) if selected_row else 0
            self.add_line(list_y + n, 0, line, width - 1, attr)

        preview_y = list_y + list_rows + 1
        self.add_line(preview_y - 1, 0, "", width - 1)
        if self.session_index < 0:
            self.add_line(preview_y, 0, "", width - 1)
            return
        selected = sessions[self.session_index]
        session_id = str(selected.get("session_id") or "")
        selected_attr = self.selection_attr(active)
        if selected.get("_kind") == "new":
            selected_label = "New session"
        elif selected.get("_kind") == "last":
            selected_label = "Last session (resume --last)"
        else:
            selected_label = session_id
        self.add_line(preview_y, 0, f"Selected: {selected_label}", width - 1, selected_attr)
        row = preview_y + 1
        preview_space = max(2, rows - list_rows - 3)
        max_prompt = max(1, preview_space // 2)
        max_answer = max(1, preview_space - max_prompt)
        for line in self.wrap_lines("Prompt", str(selected.get("last_prompt_summary") or ""), width - 3, max_prompt):
            if row >= y + rows:
                return
            self.add_line(row, 2, line, width - 3)
            row += 1
        for line in self.wrap_lines("Answer", str(selected.get("last_response_summary") or ""), width - 3, max_answer):
            if row >= y + rows:
                return
            self.add_line(row, 2, line, width - 3)
            row += 1

    def draw_main(self) -> None:
        self.stdscr.erase()
        self.list_meta = {}
        self.workdir_cursor = None
        h, w = self.stdscr.getmaxyx()
        if h < 14 or w < 52:
            self.add_line(0, 0, "ai tui: terminal is too small", max(1, w - 1), curses.A_BOLD)
            self.stdscr.refresh()
            return
        self.draw_header(w)
        available_after_builder = max(0, h - 3 - 5 - 3)
        child_rows = max(3, min(8, available_after_builder // 3))
        if available_after_builder - child_rows < 8:
            child_rows = max(0, available_after_builder - 8)
        sessions_y = self.draw_controls(3, w, child_rows) + 1
        self.draw_sessions(sessions_y, w, max(0, h - sessions_y - 4))
        self.add_line(h - 3, 0, "Tab cycles builder | Enter opens sessions/confirm | Esc back/confirm quit | / edits cwd", w - 1, curses.A_DIM)
        self.add_line(h - 2, 0, "Workdir: Down opens sibling list; Left/Right moves directory levels; leaf Right keeps the list open.", w - 1, curses.A_DIM)
        self.add_line(h - 1, 0, self.message, w - 1)
        self.update_cursor()
        self.stdscr.refresh()

    def draw_manage(self) -> None:
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        self.add_line(0, 0, " Management / settings", w - 1, curses.A_BOLD | curses.A_REVERSE)
        lines = [
            "This page holds setup actions so the launch screen stays focused.",
            "",
            "Esc  return to launcher",
        ]
        for n, line in enumerate(lines, start=2):
            self.add_line(n, 0, line, w - 1)
        self.add_line(h - 1, 0, self.message, w - 1)
        self.hide_cursor()
        self.stdscr.refresh()

    def hide_cursor(self) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass

    def update_cursor(self) -> None:
        if self.workdir_inline_focused() and self.workdir_cursor:
            y, x = self.workdir_cursor
            try:
                curses.curs_set(1)
                self.stdscr.move(y, x)
            except curses.error:
                pass
        else:
            self.hide_cursor()

    def draw(self) -> None:
        if self.view == "manage":
            self.draw_manage()
        else:
            self.draw_main()

    def active_section(self) -> str:
        return SECTIONS[self.section]

    def enter_sessions(self) -> None:
        self.last_builder_section = min(self.section, len(BUILDER_SECTIONS) - 1)
        self.section = SECTIONS.index("sessions")
        sessions = self.session_rows()
        self.session_index = 0 if sessions else -1
        self.session_scroll = 0

    def return_to_builder(self) -> None:
        self.section = max(0, min(self.last_builder_section, len(BUILDER_SECTIONS) - 1))

    def move_section(self, direction: int) -> None:
        if self.active_section() == "sessions":
            self.return_to_builder()
            return
        current = min(self.section, len(BUILDER_SECTIONS) - 1)
        self.section = max(0, min(current + direction, len(BUILDER_SECTIONS) - 1))
        self.last_builder_section = self.section
        if self.active_section() == "workdir":
            self.focus_workdir_path()

    def toggle_panel(self) -> None:
        if self.active_section() == "sessions":
            self.return_to_builder()
            self.focus_workdir_path()
        else:
            self.enter_sessions()

    def next_section(self) -> None:
        if self.active_section() == "sessions":
            return
        if self.active_section() == "workdir":
            self.commit_focused_workdir()
            self.section = SECTIONS.index("mode")
            self.last_builder_section = self.section
            return
        current = min(self.section, len(BUILDER_SECTIONS) - 1)
        self.section = (current + 1) % len(BUILDER_SECTIONS)
        self.last_builder_section = self.section
        if self.active_section() == "workdir":
            self.focus_workdir_path()

    def previous_section(self) -> None:
        if self.active_section() == "mode":
            return
        if self.active_section() == "sessions":
            return
        self.move_section(-1)

    def vertical_action(self, direction: int) -> None:
        section = self.active_section()
        if section == "sessions":
            self.move_selection(direction)
        elif section == "profile" and direction > 0:
            self.section = SECTIONS.index("workdir")
            self.last_builder_section = self.section
            self.focus_workdir_path()
        elif section == "workdir":
            if getattr(self, "workdir_layer", "path") == "children":
                self.cycle_workdir_child(direction)
            elif direction > 0:
                current = self.normalize_workdir_path(Path(self.current_workdir_path()))
                if not getattr(self, "workdir_override", False) and current == self.home_path():
                    self.open_workdir_dropdown(current)
                else:
                    self.open_workdir_dropdown(current.parent, current)
            else:
                self.previous_section()
        else:
            self.move_section(direction)

    def complete_workdir_inline(self) -> None:
        if self.active_section() != "workdir":
            self.message = "inline completion is backup-only"
            return
        self.workdir_layer = "inline"
        self.workdir_child_index = -1
        text = getattr(self, "workdir_text", "") or ""
        base, prefix = self.workdir_text_base_and_prefix()
        if not prefix:
            try:
                path = expand_workdir(text)
                if path.is_dir():
                    self.set_custom_workdir(path, "set", text=self.workdir_text_for_child(path), layer="inline")
                    self.workdir_modified = True
                    return
            except (OSError, RuntimeError, ValueError):
                pass
            self.workdir_child_index = -1
            self.message = "type a child prefix"
            return

        child = self.workdir_best_match()
        if child is None:
            if text:
                try:
                    p = expand_workdir(text)
                    if p.is_dir() and not text.endswith("/"):
                        self.set_custom_workdir(p, "set", text=text + "/", layer="inline")
                        self.workdir_modified = True
                        return
                except (OSError, RuntimeError, ValueError):
                    pass
            self.message = "no matches"
            return

        new_text = self.workdir_text_with_child(child)
        if self.workdir_has_visible_children(child):
            new_text += "/"
        self.set_custom_workdir(child, "set", text=new_text, layer="inline")
        self.workdir_modified = True

    def change_option(self, section: str, direction: int) -> None:
        if section == "mode":
            self.indices["mode"] = (self.indices["mode"] + direction) % len(MODES)
        elif section == "provider":
            self.remember_current_profile()
            self.indices["provider"] = (self.indices["provider"] + direction) % len(PROVIDERS)
            self.profiles = self.discover_profiles(self.current_provider())
            self.restore_profile_for_provider()
            self.reset_sessions()
        elif section == "profile":
            self.indices["profile"] = (self.indices["profile"] + direction) % len(self.profiles)
            self.remember_current_profile()
            self.reset_sessions()

    def horizontal_action(self, direction: int) -> None:
        section = self.active_section()
        if section in {"mode", "provider", "profile"}:
            self.change_option(section, direction)
        elif section == "workdir":
            if direction < 0:
                self.enter_workdir_parent()
            else:
                if getattr(self, "workdir_layer", "path") == "children":
                    if not self.can_enter_focused_workdir_child():
                        self.message = "no child directory"
                        return
                    self.commit_focused_workdir()
                self.open_workdir_dropdown(self.normalize_workdir_path(Path(self.current_workdir_path())))
        elif section == "sessions":
            self.move_selection(direction)

    def handle_workdir_text_key(self, ch: int) -> bool:
        if self.active_section() != "workdir":
            return False
        is_edit_key = ch in (curses.KEY_BACKSPACE, 127, 8) or ch in (curses.KEY_DC, 21)
        # Allow more characters for paths (spaces, parentheses, etc.)
        is_text_key = 32 <= ch <= 126
        if not is_edit_key and not is_text_key:
            return False
        if is_text_key and ch == ord("/"):
            return False
        self.message = "press / to edit workdir"
        return True

    def move_selection(self, direction: int) -> None:
        section = self.active_section()
        if section in {"mode", "provider", "profile"}:
            self.change_option(section, direction)
        elif section == "workdir":
            self.vertical_action(direction)
        elif section == "sessions":
            sessions = self.session_rows()
            current = self.session_index if self.session_index >= 0 else 0
            self.session_index = max(0, min(current + direction, len(sessions) - 1))

    def move_to_edge(self, end: bool) -> None:
        section = self.active_section()
        if section == "mode":
            self.indices["mode"] = len(MODES) - 1 if end else 0
        elif section == "provider":
            self.remember_current_profile()
            self.indices["provider"] = len(PROVIDERS) - 1 if end else 0
            self.profiles = self.discover_profiles(self.current_provider())
            self.restore_profile_for_provider()
            self.reset_sessions()
        elif section == "profile":
            self.indices["profile"] = len(self.profiles) - 1 if end else 0
            self.remember_current_profile()
            self.reset_sessions()
        elif section == "workdir":
            self.workdir_layer = "inline"
            self.workdir_child_index = -1
        elif section == "sessions":
            sessions = self.session_rows()
            self.session_index = max(0, len(sessions) - 1) if end else 0

    def page_size(self) -> int:
        if self.active_section() == "workdir":
            return 5
        if self.active_section() in {"mode", "provider", "profile"}:
            return 1
        return max(1, self.list_meta.get(self.active_section(), {}).get("rows", 5))

    def set_section_from_mouse(self, y: int, x: int) -> str | None:
        for section, meta in self.list_meta.items():
            top = meta.get("top", meta.get("y", 0) - 1)
            bottom = top + meta.get("height", meta.get("rows", 0) + 1) - 1
            left = meta.get("x", 0)
            right = left + meta.get("w", 0)
            if top <= y <= bottom and left <= x < right:
                if section in SECTIONS:
                    self.section = SECTIONS.index(section)
                    if section == "workdir":
                        self.workdir_layer = "inline"
                return section
        return None

    def select_mouse_row(self, section: str, y: int) -> None:
        meta = self.list_meta.get(section)
        if not meta:
            return
        if meta.get("kind") == "field":
            return
        row = y - meta.get("y", 0)
        if row < 0 or row >= meta.get("rows", 0):
            return
        item_idx = meta.get("start", 0) + row
        count = meta.get("count", 0)
        if item_idx < 0 or item_idx >= count:
            return
        if section == "mode":
            self.indices["mode"] = item_idx
        elif section == "provider":
            self.remember_current_profile()
            self.indices["provider"] = item_idx
            self.profiles = self.discover_profiles(self.current_provider())
            self.restore_profile_for_provider()
            self.session_index = 0
            self.session_scroll = 0
        elif section == "profile":
            self.indices["profile"] = item_idx
            self.remember_current_profile()
            self.session_index = 0
            self.session_scroll = 0
        elif section == "workdir":
            if self.custom_workdir:
                if item_idx == 0:
                    return
                item_idx -= 1
                self.custom_workdir = None
            self.indices["workdir"] = max(0, min(item_idx, len(self.workdirs) - 1))
            self.session_index = 0
            self.session_scroll = 0
        elif section == "sessions":
            sessions = self.session_rows()
            self.session_index = max(0, min(item_idx, len(sessions) - 1))

    def mouse_scroll_delta(self, bstate: int) -> int:
        button4 = getattr(curses, "BUTTON4_PRESSED", 0)
        button5 = getattr(curses, "BUTTON5_PRESSED", 0)
        if button4 and bstate & button4:
            return 1 if self.natural_scroll else -1
        if button5 and bstate & button5:
            return -1 if self.natural_scroll else 1
        return 0

    def handle_mouse(self) -> None:
        try:
            _, x, y, _, bstate = curses.getmouse()
        except curses.error:
            return
        section = self.set_section_from_mouse(y, x)
        delta = self.mouse_scroll_delta(bstate)
        if delta:
            if section:
                self.move_selection(delta)
            return
        button1_pressed = getattr(curses, "BUTTON1_PRESSED", 0)
        button1_released = getattr(curses, "BUTTON1_RELEASED", 0)
        if button1_pressed and bstate & button1_pressed:
            self.mouse_drag_y = y
            return
        if button1_released and bstate & button1_released:
            start_y = self.mouse_drag_y
            self.mouse_drag_y = None
            if section and start_y is not None and abs(y - start_y) >= 1:
                self.move_selection(1 if y > start_y else -1)
            return

    def handle_manage_key(self, ch: int) -> int | None:
        if ch == 27:
            self.view = "main"
        return None

    def handle_main_key(self, ch: int) -> int | None:
        if ch == 3:
            return 130
        if getattr(self, "pending_action", None):
            action = self.pending_action
            cmd = getattr(self, "pending_cmd", None)
            if action == "exec" and ch in (10, 13) and cmd:
                self.pending_action = None
                self.pending_cmd = None
                self.exec_or_preview(cmd)
                return None
            if action == "quit" and ch == 27:
                return 0
            self.pending_action = None
            self.pending_cmd = None
            self.message = "cancelled"
            return None
        if ch == 27:
            if self.active_section() == "sessions":
                self.return_to_builder()
                self.message = ""
            else:
                self.pending_action = "quit"
                self.pending_cmd = None
                self.message = "Press Esc again to quit"
            return None
        if self.active_section() == "workdir" and self.handle_workdir_text_key(ch):
            return None
        if self.active_section() == "workdir" and ch == ord("/"):
            if hasattr(self, "stdscr"):
                self.edit_workdir()
            else:
                self.message = "press / to edit workdir"
            return None
        if ch == curses.KEY_RIGHT:
            self.horizontal_action(1)
        elif ch == curses.KEY_LEFT:
            self.horizontal_action(-1)
        elif ch == 9:
            if self.active_section() == "workdir" and getattr(self, "workdir_layer", "path") == "children":
                self.commit_focused_workdir()
            else:
                self.next_section()
        elif ch == curses.KEY_BTAB:
            self.message = "use Tab to move focus"
        elif ch == curses.KEY_DOWN:
            self.vertical_action(1)
        elif ch == curses.KEY_UP:
            self.vertical_action(-1)
        elif ch == curses.KEY_NPAGE:
            self.move_selection(self.page_size())
        elif ch == curses.KEY_PPAGE:
            self.move_selection(-self.page_size())
        elif ch == curses.KEY_HOME:
            self.move_to_edge(False)
        elif ch == curses.KEY_END:
            self.move_to_edge(True)
        elif ch == curses.KEY_MOUSE:
            self.handle_mouse()
        elif ch in (10, 13):
            if self.active_section() == "sessions":
                self.resume_selected()
            else:
                if self.active_section() == "workdir":
                    self.commit_focused_workdir()
                self.enter_sessions()
        return None

    def run(self) -> int:
        curses.curs_set(0)
        self.stdscr.keypad(True)
        try:
            mouse_events = getattr(curses, "BUTTON4_PRESSED", 0) | getattr(curses, "BUTTON5_PRESSED", 0)
            mouse_events |= getattr(curses, "BUTTON1_PRESSED", 0) | getattr(curses, "BUTTON1_RELEASED", 0)
            curses.mousemask(mouse_events)
            curses.mouseinterval(0)
        except curses.error:
            pass
        while True:
            self.draw()
            try:
                ch = self.stdscr.getch()
            except KeyboardInterrupt:
                return 130
            result = self.handle_manage_key(ch) if self.view == "manage" else self.handle_main_key(ch)
            if result is not None:
                return result


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("ai tui requires a TTY", file=sys.stderr)
        return 2
    try:
        return curses.wrapper(lambda stdscr: App(stdscr).run())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
