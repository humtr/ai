# ai refactor Stage 6 — Resource Split, Session Resolve, and Bridge De-wrapper

Stage 6 turns the Stage 5 run core into a resource-oriented launcher/manager.

## Canonical syntax

```sh
ai run codex
ai run codex -p main
ai run codex -d ~/work/main
ai run codex -p main -d ~/work/main -s <session-ref>
```

Removed syntax remains removed:

```sh
ai resume ...
ai codex
aioops # unknown commands error
ai cm / ai gm / ai hm
```

## Resource commands

```sh
ai provider list|show|check
ai profile list|show
ai session refresh|list|show|resolve
ai workdir list|add|archive
ai gateway list|show|status
```

Resource names are singular by design.

## Module split

- `ai_spec.py`: command/provider config loading and validation.
- `ai_store.py`: paths, JSON read/write, workdir/gateway stores.
- `ai_provider.py`: provider profile adapters.
- `ai_session.py`: session discovery, parsing, indexing, resolution.
- `ai_plan.py`: `LaunchSpec -> ExecutionPlan`.
- `ai_resource.py`: resource command implementation.
- `ai_cli.py`: CLI frontend.
- `ai_tui.py`: TUI frontend only.
- `ai_registry.py`: compatibility shim.

## Gateway changes

`hgw` is renamed to `hgm` (Hermes Gateway Manager). Its config path is now:

```text
~/.config/hgm
```

`hgb` remains the Hermes Gemini Bridge, but no longer calls `gm task`. It uses the same `ai_plan` / Gemini profile adapter as `ai run/raw`.

## Validation

```sh
bash -n bin/ai bin/hgm lib/ai_core.sh
python -m py_compile lib/*.py bin/hgb
AI_DRY_RUN=1 bin/ai run codex
AI_DRY_RUN=1 bin/ai run gemini -p tg
AI_DRY_RUN=1 bin/ai run hermes -p main
bin/ai provider list
bin/ai session refresh
```
