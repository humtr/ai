#!/usr/bin/env python3
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import ai_spec

def validate_profile_name(profile: str | None) -> None:
    if not profile or profile == "default": return
    if profile in {"native"} or profile.startswith(".") or "/" in profile or ".." in profile or any(ch.isspace() for ch in profile):
        raise ValueError(f"invalid or reserved profile name: {profile}")

def profile_base_dir(provider: str) -> Path | None:
    spec=ai_spec.provider_spec(provider); base=(spec.get("profile") or {}).get("base_dir")
    return Path(base).expanduser() if base else None

def list_profiles(provider: str) -> list[str]:
    spec=ai_spec.provider_spec(provider); prof=spec.get("profile") or {}
    names=["default"]
    if not prof.get("supported", False): return names
    base=profile_base_dir(provider)
    if base and base.is_dir():
        for child in sorted(base.iterdir(), key=lambda p:p.name.lower()):
            if child.is_dir() and not child.name.startswith(".") and child.name not in {"default","native"}: names.append(child.name)
    return names

def ensure_agy_profile_runtime(profile_dir: Path) -> None:
    native_runtime = Path.home() / ".local" / "lib" / "agy"
    if native_runtime.exists():
        target_dir = profile_dir / ".local" / "lib"
        target_dir.mkdir(parents=True, exist_ok=True)
        link_path = target_dir / "agy"
        if not link_path.exists() and not link_path.is_symlink():
            try:
                link_path.symlink_to(native_runtime)
            except OSError:
                pass

def apply_profile(provider: str, profile: str | None) -> tuple[list[str], dict[str,str]]:
    if not profile or profile == "default": return [], {}
    validate_profile_name(profile)
    spec=ai_spec.provider_spec(provider); prof=spec.get("profile") or {}; strat=prof.get("strategy","none")
    base=Path(str(prof.get("base_dir") or "")).expanduser(); profile_dir=base/profile
    if prof.get("supported") and base and not profile_dir.is_dir():
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise SystemExit(f"ERROR: failed to create profile directory: {provider}/{profile} ({profile_dir}): {e}")
    if provider == "agy":
        ensure_agy_profile_runtime(profile_dir)
    if strat == "env_home":
        return [], {str(prof.get("env_var") or "AI_PROVIDER_HOME"): str(profile_dir)}
    if strat == "temp_home_symlink":
        temp_base=Path(str(prof.get("temp_home_base") or "~/.cache/ai/home")).expanduser()
        run_home=temp_base.parent / f"{temp_base.name}-{profile}"
        run_home.mkdir(parents=True, exist_ok=True)
        symlink=run_home / str(prof.get("symlink_name") or f".{provider}")
        if symlink.exists() or symlink.is_symlink(): symlink.unlink()
        symlink.symlink_to(profile_dir)
        return [], {"HOME": str(run_home)}
    if strat == "native_arg":
        return [str(prof.get("arg") or "--profile"), profile], {}
    if strat == "profile_use":
        # Kept as fallback strategy only. It mutates provider active profile.
        return [], {"AI_PROFILE_USE": profile}
    return [], {}

def provider_binary(provider: str) -> str: return str(ai_spec.provider_spec(provider).get("binary") or provider)

def provider_check(provider: str) -> dict[str, Any]:
    spec=ai_spec.provider_spec(provider); base=profile_base_dir(provider)
    return {"name": provider, "binary": provider_binary(provider), "profile_base": str(base or ""), "profile_base_exists": bool(base and base.exists()), "profile_strategy": (spec.get("profile") or {}).get("strategy","none"), "session_strategy": (spec.get("session") or {}).get("strategy","none")}
