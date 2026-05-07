#!/usr/bin/env bash
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TUI="$ROOT/code/ai-lib/ai_tui.py"
WKD_INTENT="$ROOT/code/ai-lib/wkd_key_intent.py"
TMP_BASE="${TMPDIR:-/data/data/com.termux/files/usr/tmp}/ai-tui-smoke-$$"
HOME_FIXTURE="$TMP_BASE/home"
BIN_FIXTURE="$TMP_BASE/bin"
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

assert_not_contains() {
  local desc="$1"
  local needle="$2"
  local file="$3"

  if grep -Fq -- "$needle" "$file"; then
    fail "$desc"
    printf 'unexpected: %s\n' "$needle" >&2
    printf 'actual:\n' >&2
    sed -n '1,120p' "$file" >&2
  else
    ok "$desc"
  fi
}

run_tui() {
  local keys="$1"
  local out="$2"
  local cols="${3:-160}"
  local rows="${4:-40}"
  local cmd

  cmd="cd $HOME_FIXTURE/work/main; stty cols $cols rows $rows; HOME=$HOME_FIXTURE AI_HOME=$HOME_FIXTURE/.ai PYTHONPATH=$ROOT/code/ai-lib AI_BIN=$BIN_FIXTURE/ai AI_TUI_DRY_RUN=1 python3 $TUI"
  printf '%b' "$keys" \
    | HOME="$HOME_FIXTURE" \
      TERM=xterm \
      script -q "$out" -c "$cmd" \
      >/dev/null 2>&1
}

mkdir -p \
  "$BIN_FIXTURE" \
  "$HOME_FIXTURE/.ai" \
  "$HOME_FIXTURE/.codex/sessions/2026/05/05" \
  "$HOME_FIXTURE/.codex-profiles/team-alpha" \
  "$HOME_FIXTURE/.codex-profiles/very-long-profile-name-for-horizontal-viewport" \
  "$HOME_FIXTURE/.gemini-profiles/team-alpha" \
  "$HOME_FIXTURE/aaa" \
  "$HOME_FIXTURE/work/a" \
  "$HOME_FIXTURE/work/ai-stack" \
  "$HOME_FIXTURE/work/main" \
  "$HOME_FIXTURE/work/main/.hidden" \
  "$HOME_FIXTURE/work/main/src" \
  "$HOME_FIXTURE/work/main/src/pkg" \
  "$HOME_FIXTURE/work/main/tests" \
  "$HOME_FIXTURE/work/other" \
  "$HOME_FIXTURE/work/work00" \
  "$HOME_FIXTURE/work/work01" \
  "$HOME_FIXTURE/work/work02" \
  "$HOME_FIXTURE/work/work03" \
  "$HOME_FIXTURE/work/work04" \
  "$HOME_FIXTURE/work/work05" \
  "$HOME_FIXTURE/work/work06" \
  "$HOME_FIXTURE/work/work07" \
  "$HOME_FIXTURE/work/work08" \
  "$HOME_FIXTURE/work/work09"

cat > "$BIN_FIXTURE/ai" <<'STUB'
#!/usr/bin/env bash
printf 'stub ai %s\n' "$*"
STUB
chmod +x "$BIN_FIXTURE/ai"

cat > "$HOME_FIXTURE/.ai/workdirs.json" <<JSON
{
  "version": 1,
  "workdirs": [
    {
      "name": "main",
      "path": "$HOME_FIXTURE/work/main",
      "purpose": "fixture main workdir",
      "favorite": true,
      "archived": false
    },
    {
      "name": "other",
      "path": "$HOME_FIXTURE/work/other",
      "purpose": "fixture other workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work00",
      "path": "$HOME_FIXTURE/work/work00",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work01",
      "path": "$HOME_FIXTURE/work/work01",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work02",
      "path": "$HOME_FIXTURE/work/work02",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work03",
      "path": "$HOME_FIXTURE/work/work03",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work04",
      "path": "$HOME_FIXTURE/work/work04",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work05",
      "path": "$HOME_FIXTURE/work/work05",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work06",
      "path": "$HOME_FIXTURE/work/work06",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work07",
      "path": "$HOME_FIXTURE/work/work07",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work08",
      "path": "$HOME_FIXTURE/work/work08",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    },
    {
      "name": "work09",
      "path": "$HOME_FIXTURE/work/work09",
      "purpose": "fixture scroll workdir",
      "favorite": false,
      "archived": false
    }
  ]
}
JSON

