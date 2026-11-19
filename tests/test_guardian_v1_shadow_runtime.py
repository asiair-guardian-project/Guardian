from datetime import datetime, timezone

from modules.asiair_state import AsiairStateTracker
from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    CommissioningStatus,
)
from modules.guardian_types import (
    Capability,
    MountMotionState,
    RoofState,
    SafetyPowerRole,
    SessionState,
)
from modules.guardian_v1_application import GuardianV1Application
from modules.guardian_v1_shadow_runtime import GuardianV1ShadowRuntime
from modules.observatory_observation_coordinator import (
    ObservatoryObservationCoordinator,
)
from modules.observatory_safety import ObservatorySafetyObservation
from modules.safety_power import (
    SafetyPowerEndpoint,
    SafetyPowerTopology,
)


class FakeAsiairAdapter:
    def is_reachable(self):
        return True


class FakeObservatoryAdapter:
    def __init__(self, observed_at):
        self.observed_at = observed_at

    def observe(self):
        return ObservatorySafetyObservation(
            state=RoofState.OPEN,
            observed_at=self.observed_at,
        )


class FakeMountAdapter:
    capabilities = frozenset(
        {
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    def query_motion(self):
        return MountMotionState.STATIONARY


class FakeSafetyPowerAdapter:
    controller_id = "controller-1"
    supports_verification = False

    def check_endpoint(self, endpoint):
        return True

    def power_off(self, endpoint):
        raise AssertionError(
            "shadow runtime must never switch power"
        )


def test_shadow_runtime_runs_one_read_only_cycle():
    configured = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
        Capability.MOUNT_CONNECTION_RECOVERY,
    }

    app = GuardianV1Application(
        configured_capabilities=configured,
    )

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR:
                SafetyPowerEndpoint("controller-1", "asiair"),
            SafetyPowerRole.MOUNT:
                SafetyPowerEndpoint("controller-1", "mount"),
        }
    )

    fingerprint = "shadow-runtime-test"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    now = datetime.now(timezone.utc)
    executed_actions = []

    runtime = GuardianV1ShadowRuntime(
        application=app,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FakeSafetyPowerAdapter(),
        },
        roof_max_age_seconds=30,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    result = runtime.run_cycle(
        armed=True,
        now=now,
    )

    assert result.observation.roof_state is RoofState.OPEN
    assert result.observation.mount_motion is MountMotionState.UNKNOWN
    assert result.evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert result.evaluation.incident is None

    # Shadow runtime may evaluate protection logic but must never execute
    # physical hardware actions.
    assert executed_actions == []
    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_shadow_runtime_roof_closure_aborts_without_hardware_execution():
    configured = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
        Capability.MOUNT_CONNECTION_RECOVERY,
    }

    app = GuardianV1Application(
        configured_capabilities=configured,
    )

    asiair_endpoint = SafetyPowerEndpoint(
        "controller-1",
        "asiair",
    )
    mount_endpoint = SafetyPowerEndpoint(
        "controller-1",
        "mount",
    )

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair_endpoint,
            SafetyPowerRole.MOUNT: mount_endpoint,
        }
    )

    fingerprint = "shadow-runtime-roof-close"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    class MutableObservatoryAdapter:
        def __init__(self):
            self.state = RoofState.OPEN
            self.observed_at = datetime.now(timezone.utc)

        def observe(self):
            return ObservatorySafetyObservation(
                state=self.state,
                observed_at=self.observed_at,
            )

    observatory_adapter = MutableObservatoryAdapter()
    executed_actions = []

    runtime = GuardianV1ShadowRuntime(
        application=app,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=observatory_adapter,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FakeSafetyPowerAdapter(),
        },
        roof_max_age_seconds=30,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    first_time = observatory_adapter.observed_at

    healthy = runtime.run_cycle(
        armed=True,
        now=first_time,
    )

    assert (
        healthy.evaluation.session.state
        is SessionState.IMAGING_PERMITTED
    )
    assert healthy.evaluation.incident is None

    # Simulate the next read-only observatory observation reporting
    # that the roof is now closed.
    observatory_adapter.state = RoofState.CLOSED
    observatory_adapter.observed_at = first_time

    protected = runtime.run_cycle(
        armed=True,
        now=first_time,
    )

    assert protected.observation.roof_state is RoofState.CLOSED
    assert protected.evaluation.session.state is SessionState.ABORTED
    assert protected.evaluation.incident is not None

    # Guardian recognized the protection event, but the application
    # remains monitor-only.
    assert executed_actions == []
    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_shadow_runtime_sustained_unknown_triggers_protection():
    from datetime import timedelta

    configured = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
        Capability.MOUNT_CONNECTION_RECOVERY,
    }

    app = GuardianV1Application(
        configured_capabilities=configured,
    )

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR:
                SafetyPowerEndpoint("controller-1", "asiair"),
            SafetyPowerRole.MOUNT:
                SafetyPowerEndpoint("controller-1", "mount"),
        }
    )

    fingerprint = "shadow-runtime-unknown"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    class MutableObservatoryAdapter:
        def __init__(self):
            self.state = RoofState.OPEN
            self.observed_at = datetime.now(timezone.utc)

        def observe(self):
            return ObservatorySafetyObservation(
                state=self.state,
                observed_at=self.observed_at,
            )

    observatory_adapter = MutableObservatoryAdapter()
    executed_actions = []

    runtime = GuardianV1ShadowRuntime(
        application=app,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=observatory_adapter,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FakeSafetyPowerAdapter(),
        },
        roof_max_age_seconds=30,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    start = observatory_adapter.observed_at

    healthy = runtime.run_cycle(armed=True, now=start)
    assert healthy.evaluation.session.state is SessionState.IMAGING_PERMITTED

    observatory_adapter.state = RoofState.UNKNOWN

    for i in range(12):
        now = start + timedelta(seconds=i * 5)
        observatory_adapter.observed_at = now

        result = runtime.run_cycle(armed=True, now=now)

        assert result.observation.roof_state is RoofState.UNKNOWN
        assert result.roof_filter.effective_state is RoofState.UNKNOWN
        assert not result.roof_filter.timed_out
        assert result.evaluation.session.state is SessionState.IMAGING_PERMITTED

    now = start + timedelta(seconds=60)
    observatory_adapter.observed_at = now

    result = runtime.run_cycle(armed=True, now=now)

    assert result.observation.roof_state is RoofState.UNKNOWN
    assert result.roof_filter.consecutive_unknown == 13
    assert result.roof_filter.timed_out
    assert result.roof_filter.effective_state is RoofState.CLOSED
    assert result.evaluation.session.state is SessionState.ABORTED
    assert result.evaluation.incident is not None

    # No hardware execution, even when the UNKNOWN timeout triggers.
    assert executed_actions == []
    assert app.mode.monitor_only is True
    assert app.mode.hardware_execution_enabled is False


