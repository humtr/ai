import json,os,socket,sys,tempfile,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import ai_terminal

def test_existing_origin_protocol_and_failure_refusal():
 with tempfile.TemporaryDirectory() as tmp:
  prefix=Path(tmp)/'usr';endpoint=prefix.parent/'apps/com.termux/termux-am/am.sock';endpoint.parent.mkdir(parents=True)
  origin={'handle':'22a0fe94-2d11-79f3-8f5b-9c1958465dc2','pid':123,'start':901}
  response={'schema':ai_terminal.SCHEMA,'result':'ok','origin':origin}
  with socket.socket(socket.AF_UNIX) as server:
   server.bind(str(endpoint))
   with patch.dict(os.environ,{'PREFIX':str(prefix)}),patch.object(ai_terminal.subprocess,'run') as run:
    run.return_value=subprocess.CompletedProcess([],0,json.dumps(response).encode(),b'')
    assert ai_terminal.resolve()==origin and ai_terminal.validate(origin) and ai_terminal.focus(origin)
    requests=[call.args[0][1] for call in run.call_args_list]
    assert requests==['termux-terminal-v1 origin','termux-terminal-v1 validate '+origin['handle']+' 123 901','termux-terminal-v1 focus '+origin['handle']+' 123 901']
    assert all(call.kwargs['timeout']==3 and call.kwargs['stdin']==subprocess.DEVNULL for call in run.call_args_list)
    for reply in (b'',b'not JSON',json.dumps(dict(response,schema='other')).encode(),json.dumps(dict(response,result='unavailable')).encode(),json.dumps(dict(response,origin=dict(origin,start=902))).encode()):
     run.return_value=subprocess.CompletedProcess([],0,reply,b'');assert not ai_terminal.focus(origin)
    run.return_value=subprocess.CompletedProcess([],69,json.dumps(response).encode(),b'');assert ai_terminal.resolve() is None
    run.return_value=subprocess.CompletedProcess([],0,json.dumps(response).encode(),b'error');assert ai_terminal.resolve() is None
    for error in (OSError('offline'),subprocess.TimeoutExpired([],3)):
     run.side_effect=error;assert ai_terminal.resolve() is None
  for bad in ({},dict(origin,pid=True),dict(origin,start=0),dict(origin,handle='codex-12345678'),dict(origin,pid=2147483648)):
   assert ai_terminal.reference(bad) is None

if __name__=='__main__':
 test_existing_origin_protocol_and_failure_refusal();print('PASS existing_origin_protocol_and_failure_refusal')
