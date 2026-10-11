#!/usr/bin/env python3
import json
import os
import subprocess
import shutil
import sys
import tempfile
import time
import tomllib
import dataclasses
import pty
import fcntl
import struct
import termios
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ai_tmux
import ai_plan
import ai_cli

def test_title_preservation():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        path = root / 'config.toml'
        original = '# retain\nmodel="example"\n[tui]\nterminal_title = [\n "project-name", "activity"\n]\nother=true\n[features]\nfoo=false\n'
        path.write_text(original)
        path.chmod(0o640)
        ai_tmux.prepare_title(root)
        changed = path.read_text()
        assert tomllib.loads(changed)['tui']['terminal_title'] == ['thread-id', 'project-name', 'activity']
        assert changed.startswith('# retain\nmodel="example"\n')
        assert changed.endswith('other=true\n[features]\nfoo=false\n')
        assert path.stat().st_mode & 0o777 == 0o640
        ai_tmux.prepare_title(root)
        assert path.read_text() == changed
        assert len(list(root.iterdir())) == 1
        path.write_text('tui={terminal_title=["activity"]}\n')
        try: ai_tmux.prepare_title(root)
        except ValueError: pass
        else: raise AssertionError('inline title must fail without config mutation')
        assert path.read_text() == 'tui={terminal_title=["activity"]}\n'
        path.unlink()
        ai_tmux.prepare_title(root)
        assert tomllib.loads(path.read_text())['tui']['terminal_title'] == ['thread-id','activity','thread-name','project-name']


def test_cli_boundary():
    calls=[]
    with patch.object(ai_plan, 'execute_plan', side_effect=lambda plan: calls.append(plan) or 0):
        assert ai_cli.run_command('run', ['codex','--tmux','--','--enable','abc']) == 0
        assert calls[-1].tmux_provider == 'codex'
        assert calls[-1].argv[-2:] == ['--enable','abc']
        assert ai_cli.run_command('run', ['codex','--','--tmux']) == 0
        assert calls[-1].tmux_provider is None and calls[-1].argv[-1] == '--tmux'
        assert ai_cli.run_command('run', ['codex','--tmux=status','--','--tmux=off']) == 0
        assert calls[-1].tmux_status and calls[-1].argv[-1] == '--tmux=off'
        assert ai_cli.run_command('run', ['codex','--tmux=hidden']) == 0
        assert not calls[-1].tmux_status and calls[-1].tmux_provider == 'codex'
        assert ai_cli.run_command('run', ['codex','--tmux=off']) == 0
        assert calls[-1].tmux_provider is None
        assert ai_cli.run_command('run', ['codex','--tmux=wrong']) == 2
        assert ai_cli.run_command('run', ['codex','--tmux=off','--tmux']) == 2
        try: ai_plan.build_execution_plan(ai_plan.LaunchSpec(command='run',provider='codex',tmux='wrong'))
        except SystemExit: pass
        else: raise AssertionError('invalid mode accepted')
        assert ai_cli.run_command('run', ['codex','--tmux','--tmux']) == 2
        assert ai_cli.run_command('ask', ['codex','--tmux','--','hello']) == 2


