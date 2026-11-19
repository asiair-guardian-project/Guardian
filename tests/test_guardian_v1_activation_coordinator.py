import pytest
from modules.guardian_v1_activation_coordinator import activate_stopped_monitor, OfflineActivationRejected
from modules.guardian_v1_setup_binding import MonitorBinding


def test_confirmation_is_mandatory(tmp_path):
    with pytest.raises(OfflineActivationRejected, match='confirmation'):
        activate_stopped_monitor(active_path=tmp_path/'active', candidate_path=tmp_path/'candidate',
            backup_path=tmp_path/'backup', journal_path=tmp_path/'journal',
            runtime_lock_path=tmp_path/'lock', binding=MonitorBinding('a','b',1,17,5))


def test_preexisting_journal_blocks_activation(tmp_path):
    (tmp_path/'journal').write_text('existing')
    with pytest.raises(OfflineActivationRejected, match='Previous'):
        activate_stopped_monitor(active_path=tmp_path/'active', candidate_path=tmp_path/'candidate',
            backup_path=tmp_path/'backup', journal_path=tmp_path/'journal',
            runtime_lock_path=tmp_path/'lock', binding=MonitorBinding('a','b',1,17,5), confirmed=True,
            recovery_file=tmp_path/'recovery', launch_plist=tmp_path/'plist', socket_path=tmp_path/'sock')


def test_monitor_still_running_blocks_before_file_access(tmp_path):
    with pytest.raises(OfflineActivationRejected, match='stopped'):
        activate_stopped_monitor(active_path=tmp_path/'active', candidate_path=tmp_path/'candidate',
            backup_path=tmp_path/'backup', journal_path=tmp_path/'journal',
            runtime_lock_path=tmp_path/'lock', binding=MonitorBinding('a','b',1,17,5),
            confirmed=True, recovery_file=tmp_path/'recovery',
            launch_plist=tmp_path/'plist', socket_path=tmp_path/'sock', verify_stopped=lambda: {'launchagent_stopped': False})
    assert not (tmp_path/'journal').exists()
