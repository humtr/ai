# ai-stack

Termux AI command stack.

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
- `run` / `raw` / `exec`: provider-native commands with sandbox routing through `ai`

## Important paths

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

- `~/storage/downloads/termux/ai-stack-final-*`
- `~/storage/downloads/termux/ai-stack-final-*.tar.gz`

## Safety

Do not commit auth files, tokens, OAuth credentials, API keys, histories, or logs.
Keep remote repositories private unless the code is intentionally public.
