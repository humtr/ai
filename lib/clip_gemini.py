#!/data/data/com.termux/files/usr/bin/python
# clip_gemini = Command Line Interface Proxy - Gemini
import argparse
import json
import os
import re
import shlex
import subprocess
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Tuple


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787
DEFAULT_PROFILE = os.environ.get("CLIP_GEMINI_PROFILE", "tg")
DEFAULT_MODEL = os.environ.get("CLIP_GEMINI_MODEL", "gemini-2.5-flash-lite")
DEFAULT_PUBLIC_MODEL = os.environ.get("CLIP_GEMINI_PUBLIC_MODEL", "clip-gemini")
DEFAULT_TIMEOUT = int(os.environ.get("CLIP_GEMINI_TIMEOUT", "120"))
DEFAULT_ROUTES_FILE = os.environ.get(
    "CLIP_GEMINI_ROUTES_FILE",
    str(Path.home() / ".config/clip/clip_gemini.routes.json"),
)

# Use absolute node path on Termux by default to bypass shebang /usr/bin/env resolution issues
if Path("/data/data/com.termux/files/usr/bin/gemini").exists():
    DEFAULT_EXEC_TEMPLATE = "node /data/data/com.termux/files/usr/bin/gemini --skip-trust -p {prompt} --output-format json"
else:
    DEFAULT_EXEC_TEMPLATE = "gemini --skip-trust -p {prompt} --output-format json"


def get_tmp_dir() -> Path:
    base = os.environ.get("TMPDIR") or str(Path.home() / "tmp")
    p = Path(base) / "clip"
    p.mkdir(parents=True, exist_ok=True)
    return p


LOG_FILE = get_tmp_dir() / "clip_gemini.log"


def log(msg: str) -> None:
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except Exception:
        pass


def extract_text_content(content: Any) -> str:
    if content is None:
        return ""

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if item.get("type") in ("text", "input_text"):
                    parts.append(str(item.get("text", "")))
                elif "text" in item:
                    parts.append(str(item.get("text", "")))
        return "\n".join(x for x in parts if x)

    return str(content)


_CLIP_AT_PATH_RE = re.compile(
    r'(?<![\\w.+-])@(?=(?:[./~]|[A-Za-z0-9_.-]+/))'
)

_CLIP_HERMES_SKILLS_RE = re.compile(
    r'<available_skills>.*?</available_skills>',
    re.S,
)

_CLIP_REFERENCED_FILES_RE = re.compile(
    r'\\n--- Content from referenced files ---.*?\\n--- End of content ---',
    re.S,
)

def guard_gemini_prompt_text(text: str) -> str:
    if not isinstance(text, str) or not text:
        return text

    text = _CLIP_HERMES_SKILLS_RE.sub(
        '<available_skills omitted by clip_gemini prompt guard>',
        text,
    )

    text = _CLIP_REFERENCED_FILES_RE.sub(
        '\\n[referenced file contents omitted by clip_gemini prompt guard]\\n',
        text,
    )

    text = _CLIP_AT_PATH_RE.sub('@\u200b', text)
    return text