SESSION_FILE_ONE="$HOME_FIXTURE/.codex/sessions/2026/05/05/rollout-2026-05-05T00-00-00-smoke111.jsonl"
cat > "$SESSION_FILE_ONE" <<JSONL
{"timestamp":"2026-05-05T00:00:00Z","type":"session_meta","payload":{"id":"smoke-session","cwd":"$HOME_FIXTURE/work/main"}}
{"timestamp":"2026-05-05T00:00:01Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"smoke prompt summary one for tui preview"}]}}
{"timestamp":"2026-05-05T00:00:02Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"smoke answer summary one for tui preview"}]}}
JSONL
touch -t 202605050000 "$SESSION_FILE_ONE"

SESSION_FILE_TWO="$HOME_FIXTURE/.codex/sessions/2026/05/05/rollout-2026-05-05T00-01-00-smoke222.jsonl"
cat > "$SESSION_FILE_TWO" <<JSONL
{"timestamp":"2026-05-05T00:01:00Z","type":"session_meta","payload":{"id":"smoke-session-two","cwd":"$HOME_FIXTURE/work/main"}}
{"timestamp":"2026-05-05T00:01:01Z","type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"smoke prompt summary two for tui preview"}]}}
{"timestamp":"2026-05-05T00:01:02Z","type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"smoke answer summary two for tui preview"}]}}
JSONL
touch -t 202605050001 "$SESSION_FILE_TWO"

if python3 -m py_compile "$TUI" "$ROOT/code/ai-lib/ai_registry.py" "$WKD_INTENT"; then
  ok "tui python syntax"
else
  fail "tui python syntax"
fi

INTENT_JSON="$TMP_BASE/wkd-intent.json"
if HOME="$HOME_FIXTURE" AI_HOME="$HOME_FIXTURE/.ai" PYTHONPATH="$ROOT/code/ai-lib" python3 "$WKD_INTENT" --self-test "$INTENT_JSON"; then
  assert_contains "wkd intent self-test writes recorder payload" '"app": "ai wkd-intent"' "$INTENT_JSON"
  assert_contains "wkd intent self-test preserves wanted memo" '"wanted": "fixture wanted behavior"' "$INTENT_JSON"
else
  fail "wkd intent self-test"
fi

INTENT_RUN_JSON="$TMP_BASE/wkd-intent-run.json"
INTENT_RUN_OUT="$TMP_BASE/wkd-intent-run.out"
INTENT_CMD="cd $HOME_FIXTURE/work/main; stty -ixon cols 160 rows 40; HOME=$HOME_FIXTURE AI_HOME=$HOME_FIXTURE/.ai PYTHONPATH=$ROOT/code/ai-lib AI_BIN=$BIN_FIXTURE/ai python3 $WKD_INTENT --run-loop-self-test $INTENT_RUN_JSON"
HOME="$HOME_FIXTURE" TERM=xterm script -q "$INTENT_RUN_OUT" -c "$INTENT_CMD" >/dev/null 2>&1
if [ -f "$INTENT_RUN_JSON" ]; then
  assert_contains "wkd intent run loop records typed key" '"name": "w"' "$INTENT_RUN_JSON"
  assert_contains "wkd intent run loop records typed memo" '"wanted": "wanted live behavior' "$INTENT_RUN_JSON"
  assert_contains "wkd intent run loop records enter skip" '"wanted_skipped": true' "$INTENT_RUN_JSON"
  assert_contains "wkd intent run loop records before snapshot" '"before": {' "$INTENT_RUN_JSON"
  assert_contains "wkd intent run loop records after snapshot" '"after": {' "$INTENT_RUN_JSON"
  assert_contains "wkd intent run loop records actual behavior" '"actual":' "$INTENT_RUN_JSON"
else
  fail "wkd intent run loop writes ctrl-s output"
fi

MAIN_OUT="$TMP_BASE/main.out"
run_tui "\033\033" "$MAIN_OUT"
assert_contains "main shows default run command" "ai run codex" "$MAIN_OUT"
assert_not_contains "main omits default profile arg" "--profile default" "$MAIN_OUT"
assert_contains "main shows command builder" "Command builder" "$MAIN_OUT"
assert_contains "main shows mode row" "Mode" "$MAIN_OUT"
assert_contains "main shows provider row" "Provider" "$MAIN_OUT"
assert_contains "main shows profile row" "Profile" "$MAIN_OUT"
assert_contains "main shows workdir row" "Workdir" "$MAIN_OUT"
assert_contains "main shows profile split" "Profile default" "$MAIN_OUT"
assert_not_contains "main has no account row" "Account" "$MAIN_OUT"
assert_contains "main shows all mode choices without shifting window" "task   ask" "$MAIN_OUT"
assert_contains "main shows all provider choices without shifting window" "Gemini   Hermes" "$MAIN_OUT"
assert_contains "main shows sessions panel" "Sessions: Codex/default" "$MAIN_OUT"
assert_contains "main shows new session row" "New session" "$MAIN_OUT"
assert_contains "main shows last session row" "Last session" "$MAIN_OUT"
assert_contains "main still shows session preview rows" "smoke prompt summary" "$MAIN_OUT"
assert_contains "main documents panel tab navigation" "Tab cycles builder" "$MAIN_OUT"
assert_contains "main documents cwd editor key" "/ edits cwd" "$MAIN_OUT"
assert_contains "main documents esc quit" "Esc back/confirm quit" "$MAIN_OUT"

NARROW_OUT="$TMP_BASE/narrow.out"
run_tui "\033\033" "$NARROW_OUT" 80 24
assert_contains "narrow screen shows command builder" "Command builder" "$NARROW_OUT"
assert_contains "narrow screen shows workdir row" "Workdir" "$NARROW_OUT"
assert_contains "narrow screen keeps sessions visible" "Sessions: Codex/default" "$NARROW_OUT"

TAB_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; app.message=""; app.handle_main_key(9); print(app.section)'
)"
[ "$TAB_OUT" = "1" ] && ok "tab advances to next builder row" || { fail "tab advances to next builder row"; printf 'actual: %s\n' "$TAB_OUT" >&2; }

BTAB_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; app.last_builder_section=0; app.handle_main_key(curses.KEY_BTAB); print(app.section)'
)"
[ "$BTAB_OUT" = "0" ] && ok "shift-tab stays at first builder row" || { fail "shift-tab stays at first builder row"; printf 'actual: %s\n' "$BTAB_OUT" >&2; }

DOWN_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; app.last_builder_section=0; app.indices={"mode":0,"provider":0,"profile":0,"workdir":0}; app.profiles=["default"]; app.handle_main_key(curses.KEY_DOWN); print("{} {}".format(app.section, app.current_mode()))'
)"
[ "$DOWN_OUT" = "1 run" ] && ok "down arrow moves to provider row" || { fail "down arrow moves to provider row"; printf 'actual: %s\n' "$DOWN_OUT" >&2; }

UP_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=2; app.last_builder_section=2; app.indices={"mode":0,"provider":0,"profile":0,"workdir":0}; app.profiles=["default"]; app.handle_main_key(curses.KEY_UP); print(app.section)'
)"
[ "$UP_OUT" = "1" ] && ok "up arrow moves to provider row" || { fail "up arrow moves to provider row"; printf 'actual: %s\n' "$UP_OUT" >&2; }

SESSION_UP_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("sessions"); app.session_index=1; app.session_scroll=0; app.current_sessions=lambda:[{},{}]; app.handle_main_key(curses.KEY_UP); print("{} {}".format(app.section, app.session_index))'
)"
[ "$SESSION_UP_OUT" = "4 0" ] && ok "up arrow stays inside sessions panel" || { fail "up arrow stays inside sessions panel"; printf 'actual: %s\n' "$SESSION_UP_OUT" >&2; }

ENTER_SESSIONS_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; app.last_builder_section=0; app.session_index=-1; app.session_scroll=0; app.current_sessions=lambda:[{"session_id":"s"}]; app.handle_main_key(10); print("{} {}".format(app.section, app.session_index))'
)"
[ "$ENTER_SESSIONS_OUT" = "4 0" ] && ok "enter from builder opens sessions with last selected" || { fail "enter from builder opens sessions with last selected"; printf 'actual: %s\n' "$ENTER_SESSIONS_OUT" >&2; }

