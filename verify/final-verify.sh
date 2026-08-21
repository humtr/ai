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
  if grep -rqE "$pat" "$@"; then
    ok "$desc"
  else
    fail "$desc"
  fi
}

grep_absent() {
  local desc="$1"
  local pat="$2"
  shift 2
  if grep --exclude-dir=__pycache__ --exclude=final-verify.sh -rqE "$pat" "$@"; then
    fail "$desc"
    grep --exclude-dir=__pycache__ --exclude=final-verify.sh -rnE "$pat" "$@" | sed -n '1,80p'
  else
    ok "$desc"
  fi
}

echo "============================================================"
echo " FINAL AI STACK VERIFY (Stage 6)"
echo "============================================================"
date

section "1. Required files"

exists_file "$ROOT/bin/ai"
exists_file "$ROOT/bin/agy"
exists_file "$ROOT/bin/clip"
exists_file "$ROOT/lib/ai_cli.py"
exists_file "$ROOT/lib/ai_spec.py"
exists_file "$ROOT/lib/ai_plan.py"
exists_file "$ROOT/lib/ai_resource.py"
exists_file "$ROOT/lib/ai_tui.py"
exists_file "$ROOT/lib/clip_gemini.py"
exists_file "$ROOT/lib/clip_agy.py"
exists_file "$ROOT/lib/clip_approve.py"
exists_file "$ROOT/lib/clip_web_fetch.py"

section "2. Syntax checks"

for f in ai agy clip; do
  if bash -n "$ROOT/bin/$f"; then
    ok "bash -n bin/$f"
  else
    fail "bash -n bin/$f"
  fi
done

if python3 -m py_compile "$ROOT/lib"/*.py; then
  ok "py_compile lib/*.py"
else
  fail "py_compile lib/*.py"
fi

section "3. ai structure and provider order checks"

AI_CLI="$ROOT/lib/ai_cli.py"
grep_ok "ai_cli has common command model" 'ai run <provider> --cwd DIR' "$AI_CLI"
grep_ok "ai_cli has tui command" 'def tui_cmd' "$AI_CLI"
grep_absent "ai_cli has no old wrapper commands" 'cmd=="gm"|cmd=="cm"|cmd=="hm"' "$AI_CLI"

PROVIDERS="$(PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/ai_cli.py" provider list | cut -f1 | tr '\n' ' ' | xargs)"
if [ "$PROVIDERS" = "codex agy hermes opencode" ]; then
  ok "provider order is strictly: codex agy hermes opencode"
else
  fail "provider order is: $PROVIDERS (expected: codex agy hermes opencode)"
fi

section "4. Independent clip proxy checks"

CLIP_HELP="$(bash "$ROOT/bin/clip" help 2>&1)"
echo "$CLIP_HELP" | grep -q 'clip = Command Line Interface Proxy Manager' && ok "clip help works" || fail "clip help works"
echo "$CLIP_HELP" | grep -q 'clip auto' && ok "clip auto command available" || fail "clip auto command available"

CLIP_STATUS="$(bash "$ROOT/bin/clip" auto status 2>&1)"
echo "$CLIP_STATUS" | grep -q 'clip auto-start:' && ok "clip auto status works" || fail "clip auto status works"

section "5. No deprecated paths or files"

grep_absent "no old proxy/cm/gm/hm in tests" 'ai cm|ai gm|ai hm|ai gateway|ai bridge' "$ROOT/tests" "$ROOT/verify"
grep_absent "no old accounts references in lib" 'accounts\.json|list_accounts|get_account' "$ROOT/lib"
grep_absent "no old resume references in lib" 'resume_command|ai resume' "$ROOT/lib"

section "6. Functional execution & dry-run checks"

echo "== ai provider list =="
PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/ai_cli.py" provider list
[ $? -eq 0 ] && ok "ai provider list" || fail "ai provider list"

echo "== ai session list =="
PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/ai_cli.py" session list | head -n 5
[ $? -eq 0 ] && ok "ai session list" || fail "ai session list"

echo "== dry run check: codex =="
OUT="$(AI_DRY_RUN=1 PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/ai_cli.py" run codex 2>&1)"
echo "$OUT" | grep -q 'codex' && ok "ai dry run codex" || fail "ai dry run codex"

echo "== dry run check: agy =="
OUT="$(AI_DRY_RUN=1 PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/ai_cli.py" run agy 2>&1)"
echo "$OUT" | grep -q 'agy' && ok "ai dry run agy" || fail "ai dry run agy"

echo "== dry run check: hermes =="
OUT="$(AI_DRY_RUN=1 PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/ai_cli.py" run hermes 2>&1)"
echo "$OUT" | grep -q 'hermes' && ok "ai dry run hermes" || fail "ai dry run hermes"

echo "== dry run check: opencode =="
OUT="$(AI_DRY_RUN=1 PYTHONPATH="$ROOT/lib" python3 "$ROOT/lib/ai_cli.py" run opencode 2>&1)"
echo "$OUT" | grep -q 'opencode' && ok "ai dry run opencode" || fail "ai dry run opencode"

section "7. TUI smoke checks"

if bash "$ROOT/verify/ai-tui-smoke.sh"; then
  ok "ai tui smoke"
else
  fail "ai tui smoke"
fi

section "8. Process check"

ps -A -o pid,ppid,etime,cmd 2>/dev/null \
  | grep -E '(/bin/ai|/usr/bin/codex|/usr/bin/hermes|/usr/bin/agy)' \
  | grep -vE 'grep'

RC=$?
if [ "$RC" -eq 0 ]; then
  warn "some ai-related processes are currently active"
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
