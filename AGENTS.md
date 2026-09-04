# Repository Guidelines

This repository is a Termux-oriented, config-driven toolkit for launching AI providers and managing independent `clip` proxy services. Make changes from the repository root so the verification scripts resolve paths consistently.

## Project Structure & Module Organization

- `bin/` contains the executable Bash entrypoints: `ai`, `agy`, and `clip`.
- `lib/` contains the Python CLI, TUI, provider/session/config logic, and `clip` integrations.
- `code/ai-lib/` contains auxiliary libraries used by the CLI and TUI.
- `config/` holds versioned provider and command JSON; keep machine-local settings in ignored `config-safe/`.
- `tests/` contains focused Python regression scripts. `verify/` contains shell integration and TUI smoke tests; `scripts/install-termux.sh` performs installation. `snapshots/` is for generated/local snapshot artifacts.

## Build, Test, and Development Commands

There is no separate build system. From the repository root, use:

```sh
python3 -m py_compile lib/*.py       # Python syntax check
bash -n bin/ai                       # Repeat for bin/agy and bin/clip
for test in tests/test_*.py; do python3 "$test"; done
bash verify/ai-tui-smoke.sh          # TUI behavior with isolated fixtures
bash verify/final-verify.sh           # Full syntax, behavior, and integration checks
```

For a non-invasive CLI check, run `AI_DRY_RUN=1 PYTHONPATH=lib python3 lib/ai_cli.py provider list`.

## Coding Style & Naming Conventions

Use Python 3 with four-space indentation, type annotations where practical, `snake_case` functions/modules, and `PascalCase` classes. Use defensive Bash (`set -u` or `set -euo pipefail` as appropriate), quote paths, and preserve executable bits. Use two-space indentation in JSON and prefer extending `config/*.json` over hardcoding provider behavior. No project-wide formatter or linter is configured; `py_compile` and `bash -n` are the baseline checks.

## Testing Guidelines

Name Python tests `tests/test_*.py`; they are standalone scripts and do not require a pytest dependency or enforce a coverage threshold. Use temporary, isolated fixtures rather than real home-directory credentials. Add or update `verify/ai-tui-smoke.sh` when changing interactive TUI behavior, and run `final-verify.sh` before submitting.

## Commit & Pull Request Guidelines

Follow the recent Conventional Commit style, such as `feat(tui): add session filter` or `fix(install): preserve config`. Keep subjects concise and scoped. PRs should explain the behavior and compatibility impact, identify relevant config or entrypoint changes, list commands run (including verification results), and include terminal output or a screenshot/GIF for TUI changes. Never commit secrets, tokens, local `.env` files, or generated full snapshots.
