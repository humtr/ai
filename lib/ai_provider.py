#!/usr/bin/env python3
from __future__ import annotations
import os
import subprocess
import re
from pathlib import Path
from typing import Any
import ai_spec
import ai_codex_manager

def validate_profile_name(profile: str | None) -> None:
    if not profile or profile == "default": return
    if profile in {"native"} or profile.startswith(".") or "/" in profile or ".." in profile or any(ch.isspace() for ch in profile):
        raise ValueError(f"invalid or reserved profile name: {profile}")

def profile_base_dir(provider: str) -> Path | None:
    if not provider or not ai_spec.is_provider(provider): return None
    if provider == "codex":
        return Path.home() / ".local/share/codex/manager/profiles"
    spec=ai_spec.provider_spec(provider); base=(spec.get("profile") or {}).get("base_dir")
    return Path(base).expanduser() if base else None

def list_profiles(provider: str) -> list[str]:
    if not provider or not ai_spec.is_provider(provider): return ["default"]
    if provider == "codex":
        try:
            names = codex_manager_profiles()
        except ValueError:
            names = ai_codex_manager.list_profiles()
        return names
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
    native_share = Path.home() / ".local" / "share" / "agy"
    if native_share.exists():
        target_share_dir = profile_dir / ".local" / "share"
        target_share_dir.mkdir(parents=True, exist_ok=True)
        link_share = target_share_dir / "agy"
        if link_share.is_dir() and not link_share.is_symlink():
            if any(link_share.iterdir()):
                raise ValueError(f"legacy AGY runtime state needs migration before launch: {link_share}")
            link_share.rmdir()
        if link_share.is_symlink() and link_share.resolve() != native_share.resolve():
            raise ValueError(f"AGY runtime state link is not canonical: {link_share}")
        if not link_share.exists() and not link_share.is_symlink():
            try:
                link_share.symlink_to(native_share)
            except OSError:
                pass

def apply_profile(provider: str, profile: str | None) -> tuple[list[str], dict[str,str]]:
    if provider == "codex":
        selected = profile or "default"
        validate_codex_profile(selected)
        try:
            names = codex_manager_profiles()
        except ValueError:
            env, _ = ai_codex_manager.launch_profile(selected)
            return [], env
        return ["termux", "profile", "use", selected, "--"], {}
    if not profile or profile == "default": return [], {}
    validate_profile_name(profile)
    spec=ai_spec.provider_spec(provider); prof=spec.get("profile") or {}; strat=prof.get("strategy","none")
    base=Path(str(prof.get("base_dir") or "")).expanduser(); profile_dir=base/profile
    if prof.get("supported") and base and not profile_dir.is_dir():
        try:
            profile_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            raise SystemExit(f"ERROR: failed to create profile directory: {provider}/{profile} ({profile_dir}): {e}")
    ensure_shared_runtime(provider, profile_dir)
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

def provider_binary(provider: str) -> str:
    if not provider or not ai_spec.is_provider(provider): return provider
    return str(ai_spec.provider_spec(provider).get("binary") or provider)

def provider_check(provider: str) -> dict[str, Any]:
    if not provider or not ai_spec.is_provider(provider):
        return {"name": provider, "binary": provider, "profile_base": "", "profile_base_exists": False, "profile_strategy": "none", "session_strategy": "none"}
    spec=ai_spec.provider_spec(provider); base=profile_base_dir(provider)
    return {"name": provider, "binary": provider_binary(provider), "profile_base": str(base or ""), "profile_base_exists": bool(base and base.exists()), "profile_strategy": "codex_manager" if provider == "codex" else (spec.get("profile") or {}).get("strategy","none"), "session_strategy": (spec.get("session") or {}).get("strategy","none")}


def validate_codex_profile(profile: str) -> None:
    ai_codex_manager.validate_id(profile)


def codex_manager_profiles() -> list[str]:
    names = codex_manager("list").splitlines()
    if not names or names[0] != "default" or len(names) != len(set(names)):
        raise ValueError("codex manager returned an invalid profile list")
    for name in names[1:]:
        ai_codex_manager.validate_id(name, custom=True)
    return names


