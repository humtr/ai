import os
import socket
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import ai_tmux

def test_socket_preselection_and_unavailable_compatibility_without_dispatch():
    with tempfile.TemporaryDirectory() as d:
        prefix=Path(d)/'usr'
        endpoint=prefix.parent/'apps/com.termux/termux-am/am.sock'
        endpoint.parent.mkdir(parents=True)
        def which(name): return '/installed/'+name
        with patch.dict(os.environ,{'PREFIX':str(prefix)}), patch.object(ai_tmux.shutil,'which',side_effect=which), patch.object(ai_tmux.subprocess,'run') as dispatch:
            assert ai_tmux._activity_manager()=='/installed/am'
            endpoint.write_text('not a socket')
            assert ai_tmux._activity_manager()=='/installed/am'
            endpoint.unlink()
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(endpoint))
                assert ai_tmux._activity_manager()=='/installed/termux-am'
                with patch.object(ai_tmux.shutil,'which',side_effect=lambda n:None if n=='termux-am' else which(n)):
                    assert ai_tmux._activity_manager()=='/installed/am'
            assert dispatch.call_count==0

if __name__=='__main__':
    test_socket_preselection_and_unavailable_compatibility_without_dispatch()
    print('android_am_transport: 1 passed')