def test_shadow_runtime_alpaca_failure_uses_unknown_grace_period():
    from datetime import timedelta

    from modules.guardian_types import CapabilityStatus

    configured = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
        Capability.MOUNT_CONNECTION_RECOVERY,
    }

    app = GuardianV1Application(configured_capabilities=configured)

    topology = SafetyPowerTopology({
        SafetyPowerRole.ASIAIR:
            SafetyPowerEndpoint("controller-1", "asiair"),
        SafetyPowerRole.MOUNT:
            SafetyPowerEndpoint("controller-1", "mount"),
    })

    fingerprint = "shadow-alpaca-failure"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    class FailingObservatoryAdapter:
        def __init__(self):
            self.failed = False
            self.observed_at = datetime.now(timezone.utc)

        def observe(self):
            if self.failed:
                raise TimeoutError("Alpaca connection timed out")

            return ObservatorySafetyObservation(
                state=RoofState.OPEN,
                observed_at=self.observed_at,
            )

    adapter = FailingObservatoryAdapter()
    executed_actions = []

    runtime = GuardianV1ShadowRuntime(
        application=app,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=adapter,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FakeSafetyPowerAdapter(),
        },
        roof_max_age_seconds=30,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    start = adapter.observed_at

    healthy = runtime.run_cycle(armed=True, now=start)
    assert healthy.evaluation.session.state is SessionState.IMAGING_PERMITTED

    adapter.failed = True

    for i in range(12):
        result = runtime.run_cycle(
            armed=True,
            now=start + timedelta(seconds=i * 5),
        )

        assert result.observation.roof_state is RoofState.UNKNOWN
        assert result.roof_filter.effective_state is RoofState.UNKNOWN
        assert not result.roof_filter.timed_out
        assert result.evaluation.session.state is SessionState.IMAGING_PERMITTED
        assert (
            app.capabilities.status(
                Capability.OBSERVATORY_SAFETY_MONITORING
            )
            is CapabilityStatus.UNKNOWN
        )

    result = runtime.run_cycle(
        armed=True,
        now=start + timedelta(seconds=60),
    )

    assert result.roof_filter.timed_out
    assert result.roof_filter.effective_state is RoofState.CLOSED
    assert result.evaluation.session.state is SessionState.ABORTED
    assert result.evaluation.incident is not None
    assert executed_actions == []
    assert app.mode.hardware_execution_enabled is False


