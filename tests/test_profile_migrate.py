from pathlib import Path
import os,sys,tempfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'lib'))
import ai_profile_migrate,ai_codex_manager,ai_provider
with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,HOME=tmp):
 home=Path(tmp); source=home/'.codex-profiles/account'; source.mkdir(parents=True,mode=0o700)
 (source/'auth.json').write_text('fixture'); (source/'config.toml').write_text('fixture-config')
 (source/'sessions').symlink_to(home/'.codex/sessions')
 before=(source/'auth.json').stat().st_ino
 stream=(source/'auth.json').open()
 assert ai_profile_migrate.migrate_legacy_profiles()==['account']
 target=home/'.local/share/codex/manager/profiles/account/home'
 assert not source.exists()
 assert not (home/'.codex-profiles').exists()
 assert (target/'auth.json').stat().st_ino==before
 assert stream.read()=='fixture'; stream.close()
 assert (target/'config.toml').read_text()=='fixture-config'
 assert (target/'sessions').readlink()==home/'.codex/sessions'
 assert ai_codex_manager.list_profiles()==['default','account']
 with patch.object(ai_provider,'codex_manager_profiles',side_effect=ValueError('unavailable')):
  assert ai_provider.list_profiles('codex')==ai_codex_manager.list_profiles()
  assert ai_provider.apply_profile('codex','account')[1]['CODEX_HOME']==str(target)
 assert ai_profile_migrate.migrate_legacy_profiles()==[]
print('PASS migration preserves credentials, inodes, open files, no leftover paths, topology, and idempotence')

# Account publication must be complete and invisible until its atomic rename.
with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,HOME=tmp):
 home=Path(tmp);source=home/'.codex-profiles/account';source.mkdir(parents=True,mode=0o700)
 (source/'auth.json').write_text('fixture');inode=(source/'auth.json').stat().st_ino
 publish=ai_codex_manager.publish
 def observe_publish(origin,destination):
  if origin.name.startswith('.migrate-ai-'):
   assert ai_codex_manager.list_profiles()==['default']
   assert (origin/'home/auth.json').stat().st_ino==inode
   assert (origin/'profile.meta').stat().st_mode & 0o777==0o600
  publish(origin,destination)
 with patch.object(ai_codex_manager,'publish',side_effect=observe_publish):
  assert ai_profile_migrate.migrate_legacy_profiles()==['account']
 assert ai_codex_manager.list_profiles()==['default','account']
print('PASS complete atomic publication never exposes an empty account')

with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,HOME=tmp):
 home=Path(tmp);source=home/'.codex-profiles/account';source.mkdir(parents=True,mode=0o700)
 (source/'auth.json').write_text('fixture');inode=(source/'auth.json').stat().st_ino
 publish=ai_codex_manager.publish
 def reject_publication(origin,destination):
  if origin.name.startswith('.migrate-ai-'):raise OSError('fixture publication failure')
  publish(origin,destination)
 with patch.object(ai_codex_manager,'publish',side_effect=reject_publication):
  try:ai_profile_migrate.migrate_legacy_profiles()
  except OSError:pass
  else:raise AssertionError('failed publication was accepted')
 assert (source/'auth.json').stat().st_ino==inode
 assert ai_codex_manager.list_profiles()==['default']
 assert not list((home/'.local/share/codex/manager/profiles').glob('.migrate-ai-*'))
print('PASS failed publication restores original account inode and path')

with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,HOME=tmp):
 home=Path(tmp);source=home/'.codex-profiles/account';source.mkdir(parents=True,mode=0o700)
 (source/'auth.json').write_text('fixture')
 read=Path.read_bytes
 def deny_own_environment(path):
  if path==Path('/proc',str(os.getpid()),'environ'):raise PermissionError('fixture inaccessible own process')
  return read(path)
 with patch.object(Path,'read_bytes',deny_own_environment):
  try:ai_profile_migrate.migrate_legacy_profiles()
  except ValueError as error:assert 'cannot verify' in str(error)
  else:raise AssertionError('unverified inactivity permitted migration')
 assert (source/'auth.json').read_text()=='fixture'
 assert ai_codex_manager.list_profiles()==['default']
print('PASS inaccessible same-user process refuses migration before account changes')
