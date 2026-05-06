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
echo " FINAL AI STACK VERIFY"
echo "============================================================"
date

section "1. Required files"

exists_file "$HOME/bin/ai"
exists_file "$HOME/bin/gm"
exists_file "$HOME/bin/cm"
exists_file "$HOME/bin/hm"
exists_file "$HOME/bin/hgw"
exists_file "$HOME/bin/hgb"
exists_file "$HOME/.config/ai/lib/manager_cwd_policy.sh"
exists_file "$HOME/.config/ai/lib/ai_registry.py"
exists_file "$HOME/.config/ai/lib/ai_tui.py"
exists_file "$HOME/.config/hgw/lib/approve.py"

section "2. Syntax checks"

for f in ai gm cm hm hgw; do
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

if python -m py_compile "$HOME/.config/hgw/lib/approve.py"; then
  ok "py_compile approve.py"
else
  fail "py_compile approve.py"
fi

if python -m py_compile "$HOME/.config/ai/lib/ai_registry.py" "$HOME/.config/ai/lib/ai_tui.py"; then
  ok "py_compile ai helpers"
else
  fail "py_compile ai helpers"
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

grep_ok "ai has provider metadata" 'provider_mgr\(\)' "$AI"
grep_absent "ai has no unused provider default profile metadata" 'provider_default_profile\(\)' "$AI"
grep_ok "ai has provider prepare" 'provider_prepare\(\)' "$AI"
grep_ok "ai has provider prompt sandbox runner" 'provider_run_manager_sandbox\(\)' "$AI"
grep_ok "ai has provider prompt project runner" 'provider_run_manager_project\(\)' "$AI"
grep_ok "ai has common provider command model" 'common_provider_cmd\(\)' "$AI"
grep_ok "ai has provider native project runner" 'provider_native_project\(\)' "$AI"
grep_ok "ai has native passthrough" 'provider_native_passthrough\(\)' "$AI"
grep_ok "ai has tui command" 'tui_cmd\(\)' "$AI"
grep_ok "ai has registry command" 'registry_cmd\(\)' "$AI"
grep_ok "ai has native subcommand metadata" 'provider_native_subcommands\(\)' "$AI"
grep_ok "ai has sandbox native subcommand metadata" 'provider_sandbox_native_subcommands\(\)' "$AI"
grep_ok "ai has native subcommand checker" 'provider_is_native_subcommand\(\)' "$AI"
grep_ok "ai has sandbox native checker" 'provider_is_sandbox_native_subcommand\(\)' "$AI"
grep_ok "ai uses provider_native_passthrough in router" 'provider_native_passthrough "\$kind" "\$mgr" "\$@"' "$AI"
grep_ok "ai uses provider_exec_sandbox" 'provider_exec_sandbox "\$kind" "\$mgr" "\$sub" "\$profile"' "$AI"

grep_absent "ai has no old provider shim funcs" '\b(task_codex|task_gemini|task_hermes|chat_codex|chat_gemini|chat_hermes|plan_codex|plan_gemini|plan_hermes)\b' "$AI"
grep_absent "ai has no old subcommand helpers" '\bis_(codex|gemini|hermes)_subcommand\b' "$AI"
grep_absent "ai does not pass bash function to timeout" 'run_with_timeout provider_(run_sandbox_env|project_env)' "$AI"

section "4. gm/cm/hm shared cwd policy"

for f in gm cm hm; do
  FILE="$HOME/bin/$f"
  grep_ok "$f sources shared cwd policy" 'manager_cwd_policy\.sh' "$FILE"
  grep_ok "$f calls ai_mgr_maybe_cd" 'ai_mgr_maybe_cd' "$FILE"
done

grep_ok "shared lib defines ai_mgr_maybe_cd" 'ai_mgr_maybe_cd\(\)' "$HOME/.config/ai/lib/manager_cwd_policy.sh"

grep_ok "shared lib uses provider sandbox root" 'sb/codex|sb/gemini|sb/hermes' "$HOME/.config/ai/lib/manager_cwd_policy.sh"

section "5. gm throttle / prompt safety"

GM="$HOME/bin/gm"

grep_ok "gm has throttle default" 'GM_THROTTLE_SEC="\$\{GM_THROTTLE_SEC:-2\}"' "$GM"
grep_ok "gm has prompt runner" 'gm_run_gemini_prompt\(\)' "$GM"
grep_ok "gm has native runner" 'gm_run_gemini_native\(\)' "$GM"
grep_ok "gm prompt runner detaches stdin" 'gemini --skip-trust -p "\$prompt" < /dev/null' "$GM"
grep_ok "gm task guard prefix exists" 'gm_task_guard_prefix\(\)' "$GM"
grep_ok "gm task guard mentions fake tools" '존재하지 않는 도구명|실제로 제공된 도구' "$GM"

section "6. Dispatch semantics"

grep_ok "ai ask/chat -> chat_cmd" 'ask\|chat\) chat_cmd "\$@"' "$AI"
grep_ok "ai task -> task_cmd" 'task\) task_cmd "\$@"' "$AI"
grep_ok "ai plan -> plan_cmd" 'plan\) plan_cmd "\$@"' "$AI"

for f in gm cm hm; do
  FILE="$HOME/bin/$f"
  grep_ok "$f task -> task_profile" 'task\)[[:space:]]*$' "$FILE"
  grep_ok "$f ask/chat -> chat_profile" 'ask\|chat\)' "$FILE"
  grep_ok "$f plan -> plan_profile" 'plan\)' "$FILE"
done

