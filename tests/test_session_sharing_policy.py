#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ai_plan  # noqa: E402
import ai_session  # noqa: E402
import ai_tui  # noqa: E402


def _session(provider: str, profile: str, path: Path, ref: str = "shared-ref") -> dict[str, str]:
    return {
        "_kind": "session",
        "provider": provider,
        "profile": profile,
        "path": str(path),
        "workdir": "",
        "session_id": ref,
        "native_session_ref": ref,
    }


def _restore_env(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


def _tui_app(provider_index: int, profile: str, rows: list[dict[str, str]]) -> ai_tui.App:
    app = ai_tui.App.__new__(ai_tui.App)
    app.providers = ["codex", "agy"]
    app.profiles = [profile]
    app.indices = {"provider": provider_index, "profile": 0, "session": 0, "workdir": 0}
    app.section = ai_tui.SECTIONS.index("sessions")
    app.session_index = 1
    app.session_scroll = 0
    app.message = ""
    app.current_sessions = lambda: rows
    return app


def test_same_provider_profile_share_is_default() -> None:
    previous_home = os.environ.get("HOME")
    original_resolve = ai_session.resolve_session
    try:
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["HOME"] = tmp
            root = Path(tmp)
            source_profile = root / ".codex-profiles" / "source"
            target_profile = root / ".codex-profiles" / "target"
            source_path = source_profile / "sessions" / "shared.jsonl"
            source_path.parent.mkdir(parents=True)
            source_path.write_text("{}\n", encoding="utf-8")
            (source_profile / "auth.json").write_text(
                '{"auth_mode":"apikey","OPENAI_API_KEY":"source"}\n',
                encoding="utf-8",
            )
            target_auth = target_profile / "auth.json"
            target_auth.parent.mkdir(parents=True)
            target_auth.write_text(
                '{"auth_mode":"apikey","OPENAI_API_KEY":"target"}\n',
                encoding="utf-8",
            )
            row = _session("codex", "source", source_path)

            ai_session.resolve_session = lambda *args, **kwargs: row
            plan = ai_plan.build_execution_plan(
                ai_plan.LaunchSpec(
                    command="run",
                    provider="codex",
                    profile="target",
                    directory=tmp,
                    session_ref="shared-ref",
                )
            )

            assert plan.argv == ["codex", "resume", "shared-ref"]
            assert plan.env["CODEX_HOME"] == str(target_profile)
            assert target_auth.is_file()
    finally:
        ai_session.resolve_session = original_resolve
        _restore_env("HOME", previous_home)


def test_tui_blocks_cross_provider_and_keeps_same_provider_profiles_runnable() -> None:
    cross_provider = _session("agy", "default", Path("/tmp/agy-session.jsonl"))
    app = _tui_app(0, "target", [{"_kind": "new"}, cross_provider])

    assert app.command_for_current_focus() is None
    assert "WARNING: refusing cross-provider session share" in app.message

    same_provider = _session("codex", "source", Path("/tmp/codex-session.jsonl"))
    app = _tui_app(0, "target", [{"_kind": "new"}, same_provider])
    command = app.command_for_current_focus()
    assert command is not None
    assert command[command.index("-p") + 1] == "target"


def test_plan_warns_and_aborts_cross_provider() -> None:
    original_resolve = ai_session.resolve_session
    try:
        with tempfile.TemporaryDirectory() as tmp:
            row = _session("agy", "default", Path(tmp) / "agy-session.jsonl")
            ai_session.resolve_session = lambda *args, **kwargs: row
            try:
                ai_plan.build_execution_plan(
                    ai_plan.LaunchSpec(
                        command="run",
                        provider="codex",
                        profile="default",
                        directory=tmp,
                        session_ref="shared-ref",
                    )
                )
            except SystemExit as exc:
                message = str(exc)
                assert message.startswith("WARNING:")
                assert "Choose an option" not in message
            else:
                raise AssertionError("cross-provider session was not rejected")
    finally:
        ai_session.resolve_session = original_resolve


def main() -> None:
    test_same_provider_profile_share_is_default()
    test_tui_blocks_cross_provider_and_keeps_same_provider_profiles_runnable()
    test_plan_warns_and_aborts_cross_provider()


if __name__ == "__main__":
    main()
