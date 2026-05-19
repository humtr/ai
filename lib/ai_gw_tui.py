#!/usr/bin/env python3
"""Gateway/bridge control TUI for the ai wrapper."""

from __future__ import annotations

import curses
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import ai_store

# Keep Esc responsive while still allowing arrow-key escape sequences.
os.environ.setdefault("ESCDELAY", "50")

HOME = Path(os.environ.get("HOME", str(Path.home())))
AI_BIN = os.environ.get("AI_BIN", str(HOME / "bin" / "ai"))
SERVICE_ACTIONS = ["Status", "Start", "Stop", "Restart", "Logs"]


def fit(value: str, width: int) -> str:
    if width <= 0:
        return ""
    value = value.replace("\t", "  ")
    return value[:width].ljust(width)


def run_command(args: list[str]) -> tuple[int, str]:
    if os.environ.get("AI_TUI_DRY_RUN"):
        return 0, "dry-run: " + shlex.join(args)
    try:
        result = subprocess.run(args, text=True, capture_output=True, check=False)
    except OSError as exc:
        return 127, str(exc)
    text = (result.stdout or "") + (result.stderr or "")
    return result.returncode, text.strip()


def summarize_status(code: int, text: str) -> list[str]:
    if code != 0:
        return [f"Status command failed ({code})", *(text.splitlines()[:3] if text else [])]

    gateway_windows: list[str] = []
    gateway_profiles: list[str] = []
    bridge_tmux = "unknown"
    bridge_health = "unknown"
    bridge_url = ""
    section = ""

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("== ") and line.endswith(" =="):
            section = line.strip("= ").lower()
            continue
        if section == "tmux session" and line.startswith("hermes-gw:"):
            gateway_windows.append(line.split()[0].split(":", 1)[1])
            continue
        if section == "telegram gateway profiles" and line:
            gateway_profiles.append(line)
            continue
        if line.startswith("url:"):
            bridge_url = line.split(":", 1)[1].strip()
            continue
        if line.startswith("tmux:"):
            bridge_tmux = line.split(":", 1)[1].strip()
            continue
        if line.startswith("health:"):
            bridge_health = line.split(":", 1)[1].strip()
            continue

    wanted = gateway_profiles or gateway_windows
    running = sorted(set(gateway_windows))
    stopped = [name for name in wanted if name not in running]
    if wanted:
        gateway_status = f"{len(running)}/{len(wanted)} running"
        if stopped:
            gateway_status += " ; stopped: " + ", ".join(stopped)
    else:
        gateway_status = "none found"

    bridge_bits = [bridge_tmux]
    if bridge_health != "unknown":
        bridge_bits.append("health " + bridge_health)
    if bridge_url:
        bridge_bits.append(bridge_url)

    return [
        "Bridge: " + " ; ".join(bridge_bits),
        "Gateways: " + gateway_status,
        "Running: " + (", ".join(running) if running else "none"),
    ]


