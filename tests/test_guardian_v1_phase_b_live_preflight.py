from guardian_v1_phase_b_live_preflight import evaluate

GOOD = [
    {'number': 1, 'name': 'Mac Mini', 'is_on': True, 'protected': True},
    {'number': 2, 'name': 'ASIAIR', 'is_on': False, 'protected': False},
    {'number': 3, 'name': 'Wave 150i', 'is_on': False, 'protected': False},
    {'number': 4, 'name': 'Pegasus', 'is_on': False, 'protected': False},
]

def test_expected_states_pass():
    checks, active = evaluate('  PID PPID COMMAND\n', GOOD)
    assert all(checks.values()) and not active

def test_active_guardian_blocks():
    checks, _ = evaluate('123 1 python /tmp/guardian_v1.py --continuous-monitor', GOOD)
    assert not checks['no_active_guardian_process']

def test_wrong_alias_blocks():
    altered = [dict(o) for o in GOOD]
    altered[2]['name'] = 'Other'
    checks, _ = evaluate('', altered)
    assert not checks['outlet_3_identity_state']

def test_mac_off_blocks():
    altered = [dict(o) for o in GOOD]
    altered[0]['is_on'] = False
    checks, _ = evaluate('', altered)
    assert not checks['outlet_1_identity_state']

def test_equipment_on_blocks():
    altered = [dict(o) for o in GOOD]
    altered[1]['is_on'] = True
    checks, _ = evaluate('', altered)
    assert not checks['outlet_2_identity_state']
