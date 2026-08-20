#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ai_cli  # noqa: E402
import ai_plan  # noqa: E402


class Executed(Exception):
    pass


def test_plan_exec_replaces_manager() -> None:
    original = os.execvpe
    previous_cwd = os.getcwd()
    with tempfile.TemporaryDirectory() as directory:
        seen: dict[str, object] = {}

        def fake(file: str, argv: list[str], env: dict[str, str]) -> None:
            seen.update(file=file, argv=argv, env=env, cwd=os.getcwd())
            raise Executed

        os.execvpe = fake
        try:
            plan = ai_plan.ExecutionPlan(
                argv=["provider", "--flag"],
                env={"AI_EXEC_TEST": "yes"},
                cwd=directory,
                display="provider --flag",
            )
            try:
                ai_plan.execute_plan(plan)
            except Executed:
                pass
            else:
                raise AssertionError("provider was not exec'd")
        finally:
            os.execvpe = original
            os.chdir(previous_cwd)

    assert seen["file"] == "provider"
    assert seen["argv"] == ["provider", "--flag"]
    assert seen["cwd"] == directory
    assert isinstance(seen["env"], dict) and seen["env"]["AI_EXEC_TEST"] == "yes"


def test_tuis_replace_cli_manager() -> None:
    original = os.execv
    seen: list[list[str]] = []

    def fake(file: str, argv: list[str]) -> None:
        assert file == sys.executable
        seen.append(argv)
        raise Executed

    os.execv = fake
    try:
        for launch, name in ((ai_cli.tui_cmd, "ai_tui.py"),):
            try:
                launch(["--test"])
            except Executed:
                pass
            else:
                raise AssertionError(f"{name} was not exec'd")
            assert Path(seen[-1][1]).name == name
            assert seen[-1][2:] == ["--test"]
    finally:
        os.execv = original


def main() -> None:
    test_plan_exec_replaces_manager()
    test_tuis_replace_cli_manager()


if __name__ == "__main__":
    main()
