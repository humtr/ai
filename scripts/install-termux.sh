#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_BIN="${AI_BIN_DEST:-$HOME/bin/ai}"
DEST_LIB="${AI_LIB_DEST:-$HOME/.config/ai/lib}"
DEST_HGM="${AI_HGM_DEST:-$HOME/bin/hgm}"
DEST_HGB="${AI_HGB_DEST:-$HOME/bin/hgb}"
DEST_AGY="${AI_AGY_DEST:-$HOME/bin/agy}"
DEST_HGM_LIB="${AI_HGM_LIB_DEST:-$HOME/.config/hgm/lib}"
BACKUP_ROOT="${AI_BACKUP_ROOT:-$HOME/.config/ai/backups}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/install-termux-$TS"

say() { printf '%s\n' "$*"; }
fail() { say "ERROR: $*" >&2; exit 1; }

say "== ai Termux installer =="
say "repo: $ROOT"
say "dest bin: $DEST_BIN"
say "dest lib: $DEST_LIB"
say "dest hgm: $DEST_HGM"
say "dest hgb: $DEST_HGB"
say "dest hgm lib: $DEST_HGM_LIB"
say "backup: $BACKUP_DIR"

[ -f "$ROOT/bin/ai" ] || fail "missing $ROOT/bin/ai"
[ -f "$ROOT/bin/hgm" ] || fail "missing $ROOT/bin/hgm"
[ -f "$ROOT/bin/hgb" ] || fail "missing $ROOT/bin/hgb"
[ -f "$ROOT/bin/agy" ] || fail "missing $ROOT/bin/agy"
[ -f "$ROOT/lib/ai_cli.py" ] || fail "missing $ROOT/lib/ai_cli.py"
[ -f "$ROOT/code/hgw-lib/approve.py" ] || fail "missing $ROOT/code/hgw-lib/approve.py"
[ -f "$ROOT/code/hgw-lib/web_fetch.py" ] || fail "missing $ROOT/code/hgw-lib/web_fetch.py"

say "-- preflight validation --"
python -m py_compile "$ROOT"/lib/*.py
python -m py_compile "$ROOT/bin/hgb" "$ROOT"/code/hgw-lib/*.py
bash -n "$ROOT/bin/ai"
bash -n "$ROOT/bin/hgm"
bash -n "$ROOT/bin/agy"

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

if [ -e "$DEST_HGM" ]; then
  cp -a "$DEST_HGM" "$BACKUP_DIR/hgm.bak"
  say "backed up $DEST_HGM -> $BACKUP_DIR/hgm.bak"
fi
if [ -e "$DEST_HGB" ]; then
  cp -a "$DEST_HGB" "$BACKUP_DIR/hgb.bak"
  say "backed up $DEST_HGB -> $BACKUP_DIR/hgb.bak"
fi
if [ -e "$DEST_AGY" ]; then
  cp -a "$DEST_AGY" "$BACKUP_DIR/agy.bak"
  say "backed up $DEST_AGY -> $BACKUP_DIR/agy.bak"
fi
if [ -e "$DEST_HGM_LIB" ]; then
  cp -a "$DEST_HGM_LIB" "$BACKUP_DIR/hgm-lib.bak"
  say "backed up $DEST_HGM_LIB -> $BACKUP_DIR/hgm-lib.bak"
fi

say "-- installing runtime lib --"
rm -rf "$DEST_LIB"
mkdir -p "$DEST_LIB"
cp -a "$ROOT/lib/." "$DEST_LIB/"

say "-- installing command --"
mkdir -p "$(dirname "$DEST_BIN")"
cp -f "$ROOT/bin/ai" "$DEST_BIN"
chmod +x "$DEST_BIN"
cp -f "$ROOT/bin/agy" "$DEST_AGY"
chmod +x "$DEST_AGY"

say "-- installing gateway commands --"
mkdir -p "$(dirname "$DEST_HGM")" "$(dirname "$DEST_HGB")"
cp -f "$ROOT/bin/hgm" "$DEST_HGM"
cp -f "$ROOT/bin/hgb" "$DEST_HGB"
chmod +x "$DEST_HGM" "$DEST_HGB"

say "-- installing gateway helper lib --"
mkdir -p "$DEST_HGM_LIB"
cp -f "$ROOT/code/hgw-lib/approve.py" "$DEST_HGM_LIB/approve.py"
cp -f "$ROOT/code/hgw-lib/web_fetch.py" "$DEST_HGM_LIB/web_fetch.py"
chmod +x "$DEST_HGM_LIB/approve.py" "$DEST_HGM_LIB/web_fetch.py"

say "-- migrating hgw config to hgm config --"
mkdir -p "$HOME/.config/hgm"
if [ -d "$HOME/.config/hgw" ]; then
  for name in aliases.tsv bridge.env bridge.routes.json auto.disabled; do
    if [ -e "$HOME/.config/hgw/$name" ] && [ ! -e "$HOME/.config/hgm/$name" ]; then
      cp -a "$HOME/.config/hgw/$name" "$HOME/.config/hgm/$name"
      say "migrated $name"
    fi
  done
fi

say "-- post-install validation --"
python -m py_compile "$DEST_LIB"/*.py
python -m py_compile "$DEST_HGB" "$DEST_HGM_LIB"/*.py
bash -n "$DEST_BIN"
bash -n "$DEST_HGM"
bash -n "$DEST_AGY"

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