ESC_SESSIONS_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("sessions"); app.last_builder_section=2; app.session_index=0; app.session_scroll=0; app.handle_main_key(27); print("{} {}".format(app.section, getattr(app, "pending_action", None)))'
)"
[ "$ESC_SESSIONS_OUT" = "2 None" ] && ok "esc from sessions returns to builder without quitting" || { fail "esc from sessions returns to builder without quitting"; printf 'actual: %s\n' "$ESC_SESSIONS_OUT" >&2; }

RIGHT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; app.indices={"mode":0,"provider":0,"profile":0,"workdir":0}; app.profiles=["default"]; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_RIGHT); print("{} {} {}".format(app.section, app.indices["mode"], app.current_mode()))'
)"
[ "$RIGHT_OUT" = "0 1 task" ] && ok "right arrow changes current row value" || { fail "right arrow changes current row value"; printf 'actual: %s\n' "$RIGHT_OUT" >&2; }

INTERRUPT_OUT="$TMP_BASE/interrupt.out"
run_tui "\003" "$INTERRUPT_OUT"
assert_not_contains "ctrl-c exits without traceback" "Traceback" "$INTERRUPT_OUT"
assert_not_contains "ctrl-c exits without keyboardinterrupt dump" "KeyboardInterrupt" "$INTERRUPT_OUT"

LAUNCH_OUT="$TMP_BASE/launch.out"
run_tui "\r\033\033\033" "$LAUNCH_OUT"
assert_not_contains "builder enter only opens sessions without running" "dry-run:" "$LAUNCH_OUT"

WORKDIR_OUT="$TMP_BASE/workdir.out"
run_tui "e\033\033" "$WORKDIR_OUT"
assert_not_contains "e key does not open workdir editor" "type to filter child directories" "$WORKDIR_OUT"
assert_not_contains "workdir no longer opens bottom editor" "Workdir entry" "$WORKDIR_OUT"

WORKDIR_NAV_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_child_index=-1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_RIGHT); app.handle_main_key(curses.KEY_RIGHT); child=ai_tui.short(app.current_workdir_path()); app.focus_workdir_path(); app.handle_main_key(curses.KEY_LEFT); parent=ai_tui.short(app.current_workdir_path()); print("{} {}".format(child, parent))'
)"
[ "$WORKDIR_NAV_OUT" = "~/work/main/src ~/work/main" ] && ok "workdir supports child and parent navigation" || { fail "workdir supports child and parent navigation"; printf 'actual: %s\n' "$WORKDIR_NAV_OUT" >&2; }

WORKDIR_PARENT_SELECTION_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.custom_workdir="'"$HOME_FIXTURE"'/work/main/tests"; app.workdir_child_index=0; app.session_index=0; app.session_scroll=0; app.enter_workdir_parent(); selected=app.filtered_workdir_children()[app.workdir_child_index].name; print("{} {} {} {}".format(app.workdir_child_index, selected, app.workdir_layer, ai_tui.short(app.current_workdir_path())))'
)"
[ "$WORKDIR_PARENT_SELECTION_OUT" = "2 main children ~/work/main" ] && ok "workdir parent opens containing directory dropdown" || { fail "workdir parent opens containing directory dropdown"; printf 'actual: %s\n' "$WORKDIR_PARENT_SELECTION_OUT" >&2; }

WORKDIR_DEEP_MEMORY_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui
app=ai_tui.App.__new__(ai_tui.App)
app.custom_workdir="'"$HOME_FIXTURE"'/work/main/tests"
app.workdir_child_index=-1
app.session_index=0
app.session_scroll=0
app.enter_workdir_parent()
first_selected=app.filtered_workdir_children()[app.workdir_child_index].name
first=ai_tui.short(app.current_workdir_path())
app.enter_workdir_parent()
second=ai_tui.short(app.current_workdir_path())
second_selected=app.filtered_workdir_children()[app.workdir_child_index].name
print("{} {} {} {}".format(first, first_selected, second, second_selected))'
)"
[ "$WORKDIR_DEEP_MEMORY_OUT" = "~/work/main main ~/work work" ] && ok "workdir repeated parent navigation opens each containing dropdown" || { fail "workdir repeated parent navigation opens each containing dropdown"; printf 'actual: %s\n' "$WORKDIR_DEEP_MEMORY_OUT" >&2; }

WORKDIR_HOME_LEFT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui
app=ai_tui.App.__new__(ai_tui.App)
app.custom_workdir="'"$HOME_FIXTURE"'"
app.workdir_child_index=1
app.session_index=0
app.session_scroll=0
app.enter_workdir_parent()
print("{} {} {}".format(app.workdir_child_index, app.workdir_layer, ai_tui.short(app.current_workdir_path())))'
)"
[ "$WORKDIR_HOME_LEFT_OUT" = "-1 path ~/" ] && ok "workdir left at home closes dropdown and keeps home cwd" || { fail "workdir left at home closes dropdown and keeps home cwd"; printf 'actual: %s\n' "$WORKDIR_HOME_LEFT_OUT" >&2; }

WORKDIR_PANEL_OUT="$TMP_BASE/workdir-panel.out"
run_tui "\033OB\033OB\033OB\033\033" "$WORKDIR_PANEL_OUT"
assert_contains "workdir panel shows inline current path" "~/work/" "$WORKDIR_PANEL_OUT"
assert_not_contains "workdir panel omits child angle brackets" "child <" "$WORKDIR_PANEL_OUT"
assert_contains "workdir panel shows matching current segment candidate" "main" "$WORKDIR_PANEL_OUT"
assert_not_contains "workdir panel omits match status text" " match" "$WORKDIR_PANEL_OUT"
assert_not_contains "workdir panel omits no-child status text" "no child" "$WORKDIR_PANEL_OUT"

WORKDIR_TAB_FOCUS_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.last_builder_section=ai_tui.SECTIONS.index("profile"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_layer="path"; app.workdir_child_index=-1; app.session_index=0; app.session_scroll=0; app.handle_main_key(9); print(app.section)'
)"
[ "$WORKDIR_TAB_FOCUS_OUT" = "0" ] && ok "workdir tab cycles inside builder" || { fail "workdir tab cycles inside builder"; printf 'actual: %s\n' "$WORKDIR_TAB_FOCUS_OUT" >&2; }

WORKDIR_BAD_INPUT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.last_builder_section=app.section; app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_layer="children"; app.workdir_child_index=0; app.session_index=0; app.session_scroll=0; app.handle_main_key(9); print("{} {} {}".format(app.section, ai_tui.short(app.current_workdir_path()), app.workdir_layer))'
)"
[ "$WORKDIR_BAD_INPUT_OUT" = "3 ~/work/main/src path" ] && ok "workdir tab commits focused dropdown child and stays in workdir section" || { fail "workdir tab commits focused dropdown child and stays in workdir section"; printf 'actual: %s\n' "$WORKDIR_BAD_INPUT_OUT" >&2; }

