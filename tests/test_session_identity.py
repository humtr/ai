#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ai_session  # noqa: E402


REF = "01a0d397-6db5-7971-b7d3-38916bf020c4"


def _row(profile: str, path: Path, *, ref: str = REF, mtime: float = 1.0, turns: int = 1) -> dict[str, object]:
    return {
        "provider": "codex",
        "profile": profile,
        "path": str(path),
        "source_path": str(path),
        "workdir": "/work/tdev",
        "session_id": ref,
        "native_session_ref": ref,
        "mtime": mtime,
        "turns": turns,
        "size": 100,
        "title": f"{profile} copy",
        "last_prompt_summary": "prompt",
    }


def test_regular_profile_copies_are_one_logical_session() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        default_path = root / ".codex" / "sessions" / "rollout.jsonl"
        profile_path = root / ".codex-profiles" / "jgnh" / "sessions" / "rollout.jsonl"
        default_path.parent.mkdir(parents=True)
        profile_path.parent.mkdir(parents=True)
        default_path.write_text("{}\n", encoding="utf-8")
        profile_path.write_text("{}\n", encoding="utf-8")

        rows = [
            _row("default", default_path, mtime=10, turns=37),
            _row("jgnh", profile_path, mtime=20, turns=39),
        ]
        deduped = ai_session.dedupe_session_rows(rows)

    assert len(deduped) == 1
    assert deduped[0]["profile"] == "jgnh"
    assert ai_session.logical_session_identity(rows[0]) == ai_session.logical_session_identity(rows[1])


def test_exact_profile_filter_still_selects_that_profile() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        default_row = _row("default", root / "default.jsonl", mtime=10)
        jgnh_row = _row("jgnh", root / "jgnh.jsonl", mtime=20)
        original_fresh = ai_session.fresh_session_index
        original_refresh = ai_session.refresh_session_index
        try:
            data = {"sessions": [default_row, jgnh_row]}
            ai_session.fresh_session_index = lambda: data
            ai_session.refresh_session_index = lambda limit=0: data

            exact = ai_session.resolve_session(REF, provider="codex", profile="default")
            fallback = ai_session.resolve_session(REF, provider="codex", profile=None)
        finally:
            ai_session.fresh_session_index = original_fresh
            ai_session.refresh_session_index = original_refresh

    assert exact is not None and not exact.get("ambiguous")
    assert exact["profile"] == "default"
    assert fallback is not None and not fallback.get("ambiguous")
    assert fallback["profile"] == "jgnh"


def test_different_native_refs_remain_distinct() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rows = [
            _row("default", root / "one.jsonl", ref="session-one"),
            _row("jgnh", root / "two.jsonl", ref="session-two"),
        ]
        assert len(ai_session.dedupe_session_rows(rows)) == 2


def main() -> None:
    test_regular_profile_copies_are_one_logical_session()
    test_exact_profile_filter_still_selects_that_profile()
    test_different_native_refs_remain_distinct()


if __name__ == "__main__":
    main()
