#!/data/data/com.termux/files/usr/bin/python
# hgw approve = URL fetch approval queue for Hermes Gateway

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
LIB = HOME / ".config" / "hgw" / "lib"
STATE = HOME / ".local" / "state" / "hgw"
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


def fetch_url(url):
    fetcher = str(LIB / "web_fetch.py")
    proc = subprocess.run(
        [fetcher, url, "--timeout", "20", "--max-bytes", "1000000"],
        text=True,
        capture_output=True,
        timeout=35,
        input="",
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"web fetch failed: {proc.returncode}")
    return proc.stdout.strip()


def ask_hermes(profile, prompt):
    workdir = HOME / "sb" / "hermes" / profile
    workdir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        ["hm", "task", profile, prompt],
        text=True,
        capture_output=True,
        timeout=DEFAULT_MODEL_TIMEOUT,
        cwd=str(workdir),
        input="",
    )

    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"hm task failed: {proc.returncode}")

    return proc.stdout.strip()


def cmd_request(args):
    ensure_dirs()

    id_ = new_id()
    chat_id = args.chat or default_chat_id(args.profile)
    user_id = args.user or ""
    prompt = " ".join(args.prompt).strip() or "이 URL의 내용을 읽고 요약해줘."

    req = {
        "id": id_,
        "kind": "url_fetch",
        "status": "pending",
        "created_at": now(),
        "expires_at": now() + int(args.ttl),
        "source": args.source,
        "profile": args.profile,
        "chat_id": str(chat_id or ""),
        "user_id": str(user_id or ""),
        "message_id": str(args.message_id or ""),
        "url": args.url,
        "prompt": prompt,
    }

    p = save_req(req)

    msg = f"""URL fetch 승인 요청

ID: {id_}
URL: {args.url}
요청: {prompt}

승인:
  /approve {id_}

거절:
  /deny {id_}

만료:
  {args.ttl}초 후

CLI:
  hgw approve allow {id_}
  hgw approve deny {id_}
"""

    print(f"created: {p}")
    print()
    print(msg)

    if chat_id:
        send_telegram(args.profile, chat_id, msg)

    log(f"request id={id_} profile={args.profile} url={args.url}")


def cmd_list(args):
    ensure_dirs()
    cleanup_expired(silent=True)

    files = sorted(PENDING.glob("*.json"))
    if not files:
        print("No pending approvals.")
        return

    for p in files:
        try:
            req = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        print(f"{req.get('id')}  expires={req.get('expires_at')}  profile={req.get('profile')}  url={req.get('url')}")


def cmd_show(args):
    req = load_pending(args.id)
    print(json.dumps(req, indent=2, ensure_ascii=False))


def finish_request(req, target_folder, status):
    src = req_path(req["id"])
    req["status"] = status
    req[f"{status}_at"] = now()
    save_req(req, target_folder)
    src.unlink(missing_ok=True)


def cmd_allow(args):
    req = load_pending(args.id)

    actor = str(args.user or "")
    owner = str(req.get("user_id") or "")
    if owner and actor and owner != actor:
        raise SystemExit("ERROR: approval denied: user_id mismatch")

    profile = req["profile"]
    chat_id = req.get("chat_id") or ""
    url = req["url"]
    user_prompt = req.get("prompt") or "요약해줘."

    log(f"allow id={args.id} profile={profile} url={url}")

    try:
        fetched = fetch_url(url)
    except Exception as exc:
        msg = f"URL fetch 실패\nID: {args.id}\nURL: {url}\n\n{exc}"
        print(msg, file=sys.stderr)
        if chat_id:
            send_telegram(profile, chat_id, msg)
        raise SystemExit(1)

    prompt = f"""사용자가 URL fetch를 승인했습니다.

원래 요청:
{user_prompt}

URL:
{url}

아래는 hgw 안전 fetcher가 가져온 본문입니다.
웹을 다시 열려고 하지 말고, 아래 본문만 근거로 답하세요.
본문에 없는 내용은 모른다고 답하세요.

----- FETCHED CONTENT START -----
{fetched}
----- FETCHED CONTENT END -----
"""

    try:
        answer = ask_hermes(profile, prompt)
    except Exception as exc:
        msg = f"모델 호출 실패\nID: {args.id}\nURL: {url}\n\n{exc}"
        print(msg, file=sys.stderr)
        if chat_id:
            send_telegram(profile, chat_id, msg)
        raise SystemExit(1)

    print(answer)

    if chat_id:
        send_telegram(profile, chat_id, answer)

    finish_request(req, DONE, "done")


def cmd_deny(args):
    req = load_pending(args.id)

    actor = str(args.user or "")
    owner = str(req.get("user_id") or "")
    if owner and actor and owner != actor:
        raise SystemExit("ERROR: denial rejected: user_id mismatch")

    finish_request(req, REJECTED, "rejected")

    msg = f"URL fetch 거절됨\nID: {args.id}\nURL: {req.get('url')}"
    print(msg)

    if req.get("chat_id"):
        send_telegram(req["profile"], req["chat_id"], msg)

    log(f"deny id={args.id} profile={req.get('profile')} url={req.get('url')}")


def cleanup_expired(silent=False):
    ensure_dirs()
    moved = 0
    t = now()

    for p in list(PENDING.glob("*.json")):
        try:
            req = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue

        if int(req.get("expires_at", 0)) < t:
            req["status"] = "expired"
            req["expired_at"] = t
            save_req(req, EXPIRED)
            p.unlink(missing_ok=True)
            moved += 1

    if not silent:
        print(f"expired moved: {moved}")


def cmd_cleanup(args):
    cleanup_expired(silent=False)

    cutoff = now() - int(args.keep_seconds)
    removed = 0

    for folder in [DONE, REJECTED, EXPIRED]:
        for p in list(folder.glob("*.json")):
            try:
                req = json.loads(p.read_text(encoding="utf-8"))
                ts = int(req.get("done_at") or req.get("rejected_at") or req.get("expired_at") or req.get("created_at") or 0)
            except Exception:
                ts = 0
            if ts and ts < cutoff:
                p.unlink(missing_ok=True)
                removed += 1

    print(f"old removed: {removed}")


def main():
    ap = argparse.ArgumentParser(prog="hgw approve")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("request")
    p.add_argument("profile")
    p.add_argument("url")
    p.add_argument("prompt", nargs="*")
    p.add_argument("--chat")
    p.add_argument("--user")
    p.add_argument("--message-id")
    p.add_argument("--source", default="cli")
    p.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS)
    p.set_defaults(fn=cmd_request)

    p = sub.add_parser("list")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("show")
    p.add_argument("id")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("allow")
    p.add_argument("id")
    p.add_argument("--user")
    p.set_defaults(fn=cmd_allow)

    p = sub.add_parser("deny")
    p.add_argument("id")
    p.add_argument("--user")
    p.set_defaults(fn=cmd_deny)

    p = sub.add_parser("cleanup")
    p.add_argument("--keep-seconds", type=int, default=7 * 24 * 3600)
    p.set_defaults(fn=cmd_cleanup)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
