#!/data/data/com.termux/files/usr/bin/python
# clip_approve = 비동기 명령 승인 처리기 (Command Line Interface Proxy - Approve)
import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path.home()
STATE = HOME / ".local" / "state" / "clip"
PENDING = STATE / "approvals" / "pending"
DONE = STATE / "approvals" / "done"
REJECTED = STATE / "approvals" / "rejected"
EXPIRED = STATE / "approvals" / "expired"
LOG = STATE / "logs" / "approve.log"

DEFAULT_TTL_SECONDS = 600
DEFAULT_MODEL_TIMEOUT = 240


def ensure_dirs():
    for d in [PENDING, DONE, REJECTED, EXPIRED, LOG.parent]:
        d.mkdir(parents=True, exist_ok=True)


def log(msg):
    ensure_dirs()
    with LOG.open("a", encoding="utf-8") as f:
        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def new_id():
    return time.strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(3)


def now():
    return int(time.time())


def req_path(id_, folder=PENDING):
    return folder / f"{id_}.json"


def save_req(req, folder=PENDING):
    ensure_dirs()
    p = req_path(req["id"], folder)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(req, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def load_pending(id_):
    p = req_path(id_)
    if not p.exists():
        raise SystemExit(f"ERROR: pending request not found: {id_}")
    req = json.loads(p.read_text(encoding="utf-8"))
    if int(req.get("expires_at", 0)) < now():
        req["status"] = "expired"
        req["expired_at"] = now()
        save_req(req, EXPIRED)
        p.unlink(missing_ok=True)
        raise SystemExit(f"ERROR: request expired: {id_}")
    return req


def load_env(profile):
    # 하위 호환성 유지: 기존 .hermes 프로필 또는 신규 .config/clip 프로필 체크
    envfile = HOME / ".config" / "clip" / "profiles" / profile / ".env"
    if not envfile.exists():
        envfile = HOME / ".hermes" / "profiles" / profile / ".env"
    
    out = {}
    if not envfile.exists():
        return out
    for raw in envfile.read_text(errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def telegram_token(profile):
    return load_env(profile).get("TELEGRAM_BOT_TOKEN")


def default_chat_id(profile):
    env = load_env(profile)
    for key in [
        "CLIP_APPROVAL_CHAT_ID",
        "HGW_APPROVAL_CHAT_ID",
        "TELEGRAM_ADMIN_CHAT_ID",
        "TELEGRAM_HOME_CHAT_ID",
        "TELEGRAM_HOME",
        "TELEGRAM_CHAT_ID",
        "HOME_CHAT_ID",
    ]:
        if env.get(key):
            return env[key]
    return None


def split_text(text, limit=3800):
    if len(text) <= limit:
        return [text]
    chunks = []
    cur = ""
    for line in text.splitlines(True):
        if len(cur) + len(line) > limit:
            if cur:
                chunks.append(cur)
            cur = ""
        cur += line
    if cur:
        chunks.append(cur)
    return chunks


def send_telegram(profile, chat_id, text):
    if not chat_id:
        return False

    token = telegram_token(profile)
    if not token:
        print(f"WARNING: TELEGRAM_BOT_TOKEN not found for profile={profile}", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = True

    for chunk in split_text(text):
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": "true",
        }).encode()

        try:
            req = urllib.request.Request(url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
        except Exception as exc:
            print(f"WARNING: Telegram send failed: {exc}", file=sys.stderr)
            ok = False
    return ok


def run_command(cmd, timeout):
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout} seconds"
    except Exception as exc:
        return -2, "", str(exc)


def cmd_request(args):
    ensure_dirs()
    id_ = new_id()
    ttl = args.ttl or DEFAULT_TTL_SECONDS
    expires_at = now() + ttl

    req = {
        "id": id_,
        "status": "pending",
        "created_at": now(),
        "expires_at": expires_at,
        "profile": args.profile,
        "chat_id": args.chat_id or default_chat_id(args.profile),
        "command": args.command,
        "timeout": args.timeout or DEFAULT_MODEL_TIMEOUT,
    }

    p = save_req(req, PENDING)
    log(f"REQUESTED id={id_} profile={args.profile} cmd={args.command[:100]}")

    if args.silent:
        print(id_)
        return

    print(f"Created pending approval request:")
    print(f"  ID:      {id_}")
    print(f"  Command: {args.command}")
    print(f"  Expires: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}")

    chat_id = req["chat_id"]
    if chat_id:
        msg = (
            f"🔔 [CLIP 승인 요청]\n"
            f"ID: `{id_}`\n"
            f"명령어: `{args.command}`\n\n"
            f"승인하려면 아래 명령을 터미널에 입력하거나 챗봇에 답장하세요:\n"
            f"`clip approve allow {id_}`"
        )
        if send_telegram(args.profile, chat_id, msg):
            print(f"Sent Telegram notification to chat_id: {chat_id}")
        else:
            print("WARNING: Failed to send Telegram notification.")
    else:
        print("NOTE: No chat_id resolved. Telegram notification skipped.")


def cmd_allow(args):
    req = load_pending(args.id)
    req["status"] = "allowed"
    req["allowed_at"] = now()
    save_req(req, DONE)

    req_path(args.id, PENDING).unlink(missing_ok=True)
    log(f"ALLOWED id={args.id}")
    print(f"Request {args.id} has been allowed.")

    cmd_str = req["command"]
    timeout = req["timeout"]

    print(f"Executing: {cmd_str}")
    code, stdout, stderr = run_command(cmd_str, timeout)

    req["returncode"] = code
    req["stdout"] = stdout
    req["stderr"] = stderr
    req["executed_at"] = now()
    save_req(req, DONE)

    log(f"EXECUTED id={args.id} rc={code}")

    chat_id = req["chat_id"]
    if chat_id:
        result_str = (stdout + "\n" + stderr).strip()
        if not result_str:
            result_str = "[출력 없음]"
        
        msg = (
            f"✅ [CLIP 승인 실행 완료]\n"
            f"ID: `{args.id}`\n"
            f"결과코드: `{code}`\n"
            f"출력:\n```\n{result_str[:3000]}\n```"
        )
        send_telegram(req["profile"], chat_id, msg)


def cmd_deny(args):
    req = load_pending(args.id)
    req["status"] = "denied"
    req["denied_at"] = now()
    save_req(req, REJECTED)

    req_path(args.id, PENDING).unlink(missing_ok=True)
    log(f"DENIED id={args.id}")
    print(f"Request {args.id} has been denied.")

    chat_id = req["chat_id"]
    if chat_id:
        msg = f"❌ [CLIP 승인 거절됨]\nID: `{args.id}`\n요청이 반려되었습니다."
        send_telegram(req["profile"], chat_id, msg)


def cmd_list(args):
    ensure_dirs()
    pending_files = sorted(PENDING.glob("*.json"))

    if not pending_files:
        print("No pending requests.")
        return

    print(f"{'ID':<25} {'Created':<20} {'Profile':<12} {'Command'}")
    print("-" * 80)
    for p in pending_files:
        try:
            req = json.loads(p.read_text(encoding="utf-8"))
            id_ = req.get("id")
            created = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(req.get("created_at", 0)))
            profile = req.get("profile", "")
            cmd_str = req.get("command", "")
            if len(cmd_str) > 40:
                cmd_str = cmd_str[:37] + "..."
            print(f"{id_:<25} {created:<20} {profile:<12} {cmd_str}")
        except Exception:
            pass


