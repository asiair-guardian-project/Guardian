from datetime import datetime


class SessionManager:
    """Tracks Guardian imaging-session state."""

    DISARMED = "DISARMED"
    WAITING_FOR_ROOF = "WAITING_FOR_ROOF"
    IMAGING_PERMITTED = "IMAGING_PERMITTED"
    ABORTED = "ABORTED"

    def __init__(self, observatory_name, guardian_version):
        self.observatory_name = observatory_name
        self.guardian_version = guardian_version

        self.state = self.DISARMED

        self.started_at = None
        self.permitted_at = None
        self.ended_at = None

    @property
    def active(self):
        """
        Return True only while Guardian protection is armed.

        WAITING_FOR_ROOF and IMAGING_PERMITTED are protected states.
        ABORTED records an abnormal end state but is no longer active.
        """

        return self.state in {
            self.WAITING_FOR_ROOF,
            self.IMAGING_PERMITTED,
        }

    @property
    def imaging_permitted(self):
        """Return True only when imaging is permitted to operate."""

        return self.state == self.IMAGING_PERMITTED

    def start(self):
        """
        Arm Guardian for an imaging session.

        Imaging does not begin immediately.
        Guardian initially waits for a fresh OPEN roof state.
        """

        if self.active:
            return False

        self.state = self.WAITING_FOR_ROOF
        self.started_at = datetime.now()
        self.permitted_at = None
        self.ended_at = None

        return True

    def permit_imaging(self):
        """Permit imaging after the roof gate has been satisfied."""

        if self.state != self.WAITING_FOR_ROOF:
            return False

        self.state = self.IMAGING_PERMITTED
        self.permitted_at = datetime.now()

        return True

    def abort(self):
        """Abort the current protected imaging session."""

        if not self.active:
            return False

        self.state = self.ABORTED
        self.ended_at = datetime.now()

        return True
    
    def restore_emergency_abort(self):
        """Restore an aborted session without rearming equipment."""
        if self.active:
            return False

        self.state = self.ABORTED
        self.started_at = None
        self.permitted_at = None
        self.ended_at = datetime.now()
        return True

    def stop(self):
        """End the current protected imaging session."""

        if not self.active:
            return False

        self.state = self.DISARMED
        self.ended_at = datetime.now()

        return True

    def status(self):
        """Return the current session state."""

        return {
            "state": self.state,
            "active": self.active,
            "imaging_permitted": self.imaging_permitted,
            "started_at": self.started_at,
            "permitted_at": self.permitted_at,
            "ended_at": self.ended_at,
            "observatory_name": self.observatory_name,
            "guardian_version": self.guardian_version,
        }