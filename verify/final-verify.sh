#!/usr/bin/env bash
set +e

PASS=0
FAIL=0
WARN=0
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

ok() {
  PASS=$((PASS + 1))
  echo "✅ $*"
}

fail() {
  FAIL=$((FAIL + 1))
  echo "❌ $*"
}

warn() {
  WARN=$((WARN + 1))
  echo "⚠️ $*"
}

section() {
  echo
  echo "============================================================"
  echo " $*"
  echo "============================================================"
}

exists_file() {
  local f="$1"
  if [ -e "$f" ]; then
    ok "exists: $f"
    ls -lh "$f"
  else
    fail "missing: $f"
  fi
}

grep_ok() {
  local desc="$1"
  local pat="$2"
  shift 2
  if grep -qE "$pat" "$@"; then
    ok "$desc"
  else
    fail "$desc"
  fi
}

grep_absent() {
  local desc="$1"
  local pat="$2"
  shift 2
  if grep -qE "$pat" "$@"; then
    fail "$desc"
    grep -nE "$pat" "$@" | sed -n '1,80p'
  else
    ok "$desc"
  fi
}

echo "============================================================"
echo " FINAL AI STACK VERIFY (Stage 6)"
echo "============================================================"
date

section "1. Required files"

exists_file "$HOME/bin/ai"
exists_file "$HOME/bin/hgm"
exists_file "$HOME/bin/hgb"
exists_file "$HOME/.config/ai/lib/ai_cli.py"
exists_file "$HOME/.config/ai/lib/ai_spec.py"
exists_file "$HOME/.config/ai/lib/ai_plan.py"
exists_file "$HOME/.config/ai/lib/ai_resource.py"
exists_file "$HOME/.config/ai/lib/ai_tui.py"
exists_file "$HOME/.config/hgm/lib/approve.py"
exists_file "$HOME/.config/hgm/lib/web_fetch.py"

section "2. Syntax checks"

for f in ai hgm; do
  if bash -n "$HOME/bin/$f"; then
    ok "bash -n $f"
  else
    fail "bash -n $f"
  fi
done

if python -m py_compile "$HOME/bin/hgb"; then
  ok "py_compile hgb"
else
  fail "py_compile hgb"
fi

if python -m py_compile "$HOME/.config/hgm/lib/approve.py" "$HOME/.config/hgm/lib/web_fetch.py"; then
  ok "py_compile hgm helpers"
else
  fail "py_compile hgm helpers"
fi

if python -m py_compile "$HOME/.config/ai/lib"/*.py; then
  ok "py_compile ai lib"
else
  fail "py_compile ai lib"
fi

section "3. ai structure checks"

AI="$HOME/bin/ai"
REPO_AI="$HOME/prj/ai/bin/ai"

if [ -f "$REPO_AI" ]; then
  if cmp -s "$AI" "$REPO_AI"; then
    ok "live ~/bin/ai matches repo bin/ai"
  else
    fail "live ~/bin/ai matches repo bin/ai"
  fi
else
  warn "repo bin/ai not found: $REPO_AI"
fi

AI_CLI="$HOME/.config/ai/lib/ai_cli.py"
grep_ok "ai_cli has common command model" 'ai run <provider> --cwd DIR' "$AI_CLI"
grep_ok "ai_cli has resource commands" 'if cmd=="bridge":|if cmd=="gateway":|if cmd=="gw":' "$AI_CLI"
grep_ok "ai_cli has tui command" 'def tui_cmd' "$AI_CLI"
grep_absent "ai_cli has no old wrapper commands" 'cmd=="gm"|cmd=="cm"|cmd=="hm"' "$AI_CLI"

section "4. Resource wiring"

grep_ok "hgb uses ai_plan" 'ai_plan' "$HOME/bin/hgb"
grep_ok "approve.py uses hgm" 'hgm approve' "$HOME/.config/hgm/lib/approve.py"

echo "== hgm status =="
hgm status
RC=$?
if [ "$RC" -eq 0 ]; then
  ok "hgm status"
else
  warn "hgm status rc=$RC"
fi

echo "== ai bridge status =="
ai bridge status
RC=$?
if [ "$RC" -eq 0 ]; then
  ok "ai bridge status"
else
  warn "ai bridge status rc=$RC"
fi

section "5. Help text checks"

HELP="$(ai help 2>&1)"
echo "$HELP" | grep -q 'run <provider>' && ok "ai help mentions run" || fail "ai help mentions run"
echo "$HELP" | grep -q 'ask <provider>' && ok "ai help mentions ask" || fail "ai help mentions ask"
echo "$HELP" | grep -q 'chat <provider>' && ok "ai help mentions chat" || fail "ai help mentions chat"
echo "$HELP" | grep -q 'raw <provider>' && ok "ai help mentions raw" || fail "ai help mentions raw"
echo "$HELP" | grep -q 'ai bridge' && ok "ai help mentions bridge" || fail "ai help mentions bridge"
echo "$HELP" | grep -q 'ai gateway' && ok "ai help mentions gateway" || fail "ai help mentions gateway"
echo "$HELP" | grep -q 'ai gw' && ok "ai help mentions gw" || fail "ai help mentions gw"
echo "$HELP" | grep -q 'ai tui' && ok "ai help mentions tui" || fail "ai help mentions tui"

section "6. Smoke checks"

echo "== ai provider list =="
ai provider list
[ $? -eq 0 ] && ok "ai provider list" || fail "ai provider list"

echo "== ai session list =="
ai session list | head -n 5
[ $? -eq 0 ] && ok "ai session list" || fail "ai session list"

echo "== dry run check =="
OUT="$(AI_DRY_RUN=1 ai run codex 2>&1)"
echo "$OUT" | grep -q 'codex' && ok "ai dry run codex" || fail "ai dry run codex"

section "7. TUI smoke checks"

if bash "$ROOT/verify/ai-tui-smoke.sh"; then
  ok "ai tui smoke"
else
  fail "ai tui smoke"
fi

section "8. Optional live model checks"

if [ "${RUN_LIVE:-0}" = "1" ]; then
  timeout -k 5 60 ai ask gemini -p tg -- "정확히 다음 토큰만 출력해: FINAL_LIVE_ASK_OK"
  RC=$?
  [ "$RC" -eq 0 ] && ok "live ai ask gemini" || fail "live ai ask gemini rc=$RC"
else
  echo "Skipped live calls."
fi

section "9. Process check"

ps -A -o pid,ppid,etime,cmd 2>/dev/null \
  | grep -E '(/bin/ai|/bin/hgm|/bin/hgb|/usr/bin/gemini|/usr/bin/codex|/usr/bin/hermes|node.*gemini)' \
  | grep -vE 'grep'

RC=$?
if [ "$RC" -eq 0 ]; then
  warn "some ai-related processes are still running"
else
  ok "no stuck ai process"
fi

section "SUMMARY"

echo "pass=$PASS"
echo "warn=$WARN"
echo "fail=$FAIL"

if [ "$FAIL" -eq 0 ]; then
  echo
  echo "✅ FINAL VERIFY PASSED with $WARN warning(s)"
  exit 0
else
  echo
  echo "❌ FINAL VERIFY FAILED with $FAIL failure(s), $WARN warning(s)"
  exit 1
fi
