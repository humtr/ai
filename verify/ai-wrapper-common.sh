#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
AI="$ROOT/bin/ai"
LIVE_AI="${AI_LIVE:-$HOME/bin/ai}"
TMP_BASE="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/ai-wrapper-test-$$"
HOME_FIXTURE="$TMP_BASE/home"
BIN_FIXTURE="$TMP_BASE/bin"
TRACE="$TMP_BASE/trace.log"
PASS=0
FAIL=0

cleanup() {
  rm -rf "$TMP_BASE"
}
trap cleanup EXIT

ok() {
  PASS=$((PASS + 1))
  printf 'ok: %s\n' "$*"
}

fail() {
  FAIL=$((FAIL + 1))
  printf 'FAIL: %s\n' "$*" >&2
}

assert_contains() {
  local desc="$1"
  local needle="$2"
  local file="$3"

  if grep -Fq -- "$needle" "$file"; then
    ok "$desc"
  else
    fail "$desc"
    printf 'wanted: %s\n' "$needle" >&2
    printf 'actual:\n' >&2
    sed -n '1,120p' "$file" >&2
  fi
}

assert_output_contains() {
  local desc="$1"
  local needle="$2"
  local output="$3"

  if printf '%s' "$output" | grep -Fq -- "$needle"; then
    ok "$desc"
  else
    fail "$desc"
    printf 'wanted: %s\n' "$needle" >&2
    printf 'actual:\n%s\n' "$output" >&2
  fi
}

assert_occurs() {
  local desc="$1"
  local needle="$2"
  local expected="$3"
  local file="$4"
  local actual

  actual="$(grep -Fc -- "$needle" "$file" 2>/dev/null || true)"
  if [ "$actual" = "$expected" ]; then
    ok "$desc"
  else
    fail "$desc"
    printf 'wanted %s occurrence(s) of: %s\n' "$expected" "$needle" >&2
    printf 'actual %s occurrence(s):\n' "$actual" >&2
    sed -n '1,120p' "$file" >&2
  fi
}

assert_files_equal() {
  local desc="$1"
  local left="$2"
  local right="$3"

  if cmp -s "$left" "$right"; then
    ok "$desc"
  else
    fail "$desc"
    printf 'left:  %s\n' "$left" >&2
    printf 'right: %s\n' "$right" >&2
  fi
}

write_stub() {
  local name="$1"
  local path="$BIN_FIXTURE/$name"

  cat > "$path" <<'STUB'
#!/usr/bin/env bash
{
  printf 'cmd=%s\n' "$(basename "$0")"
  printf 'pwd=%s\n' "$PWD"
  printf 'args='
  for arg in "$@"; do
    printf '<%s>' "$arg"
  done
  printf '\n'
  printf 'CODEX_HOME=%s\n' "${CODEX_HOME:-}"
  printf 'GM_CWD_NONTTY_POLICY=%s\n' "${GM_CWD_NONTTY_POLICY:-}"
  printf 'HM_CWD_NONTTY_POLICY=%s\n' "${HM_CWD_NONTTY_POLICY:-}"
  printf 'CM_CWD_NONTTY_POLICY=%s\n' "${CM_CWD_NONTTY_POLICY:-}"
  printf 'GEMINI_CLI_TRUST_WORKSPACE=%s\n' "${GEMINI_CLI_TRUST_WORKSPACE:-}"
} >> "$AI_TRACE"
exit 0
STUB
  chmod +x "$path"
}

run_ai() {
  : > "$TRACE"
  HOME="$HOME_FIXTURE" \
    PATH="$BIN_FIXTURE:$PATH" \
    AI_TRACE="$TRACE" \
    AI_DEFAULT_PROVIDER=gemini \
    AI_CODEX_PROFILE=default \
    AI_GEMINI_PROFILE=default \
    AI_HERMES_PROFILE=default \
    bash "$AI" "$@"
}

