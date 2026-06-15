#!/data/data/com.termux/files/usr/bin/python
# clip_web_fetch = safe public URL fetcher (Command Line Interface Proxy - Web Fetch)
import argparse
import html
import ipaddress
import socket
import sys
import urllib.parse
import urllib.request
from html.parser import HTMLParser

DEFAULT_TIMEOUT = 15
DEFAULT_MAX_BYTES = 1_000_000


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self.skip += 1
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas"} and self.skip:
            self.skip -= 1
        if tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "article", "section"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip:
            return
        text = data.strip()
        if text:
            self.parts.append(text + " ")

    def get_text(self):
        raw = "".join(self.parts)
        lines = []
        for line in raw.splitlines():
            line = " ".join(line.split())
            if line:
                lines.append(line)
        return "\n".join(lines)


def fail(msg, code=2):
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def is_public_host(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False

    seen = False
    for info in infos:
        ip = info[4][0]
        try:
            addr = ipaddress.ip_address(ip)
        except Exception:
            return False

        if not addr.is_global:
            return False
        seen = True

    return seen


def validate_url(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        fail("only http/https URLs are allowed")
    if not parsed.hostname:
        fail("URL host is missing")
    if not is_public_host(parsed.hostname):
        fail(f"blocked non-public host: {parsed.hostname}")
    return parsed.geturl()


def fetch_url(url, timeout, max_bytes):
    validate_url(url)

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "clip-web-fetch/1.0",
            "Accept": "text/html,text/plain,application/xhtml+xml,*/*;q=0.8",
        },
    )

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        final_url = resp.geturl()
        validate_url(final_url)

        content_type = resp.headers.get("Content-Type", "")
        data = resp.read(max_bytes + 1)

    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]

    encoding = "utf-8"
    if "charset=" in content_type.lower():
        encoding = content_type.split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"

    text = data.decode(encoding, errors="replace")

    if "html" in content_type.lower() or "<html" in text[:1000].lower():
        parser = TextExtractor()
        parser.feed(text)
        text = parser.get_text()
    else:
        text = html.unescape(text)

    text = text.strip()

    print(f"URL: {final_url}")
    print(f"Content-Type: {content_type}")
    print(f"Truncated: {str(truncated).lower()}")
    print()
    print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = ap.parse_args()

    fetch_url(args.url, args.timeout, args.max_bytes)


if __name__ == "__main__":
    main()
