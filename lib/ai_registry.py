#!/usr/bin/env python3
"""Compatibility shim for legacy imports after Stage 6 split."""
from __future__ import annotations
import argparse
import ai_store
from ai_store import *  # noqa: F401,F403
from ai_provider import list_profiles as _list_profiles
from ai_provider import profile_base_dir
from ai_session import *  # noqa: F401,F403

def existing_provider_profiles(provider: str) -> list[str]:
    return [p for p in _list_profiles(provider) if p != "default"]

def load_workdirs(): return ai_store.load_workdirs()
def save_workdirs(data): return ai_store.save_workdirs(data)
def load_gateways(): return ai_store.load_gateways()
def ensure_registry(): return ai_store.ensure_registry()

def main(argv=None) -> int:
    import ai_resource, sys
    p=argparse.ArgumentParser(prog="ai_registry")
    sub=p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ensure")
    s=sub.add_parser("workdirs-list"); s.add_argument("--all", action="store_true")
    s=sub.add_parser("workdirs-add"); s.add_argument("name"); s.add_argument("path"); s.add_argument("--purpose"); s.add_argument("--favorite", action="store_true"); s.add_argument("--create", action="store_true")
    s=sub.add_parser("workdirs-archive"); s.add_argument("name")
    s=sub.add_parser("profiles-list"); s.add_argument("provider", nargs="?")
    sub.add_parser("gateways-list")
    s=sub.add_parser("sessions-refresh"); s.add_argument("--limit", type=int, default=500)
    s=sub.add_parser("sessions-list"); s.add_argument("--provider"); s.add_argument("--profile"); s.add_argument("--cwd"); s.add_argument("--limit", type=int, default=10); s.add_argument("--refresh", action="store_true")
    ns=p.parse_args(argv)
    if ns.cmd=="ensure": ensure_registry(); return 0
    if ns.cmd=="workdirs-list": return ai_resource.workdir_cmd(["list"])
    if ns.cmd=="workdirs-add": return ai_resource.workdir_cmd(["add", ns.name, ns.path])
    if ns.cmd=="workdirs-archive": return ai_resource.workdir_cmd(["archive", ns.name])
    if ns.cmd=="profiles-list": return ai_resource.profile_cmd(["list"] + ([ns.provider] if ns.provider else []))
    if ns.cmd=="gateways-list": return ai_resource.gateway_cmd(["list"])
    if ns.cmd=="sessions-refresh": return ai_resource.session_cmd(["refresh", "--limit", str(ns.limit)])
    if ns.cmd=="sessions-list":
        args=["list", "--limit", str(ns.limit)]
        if ns.provider: args += ["--provider", ns.provider]
        if ns.profile: args += ["--profile", ns.profile]
        if ns.cwd: args += ["-d", ns.cwd]
        if ns.refresh: refresh_session_index(ns.limit)
        return ai_resource.session_cmd(args)
    return 2
if __name__ == "__main__": raise SystemExit(main())