def test_native_tmux_color_environment():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        socket = str(root / 'tmux.sock')
        def tm(*args):
            return subprocess.check_output(['tmux', '-S', socket, *args], text=True).strip()
        tm('-f', '/dev/null', 'new-session', '-d', '-s', 'isolated', 'sleep 90')
        provider = root / 'color-provider'
        provider.write_text('#!' + sys.executable + '\nimport json,os,sys,time\nkeys=' + repr((*ai_tmux.COLOR_ENVIRONMENT, 'TERM', 'TERM_PROGRAM')) + '\nwith open(sys.argv[1]+".tmp","w") as out: json.dump({k:os.environ.get(k) for k in keys},out)\nos.replace(sys.argv[1]+".tmp",sys.argv[1])\nprint("plain" if os.environ.get("NO_COLOR") else "\\x1b[1;38;2;12;200;90mcolored\\x1b[0m",flush=True)\ntime.sleep(90)\n')
        provider.chmod(0o700)
        try:
            for key in ai_tmux.COLOR_ENVIRONMENT:
                tm('set-environment', '-g', key, 'stale')
            caller = {k:v for k,v in os.environ.items() if k not in ai_tmux.COLOR_ENVIRONMENT}
            caller.update(HOME=str(root), TMUX=socket+',1,0', TMUX_PANE='%0', TERM='xterm-256color')
            for index, preferences in enumerate(({'COLORTERM':'truecolor'}, {'NO_COLOR':'1'}, {'FORCE_COLOR':'1','COLORFGBG':'15;0'})):
                marker = root / f'color-{index}.json'
                plan = ai_plan.ExecutionPlan(argv=[str(provider), str(marker)], env={}, cwd=str(root), display='')
                with patch.dict(os.environ, {**caller, **preferences}, clear=True):
                    assert ai_tmux.launch(plan, 'example') == 0
                deadline = time.monotonic() + 3
                while not marker.exists() and time.monotonic() < deadline: time.sleep(.05)
                values = json.loads(marker.read_text())
                for key in ai_tmux.COLOR_ENVIRONMENT: assert values[key] == preferences.get(key), (key, values)
                assert values['TERM'].startswith(('screen', 'tmux')) and values['TERM'] != caller['TERM']
                assert values['TERM_PROGRAM'] == 'tmux'
                deadline = time.monotonic() + 3
                pane = tm('display-message', '-p', '#{pane_id}')
                while time.monotonic() < deadline:
                    capture = tm('capture-pane', '-p', '-e', '-t', pane)
                    if ('plain' if index == 1 else 'colored') in capture: break
                    time.sleep(.05)
                assert ('plain' if index == 1 else 'colored') in capture
                if index != 1: assert '\x1b[' in capture
                tm('kill-pane', '-t', pane)
        finally:
            subprocess.run(['tmux', '-S', socket, 'kill-server'], capture_output=True)


def test_native_status_mouse_switch():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        socket = str(root / 'tmux.sock')
        def tm(*args):
            return subprocess.check_output(['tmux', '-S', socket, *args], text=True).strip()
        tm('-f', '/dev/null', 'new-session', '-d', '-s', 'humtr-ai', '-n', 'first', 'sleep 90')
        tm('set-option', '-t', 'humtr-ai', '@humtr_ai_session', '1')
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        client = None
        try:
            plan = ai_plan.ExecutionPlan(argv=['sleep', '90'], env={}, cwd=str(root), display='', tmux_status=True)
            with patch.dict(os.environ, {'HOME': str(root), 'TMUX': socket+',1,0', 'TMUX_PANE': tm('display-message','-p','#{pane_id}')}):
                assert ai_tmux.launch(plan, 'example') == 0
            second = tm('display-message', '-p', '#{window_id}')
            tm('set-option', '-t', 'humtr-ai', 'status-left', '')
            tm('set-option', '-t', 'humtr-ai', 'status-right', '')
            tm('set-option', '-t', 'humtr-ai', 'status-justify', 'left')
            tm('set-window-option', '-g', 'window-status-format', '#I:#W')
            tm('set-window-option', '-g', 'window-status-current-format', '#I:#W')
            tm('select-window', '-t', 'humtr-ai:0')
            client = subprocess.Popen(['tmux', '-S', socket, 'attach-session', '-t', 'humtr-ai'], stdin=slave, stdout=slave, stderr=slave, start_new_session=True, env={**os.environ, 'TERM':'xterm-256color', 'TMUX':''})
            deadline = time.monotonic()+3
            while not tm('list-clients') and time.monotonic()<deadline: time.sleep(.05)
            assert tm('list-clients'), 'attached native client required'
            # SGR mouse press/release at second window label in the native status row.
            os.write(master, b'\x1b[<0;12;24M\x1b[<0;12;24m')
            deadline = time.monotonic()+3
            while tm('display-message', '-p', '#{window_id}') != second and time.monotonic()<deadline: time.sleep(.05)
            assert tm('display-message', '-p', '#{window_id}') == second
        finally:
            subprocess.run(['tmux', '-S', socket, 'kill-server'], capture_output=True)
            if client: client.wait(timeout=3)
            os.close(master)
            os.close(slave)


