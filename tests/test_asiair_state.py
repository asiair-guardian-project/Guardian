from modules.asiair_state import AsiairStateTracker
from modules.guardian_types import AsiairState


def test_starts_not_established():
    tracker = AsiairStateTracker()
    assert tracker.state is AsiairState.NOT_ESTABLISHED


def test_offline_before_first_connection_remains_not_established():
    tracker = AsiairStateTracker()
    assert tracker.observe(False) is AsiairState.NOT_ESTABLISHED
    assert tracker.observe(False) is AsiairState.NOT_ESTABLISHED


def test_first_reachable_observation_establishes_online():
    tracker = AsiairStateTracker()
    assert tracker.observe(True) is AsiairState.ONLINE


def test_online_remains_online_while_reachable():
    tracker = AsiairStateTracker()
    tracker.observe(True)
    assert tracker.observe(True) is AsiairState.ONLINE


def test_offline_after_establishment_becomes_lost():
    tracker = AsiairStateTracker()
    tracker.observe(True)
    assert tracker.observe(False) is AsiairState.LOST


def test_lost_remains_lost_while_unreachable():
    tracker = AsiairStateTracker()
    tracker.observe(True)
    tracker.observe(False)
    assert tracker.observe(False) is AsiairState.LOST


def test_lost_asiair_can_return_online():
    tracker = AsiairStateTracker()
    tracker.observe(True)
    tracker.observe(False)
    assert tracker.observe(True) is AsiairState.ONLINE


def test_reset_clears_establishment_history():
    tracker = AsiairStateTracker()
    tracker.observe(True)
    tracker.observe(False)

    assert tracker.reset() is AsiairState.NOT_ESTABLISHED
    assert tracker.observe(False) is AsiairState.NOT_ESTABLISHED


def test_two_misses_in_a_row_are_needed_when_configured():
    tracker = AsiairStateTracker(lost_after_misses=2)
    tracker.observe(True)
    assert tracker.observe(False) is AsiairState.ONLINE
    assert tracker.observe(False) is AsiairState.LOST


def test_a_reply_between_misses_resets_the_count():
    tracker = AsiairStateTracker(lost_after_misses=2)
    tracker.observe(True)
    for _ in range(5):
        assert tracker.observe(False) is AsiairState.ONLINE
        assert tracker.observe(True) is AsiairState.ONLINE


def test_lost_recovers_on_the_first_reply():
    tracker = AsiairStateTracker(lost_after_misses=2)
    tracker.observe(True)
    tracker.observe(False)
    tracker.observe(False)
    assert tracker.observe(True) is AsiairState.ONLINE
    assert tracker.observe(False) is AsiairState.ONLINE  # count started again


def test_misses_before_first_connection_never_count():
    tracker = AsiairStateTracker(lost_after_misses=2)
    for _ in range(4):
        assert tracker.observe(False) is AsiairState.NOT_ESTABLISHED
    tracker.observe(True)
    assert tracker.observe(False) is AsiairState.ONLINE


def test_reset_clears_the_miss_count():
    tracker = AsiairStateTracker(lost_after_misses=2)
    tracker.observe(True)
    tracker.observe(False)
    tracker.reset()
    tracker.observe(True)
    assert tracker.observe(False) is AsiairState.ONLINE


def test_default_tracker_is_still_immediate_and_threshold_is_validated():
    import pytest
    tracker = AsiairStateTracker()
    tracker.observe(True)
    assert tracker.observe(False) is AsiairState.LOST
    with pytest.raises(ValueError):
        AsiairStateTracker(lost_after_misses=0)


def test_guardian_default_is_two():
    from modules.asiair_state import DEFAULT_LOST_AFTER_MISSES
    assert DEFAULT_LOST_AFTER_MISSES == 2