run_ai_expect_fail() {
  : > "$TRACE"
  HOME="$HOME_FIXTURE" \
    PATH="$BIN_FIXTURE:$PATH" \
    AI_TRACE="$TRACE" \
    AI_DEFAULT_PROVIDER=gemini \
    AI_CODEX_PROFILE=default \
    AI_GEMINI_PROFILE=default \
    AI_HERMES_PROFILE=default \
    bash "$AI" "$@"
}

run_ai_missing_codex_profile() {
  : > "$TRACE"
  mkdir -p "$HOME_FIXTURE/.config/ai"
  printf 'AI_CODEX_PROFILE="missing"\n' > "$HOME_FIXTURE/.config/ai/config.env"
  HOME="$HOME_FIXTURE" \
    PATH="$BIN_FIXTURE:$PATH" \
    AI_TRACE="$TRACE" \
    AI_DEFAULT_PROVIDER=gemini \
    AI_CODEX_PROFILE=default \
    AI_GEMINI_PROFILE=default \
    AI_HERMES_PROFILE=default \
    bash "$AI" "$@"
  local rc=$?
  rm -f "$HOME_FIXTURE/.config/ai/config.env"
  return "$rc"
}

mkdir -p \
  "$BIN_FIXTURE" \
  "$HOME_FIXTURE/.codex/sessions/2026/05/04" \
  "$HOME_FIXTURE/.gemini" \
  "$HOME_FIXTURE/.hermes" \
  "$HOME_FIXTURE/.codex-homes/main/sessions/2026/05/04" \
  "$HOME_FIXTURE/.gemini-homes/main" \
  "$HOME_FIXTURE/.hermes/profiles/main" \
  "$HOME_FIXTURE/prj/photos" \
  "$HOME_FIXTURE/sb/codex" \
  "$HOME_FIXTURE/sb/gemini" \
  "$HOME_FIXTURE/sb/hermes"

touch "$HOME_FIXTURE/.codex-homes/main/sessions/2026/05/04/rollout-2026-05-04T00-00-00-abc123.jsonl"
touch "$HOME_FIXTURE/.codex/sessions/2026/05/04/rollout-2026-05-04T00-00-00-native999.jsonl"

for cmd in cm gm hm codex gemini hermes hgw hgb; do
  write_stub "$cmd"
done

if bash -n "$AI"; then
  ok "ai syntax"
else
  fail "ai syntax"
fi

if bash -n "$LIVE_AI"; then
  ok "live ai syntax"
else
  fail "live ai syntax"
fi

assert_files_equal "repo bin/ai matches live ~/bin/ai" "$AI" "$LIVE_AI"

HELP="$(HOME="$HOME_FIXTURE" PATH="$BIN_FIXTURE:$PATH" bash "$AI" help)"
assert_output_contains "help documents common command model" "Common command model:" "$HELP"
assert_output_contains "help documents cwd option" "--cwd DIR, --cd DIR, -C DIR" "$HELP"
assert_output_contains "help documents native default account" "default/native uses the provider's original install environment" "$HELP"

run_ai run gemini --account default --cwd '~/prj/photos' -- --version
assert_contains "gemini default uses native binary" "cmd=gemini" "$TRACE"
assert_contains "gemini default keeps project cwd" "pwd=$HOME_FIXTURE/prj/photos" "$TRACE"
assert_contains "gemini default passes native args" "args=<--version>" "$TRACE"

run_ai run codex --account default --cwd '~/prj/photos' -- --version
assert_contains "codex default calls native codex with -C" "args=<-C><$HOME_FIXTURE/prj/photos><--version>" "$TRACE"
assert_contains "codex default leaves CODEX_HOME unset" "CODEX_HOME=" "$TRACE"

run_ai run hermes --account default --cwd '~/prj/photos' -- --version
assert_contains "hermes default uses native binary" "cmd=hermes" "$TRACE"
assert_contains "hermes default keeps project cwd" "pwd=$HOME_FIXTURE/prj/photos" "$TRACE"

run_ai task gemini --profile main --cwd '~/prj/photos' "hello"
assert_contains "gemini task uses project cwd" "pwd=$HOME_FIXTURE/prj/photos" "$TRACE"
assert_contains "gemini task translates to manager task" "args=<task><main><hello>" "$TRACE"
assert_contains "gemini task forces cwd policy" "GM_CWD_NONTTY_POLICY=cwd" "$TRACE"

