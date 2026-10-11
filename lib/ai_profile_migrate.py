"""Preserve legacy Codex homes while registering them in manager topology."""
from __future__ import annotations
import os
import shutil
import tempfile
from pathlib import Path
import ai_codex_manager as manager

SHARED = ["sessions", "archived_sessions", "thread-writer-locks", "rollout-migrations",
          "memories", "memories_v2", "tui-thread-reference-capabilities",
          "session_index.jsonl", "history.jsonl", "installation_id"]


def migrate_legacy_profiles() -> list[str]:
    home = manager.home_dir()
    legacy = home / ".codex-profiles"
    if not legacy.is_dir():
        return []
    sources = []
    profiles = manager.profiles_dir(create=True)
    for source in sorted(legacy.iterdir()):
        if source.name.startswith('.'):
            continue
        manager.validate_id(source.name, custom=True)
        destination = profiles / source.name
        if source.is_symlink():
            if source.readlink() == destination / 'home' and manager.complete(profiles, source.name):
                continue
            raise ValueError(f"unrecognized legacy profile link: {source}")
        if not manager.private_dir(source):
            continue
        if destination.exists() or destination.is_symlink():
            raise ValueError(f"manager profile collision: {source.name}")
        for name in SHARED:
            path = source / name
            if path.is_symlink() and path.readlink() == home / '.codex' / name:
                continue
            if path.exists() or path.is_symlink():
                if not (path.is_dir() and not path.is_symlink() and not any(path.iterdir())):
                    raise ValueError(f"legacy shared topology needs transition: {path}")
        sources.append(source)
    # Readable ownership/process state is required before changing account paths.
    for process in Path('/proc').iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.geteuid():
                continue
            info = (process / 'stat').read_text().rsplit(')', 1)[1].split()
            if info[0] in {'Z', 'X'}:
                continue
            environment = (process / 'environ').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError, IndexError) as error:
            raise ValueError(f"cannot verify legacy profile inactivity (PID {process.name})") from error
        for source in sources:
            if os.fsencode('CODEX_HOME=' + str(source)) in environment:
                raise ValueError(f"finish active legacy profile before migration: {source.name} (PID {process.name})")
    moved = []
    for source in sources:
        destination = profiles / source.name
        temporary = Path(tempfile.mkdtemp(prefix='.migrate-ai-', dir=profiles))
        temporary.chmod(0o700)
        target = temporary / 'home'
        published = False
        try:
            # Hidden staging is never a discoverable incomplete account.
            with (temporary / 'profile.meta').open('xb') as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(manager.metadata(source.name))
                stream.flush()
                os.fsync(stream.fileno())
            manager.publish(source, target)
            manager.sync_dir(source.parent)
            manager.sync_dir(target)
            manager.sync_dir(temporary)
            manager.publish(temporary, destination)
            published = True
            manager.sync_dir(profiles)
            moved.append(source.name)
        except BaseException:
            if not published and target.exists():
                # Never overwrite a concurrent legacy home or discard its data.
                # A failed recovery leaves the private staged home intact.
                manager.publish(target, source)
                manager.sync_dir(source.parent)
            raise
        finally:
            if temporary.exists() and not target.exists():
                shutil.rmtree(temporary)
    if not any(legacy.iterdir()):
        legacy.rmdir()
    return moved


if __name__ == '__main__':
    for name in migrate_legacy_profiles():
        print(f"registered legacy profile: {name}")
