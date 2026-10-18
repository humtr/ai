#!/usr/bin/env python3
"""Session filters must work on either side of a session reference."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import ai_cli  # noqa: E402
import ai_session  # noqa: E402


def test_filters_after_session_reference() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        records = [
            {
                "provider": provider,
                "profile": profile,
                "path": str(Path(tmp) / f"{provider}.jsonl"),
                "workdir": tmp,
                "session_id": "shared-ref",
                "native_session_ref": "shared-ref",
                "mtime": 1.0,
                "title": provider,
            }
            for provider, profile in (("codex", "work"), ("agy", "default"))
        ]
        index = {"sessions": records}
        with patch.object(ai_session, "fresh_session_index", return_value=index), patch.object(
            ai_session, "refresh_session_index", return_value=index
        ):
            for command, options, expected_provider in (
                ("show", ["--provider", "codex"], "codex"),
                ("resolve", ["--provider", "agy"], "agy"),
                ("show", ["--provider", "codex", "--profile", "work"], "codex"),
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    status = ai_cli.main(["session", command, "shared-ref", *options])
                assert status == 0, (command, options, status)
                selected = json.loads(stdout.getvalue())
                assert selected.get("provider") == expected_provider, selected
                assert not selected.get("ambiguous"), selected
                assert selected.get("native_session_ref") == "shared-ref", selected


if __name__ == "__main__":
    test_filters_after_session_reference()