run_ai task --provider gemini --home main -C '~/prj/photos' "hello"
assert_contains "provider option and home alias work" "args=<task><main><hello>" "$TRACE"
assert_contains "short cwd option works" "pwd=$HOME_FIXTURE/prj/photos" "$TRACE"

run_ai task gemini --profile main --sandbox "hello"
assert_contains "gemini task sandbox override" "pwd=$HOME_FIXTURE/sb/gemini" "$TRACE"

run_ai run gemini --profile main --cwd '~/prj/photos' -- --version
assert_contains "gemini run translates to raw passthrough" "args=<raw><main><--><--version>" "$TRACE"
assert_contains "gemini run keeps project cwd" "pwd=$HOME_FIXTURE/prj/photos" "$TRACE"

run_ai list gemini --profile main --cwd '~/prj/photos'
assert_contains "gemini list translates to --list-sessions" "args=<raw><main><--><--list-sessions>" "$TRACE"

run_ai resume gemini --profile main --cwd '~/prj/photos' latest
assert_contains "gemini resume translates latest" "args=<raw><main><--><--resume><latest>" "$TRACE"

run_ai run --provider gemini --profile main --cwd '~/prj/photos' -- --version
assert_contains "common run accepts --provider" "args=<raw><main><--><--version>" "$TRACE"

run_ai run codex --profile main --cwd '~/prj/photos' -- --version
assert_contains "codex run calls native codex with -C" "args=<-C><$HOME_FIXTURE/prj/photos><--version>" "$TRACE"
assert_contains "codex run sets CODEX_HOME" "CODEX_HOME=$HOME_FIXTURE/.codex-homes/main" "$TRACE"

if run_ai_missing_codex_profile codex raw -- --version > "$TMP_BASE/missing.out" 2>&1; then
  fail "codex raw reports missing default profile"
else
  assert_contains "codex raw missing profile reports hint" "Codex profile not found or not ready: missing" "$TMP_BASE/missing.out"
  assert_occurs "codex raw missing profile does not re-enter task fallback" "Codex profile not found or not ready: missing" 1 "$TMP_BASE/missing.out"
fi

run_ai resume codex --profile main --cwd '~/prj/photos' latest
assert_contains "codex resume latest translates to --last" "args=<-C><$HOME_FIXTURE/prj/photos><resume><--last>" "$TRACE"

run_ai resume --provider codex --profile main --cwd '~/prj/photos' --session abc123
assert_contains "common resume accepts --session" "args=<-C><$HOME_FIXTURE/prj/photos><resume><abc123>" "$TRACE"

CODEX_LIST="$(run_ai list codex --profile main --cwd '~/prj/photos')"
assert_output_contains "codex list shows fixture session" "abc123" "$CODEX_LIST"

run_ai run hermes --profile main --cwd '~/prj/photos' -- --version
assert_contains "hermes run translates to raw passthrough" "args=<raw><main><--><--version>" "$TRACE"
assert_contains "hermes run keeps project cwd" "pwd=$HOME_FIXTURE/prj/photos" "$TRACE"

run_ai list hermes --profile main --cwd '~/prj/photos'
assert_contains "hermes list translates sessions list" "args=<raw><main><--><sessions><list><--limit><40>" "$TRACE"

run_ai resume hermes --profile main --cwd '~/prj/photos' latest
assert_contains "hermes resume latest translates to continue" "args=<raw><main><--><--continue>" "$TRACE"

run_ai browse hermes --profile main --cwd '~/prj/photos'
assert_contains "hermes browse translates to sessions browse" "args=<raw><main><--><sessions><browse>" "$TRACE"

if run_ai_expect_fail browse gemini --profile main --cwd '~/prj/photos' > "$TMP_BASE/browse.out" 2>&1; then
  fail "gemini browse reports unsupported"
else
  assert_contains "gemini browse gives safe fallback" "Use: ai list gemini --cwd DIR" "$TMP_BASE/browse.out"
fi

printf '\nPASS=%s FAIL=%s\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
