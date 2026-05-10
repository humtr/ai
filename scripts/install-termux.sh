#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_BIN="${AI_BIN_DEST:-$HOME/bin/ai}"
DEST_LIB="${AI_LIB_DEST:-$HOME/.config/ai/lib}"
BACKUP_ROOT="${AI_BACKUP_ROOT:-$HOME/.config/ai/backups}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/install-termux-$TS"

say() { printf '%s\n' "$*"; }
fail() { say "ERROR: $*" >&2; exit 1; }

say "== ai Termux installer =="
say "repo: $ROOT"
say "dest bin: $DEST_BIN"
say "dest lib: $DEST_LIB"
say "backup: $BACKUP_DIR"

[ -f "$ROOT/bin/ai" ] || fail "missing $ROOT/bin/ai"
[ -f "$ROOT/lib/ai_cli.py" ] || fail "missing $ROOT/lib/ai_cli.py"

say "-- preflight validation --"
python -m py_compile "$ROOT"/lib/*.py
bash -n "$ROOT/bin/ai"

mkdir -p "$BACKUP_DIR"

if [ -e "$DEST_BIN" ]; then
  cp -a "$DEST_BIN" "$BACKUP_DIR/ai.bak"
  say "backed up bin -> $BACKUP_DIR/ai.bak"
else
  say "no existing ai command to back up at $DEST_BIN"
fi

if [ -e "$DEST_LIB" ]; then
  cp -a "$DEST_LIB" "$BACKUP_DIR/lib.bak"
  say "backed up lib -> $BACKUP_DIR/lib.bak"
else
  say "no existing runtime lib to back up at $DEST_LIB"
fi

say "-- installing runtime lib --"
rm -rf "$DEST_LIB"
mkdir -p "$DEST_LIB"
cp -a "$ROOT/lib/." "$DEST_LIB/"

say "-- installing command --"
mkdir -p "$(dirname "$DEST_BIN")"
cp -f "$ROOT/bin/ai" "$DEST_BIN"
chmod +x "$DEST_BIN"

say "-- post-install validation --"
python -m py_compile "$DEST_LIB"/*.py
bash -n "$DEST_BIN"

say "-- resolution --"
RESOLVED="$(command -v ai || true)"
say "command -v ai: ${RESOLVED:-not found}"
if [ -n "$RESOLVED" ] && [ "$RESOLVED" != "$DEST_BIN" ]; then
  say "WARNING: PATH resolves ai to a different file:"
  say "  resolved: $RESOLVED"
  say "  installed: $DEST_BIN"
  say "Set AI_BIN_DEST to the resolved path, or adjust PATH, if this is not intended."
fi

say ""
say "Installed."
say "Backups: $BACKUP_DIR"
say "Run: ai"
