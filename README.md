# ai & clip — Unified AI CLI & Decoupled Proxy Suite

## 1. Overview

- **`ai`**: Pure config-driven CLI launcher and curses TUI for primary AI assistants (`codex`, `agy`, `hermes`, `opencode`).
- **`clip`**: Standalone Command Line Interface Proxy manager (Telegram gateways, web fetcher, approvals, Gemini/AGY proxy bridges).

---

## 2. Supported Providers

1. **`codex`** (OpenAI Codex CLI)
   - Profile home: `CODEX_HOME` (`~/.codex` or `~/.codex-profiles/<profile>`)
   - Session resume: `codex resume <session-ref>`
2. **`agy`** (Antigravity CLI)
   - Profile home: `AGY_PROFILE_HOME` (`~/.gemini` or `~/.agy-profiles/<profile>/.gemini`)
   - Session resume: `agy --conversation <session-ref>`
3. **`hermes`** (Hermes Agent)
   - Profile arg: `--profile <profile>`
   - Session resume: `hermes --resume <session-ref>`
4. **`opencode`** (OpenCode AI)
   - Profile home: `HOME` (`~/.local/share/opencode` or `~/.opencode-profiles/<profile>`)
   - Session resume: `opencode --session <session-ref>` (or `opencode --continue`)

---

## 3. Canonical `ai` Syntax

```sh
ai run <provider> [-p PROFILE] [-d DIRECTORY] [-s SESSION]
ai ask <provider> [-p PROFILE] -- "prompt"
ai chat <provider> [-p PROFILE] -- "prompt"
ai raw <provider> [-p PROFILE] -- <native args>
ai tui
```

### Resource Management
```sh
ai provider list|show|check
ai profile list|show|add|delete
ai session refresh|list|show|resolve
ai workdir list|add|archive
```

---

## 4. `clip` Proxy Manager

`clip` operates independently from `ai`:

```sh
clip list
clip run <profile|alias|all>
clip stop <profile|alias|all>
clip restart <profile|alias|all>
clip status
clip auto on|off|status|run
clip web <url>
clip approve <request|allow|deny|list|show|cleanup>
clip gemini start|stop|status|logs|test|config|set
clip agy start|stop|status|logs|test|config|set
```

---

## 5. Verification & Installation

### Verification
```bash
bash verify/final-verify.sh
bash verify/ai-tui-smoke.sh
```

### Termux Installation
```bash
./scripts/install-termux.sh
```

### Optional tmux launch

`ai run codex --tmux` opens a managed tmux window (reuses the current server
when already inside tmux). The TUI tmux toggle defaults off and is stored with
launcher options; it is never passed upstream. Profiles, CWD and native arguments
are preserved. Codex's native terminal title gains `thread-id` first, retaining
other title items; no CLI config override is added.

`codex termux notify set --focus tmux` lets a notification select the existing
managed pane for its live conversation. Closed, ambiguous or unidentifiable
targets are left alone. The Termux terminal must display the originating tmux session; Android
foregrounding still selects the last Termux terminal. Taps never start another
Codex process or terminal. `--focus termux` restores ordinary foregrounding.

`bash scripts/install-termux.sh --ai-only` updates only the AI launcher/modules
atomically per file, without backups or changes to config, profiles, clip or AGY.