def messages_to_prompt(messages: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []

    for msg in messages:
        role = msg.get("role", "user")
        content = extract_text_content(msg.get("content", ""))
        content = guard_gemini_prompt_text(content)

        if not content:
            continue

        if role == "system":
            blocks.append(f"[system]\\n{content}")
        elif role == "assistant":
            blocks.append(f"[assistant]\\n{content}")
        elif role == "tool":
            name = msg.get("name") or msg.get("tool_call_id") or "tool"
            blocks.append(f"[tool:{name}]\\n{content}")
        else:
            blocks.append(f"[user]\\n{content}")

    return guard_gemini_prompt_text("\\n\\n".join(blocks).strip())


def parse_gemini_json(stdout: str) -> Dict[str, Any]:
    text = stdout.strip()
    if not text:
        raise ValueError("empty stdout from gemini")

    start = text.find("{")
    end = text.rfind("}")

    if start < 0 or end < start:
        raise ValueError(f"no JSON object found in gemini stdout: {text[:500]}")

    return json.loads(text[start:end + 1])


def load_routes(routes_file: str, fallback_public: str, fallback_profile: str, fallback_model: str) -> Dict[str, Dict[str, Any]]:
    routes: Dict[str, Dict[str, Any]] = {}

    p = Path(routes_file)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for name, route in data.items():
                    if isinstance(route, dict):
                        routes[str(name)] = dict(route)
        except Exception as e:
            log(f"ROUTES_LOAD_ERROR file={routes_file} error={e}")

    if fallback_public not in routes:
        routes[fallback_public] = {
            "profile": fallback_profile,
            "model": fallback_model,
            "skip_trust": True,
        }

    return routes


def normalize_route(route: Dict[str, Any], fallback_profile: str, fallback_model: str, fallback_timeout: int) -> Dict[str, Any]:
    return {
        "profile": str(route.get("profile") or fallback_profile),
        "model": str(route.get("model") or fallback_model),
        "skip_trust": bool(route.get("skip_trust", True)),
        "timeout": int(route.get("timeout") or fallback_timeout),
    }


def call_gemini_decoupled(prompt: str, route_name: str, route: Dict[str, Any], default_template: str) -> Tuple[str, Dict[str, Any]]:
    prompt = guard_gemini_prompt_text(prompt)
    profile = route["profile"]
    model = route["model"]
    timeout = route["timeout"]

    exec_template = route.get("exec_template") or os.environ.get("CLIP_GEMINI_TEMPLATE") or default_template

    cmd_str = exec_template
    if "{profile}" in cmd_str:
        cmd_str = cmd_str.replace("{profile}", profile)
    if "{model}" in cmd_str:
        cmd_str = cmd_str.replace("{model}", model or "")

    argv = shlex.split(cmd_str)
    argv = [arg.replace("{prompt}", prompt) if "{prompt}" in arg else arg for arg in argv]

    env = os.environ.copy()
    if profile and profile != "default":
        temp_base = Path("~/.cache/clip/gemini-home").expanduser()
        run_home = temp_base.parent / f"{temp_base.name}-{profile}"
        run_home.mkdir(parents=True, exist_ok=True)
        symlink = run_home / ".gemini"
        if symlink.exists() or symlink.is_symlink():
            symlink.unlink()
        profile_dir = Path("~/.gemini-profiles").expanduser() / profile
        profile_dir.mkdir(parents=True, exist_ok=True)
        symlink.symlink_to(profile_dir)
        env["HOME"] = str(run_home)

    log(f"CALL route={route_name} profile={profile} model={model} chars={len(prompt)}")
    started = time.time()

    proc = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        timeout=timeout,
        input="",
        env=env,
    )

    elapsed = time.time() - started
    log(
        f"DONE route={route_name} rc={proc.returncode} elapsed={elapsed:.2f}s "
        f"stdout={len(proc.stdout)} stderr={len(proc.stderr)}"
    )

    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or f"gemini exited with code {proc.returncode}"
        raise RuntimeError(err[:4000])

    data = parse_gemini_json(proc.stdout)
    response = data.get("response", "")
    if response is None:
        response = ""
    return str(response), data


def usage_from_stats(data: Dict[str, Any]) -> Dict[str, int]:
    stats = data.get("stats", {})
    models = stats.get("models", {})

    if isinstance(models, dict) and models:
        first = next(iter(models.values()))
        tokens = first.get("tokens", {}) if isinstance(first, dict) else {}
    else:
        tokens = {}

    prompt_tokens = int(tokens.get("prompt") or tokens.get("input") or 0)
    completion_tokens = int(tokens.get("candidates") or 0)
    total_tokens = int(tokens.get("total") or prompt_tokens + completion_tokens)

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


