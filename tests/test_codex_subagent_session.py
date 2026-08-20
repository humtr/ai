#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ai_session  # noqa: E402


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rollout-2026-07-28T01-02-34-child-session.jsonl"
        rows = [
            {
                "timestamp": "2026-07-28T01:02:34Z",
                "type": "session_meta",
                "payload": {
                    "id": "child-session",
                    "session_id": "parent-session",
                    "cwd": "/work/child",
                    "thread_source": "subagent",
                },
            },
            {
                "timestamp": "2026-07-28T01:02:35Z",
                "type": "session_meta",
                "payload": {
                    "id": "parent-session",
                    "session_id": "parent-session",
                    "cwd": "/work/parent",
                    "thread_source": "user",
                },
            },
            {
                "timestamp": "2026-07-28T01:02:36Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "inspect the child task"},
            },
        ]
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        stat = path.stat()
        parsed = ai_session.parse_codex_session(
            {
                "provider": "codex",
                "profile": "work",
                "path": path,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
        )

    assert parsed["session_id"] == "child-session"
    assert parsed["native_session_ref"] == "child-session"
    assert parsed["workdir"] == "/work/child"


if __name__ == "__main__":
    main()
