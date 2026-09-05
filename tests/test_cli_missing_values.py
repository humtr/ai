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


def main() -> None:
    for opt in ("-p", "--profile", "-s", "--session", "-d", "--directory", "--cwd", "--cd", "-C", "--context"):
        expect_missing_value([opt])
        expect_missing_value([opt, "--"])


if __name__ == "__main__":
    main()
