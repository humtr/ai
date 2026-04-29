# Shared cwd policy for gm/cm/hm.
# Source this file from manager wrappers only.

ai_mgr_maybe_cd() {
  local mgr_name="$1"
  local profile_home="$2"
  local sb_root="$3"
  local cmd="$4"
  local profile="$5"
  local force_policy="$6"
  local tty_policy="$7"
  local non_tty_policy="$8"
  local ask_default="$9"
  local allowed_cmds="${10}"

  [ -n "$profile" ] || return 0
  [ -d "$profile_home/$profile" ] || return 0

  case " $allowed_cmds " in
    *" $cmd "*) ;;
    *) return 0 ;;
  esac

  local target="$sb_root/$profile"
  local current
  current="$(pwd -P 2>/dev/null || pwd)"

  if [ "$current" = "$target" ]; then
    return 0
  fi

  local policy="$force_policy"

  if [ -z "$policy" ]; then
    if [ -t 0 ] && [ -t 1 ]; then
      policy="$tty_policy"
    else
      policy="$non_tty_policy"
    fi
  fi

  case "$policy" in
    cwd|"")
      return 0
      ;;

    sandbox|sb)
      mkdir -p "$target"
      cd "$target" 2>/dev/null || true
      return 0
      ;;

    ask)
      if ! [ -t 0 ] || ! [ -t 1 ]; then
        case "$non_tty_policy" in
          sandbox|sb)
            mkdir -p "$target"
            cd "$target" 2>/dev/null || true
            ;;
        esac
        return 0
      fi

      echo >&2
      echo "[$mgr_name] 현재 위치가 profile sandbox와 다릅니다." >&2
      echo >&2
      echo "  현재 위치:" >&2
      echo "    $current" >&2
      echo "  profile sandbox:" >&2
      echo "    $target" >&2
      echo >&2
      echo "선택:" >&2
      echo "  1) 현재 위치에서 실행" >&2
      echo "  2) sandbox에서 실행" >&2
      echo "  3) 취소" >&2
      echo >&2

      local default_label
      if [ "$ask_default" = "sandbox" ] || [ "$ask_default" = "sb" ]; then
        default_label="2"
      else
        default_label="1"
      fi

      local ans
      printf "선택 [%s]: " "$default_label" > /dev/tty
      IFS= read -r ans < /dev/tty || ans=""
      [ -n "$ans" ] || ans="$default_label"

      case "$ans" in
        1|c|cwd|C|current)
          return 0
          ;;
        2|s|sb|S|sandbox)
          mkdir -p "$target"
          cd "$target" 2>/dev/null || true
          return 0
          ;;
        3|q|Q|quit|cancel|취소)
          echo "cancelled" >&2
          return 130
          ;;
        *)
          echo "ERROR: unknown choice: $ans" >&2
          return 2
          ;;
      esac
      ;;

    *)
      echo "ERROR: invalid $mgr_name cwd policy: $policy" >&2
      return 2
      ;;
  esac
}
