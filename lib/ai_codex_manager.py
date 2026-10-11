"""Local fallback for the Codex manager profile contract.

Matches manager/src/lib.rs: private profile material only; Core owns shared layout.
"""
from __future__ import annotations
import ctypes
import errno
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile

RESERVED = {"default", "home", "termux"}
LAUNCH_UNSET = ["CODEX_TERMUX_CORE_API", "CODEX_TERMUX_CORE_ENTRYPOINT", "CODEX_SQLITE_HOME"]


def validate_id(name: str, *, custom: bool = False) -> None:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name) or name == "termux" or (custom and name in RESERVED):
        raise ValueError(f"invalid codex manager profile name: {name}")


def inspect(path: Path) -> os.stat_result | None:
    if not path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise ValueError(f"codex manager path is unsafe: {path}")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(info.st_mode) or (current != path and not stat.S_ISDIR(info.st_mode)):
            raise ValueError(f"codex manager path is unsafe: {current}")
    return info


def home_dir() -> Path:
    home = Path(os.environ.get("HOME", ""))
    info = inspect(home)
    if info is None or not stat.S_ISDIR(info.st_mode):
        raise ValueError("codex manager HOME is invalid")
    return home


def private_dir(path: Path, *, create: bool = False) -> bool:
    info = inspect(path)
    if info is None and create:
        # Manager creates each missing ancestor privately, without chmod of existing paths.
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current /= part
            if inspect(current) is None:
                current.mkdir(mode=0o700)
                current.chmod(0o700)
        info = inspect(path)
    if info is None:
        return False
    if not stat.S_ISDIR(info.st_mode) or (stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.geteuid()):
        raise ValueError(f"codex manager directory must have mode 0700: {path}")
    return True


def profiles_dir(*, create: bool = False) -> Path:
    root = home_dir() / ".local/share/codex/manager"
    private_dir(root, create=create)
    profiles = root / "profiles"
    private_dir(profiles, create=create)
    return profiles


def metadata(name: str) -> bytes:
    return f"codex-manager-profile-v1\nid\t{name}\n".encode("ascii")


def complete(profiles: Path, name: str) -> bool:
    try:
        validate_id(name, custom=True)
        profile = profiles / name
        if not private_dir(profile) or not private_dir(profile / "home"):
            return False
        path = profile / "profile.meta"
        info = inspect(path)
        if info is None or not stat.S_ISREG(info.st_mode) or (stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid()):
            return False
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as stream:
            return stream.read(4097) in {metadata(name), b"codex-manager-profile-v2\n"}
    except (ValueError, OSError):
        return False


def list_profiles() -> list[str]:
    profiles = profiles_dir()
    if inspect(profiles) is None:
        return ["default"]
    return ["default", *sorted(
        (path.name for path in profiles.iterdir() if complete(profiles, path.name)),
        key=lambda name: name.encode("ascii"),
    )]



def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def publish(source: Path, destination: Path) -> None:
    # Same atomic no-replace boundary as manager's renameat2.
    libc = ctypes.CDLL(None, use_errno=True)
    args = (-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if hasattr(libc, "renameat2"):
        fn = libc.renameat2
        fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        fn.restype = ctypes.c_int
        result = fn(*args)
    else:
        import platform
        if platform.machine() not in {"aarch64", "arm64"}:
            raise ValueError("atomic manager profile publication is unavailable on this platform")
        result = libc.syscall(ctypes.c_long(276), ctypes.c_int(-100), ctypes.c_char_p(args[1]),
                              ctypes.c_int(-100), ctypes.c_char_p(args[3]), ctypes.c_uint(1))
    if result:
        code = ctypes.get_errno()
        if code == errno.EEXIST:
            raise FileExistsError(code, "codex manager profile already exists", str(destination))
        raise OSError(code, os.strerror(code), str(destination))


def create_profile(name: str) -> Path:
    validate_id(name, custom=True)
    profiles = profiles_dir(create=True)
    destination = profiles / name
    if destination.exists() or destination.is_symlink():
        raise ValueError(f"codex manager profile already exists: {name}")
    temporary = Path(tempfile.mkdtemp(prefix=".create-ai-", dir=profiles))
    try:
        temporary.chmod(0o700)
        (temporary / "home").mkdir(mode=0o700)
        (temporary / "home").chmod(0o700)
        fd = os.open(temporary / "profile.meta", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(metadata(name))
            stream.flush()
            os.fsync(stream.fileno())
        sync_dir(temporary / "home")
        sync_dir(temporary)
        publish(temporary, destination)
        sync_dir(profiles)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination / "home"


def launch_profile(name: str) -> tuple[dict[str, str], list[str]]:
    validate_id(name)
    home = home_dir()
    if name in {"default", "home"}:
        return {}, [*LAUNCH_UNSET, "CODEX_HOME"]
    profiles = profiles_dir()
    if not complete(profiles, name):
        raise ValueError(f"codex manager profile is unavailable: {name}")
    return {"CODEX_HOME": str(home / ".local/share/codex/manager/profiles" / name / "home")}, list(LAUNCH_UNSET)
