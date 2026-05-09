# Compatibility shim for older bin/ai entrypoints. Prefer bin/ai -> ai_cli.py.
ai_cli() {
  local lib="${AI_LIB_DIR:-${HOME}/.config/ai/lib}"
  python "$lib/ai_cli.py" "$@"
}
ai_main() { ai_cli "$@"; }
ai_main "$@"
