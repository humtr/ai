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

Use `ai` first when you do not want to remember the native provider syntax:

```sh
ai run gemini --profile main --cwd ~/prj/photos
ai task gemini --profile main --cwd ~/prj/photos "inspect this project"
ai list codex --profile main --cwd ~/prj/photos
ai resume codex --profile main --cwd ~/prj/photos latest
ai browse hermes --profile main --cwd ~/prj/photos
```

Common options:

- `--provider codex|gemini|hermes`
- `--profile NAME` or `--home NAME`
- `--cwd DIR`, `--cd DIR`, or `-C DIR`
- `--sandbox` or `--sb`

By default the common `run`, `task`, `list`, and `resume` commands use the
current directory as the project working directory. Use `--cwd ~/prj/photos` for
a specific project, or `--sandbox` to force `~/sb/<provider>/<profile>`.

Account selection is profile/home-bound. Choose the provider home that carries
the desired credentials with `--profile`/`--home`; pass narrower provider-native
account switches after `--` only when the provider supports them.

## Important paths

Canonical `ai` paths:

- Source: `~/prj/ai/bin/ai`
- Live: `~/bin/ai`

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
