from datetime import datetime


def roof_status_age_seconds(timestamp, now=None):
    """
    Return the age of a roof-status timestamp in seconds.

    `timestamp` must be a datetime.
    `now` may be supplied for testing.
    """

    if now is None:
        now = datetime.now()

    age = now - timestamp

    return age.total_seconds()


def roof_status_is_stale(timestamp, stale_after_seconds, now=None):
    """
    Return True if the roof-status timestamp is older than the threshold.

    This function does not choose the threshold.
    """

    age_seconds = roof_status_age_seconds(
        timestamp=timestamp,
        now=now,
    )

    # Reject timestamps more than five seconds in the future.
    # Small clock differences are tolerated.
    if age_seconds < -5:
        return True

    return age_seconds > stale_after_seconds