import sys,os,json,tempfile,pty
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import ai_tmux

def test_direct_and_supervised_native_identity():
 with tempfile.TemporaryDirectory() as tmp:
  root=Path(tmp);proc=root/'proc';proc.mkdir();home=root/'home';home.mkdir()
  a,b=pty.openpty();c,d=pty.openpty()
  try:
   tty=os.ttyname(b);childtty=os.ttyname(d);native=str(home/'.local/lib/codex/core/generations/exact/runtime');preview=str(home/'.local/lib/codex/profile-tui-preview/direct-selection-v1/native')
   def process(pid,exe,parent=1,stdin=tty,argv=None):
    p=proc/str(pid);p.mkdir(exist_ok=True);(p/'fd').mkdir(exist_ok=True)
    for n,target in [('exe',exe),('fd/0',stdin)]:
     q=p/n;q.unlink(missing_ok=True);q.symlink_to(target)
    (p/'stat').write_text(str(pid)+' (owned process) '+' '.join(['S',str(parent)]+['0']*17+['123']))
    (p/'cmdline').write_bytes(b'\0'.join(os.fsencode(v) for v in (argv or [exe]))+b'\0')
    return p
   with patch.object(ai_tmux,'PROC',proc),patch.dict(os.environ,{'HOME':str(home)}):
    process(10,native);assert ai_tmux._runtime('10',tty)
    process(10,preview);assert ai_tmux._runtime('10',tty)
    process(10,native,stdin=childtty);assert not ai_tmux._runtime('10',tty)
    launch=[sys.executable,str(Path(ai_tmux.__file__).with_name('ai_run.py')),json.dumps({'auth_recovery':True,'argv':['codex','resume','example']})]
    process(10,str(Path(sys.executable).resolve()),argv=launch)
    child=process(20,native,parent=10,stdin=childtty);assert ai_tmux._runtime('10',tty)
    process(20,preview,parent=10,stdin=childtty);assert ai_tmux._runtime('10',tty)
    process(30,native,parent=10,stdin=childtty);assert not ai_tmux._runtime('10',tty)
    import shutil;shutil.rmtree(proc/'30')
    process(20,native,parent=99,stdin=childtty);assert not ai_tmux._runtime('10',tty)
    process(20,native,parent=10,stdin='/dev/null');assert not ai_tmux._runtime('10',tty)
    process(20,'/untrusted/runtime',parent=10,stdin=childtty);assert not ai_tmux._runtime('10',tty)
    process(20,native,parent=10,stdin=childtty)
    foreign=[*launch];foreign[1]='/untrusted/ai_run.py';process(10,str(Path(sys.executable).resolve()),argv=foreign);assert not ai_tmux._runtime('10',tty)
    foreign=[*launch];foreign[2]=json.dumps({'auth_recovery':True,'argv':['untrusted']});process(10,str(Path(sys.executable).resolve()),argv=foreign);assert not ai_tmux._runtime('10',tty)
    process(10,'/untrusted/python',argv=launch);assert not ai_tmux._runtime('10',tty)
    assert not ai_tmux._runtime('not-a-pid',tty)
  finally:
   for fd in [a,b,c,d]:os.close(fd)
if __name__=='__main__':
 test_direct_and_supervised_native_identity();print('tmux runtime identity: direct/supervisor/preview and refusal cases passed')
