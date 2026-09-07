#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ai_cli  # noqa: E402


def expect_missing_value(args: list[str]) -> None:
    try:
        ai_cli.parse_common(args)
    except SystemExit as exc:
        assert exc.code != 0
        return
    raise AssertionError(f"expected SystemExit for {args!r}")


def test_json_cmd_missing_args() -> None:
    assert ai_cli.json_cmd(["profiles"]) == 2
    assert ai_cli.json_cmd(["plan"]) == 2


def test_resource_cmd_missing_or_invalid_args() -> None:
    assert ai_cli.main(["session", "list", "--provider"]) == 2
    assert ai_cli.main(["session", "list", "--limit", "notanint"]) == 2
    assert ai_cli.main(["provider", "show", "nonexistent"]) == 1
    assert ai_cli.main(["profile", "list", "nonexistent"]) == 1


def main() -> None:
    for opt in ("-p", "--profile", "-s", "--session", "-d", "--directory", "--cwd", "--cd", "-C", "--context", "--compact"):
        expect_missing_value([opt])
        expect_missing_value([opt, "--"])
    test_json_cmd_missing_args()
    test_resource_cmd_missing_or_invalid_args()


if __name__ == "__main__":
    main()
