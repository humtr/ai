# Codex manager follow-up

The ai changes preserve the Codex wrapper source and use its public
`codex termux profile list/create/use` commands. The local fallback implements the same profile validation and private creation
contract. Existing credentials and shared conversation topology are not rewritten.

## Confirmed integration problem fixed in ai

ai previously discovered and created `~/.codex-profiles/<name>` and copied or
symlinked individual conversations when resuming with a different account.
The current wrapper instead discovers manager profiles at
`~/.local/share/codex/manager/profiles/<id>/home` and prepares conversation links
to `~/.codex`. Core's `shared_layout::prepare` deliberately rejects nonempty
private conversation entries or links pointing anywhere other than the canonical
shared location. ai now delegates profile ownership to manager and removes
per-conversation sharing mutations.

A read-only inspection of the currently present legacy and manager profile roots
found no conflicting conversation entries. This does not reproduce the historical
launch failure or prove that other machines have completed the legacy transition.
Legacy accounts are transitioned into real manager homes by ai_profile_migrate.py.
The original directories are moved into hidden private staging and atomically
published only after the real home and metadata are complete, without copying
credentials or SQLite files. Failure before publication restores the original
path; inability to verify any same-user live process refuses migration.
and the empty legacy root is removed after migration. Active legacy profiles
block migration until their sessions are closed. ai and manager then list one profile set. ai does not silently import credentials or rewrite
upstream session files/databases.

## Manager lifecycle integration

Current manager supports profile delete, rename, and default selection. ai calls
its delete/rename commands, then verifies the resulting list before reporting
success. TUI Ctrl-R renames Codex profiles and Ctrl-D deletes after confirmation.
Manager errors are shown in a popup, preserving the selected profile on refusal.
The read/launch fallback accepts both v1 metadata and manager's name-independent
v2 metadata emitted by rename. It does not implement destructive lifecycle
fallbacks that could bypass manager process/default-profile checks.

Actual installed manager create/rename/delete is tested against temporary profiles,
including the TUI yes input, protected-default refusal, and preservation of a
shared session symlink target. Real account profiles are not deleted by tests.

## Routing timeout needs separate investigation

`account/read failed ... workspace routing discovery timed out (code -32603)`
does not establish token expiry. The inspected manager/core files do not establish
the cause, and no live failing account was reproduced. Do not log out accounts or
restart a shared server solely because this timeout occurred.

For the wrapper maintainer: reproduce account/read with the affected manager
profile, compare direct wrapper launch with ai launch, and inspect workspace
routing discovery and shared-server account selection. Check whether logout/login
on that profile invalidates or refreshes server account state. If it does not,
manager/core needs an account refresh mechanism that preserves other live clients.
These are investigation steps, not confirmed defects.

ai offers an explicit logout/login and one retry after recognized authentication
failure, preserving the selected profile, session, and working directory. This
was tested with a fake provider in real PTYs, including declining the prompt and
not treating the routing timeout as an authentication error. No real credentials
were changed during verification.

## Manager failure behavior

If manager commands fail, time out, or return malformed lists, ai uses a local
implementation of the inspected manager contract in `lib/ai_codex_manager.py`.
It validates the same IDs, reserved names, non-symlink path chain, 0700 directories,
and bounded exact 0600 metadata. Listing excludes incomplete entries. Creation
writes only private profile material, fsyncs it, and publishes with atomic
renameat2/no-replace. It never imports a legacy account or changes an existing one.

Launch uses the same `<id>/home` for `CODEX_HOME`, removes manager handoff and
CODEX_SQLITE_HOME overrides, and runs Core through the existing Codex wrapper.
Default/home removes inherited CODEX_HOME. Shared layout preparation stays in Core.
Known manager handoff failures at execution time also trigger one local fallback;
authentication and ordinary upstream failures do not. Unsafe paths, bad permissions,
and missing/invalid selected profiles still fail, without choosing another account.