WORKDIR_TYPE_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_child_index=0; app.handle_main_key(ord("w")); print("{} {}".format(getattr(app, "workdir_text", None), app.workdir_child_index))'
)"
[ "$WORKDIR_TYPE_OUT" = "None 0" ] && ok "workdir panel blocks direct inline text edits without clearing focus" || { fail "workdir panel blocks direct inline text edits without clearing focus"; printf 'actual: %s\n' "$WORKDIR_TYPE_OUT" >&2; }

WORKDIR_TYPE_WORK_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.workdir_layer="inline"; app.workdir_text=""; app.workdir_child_index=-1; [app.handle_main_key(ord(ch)) for ch in "wo"]; print("{} {} {}".format(app.section, app.workdir_text, app.workdir_layer))'
)"
[ "$WORKDIR_TYPE_WORK_OUT" = "3  inline" ] && ok "workdir inline typing no longer mutates the row" || { fail "workdir inline typing no longer mutates the row"; printf 'actual: %s\n' "$WORKDIR_TYPE_WORK_OUT" >&2; }

WORKDIR_TYPE_QJ_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.workdir_layer="inline"; app.workdir_text=""; app.workdir_child_index=-1; rc=app.handle_main_key(ord("q")); print("{} {} {} {}".format(rc, app.section, app.workdir_text, app.workdir_layer))'
)"
[ "$WORKDIR_TYPE_QJ_OUT" = "None 3  inline" ] && ok "workdir q is not a shortcut" || { fail "workdir q is not a shortcut"; printf 'actual: %s\n' "$WORKDIR_TYPE_QJ_OUT" >&2; }

WORKDIR_BACKSPACE_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text=""; app.workdir_child_index=0; app.handle_main_key(curses.KEY_BACKSPACE); print(app.workdir_text)'
)"
[ "$WORKDIR_BACKSPACE_OUT" = "" ] && ok "workdir backspace preserves fully cleared inline path text" || { fail "workdir backspace preserves fully cleared inline path text"; printf 'actual: %s\n' "$WORKDIR_BACKSPACE_OUT" >&2; }

WORKDIR_BACKSPACE_INDEX_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/a"; app.workdir_child_index=1; app.handle_main_key(curses.KEY_BACKSPACE); print("{} {}".format(app.workdir_text, app.workdir_child_index))'
)"
[ "$WORKDIR_BACKSPACE_INDEX_OUT" = "~/work/main/a 1" ] && ok "workdir backspace is blocked outside the editor without clearing focus" || { fail "workdir backspace is blocked outside the editor without clearing focus"; printf 'actual: %s\n' "$WORKDIR_BACKSPACE_INDEX_OUT" >&2; }

WORKDIR_EMPTY_PREFIX_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/"; app.workdir_child_index=-1; print("{} {}".format(len(app.filtered_workdir_children()), app.workdir_child_index))'
)"
[ "$WORKDIR_EMPTY_PREFIX_OUT" = "14 -1" ] && ok "workdir directory boundary shows candidates without preselecting one" || { fail "workdir directory boundary shows candidates without preselecting one"; printf 'actual: %s\n' "$WORKDIR_EMPTY_PREFIX_OUT" >&2; }

WORKDIR_CLEARED_TEXT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text=""; app.workdir_child_index=0; app.list_meta={}; calls=[]; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda y,x,text,width,attr=0: calls.append(text); app.draw_workdir_row(0,100); print(any("home" in text or "main" in text for text in calls), len(app.filtered_workdir_children()))'
)"
[ "$WORKDIR_CLEARED_TEXT_OUT" = "False 0" ] && ok "workdir fully cleared text does not resurrect home/main" || { fail "workdir fully cleared text does not resurrect home/main"; printf 'actual: %s\n' "$WORKDIR_CLEARED_TEXT_OUT" >&2; }

WORKDIR_RIGHT_AT_BOUNDARY_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_child_index=-1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_RIGHT); layer=app.workdir_layer; app.handle_main_key(curses.KEY_RIGHT); print("{} {}".format(layer, ai_tui.short(app.current_workdir_path())))'
)"
[ "$WORKDIR_RIGHT_AT_BOUNDARY_OUT" = "children ~/work/main/src" ] && ok "workdir right opens child dropdown and enters focused child" || { fail "workdir right opens child dropdown and enters focused child"; printf 'actual: %s\n' "$WORKDIR_RIGHT_AT_BOUNDARY_OUT" >&2; }

WORKDIR_RIGHT_LEAF_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_RIGHT); before=ai_tui.short(app.effective_workdir_path()); app.handle_main_key(curses.KEY_RIGHT); print("{} {} {} {}".format(ai_tui.short(app.current_workdir_path()), app.workdir_text, app.workdir_child_index, before))'
)"
[ "$WORKDIR_RIGHT_LEAF_OUT" = "~/work/main ~/work/main/ 1 ~/work/main/tests" ] && ok "workdir right on focused leaf keeps dropdown open" || { fail "workdir right on focused leaf keeps dropdown open"; printf 'actual: %s\n' "$WORKDIR_RIGHT_LEAF_OUT" >&2; }

WORKDIR_LEAF_EDGE_KEYS_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_RIGHT); app.handle_main_key(curses.KEY_HOME); after_home=ai_tui.short(app.effective_workdir_path()); app.handle_main_key(curses.KEY_END); print("{} {} {}".format(ai_tui.short(app.current_workdir_path()), after_home, ai_tui.short(app.effective_workdir_path())))'
)"
[ "$WORKDIR_LEAF_EDGE_KEYS_OUT" = "~/work/main ~/work/main ~/work/main" ] && ok "workdir home/end keep parent path after leaf right preserves dropdown" || { fail "workdir home/end keep parent path after leaf right preserves dropdown"; printf 'actual: %s\n' "$WORKDIR_LEAF_EDGE_KEYS_OUT" >&2; }

WORKDIR_SLASH_NO_PRESELECT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_child_index=0; app.handle_main_key(ord("w")); print("{} {}".format(app.workdir_text, app.workdir_child_index))'
)"
[ "$WORKDIR_SLASH_NO_PRESELECT_OUT" = "~/work/main/ 0" ] && ok "workdir blocked text leaves existing dropdown focus untouched" || { fail "workdir blocked text leaves existing dropdown focus untouched"; printf 'actual: %s\n' "$WORKDIR_SLASH_NO_PRESELECT_OUT" >&2; }