def codex_manager(action: str, *names: str) -> str:
    for name in names:
        validate_codex_profile(name)
    try:
        result = subprocess.run(
            [provider_binary("codex"), "termux", "profile", action, *names],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"codex manager {action} unavailable: {error}") from error
    if result.returncode:
        detail = result.stderr.strip() or "operation failed"
        raise ValueError(f"codex manager {action}: {detail}")
    return result.stdout


def profile_path(provider: str, profile: str) -> Path:
    if provider == "codex":
        validate_codex_profile(profile)
    else:
        validate_profile_name(profile)
    base = profile_base_dir(provider)
    if not base or profile == "default":
        raise ValueError("default profile cannot be modified")
    path = base / profile
    return path / "home" if provider == "codex" else path


def create_profile(provider: str, profile: str) -> Path:
    path = profile_path(provider, profile)
    if provider == "codex":
        ai_codex_manager.validate_id(profile, custom=True)
        try:
            codex_manager("create", profile)
        except ValueError:
            return ai_codex_manager.create_profile(profile)
    else:
        path.mkdir(parents=True, exist_ok=True)
        ensure_shared_runtime(provider, path)
    return path


def rename_profile(provider: str, profile: str, name: str) -> None:
    if provider == "codex":
        ai_codex_manager.validate_id(profile, custom=True)
        ai_codex_manager.validate_id(name, custom=True)
        codex_manager("rename", profile, name)
        names = codex_manager_profiles()
        if profile in names or name not in names:
            raise ValueError("codex manager did not complete the profile rename; refresh the profile list")
        return
    source = profile_path(provider, profile)
    target = profile_path(provider, name)
    if target.exists() or target.is_symlink():
        raise ValueError(f"profile already exists: {name}")
    if source.is_symlink() or not source.is_dir():
        raise ValueError(f"profile not found or unsafe: {profile}")
    source.rename(target)


def delete_profile(provider: str, profile: str) -> None:
    if provider == "codex":
        ai_codex_manager.validate_id(profile, custom=True)
        codex_manager("delete", profile)
        if profile in codex_manager_profiles():
            raise ValueError("codex manager did not delete the profile; no change confirmed")
        return
    import shutil
    path = profile_path(provider, profile)
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"profile not found or unsafe: {profile}")
    shutil.rmtree(path)


def ensure_shared_runtime(provider: str, profile_dir: Path) -> None:
    # Keep account files private; share only upstream conversation storage.
    home = Path.home()
    entries = {
        "agy": [(".gemini/antigravity-cli/conversations", ".gemini/antigravity-cli/conversations"),
                (".gemini/antigravity-cli/brain", ".gemini/antigravity-cli/brain"),
                (".gemini/tmp", ".gemini/tmp")],
        "hermes": [("sessions", ".hermes/sessions"), ("state.db", ".hermes/state.db")],
        "opencode": [(".local/share/opencode/storage", ".local/share/opencode/storage"),
                     (".local/share/opencode/opencode.db", ".local/share/opencode/opencode.db")],
    }
    shared_entries = entries.get(provider, [])
    # Validate the whole topology before changing any entry.
    for relative, native in shared_entries:
        link = profile_dir / relative
        target = home / native
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if link.exists() or link.is_symlink():
            if not (link.is_dir() and not link.is_symlink() and not any(link.iterdir())):
                raise ValueError(f"legacy session storage needs migration before launch: {link}")
    for relative, native in shared_entries:
        link = profile_dir / relative
        target = home / native
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if link.exists() or link.is_symlink():
            if link.is_dir() and not link.is_symlink() and not any(link.iterdir()):
                link.rmdir()
            else:
                raise ValueError(f"legacy session storage needs migration before launch: {link}")
        link.parent.mkdir(parents=True, exist_ok=True)
        if target.suffix != ".db":
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
    if provider == "agy":
        ensure_agy_profile_runtime(profile_dir)
