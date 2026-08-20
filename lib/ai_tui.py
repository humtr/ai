#!/usr/bin/env python3
"""Curses launcher/editor for the ai wrapper."""

from __future__ import annotations

import curses
import datetime
import os
import shlex
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

import ai_spec
import ai_provider
import ai_store
import ai_session


# Set ncurses ESC timeout to 50ms (default is 1000ms) to make Esc key responsive.
# Must be set before curses is initialized.
os.environ.setdefault("ESCDELAY", "50")


HOME = Path(os.environ.get("HOME", str(Path.home())))
AI_BIN = os.environ.get("AI_BIN", str(HOME / "bin" / "ai"))
SESSION_SCOPES = ["workdir", "provider", "profile", "all"]
SESSION_SCOPE_LABELS = ["Current Dir", "Provider", "Profile", "All"]
SESSION_SCOPE_FIELDS = {
    "workdir": {"workdir"},
    "provider": {"provider"},
    "profile": {"profile"},
    "all": set(),
}
COMMAND_SECTIONS = ["session", "provider", "profile"]
BUILDER_SECTIONS = ["session", "provider", "profile", "workdir"]
SECTIONS = BUILDER_SECTIONS + ["sessions"]


TZ_UTC9 = datetime.timezone(datetime.timedelta(hours=9))
_SHORT_TIME_CACHE: dict[str, str] = {}


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
    if value in _SHORT_TIME_CACHE:
        return _SHORT_TIME_CACHE[value]
    try:
        val = value.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(val)
        dt_local = dt.astimezone(TZ_UTC9)
        now_local = datetime.datetime.now(TZ_UTC9)
        if dt_local.date() == now_local.date():
            res = dt_local.strftime("%H:%M (Today)")
        elif (now_local.date() - dt_local.date()).days == 1:
            res = dt_local.strftime("%H:%M (Y-day)")
        elif dt_local.year == now_local.year:
            res = dt_local.strftime("%m/%d %H:%M")
        else:
            res = dt_local.strftime("%y/%m/%d %H:%M")
    except Exception:
        cleaned = value.replace("T", " ").replace("Z", "")
        if len(cleaned) >= 16:
            res = cleaned[2:4] + "/" + cleaned[5:7] + "/" + cleaned[8:10] + " " + cleaned[11:16]
        else:
            res = cleaned[:16]
    _SHORT_TIME_CACHE[value] = res
    return res