WORKDIR_INLINE_RIGHT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_child_index=-1; app.handle_main_key(curses.KEY_RIGHT); print(ai_tui.short(app.current_workdir_path()))'
)"
[ "$WORKDIR_INLINE_RIGHT_OUT" = "~/work/main" ] && ok "workdir right does not browse while inline layer is focused" || { fail "workdir right does not browse while inline layer is focused"; printf 'actual: %s\n' "$WORKDIR_INLINE_RIGHT_OUT" >&2; }

WORKDIR_TAB_BOUNDARY_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_child_index=-1; app.handle_main_key(9); print("{} {}".format(app.workdir_text, ai_tui.short(app.current_workdir_path())))'
)"
[ "$WORKDIR_TAB_BOUNDARY_OUT" = "~/work/main ~/work/main" ] && ok "workdir tab cycles builder without descending into first child" || { fail "workdir tab cycles builder without descending into first child"; printf 'actual: %s\n' "$WORKDIR_TAB_BOUNDARY_OUT" >&2; }

WORKDIR_DOWN_HINT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/wo"; app.workdir_modified=True; app.workdir_child_index=-1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_DOWN); print("{} {} {}".format(app.workdir_layer, app.workdir_child_index, app.filtered_workdir_children()[app.workdir_child_index].name))'
)"
[ "$WORKDIR_DOWN_HINT_OUT" = "children 2 main" ] && ok "workdir down opens parent sibling dropdown" || { fail "workdir down opens parent sibling dropdown"; printf 'actual: %s\n' "$WORKDIR_DOWN_HINT_OUT" >&2; }

WORKDIR_DOWN_MEMORY_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work"; app.workdir_text="~/work/"; app.workdir_child_index=-1; app.workdir_child_memory={"'"$HOME_FIXTURE"'/work":"work05"}; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_DOWN); print("{} {}".format(app.workdir_child_index, app.workdir_layer))'
)"
[ "$WORKDIR_DOWN_MEMORY_OUT" = "1 children" ] && ok "workdir down selects current item in parent sibling dropdown" || { fail "workdir down selects current item in parent sibling dropdown"; printf 'actual: %s\n' "$WORKDIR_DOWN_MEMORY_OUT" >&2; }

WORKDIR_DOWN_WRAP_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_DOWN); print("{} {}".format(app.workdir_child_index, app.workdir_layer))'
)"
[ "$WORKDIR_DOWN_WRAP_OUT" = "0 children" ] && ok "workdir down wraps focused dropdown child" || { fail "workdir down wraps focused dropdown child"; printf 'actual: %s\n' "$WORKDIR_DOWN_WRAP_OUT" >&2; }

WORKDIR_FOCUS_MEMORY_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=0; app.workdir_child_memory={}; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_DOWN); print(app.workdir_child_memory)'
)"
case "$WORKDIR_FOCUS_MEMORY_OUT" in
  *"work"*"main"*) ok "workdir dropdown focus updates child memory" ;;
  *) fail "workdir dropdown focus updates child memory"; printf 'actual: %s\n' "$WORKDIR_FOCUS_MEMORY_OUT" >&2 ;;
esac

WORKDIR_FOCUS_COMMAND_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.indices={"mode":0,"provider":0,"profile":0,"workdir":0}; app.profiles=["default"]; app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=0; app.session_index=0; app.session_scroll=0; before=app.command_line(); app.handle_main_key(curses.KEY_DOWN); after=app.command_line(); print("{} | {}".format(before, after))'
)"
[ "$WORKDIR_FOCUS_COMMAND_OUT" = "ai run codex --cwd ~/work/main/src | ai run codex --cwd ~/work/main/tests" ] && ok "workdir dropdown focus updates command cwd preview" || { fail "workdir dropdown focus updates command cwd preview"; printf 'actual: %s\n' "$WORKDIR_FOCUS_COMMAND_OUT" >&2; }

WORKDIR_UP_FOCUS_COMMAND_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.indices={"mode":0,"provider":0,"profile":0,"workdir":0}; app.profiles=["default"]; app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=1; app.session_index=0; app.session_scroll=0; before=app.command_line(); app.handle_main_key(curses.KEY_UP); after=app.command_line(); print("{} | {}".format(before, after))'
)"
[ "$WORKDIR_UP_FOCUS_COMMAND_OUT" = "ai run codex --cwd ~/work/main/tests | ai run codex --cwd ~/work/main/src" ] && ok "workdir up updates command cwd preview to focused child" || { fail "workdir up updates command cwd preview to focused child"; printf 'actual: %s\n' "$WORKDIR_UP_FOCUS_COMMAND_OUT" >&2; }

WORKDIR_UP_TOP_INLINE_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=0; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_UP); print("{} {}".format(app.workdir_layer, app.workdir_child_index))'
)"
[ "$WORKDIR_UP_TOP_INLINE_OUT" = "children 1" ] && ok "workdir up at first child cycles to bottom" || { fail "workdir up at first child cycles to bottom"; printf 'actual: %s\n' "$WORKDIR_UP_TOP_INLINE_OUT" >&2; }

WORKDIR_LEFT_RIGHT_MEMORY_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=0; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_DOWN); app.handle_main_key(curses.KEY_LEFT); app.handle_main_key(curses.KEY_RIGHT); print("{} {}".format(ai_tui.short(app.current_workdir_path()), app.filtered_workdir_children()[app.workdir_child_index].name))'
)"
[ "$WORKDIR_LEFT_RIGHT_MEMORY_OUT" = "~/work/main tests" ] && ok "workdir left from dropdown uses focused child and restores remembered sibling" || { fail "workdir left from dropdown uses focused child and restores remembered sibling"; printf 'actual: %s\n' "$WORKDIR_LEFT_RIGHT_MEMORY_OUT" >&2; }

WORKDIR_LEFT_RIGHT_LEFT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_layer="path"; app.workdir_child_index=-1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_LEFT); after_left=ai_tui.short(app.current_workdir_path()); app.handle_main_key(curses.KEY_RIGHT); focused=ai_tui.short(app.effective_workdir_path()); app.handle_main_key(curses.KEY_LEFT); print("{} {} {} {}".format(after_left, focused, ai_tui.short(app.current_workdir_path()), app.workdir_layer))'
)"
[ "$WORKDIR_LEFT_RIGHT_LEFT_OUT" = "~/work ~/work/main ~/work children" ] && ok "workdir left after reopened dropdown keeps parent dropdown open" || { fail "workdir left after reopened dropdown keeps parent dropdown open"; printf 'actual: %s\n' "$WORKDIR_LEFT_RIGHT_LEFT_OUT" >&2; }

