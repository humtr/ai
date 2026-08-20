#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_BIN="${AI_BIN_DEST:-$HOME/bin/ai}"
DEST_LIB="${AI_LIB_DEST:-$HOME/.config/ai/lib}"
DEST_CONFIG="${AI_CONFIG_DEST:-$HOME/.config/ai/config}"
DEST_AGY="${AI_AGY_DEST:-$HOME/bin/agy}"

# Rebranded CLI Proxy Suite destinations
DEST_CLIP="${AI_CLIP_DEST:-$HOME/bin/clip}"
DEST_CLIP_LIB="${AI_CLIP_LIB_DEST:-$HOME/.config/clip/lib}"
BACKUP_ROOT="${AI_BACKUP_ROOT:-$HOME/.config/ai/backups}"
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/install-termux-$TS"

say() { printf '%s\n' "$*"; }
fail() { say "ERROR: $*" >&2; exit 1; }

say "== ai & clip Termux installer =="
say "repo: $ROOT"
say "dest bin: $DEST_BIN"
say "dest lib: $DEST_LIB"
say "dest config: $DEST_CONFIG"
say "dest clip: $DEST_CLIP"
say "dest clip lib: $DEST_CLIP_LIB"
say "backup: $BACKUP_DIR"

[ -f "$ROOT/bin/ai" ] || fail "missing $ROOT/bin/ai"
[ -f "$ROOT/bin/clip" ] || fail "missing $ROOT/bin/clip"
[ -f "$ROOT/lib/clip_gemini.py" ] || fail "missing $ROOT/lib/clip_gemini.py"
[ -f "$ROOT/lib/clip_agy.py" ] || fail "missing $ROOT/lib/clip_agy.py"
[ -f "$ROOT/lib/clip_approve.py" ] || fail "missing $ROOT/lib/clip_approve.py"
[ -f "$ROOT/lib/clip_web_fetch.py" ] || fail "missing $ROOT/lib/clip_web_fetch.py"
[ -f "$ROOT/bin/agy" ] || fail "missing $ROOT/bin/agy"
[ -f "$ROOT/lib/ai_cli.py" ] || fail "missing $ROOT/lib/ai_cli.py"

