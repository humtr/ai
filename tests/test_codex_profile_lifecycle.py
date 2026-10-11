#!/usr/bin/env python3
"""Exercise AI lifecycle against the installed manager with isolated profiles."""
from __future__ import annotations
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'lib'))
import ai_codex_manager
import ai_provider
import ai_tui


def main() -> None:
    state = Path.home() / '.local/share/codex/core/activation-state'
    if not state.is_file():
        print('SKIP installed manager lifecycle: no activation state')
        return
    records = dict(line.split('=', 1) for line in state.read_text().splitlines() if '=' in line)
    generation = Path.home() / '.local/lib/codex/core/generations' / records['current']
    manager = generation / 'manager'
    core = generation / 'core'
    if not manager.is_file():
        print('SKIP installed manager lifecycle: no manager artifact')
        return
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        core_fixture = home / 'core-fixture'
        shutil.copyfile(sys.executable, core_fixture)
        core_fixture.chmod(0o700)
        adapter = home / 'codex-fixture'
        adapter.write_text('#!' + sys.executable + '\n' + f'''
import os,sys
assert sys.argv[1] == 'termux'
os.environ['CODEX_TERMUX_CORE_API'] = 'codex-manager-core-v1'
os.environ['CODEX_TERMUX_CORE_ENTRYPOINT'] = {str(core_fixture)!r}
os.execv({str(manager)!r}, [{str(manager)!r}, *sys.argv[2:]])
''')
        adapter.chmod(0o700)
        with patch.dict(os.environ, {'HOME': tmp}), patch.object(ai_provider, 'provider_binary', return_value=str(adapter)):
            ai_provider.create_profile('codex', 'fixture')
            profile = ai_provider.profile_path('codex', 'fixture')
            (profile / 'auth.json').write_text('isolated-account')
            shared = home / '.codex/sessions/shared.jsonl'
            shared.parent.mkdir(parents=True)
            shared.write_text('preserved conversation')
            (profile / 'sessions').symlink_to(shared.parent)
            assert ai_provider.list_profiles('codex') == ['default', 'fixture']

            app = ai_tui.App.__new__(ai_tui.App)
            app.providers = ['codex']
            app.profiles = ['default', 'fixture']
            app.profile_memory = {}
            app.indices = {'provider': 0, 'profile': 1}
            app.prompt = lambda *args, **kwargs: 'renamed'
            def reload():
                app.profiles = ai_provider.list_profiles('codex')
                app.indices['profile'] = 0
            app.reload = reload
            app.rename_profile()
            assert app.current_profile_label() == 'renamed'
            assert ai_provider.list_profiles('codex') == ['default', 'renamed']
            renamed = ai_provider.profile_path('codex', 'renamed')
            assert (renamed / 'auth.json').read_text() == 'isolated-account'
            assert (renamed.parent / 'profile.meta').read_bytes() == b'codex-manager-profile-v2\n'
            with patch.object(ai_provider, 'codex_manager_profiles', side_effect=ValueError('unavailable')):
                assert ai_provider.list_profiles('codex') == ['default', 'renamed']
                assert ai_provider.apply_profile('codex', 'renamed')[1]['CODEX_HOME'] == str(renamed)

            # A protected default must fail visibly and retain selection/data.
            ai_provider.codex_manager('default', 'renamed')
            app.confirm_delete = lambda *args: True
            app.delete_profile()
            assert 'choose another default profile' in app.message
            assert app.current_profile_label() == 'renamed'
            assert renamed.is_dir()
            ai_provider.codex_manager('default', 'default')

            # Successful exit with no mutation is not reported as deletion.
            with patch.object(ai_provider, 'codex_manager', return_value=''), \
                    patch.object(ai_provider, 'codex_manager_profiles', return_value=['default', 'renamed']):
                try:
                    ai_provider.delete_profile('codex', 'renamed')
                except ValueError as error:
                    assert 'did not delete' in str(error)
                else:
                    raise AssertionError('no-op manager result was reported as deletion')

            worker = subprocess.Popen(
                [str(core_fixture), '-c', 'import time; print("ready",flush=True); time.sleep(30)'],
                env={**os.environ, 'CODEX_HOME': str(renamed)}, stdout=subprocess.PIPE, text=True,
            )
            try:
                assert worker.stdout is not None and worker.stdout.readline().strip() == 'ready'
                app.delete_profile()
                assert 'profile is in use' in app.message, app.message
                assert renamed.is_dir() and app.current_profile_label() == 'renamed'
            finally:
                worker.terminate()
                worker.wait(timeout=5)
                worker.stdout.close()

            class Screen:
                keys = iter([ord('y'), ord('e'), ord('s'), 10])
                def getmaxyx(self): return (40, 100)
                def getch(self): return next(self.keys)
                def move(self, *args): pass
            app.stdscr = Screen()
            app.draw_popup_window = lambda **kwargs: None
            app.draw = lambda: None
            app.confirm_delete = lambda label: ai_tui.App.confirm_delete(app, label)
            with patch.object(ai_tui.curses, 'noecho'), patch.object(ai_tui.curses, 'curs_set'):
                app.delete_profile()
            assert app.message == 'deleted profile: codex/renamed'
            assert app.profiles == ['default'] and app.current_profile_label() == 'default'
            assert ai_provider.codex_manager_profiles() == ai_codex_manager.list_profiles() == ['default']
            assert not renamed.parent.exists()
            assert shared.read_text() == 'preserved conversation'
            ai_provider.create_profile('codex', 'again')
            ai_provider.delete_profile('codex', 'again')
            assert ai_provider.list_profiles('codex') == ['default']
    print('PASS actual manager create/rename/delete, TUI yes, blocked default, v2 fallback, shared session preservation')


if __name__ == '__main__':
    main()
