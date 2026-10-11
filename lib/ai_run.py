#!/usr/bin/env python3
"""Execute a serialized launch plan inside its tmux terminal."""
from __future__ import annotations
import json
import sys
from ai_plan import ExecutionPlan, execute_plan

if __name__ == "__main__":
    try:
        raise SystemExit(execute_plan(ExecutionPlan(**json.loads(sys.argv[1]))))
    except (ValueError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