class CLIPGHandler(BaseHTTPRequestHandler):
    server_version = "clip-gemini/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        log(f"{self.address_string()} {fmt % args}")

    def routes(self) -> Dict[str, Dict[str, Any]]:
        return load_routes(
            self.server.routes_file,
            self.server.public_model,
            self.server.profile,
            self.server.model,
        )

    def send_json(self, code: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(n).decode("utf-8", errors="replace")
        if not raw:
            return {}
        return json.loads(raw)

    def do_GET(self) -> None:
        if self.path in ("/", "/health", "/v1/health"):
            routes = self.routes()
            self.send_json(200, {
                "ok": True,
                "service": "clip-gemini",
                "version": "0.1",
                "profile": self.server.profile,
                "model": self.server.model,
                "public_model": self.server.public_model,
                "routes_file": self.server.routes_file,
                "routes": sorted(routes.keys()),
            })
            return

        if self.path == "/v1/models":
            now = int(time.time())
            routes = self.routes()
            self.send_json(200, {
                "object": "list",
                "data": [
                    {
                        "id": name,
                        "object": "model",
                        "created": now,
                        "owned_by": "clip-gemini",
                    }
                    for name in sorted(routes.keys())
                ],
            })
            return

        self.send_json(404, {
            "error": {
                "message": f"not found: {self.path}",
                "type": "not_found",
            }
        })

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_json(404, {
                "error": {
                    "message": f"not found: {self.path}",
                    "type": "not_found",
                }
            })
            return

        try:
            req = self.read_json()
            messages = req.get("messages", [])
            stream = bool(req.get("stream", False))

            if not isinstance(messages, list):
                raise ValueError("messages must be a list")

            prompt = messages_to_prompt(messages)

            if not prompt:
                prompt = str(req.get("prompt", "")).strip()

            if not prompt:
                raise ValueError("empty prompt/messages")

            requested_model = str(req.get("model") or self.server.public_model)
            routes = self.routes()

            if requested_model in routes:
                route_name = requested_model
                raw_route = routes[requested_model]
            else:
                route_name = self.server.public_model
                raw_route = routes.get(route_name, {
                    "profile": self.server.profile,
                    "model": self.server.model,
                    "skip_trust": True,
                })
                log(f"ROUTE_FALLBACK requested={requested_model} fallback={route_name}")

            route = normalize_route(
                raw_route,
                fallback_profile=self.server.profile,
                fallback_model=self.server.model,
                fallback_timeout=self.server.timeout,
            )

            content, gm_data = call_gemini_decoupled(
                prompt,
                route_name=route_name,
                route=route,
                default_template=self.server.exec_template,
            )

            if stream:
                self.send_stream_response(requested_model, content)
            else:
                self.send_completion_response(requested_model, content, gm_data)

        except subprocess.TimeoutExpired:
            self.send_json(504, {
                "error": {
                    "message": f"gemini timed out after {self.server.timeout}s",
                    "type": "timeout",
                }
            })
        except Exception as e:
            log(f"ERROR {type(e).__name__}: {e}")
            self.send_json(502, {
                "error": {
                    "message": str(e),
                    "type": "clip_gemini_error",
                }
            })

    def send_completion_response(self, model: str, content: str, gm_data: Dict[str, Any]) -> None:
        now = int(time.time())
        cid = f"chatcmpl-clip-gemini-{uuid.uuid4().hex[:16]}"

        self.send_json(200, {
            "id": cid,
            "object": "chat.completion",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": usage_from_stats(gm_data),
        })

    def send_stream_response(self, model: str, content: str) -> None:
        now = int(time.time())
        cid = f"chatcmpl-clip-gemini-{uuid.uuid4().hex[:16]}"

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        first = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": None,
                }
            ],
        }

        final = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": now,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }

        for obj in (first, final):
            self.wfile.write(("data: " + json.dumps(obj, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class CLIPGServer(ThreadingHTTPServer):
    def __init__(
        self,
        addr: Tuple[str, int],
        profile: str,
        model: str,
        public_model: str,
        timeout: int,
        routes_file: str,
        exec_template: str,
    ):
        super().__init__(addr, CLIPGHandler)
        self.profile = profile
        self.model = model
        self.public_model = public_model
        self.timeout = timeout
        self.routes_file = routes_file
        self.exec_template = exec_template


def serve(args: argparse.Namespace) -> None:
    server = CLIPGServer(
        (args.host, args.port),
        profile=args.profile,
        model=args.model,
        public_model=args.public_model,
        timeout=args.timeout,
        routes_file=args.routes_file,
        exec_template=args.exec_template,
    )

    log(
        f"START host={args.host} port={args.port} "
        f"profile={args.profile} model={args.model} "
        f"public_model={args.public_model} routes_file={args.routes_file} "
        f"exec_template={args.exec_template}"
    )

    print(f"clip-gemini listening on http://{args.host}:{args.port}/v1")
    print(f"profile={args.profile}")
    print(f"model={args.model}")
    print(f"public_model={args.public_model}")
    print(f"routes_file={args.routes_file}")
    print(f"exec_template={args.exec_template}")
    print(f"log={LOG_FILE}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
        print("clip-gemini stopped")


def main() -> None:
    parser = argparse.ArgumentParser(prog="clip-gemini")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("serve")
    p.add_argument("--host", default=os.environ.get("CLIP_GEMINI_HOST", DEFAULT_HOST))
    p.add_argument("--port", type=int, default=int(os.environ.get("CLIP_GEMINI_PORT", DEFAULT_PORT)))
    p.add_argument("--profile", default=DEFAULT_PROFILE)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--public-model", default=DEFAULT_PUBLIC_MODEL)
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    p.add_argument("--routes-file", default=os.environ.get("CLIP_GEMINI_ROUTES_FILE", DEFAULT_ROUTES_FILE))
    p.add_argument("--exec-template", default=os.environ.get("CLIP_GEMINI_TEMPLATE", DEFAULT_EXEC_TEMPLATE))

    args = parser.parse_args()

    if args.cmd == "serve":
        serve(args)
    else:
        parser.print_help()
        raise SystemExit(2)


if __name__ == "__main__":
    main()
