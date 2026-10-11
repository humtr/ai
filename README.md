# ai & clip — Unified AI CLI & Decoupled Proxy Suite

## 1. Overview

- **`ai`**: Pure config-driven CLI launcher and curses TUI for primary AI assistants (`codex`, `agy`, `hermes`, `opencode`).
- **`clip`**: Standalone Command Line Interface Proxy manager (Telegram gateways, web fetcher, approvals, Gemini/AGY proxy bridges).

---

## 2. Supported Providers

1. **`codex`** (OpenAI Codex CLI)
   - Profiles: `codex termux profile list/create/use`; manager homes are `~/.local/share/codex/manager/profiles/<profile>/home`, with conversations shared through `~/.codex`
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
ai profile list|show|add|rename|delete
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

`ai run codex --tmux` outside tmux starts a separate managed session with its
own originating Android terminal; it never hides a prior launch in another terminal.
Inside tmux it opens a window in the invoking pane's exact session, preserving
other sessions' selection even when another client was active more recently.
`--tmux=hidden` is equivalent; `--tmux=status` shows
a clickable window bar and `--tmux=off` uses an ordinary terminal. The TUI offers
`off / on-hidden / on-status`, defaults off and is stored with
launcher options; it is never passed upstream. Profiles, CWD and native arguments
are preserved. The qualified Codex Core/Manager capability keeps native title settings intact;
historical title-based focus gains `thread-id` first, retaining
other title items; no CLI config override is added. New panes inherit the current
caller's color preferences, including absence of `NO_COLOR`, rather than stale
server values. Explicit color settings are preserved; tmux owns `TERM`. An already
running application keeps its startup environment until it is relaunched.
Hidden mode hides the AI-managed session's bottom status row. Status mode shows
one row and enables mouse support; tap a window name to select it. The latest
launch choice applies to the managed session. Existing unmanaged sessions retain
their status/mouse settings; global tmux configuration is preserved. Old stored
true/false preferences become on-hidden/off. This bar switches tmux windows;
Android Termux terminal selection remains a separate capability.

`codex termux notify set --focus window` selects the registered live workload.
The former tmux value remains a compatibility alias. `--focus termux` brings
only the app forward. Exact-return failure never automatically changes routes.
A separate Android terminal may run independent work; requesting another tmux
container inside tmux is refused.

`bash scripts/install-termux.sh --ai-only` updates only the AI launcher/modules
atomically per file, without backups or changes to config, profiles, clip or AGY.


The TUI Scope choices are New, Provider, and All. Profile selects account credentials;
it does not filter the session list. The launcher no longer copies individual
conversations between profiles. Other providers share their upstream conversation
storage while keeping account files private. Existing nonempty private session
storage requires a separate migration; the launcher preserves it and reports its path.

Ctrl-R on the Profile row renames profiles; elsewhere it refreshes sessions.
`ai profile rename PROVIDER OLD NEW` provides the same operation. Codex rename and delete call the manager lifecycle commands and verify the
result by reloading the manager list. Manager refusal (for example, an active
or selected default profile) is shown in a popup. Lifecycle operations never
bypass manager protections through local fallback. Renamed v2 metadata is
recognized by the read/launch fallback.

After an interactive Codex launch fails with a recognized authentication error,
ai offers logout, login, and one retry using the same selected profile and session.
Declining leaves credentials untouched. A workspace routing discovery timeout is
reported separately because it does not establish authentication expiry.

If the Codex manager is unavailable, fails, times out, or returns an invalid list,
ai falls back to the same manager profile contract locally: ASCII IDs, private
0700 directories, exact 0600 `profile.meta`, and `<id>/home` for credentials.
Listing ignores incomplete profiles; creation publishes a new private profile
atomically without replacing an existing one. Launch sets the selected
`CODEX_HOME`, clears manager handoff/SQLite overrides, and invokes the Codex wrapper
with the original upstream arguments. Default/home clears inherited `CODEX_HOME`.
Core still prepares the canonical shared conversation topology. A manager handoff
failure during launch also switches to this fallback once; authentication and
upstream session failures do not trigger it. Invalid profile/root state remains
an error. Legacy profiles are registered into manager homes using
`PYTHONPATH=lib python3 lib/ai_profile_migrate.py`. The transition preserves the
original directory and file identities, requires legacy sessions to be closed and removes the empty legacy root,
and checks all profiles for collisions and canonical shared topology before moving.
ai and its fallback list only registered manager profiles, using one storage tree.

### Android notification navigation

Codex uses its qualified Core/Manager route with or without tmux. The installed
native-origin Termux extension returns to the invoking terminal using live handle,
PID and kernel start identity. `/title` chooses upstream information fields and
order; it does not change the terminal address. AI preserves the title selection
when native foreground identity is supported. The app source belongs to the
separate `humtr/termux` project.

A confirmed stock APK uses one named dedicated terminal at launch, then reuses
that window without requiring tmux. Stock has no atomic existing-only selection:
a manual rename or close race may create an inert empty terminal, never restart
Codex. Inconclusive AM failure does not become another launch attempt. Each fresh
notification takes one tap and is consumed by Android.

`codex termux launch` provides profile choice with tmux off by default;
`codex termux tmux` requests hidden tmux. AI's explicit tmux mode uses the same
qualified Manager adapter, retaining authentication recovery. A tmux request from
inside tmux is refused before constructing another session/window/pane. Start
independent work in another Android terminal. Legacy title-based routing remains
only for unsupported older frontends.
