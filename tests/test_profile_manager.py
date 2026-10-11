#!/usr/bin/env python3
"""Manager ownership, account isolation, and preservation regression checks."""
from __future__ import annotations
import os
import json
import shlex
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import ai_provider
import ai_codex_manager
import ai_tui
import ai_plan
import ai_tmux


def main() -> None:
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"HOME": directory}):
        home = Path(directory)
        legacy = home / ".codex-profiles/legacy/sessions/thread.jsonl"
        legacy.parent.mkdir(parents=True)
        legacy.parent.parent.chmod(0o700)
        legacy.write_text("preserved")
        calls = []

        def manager(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, "default\naccount\n" if argv[-1] == "list" else "", "")

        with patch.object(ai_provider.subprocess, "run", manager):
            assert ai_provider.list_profiles("codex") == ["default", "account"]
            path = ai_provider.create_profile("codex", "new")
            assert path == home / ".local/share/codex/manager/profiles/new/home"
            assert calls[-1] == ["codex", "termux", "profile", "create", "new"]
        with patch.object(ai_provider.subprocess, "run", manager):
            args, env = ai_provider.apply_profile("codex", "account")
            assert args == ["termux", "profile", "use", "account", "--"] and env == {}
            assert ai_provider.apply_profile("codex", "default")[0][3] == "default"
        account = ai_codex_manager.create_profile("account")
        assert (account.parent / "profile.meta").read_bytes() == b"codex-manager-profile-v1\nid\taccount\n"
        assert account.stat().st_mode & 0o7777 == 0o700
        assert (account.parent / "profile.meta").stat().st_mode & 0o7777 == 0o600
        assert not (account / "sessions").exists()
        (account / "auth.json").write_text("private")
        assert legacy.read_text() == "preserved"
        failures = [FileNotFoundError("missing"), subprocess.TimeoutExpired("codex", 15)]
        for index, failure in enumerate(failures):
            with patch.object(ai_provider.subprocess, "run", side_effect=failure):
                assert ai_provider.list_profiles("codex") == ["default", "account", *(["new0"] if index else [])]
                args, env = ai_provider.apply_profile("codex", "account")
                assert args == [] and env == {"CODEX_HOME": str(account)}
                assert ai_provider.create_profile("codex", f"new{index}").is_dir()
                app = ai_tui.App.__new__(ai_tui.App)
                app.providers = ["codex"]
                app.indices = {"provider": 0, "profile": 0}
                app.profiles = app.discover_profiles("codex")
                assert app.validate_builder_profile()
        assert legacy.read_text() == "preserved"
        assert (account / "auth.json").read_text() == "private"
        candidate = account.parent.parent / ".publish-test"
        candidate.mkdir(mode=0o700)
        try:
            ai_codex_manager.publish(candidate, account.parent)
        except FileExistsError:
            pass
        else:
            raise AssertionError("atomic publication replaced an existing profile")
        assert candidate.is_dir() and (account / "auth.json").read_text() == "private"
        for name in ("native", "a..b"):
            assert ai_codex_manager.create_profile(name).is_dir()
        assert "CODEX_HOME" in ai_codex_manager.launch_profile("default")[1]
        for name in ("_wrong", "-wrong", "home", "default", "termux", "../wrong"):
            try:
                ai_codex_manager.create_profile(name)
            except ValueError:
                pass
            else:
                raise AssertionError(f"invalid manager identity was created: {name}")
        try:
            ai_codex_manager.create_profile("account")
        except ValueError:
            pass
        else:
            raise AssertionError("existing manager profile was overwritten")
        meta = account.parent / "profile.meta"
        meta.chmod(0o644)
        assert "account" not in ai_codex_manager.list_profiles()
        try:
            ai_codex_manager.launch_profile("account")
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe profile was launched")
        meta.chmod(0o600)
        root = home / ".local/share/codex/manager"
        root.chmod(0o755)
        with patch.object(ai_provider.subprocess, "run", side_effect=failures[0]):
            try:
                ai_provider.list_profiles("codex")
            except ValueError:
                pass
            else:
                raise AssertionError("unsafe manager root was bypassed")
        root.chmod(0o700)

        for provider in ("agy", "hermes", "opencode"):
            path = ai_provider.create_profile(provider, "a")
            (path / "auth.json").write_text("private")
            ai_provider.rename_profile(provider, "a", "b")
            renamed = ai_provider.profile_path(provider, "b")
            assert (renamed / "auth.json").read_text() == "private"
            if provider == "hermes":
                assert (renamed / "state.db").is_symlink()
            ai_provider.delete_profile(provider, "b")
            assert not renamed.exists()

        path = home / ".agy-profiles/old"
        conflict = path / ".gemini/antigravity-cli/brain/thread"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("preserved")
        try:
            ai_provider.ensure_shared_runtime("agy", path)
        except ValueError:
            pass
        else:
            raise AssertionError("legacy data was overwritten")
        assert conflict.read_text() == "preserved"
        assert not (path / ".gemini/antigravity-cli/conversations").exists()
        for action in (ai_provider.delete_profile, ai_provider.rename_profile):
            try:
                action("codex", "account", *(["new"] if action == ai_provider.rename_profile else []))
            except ValueError as error:
                assert "manager" in str(error)
            else:
                raise AssertionError("manager-owned profile was modified")
    class Captured(Exception):
        pass
    commands = []
    titles = []
    def tmux(socket, *args):
        if args[0] == "show-options":
            assert args[-1] == "@termux_origin_v1"
            return ""
        if args[0] == "display-message":
            return "/fixture/socket"
        if args[0] == "new-session":
            commands.append(args[-1])
            raise Captured
        raise AssertionError(args)
    plan = ai_plan.ExecutionPlan(
        argv=["codex", "termux", "profile", "use", "account", "--", "resume", "thread"],
        env={}, cwd="/fixture/work", display="", tmux_provider="codex", auth_recovery=True,
    )
    with patch.dict(os.environ, {"TMUX": ""}), \
            patch.object(ai_tmux.shutil, "which", return_value="tmux"), \
            patch.object(ai_provider, "list_profiles", return_value=["default", "account"]), \
            patch.object(ai_tmux, "prepare_title", side_effect=lambda home: titles.append(home)), \
            patch.object(ai_tmux, "_tmux", tmux), \
            patch.object(ai_tmux, "_manager_launch", return_value=False), \
            patch.object(ai_tmux, "_native_identity", return_value=False), \
            patch.object(ai_tmux.ai_terminal, "resolve", return_value=None):
        try:
            ai_tmux.launch(plan, "codex")
        except Captured:
            pass
        else:
            raise AssertionError("tmux window command not reached")
    argv = shlex.split(commands[0])
    helper_index = next(i for i, value in enumerate(argv) if value.endswith("ai_run.py"))
    serialized = json.loads(argv[helper_index + 1])
    assert serialized["argv"] == plan.argv
    assert serialized["auth_recovery"] and serialized["tmux_provider"] is None
    assert serialized["cwd"] == plan.cwd
    assert titles == [Path.home() / ".local/share/codex/manager/profiles/account/home"]
    from dataclasses import replace
    for selected_env, unset, expected_title in [
        ({"CODEX_HOME": "/fixture/account/home"}, list(ai_codex_manager.LAUNCH_UNSET), Path("/fixture/account/home")),
        ({}, [*ai_codex_manager.LAUNCH_UNSET, "CODEX_HOME"], Path.home() / ".codex"),
    ]:
        fallback = replace(plan, argv=["codex", "resume", "thread"], env=selected_env, env_unset=unset)
        titles.clear()
        with patch.dict(os.environ, {"TMUX": "", "CODEX_HOME": "/wrong-account"}), \
                patch.object(ai_tmux.shutil, "which", return_value="tmux"), \
                patch.object(ai_tmux, "prepare_title", side_effect=lambda home: titles.append(home)), \
                patch.object(ai_tmux, "_tmux", tmux), \
            patch.object(ai_tmux, "_manager_launch", return_value=False), \
            patch.object(ai_tmux, "_native_identity", return_value=False), \
            patch.object(ai_tmux.ai_terminal, "resolve", return_value=None):
            try:
                ai_tmux.launch(fallback, "codex")
            except Captured:
                pass
        argv = shlex.split(commands[-1])
        helper_index = next(i for i, value in enumerate(argv) if value.endswith("ai_run.py"))
        serialized = json.loads(argv[helper_index + 1])
        assert serialized["env_unset"] == unset
        assert serialized["env"] == selected_env
        assert "CODEX_HOME=/wrong-account" not in argv
        assert titles == [expected_title]
    print("PASS manager failures, account isolation, shared storage, and preservation")


if __name__ == "__main__":
    main()
