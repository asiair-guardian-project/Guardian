"""Test-wide settings for Guardian's pacing, so logic tests run instantly.

Production paces the retry of an unresolved shutdown (15 s, then 60 s, then
300 s) and waits 5 s before reading a cut back. Tests of retry LOGIC should not
sit through that, so by default every test sees retries that are always due and
no read-back pause. Tests that check the pacing itself set their own clock and
gap explicitly (see test_guardian_v1_emergency_pacing.py).
"""
import itertools

import pytest


@pytest.fixture(autouse=True)
def _instant_emergency_pacing(monkeypatch):
    import modules.kasa_safety_power_adapter as kasa
    import modules.protection_coordinator as coordinator

    ticks = itertools.count(0, 1000)  # each reading is 1000 s later: always due
    monkeypatch.setattr(coordinator, "_now", lambda: float(next(ticks)))
    monkeypatch.setattr(kasa, "DEFAULT_VERIFY_GAP_SECONDS", 0.0)