WORKDIR_HOME_LEFT_TEXT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'"; app.workdir_text="~/wo"; app.workdir_layer="children"; app.workdir_child_index=1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_LEFT); print("{} {}".format(app.workdir_text, ai_tui.short(app.current_workdir_path())))'
)"
[ "$WORKDIR_HOME_LEFT_TEXT_OUT" = "~/ ~/" ] && ok "workdir left at home normalizes to home path focus" || { fail "workdir left at home normalizes to home path focus"; printf 'actual: %s\n' "$WORKDIR_HOME_LEFT_TEXT_OUT" >&2; }

WORKDIR_HOME_PREFIX_LEFT_RIGHT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'"; app.workdir_text="~/wo"; app.workdir_layer="children"; app.workdir_child_index=1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_LEFT); app.handle_main_key(curses.KEY_RIGHT); selected=app.selected_workdir_child().name if app.selected_workdir_child() else "-"; print("{} {} {} {}".format(app.workdir_text, ai_tui.short(app.current_workdir_path()), app.workdir_layer, selected))'
)"
[ "$WORKDIR_HOME_PREFIX_LEFT_RIGHT_OUT" = "~/ ~/ children work" ] && ok "workdir right from home restores remembered child focus" || { fail "workdir right from home restores remembered child focus"; printf 'actual: %s\n' "$WORKDIR_HOME_PREFIX_LEFT_RIGHT_OUT" >&2; }

WORKDIR_TAB_CHILD_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_text="~/work/main/"; app.workdir_layer="children"; app.workdir_child_index=1; app.session_index=0; app.session_scroll=0; app.handle_main_key(9); print("{} {} {} {} {}".format(app.workdir_text, app.workdir_layer, app.workdir_child_index, ai_tui.short(app.current_workdir_path()), app.section))'
)"
[ "$WORKDIR_TAB_CHILD_OUT" = "~/work/main/tests path -1 ~/work/main/tests 3" ] && ok "workdir tab commits focused dropdown child and stays in workdir section" || { fail "workdir tab commits focused dropdown child and stays in workdir section"; printf 'actual: %s\n' "$WORKDIR_TAB_CHILD_OUT" >&2; }

WORKDIR_VISUAL_LIST_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'from pathlib import Path; import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.list_meta={}; app.workdir_text="~/wo"; app.workdir_modified=True; app.workdir_layer="inline"; app.workdir_child_index=-1; app.filtered_workdir_children=lambda:[Path("'"$HOME_FIXTURE"'/work")]; calls=[]; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda y,x,text,width,attr=0: calls.append((y,text,attr)); app.draw_workdir_row(0,100); app.draw_workdir_children(1,100,3); print(any(y == 1 and text == "work" for y,text,attr in calls), any(y == 1 and attr & curses.A_REVERSE for y,text,attr in calls))'
)"
[ "$WORKDIR_VISUAL_LIST_OUT" = "True False" ] && ok "workdir completion list previews candidates before activation" || { fail "workdir completion list previews candidates before activation"; printf 'actual: %s\n' "$WORKDIR_VISUAL_LIST_OUT" >&2; }

NEW_SESSION_OUT="$TMP_BASE/new-session.out"
run_tui "\r\033OB\r\r\033\033\033" "$NEW_SESSION_OUT"
assert_contains "new session dry-run runs default command" "dry-run: $BIN_FIXTURE/ai run codex" "$NEW_SESSION_OUT"
assert_not_contains "new session dry-run does not resume" "resume codex" "$NEW_SESSION_OUT"

LAST_RESUME_OUT="$TMP_BASE/last-resume.out"
run_tui "\r\r\r\033\033\033" "$LAST_RESUME_OUT"
assert_contains "last session dry-run uses resume last" "dry-run: $BIN_FIXTURE/ai resume codex last" "$LAST_RESUME_OUT"
assert_not_contains "last session dry-run omits default profile" "resume codex --profile default" "$LAST_RESUME_OUT"

CONCRETE_RESUME_OUT="$TMP_BASE/concrete-resume.out"
run_tui "\r\033OB\033OB\r\r\033\033\033" "$CONCRETE_RESUME_OUT"
assert_contains "concrete session dry-run uses selected id" "dry-run: $BIN_FIXTURE/ai resume codex smoke-session-two" "$CONCRETE_RESUME_OUT"

WORKDIR_CHILD_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("workdir"); app.last_builder_section=app.section; app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdir_child_index=-1; app.session_index=0; app.session_scroll=0; app.handle_main_key(curses.KEY_DOWN); print("{} {} {}".format(app.section, app.workdir_child_index, app.workdir_layer))'
)"
[ "$WORKDIR_CHILD_OUT" = "3 2 children" ] && ok "workdir down opens parent sibling completion list" || { fail "workdir down opens parent sibling completion list"; printf 'actual: %s\n' "$WORKDIR_CHILD_OUT" >&2; }

NAV_OUT="$TMP_BASE/nav.out"
run_tui "\t\t\t\t\033\033" "$NAV_OUT"
assert_contains "tab cycles only inside builder" "Command builder" "$NAV_OUT"
assert_contains "session list remains browsable" "smoke prompt summary one" "$NAV_OUT"

SCROLL_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.natural_scroll=True; app.section=ai_tui.SECTIONS.index("sessions"); app.session_index=0; app.session_scroll=0; app.current_sessions=lambda:[{} for _ in range(12)]; d4=app.mouse_scroll_delta(getattr(curses,"BUTTON4_PRESSED",0)); d5=app.mouse_scroll_delta(getattr(curses,"BUTTON5_PRESSED",0)); app.move_selection(d4); app.natural_scroll=False; c4=app.mouse_scroll_delta(getattr(curses,"BUTTON4_PRESSED",0)); c5=app.mouse_scroll_delta(getattr(curses,"BUTTON5_PRESSED",0)); print("natural={},{} classic={},{} session={}".format(d4,d5,c4,c5,app.session_index))'
)"
case "$SCROLL_OUT" in
  *"natural=1,-1"*"classic=-1,1"*"session=1"*) ok "touch scroll direction is natural by default" ;;
  *) fail "touch scroll direction is natural by default"; printf 'actual: %s\n' "$SCROLL_OUT" >&2 ;;
