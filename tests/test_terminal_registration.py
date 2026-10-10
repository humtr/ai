"""Owned actual launch and transport tests, with no live Android dispatch."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
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


def test_initial_launch_registers_one_workload_with_upstream_title_and_shared_attachment():
    for service_success in (True,False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); socket=str(root/'tmux.sock'); home=root/'home'; home.mkdir()
            config=home/'profile/config.toml';config.parent.mkdir();before=b'# user title\n[tui]\nterminal_title=["thread-name","activity"]\n';config.write_bytes(before)
            program=root/'codex'; marker=root/'runs'
            program.write_text('#!' + sys.executable + '\nimport sys,time\nfrom pathlib import Path\nif sys.argv[1:3]==["termux","__terminal-capabilities-v1"]:\n print("codex-terminal-capabilities-v1\\nidentity=native");sys.exit(0)\np=Path('+repr(str(marker))+');p.write_text(p.read_text()+"run\\n" if p.exists() else "run\\n")\ntime.sleep(90)\n');program.chmod(0o755)
            plan=ai_plan.ExecutionPlan(argv=[str(program)],env={'CODEX_HOME':str(config.parent)},cwd=tmp,display='')
            original=ai_tmux._tmux; native_run=subprocess.run; requests=[];direct=[]
            def tm(sock,*args): return original(sock or socket,*args)
            def run(args,**kwargs):
                if args[0]=='/owned/am':
                    requests.append(args)
                    return subprocess.CompletedProcess(args,0 if service_success else 1,'','')
                return native_run(args,**kwargs)
            native_which=ai_tmux.shutil.which
            def which(name): return '/owned/tmux' if name=='tmux' else native_which(name)
            def attach(*args): direct.append(args); raise RuntimeError('owned exec boundary')
            try:
                with patch.dict(os.environ, {'HOME':str(home),'TMUX':''}), patch.object(ai_tmux,'_tmux',side_effect=tm),patch.object(ai_tmux,'_activity_manager',return_value='/owned/am'),patch.object(ai_tmux.shutil,'which',side_effect=which),patch.object(ai_tmux.subprocess,'run',side_effect=run),patch.object(ai_tmux.os,'execvp',side_effect=attach):
                    if service_success: assert ai_tmux.launch(plan,'codex')==0
                    else:
                        try: ai_tmux.launch(plan,'codex')
                        except RuntimeError as e: assert str(e)=='owned exec boundary'
                        else: raise AssertionError('missing direct attachment fallback')
                    assert len(requests)==1 and len(direct)==(0 if service_success else 1)
                    sid=original(socket,'list-panes','-a','-F','#{session_id}')
                    name=original(socket,'show-options','-qv','-t',sid,'@humtr_ai_terminal_name')
                    assert name.startswith('codex-') and len(name)==14
                    assert requests[0][requests[0].index('com.termux.RUN_COMMAND_SHELL_NAME')+1]==name
                    native_socket=original(socket,'display-message','-p','-t',sid,'#{socket_path}')
                    assert ai_tmux._socket_identity(native_socket)==ai_tmux._socket_identity(socket)
                    assert requests[0][requests[0].index('com.termux.RUN_COMMAND_ARGUMENTS')+1]=='-S,'+native_socket+',attach-session,-t,'+sid, (requests[0], native_socket, sid)
                    assert requests[0][requests[0].index('com.termux.RUN_COMMAND_SHELL_CREATE_MODE')+1]=='no-shell-with-name'
                    assert ai_tmux.terminal_name(socket,sid,'agy')==name
                    assert config.read_bytes()==before
                    assert original(socket,'list-panes','-a','-F','#{pane_id}').count('\n')==0
                    deadline=time.monotonic()+3
                    while not marker.exists() and time.monotonic()<deadline: time.sleep(.01)
                    assert marker.read_text()=='run\n'
                    # All repeated service calls attach the same existing job/session.
                    for _ in range(2): ai_tmux._attach_terminal(native_socket,sid,name)
                    assert len(requests)==3 and all(r==requests[0] for r in requests)
                    assert marker.read_text()=='run\n' and config.read_bytes()==before
            finally: native_run(['tmux','-S',socket,'kill-server'],capture_output=True)


if __name__=='__main__':
    for test in (test_read_only_capability_delegates_exact_plan_and_refuses_invalid_protocol,test_initial_launch_registers_one_workload_with_upstream_title_and_shared_attachment):
        test();print('PASS',test.__name__)