class GatewayApp:
    def __init__(self, stdscr: "curses._CursesWindow") -> None:
        self.stdscr = stdscr
        self.focus = "ops"
        self.op_index = 0
        self.service_index = 0
        self.action_index = 0
        self.message = ""
        self.output_lines: list[str] = []
        self.services: list[dict[str, str]] = []
        self.reload()
        self.refresh_status()

    def reload(self) -> None:
        gateways = ai_store.load_gateways().get("gateways", [])
        services = [
            {
                "id": "bridge",
                "name": "Bridge",
                "role": "OpenAI-compatible Gemini bridge",
                "profile": "",
                "bridge": "",
            }
        ]
        for item in gateways:
            if item.get("kind") != "telegram-gateway":
                continue
            services.append(
                {
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("id") or ""),
                    "role": "Telegram gateway",
                    "profile": str(item.get("hermes_profile") or ""),
                    "bridge": str(item.get("bridge") or ""),
                }
            )
        self.services = services
        self.service_index = max(0, min(self.service_index, len(self.services) - 1))
        self.action_index = max(0, min(self.action_index, len(SERVICE_ACTIONS) - 1))

    def operations(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "Start all",
                "summary": "Start bridge first, then all Telegram gateways",
                "commands": [[AI_BIN, "bridge", "start"], [AI_BIN, "gateway", "start", "all"]],
            },
            {
                "name": "Stop all",
                "summary": "Stop all Telegram gateways, then stop bridge",
                "commands": [[AI_BIN, "gateway", "stop", "all"], [AI_BIN, "bridge", "stop"]],
            },
            {
                "name": "Restart all",
                "summary": "Restart bridge, then restart all Telegram gateways",
                "commands": [[AI_BIN, "bridge", "restart"], [AI_BIN, "gateway", "restart", "all"]],
            },
            {
                "name": "Refresh status",
                "summary": "Reload the current bridge and gateway status",
                "commands": [[AI_BIN, "gateway", "status"]],
                "refresh_only": True,
            },
        ]

    def selected_service(self) -> dict[str, str]:
        return self.services[self.service_index]

    def service_command(self, service: dict[str, str], action: str) -> list[str]:
        sid = service["id"]
        lower = action.lower()
        if sid == "bridge":
            if lower == "logs":
                return [AI_BIN, "bridge", "logs"]
            return [AI_BIN, "bridge", lower]
        if lower == "logs":
            return [AI_BIN, "gateway", "logs", sid]
        if lower == "status":
            return [AI_BIN, "gateway", "show", sid]
        return [AI_BIN, "gateway", lower, sid]

    def current_commands(self) -> list[list[str]]:
        if self.focus == "ops":
            return list(self.operations()[self.op_index]["commands"])
        return [self.service_command(self.selected_service(), SERVICE_ACTIONS[self.action_index])]

    def refresh_status(self) -> None:
        code, text = run_command([AI_BIN, "gateway", "status"])
        if os.environ.get("AI_TUI_DRY_RUN"):
            self.output_lines = [
                "Bridge: dry-run",
                "Gateways: dry-run",
                text,
            ]
            return
        self.output_lines = summarize_status(code, text)

    def add_line(self, y: int, x: int, text: str, width: int, attr: int = 0) -> None:
        try:
            self.stdscr.addnstr(y, x, fit(text, width), width, attr)
        except curses.error:
            pass

    def draw_status(self, y: int, height: int, width: int) -> None:
        self.add_line(y, 0, "Current status", width, curses.A_BOLD)
        for idx, line in enumerate(self.output_lines[: max(0, height - 1)]):
            self.add_line(y + 1 + idx, 0, line, width)

    def draw_ops(self, y: int, height: int, width: int) -> None:
        self.add_line(y, 0, "Operations", width, curses.A_BOLD)
        for idx, op in enumerate(self.operations()[: max(0, height - 1)]):
            marker = "> " if idx == self.op_index else "  "
            text = f"{marker}{op['name']:<14} {op['summary']}"
            attr = curses.A_REVERSE if self.focus == "ops" and idx == self.op_index else 0
            self.add_line(y + 1 + idx, 0, text, width, attr)

    def draw_services(self, y: int, height: int, width: int) -> None:
        self.add_line(y, 0, "Services", width, curses.A_BOLD if self.focus == "services" else 0)
        header = f"{'Name':<14} {'Role':<34} {'Profile':<14} {'Bridge':<14}"
        self.add_line(y + 1, 0, header, width, curses.A_DIM)
        max_rows = max(0, height - 2)
        start = max(0, min(self.service_index, max(0, len(self.services) - max_rows)))
        for offset, service in enumerate(self.services[start : start + max_rows]):
            idx = start + offset
            marker = "> " if idx == self.service_index else "  "
            text = (
                f"{marker}{service['name']:<12} "
                f"{service['role']:<34} "
                f"{service['profile']:<14} "
                f"{service['bridge']:<14}"
            )
            attr = curses.A_REVERSE if self.focus == "services" and idx == self.service_index else 0
            self.add_line(y + 2 + offset, 0, text, width, attr)

    def draw_actions(self, y: int, width: int) -> None:
        title = "Service action"
        self.add_line(y, 0, title, width, curses.A_BOLD if self.focus == "actions" else 0)
        x = 0
        for idx, action in enumerate(SERVICE_ACTIONS):
            label = f" {action} "
            attr = curses.A_REVERSE if self.focus == "actions" and idx == self.action_index else 0
            self.add_line(y + 1, x, label, len(label), attr)
            x += len(label) + 1

    def draw(self) -> None:
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()
        if h < 16 or w < 60:
            self.add_line(0, 0, "ai gw: terminal is too small", max(1, w - 1), curses.A_BOLD)
            self.stdscr.refresh()
            return
        width = w - 1
        self.add_line(0, 0, " ai gw", width, curses.A_BOLD | curses.A_REVERSE)
        status_h = max(3, min(4, h // 6))
        self.draw_status(2, status_h, width)
        actions_y = h - 5
        services_y = status_h + 3
        ops_h = 5
        ops_y = max(services_y + 3, actions_y - ops_h - 1)
        self.draw_services(services_y, max(1, ops_y - services_y - 1), width)
        self.draw_ops(ops_y, ops_h, width)
        self.draw_actions(actions_y, width)
        command_text = " ; ".join(shlex.join(cmd) for cmd in self.current_commands())
        self.add_line(actions_y + 2, 0, "Enter runs: " + command_text, width, curses.A_DIM)
        self.add_line(h - 2, 0, "Up/Down select | Left/Right/Tab panel | Enter run | Esc quit", width, curses.A_DIM)
        self.add_line(h - 1, 0, self.message, width)
        self.stdscr.refresh()

    def execute_commands(self, commands: list[list[str]]) -> None:
        lines: list[str] = []
        failed = False
        for cmd in commands:
            code, text = run_command(cmd)
            lines.append(f"$ {shlex.join(cmd)}")
            lines.append(f"exit {code}")
            if text:
                lines.extend(text.splitlines())
            if code != 0:
                failed = True
                break
        self.message = ("failed: " if failed else "done: ") + " ; ".join(shlex.join(c) for c in commands)
        self.output_lines = lines or ["done"]
        if not failed:
            self.refresh_status()
        self.reload()

    def move_panel(self, direction: int) -> None:
        order = ["ops", "services", "actions"]
        idx = order.index(self.focus)
        self.focus = order[(idx + direction) % len(order)]

    def handle_key(self, ch: int) -> int | None:
        if ch in (3, 27):
            return 130 if ch == 3 else 0
        if ch == 9:
            self.move_panel(1)
        elif ch == curses.KEY_RIGHT:
            self.move_panel(1)
        elif ch == curses.KEY_LEFT:
            self.move_panel(-1)
        elif ch == curses.KEY_DOWN:
            if self.focus == "ops":
                self.op_index = min(len(self.operations()) - 1, self.op_index + 1)
            elif self.focus == "services":
                self.service_index = min(len(self.services) - 1, self.service_index + 1)
            else:
                self.action_index = (self.action_index + 1) % len(SERVICE_ACTIONS)
        elif ch == curses.KEY_UP:
            if self.focus == "ops":
                self.op_index = max(0, self.op_index - 1)
            elif self.focus == "services":
                self.service_index = max(0, self.service_index - 1)
            else:
                self.action_index = (self.action_index - 1) % len(SERVICE_ACTIONS)
        elif ch in (10, 13, getattr(curses, "KEY_ENTER", 343)):
            if self.focus == "ops" and self.operations()[self.op_index].get("refresh_only"):
                self.refresh_status()
                self.message = "refreshed status"
            else:
                self.execute_commands(self.current_commands())
        return None

    def run(self) -> int:
        curses.curs_set(0)
        self.stdscr.keypad(True)
        while True:
            self.draw()
            try:
                result = self.handle_key(self.stdscr.getch())
            except KeyboardInterrupt:
                return 130
            if result is not None:
                return result


def main() -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("ai gw requires a TTY", file=sys.stderr)
        return 2
    try:
        return curses.wrapper(lambda stdscr: GatewayApp(stdscr).run())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