esac

SESSION_ROWS_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("sessions"); app.session_index=0; app.session_scroll=0; app.list_meta={}; app.current_provider=lambda:"codex"; app.current_profile=lambda:"default"; app.add_line=lambda *args, **kwargs: None; app.current_sessions=lambda:[{"session_id":str(i),"updated":"2026-05-05T00:00:00Z","profile":"default","workdir":"/tmp","title":"session","last_prompt_summary":"prompt summary","last_response_summary":"answer summary"} for i in range(20)]; app.draw_sessions(0,120,22); print(app.list_meta["sessions"]["rows"])'
)"
[ "$SESSION_ROWS_OUT" = "10" ] && ok "session list grows to ten rows" || { fail "session list grows to ten rows"; printf 'actual: %s\n' "$SESSION_ROWS_OUT" >&2; }

LAYOUT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; app.indices={"mode":0,"provider":0,"profile":0,"workdir":0}; app.profiles=["default"]; app.custom_workdir="'"$HOME_FIXTURE"'/work/main"; app.workdirs=[]; app.workdir_child_index=0; app.list_meta={}; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda *args, **kwargs: None; y1=app.draw_controls(4,100,6); app.section=ai_tui.SECTIONS.index("workdir"); y2=app.draw_controls(4,100,6); print("{} {}".format(y1,y2))'
)"
[ "$LAYOUT_OUT" = "15 15" ] && ok "command builder reserves stable workdir panel height" || { fail "command builder reserves stable workdir panel height"; printf 'actual: %s\n' "$LAYOUT_OUT" >&2; }

CHOICE_ATTR_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; app.list_meta={}; calls=[]; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda y,x,text,width,attr=0: calls.append((text,attr)); app.draw_choice_row(0,80,"mode","Mode",ai_tui.MODES,0); print(any(text == "run" and attr & curses.A_REVERSE and attr & curses.A_BOLD for text, attr in calls), any(text.startswith("run ") and attr & curses.A_REVERSE for text, attr in calls))'
)"
[ "$CHOICE_ATTR_OUT" = "True False" ] && ok "choice highlight covers text but not padding" || { fail "choice highlight covers text but not padding"; printf 'actual: %s\n' "$CHOICE_ATTR_OUT" >&2; }

INACTIVE_CHOICE_ATTR_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("mode"); app.list_meta={}; calls=[]; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda y,x,text,width,attr=0: calls.append((text,attr)); app.draw_choice_row(0,80,"provider","Provider",["Codex","Gemini"],0); attr=[attr for text,attr in calls if text == "Codex"][0]; print(bool(attr & curses.A_REVERSE), bool(attr & curses.A_DIM), bool(attr & curses.A_BOLD))'
)"
[ "$INACTIVE_CHOICE_ATTR_OUT" = "True True False" ] && ok "inactive selected choice uses dim reverse highlight" || { fail "inactive selected choice uses dim reverse highlight"; printf 'actual: %s\n' "$INACTIVE_CHOICE_ATTR_OUT" >&2; }

SESSION_ATTR_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("mode"); app.session_index=-1; app.session_scroll=0; app.list_meta={}; calls=[]; app.current_provider=lambda:"codex"; app.current_profile=lambda:"default"; app.current_sessions=lambda:[{"session_id":"s","updated":"2026-05-05T00:00:00Z","profile":"default","workdir":"/tmp","title":"session","last_prompt_summary":"prompt","last_response_summary":"answer"}]; app.add_line=lambda y,x,text,width,attr=0: calls.append((y,text,attr)); app.draw_sessions(0,100,10); title_attr=[attr for y,text,attr in calls if text.startswith("Sessions:")][0]; selected_rows=[text for y,text,attr in calls if text.startswith("> ")]; selected_label=any("Selected:" in text for y,text,attr in calls); spacer=any(y == 1 and text.strip() == "" for y,text,attr in calls); print(bool(title_attr & curses.A_REVERSE), len(selected_rows), selected_label, spacer)'
)"
[ "$SESSION_ATTR_OUT" = "False 0 False False" ] && ok "initial session list has builder-style title and no selected row" || { fail "initial session list has builder-style title and no selected row"; printf 'actual: %s\n' "$SESSION_ATTR_OUT" >&2; }

SESSION_SELECTED_SPACING_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("sessions"); app.session_index=0; app.session_scroll=0; app.list_meta={}; calls=[]; app.current_provider=lambda:"codex"; app.current_profile=lambda:"default"; app.current_sessions=lambda:[{"session_id":"s","updated":"2026-05-05T00:00:00Z","profile":"default","workdir":"/tmp","title":"session","last_prompt_summary":"prompt","last_response_summary":"answer"}]; app.add_line=lambda y,x,text,width,attr=0: calls.append((y,text,attr)); app.draw_sessions(0,100,10); selected_y=[y for y,text,attr in calls if text.startswith("Selected:")][0]; blank_before=any(y == selected_y - 1 and text.strip() == "" for y,text,attr in calls); title_gap=any(y == 1 and text.strip() == "" for y,text,attr in calls); print(blank_before, title_gap)'
)"
[ "$SESSION_SELECTED_SPACING_OUT" = "True False" ] && ok "session list is separated from selected preview, not from title" || { fail "session list is separated from selected preview, not from title"; printf 'actual: %s\n' "$SESSION_SELECTED_SPACING_OUT" >&2; }

CHOICE_SPACING_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; calls=[]; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda y,x,text,width,attr=0: calls.append((x,text,width)); app.draw_choice_row(0,100,"provider","Provider",["Codex","Gemini","Hermes"],0); xs={text:x for x,text,width in calls if text in {"Codex","Gemini","Hermes"}}; print(xs["Gemini"] - xs["Codex"], xs["Hermes"] - xs["Gemini"])'
)"
[ "$CHOICE_SPACING_OUT" = "8 9" ] && ok "choice row uses natural three-cell gaps" || { fail "choice row uses natural three-cell gaps"; printf 'actual: %s\n' "$CHOICE_SPACING_OUT" >&2; }

CHOICE_COLUMN_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=0; calls=[]; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda y,x,text,width,attr=0: calls.append((x,text)); app.draw_choice_row(0,100,"provider","Provider",["Codex"],0); print([x for x,text in calls if text == "Codex"][0])'
)"
[ "$CHOICE_COLUMN_OUT" = "14" ] && ok "choice content starts one column earlier" || { fail "choice content starts one column earlier"; printf 'actual: %s\n' "$CHOICE_COLUMN_OUT" >&2; }