def test_native_title_forwarding():
    import select
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        socket = str(root / 'tmux.sock')
        def tm(*args):
            return subprocess.check_output(['tmux', '-S', socket, *args], text=True).strip()
        tm('-f', '/dev/null', 'new-session', '-d', '-s', 'humtr-ai', 'sleep 90')
        tm('set-option', '-t', 'humtr-ai', '@humtr_ai_session', '1')
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 80, 0, 0))
        client = None
        try:
            plan = ai_plan.ExecutionPlan(argv=['sleep', '90'], env={}, cwd=str(root), display='')
            with patch.dict(os.environ, {'HOME': str(root), 'TMUX': socket+',1,0', 'TMUX_PANE': tm('display-message','-p','#{pane_id}')}):
                ai_tmux.launch(plan, 'example')
            pane = tm('display-message', '-p', '#{pane_id}')
            client = subprocess.Popen(['tmux', '-S', socket, 'attach-session', '-t', 'humtr-ai'], stdin=slave, stdout=slave, stderr=slave, start_new_session=True, env={**os.environ, 'TERM':'xterm-256color', 'TMUX':''})
            for title in ('Native thread title', 'Changed /title #{session_name}'):
                # select-pane -T interprets formats; escape fixture input, as native OSC does not.
                tm('select-pane', '-t', pane, '-T', title.replace('#', '##'))
                data = b''
                deadline = time.monotonic()+4
                while time.monotonic() < deadline:
                    if select.select([master], [], [], .1)[0]:
                        data += os.read(master, 65536)
                        if b'\x1b]0;'+title.encode()+b'\x07' in data: break
                assert b'\x1b]0;'+title.encode()+b'\x07' in data, repr(data)
                assert tm('display-message', '-p', '-t', pane, '#{pane_title}') == title
        finally:
            subprocess.run(['tmux', '-S', socket, 'kill-server'], capture_output=True)
            if client: client.wait(timeout=3)
            os.close(master)
            os.close(slave)


def test_bounded_install():
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        (root/'config').mkdir()
        (root/'config/sentinel').write_text('preserve')
        env=os.environ.copy()
        env.update(HOME=temporary, AI_BIN_DEST=str(root/'bin/ai'), AI_LIB_DEST=str(root/'lib'), AI_CONFIG_DEST=str(root/'config'))
        installer=Path(__file__).resolve().parents[1]/'scripts/install-termux.sh'
        result=subprocess.run(['bash',str(installer),'--ai-only'],env=env,capture_output=True)
        assert result.returncode == 0
        assert (root/'lib/ai_tmux.py').is_file()
        assert (root/'config/sentinel').read_text() == 'preserve'
        assert not (root/'.config/ai/backups').exists() and not (root/'bin/agy').exists()