def test_shadow_incident_remains_latched_without_hardware_execution():
    """Roof closure, repeated retries, and reopening remain shadow-only."""
    from datetime import timedelta

    configured = {
        Capability.ASIAIR_MONITORING,
        Capability.OBSERVATORY_SAFETY_MONITORING,
        Capability.SAFETY_POWER_CONTROL,
        Capability.INDEPENDENT_MOUNT_MOTION,
        Capability.INDEPENDENT_MOUNT_STOP,
        Capability.MOUNT_STOP_VERIFICATION,
        Capability.MOUNT_CONNECTION_RECOVERY,
    }

    app = GuardianV1Application(configured_capabilities=configured)

    class MutableRoof:
        def __init__(self, now):
            self.state = RoofState.OPEN
            self.observed_at = now

        def observe(self):
            return ObservatorySafetyObservation(
                state=self.state,
                observed_at=self.observed_at,
            )

    class MovingMount(FakeMountAdapter):
        def query_motion(self):
            return MountMotionState.MOVING

    def forbidden(*args, **kwargs):
        raise AssertionError("Physical hardware callback invoked")

    start = datetime.now(timezone.utc)
    roof = MutableRoof(start)
    fingerprint = "shadow-incident-lifecycle"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    topology = SafetyPowerTopology({
        SafetyPowerRole.ASIAIR:
            SafetyPowerEndpoint("controller-1", "asiair"),
        SafetyPowerRole.MOUNT:
            SafetyPowerEndpoint("controller-1", "mount"),
    })

    runtime = GuardianV1ShadowRuntime(
        application=app,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=roof,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FakeSafetyPowerAdapter(),
        },
        roof_max_age_seconds=30,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=forbidden,
        execute_safety_power=forbidden,
    )

    # 1. Healthy imaging session.
    healthy = runtime.run_cycle(armed=True, now=start)
    assert healthy.evaluation.session.state is SessionState.IMAGING_PERMITTED
    assert healthy.evaluation.incident is None

    # 2. Roof closes during imaging.
    roof.state = RoofState.CLOSED
    roof.observed_at = start + timedelta(seconds=5)

    aborted = runtime.run_cycle(
        armed=True,
        now=roof.observed_at,
    )
    assert aborted.evaluation.session.state is SessionState.ABORTED
    assert aborted.evaluation.incident is not None

    # 3. Repeated cycles while the roof remains closed.
    for seconds in (10, 15, 20):
        roof.observed_at = start + timedelta(seconds=seconds)
        result = runtime.run_cycle(
            armed=True,
            now=roof.observed_at,
        )
        assert result.evaluation.session.state is SessionState.ABORTED
        assert result.evaluation.incident is not None

    # 4. Roof reopens; incident must remain latched.
    roof.state = RoofState.OPEN
    roof.observed_at = start + timedelta(seconds=25)

    reopened = runtime.run_cycle(
        armed=True,
        now=roof.observed_at,
    )
    assert reopened.evaluation.session.state is SessionState.ABORTED
    assert reopened.evaluation.incident is not None

    assert app.mode.monitor_only
    assert not app.mode.hardware_execution_enabled
