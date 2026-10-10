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


def test_cli_watchdog_allows_android_response_budget():
    import signal, ai_cli
    sid='01a0fe94-2d11-79f3-8f5b-9c1958465dc2'
    with patch.object(signal,'alarm') as alarm, patch.object(ai_tmux,'focus',return_value=0) as focus:
        assert ai_cli.main(['__tmux_focus',sid])==0
        alarm.assert_called_once_with(20)
        focus.assert_called_once_with(sid)

if __name__ == "__main__":
    test_cli_watchdog_allows_android_response_budget()
    print("android_focus_watchdog: 1 passed")