def set_terminal_title(title: str) -> None:
    title = " ".join(title.split())
    if not title:
        return
    try:
        sys.stdout.write(f"\033]0;{title}\033\\")
        sys.stdout.flush()
    except Exception:
        pass


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
        self.section = SECTIONS.index("workdir")
        self.indices = {"workdir": 0, "provider": 0, "profile": 0, "session": 0}
        self.scroll_offsets = {section: 0 for section in SECTIONS}
        self.list_meta: dict[str, dict[str, int]] = {}
        self.custom_workdir: str | None = None
        self.workdir_child_index = -1
        self.workdir_text: str | None = None
        self.workdir_layer = "inline"
        self.workdir_editing = False
        self.workdir_dropdown_base: str | None = None
        self.workdir_cursor: tuple[int, int] | None = None
        self.workdir_child_memory: dict[str, str] = {}
        self.last_builder_section = BUILDER_SECTIONS.index("workdir")
        self.last_command_section = "session"
        self.session_index = -1
        self.session_scroll = 0
        self.session_memory: dict[str, str] = {}
        self.session_extra_fields: set[str] = set()
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
        self.providers: list[str] = []
        self.profiles: list[str] = []
        self.profile_memory: dict[str, str] = {}
        self.hide_empty_sessions = True
        self.add_profile_active = False
        self.help_popup_active = False
        self.run_confirm_active = False
        self._session_cache_key: tuple[str, ...] | None = None
        self._session_cache_rows: list[dict[str, Any]] = []
        self.workdirs: list[dict[str, Any]] = []
        self.selection_active_attr = curses.A_REVERSE | curses.A_BOLD
        self.selection_inactive_attr = curses.A_REVERSE | curses.A_DIM
        self.reload()
        self.refresh_sessions(silent=True)

    def is_dry_run(self) -> bool:
        if os.environ.get("AI_TUI_DRY_RUN") == "1":
            return True
        if not sys.stdout.isatty() or not sys.stdin.isatty():
            return True
        stdscr = getattr(self, "stdscr", None)
        if stdscr is not None and stdscr.__class__.__name__ == "FakeStdout":
            return True
        return False

    def init_colors(self) -> None:
        try:
            curses.start_color()
            curses.use_default_colors()
            num_colors = getattr(curses, "COLORS", 8)
            
            # 1: Red background for delete mode
            curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_RED)
            
            # 2: Deeper green background for add profile mode
            dark_green = 22 if num_colors >= 256 else curses.COLOR_GREEN
            curses.init_pair(2, curses.COLOR_WHITE, dark_green)
            
            # 3: Dark gray background for help mode
            dark_gray = 235 if num_colors >= 256 else curses.COLOR_BLACK
            curses.init_pair(3, curses.COLOR_WHITE, dark_gray)
            
            # 4: Neutral Black background for popup windows themselves
            curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLACK)
            
            # 5: Green on Black for Add popup accent
            green_accent = curses.COLOR_GREEN if num_colors < 256 else 40
            curses.init_pair(5, green_accent, curses.COLOR_BLACK)
            
            # 6: Red on Black for Delete popup accent
            red_accent = curses.COLOR_RED if num_colors < 256 else 196
            curses.init_pair(6, red_accent, curses.COLOR_BLACK)
            
            # 7: Cyan on Black for Help popup accent
            cyan_accent = curses.COLOR_CYAN if num_colors < 256 else 45
            curses.init_pair(7, cyan_accent, curses.COLOR_BLACK)
            
            # 8: Dark blue background for run confirm mode
            dark_blue = 18 if num_colors >= 256 else curses.COLOR_BLUE
            curses.init_pair(8, curses.COLOR_WHITE, dark_blue)
            
            # 9: Blue on Black for Run confirm popup accent
            blue_accent = curses.COLOR_BLUE if num_colors < 256 else 33
            curses.init_pair(9, blue_accent, curses.COLOR_BLACK)
        except Exception:
            pass

    def reload(self) -> None:
        ai_store.ensure_store()
        cur_provider = self.current_provider() if getattr(self, "providers", None) else None
        cur_profile = self.current_profile_label() if getattr(self, "profiles", None) else None

        self.launch_state = ai_store.load_tui_state()
        self.providers = self.discover_providers()
        preferred_provider = cur_provider or str(self.launch_state.get("last_provider") or "")
        if preferred_provider in self.providers:
            self.indices["provider"] = self.providers.index(preferred_provider)
        self.profiles = self.discover_profiles(self.current_provider())
        preferred_profile = cur_profile or str(self.launch_state.get("last_profile") or "default")
        if preferred_profile in self.profiles:
            self.indices["profile"] = self.profiles.index(preferred_profile)
        else:
            self.indices["profile"] = 0
        self.profile_memory[self.current_provider()] = self.current_profile_label()
        self.workdirs = [
            w
            for w in ai_store.load_workdirs().get("workdirs", [])
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
        providers = getattr(self, "providers", []) or ["codex", "agy", "hermes"]
        self.indices["provider"] = max(0, min(self.indices["provider"], len(providers) - 1))
        self.indices["profile"] = max(0, min(self.indices["profile"], len(self.profiles) - 1))
        self.indices["session"] = max(0, min(self.indices["session"], len(SESSION_SCOPES) - 1))
        self.indices["workdir"] = max(0, min(self.indices["workdir"], len(self.workdirs) - 1))
        for section in SECTIONS:
            self.scroll_offsets[section] = max(0, self.scroll_offsets.get(section, 0))

    def current_provider(self) -> str:
        providers = getattr(self, "providers", []) or ["codex", "agy", "hermes"]
        idx = max(0, min(getattr(self, "indices", {}).get("provider", 0), len(providers) - 1))
        return providers[idx]

    def discover_providers(self) -> list[str]:
        try:
            providers = ai_spec.provider_names()
        except Exception:
            providers = []
        return providers or ["codex", "agy", "hermes"]

    def discover_profiles(self, provider: str) -> list[str]:
        try:
            profiles = ai_provider.list_profiles(provider)
        except Exception:
            profiles = ["default"]
        names = list(profiles or ["default"])
        if "default" in names:
            names = ["default", *[name for name in names if name != "default"]]
        elif names:
            names.insert(0, "default")
        else:
            names = ["default"]
        return names

    def provider_profiles(self, provider: str) -> list[str]:
        try:
            profiles = ai_provider.list_profiles(provider)
        except Exception:
            profiles = ["default"]
        return profiles or ["default"]

    def sync_profiles_for_current_provider(self, preferred: str | None = None) -> None:
        self.profiles = self.discover_profiles(self.current_provider())
        memory = getattr(self, "profile_memory", {})
        target = preferred if preferred in self.profiles else memory.get(self.current_provider(), "default")
        if not hasattr(self, "indices"):
            self.indices = {"provider": 0, "profile": 0, "session": 0, "workdir": 0}
        if target in self.profiles:
            self.indices["profile"] = self.profiles.index(target)
        else:
            self.indices["profile"] = 0

    def current_profile_valid_for_provider(self) -> bool:
        profile = self.current_profile_label()
        if profile == "default":
            return True
        provider = self.current_provider()
        try:
            spec = ai_spec.provider_spec(provider)
            supported = bool((spec.get("profile") or {}).get("supported", False))
        except Exception:
            supported = False
        return supported

    def validate_builder_profile(self) -> bool:
        if self.current_profile_valid_for_provider():
            return True
        self.message = (
            "profile not available for provider: "
            f"{self.current_provider()}/{self.current_profile_label()}"
        )
        return False

    def current_profile_label(self) -> str:
        profiles = getattr(self, "profiles", [])
        indices = getattr(self, "indices", {})
        if not profiles:
            return "default"
        return profiles[indices.get("profile", 0)]

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

    def current_session_scope(self) -> str:
        idx = getattr(self, "indices", {}).get("session", 0)
        if idx < 0 or idx >= len(SESSION_SCOPES):
            return "workdir"
        return SESSION_SCOPES[idx]

    def current_session_filter_fields(self) -> set[str]:
        scope = self.current_session_scope()
        if scope in {"workdir", "all"}:
            return set(SESSION_SCOPE_FIELDS.get(scope, set()))
        fields = set(SESSION_SCOPE_FIELDS.get(scope, set()))
        fields.update(getattr(self, "session_extra_fields", set()))
        return fields

    def session_context_fields(self, scope: str | None = None) -> set[str]:
        scope = scope or self.current_session_scope()
        fields = set(SESSION_SCOPE_FIELDS.get(scope, set()))
        fields.update(getattr(self, "session_extra_fields", set()))
        return fields

    def promote_session_scope(self, field: str) -> None:
        if not hasattr(self, "session_extra_fields"):
            self.session_extra_fields = set()
        self.session_extra_fields.add(field)

    def session_list_title(self) -> str:
        return "SESSION LIST"

    def session_scope_key(self, scope: str | None = None) -> str:
        scope = scope or self.current_session_scope()
        indices = getattr(self, "indices", {})
        provider_index = indices.get("provider", 0)
        profile_index = indices.get("profile", 0)
        providers = getattr(self, "providers", []) or ["codex", "agy", "hermes"]
        provider = providers[provider_index] if 0 <= provider_index < len(providers) else providers[0]
        profiles = getattr(self, "profiles", ["default"]) or ["default"]
        profile = profiles[profile_index] if 0 <= profile_index < len(profiles) else profiles[0]
        fields = self.session_context_fields(scope)
        parts = [scope]
        if "workdir" in fields:
            parts.append(ai_store.normalize_path(self.effective_workdir_path()))
        if "provider" in fields:
            parts.append(provider)
        if "profile" in fields:
            parts.append(profile)
        return ":".join(parts)

    def session_policy_field_keys(self, policy: str | None = None) -> list[str]:
        keys = ["time", "turns", "provider", "profile", "workdir", "title"]
        fields = self.current_session_filter_fields()
        for field in fields:
            if field in keys:
                keys.remove(field)
        return keys

    def session_scope_columns(self, scope: str | None = None) -> str:
        labels = self.session_field_labels()
        return " | ".join(labels)

    def session_scope_field_keys(self, scope: str | None = None) -> list[str]:
        return self.session_policy_field_keys()

    def session_field_labels(self, scope: str | None = None) -> list[str]:
        labels = {
            "time": "Time",
            "turns": "Turns",
            "provider": "Provider",
            "profile": "Profile",
            "workdir": "Workdir",
            "title": "Latest Prompt",
        }
        return [labels[key] for key in self.session_policy_field_keys()]

    def session_field_value(self, item: dict[str, Any], key: str, scope: str | None = None) -> str:
        if key == "time":
            if item.get("_kind") == "new":
                return "New session"
            return short_time(str(item.get("updated") or ""))
        if key == "turns":
            if item.get("_kind") == "new":
                return "-"
            turns = item.get("turns")
            if turns is None:
                return "-"
            return f"{turns}"
        if key == "provider":
            return str(item.get("provider") or self.current_provider())
        if key == "profile":
            return str(item.get("profile") or "-")
        if key == "workdir":
            return short(str(item.get("workdir") or ""))
        if key == "title":
            if item.get("_kind") == "new":
                return "Start with current command settings"
            value = str(item.get("last_prompt_summary") or item.get("title") or "")
            return value or str(item.get("session_id") or "")
        return ""

    def session_column_specs(self, scope: str | None = None, sessions: list[dict[str, Any]] | None = None, width: int | None = None) -> list[tuple[str, str, int]]:
        sessions = sessions or []
        field_specs = {
            "time": ("Time", 18),
            "turns": ("Turns", 6),
            "provider": ("Provider", 10),
            "profile": ("Profile", 80),
            "workdir": ("Workdir", 18),
            "title": ("Latest Prompt", 32),
        }
        keys = self.session_policy_field_keys()
        selected_id = None
        if hasattr(self, "session_index") and self.session_index >= 0:
            cache_rows = getattr(self, "_session_cache_rows", [])
            if cache_rows and self.session_index < len(cache_rows):
                selected_id = cache_rows[self.session_index].get("session_id")
        specs: list[tuple[str, str, int]] = []
        for key in keys:
            label, cap = field_specs[key]
            widths = []
            for item in sessions:
                val = self.session_field_value(item, key, scope)
                is_selected = selected_id is not None and item.get("session_id") == selected_id
                if key == "profile":
                    h_limit = cell_width(label)
                    if not is_selected:
                        widths.append(min(h_limit, cell_width(val)))
                    else:
                        widths.append(cell_width(val))
                else:
                    widths.append(cell_width(val))
            content_width = max(widths or [0])
            column_width = min(max(cell_width(label), content_width), cap)
            specs.append((key, label, column_width))
        if width is not None and specs:
            available = max(0, width - 2 - 2 * max(0, len(specs) - 1))
            min_widths = [cell_width(label) for _, label, _ in specs]
            current = [col_width for _, _, col_width in specs]
            if sum(current) > available:
                while sum(current) > available:
                    shrinkable = [i for i in range(len(current) - 1, -1, -1) if current[i] > min_widths[i]]
                    if not shrinkable:
                        break
                    idx = shrinkable[0]
                    current[idx] -= 1
            elif sum(current) < available:
                title_idx = next((i for i, (k, _, _) in enumerate(specs) if k == "title"), None)
                if title_idx is not None:
                    current[title_idx] += (available - sum(current))
            specs = [(key, label, current[i]) for i, (key, label, _) in enumerate(specs)]
        return specs

    def stable_session_key(self, item: dict[str, Any]) -> str:
        if item.get("_kind") == "new":
            return "new"
        native_ref = str(item.get("native_session_ref") or item.get("session_id") or "")
        return str(
            item.get("stable_session_key")
            or item.get("stable_key")
            or "|".join([
                str(item.get("provider") or self.current_provider()),
                str(item.get("profile") or "default"),
                str(item.get("workdir") or ""),
                native_ref,
            ])
        )

    def invalidate_session_cache(self, reset: bool = False) -> None:
        self._session_cache_key = None
        self._session_cache_rows = []
        if reset:
            self.session_index = -1
            self.session_scroll = 0

    def remember_session_selection(self, scope: str | None = None, sessions: list[dict[str, Any]] | None = None) -> None:
        if not hasattr(self, "session_memory"):
            self.session_memory = {}
        sessions = sessions if sessions is not None else self.current_sessions()
        if not sessions or self.session_index < 0 or self.session_index >= len(sessions):
            return
        if sessions[self.session_index].get("_kind") == "new":
            return
        session_key = self.stable_session_key(sessions[self.session_index])
        if not session_key:
            return
        self.session_memory[self.session_scope_key(scope)] = session_key

    def restore_session_selection(self, sessions: list[dict[str, Any]], scope: str | None = None) -> None:
        if not hasattr(self, "session_memory"):
            self.session_memory = {}
        if not sessions:
            self.session_index = -1
            self.session_scroll = 0
            return
        remembered = self.session_memory.get(self.session_scope_key(scope), "")
        if remembered:
            for idx, item in enumerate(sessions):
                if self.stable_session_key(item) == remembered:
                    self.session_index = idx
                    self.session_scroll = 0
                    return
        self.session_index = self.first_selectable_session_index(sessions)
        self.session_scroll = 0

    def first_selectable_session_index(self, sessions: list[dict[str, Any]]) -> int:
        for idx, item in enumerate(sessions):
            if item.get("_kind") != "new":
                return idx
        return 0 if sessions else -1

    def session_header_segments(self, scope: str, sessions: list[dict[str, Any]], width: int) -> list[tuple[str, int]]:
        segments: list[tuple[str, int]] = [("  ", 0)]
        for idx, (_key, label, col_width) in enumerate(self.session_column_specs(scope, sessions, width)):
            segments.append((pad_cells(label, col_width), curses.A_DIM))
            if idx + 1 < len(self.session_scope_field_keys(scope)):
                segments.append(("  ", 0))
        return segments

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
        self.invalidate_session_cache()

    def directory_is_cwd(self, directory: str) -> bool:
        if not directory:
            return True
        return self.same_path(directory, str(Path.cwd()))

    def directory_args(self, directory: str, display: bool = False) -> list[str]:
        if not directory or self.directory_is_cwd(directory):
            return []
        value = short(directory) if display else directory
        return ["-d", value]

    def selected_workdir_is_cwd(self) -> bool:
        return self.directory_is_cwd(self.effective_workdir_path())

    def commit_workdir_text_if_present(self) -> bool:
        if getattr(self, "workdir_layer", "inline") == "inline" and getattr(self, "workdir_child_index", -1) >= 0:
            children = self.filtered_workdir_children()
            if 0 <= self.workdir_child_index < len(children):
                child = children[self.workdir_child_index]
                self.set_custom_workdir(child, "set", text=self.workdir_text_for_child(child), layer="path")
                self.workdir_modified = False
                self.workdir_editing = False
                return True
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
        self.set_custom_workdir(path, "set", text=short(str(path)), layer="path")
        self.workdir_modified = False
        self.workdir_editing = False
        return True

    def common_args(self, display: bool = False) -> list[str]:
        args = [self.current_provider()]
        profile = self.current_profile_arg()
        if profile:
            args.extend(["-p", profile])
        args.extend(self.directory_args(self.effective_workdir_path(), display))
        return args

    def command_line(self) -> str:
        return " ".join(["ai", "run", *self.common_args(display=True)])

    def run_command(self) -> list[str]:
        return [AI_BIN, "run", *self.common_args(display=False)]

    def session_args(self, item: dict[str, Any], display: bool = False) -> list[str]:
        provider = str(item.get("provider") or self.current_provider())
        profile = self.session_launch_profile(item)
        workdir = str(item.get("workdir") or "")
        ref = str(item.get("native_session_ref") or item.get("session_id") or "")
        args = [provider]
        if profile and profile != "default":
            args.extend(["-p", profile])
        if workdir and not Path(workdir).expanduser().is_dir():
            workdir = self.effective_workdir_path()
        if workdir:
            args.extend(self.directory_args(workdir, display))
        if ref:
            args.extend(["-s", ref])
        return args

    def session_command_line(self, item: dict[str, Any]) -> str:
        return " ".join(["ai", "run", *self.session_args(item, display=True)])

    def session_command(self, item: dict[str, Any]) -> list[str]:
        return [AI_BIN, "run", *self.session_args(item, display=False)]

    def session_launch_profile(self, item: dict[str, Any]) -> str:
        selected = self.current_profile_label() or "default"
        provider = str(item.get("provider") or self.current_provider())
        if provider == self.current_provider() or selected == "default":
            return selected
        try:
            if selected in self.provider_profiles(provider):
                return selected
        except Exception:
            pass
        return str(item.get("profile") or "default")

    def selected_session_command_line(self) -> str:
        selected = self.selected_session()
        if not selected or selected.get("_kind") == "new":
            return self.command_line()
        if not str(selected.get("native_session_ref") or selected.get("session_id") or ""):
            return self.command_line()
        return self.session_command_line(selected)

    def window_title(self) -> str:
        if self.view == "manage":
            return "ai manage"
        if self.active_section() == "sessions":
            return self.selected_session_command_line()
        return self.command_line()

    def selected_session_summary(self) -> str:
        selected = self.selected_session()
        if not selected or not str(selected.get("native_session_ref") or selected.get("session_id") or ""):
            return f"Provider {self.current_provider().title()} | Profile {self.current_profile()} | Cwd {short(self.effective_workdir_path())}"
        provider = str(selected.get("provider") or self.current_provider())
        profile = self.session_launch_profile(selected)
        workdir = str(selected.get("workdir") or self.effective_workdir_path())
        return f"Provider {provider.title()} | Profile {profile} | Cwd {short(workdir)}"

    def sync_terminal_title(self) -> None:
        title = self.window_title()
        if getattr(self, "_terminal_title", None) == title:
            return
        self._terminal_title = title
        set_terminal_title(title)

    def session_choice_command_line(self) -> str:
        return self.command_line()

    def refresh_sessions(self, silent: bool = False) -> None:
        try:
            data = ai_session.refresh_session_index()
        except Exception as exc:  # pragma: no cover - defensive TUI boundary
            if not silent:
                self.message = f"session index failed: {exc}"
            return
        if not silent:
            self.message = f"session summaries indexed: {len(data.get('sessions', []))}"

    def set_status_message(self, en_msg: str, ko_msg: str) -> None:
        # Revert status messages to English for consistency with the TUI locale.
        self.message = en_msg

    def draw_popup_window(self, title: str, lines: list[Any], accent_color_pair: int = 4, align_right: bool = False, has_input: bool = False, input_prompt: str = "", input_text: str = "") -> None:
        self.draw_main_background()
        h, w = self.stdscr.getmaxyx()
        
        max_line_w = 0
        for line in lines:
            if isinstance(line, tuple):
                max_line_w = max(max_line_w, cell_width(line[0]) + cell_width(line[1]) + 5)
            else:
                max_line_w = max(max_line_w, cell_width(line))
        if has_input:
            max_line_w = max(max_line_w, cell_width(input_prompt) + cell_width(input_text) + 10)
            
        width = min(w - 4, max(48, max_line_w + 8))
        height = len(lines) + 4
        if has_input:
            height += 2
            
        top = (h - height) // 2
        left = (w - width) // 2
        
        # Base neutral colors (Pair 4)
        popup_attr = curses.color_pair(4)
        # Accent colors (Pair 5=Green, Pair 6=Red, Pair 7=Cyan, Pair 4=White)
        accent_attr = curses.color_pair(accent_color_pair) | curses.A_BOLD
        
        for dy in range(height):
            y = top + dy
            if dy == 0:
                self.add_line(y, left, "┌" + "─" * (width - 2) + "┐", width, accent_attr)
            elif dy == height - 1:
                self.add_line(y, left, "└" + "─" * (width - 2) + "┘", width, accent_attr)
            else:
                self.add_text(y, left, "│", 1, accent_attr)
                self.add_text(y, left + 1, " " * (width - 2), width - 2, popup_attr)
                self.add_text(y, left + width - 1, "│", 1, accent_attr)
                
        title_str = f" {title} "
        title_x = left + (width - cell_width(title_str)) // 2
        self.add_text(top, title_x, title_str, width - 4, curses.color_pair(accent_color_pair) | curses.A_REVERSE | curses.A_BOLD)
        
        content_w = width - 6
        for i, line in enumerate(lines):
            y = top + 2 + i
            if isinstance(line, tuple):
                shortcut, description = line
                sh_str = f"{shortcut:<13}"
                # Shortcut in Bold
                self.add_text(y, left + 3, sh_str, 13, popup_attr | curses.A_BOLD)
                # Description not bold
                self.add_text(y, left + 3 + 13, description, content_w - 13, popup_attr)
            else:
                if align_right:
                    aligned_line = line.rjust(content_w)
                else:
                    aligned_line = line
                line_attr = popup_attr
                if line.startswith("───"):
                    line_attr |= curses.A_DIM
                elif "Shortcuts" in line:
                    line_attr |= curses.A_BOLD
                self.add_text(y, left + 3, aligned_line, content_w, line_attr)
                
        if has_input:
            sep_y = top + height - 3
            self.add_line(sep_y, left, "├" + "─" * (width - 2) + "┤", width, accent_attr)
            input_prompt_full = f" {input_prompt}{input_text}"
            self.add_text(top + height - 2, left + 3, input_prompt_full, content_w, popup_attr | curses.A_BOLD)
            
        self.stdscr.refresh()

    def show_help_popup(self) -> None:
        self.help_popup_active = True
        lines = [
            "Keyboard Shortcuts",
            "──────────────────",
            ("Tab", "Cycle panels (Workdir -> Command -> Sessions)"),
            ("Shift-Tab", "Cycle panels backwards"),
            ("Enter", "Open sessions / Confirm action"),
            ("Esc", "Back / Exit launcher"),
            ("Ctrl-E or /", "Edit Cwd in Workdir panel"),
            ("Ctrl-A", "Add profile (in Profile panel)"),
            ("Ctrl-D", "Delete profile / session"),
            ("Ctrl-T", "Toggle automated/empty sessions"),
            ("Arrow Keys", "Navigate choices / items"),
            "",
            "Press any key to close..."
        ]
        try:
            self.draw_popup_window(
                title="HELP GUIDE",
                lines=lines,
                accent_color_pair=7,
                align_right=False,
                has_input=False
            )
            self.stdscr.getch()
        finally:
            self.help_popup_active = False
            self.draw()

    def prompt(self, label: str, default: str = "", bg_color_pair: int = 0) -> str | None:
        curses.noecho()
        curses.curs_set(1)
        h, w = self.stdscr.getmaxyx()
        input_text = ""
        
        if bg_color_pair == 1:
            self.delete_confirm_active = True
        elif bg_color_pair == 2:
            self.add_profile_active = True
        self.draw()
        
        try:
            while True:
                if bg_color_pair == 2:
                    lines = ["Enter a name for the new profile."]
                    input_prompt = "Profile name: "
                    self.draw_popup_window(
                        title=label.upper(),
                        lines=lines,
                        accent_color_pair=5,
                        align_right=False,
                        has_input=True,
                        input_prompt=input_prompt,
                        input_text=input_text
                      )
                    max_line_w = max(cell_width(label), cell_width(input_prompt) + cell_width(input_text) + 10)
                    pw = min(w - 4, max(48, max_line_w + 8))
                    p_height = len(lines) + 6
                    p_top = (h - p_height) // 2
                    p_left = (w - pw) // 2
                    cursor_y = p_top + p_height - 2
                    cursor_x = p_left + 3 + cell_width(f" {input_prompt}") + cell_width(input_text)
                else:
                    self.stdscr.move(h - 2, 0)
                    self.stdscr.clrtoeol()
                    prompt_str = f"{label} [{default}]: {input_text}"
                    attr = curses.A_BOLD
                    if bg_color_pair > 0:
                        attr |= curses.color_pair(bg_color_pair)
                    self.add_line(h - 2, 0, prompt_str, w - 1, attr)
                    cursor_y = h - 2
                    cursor_x = cell_width(prompt_str)
                    
                self.stdscr.move(cursor_y, min(w - 2, cursor_x))
                self.stdscr.refresh()
                
                ch = self.stdscr.getch()
                if ch == 27:
                    return None
                elif ch in (10, 13):
                    res = input_text.strip() or default
                    return res if res else None
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    input_text = input_text[:-1]
                elif 32 <= ch <= 126:
                    input_text += chr(ch)
        finally:
            curses.curs_set(0)
            self.delete_confirm_active = False
            self.add_profile_active = False
            self.draw()

    def confirm_delete(self, label: str) -> bool:
        curses.noecho()
        curses.curs_set(1)
        h, w = self.stdscr.getmaxyx()
        
        self.delete_confirm_active = True
        input_text = ""
        
        try:
            while True:
                lines = [label]
                input_prompt = "Type 'yes' to delete: "
                self.draw_popup_window(
                    title="DELETE CONFIRMATION",
                    lines=lines,
                    accent_color_pair=6,
                    align_right=True,
                    has_input=True,
                    input_prompt=input_prompt,
                    input_text=input_text
                )
                
                max_line_w = max(cell_width(label), cell_width(input_prompt) + cell_width(input_text) + 10)
                pw = min(w - 4, max(48, max_line_w + 8))
                p_height = len(lines) + 6
                p_top = (h - p_height) // 2
                p_left = (w - pw) // 2
                cursor_y = p_top + p_height - 2
                cursor_x = p_left + 3 + cell_width(f" {input_prompt}") + cell_width(input_text)
                
                try:
                    self.stdscr.move(cursor_y, min(w - 2, cursor_x))
                except curses.error:
                    pass
                
                ch = self.stdscr.getch()
                
                if ch == 27:
                    return False
                    
                if ch in (10, 13):
                    if input_text == "yes":
                        return True
                    else:
                        return False
                        
                elif ch in (curses.KEY_BACKSPACE, 127, 8):
                    input_text = input_text[:-1]
                    
                elif 32 <= ch <= 126:
                    new_char = chr(ch)
                    candidate = input_text + new_char
                    if not "yes".startswith(candidate):
                        return False
                    input_text = candidate
        finally:
            curses.curs_set(0)
            self.delete_confirm_active = False
            self.draw()

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
        self.remember_executed_selection(cmd)
        curses.def_prog_mode()
        curses.endwin()
        os.execvp(cmd[0], cmd)

    def remember_executed_selection(self, cmd: list[str]) -> None:
        provider = self.current_provider()
        profile = self.current_profile_label()
        try:
            run_index = cmd.index("run")
            if run_index + 1 < len(cmd):
                provider = cmd[run_index + 1]
            if "-p" in cmd:
                profile_index = cmd.index("-p")
                if profile_index + 1 < len(cmd):
                    profile = cmd[profile_index + 1]
                else:
                    profile = "default"
            else:
                profile = "default"
        except (ValueError, IndexError):
            pass
        state = {
            "version": 1,
            "last_provider": provider,
            "last_profile": profile,
        }
        ai_store.save_tui_state(state)
        self.launch_state = state
        if not hasattr(self, "profile_memory"):
            self.profile_memory = {}
        self.profile_memory[provider] = profile


    # Stage 6.4 TUI structural helpers
    def section_name(self) -> str:
        sections = list(SECTIONS)
        try:
            section = int(getattr(self, "section", 0))
        except (TypeError, ValueError):
            section = 0
        if section < 0 or section >= len(sections):
            section = 0
            self.section = section
        return sections[section]

    def set_section(self, name: str) -> None:
        sections = list(SECTIONS)
        if name not in sections:
            name = sections[0]
        self.section = sections.index(name)
        if name in BUILDER_SECTIONS:
            self.last_builder_section = BUILDER_SECTIONS.index(name)
        if name in COMMAND_SECTIONS:
            self.last_command_section = name
        self.workdir_editing = False

    def command_focus_section(self) -> str:
        section = getattr(self, "last_command_section", "session")
        if section in COMMAND_SECTIONS:
            return section
        return "session"

    def can_focus_sessions(self) -> bool:
        try:
            return bool(self.current_sessions())
        except Exception:
            return False

    def tab_sections(self) -> list[str]:
        sections = ["workdir", self.command_focus_section()]
        if self.can_focus_sessions():
            sections.append("sessions")
        return sections

    def normalize_focus(self) -> None:
        sections = self.tab_sections()
        current = self.section_name()
        if current not in sections:
            self.set_section(sections[0])

    def move_focus_next(self) -> None:
        sections = self.tab_sections()
        current = self.section_name()
        if current not in sections:
            self.set_section(sections[0])
            return
        target = sections[(sections.index(current) + 1) % len(sections)]
        if target == "sessions":
            self.enter_sessions()
        else:
            self.set_section(target)

    def move_focus_prev(self) -> None:
        sections = self.tab_sections()
        current = self.section_name()
        if current not in sections:
            self.set_section(sections[-1])
            return
        target = sections[(sections.index(current) - 1) % len(sections)]
        if target == "sessions":
            self.enter_sessions()
        else:
            self.set_section(target)

    def in_run_confirm(self) -> bool:
        return getattr(self, "pending_action", None) == "exec" and bool(getattr(self, "pending_cmd", None))

    def enter_run_confirm(self, cmd: list[str] | None) -> None:
        if not cmd:
            self.message = "nothing to run"
            return
            
        if self.is_dry_run():
            self.pending_action = "exec"
            self.pending_cmd = list(cmd)
            self.message = "RUN ready: Enter to run | Esc cancel | Tab cancel + next"
            return

        self.pending_action = "exec"
        self.pending_cmd = list(cmd)
        self.run_confirm_active = True
        
        cmd_str = " ".join(cmd)
        h, w = self.stdscr.getmaxyx()
        max_width = w - 12
        if len(cmd_str) > max_width:
            cmd_str = cmd_str[:max_width - 3] + "..."
            
        lines = [
            "Are you sure you want to run the following command?",
            "",
            f"  {cmd_str}",
            "",
            "Press Enter to confirm and run.",
            "Press Esc to cancel."
        ]
        
        try:
            while True:
                self.draw_popup_window(
                    title="RUN CONFIRMATION",
                    lines=lines,
                    accent_color_pair=9,
                    align_right=False,
                    has_input=False
                )
                
                ch = self.stdscr.getch()
                if ch in (10, 13):
                    self.execute_run_confirm()
                    return
                elif ch == 27:
                    self.leave_run_confirm("run cancelled")
                    return
        finally:
            self.run_confirm_active = False
            self.draw()

    def leave_run_confirm(self, message: str = "run cancelled") -> None:
        self.pending_action = None
        self.pending_cmd = None
        self.message = message

    def execute_run_confirm(self) -> None:
        cmd = list(self.pending_cmd or [])
        self.pending_action = None
        self.pending_cmd = None
        if not cmd:
            self.message = "nothing to run"
            return
        self.exec_or_preview(cmd)

    def workdir_dropdown_open(self) -> bool:
        return getattr(self, "workdir_layer", "inline") == "children"

    def commit_workdir_dropdown(self) -> bool:
        if not self.workdir_dropdown_open():
            return False
        self.commit_focused_workdir()
        self.set_section("workdir")
        return True

    def cancel_workdir_dropdown(self) -> bool:
        self.workdir_editing = False
        if not self.workdir_dropdown_open():
            return False
        self.focus_workdir_path()
        self.set_section("workdir")
        self.message = "workdir selection cancelled"
        return True

    def command_for_current_focus(self) -> list[str] | None:
        if self.section_name() == "workdir" and not self.commit_workdir_text_if_present():
            return None
        if self.section_name() == "sessions":
            selected = self.selected_session()
            if (
                selected
                and selected.get("_kind") != "new"
                and str(selected.get("native_session_ref") or selected.get("session_id") or "")
            ):
                return self.session_command(selected)
        if not self.validate_builder_profile():
            return None
        return self.run_command()

    def key_is_tab(self, key: object) -> bool:
        return key in (9, "\t")

    def key_is_shift_tab(self, key: object) -> bool:
        return key == getattr(curses, "KEY_BTAB", 353) or key in (353, "\x1b[Z")

    def key_is_enter(self, key: object) -> bool:
        return key in (10, 13, "\n", "\r", getattr(curses, "KEY_ENTER", 343))

    def key_is_escape(self, key: object) -> bool:
        return key in (27, "\x1b")

    def handle_navigation_key(self, key: object) -> bool:
        if self.key_is_tab(key):
            return self.handle_tab()
        if self.key_is_shift_tab(key):
            return self.handle_shift_tab()
        if self.key_is_enter(key):
            return self.handle_enter()
        if self.key_is_escape(key):
            return self.handle_escape()
        return False

    def handle_tab(self) -> bool:
        if self.in_run_confirm():
            self.leave_run_confirm("run cancelled")
        if self.workdir_dropdown_open():
            self.commit_workdir_dropdown()
            if self.is_dry_run():
                return True
        section = self.section_name()
        if section == "workdir":
            self.set_section(self.command_focus_section())
        elif section in COMMAND_SECTIONS:
            self.last_command_section = section
            self.enter_sessions()
        elif section == "sessions":
            self.set_section("workdir")
        else:
            self.set_section("workdir")
        return True

    def handle_shift_tab(self) -> bool:
        if self.in_run_confirm():
            self.leave_run_confirm("run cancelled")
        if self.workdir_dropdown_open():
            self.commit_workdir_dropdown()
            if self.is_dry_run():
                return True
        section = self.section_name()
        if section == "workdir":
            self.enter_sessions()
        elif section in COMMAND_SECTIONS:
            self.set_section("workdir")
        elif section == "sessions":
            target = getattr(self, "last_command_section", "profile") or "profile"
            self.set_section(target)
        else:
            self.set_section("workdir")
        return True

    def handle_enter(self) -> bool:
        if self.in_run_confirm():
            self.execute_run_confirm()
            return True
        if self.workdir_dropdown_open():
            if self.commit_workdir_dropdown():
                self.set_section(self.command_focus_section())
            return True
        section = self.section_name()
        if section == "sessions":
            cmd = self.command_for_current_focus()
            if cmd is not None:
                self.enter_run_confirm(cmd)
            return True
        if section == "workdir":
            if not self.commit_workdir_text_if_present():
                return True
            self.set_section(self.command_focus_section())
            return True
        if section in COMMAND_SECTIONS:
            if self.can_focus_sessions():
                self.enter_sessions()
            else:
                self.message = "no sessions"
            return True
        self.set_section("workdir")
        return True

    def handle_escape(self) -> bool:
        self.workdir_editing = False
        if self.in_run_confirm():
            self.leave_run_confirm("run cancelled")
            return True
        if self.cancel_workdir_dropdown():
            return True
        return False

    def confirm_exec_or_preview(self, cmd: list[str]) -> None:
        self.enter_run_confirm(cmd)

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
        p = expand_workdir(path)
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.message = f"failed to create workdir: {exc}"
            return
        data = ai_store.load_workdirs()
        items = data.setdefault("workdirs", [])
        items.append({"name": name, "path": str(p), "purpose": purpose, "favorite": False, "archived": False})
        ai_store.save_workdirs(data)
        self.message = "added workdir"
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

    def set_custom_workdir(
        self,
        path: Path,
        verb: str = "set",
        announce: bool = False,
        text: str = None,
        layer: str = "inline",
        promote: bool = True,
    ) -> None:
        previous = getattr(self, "custom_workdir", None)
        self.custom_workdir = str(self.normalize_workdir_path(path))
        self.workdir_child_index = -1
        self.workdir_text = text
        self.workdir_layer = layer
        if layer != "children":
            self.workdir_dropdown_base = None
        if previous != self.custom_workdir:
            if promote:
                self.promote_session_scope("workdir")
                self.invalidate_session_cache(reset=True)
        if announce:
            self.message = f"workdir {verb}: {short(self.custom_workdir)}"

    def focus_workdir_path(self) -> None:
        self.set_custom_workdir(
            Path(self.current_workdir_path()),
            "set",
            text=short(self.current_workdir_path()),
            layer="path",
            promote=False,
        )
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

    def add_profile(self) -> None:
        provider = self.current_provider()
        try:
            spec = ai_spec.provider_spec(provider)
            supported = bool((spec.get("profile") or {}).get("supported", False))
        except Exception:
            supported = False

        if not supported:
            self.set_status_message(f"provider {provider} does not support profiles", f"프로바이더 {provider}는 프로필을 지원하지 않는다.")
            return

        name = self.prompt("Add profile name", bg_color_pair=2)
        if not name:
            self.set_status_message("add profile cancelled", "프로필 생성을 취소했다.")
            return

        try:
            ai_provider.validate_profile_name(name)
        except ValueError as e:
            self.set_status_message(str(e), f"오류: {e}")
            return

        base = ai_provider.profile_base_dir(provider)
        if not base:
            self.set_status_message(f"provider {provider} has no profile base directory", "프로필 디렉터리가 없다.")
            return

        path = base / name
        try:
            path.mkdir(parents=True, exist_ok=True)
            self.set_status_message(f"profile created: {provider}/{name}", "프로필을 만들었다.")
            self.reload()
            if name in self.profiles:
                self.indices["profile"] = self.profiles.index(name)
        except Exception as e:
            self.set_status_message(f"failed to create profile: {e}", f"프로필 생성 실패: {e}")

    def delete_profile(self) -> None:
        profile = self.current_profile_label()
        if profile == "default":
            self.set_status_message("cannot delete default profile", "기본 프로필은 삭제할 수 없다.")
            return

        provider = self.current_provider()
        self.sync_profiles_for_current_provider(profile)
        if profile not in self.profiles:
            self.set_status_message(f"profile not found for provider: {provider}/{profile}", f"프로필을 찾을 수 없다: {provider}/{profile}")
            return

        confirm = self.confirm_delete(f"Delete profile '{profile}'?")
        if not confirm:
            self.set_status_message("delete profile cancelled", "삭제를 취소했다.")
            return

        base = ai_provider.profile_base_dir(provider)
        if not base:
            self.set_status_message(f"provider {provider} has no profile base directory", "프로필 디렉터리가 없다.")
            return

        path = base / profile
        try:
            if path.is_dir():
                import shutil
                shutil.rmtree(path)
                self.set_status_message(f"deleted profile: {provider}/{profile}", "프로필을 삭제했다.")
            else:
                self.set_status_message(f"profile not found on disk: {provider}/{profile}", "프로필을 찾을 수 없다.")
            self.reload()
            self.indices["profile"] = 0
        except Exception as e:
            self.set_status_message(f"failed to delete profile: {e}", f"삭제 실패: {e}")

    def delete_session(self) -> None:
        item = self.selected_session()
        if not item:
            self.set_status_message("no session selected to delete", "삭제할 세션이 없다.")
            return
        if item.get("_kind") == "new":
            self.set_status_message("cannot delete 'new session' template", "템플릿은 삭제할 수 없다.")
            return
        
        session_id = item.get("session_id") or ""
        path_str = item.get("path") or item.get("source_path") or ""
        if not path_str:
            self.set_status_message("selected session has no file path", "파일 경로가 없다.")
            return
        
        confirm = self.confirm_delete(f"Delete session '{session_id[:8]}'")
        if not confirm:
            self.set_status_message("delete session cancelled", "삭제를 취소했다.")
            return
        
        try:
            path = Path(path_str)
            if path.is_file():
                path.unlink()
                self.set_status_message(f"deleted session: {session_id[:8]}", "세션을 삭제했다.")
            else:
                self.set_status_message(f"session file not found: {path_str}", "세션 파일을 찾을 수 없다.")
            ai_session.refresh_session_index()
            self.invalidate_session_cache(reset=True)
            self.session_index = -1
        except Exception as e:
            self.set_status_message(f"failed to delete session: {e}", f"삭제 실패: {e}")

    def toggle_empty_sessions(self) -> None:
        old_sessions = self.session_rows()
        old_idx = self.session_index
        old_selected_id = None
        if 0 <= old_idx < len(old_sessions):
            old_selected_id = old_sessions[old_idx].get("session_id")

        self.hide_empty_sessions = not getattr(self, "hide_empty_sessions", False)
        self.invalidate_session_cache(reset=False)
        
        new_sessions = self.session_rows()
        if not new_sessions:
            self.session_index = -1
        elif old_selected_id is not None:
            found_idx = -1
            for idx, s in enumerate(new_sessions):
                if s.get("session_id") == old_selected_id:
                    found_idx = idx
                    break
            if found_idx >= 0:
                self.session_index = found_idx
            else:
                self.session_index = max(0, min(old_idx, len(new_sessions) - 1))
        else:
            self.session_index = -1

        if self.hide_empty_sessions:
            self.message = "automated/empty sessions hidden (turns = 0)"
        else:
            self.message = "all sessions shown"

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
        if not self.validate_builder_profile():
            return
        self.confirm_exec_or_preview(self.run_command())

    def current_sessions(self) -> list[dict[str, Any]]:
        scope = self.current_session_scope()
        fields = self.current_session_filter_fields()
        context_fields = self.session_context_fields(scope)
        provider = self.current_provider() if "provider" in fields else None
        profile = self.current_profile_label() if "profile" in fields else None
        workdir = self.effective_workdir_path() if "workdir" in fields else None
        cache_provider = self.current_provider() if "provider" in context_fields else ""
        cache_profile = self.current_profile_label() if "profile" in context_fields else ""
        cache_workdir = self.effective_workdir_path() if "workdir" in context_fields else ""
        key = (scope, cache_provider, cache_profile, ai_store.normalize_path(cache_workdir))
        if not hasattr(self, "_session_cache_key"):
            self._session_cache_key = None
        if not hasattr(self, "_session_cache_rows"):
            self._session_cache_rows = []
        if self._session_cache_key == key:
            return self._session_cache_rows
        if self._session_cache_key is not None:
            self.remember_session_selection(self._session_cache_key[0], self._session_cache_rows)
        if not hasattr(self, "session_index"):
            self.session_index = -1
        if not hasattr(self, "session_scroll"):
            self.session_scroll = 0
        try:
            sessions = ai_session.recent_sessions(provider, profile, workdir, limit=60, ranking="strict")
        except Exception as exc:  # pragma: no cover - defensive TUI boundary
            self.message = f"session list failed: {exc}"
            sessions = []
        if getattr(self, "hide_empty_sessions", False):
            sessions = [s for s in sessions if s.get("turns", 0) > 0]
        rows = [self.new_session_row(), *[dict(session, _kind="session") for session in sessions]]
        self._session_cache_key = key
        self._session_cache_rows = rows
        self.restore_session_selection(rows, scope)
        return rows

    def new_session_row(self) -> dict[str, Any]:
        return {
            "_kind": "new",
            "provider": self.current_provider(),
            "profile": self.current_profile_label(),
            "workdir": self.effective_workdir_path(),
            "session_id": "",
            "native_session_ref": "",
            "updated": "",
            "title": "Start with current command settings",
            "last_prompt_summary": self.command_line(),
            "last_response_summary": "",
        }

    def session_row_segments(
        self,
        item: dict[str, Any],
        width: int,
        selected: bool = False,
        focused: bool = False,
        scope: str | None = None,
        specs: list[tuple[str, str, int]] | None = None,
    ) -> list[tuple[str, int]]:
        scope = scope or self.current_session_scope()
        marker = ">" if (selected and focused) else " "
        marker_attr = curses.A_BOLD if (selected and focused) else 0
        attr = self.selection_attr(focused) if selected else self.subdued_attr(focused)
        specs = specs or self.session_column_specs(scope, [item], width)
        segments: list[tuple[str, int]] = [(marker, marker_attr), (" ", 0)]
        for idx, (key, _label, col_width) in enumerate(specs):
            value = self.session_field_value(item, key, scope)
            if key == "profile" and not selected:
                h_limit = cell_width("Profile")
                if cell_width(value) > h_limit:
                    value = fit_cells(value, h_limit - 2) + ".."
            visible = fit_cells(value, col_width)
            segments.append((visible, attr))
            padding = col_width - cell_width(visible)
            if padding > 0:
                segments.append((" " * padding, 0))
            if idx + 1 < len(specs):
                segments.append(("  ", 0))
        return segments

    def session_rows(self) -> list[dict[str, Any]]:
        rows = self.current_sessions()
        self.session_index = max(-1, min(self.session_index, len(rows) - 1))
        return rows

    def selected_session(self) -> dict[str, Any] | None:
        sessions = self.session_rows()
        if not sessions or self.session_index < 0:
            return None
        return sessions[self.session_index]

    def run_selected_session(self) -> None:
        item = self.selected_session()
        if not item:
            self.message = "no selected session"
            return
        if not self.commit_workdir_text_if_present():
            return
        if item.get("_kind") == "new":
            if self.validate_builder_profile():
                self.confirm_exec_or_preview(self.run_command())
            return
        session_ref = str(item.get("native_session_ref") or item.get("session_id") or "")
        if not session_ref:
            self.message = "selected session has no id"
            return
        self.confirm_exec_or_preview(self.session_command(item))

    def execute_new_session(self) -> None:
        if not self.commit_workdir_text_if_present():
            return
        if not self.validate_builder_profile():
            return
        self.confirm_exec_or_preview(self.run_command())

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
        if not hasattr(self, "selection_active_attr"):
            self.selection_active_attr = curses.A_REVERSE | curses.A_BOLD
        if not hasattr(self, "selection_inactive_attr"):
            self.selection_inactive_attr = curses.A_REVERSE | curses.A_DIM
        if focused:
            return self.selection_active_attr
        return self.selection_inactive_attr

    def section_label_attr(self, active: bool) -> int:
        return curses.A_BOLD if active else curses.A_DIM

    def subdued_attr(self, active: bool) -> int:
        return 0 if active else curses.A_DIM

    def panel_title(self, label: str, active: bool) -> str:
        del active  # unused
        return "  " + label

    def workdir_child_focused(self) -> bool:
        return self.active_section() == "workdir" and getattr(self, "workdir_layer", "path") in {"path", "children"}

    def workdir_inline_focused(self) -> bool:
        return self.active_section() == "workdir" and getattr(self, "workdir_layer", "inline") == "inline"

    def add_segments(self, y: int, x: int, segments: list[tuple[str, int]], width: int) -> int:
        if not hasattr(self, "stdscr"):
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
        self.sync_terminal_title()
        command = self.command_line()
        if self.active_section() == "sessions":
            command = self.selected_session_command_line()
        self.add_line(1, 0, f" ⚡ COMMAND: {command}", width - 1, curses.A_BOLD | curses.A_REVERSE)
        if self.active_section() == "sessions":
            summary = self.selected_session_summary()
        else:
            summary = f" 📡 Provider: {self.current_provider().title()}   👤 Profile {self.current_profile()}: {self.current_profile()}   📁 Cwd: {short(self.effective_workdir_path())}"
        self.add_line(2, 0, summary, width - 1, curses.A_BOLD)

    def draw_choice_row(self, y: int, width: int, section: str, label: str, items: list[str], idx: int) -> None:
        active = self.active_section() == section
        marker = "> " if active else "  "
        label_width = 10
        prefix = f"{marker}{label:<{label_width}}  "
        self.add_line(y, 0, "", width - 1)
        self.add_text(y, 0, prefix, min(width - 1, len(prefix)), self.section_label_attr(active))

        start_x = len(prefix)
        remaining = max(0, width - start_x - 1)
        if not items or remaining <= 0:
            return

        gap = 3
        visible_start = max(0, min(idx, len(items) - 1))
        visible_end = visible_start + 1
        while True:
            trial_start = max(0, visible_start - 1)
            trial_end = min(len(items), visible_end + 1)
            trial_items = items[trial_start:trial_end]
            trial_width = sum(cell_width(item) for item in trial_items) + gap * max(0, len(trial_items) - 1)
            if trial_start > 0:
                trial_width += 4
            if trial_end < len(items):
                trial_width += 3
            if trial_width > remaining:
                break
            visible_start, visible_end = trial_start, trial_end
            if visible_start == 0 and visible_end == len(items):
                break
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
            if item_idx == idx:
                attr = self.selection_attr(active)
            else:
                attr = self.subdued_attr(active)
            self.add_text(y, x, item, item_width, attr)
            x += item_width
            if offset + 1 < len(visible_items) and x < width - 1:
                gap_attr = self.subdued_attr(active)
                self.add_text(y, x, " " * gap, min(gap, width - 1 - x), gap_attr)
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
        self.ensure_workdir_text()
        path = self.normalize_workdir_path(Path(self.current_workdir_path()))
        if getattr(self, "workdir_text", None) == "":
            return "", "", ""
        if getattr(self, "workdir_layer", "inline") == "children":
            text = short(str(path))
            if not text.endswith("/"):
                text += "/"
            return text, "", ""
        text = self.workdir_text or short(str(path))
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
            
            display_name = child.name
            if self.workdir_has_visible_children(child):
                display_name += "/"
                
            attr = self.selection_attr(True) if selected else curses.A_DIM
            self.add_text(y + n, x0 + 2, display_name, max(1, width - x0 - 3), attr)
        for n in range(len(visible), rows):
            self.add_line(y + n, x0, "", width - x0 - 1)
        return y + rows

    def draw_workdir_row(self, y: int, width: int) -> None:
        active = self.active_section() == "workdir"
        marker = "> " if active else "  "
        label_width = 10
        prefix = f"{marker}{'Workdir':<{label_width}}  "
        self.add_line(y, 0, "", width - 1)
        self.add_text(y, 0, prefix, min(width - 1, len(prefix)), self.section_label_attr(active))
        x = len(prefix)
        base_attr = curses.A_BOLD if active else 0
        if getattr(self, "workdir_layer", "inline") == "children":
            base_attr |= curses.A_DIM

        display_path, selected_segment, status = self.selected_workdir_path()
        right_hint = f" {status}"
        if self.workdir_inline_focused() and getattr(self, "workdir_editing", False) and getattr(self, "workdir_text", None) is not None:
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
        self.sync_profiles_for_current_provider(self.current_profile_label())
        child_rows = max(0, rows)
        active = self.active_section()
        
        # Add 1 line empty space and DIRECTORY panel title (ALL CAP)
        self.add_line(y, 0, "", width - 1)
        workdir_active = active == "workdir"
        self.add_line(y + 1, 0, self.panel_title("DIRECTORY", workdir_active), width - 1, self.section_label_attr(workdir_active))
        
        self.draw_workdir_row(y + 2, width)
        next_y = y + 3
        show_dropdown = active == "workdir" and (
            getattr(self, "workdir_layer", "path") == "children" or
            (getattr(self, "workdir_layer", "path") == "inline" and getattr(self, "workdir_editing", False))
        )
        if show_dropdown:
            next_y = self.draw_workdir_children(next_y, width, child_rows)
        self.add_line(next_y, 0, "", width - 1)
        next_y += 1

        command_active = active in COMMAND_SECTIONS
        self.add_line(next_y, 0, self.panel_title("COMMAND", command_active), width - 1, self.section_label_attr(command_active))
        session_idx = getattr(self, "indices", {}).get("session", 0)
        self.draw_choice_row(next_y + 1, width, "session", "Scope", SESSION_SCOPE_LABELS, session_idx)
        providers = getattr(self, "providers", []) or [self.current_provider()]
        self.draw_choice_row(next_y + 2, width, "provider", "Provider", [p.title() for p in providers], self.indices["provider"])
        profiles = getattr(self, "profiles", ["default"])
        self.draw_choice_row(next_y + 3, width, "profile", "Profile", profiles, self.indices["profile"])
        return next_y + 4

    def draw_sessions(self, y: int, width: int, rows: int) -> None:
        if rows <= 2:
            return
        sessions = self.session_rows()
        active = self.active_section() == "sessions"
        self.add_line(y, 0, self.panel_title(self.session_list_title(), active), width - 1, self.section_label_attr(active))
        if not sessions:
            self.list_meta["sessions"] = {
                "y": y + 1,
                "x": 0,
                "w": width,
                "rows": 0,
                "start": 0,
                "count": 0,
                "top": y,
                "height": 2,
            }
            self.add_line(y + 1, 0, "No summaries yet.", width - 1)
            for n in range(2, rows):
                self.add_line(y + n, 0, "", width - 1)
            return

        list_y = y + 1
        if self.is_dry_run():
            list_rows = 2 if rows <= 7 else max(3, min(10, rows - 9))
        else:
            list_rows = 3
            if rows <= 7:
                list_rows = max(1, rows - 5)
            elif rows > 12:
                list_rows = max(3, min(6, rows // 3))
        scope = self.current_session_scope()
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
        visible_sessions = sessions[self.session_scroll : self.session_scroll + list_rows]
        specs = self.session_column_specs(scope, visible_sessions, width)

        if hasattr(self, "stdscr"):
            self.add_segments(list_y, 0, self.session_header_segments(scope, visible_sessions, width), width - 1)
        else:
            self.add_line(list_y, 0, "  " + self.session_scope_columns(scope), width - 1, curses.A_DIM)
        list_y += 1

        for n in range(list_rows):
            item_idx = self.session_scroll + n
            if item_idx >= len(sessions):
                self.add_line(list_y + n, 0, "", width - 1)
                continue
            item = sessions[item_idx]
            selected_row = self.session_index >= 0 and item_idx == self.session_index
            if hasattr(self, "stdscr"):
                segments = self.session_row_segments(item, width, selected_row, active, scope, specs)
                self.add_segments(list_y + n, 0, segments, width - 1)
            else:
                row = self.session_row_text(item, width, selected_row, scope)
                self.add_line(list_y + n, 0, row, width - 1)

        preview_y = list_y + list_rows + 1
        self.add_line(preview_y - 1, 0, "", width - 1)
        if self.session_index < 0:
            self.add_line(preview_y, 0, "", width - 1)
            return
        selected = sessions[self.session_index]
        session_id = str(selected.get("session_id") or "")
        provider = str(selected.get("provider") or "-")
        profile = str(selected.get("profile") or "-")
        turns = str(selected.get("turns") or "0")
        updated_time = short_time(str(selected.get("updated") or ""))
        workdir_path = short(str(selected.get("workdir") or ""))

        preview_attr = self.section_label_attr(active)
        preview_text_attr = self.subdued_attr(active)
        self.add_line(preview_y, 0, self.panel_title("SESSION DETAILS", active), width - 1, preview_attr)
        
        if self.is_dry_run():
            self.add_line(preview_y + 1, 2, f"ID: {session_id or '-'}", width - 3, preview_text_attr)
            row = preview_y + 2
            preview_space = max(2, rows - list_rows - 4)
        else:
            meta_line1 = f"  Provider: {provider}  │  Profile: {profile}  │  Turns: {turns}  │  Updated: {updated_time}"
            self.add_line(preview_y + 1, 0, meta_line1, width - 1, preview_text_attr)
            meta_line2 = f"  Workdir: {workdir_path}  │  ID: {session_id}"
            self.add_line(preview_y + 2, 0, meta_line2, width - 1, preview_text_attr)
            self.add_line(preview_y + 3, 0, "", width - 1)
            row = preview_y + 4
            preview_space = max(2, rows - list_rows - 6)
        max_prompt = max(1, preview_space // 2)
        max_answer = max(1, preview_space - max_prompt)
        for line in self.wrap_lines("Prompt", str(selected.get("last_prompt_summary") or ""), width - 3, max_prompt):
            if row >= y + rows:
                return
            self.add_line(row, 2, line, width - 3, preview_text_attr)
            row += 1
        if not self.is_dry_run() and row < y + rows:
            self.add_line(row, 2, "", width - 3, preview_text_attr)
            row += 1
        for line in self.wrap_lines("Answer", str(selected.get("last_response_summary") or ""), width - 3, max_answer):
            if row >= y + rows:
                return
            self.add_line(row, 2, line, width - 3, preview_text_attr)
            row += 1

    def session_row_text(self, item: dict[str, Any], width: int, selected: bool = False, scope: str | None = None) -> str:
        segments = self.session_row_segments(item, width, selected, False, scope)
        return "".join(text for text, _attr in segments)

    def draw_main_background(self) -> None:
        self.stdscr.erase()
        if getattr(self, "delete_confirm_active", False):
            try:
                self.stdscr.bkgd(curses.color_pair(1))
            except (curses.error, AttributeError):
                pass
        elif getattr(self, "add_profile_active", False):
            try:
                self.stdscr.bkgd(curses.color_pair(2))
            except (curses.error, AttributeError):
                pass
        elif getattr(self, "help_popup_active", False):
            try:
                self.stdscr.bkgd(curses.color_pair(3))
            except (curses.error, AttributeError):
                pass
        elif getattr(self, "run_confirm_active", False):
            try:
                self.stdscr.bkgd(curses.color_pair(8))
            except (curses.error, AttributeError):
                pass
        else:
            try:
                self.stdscr.bkgd(curses.A_NORMAL)
            except (curses.error, AttributeError):
                pass
        self.list_meta = {}
        self.workdir_cursor = None
        h, w = self.stdscr.getmaxyx()
        if h < 14 or w < 52:
            self.add_line(0, 0, "ai tui: terminal is too small", max(1, w - 1), curses.A_BOLD)
            return

        if self.is_dry_run():
            self.add_line(0, 0, "─" * (w - 1), w - 1, curses.A_DIM)
            self.draw_header(w)
            available_after_builder = max(0, h - 4 - 4 - 3)
            child_rows = max(3, min(5, available_after_builder // 3))
            if available_after_builder - child_rows < 8:
                child_rows = max(0, available_after_builder - 8)
            self.add_line(3, 0, "─" * (w - 1), w - 1, curses.A_DIM)
            sessions_y = self.draw_controls(4, w, child_rows) + 1
            self.draw_sessions(sessions_y, w, max(0, h - sessions_y - 4))
            
            active_sec = self.active_section()
            self.add_line(h - 4, 0, "Navigation: Tab cycles Workdir/Command/Sessions", w - 1, curses.A_DIM)
            if active_sec == "profile":
                self.add_line(h - 3, 0, "Profile actions: Ctrl-A to add, Ctrl-D to delete", w - 1, curses.A_DIM)
            elif active_sec == "sessions":
                self.add_line(h - 3, 0, "Session actions: Enter to resume, Ctrl-T to toggle automated, Ctrl-D to delete", w - 1, curses.A_DIM)
            elif active_sec == "workdir":
                self.add_line(h - 3, 0, "Workdir actions: Ctrl-E or / edits cwd", w - 1, curses.A_DIM)
            else:
                self.add_line(h - 3, 0, "Actions: Enter to open sessions / confirm", w - 1, curses.A_DIM)
                
            self.add_line(h - 2, 0, "Controls: Esc back/confirm quit".rjust(w - 1), w - 1, curses.A_DIM)
            self.add_line(h - 1, 0, self.message, w - 1)
        else:
            self.add_line(0, 0, "─" * (w - 1), w - 1, curses.A_DIM)
            self.draw_header(w)
            available_after_builder = max(0, h - 4 - 4 - 3)
            child_rows = max(3, min(5, available_after_builder // 3))
            if available_after_builder - child_rows < 8:
                child_rows = max(0, available_after_builder - 8)
            self.add_line(3, 0, "─" * (w - 1), w - 1, curses.A_DIM)
            sessions_y = self.draw_controls(4, w, child_rows) + 1
            self.draw_sessions(sessions_y, w, max(0, h - sessions_y - 2))
            
            self.add_line(h - 2, 0, "", w - 1)
            self.add_line(h - 1, 0, "", w - 1)
            if self.message:
                padding = max(0, (w - 1) - cell_width(self.message))
                self.add_line(h - 2, 0, " " * padding + self.message, w - 1, curses.A_BOLD)
        self.update_cursor()

    def draw_main(self) -> None:
        self.draw_main_background()
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
        if self.workdir_inline_focused() and getattr(self, "workdir_editing", False) and self.workdir_cursor:
            y, x = self.workdir_cursor
            try:
                curses.curs_set(1)
                self.stdscr.move(y, x)
            except curses.error:
                pass
        else:
            self.hide_cursor()

    def draw(self) -> None:
        self.sync_terminal_title()
        if self.view == "manage":
            self.draw_manage()
        else:
            self.draw_main()

    def active_section(self) -> str:
        return SECTIONS[self.section]

    def enter_sessions(self) -> None:
        section = self.section_name()
        if section in COMMAND_SECTIONS:
            self.last_command_section = section
        self.last_builder_section = min(self.section, len(BUILDER_SECTIONS) - 1)
        self.section = SECTIONS.index("sessions")
        sessions = self.session_rows()
        self.restore_session_selection(sessions)
        if self.session_index < 0 and sessions:
            self.session_index = 0
        self.session_scroll = max(0, min(self.session_scroll, max(0, len(sessions) - 1)))

    def return_to_builder(self) -> None:
        self.section = max(0, min(self.last_builder_section, len(BUILDER_SECTIONS) - 1))

    def move_section(self, direction: int) -> None:
        section = self.active_section()
        if section == "sessions":
            self.return_to_builder()
            return
        if section == "workdir":
            if direction > 0:
                self.set_section(self.command_focus_section())
            return
        if section in COMMAND_SECTIONS:
            current = COMMAND_SECTIONS.index(section)
            target = (current + direction) % len(COMMAND_SECTIONS)
            self.set_section(COMMAND_SECTIONS[target])

    def toggle_panel(self) -> None:
        if self.active_section() == "sessions":
            self.return_to_builder()
            self.focus_workdir_path()
        else:
            self.enter_sessions()

    def next_section(self) -> None:
        section = self.active_section()
        if section == "sessions":
            return
        if section == "workdir":
            self.commit_focused_workdir()
            self.set_section(self.command_focus_section())
            return
        if section in COMMAND_SECTIONS:
            current = COMMAND_SECTIONS.index(section)
            self.set_section(COMMAND_SECTIONS[min(current + 1, len(COMMAND_SECTIONS) - 1)])

    def previous_section(self) -> None:
        section = self.active_section()
        if section == "workdir":
            return
        if section == "sessions":
            return
        if section in COMMAND_SECTIONS:
            current = COMMAND_SECTIONS.index(section)
            if current == 0:
                self.set_section("workdir")
            else:
                self.set_section(COMMAND_SECTIONS[current - 1])

    def vertical_action(self, direction: int) -> None:
        section = self.active_section()
        if section == "sessions":
            self.move_selection(direction)
        elif section == "workdir":
            if getattr(self, "workdir_layer", "path") == "children" or (getattr(self, "workdir_layer", "path") == "inline" and getattr(self, "workdir_editing", False)):
                self.cycle_workdir_child(direction)
            elif direction > 0:
                current = self.normalize_workdir_path(Path(self.current_workdir_path()))
                if not getattr(self, "workdir_override", False) and current == self.home_path():
                    self.open_workdir_dropdown(current)
                else:
                    self.open_workdir_dropdown(current.parent, current)
            else:
                self.move_section(direction)
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
        if section == "provider":
            self.remember_session_selection()
            self.remember_current_profile()
            providers = getattr(self, "providers", []) or [self.current_provider()]
            self.indices["provider"] = (self.indices["provider"] + direction) % len(providers)
            self.sync_profiles_for_current_provider()
            self.promote_session_scope("provider")
            self.invalidate_session_cache(reset=True)
        elif section == "profile":
            self.remember_session_selection()
            self.indices["profile"] = (self.indices["profile"] + direction) % len(self.profiles)
            self.remember_current_profile()
            self.promote_session_scope("profile")
            self.invalidate_session_cache(reset=True)
        elif section == "session":
            self.remember_session_selection()
            self.indices["session"] = (self.indices["session"] + direction) % len(SESSION_SCOPES)
            getattr(self, "session_extra_fields", set()).clear()
            self.invalidate_session_cache(reset=True)

    def horizontal_action(self, direction: int) -> None:
        section = self.active_section()
        if section in {"provider", "profile", "session"}:
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
        if is_text_key and ch == 5:
            return False
        self.ensure_workdir_text()
        self.workdir_layer = "inline"
        self.workdir_editing = True
        if is_edit_key:
            if ch in (curses.KEY_BACKSPACE, 127, 8):
                if self.workdir_text:
                    self.workdir_text = self.workdir_text[:-1]
            elif ch == 21:
                self.workdir_text = ""
        else:
            self.workdir_text += chr(ch)
        self.workdir_modified = True
        base, prefix = self.workdir_text_base_and_prefix()
        try:
            if base.is_dir():
                self.workdir_dropdown_base = str(base)
                children = self.filtered_workdir_children()
                if children:
                    self.workdir_child_index = 0
                else:
                    self.workdir_child_index = -1
        except Exception:
            pass
        self.message = ""
        return True

    def move_selection(self, direction: int) -> None:
        section = self.active_section()
        if section in {"provider", "profile", "session"}:
            self.change_option(section, direction)
        elif section == "workdir":
            self.vertical_action(direction)
        elif section == "sessions":
            sessions = self.session_rows()
            if sessions and self.session_index >= 0:
                self.remember_session_selection(sessions=sessions)
            current = self.session_index if self.session_index >= 0 else -1
            self.session_index = max(0, min(current + direction, len(sessions) - 1))

    def move_to_edge(self, end: bool) -> None:
        section = self.active_section()
        if section == "provider":
            self.remember_session_selection()
            self.remember_current_profile()
            self.indices["provider"] = len(self.providers) - 1 if end else 0
            self.sync_profiles_for_current_provider()
            self.promote_session_scope("provider")
            self.reset_sessions()
        elif section == "profile":
            self.remember_session_selection()
            self.indices["profile"] = len(self.profiles) - 1 if end else 0
            self.remember_current_profile()
            self.promote_session_scope("profile")
            self.reset_sessions()
        elif section == "workdir":
            self.workdir_layer = "inline"
            self.workdir_child_index = -1
        elif section == "sessions":
            sessions = self.session_rows()
            if sessions and self.session_index >= 0:
                self.remember_session_selection(sessions=sessions)
            if sessions:
                self.session_index = max(0, len(sessions) - 1) if end else 0

    def page_size(self) -> int:
        if self.active_section() == "workdir":
            return 5
        if self.active_section() in {"provider", "profile"}:
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
                    self.set_section(section)
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
        if section == "provider":
            self.remember_session_selection()
            self.remember_current_profile()
            self.indices["provider"] = item_idx
            self.sync_profiles_for_current_provider()
            self.promote_session_scope("provider")
            self.invalidate_session_cache(reset=True)
        elif section == "profile":
            self.remember_session_selection()
            self.indices["profile"] = item_idx
            self.remember_current_profile()
            self.promote_session_scope("profile")
            self.invalidate_session_cache(reset=True)
        elif section == "workdir":
            if self.custom_workdir:
                if item_idx == 0:
                    return
                item_idx -= 1
                self.custom_workdir = None
            self.indices["workdir"] = max(0, min(item_idx, len(self.workdirs) - 1))
            self.promote_session_scope("workdir")
            self.invalidate_session_cache(reset=True)
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
        if ch == ord('?'):
            if hasattr(self, "stdscr"):
                self.show_help_popup()
            return None
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
            elif self.active_section() == "workdir" and getattr(self, "workdir_layer", "path") == "children":
                self.focus_workdir_path()
                self.message = "workdir focus"
            else:
                self.pending_action = "quit"
                self.pending_cmd = None
                self.message = "Press Esc again to quit"
            return None
        if ch == 1 and self.active_section() == "profile":
            if hasattr(self, "stdscr"):
                self.add_profile()
            else:
                self.message = "add profile not supported here"
            return None
        if ch == 4:
            if self.active_section() == "profile":
                if hasattr(self, "stdscr"):
                    self.delete_profile()
                else:
                    self.message = "delete profile not supported here"
                return None
            elif self.active_section() == "sessions":
                self.delete_session()
                return None
        if ch == 20:
            self.toggle_empty_sessions()
            return None
        if self.active_section() == "workdir" and self.handle_workdir_text_key(ch):
            return None
        if ch == 5 and self.active_section() == "workdir":
            if hasattr(self, "stdscr"):
                self.edit_workdir()
            else:
                self.message = "press Ctrl-E to edit workdir"
            return None
        if ch == curses.KEY_RIGHT:
            self.horizontal_action(1)
        elif ch == curses.KEY_LEFT:
            self.horizontal_action(-1)
        elif ch == 9:
            self.handle_tab()
        elif ch in (curses.KEY_BTAB, 353):
            self.handle_shift_tab()
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
            self.handle_enter()
        return None

    def run(self) -> int:
        curses.curs_set(0)
        self.stdscr.keypad(True)
        self.init_colors()
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
                if self.view == "main" and self.handle_navigation_key(ch):
                    continue
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