CHOICE_DEFAULT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses, ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.section=ai_tui.SECTIONS.index("profile"); calls=[]; app.add_line=lambda *args, **kwargs: None; app.add_text=lambda y,x,text,width,attr=0: calls.append((text,width,attr)); app.draw_choice_row(0,32,"profile","Profile",["default","very-long-profile-name"],0); print(any(text == "default" and width == 7 and attr & curses.A_REVERSE for text,width,attr in calls), any(text == "default ..." for text,width,attr in calls))'
)"
[ "$CHOICE_DEFAULT_OUT" = "True False" ] && ok "choice row keeps selected default readable in narrow profile list" || { fail "choice row keeps selected default readable in narrow profile list"; printf 'actual: %s\n' "$CHOICE_DEFAULT_OUT" >&2; }

WORKDIR_ROULETTE_X_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses
from pathlib import Path
import ai_tui
app=ai_tui.App.__new__(ai_tui.App)
app.section=ai_tui.SECTIONS.index("workdir")
app.list_meta={}
app.custom_workdir="'"$HOME_FIXTURE"'/work/main"
app.workdir_layer="children"
app.workdir_child_index=0
app.filtered_workdir_children=lambda:[Path("'"$HOME_FIXTURE"'/work/main/src"), Path("'"$HOME_FIXTURE"'/work/main/tests")]
app.workdir_children=lambda path=None:[Path("'"$HOME_FIXTURE"'/work/main/src"), Path("'"$HOME_FIXTURE"'/work/main/tests")]
calls=[]
app.add_line=lambda *args, **kwargs: None
app.add_text=lambda y,x,text,width,attr=0: calls.append((y,x,text,attr))
app.draw_workdir_row(0,100)
app.draw_workdir_children(1,100,3)
text_x=[x for y,x,text,attr in calls if text == "~/work/main/" and y == 0][0]
child_x=[x for y,x,text,attr in calls if text == "src" and y == 1][0]
selected=any(text == "src" and attr & curses.A_REVERSE for y,x,text,attr in calls)
print(text_x + ai_tui.cell_width("~/work/main/"), child_x, selected)'
)"
[ "$WORKDIR_ROULETTE_X_OUT" = "26 26 True" ] && ok "workdir focused dropdown aligns under child segment with reverse highlight" || { fail "workdir focused dropdown aligns under child segment with reverse highlight"; printf 'actual: %s\n' "$WORKDIR_ROULETTE_X_OUT" >&2; }

WORKDIR_NO_COUNT_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses
from pathlib import Path
import ai_tui
app=ai_tui.App.__new__(ai_tui.App)
app.section=ai_tui.SECTIONS.index("workdir")
app.list_meta={}
app.workdir_child_index=0
app.custom_workdir="'"$HOME_FIXTURE"'/work/main"
app.filtered_workdir_children=lambda:[Path("'"$HOME_FIXTURE"'/work/main/src")]
app.workdir_children=lambda:[Path("'"$HOME_FIXTURE"'/work/main/src")]
app.workdir_completion_suffix=lambda:""
calls=[]
app.add_line=lambda *args, **kwargs: None
app.add_text=lambda y,x,text,width,attr=0: calls.append(text)
app.draw_workdir_row(0,100)
print(any("/" in text and text[0].isdigit() for text in calls))'
)"
[ "$WORKDIR_NO_COUNT_OUT" = "False" ] && ok "workdir row omits selected count indicator" || { fail "workdir row omits selected count indicator"; printf 'actual: %s\n' "$WORKDIR_NO_COUNT_OUT" >&2; }

PROFILE_MEMORY_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; app=ai_tui.App.__new__(ai_tui.App); app.indices={"mode":0,"provider":0,"profile":1,"workdir":0}; app.profiles=["default","team-alpha"]; app.profile_memory={}; app.reset_sessions=lambda: None; app.change_option("provider",1); app.profiles=["default","team-alpha"]; app.indices["profile"]=1; app.change_option("provider",-1); print(app.current_provider(), app.current_profile())'
)"
[ "$PROFILE_MEMORY_OUT" = "codex team-alpha" ] && ok "provider switching restores provider-specific profile" || { fail "provider switching restores provider-specific profile"; printf 'actual: %s\n' "$PROFILE_MEMORY_OUT" >&2; }

WORKDIR_SEGMENT_ATTR_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import curses
from pathlib import Path
import ai_tui
app=ai_tui.App.__new__(ai_tui.App)
app.section=ai_tui.SECTIONS.index("workdir")
app.list_meta={}
app.workdir_child_index=0
app.custom_workdir="'"$HOME_FIXTURE"'/work/main"
app.workdir_layer="path"
app.workdir_text="~/work/main"
app.filtered_workdir_children=lambda:[Path("'"$HOME_FIXTURE"'/work/main/src"), Path("'"$HOME_FIXTURE"'/work/main/tests")]
app.workdir_completion_suffix=lambda:""
calls=[]
app.add_line=lambda *args, **kwargs: None
app.add_text=lambda y,x,text,width,attr=0: calls.append((text,attr))
app.draw_workdir_row(0,100)
print(any(text == "main" for text, attr in calls), any(text == "main" and attr & curses.A_REVERSE for text, attr in calls), any("child <" in text for text, attr in calls))'
)"
[ "$WORKDIR_SEGMENT_ATTR_OUT" = "True True False" ] && ok "workdir path focus reverse-highlights selected directory segment" || { fail "workdir path focus reverse-highlights selected directory segment"; printf 'actual: %s\n' "$WORKDIR_SEGMENT_ATTR_OUT" >&2; }

KOREAN_WRAP_OUT="$(
  HOME="$HOME_FIXTURE" PYTHONPATH="$ROOT/code/ai-lib" python3 -c 'import ai_tui; lines=ai_tui.wrap_cell_text("한글이계속이어지는세션요약입니다", 10); print(max(ai_tui.cell_width(line) for line in lines))'
)"
[ "$KOREAN_WRAP_OUT" -le 10 ] && ok "korean preview wrapping respects terminal cells" || { fail "korean preview wrapping respects terminal cells"; printf 'actual: %s\n' "$KOREAN_WRAP_OUT" >&2; }

printf '\nPASS=%s FAIL=%s\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
