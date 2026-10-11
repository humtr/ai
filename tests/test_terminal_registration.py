"""Owned actual launch and transport tests, with no live Android dispatch."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
import ai_plan
import ai_tmux


def test_read_only_capability_delegates_exact_plan_and_refuses_invalid_protocol():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        program = root/'codex'
        program.write_text('#!' + sys.executable + '\nimport os,sys,json\nassert sys.argv[1:4]==["termux","__terminal-capabilities-v1","--"]\nassert sys.argv[4:]==["resume","owned title"]\nassert os.environ["OWNED"]=="selected" and "REMOVE_ME" not in os.environ\nsys.stdout.write(os.environ["REPLY"])\nsys.exit(int(os.environ["STATUS"]))\n'); program.chmod(0o755)
        for reply, status, expected in [('codex-terminal-capabilities-v1\nidentity=native\n',0,True), ('codex-terminal-capabilities-v1\nidentity=title\n',0,False), ('codex-terminal-capabilities-v1\nidentity=native\nextra\n',0,False), ('codex-terminal-capabilities-v1\nidentity=native\n',1,False)]:
            plan = SimpleNamespace(argv=[str(program),'resume','owned title'], env={'OWNED':'selected','REPLY':reply,'STATUS':str(status)}, env_unset=['REMOVE_ME'],cwd=tmp)
            with patch.dict(os.environ, {'REMOVE_ME':'inherited'}):
                assert ai_tmux._native_identity(plan) == expected
                assert os.environ['REMOVE_ME']=='inherited'
        with patch.object(ai_tmux.subprocess,'run',side_effect=subprocess.TimeoutExpired(['owned'],2)):
            assert not ai_tmux._native_identity(plan)



def test_direct_launches_do_not_dispatch_android_creation():
    import pty,shlex,fcntl,termios,struct
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp);home=root/'home';home.mkdir();(root/'run').mkdir()
        program=root/'codex';marker=root/'runs'
        program.write_text('#!'+sys.executable+'\nimport os,sys,time\nfrom pathlib import Path\nif sys.argv[1:3]==["termux","__terminal-launch-capabilities-v1"]:sys.exit(2)\nif sys.argv[1:3]==["termux","__terminal-capabilities-v1"]:print("codex-terminal-capabilities-v1\\nidentity=native");sys.exit(0)\nPath('+repr(str(marker))+').open("a").write("run\\n")\nprint("OWNED_WORKLOAD",flush=True)\ntime.sleep(90)\n');program.chmod(0o755)
        clients=[];fds=[];socket=str(root/'run'/('tmux-'+str(os.getuid()))/'default')
        def tm(*args):return subprocess.check_output(['tmux','-S',socket,*args],text=True).strip()
        try:
            for _ in range(2):
                master,slave=pty.openpty();fds.extend([master,slave]);fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',12,80,0,0))
                code='import sys;sys.path.insert(0,'+repr(str(Path(ai_tmux.__file__).parent))+');import ai_tmux,ai_plan;ai_tmux.ai_terminal.resolve=lambda:None;ai_tmux.launch(ai_plan.ExecutionPlan(argv=['+repr(str(program))+'],env={},cwd='+repr(tmp)+',display=""),"codex")'
                process=subprocess.Popen([sys.executable,'-c',code],stdin=slave,stdout=slave,stderr=slave,start_new_session=True,env={**os.environ,'HOME':str(home),'TMUX':'','TMUX_PANE':'','TMUX_TMPDIR':str(root/'run'),'TERM':'xterm-256color','PYTHONDONTWRITEBYTECODE':'1'});clients.append((process,os.ttyname(slave)))
                deadline=time.monotonic()+4
                while (not marker.exists() or len(marker.read_text().splitlines())!=len(clients)) and time.monotonic()<deadline:time.sleep(.01)
                assert process.poll() is None and marker.read_text()=='run\n'*len(clients)
                deadline=time.monotonic()+4
                while not os.readlink('/proc/'+str(process.pid)+'/exe').endswith('/tmux') and time.monotonic()<deadline:time.sleep(.01)
                assert os.readlink('/proc/'+str(process.pid)+'/exe').endswith('/tmux'),'launcher did not exec attachment in its caller terminal'
            deadline=time.monotonic()+4
            while True:
                rows=dict(row.split('\t') for row in tm('list-clients','-F','#{client_tty}\t#{session_id}').splitlines())
                if len(rows)==2 or time.monotonic()>=deadline:break
                time.sleep(.01)
            assert len(rows)==2 and rows[clients[0][1]]!=rows[clients[1][1]]
            sessions=tm('list-sessions','-F','#{session_id}').splitlines();assert len(sessions)==2
            tm('kill-session','-t',rows[clients[1][1]])
            assert clients[0][0].poll() is None and tm('has-session','-t',rows[clients[0][1]])==''
        finally:
            subprocess.run(['tmux','-S',socket,'kill-server'],capture_output=True)
            for process,_ in clients:
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            for fd in fds:os.close(fd)

def test_manager_launch_preserves_supervisor_plan_and_never_replays():
    with tempfile.TemporaryDirectory() as tmp:
        @dataclass
        class RecoveryPlan:
            argv: list
            env: dict
            env_unset: list
            cwd: str
            tmux_provider: str | None = "codex"
            tmux_status: bool = True
            auth_recovery: bool = True
            def as_dict(self): return asdict(self)
        plan = RecoveryPlan(argv=[sys.executable, "resume", "owned"], env={"OWNED":"selected"}, env_unset=["REMOVE_ME"], cwd=tmp)
        accepted = subprocess.CompletedProcess([],0,b"codex-terminal-launch-v1\ncontainer=off,hidden,status\n",b"")
        original = os.getcwd()
        try:
            with patch.dict(os.environ,{"REMOVE_ME":"inherited"}), patch.object(ai_tmux.subprocess,'run',return_value=accepted) as query, patch.object(ai_tmux.os,'execvpe',side_effect=RuntimeError("dispatch failed")) as execute:
                try: ai_tmux._manager_launch(plan)
                except RuntimeError: pass
                else: raise AssertionError("failed dispatch unexpectedly returned")
                assert query.call_args.kwargs['env']['OWNED']=='selected' and 'REMOVE_ME' not in query.call_args.kwargs['env']
                assert query.call_args.kwargs['cwd']==tmp
                execute.assert_called_once()
                _, argv, environment = execute.call_args.args
                assert argv[1:5] == ["termux","__terminal-launch-command-v1","status","--"]
                assert Path(argv[5]) == Path(sys.executable).resolve()
                assert argv[6] == str(Path(ai_tmux.__file__).with_name('ai_run.py'))
                restored=json.loads(argv[7]);assert restored['argv']==plan.argv and restored['auth_recovery'] and restored['tmux_provider'] is None
                assert environment['OWNED']=='selected' and 'REMOVE_ME' not in environment
            legacy = SimpleNamespace(argv=[sys.executable, "owned"], env={}, cwd=tmp, tmux_status=False)
            with patch.object(ai_tmux.subprocess,'run',return_value=accepted), patch.object(ai_tmux.os,'execvpe',side_effect=RuntimeError("dispatch failed")) as execute:
                try: ai_tmux._manager_launch(legacy)
                except RuntimeError: pass
                else: raise AssertionError("failed dispatch unexpectedly returned")
                execute.assert_called_once()
                assert execute.call_args.args[1][1:5]==["termux","__terminal-launch-command-v1","hidden","--"]
                assert execute.call_args.args[1][6:]==["owned"]
            for reply in (b"",b"codex-terminal-launch-v1\ncontainer=off,hidden,status\nextra\n"):
                with patch.object(ai_tmux.subprocess,'run',return_value=subprocess.CompletedProcess([],0,reply,b"")),patch.object(ai_tmux.os,'execvpe') as execute:
                    assert not ai_tmux._manager_launch(plan);execute.assert_not_called()
        finally:os.chdir(original)


if __name__=='__main__':
 for test in (test_read_only_capability_delegates_exact_plan_and_refuses_invalid_protocol,test_direct_launches_do_not_dispatch_android_creation,test_manager_launch_preserves_supervisor_plan_and_never_replays):
  test();print('PASS',test.__name__)
