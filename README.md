# ai

Local Termux `ai` command for routing Codex, Gemini, Hermes, and bridge workflows.

## Live commands

- `ai`
- `gm`
- `cm`
- `hm`
- `hgw`
- `hgb`

## Meaning

- `ask` / `chat`: no-tool chat mode
- `task`: tool-capable work mode
- `plan`: plan-only mode
- `run`: provider-native interactive command through the common `ai` model
- `list`: session listing through the common `ai` model
- `resume`: session resume through the common `ai` model
- `browse`: interactive session picker where the provider supports one
- `raw` / `exec`: provider-native manager passthroughs

## Common wrapper model

Use `ai` first when you do not want to remember the native provider syntax.
Running `ai` with no arguments opens the TUI launcher/editor when attached to a
terminal.

```sh
ai
ai run gemini --profile main --cwd ~/prj/photos
ai task gemini --profile main --cwd ~/prj/photos "inspect this project"
ai list codex --profile main --cwd ~/prj/photos
ai resume codex --profile main --cwd ~/prj/photos latest
ai browse hermes --profile main --cwd ~/prj/photos
```

Common options:

- `--provider codex|gemini|hermes`
- `--account NAME`
- `--profile NAME` or `--home NAME` as legacy aliases for `--account`
- `--cwd DIR`, `--cd DIR`, or `-C DIR`
- `--sandbox` or `--sb`

By default the common `run`, `task`, `list`, and `resume` commands use the current
directory as the project working directory. Use `--cwd ~/work/main` or
`--cwd ~/prj/photos` for a specific work directory, or `--sandbox` to force the
provider sandbox under `~/sb/<provider>`.

`default`/`native` means the provider's original install environment:

- Codex: `~/.codex` with `CODEX_HOME` unset
- Gemini: real `~/.gemini` with `HOME` unchanged
- Hermes: `~/.hermes` native/current profile state

Named accounts are defined in `~/.ai/accounts.json` and map to provider-specific
profiles only when needed. Work directories are defined separately in
`~/.ai/workdirs.json`; accounts and work directories are not assumed to be 1:1.

Registry helpers:

```sh
ai accounts list
ai accounts add sub1-humetro --alias sub1 --map codex:sub1-humetro
ai workdirs add main ~/work/main --create --purpose "daily work"
ai profiles
ai gateways
```

## Important paths

Canonical `ai` paths:

- Source: `~/prj/ai/bin/ai`
- Live: `~/bin/ai`
- TUI/helper source: `~/prj/ai/code/ai-lib`
- TUI/helper live: `~/.config/ai/lib`

The source and live `ai` files must stay byte-identical. The common verifier
fails when `~/prj/ai/bin/ai` and `~/bin/ai` drift.

Live binaries:

- `~/bin/ai`
- `~/bin/gm`
- `~/bin/cm`
- `~/bin/hm`
- `~/bin/hgw`
- `~/bin/hgb`

Shared libs:

- `~/.config/ai/lib/manager_cwd_policy.sh`
- `~/.config/ai/lib/ai_registry.py`
- `~/.config/ai/lib/ai_tui.py`
- `~/.config/hgw/lib/approve.py`

Verified snapshots:

- `~/storage/downloads/termux/ai-final-*`
- `~/storage/downloads/termux/ai-final-*.tar.gz`

## Safety

Do not commit auth files, tokens, OAuth credentials, API keys, histories, or logs.
Keep remote repositories private unless the code is intentionally public.


## Local backup policy

Canonical local backups are stored under:

- `~/bak/ai/final`
- `~/bak/ai/archive`

Shared-storage copies under `~/storage/downloads/termux` are for export/transfer only.

## Verification

Run the common wrapper verifier without touching real sessions or credentials:

```sh
bash verify/ai-wrapper-common.sh
```
