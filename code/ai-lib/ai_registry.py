#!/usr/bin/env python3
"""Small registry helper for the ai wrapper.

This module intentionally uses only the Python standard library so it can run
inside Termux without extra packages.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", str(Path.home())))
AI_HOME = Path(os.environ.get("AI_HOME", str(HOME / ".ai")))
WORKDIRS_FILE = AI_HOME / "workdirs.json"
GATEWAYS_FILE = AI_HOME / "gateways.json"
SESSION_INDEX_DIR = AI_HOME / "session-index"
SESSION_INDEX_FILE = SESSION_INDEX_DIR / "sessions.json"
SESSION_INDEX_VERSION = 6
SESSION_SCAN_LIMIT = int(os.environ.get("AI_SESSION_SCAN_LIMIT", "500"))


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def compact_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()
    if isinstance(value, list):
        parts = [compact_text(item) for item in value]
        return compact_text(" ".join(p for p in parts if p))
    if isinstance(value, dict):
        for key in ("text", "content", "message", "value"):
            if key in value:
                text = compact_text(value.get(key))
                if text:
                    return text
        return ""
    return compact_text(str(value))


def text_summary(value: Any, limit: int = 260) -> str:
    text = compact_text(value)
    strip_prefixes = (
        '도구 사용 가능 작업 모드다. 단, 실제로 제공된 도구만 사용하고, 존재하지 않는 도구명이나 API를 만들지 마라. 도구가 필요 없는 요청이면 도구를 사용하지 말고 바로 답하라. 사용자가 "정확히", "토큰만", "한 문장만" 같은 출력 제약을 주면 그 출력 제약을 최우선으로 지켜라.',
        "도구, 검색, 파일 탐색, 파일 읽기, 파일 쓰기, 셸 실행을 사용하지 말고 네 지식만으로 답해. 내부 계획이나 검색 결과 설명을 쓰지 말고, 사용자가 요구한 답만 작성해.",
        "실행, 수정, 파일 쓰기, 셸 명령 실행은 하지 말고 읽기/분석 중심으로 계획만 세워. 필요한 경우 가정과 위험을 명확히 구분해.",
    )
    for prefix in strip_prefixes:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    skip_prefixes = (
        "<environment_context>",
        "The following is the Codex agent history whose request action you are assessing.",
        "The following is the Codex agent history added since your last approval assessment.",
        "You are an automated command approval reviewer.",
        "You are an automated command approval reviewer",
        '{"outcome":',
        '{"risk_level":',
    )
    if any(text.startswith(prefix) for prefix in skip_prefixes):
        return ""
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip() + "..."


def iso_from_mtime(path: Path) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(path.stat().st_mtime))


def safe_stat(path: Path) -> os.stat_result | None:
    try:
        return path.stat()
    except OSError:
        return None


def read_project_root(path: Path) -> str:
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return str(Path(value).expanduser()) if value else ""


def existing_provider_profiles(provider: str) -> list[str]:
    if provider == "codex":
        root = HOME / ".codex-profiles"
    elif provider == "gemini":
        root = HOME / ".gemini-profiles"
    elif provider == "hermes":
        root = HOME / ".hermes" / "profiles"
    else:
        return []
    if not root.is_dir():
        return []
    reserved = {"default", "native"}
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in reserved
    )


def default_workdirs() -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    work_root = HOME / "work"
    if work_root.is_dir():
        for path in sorted(work_root.iterdir()):
            if path.is_dir():
                items.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "purpose": "",
                        "favorite": path.name in {"main", "test"},
                        "archived": False,
                    }
                )
    return {"version": 1, "workdirs": items}


def default_gateways() -> dict[str, Any]:
    return {
        "version": 1,
        "gateways": [
            {
                "id": "codex-tg",
                "kind": "telegram-gateway",
                "hermes_profile": "codex-tg",
                "bridge": None,
                "hidden": False,
            },
            {
                "id": "gemini-tg",
                "kind": "telegram-gateway",
                "hermes_profile": "gemini-tg",
                "bridge": "gemini-bridge",
                "hidden": False,
            },
            {
                "id": "gemini-bridge",
                "kind": "openai-compatible-bridge",
                "command": "hgb",
                "hidden": False,
            },
        ],
    }


def ensure_registry() -> None:
    if not WORKDIRS_FILE.exists():
        write_json(WORKDIRS_FILE, default_workdirs())
    if not GATEWAYS_FILE.exists():
        write_json(GATEWAYS_FILE, default_gateways())


def load_workdirs() -> dict[str, Any]:
    ensure_registry()
    data = read_json(WORKDIRS_FILE, default_workdirs())
    data.setdefault("version", 1)
    data.setdefault("workdirs", [])
    return data


def save_workdirs(data: dict[str, Any]) -> None:
    write_json(WORKDIRS_FILE, data)


def load_gateways() -> dict[str, Any]:
    ensure_registry()
    data = read_json(GATEWAYS_FILE, default_gateways())
    data.setdefault("version", 1)
    data.setdefault("gateways", [])
    return data


def load_session_index() -> dict[str, Any]:
    data = read_json(SESSION_INDEX_FILE, {"version": SESSION_INDEX_VERSION, "sessions": []})
    data.setdefault("version", SESSION_INDEX_VERSION)
    data.setdefault("sessions", [])
    return data


def save_session_index(data: dict[str, Any]) -> None:
    write_json(SESSION_INDEX_FILE, data)


def codex_session_id(path: Path) -> str:
    stem = path.stem
    return re.sub(r"^rollout-[0-9TZ:-]+-", "", stem) or stem


def hermes_session_id(path: Path) -> str:
    stem = path.stem
    if stem.startswith("session_"):
        return stem[len("session_") :]
    return stem


def gemini_project_root(path: Path) -> str:
    for parent in path.parents:
        if parent.name == "chats":
            project_root = parent.parent / ".project_root"
            if project_root.exists():
                return read_project_root(project_root)
            break
    return ""


def add_session_record(
    records: list[dict[str, Any]],
    provider: str,
    profile: str,
    path: Path,
    workdir_hint: str = "",
) -> None:
    stat = safe_stat(path)
    if stat is None or not path.is_file():
        return
    records.append(
        {
            "provider": provider,
            "profile": profile,
            "path": path,
            "workdir_hint": workdir_hint,
            "mtime": stat.st_mtime,
            "size": stat.st_size,
        }
    )


def discover_session_files(limit: int = SESSION_SCAN_LIMIT) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    codex_sessions = HOME / ".codex" / "sessions"
    if codex_sessions.is_dir():
        for path in codex_sessions.rglob("*.jsonl"):
            add_session_record(records, "codex", "default", path)

    codex_homes = HOME / ".codex-profiles"
    if codex_homes.is_dir():
        for profile_home in sorted(p for p in codex_homes.iterdir() if p.is_dir()):
            sessions = profile_home / "sessions"
            if sessions.is_dir():
                for path in sessions.rglob("*.jsonl"):
                    add_session_record(records, "codex", profile_home.name, path)

    def scan_gemini_home(root: Path, profile: str) -> None:
        tmp = root / "tmp"
        if not tmp.is_dir():
            return
        for project_dir in sorted(p for p in tmp.iterdir() if p.is_dir()):
            chats = project_dir / "chats"
            if not chats.is_dir():
                continue
            workdir = read_project_root(project_dir / ".project_root")
            for path in chats.rglob("*.jsonl"):
                add_session_record(records, "gemini", profile, path, workdir)

    scan_gemini_home(HOME / ".gemini", "default")
    gemini_homes = HOME / ".gemini-profiles"
    if gemini_homes.is_dir():
        for profile_home in sorted(p for p in gemini_homes.iterdir() if p.is_dir()):
            scan_gemini_home(profile_home, profile_home.name)

    hermes_sessions = HOME / ".hermes" / "sessions"
    if hermes_sessions.is_dir():
        for path in hermes_sessions.iterdir():
            if path.suffix in {".json", ".jsonl"} and path.name != "sessions.json":
                add_session_record(records, "hermes", "default", path)

    hermes_profiles = HOME / ".hermes" / "profiles"
    if hermes_profiles.is_dir():
        for profile_home in sorted(p for p in hermes_profiles.iterdir() if p.is_dir()):
            sessions = profile_home / "sessions"
            if not sessions.is_dir():
                continue
            for path in sessions.iterdir():
                if path.name == "sessions.json" or path.name.startswith("request_dump_"):
                    continue
                if path.suffix in {".json", ".jsonl"}:
                    add_session_record(records, "hermes", profile_home.name, path)

    records.sort(key=lambda item: float(item.get("mtime") or 0), reverse=True)
    return records[:limit]


def add_message(messages: list[dict[str, str]], role: str, content: Any, timestamp: str = "") -> None:
    if role not in {"user", "assistant"}:
        return
    text = text_summary(content)
    if text:
        messages.append({"role": role, "text": text, "timestamp": timestamp})


def entry_from_messages(record: dict[str, Any], meta: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    path = Path(record["path"])
    users = [m for m in messages if m.get("role") == "user"]
    assistants = [m for m in messages if m.get("role") == "assistant"]
    last_msg = messages[-1] if messages else {}
    session_id = str(meta.get("session_id") or path.stem)
    last_user = users[-1].get("text", "") if users else ""
    last_assistant = assistants[-1].get("text", "") if assistants else ""
    title = users[0].get("text", "") if users else last_user or session_id
    workdir = str(meta.get("workdir") or record.get("workdir_hint") or "")
    updated = str(meta.get("updated") or last_msg.get("timestamp") or iso_from_mtime(path))
    return {
        "provider": record["provider"],
        "profile": record["profile"],
        "session_id": session_id,
        "title": text_summary(title, 120) or session_id,
        "last_prompt_summary": text_summary(last_user, 360),
        "last_response_summary": text_summary(last_assistant, 360),
        "updated": updated,
        "workdir": workdir,
        "path": str(path),
        "mtime": record["mtime"],
        "size": record["size"],
    }


def parse_codex_session(record: dict[str, Any]) -> dict[str, Any]:
    path = Path(record["path"])
    meta = {"session_id": codex_session_id(path), "workdir": "", "updated": ""}
    messages: list[dict[str, str]] = []
    fallback: list[dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                timestamp = str(item.get("timestamp") or payload.get("timestamp") or "")
                if timestamp:
                    meta["updated"] = timestamp
                if item.get("type") == "session_meta":
                    meta["session_id"] = str(payload.get("id") or meta["session_id"])
                    meta["workdir"] = str(payload.get("cwd") or meta["workdir"])
                    continue
                if item.get("type") == "response_item" and payload.get("type") == "message":
                    add_message(messages, str(payload.get("role") or ""), payload.get("content"), timestamp)
                    continue
                if item.get("type") == "event_msg":
                    event_type = payload.get("type")
                    if event_type == "user_message":
                        add_message(fallback, "user", payload.get("message"), timestamp)
                    elif event_type == "agent_message":
                        add_message(fallback, "assistant", payload.get("message"), timestamp)
    except OSError:
        pass
    return entry_from_messages(record, meta, messages or fallback)


def parse_gemini_session(record: dict[str, Any]) -> dict[str, Any]:
    path = Path(record["path"])
    meta = {"session_id": path.stem, "workdir": record.get("workdir_hint") or gemini_project_root(path), "updated": ""}
    messages: list[dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if line_no == 0:
                    meta["session_id"] = str(item.get("sessionId") or meta["session_id"])
                    meta["updated"] = str(item.get("lastUpdated") or item.get("startTime") or meta["updated"])
                    continue
                timestamp = str(item.get("timestamp") or "")
                if timestamp:
                    meta["updated"] = timestamp
                kind = item.get("type")
                if kind == "user":
                    add_message(messages, "user", item.get("content"), timestamp)
                elif kind in {"gemini", "assistant", "model"}:
                    add_message(messages, "assistant", item.get("content"), timestamp)
    except OSError:
        pass
    return entry_from_messages(record, meta, messages)


def parse_hermes_session(record: dict[str, Any]) -> dict[str, Any]:
    path = Path(record["path"])
    meta = {"session_id": hermes_session_id(path), "workdir": "", "updated": ""}
    messages: list[dict[str, str]] = []
    try:
        if path.suffix == ".jsonl":
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    timestamp = str(item.get("timestamp") or "")
                    if timestamp:
                        meta["updated"] = timestamp
                    role = str(item.get("role") or "")
                    if role == "session_meta":
                        meta["session_id"] = str(item.get("session_id") or meta["session_id"])
                        continue
                    add_message(messages, role, item.get("content"), timestamp)
        else:
            item = read_json(path, {})
            meta["session_id"] = str(item.get("session_id") or meta["session_id"])
            meta["updated"] = str(item.get("last_updated") or item.get("session_start") or "")
            meta["workdir"] = str(item.get("cwd") or item.get("workdir") or item.get("working_directory") or "")
            for message in item.get("messages") or []:
                add_message(messages, str(message.get("role") or ""), message.get("content"))
    except OSError:
        pass
    return entry_from_messages(record, meta, messages)


def parse_session_record(record: dict[str, Any]) -> dict[str, Any]:
    provider = record.get("provider")
    if provider == "codex":
        return parse_codex_session(record)
    if provider == "gemini":
        return parse_gemini_session(record)
    if provider == "hermes":
        return parse_hermes_session(record)
    return entry_from_messages(record, {"session_id": Path(record["path"]).stem}, [])


def refresh_session_index(limit: int = SESSION_SCAN_LIMIT) -> dict[str, Any]:
    existing = load_session_index()
    can_reuse = existing.get("version") == SESSION_INDEX_VERSION
    existing_by_path = {str(item.get("path")): item for item in existing.get("sessions", [])}
    entries: list[dict[str, Any]] = []
    for record in discover_session_files(limit):
        path_key = str(record["path"])
        old = existing_by_path.get(path_key)
        if (
            can_reuse
            and old
            and old.get("mtime") == record.get("mtime")
            and old.get("size") == record.get("size")
        ):
            entries.append(old)
        else:
            entries.append(parse_session_record(record))
    entries.sort(key=lambda item: float(item.get("mtime") or 0), reverse=True)
    data = {
        "version": SESSION_INDEX_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime()),
        "sessions": entries,
    }
    save_session_index(data)
    return data


def normalize_workdir(path: str | None) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).expanduser().resolve())
    except OSError:
        return str(Path(path).expanduser())


def recent_sessions(
    provider: str | None = None,
    profile: str | None = None,
    workdir: str | None = None,
    limit: int = 6,
) -> list[dict[str, Any]]:
    data = load_session_index()
    target_workdir = normalize_workdir(workdir)
    ranked: list[tuple[int, float, dict[str, Any]]] = []
    for item in data.get("sessions", []):
        if provider and item.get("provider") != provider:
            continue
        if not item.get("last_prompt_summary") and not item.get("last_response_summary"):
            continue
        score = 0
        if profile and item.get("profile") == profile:
            score += 4
        if target_workdir and normalize_workdir(str(item.get("workdir") or "")) == target_workdir:
            score += 2
        ranked.append((score, float(item.get("mtime") or 0), item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _, _, item in ranked[:limit]]


def cmd_ensure(_: argparse.Namespace) -> int:
    ensure_registry()
    return 0


def cmd_workdirs_list(args: argparse.Namespace) -> int:
    data = load_workdirs()
    for item in data["workdirs"]:
        if item.get("archived") and not args.all:
            continue
        print(
            "\t".join(
                [
                    str(item.get("name", "")),
                    str(item.get("path", "")),
                    str(item.get("purpose", "")),
                    "archived" if item.get("archived") else "active",
                ]
            )
        )
    return 0


def cmd_workdirs_add(args: argparse.Namespace) -> int:
    data = load_workdirs()
    path = Path(args.path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    for item in data["workdirs"]:
        if item.get("name") == args.name:
            print(f"ERROR: workdir already exists: {args.name}", file=sys.stderr)
            return 2
    if args.create:
        path.mkdir(parents=True, exist_ok=True)
    data["workdirs"].append(
        {
            "name": args.name,
            "path": str(path),
            "purpose": args.purpose or "",
            "favorite": bool(args.favorite),
            "archived": False,
        }
    )
    save_workdirs(data)
    print(f"added workdir: {args.name} -> {path}")
    return 0


def cmd_workdirs_archive(args: argparse.Namespace) -> int:
    data = load_workdirs()
    for item in data["workdirs"]:
        if item.get("name") == args.name:
            item["archived"] = True
            save_workdirs(data)
            print(f"archived workdir: {args.name}")
            return 0
    print(f"ERROR: workdir not found: {args.name}", file=sys.stderr)
    return 2


def cmd_profiles_list(args: argparse.Namespace) -> int:
    providers = [args.provider] if args.provider else ["codex", "gemini", "hermes"]
    for provider in providers:
        print(f"== {provider} ==")
        print("default\tofficial-home")
        for profile in existing_provider_profiles(provider):
            print(f"{profile}\tmanaged")
    return 0


def cmd_gateways_list(_: argparse.Namespace) -> int:
    data = load_gateways()
    for item in data["gateways"]:
        print(
            "\t".join(
                [
                    str(item.get("id", "")),
                    str(item.get("kind", "")),
                    str(item.get("hermes_profile") or ""),
                    str(item.get("bridge") or ""),
                ]
            )
        )
    return 0


def cmd_sessions_refresh(args: argparse.Namespace) -> int:
    data = refresh_session_index(args.limit)
    print(f"indexed sessions: {len(data.get('sessions', []))}")
    print(str(SESSION_INDEX_FILE))
    return 0


def cmd_sessions_list(args: argparse.Namespace) -> int:
    if args.refresh:
        refresh_session_index(args.limit)
    sessions = recent_sessions(args.provider, args.profile, args.cwd, args.limit)
    for item in sessions:
        print(
            "\t".join(
                [
                    str(item.get("provider", "")),
                    str(item.get("profile", "")),
                    str(item.get("updated", "")),
                    str(item.get("session_id", "")),
                    str(item.get("title", "")),
                ]
            )
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ai_registry")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ensure")
    s.set_defaults(fn=cmd_ensure)

    s = sub.add_parser("workdirs-list")
    s.add_argument("--all", action="store_true")
    s.set_defaults(fn=cmd_workdirs_list)

    s = sub.add_parser("workdirs-add")
    s.add_argument("name")
    s.add_argument("path")
    s.add_argument("--purpose")
    s.add_argument("--favorite", action="store_true")
    s.add_argument("--create", action="store_true")
    s.set_defaults(fn=cmd_workdirs_add)

    s = sub.add_parser("workdirs-archive")
    s.add_argument("name")
    s.set_defaults(fn=cmd_workdirs_archive)

    s = sub.add_parser("profiles-list")
    s.add_argument("provider", nargs="?", choices=["codex", "gemini", "hermes"])
    s.set_defaults(fn=cmd_profiles_list)

    s = sub.add_parser("gateways-list")
    s.set_defaults(fn=cmd_gateways_list)

    s = sub.add_parser("sessions-refresh")
    s.add_argument("--limit", type=int, default=SESSION_SCAN_LIMIT)
    s.set_defaults(fn=cmd_sessions_refresh)

    s = sub.add_parser("sessions-list")
    s.add_argument("--provider", choices=["codex", "gemini", "hermes"])
    s.add_argument("--profile")
    s.add_argument("--cwd")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--refresh", action="store_true")
    s.set_defaults(fn=cmd_sessions_list)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