grep_ok "cm has exec_profile" 'exec_profile\(\)' "$HOME/bin/cm"
grep_ok "cm exec -> exec_profile" 'exec\)[[:space:]]*$' "$HOME/bin/cm"
grep_ok "cm exec uses native codex exec" 'codex exec' "$HOME/bin/cm"

section "7. hgb / hgw / approve wiring"

grep_ok "hgb uses gm task" '\["gm", "task"' "$HOME/bin/hgb"
grep_ok "approve.py uses hm task" '\["hm", "task"' "$HOME/.config/hgw/lib/approve.py"

echo "== hgw bridge status =="
hgw bridge status
RC=$?
if [ "$RC" -eq 0 ]; then
  ok "hgw bridge status"
else
  warn "hgw bridge status rc=$RC"
fi

section "8. Help text checks"

for f in ai gm cm hm; do
  HELP="$("$HOME/bin/$f" help 2>&1)"
  echo "$HELP" | grep -q 'ask/chat' && ok "$f help mentions ask/chat" || fail "$f help mentions ask/chat"
  echo "$HELP" | grep -q 'task' && ok "$f help mentions task" || fail "$f help mentions task"
  echo "$HELP" | grep -q 'plan' && ok "$f help mentions plan" || fail "$f help mentions plan"
  echo "$HELP" | grep -q 'raw' && ok "$f help mentions raw" || fail "$f help mentions raw"
done

"$HOME/bin/gm" help 2>&1 | grep -q 'GM_THROTTLE_SEC=2' && ok "gm help mentions throttle" || fail "gm help mentions throttle"
"$HOME/bin/cm" help 2>&1 | grep -q 'exec' && ok "cm help mentions exec" || fail "cm help mentions exec"
"$HOME/bin/ai" help 2>&1 | grep -q 'Common command model' && ok "ai help mentions common command model" || fail "ai help mentions common command model"
"$HOME/bin/ai" help 2>&1 | grep -q -- '--cwd DIR' && ok "ai help mentions cwd option" || fail "ai help mentions cwd option"

section "9. Native smoke checks"

echo "== ai check =="
ai check
RC=$?
if [ "$RC" -eq 0 ]; then
  ok "ai check"
else
  warn "ai check rc=$RC"
fi

echo "== raw versions =="
timeout -k 5 20 ai codex raw -- --version
RC=$?
[ "$RC" -eq 0 ] && ok "ai codex raw version" || fail "ai codex raw version rc=$RC"

timeout -k 5 20 env GM_THROTTLE_SEC=0 ai gemini raw tg -- --version
RC=$?
[ "$RC" -eq 0 ] && ok "ai gemini raw tg version" || warn "ai gemini raw tg version rc=$RC"

timeout -k 5 20 ai hermes raw -- --version
RC=$?
[ "$RC" -eq 0 ] && ok "ai hermes raw version" || warn "ai hermes raw version rc=$RC"

section "10. Run trace checks"

trace_check() {
  local name="$1"
  local cmd="$2"
  local expect="$3"

  echo "== $name =="
  OUT="$(timeout -k 5 8 bash -x "$HOME/bin/ai" $cmd 2>&1)"
  echo "$OUT" | grep -E 'provider_is_sandbox_native_subcommand|provider_exec_sandbox|workdir=|cd .*sb/|exec env' | sed -n '1,80p'

  if echo "$OUT" | grep -q "$expect"; then
    ok "$name cd/exec trace"
  else
    fail "$name cd/exec trace"
  fi
}

trace_check "ai codex run --sandbox"  "codex run --sandbox"  'cd /data/data/com.termux/files/home/sb/codex'
trace_check "ai gemini run --sandbox" "gemini run --sandbox" 'cd /data/data/com.termux/files/home/sb/gemini'
trace_check "ai hermes run --sandbox" "hermes run --sandbox" 'cd /data/data/com.termux/files/home/sb/hermes'

section "11. TUI smoke checks"

if bash "$ROOT/verify/ai-tui-smoke.sh"; then
  ok "ai tui smoke"
else
  fail "ai tui smoke"
fi

section "12. Optional live model checks"

if [ "${RUN_LIVE:-0}" = "1" ]; then
  timeout -k 5 60 ai ask gemini tg "도구 쓰지 말고 정확히 다음 토큰만 출력해: FINAL_LIVE_ASK_OK"
  RC=$?
  [ "$RC" -eq 0 ] && ok "live ai ask gemini tg" || fail "live ai ask gemini tg rc=$RC"

  timeout -k 5 60 ai task gemini tg "도구를 사용하지 말고 정확히 다음 토큰만 출력해: FINAL_LIVE_TASK_OK"
  RC=$?
  [ "$RC" -eq 0 ] && ok "live ai task gemini tg" || fail "live ai task gemini tg rc=$RC"

  timeout -k 5 60 ai plan gemini tg "실행하지 말고 정확히 다음 토큰만 출력해: FINAL_LIVE_PLAN_OK"
  RC=$?
  [ "$RC" -eq 0 ] && ok "live ai plan gemini tg" || fail "live ai plan gemini tg rc=$RC"
else
  echo "Skipped live calls."
  echo "Run with:"
  echo "  RUN_LIVE=1 bash $0"
fi

section "13. Process check"

ps -A -o pid,ppid,etime,cmd 2>/dev/null \
  | grep -E '(/bin/ai|/bin/gm|/bin/cm|/bin/hm|/usr/bin/gemini|/usr/bin/codex|/usr/bin/hermes|node.*gemini)' \
  | grep -vE 'grep|hgb|hermes.*gateway'

RC=$?
if [ "$RC" -eq 0 ]; then
  warn "some ai/cm/gm/hm-related processes are still running"
else
  ok "no stuck ai/cm/gm/hm process"
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
