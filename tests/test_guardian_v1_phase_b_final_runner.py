import pytest
import guardian_v1_phase_b_final_runner as runner


def outlets(on):
    return [dict(number=n, name=name, is_on=(n == 1 or (n in (2, 3, 4) and on)),
                 protected=(n == 1)) for n, name in
            [(1, 'Mac Mini'), (2, 'ASIAIR'), (3, 'Wave 150i'), (4, 'Pegasus'),
             (5, 'spare'), (6, 'Plug 6')]]


def test_identity_and_state_checks():
    assert runner.check_outlets(outlets(True), runner.EXPECTED)
    assert not runner.check_outlets(outlets(False), runner.EXPECTED)
    broken = outlets(True)
    broken[0]['protected'] = False
    assert not runner.check_outlets(broken, runner.EXPECTED)


def test_no_approval_prevents_even_reading_hardware(monkeypatch):
    monkeypatch.setattr(runner, 'read_outlets', lambda: pytest.fail('hardware access'))
    with pytest.raises(RuntimeError, match='approval'):
        runner.run_live(fingerprint='fp', test_id='a', approval='no', roof_closed=True,
                        mount_stationary=True, imaging_stopped=True)


def test_process_ownership_prevents_hardware(monkeypatch):
    monkeypatch.setattr(runner, 'process_check', lambda: False)
    monkeypatch.setattr(runner, 'read_outlets', lambda: pytest.fail('hardware access'))
    with pytest.raises(RuntimeError, match='process'):
        runner.run_live(fingerprint='fp', test_id='a', approval=runner.APPROVAL,
                        roof_closed=True, mount_stationary=True, imaging_stopped=True)


def test_off_targets_prevent_executor(monkeypatch):
    monkeypatch.setattr(runner, 'process_check', lambda: True)
    monkeypatch.setattr(runner, 'read_outlets', lambda: outlets(False))
    monkeypatch.setattr(runner, 'compose_starfront_kasa', lambda **kwargs: pytest.fail('executor created'))
    with pytest.raises(RuntimeError, match='preflight'):
        runner.run_live(fingerprint='fp', test_id='a', approval=runner.APPROVAL,
                        roof_closed=True, mount_stationary=True, imaging_stopped=True)