def test_title_independent_native_binding():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        native = root / '.local/lib/codex/core/generations/owned/runtime'
        native.parent.mkdir(parents=True)
        source = root / 'native.c'
        source.write_text('#include <unistd.h>\n#include <stdlib.h>\n#include <sys/stat.h>\n#include <stdio.h>\n#include <fcntl.h>\nint main(void) { char path[4096]; snprintf(path,sizeof path,"%s/.codex-terminal-thread-v1-%d-XXXXXX",getenv("TMPDIR"),getpid()); int fd=mkstemp(path); unlink(path); fcntl(fd,F_SETFD,FD_CLOEXEC); fchmod(fd,0600); for (;;) { int input=open("'+str(root/'thread')+'",O_RDONLY); if(input>=0) { char buf[128]; int n=read(input,buf,sizeof buf); close(input); ftruncate(fd,0); if(n>0) pwrite(fd,buf,n,0); unlink("'+str(root/'thread')+'"); } usleep(10000); } }\n')
        subprocess.run(['cc', str(source), '-o', str(native)], check=True, capture_output=True)
        socket = str(root / 'socket,valid\\path')
        def tm(*args):
            return subprocess.check_output(['tmux','-S',socket,*args],text=True,env=dict(os.environ,TMPDIR=str(root))).strip()
        pane = tm('-f','/dev/null','new-session','-d','-P','-F','#{pane_id}','-s','native',str(native))
        sid = '01a0fc82-dc8f-7d13-bb78-7e120f1fa9b3'
        try:
            pid = tm('display-message','-p','-t',pane,'#{pane_pid}')
            start = ai_tmux._process_identity(Path('/proc') / pid)[1]
            descriptor = None
            deadline = time.monotonic()+3
            while descriptor is None and time.monotonic()<deadline:
                for path in (Path('/proc')/pid/'fd').iterdir():
                    try:
                        link = os.readlink(path)
                        if Path(link).name.startswith(f'.codex-terminal-thread-v1-{pid}-') and link.endswith(' (deleted)'):
                            descriptor = path.name
                            break
                    except OSError:
                        pass
                if descriptor is None: time.sleep(.01)
            assert descriptor is not None, 'native identity slot did not become ready'
            binding = f'{pid}:{start}:{pid}:{start}:{descriptor}'
            def set_thread(value):
                request = root / 'thread'
                request.write_text(value)
                deadline = time.monotonic()+2
                while request.exists() and time.monotonic()<deadline: time.sleep(.01)
                assert not request.exists()
            set_thread(sid)
            tm('set-option','-p','-t',pane,'@codex_terminal_binding_v1',binding)
            # Full native binding does not need a title ID, provider hint or rollout scan.
            tm('select-pane','-t',pane,'-T','project | custom title without ID')
            origin = {"handle":"22a0fe94-2d11-79f3-8f5b-9c1958465dc2","pid":int(pid),"start":start}
            tm('set-option','-t',pane,ai_tmux.ai_terminal.OPTION,json.dumps(origin))
            requests = []
            with patch.dict(os.environ,{'HOME':str(root), 'LANG':'', 'LC_ALL':'', 'LC_CTYPE':''}), patch.object(ai_tmux.ai_terminal,'validate',return_value=True), patch.object(ai_tmux.ai_terminal,'focus',side_effect=lambda value: requests.append(value) or True):
                ai_tmux.register(socket)
                with patch.object(ai_tmux,'_local_id',side_effect=AssertionError('binding must not consult title/history')):
                    assert ai_tmux.focus(sid) == 0 and len(requests) == 1
                    tm('select-pane','-t',pane,'-T','different ordering')
                    assert ai_tmux.focus(sid) == 0 and len(requests) == 2
                    tm('select-pane','-t',pane,'-T','')
                    assert ai_tmux.focus(sid) == 0 and len(requests) == 3
                for invalid in ['invalid', f'{pid}:{start+1}:{pid}:{start}:{descriptor}', f'{pid}:{start}:{pid}:{start+1}:{descriptor}', f'1:{start}:{pid}:{start}:{descriptor}', f'{pid}:{start}:{pid}:{start}:999999']:
                    tm('set-option','-p','-t',pane,'@codex_terminal_binding_v1',invalid)
                    # A title that would have matched the old path cannot override invalid metadata.
                    tm('select-pane','-t',pane,'-T',sid[:29]+'...')
                    assert ai_tmux.focus(sid) == 1 and len(requests) == 3
                tm('set-option','-p','-t',pane,'@codex_terminal_binding_v1',binding)
                for value in ['', 'bad', sid[:-1]+'4']:
                    set_thread(value)
                    assert ai_tmux.focus(sid) == 1 and len(requests) == 3
                set_thread(sid)
                duplicate = tm('new-window','-d','-P','-F','#{pane_id}',str(native))
                otherpid = tm('display-message','-p','-t',duplicate,'#{pane_pid}')
                otherstart = ai_tmux._process_identity(Path('/proc') / otherpid)[1]
                deadline = time.monotonic()+3
                other_slot = None
                while other_slot is None and time.monotonic()<deadline:
                    for path in (Path('/proc')/otherpid/'fd').iterdir():
                        try:
                            link = os.readlink(path)
                            if Path(link).name.startswith(f'.codex-terminal-thread-v1-{otherpid}-') and link.endswith(' (deleted)'):
                                other_slot = path
                                break
                        except OSError: pass
                    if other_slot is None: time.sleep(.01)
                assert other_slot is not None
                other_slot.write_text(sid)
                tm('set-option','-p','-t',duplicate,'@codex_terminal_binding_v1',f'{otherpid}:{otherstart}:{otherpid}:{otherstart}:{other_slot.name}')
                assert ai_tmux.focus(sid) == 1 and len(requests) == 3
                tm('kill-pane','-t',duplicate)
                original = ai_tmux._tmux
                def race(sock,*args):
                    if args[0] == 'if-shell':
                        tm('set-option','-p','-t',pane,'@codex_terminal_binding_v1','none')
                    return original(sock,*args)
                with patch.object(ai_tmux,'_tmux',side_effect=race):
                    assert ai_tmux.focus(sid) == 1 and len(requests) == 3
                tm('set-option','-p','-t',pane,'@codex_terminal_binding_v1',binding)
                with patch.object(ai_tmux,'_bound_thread',side_effect=[sid,None]):
                    assert ai_tmux.focus(sid) == 1 and len(requests) == 3
                def thread_race(sock,*args):
                    if args[0] == 'if-shell': set_thread(sid[:-1]+'4')
                    return original(sock,*args)
                with patch.object(ai_tmux,'_tmux',side_effect=thread_race):
                    assert ai_tmux.focus(sid) == 1 and len(requests) == 3
        finally:
            subprocess.run(['tmux','-S',socket,'kill-server'],capture_output=True)


if __name__=='__main__':
    for test in (test_title_preservation,test_cli_boundary,test_native_tmux_color_environment,test_native_status_mouse_switch,test_native_title_forwarding,test_bounded_install,test_title_independent_native_binding):
        test();print('PASS',test.__name__)