def cmd_show(args):
    for folder in [PENDING, DONE, REJECTED, EXPIRED]:
        p = req_path(args.id, folder)
        if p.exists():
            print(p.read_text(encoding="utf-8"))
            return
    print(f"ERROR: request not found: {args.id}", file=sys.stderr)
    sys.exit(1)


def cmd_cleanup(args):
    ensure_dirs()
    cleaned = 0
    for p in PENDING.glob("*.json"):
        try:
            req = json.loads(p.read_text(encoding="utf-8"))
            if int(req.get("expires_at", 0)) < now():
                req["status"] = "expired"
                req["expired_at"] = now()
                save_req(req, EXPIRED)
                p.unlink(missing_ok=True)
                cleaned += 1
        except Exception:
            pass
    print(f"Cleaned up {cleaned} expired requests.")


def main():
    parser = argparse.ArgumentParser(prog="clip-approve")
    sub = parser.add_subparsers(dest="cmd")

    req = sub.add_parser("request")
    req.add_argument("command")
    req.add_argument("--profile", required=True)
    req.add_argument("--chat-id")
    req.add_argument("--ttl", type=int)
    req.add_argument("--timeout", type=int)
    req.add_argument("--silent", action="store_true")

    allow = sub.add_parser("allow")
    allow.add_argument("id")

    deny = sub.add_parser("deny")
    deny.add_argument("id")

    sub.add_parser("list")

    show = sub.add_parser("show")
    show.add_argument("id")

    sub.add_parser("cleanup")

    args = parser.parse_args()

    if args.cmd == "request":
        cmd_request(args)
    elif args.cmd == "allow":
        cmd_allow(args)
    elif args.cmd == "deny":
        cmd_deny(args)
    elif args.cmd == "list":
        cmd_list(args)
    elif args.cmd == "show":
        cmd_show(args)
    elif args.cmd == "cleanup":
        cmd_cleanup(args)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
