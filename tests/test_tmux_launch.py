#!/usr/bin/env python3
import json
import os
import subprocess
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


def test_native_tmux_launch_focus():
    with tempfile.TemporaryDirectory() as temporary:
        root=Path(temporary)
        socket=str(root/'tmux.sock')
        def tm(*args):
            return subprocess.check_output(['tmux','-S',socket,*args], text=True).strip()
        tm('-f','/dev/null','new-session','-d','-s','isolated','sleep 90')
        foreign_status = tm('show-options', '-v', '-t', 'isolated', 'status')
        foreign_mouse = tm('show-options', '-v', '-t', 'isolated', 'mouse')
        marker=root/'argv.json'
        provider=root/'provider'
        provider.write_text('#!'+sys.executable+'\nimport json,os,sys,time\njson.dump([sys.argv[1:],os.getcwd(),os.environ.get("CODEX_HOME")],open('+repr(str(marker))+',"w"))\nprint("\\x1b]0;01a0fc82-dc8f-7d13-bb78-7e120... | native\\x07",flush=True)\ntime.sleep(90)\n')
        provider.chmod(0o700)
        sid='01a0fc82-dc8f-7d13-bb78-7e120f1fa9b3'
        sessions=root/'.codex/sessions'
        sessions.mkdir(parents=True)
        session=sessions/('rollout-test-'+sid+'.jsonl')
        session.write_text(json.dumps({'type':'session_meta','payload':{'id':sid}})+'\n')
        plan=ai_plan.ExecutionPlan(argv=[str(provider), 'space argument', "apostrophe'", '$(false)'],env={'CODEX_HOME':str(root/'.profile')},cwd=str(root),display='')
        try:
            with patch.dict(os.environ, {'HOME':str(root),'TMUX':socket+',1,0','AUTH_TEST_SECRET':'never-serialize'}, clear=False):
                assert ai_tmux.launch(dataclasses.replace(plan, tmux_status=True),'codex') == 0
                deadline=time.monotonic()+3
                while not marker.exists() and time.monotonic()<deadline: time.sleep(.05)
                assert json.loads(marker.read_text()) == [plan.argv[1:],str(root),str(root/'.profile')]
                assert tm('show-options', '-v', '-t', 'isolated', 'status') == foreign_status
                assert tm('show-options', '-v', '-t', 'isolated', 'mouse') == foreign_mouse
                command=tm('display-message','-p','#{pane_start_command}')
                assert 'AUTH_TEST_SECRET' not in command
                target=tm('display-message','-p','#{pane_id}')
                dead=ai_tmux._registry()/'000-dead.json'
                dead.write_text(json.dumps({'socket':str(root/'missing.sock'),'identity':[0,0]}))
                dead.chmod(0o600)
                tm('select-window','-t','isolated:0')
                before=tm('list-panes','-a','-F','#{pane_id}:#{pane_pid}')
                with patch.object(ai_tmux,'_runtime',return_value=True):
                    assert ai_tmux.focus(sid) == 0
                    assert tm('display-message','-p','#{pane_id}') == target
                    assert before == tm('list-panes','-a','-F','#{pane_id}:#{pane_pid}')
                    # full-ID collision refuses prefix guesses.
                    collision=sessions/('rollout-test-'+sid[:-1]+'4.jsonl')
                    collision.write_text(json.dumps({'type':'session_meta','payload':{'id':sid[:-1]+'4'}})+'\n')
                    tm('select-window','-t','isolated:0')
                    assert ai_tmux.focus(sid) == 1
                    assert tm('display-message','-p','#{pane_id}') != target
                    collision.unlink()
                    # Native title content is never evaluated as shell/format code.
                    tm('select-pane','-t',target,'-T',sid[:29]+'... | #(touch '+str(root/'injected')+')')
                    assert ai_tmux.focus(sid) == 0
                    assert not (root/'injected').exists()
                    tm('select-window','-t','isolated:0')
                    original=ai_tmux._tmux
                    def race(sock,*args):
                        if args[0] == 'if-shell':
                            tm('select-pane','-t',target,'-T','different thread')
                        return original(sock,*args)
                    with patch.object(ai_tmux,'_tmux',side_effect=race):
                        assert ai_tmux.focus(sid) == 0
                    assert tm('display-message','-p','#{pane_id}') != target
                    tm('select-pane','-t',target,'-T','foreign | '+sid[:29]+'...')
                    assert ai_tmux.focus(sid) == 1
                    tm('kill-pane','-t',target)
                    assert ai_tmux.focus(sid) == 1
                assert ai_tmux.focus('$(false)') == 1
                assert not ai_tmux._runtime('1','/dev/null')
                # Outside tmux: a native managed session and one attach, no other session mutation.
                class Attached(Exception): pass
                def attach(binary,argv):
                    assert binary == 'tmux' and argv[:4] == ['tmux','-S',socket,'attach-session']
                    raise Attached
                original=ai_tmux._tmux
                def routed(sock,*args): return original(sock or socket,*args)
                with patch.dict(os.environ, {'TMUX':''}), patch.object(ai_tmux,'_tmux',side_effect=routed), patch.object(os,'execvp',side_effect=attach):
                    try: ai_tmux.launch(plan,'codex')
                    except Attached: pass
                    else: raise AssertionError('outside launch must attach')
                assert tm('show-options','-v','-t','humtr-ai','@humtr_ai_session') == '1'
                assert tm('show-options', '-v', '-t', 'humtr-ai', 'status') == 'off'
                assert tm('show-options', '-v', '-t', 'isolated', 'status') == foreign_status
                visible = dataclasses.replace(plan, tmux_status=True)
                with patch.dict(os.environ, {'TMUX':''}), patch.object(ai_tmux,'_tmux',side_effect=routed), patch.object(os,'execvp',side_effect=attach):
                    try: ai_tmux.launch(visible,'codex')
                    except Attached: pass
                    else: raise AssertionError('visible launch must attach')
                assert tm('show-options', '-v', '-t', 'humtr-ai', 'status') == 'on'
                assert tm('show-options', '-v', '-t', 'humtr-ai', 'mouse') == 'on'
                assert tm('show-options', '-v', '-t', 'isolated', 'status') == foreign_status
                assert tm('show-options', '-v', '-t', 'isolated', 'mouse') == foreign_mouse
                assert tm('has-session','-t','=isolated') == ''
        finally:
            subprocess.run(['tmux','-S',socket,'kill-server'],capture_output=True)