say "-- preflight validation --"
python3 -m py_compile "$ROOT"/lib/*.py
bash -n "$ROOT/bin/ai"
bash -n "$ROOT/bin/clip"
bash -n "$ROOT/bin/agy"

mkdir -p "$BACKUP_DIR"

# Back up ai command
if [ -e "$DEST_BIN" ]; then
  cp -a "$DEST_BIN" "$BACKUP_DIR/ai.bak"
  say "backed up bin -> $BACKUP_DIR/ai.bak"
else
  say "no existing ai command to back up at $DEST_BIN"
fi

# Back up runtime lib
if [ -e "$DEST_LIB" ]; then
  cp -a "$DEST_LIB" "$BACKUP_DIR/lib.bak"
  say "backed up lib -> $BACKUP_DIR/lib.bak"
else
  say "no existing runtime lib to back up at $DEST_LIB"
fi

# Back up config
if [ -e "$DEST_CONFIG" ]; then
  cp -a "$DEST_CONFIG" "$BACKUP_DIR/config.bak"
  say "backed up config -> $BACKUP_DIR/config.bak"
fi

# Back up clip bin & lib
if [ -e "$DEST_CLIP" ]; then
  cp -a "$DEST_CLIP" "$BACKUP_DIR/clip.bak"
  say "backed up $DEST_CLIP -> $BACKUP_DIR/clip.bak"
fi
if [ -e "$DEST_CLIP_LIB" ]; then
  cp -a "$DEST_CLIP_LIB" "$BACKUP_DIR/clip-lib.bak"
  say "backed up $DEST_CLIP_LIB -> $BACKUP_DIR/clip-lib.bak"
fi
if [ -e "$DEST_AGY" ]; then
  cp -a "$DEST_AGY" "$BACKUP_DIR/agy.bak"
  say "backed up $DEST_AGY -> $BACKUP_DIR/agy.bak"
fi

# Back up legacy HGM files if they exist to keep backup safety
if [ -e "$HOME/bin/hgm" ]; then
  cp -a "$HOME/bin/hgm" "$BACKUP_DIR/hgm.bak"
  say "backed up legacy hgm -> $BACKUP_DIR/hgm.bak"
fi

say "-- installing runtime lib --"
rm -rf "$DEST_LIB"
mkdir -p "$DEST_LIB"
cp -a "$ROOT/lib/." "$DEST_LIB/"

say "-- installing config --"
mkdir -p "$DEST_CONFIG"
cp -a "$ROOT/config/." "$DEST_CONFIG/"

say "-- installing command --"
mkdir -p "$(dirname "$DEST_BIN")"
cp -f "$ROOT/bin/ai" "$DEST_BIN"
chmod +x "$DEST_BIN"
cp -f "$ROOT/bin/agy" "$DEST_AGY"
chmod +x "$DEST_AGY"

say "-- installing clip commands & libraries --"
mkdir -p "$(dirname "$DEST_CLIP")"
cp -f "$ROOT/bin/clip" "$DEST_CLIP"
chmod +x "$DEST_CLIP"

rm -rf "$DEST_CLIP_LIB"
mkdir -p "$DEST_CLIP_LIB"
cp -f "$ROOT/lib/clip_gemini.py" "$DEST_CLIP_LIB/clip_gemini.py"
cp -f "$ROOT/lib/clip_agy.py" "$DEST_CLIP_LIB/clip_agy.py"
cp -f "$ROOT/lib/clip_approve.py" "$DEST_CLIP_LIB/clip_approve.py"
cp -f "$ROOT/lib/clip_web_fetch.py" "$DEST_CLIP_LIB/clip_web_fetch.py"
chmod +x "$DEST_CLIP_LIB"/*.py

say "-- migrating config to clip config --"
mkdir -p "$HOME/.config/clip"

# 1. Migrate from legacy HGW (old hermes gateway) if config exists and clip doesn't
if [ -d "$HOME/.config/hgw" ]; then
  for name in aliases.tsv auto.disabled; do
    if [ -e "$HOME/.config/hgw/$name" ] && [ ! -e "$HOME/.config/clip/$name" ]; then
      cp -a "$HOME/.config/hgw/$name" "$HOME/.config/clip/$name"
      say "migrated $name from hgw"
    fi
  done
  if [ -e "$HOME/.config/hgw/bridge.env" ] && [ ! -e "$HOME/.config/clip/clip_gemini.env" ]; then
    cp -a "$HOME/.config/hgw/bridge.env" "$HOME/.config/clip/clip_gemini.env"
    say "migrated bridge.env -> clip_gemini.env"
  fi
  if [ -e "$HOME/.config/hgw/hab.env" ] && [ ! -e "$HOME/.config/clip/clip_agy.env" ]; then
    cp -a "$HOME/.config/hgw/hab.env" "$HOME/.config/clip/clip_agy.env"
    say "migrated hab.env -> clip_agy.env"
  fi
  if [ -e "$HOME/.config/hgw/bridge.routes.json" ] && [ ! -e "$HOME/.config/clip/clip_gemini.routes.json" ]; then
    cp -a "$HOME/.config/hgw/bridge.routes.json" "$HOME/.config/clip/clip_gemini.routes.json"
    say "migrated bridge.routes.json -> clip_gemini.routes.json"
  fi
  if [ -e "$HOME/.config/hgw/agy.routes.json" ] && [ ! -e "$HOME/.config/clip/clip_agy.routes.json" ]; then
    cp -a "$HOME/.config/hgw/agy.routes.json" "$HOME/.config/clip/clip_agy.routes.json"
    say "migrated agy.routes.json -> clip_agy.routes.json"
  fi
fi

# 2. Migrate from legacy HGM config to Clip config
if [ -d "$HOME/.config/hgm" ]; then
  for name in aliases.tsv auto.disabled; do
    if [ -e "$HOME/.config/hgm/$name" ] && [ ! -e "$HOME/.config/clip/$name" ]; then
      cp -a "$HOME/.config/hgm/$name" "$HOME/.config/clip/$name"
      say "migrated $name from hgm"
    fi
  done
  if [ -e "$HOME/.config/hgm/hgb-g.env" ] && [ ! -e "$HOME/.config/clip/clip_gemini.env" ]; then
    cp -a "$HOME/.config/hgm/hgb-g.env" "$HOME/.config/clip/clip_gemini.env"
    sed -i 's/HGB_G_/CLIP_GEMINI_/g' "$HOME/.config/clip/clip_gemini.env" || true
    say "migrated hgb-g.env -> clip_gemini.env"
  fi
  if [ -e "$HOME/.config/hgm/hgb-a.env" ] && [ ! -e "$HOME/.config/clip/clip_agy.env" ]; then
    cp -a "$HOME/.config/hgm/hgb-a.env" "$HOME/.config/clip/clip_agy.env"
    sed -i 's/HGB_A_/CLIP_AGY_/g' "$HOME/.config/clip/clip_agy.env" || true
    say "migrated hgb-a.env -> clip_agy.env"
  fi
  if [ -e "$HOME/.config/hgm/hgb-g.routes.json" ] && [ ! -e "$HOME/.config/clip/clip_gemini.routes.json" ]; then
    cp -a "$HOME/.config/hgm/hgb-g.routes.json" "$HOME/.config/clip/clip_gemini.routes.json"
    say "migrated hgb-g.routes.json -> clip_gemini.routes.json"
  fi
  if [ -e "$HOME/.config/hgm/hgb-a.routes.json" ] && [ ! -e "$HOME/.config/clip/clip_agy.routes.json" ]; then
    cp -a "$HOME/.config/hgm/hgb-a.routes.json" "$HOME/.config/clip/clip_agy.routes.json"
    say "migrated hgb-a.routes.json -> clip_agy.routes.json"
  fi
fi

# Clean up legacy HGM binaries in ~/bin to prevent command conflicts
if [ -e "$HOME/bin/hgm" ]; then
  rm -f "$HOME/bin/hgm"
  say "removed legacy hgm executable from bin"
fi
if [ -e "$HOME/bin/hgb-g" ]; then
  rm -f "$HOME/bin/hgb-g"
  say "removed legacy hgb-g executable from bin"
fi
if [ -e "$HOME/bin/hgb-a" ]; then
  rm -f "$HOME/bin/hgb-a"
  say "removed legacy hgb-a executable from bin"
fi

say "-- post-install validation --"
python3 -m py_compile "$DEST_LIB"/*.py
python3 -m py_compile "$DEST_CLIP_LIB"/*.py
bash -n "$DEST_BIN"
bash -n "$DEST_CLIP"
bash -n "$DEST_AGY"

say "-- resolution --"
RESOLVED="$(command -v clip || true)"
say "command -v clip: ${RESOLVED:-not found}"
if [ -n "$RESOLVED" ] && [ "$RESOLVED" != "$DEST_CLIP" ]; then
  say "WARNING: PATH resolves clip to a different file:"
  say "  resolved: $RESOLVED"
  say "  installed: $DEST_CLIP"
fi

say ""
say "Installed successfully."
say "Backups: $BACKUP_DIR"
say "Run: clip"
