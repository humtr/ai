# ai & clip — Unified AI CLI & Decoupled Proxy Suite

## 1. Overview

- **`ai`**: Pure config-driven CLI launcher and curses TUI for primary AI assistants (`codex`, `agy`, `hermes`).
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