def test_native_tmux_color_environment():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        socket = str(root / 'tmux.sock')
        def tm(*args):
            return subprocess.check_output(['tmux', '-S', socket, *args], text=True).strip()
        tm('-f', '/dev/null', 'new-session', '-d', '-s', 'isolated', 'sleep 90')
        provider = root / 'color-provider'
        provider.write_text('#!' + sys.executable + '\nimport json,os,sys,time\nkeys=' + repr((*ai_tmux.COLOR_ENVIRONMENT, 'TERM', 'TERM_PROGRAM')) + '\njson.dump({k:os.environ.get(k) for k in keys},open(sys.argv[1],"w"))\nprint("plain" if os.environ.get("NO_COLOR") else "\\x1b[1;38;2;12;200;90mcolored\\x1b[0m",flush=True)\ntime.sleep(90)\n')
        provider.chmod(0o700)
        try:
            for key in ai_tmux.COLOR_ENVIRONMENT:
                tm('set-environment', '-g', key, 'stale')
            caller = {k:v for k,v in os.environ.items() if k not in ai_tmux.COLOR_ENVIRONMENT}
            caller.update(HOME=str(root), TMUX=socket+',1,0', TERM='xterm-256color')
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
            with patch.dict(os.environ, {'HOME': str(root), 'TMUX': socket+',1,0'}):
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


if __name__=='__main__':
    for test in (test_title_preservation,test_cli_boundary,test_native_tmux_launch_focus,test_native_tmux_color_environment,test_native_status_mouse_switch,test_bounded_install):
        test()
        print('PASS',test.__name__)
