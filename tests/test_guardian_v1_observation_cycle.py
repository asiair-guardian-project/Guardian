from datetime import datetime, timezone

from modules.asiair_state import AsiairStateTracker
from modules.capability_registry import CapabilityRegistry
from modules.guardian_types import (
    AsiairState,
    Capability,
    CapabilityStatus,
    MountMotionState,
    RoofState,
)
from modules.guardian_v1_observation_cycle import run_observation_cycle
from modules.observatory_observation_coordinator import (
    ObservatoryObservationCoordinator,
)
from modules.observatory_safety import ObservatorySafetyObservation


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


def test_read_only_observation_cycle_builds_normalized_snapshot():
    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    now = datetime.now(timezone.utc)

    result = run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
    )

    assert result.observation.roof_state is RoofState.OPEN
    assert result.observation.asiair_state is AsiairState.ONLINE
    assert result.observation.mount_motion is MountMotionState.UNKNOWN

    assert (
        registry.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )
    assert (
        registry.status(Capability.OBSERVATORY_SAFETY_MONITORING)
        is CapabilityStatus.AVAILABLE
    )
    assert (
        registry.status(Capability.INDEPENDENT_MOUNT_MOTION)
        is CapabilityStatus.UNKNOWN
    )


class UnreachableAsiairAdapter:
    def is_reachable(self):
        return False


def test_observation_cycle_distinguishes_asiair_loss_from_monitor_failure():
    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    tracker = AsiairStateTracker()
    tracker.observe(True)

    now = datetime.now(timezone.utc)

    result = run_observation_cycle(
        registry=registry,
        asiair_tracker=tracker,
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=UnreachableAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
    )

    assert result.observation.asiair_state is AsiairState.LOST

    assert (
        registry.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.AVAILABLE
    )


class FailedAsiairMonitorAdapter:
    def is_reachable(self):
        raise RuntimeError("monitoring path failed")


def test_observation_cycle_distinguishes_monitor_failure_from_asiair_loss():
    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    tracker = AsiairStateTracker()
    tracker.observe(True)

    now = datetime.now(timezone.utc)

    result = run_observation_cycle(
        registry=registry,
        asiair_tracker=tracker,
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FailedAsiairMonitorAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
    )

    assert result.observation.asiair_state is AsiairState.ONLINE

    assert (
        registry.status(Capability.ASIAIR_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


class FailedObservatoryAdapter:
    def observe(self):
        raise RuntimeError("observatory monitoring path failed")


def test_observation_cycle_does_not_trust_stale_roof_after_monitor_failure():
    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    coordinator = ObservatoryObservationCoordinator()

    initial_time = datetime.now(timezone.utc)

    run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=coordinator,
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(initial_time),
        now=initial_time,
        roof_max_age_seconds=30,
    )

    from datetime import timedelta

    later = initial_time + timedelta(seconds=31)

    result = run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=coordinator,
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FailedObservatoryAdapter(),
        now=later,
        roof_max_age_seconds=30,
    )

    assert result.observation.roof_state is RoofState.UNKNOWN

    assert (
        registry.status(Capability.OBSERVATORY_SAFETY_MONITORING)
        is CapabilityStatus.UNKNOWN
    )


class UnknownMountAdapter:
    capabilities = FakeMountAdapter.capabilities

    def query_motion(self):
        return MountMotionState.UNKNOWN


def test_observation_cycle_treats_unknown_mount_motion_conservatively():
    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    now = datetime.now(timezone.utc)

    result = run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
    )

    assert result.observation.mount_motion is MountMotionState.UNKNOWN

    for capability in UnknownMountAdapter.capabilities:
        assert (
            registry.status(capability)
            is CapabilityStatus.UNKNOWN
        )


def test_observation_cycle_probes_safety_power_without_switching():
    from modules.guardian_types import SafetyPowerRole
    from modules.safety_power import (
        SafetyPowerEndpoint,
        SafetyPowerTopology,
    )

    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.SAFETY_POWER_CONTROL,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
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

    class FakeSafetyPowerAdapter:
        controller_id = "controller-1"
        supports_verification = False

        def __init__(self):
            self.checked = []

        def check_endpoint(self, endpoint):
            self.checked.append(endpoint)
            return True

        def power_off(self, endpoint):
            raise AssertionError(
                "observation cycle must never switch power"
            )

    safety_power_adapter = FakeSafetyPowerAdapter()
    now = datetime.now(timezone.utc)

    run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": safety_power_adapter,
        },
    )

    assert (
        registry.status(Capability.SAFETY_POWER_CONTROL)
        is CapabilityStatus.AVAILABLE
    )

    assert set(safety_power_adapter.checked) == {
        asiair_endpoint,
        mount_endpoint,
    }


def test_observation_cycle_marks_safety_power_unknown_on_probe_failure():
    from modules.guardian_types import SafetyPowerRole
    from modules.safety_power import (
        SafetyPowerEndpoint,
        SafetyPowerTopology,
    )

    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.SAFETY_POWER_CONTROL,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR:
                SafetyPowerEndpoint("controller-1", "asiair"),
            SafetyPowerRole.MOUNT:
                SafetyPowerEndpoint("controller-1", "mount"),
        }
    )

    class FailedSafetyPowerAdapter:
        controller_id = "controller-1"
        supports_verification = False

        def check_endpoint(self, endpoint):
            raise RuntimeError("safety power controller unreachable")

        def power_off(self, endpoint):
            raise AssertionError(
                "observation cycle must never switch power"
            )

    now = datetime.now(timezone.utc)

    run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FailedSafetyPowerAdapter(),
        },
    )

    assert (
        registry.status(Capability.SAFETY_POWER_CONTROL)
        is CapabilityStatus.UNKNOWN
    )


def test_observation_cycle_marks_safety_power_failed_for_incomplete_topology():
    from modules.guardian_types import SafetyPowerRole
    from modules.safety_power import (
        SafetyPowerEndpoint,
        SafetyPowerTopology,
    )

    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.SAFETY_POWER_CONTROL,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    # Deliberately incomplete: ASIAIR exists, MOUNT does not.
    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR:
                SafetyPowerEndpoint("controller-1", "asiair"),
        }
    )

    class FakeSafetyPowerAdapter:
        controller_id = "controller-1"
        supports_verification = False

        def check_endpoint(self, endpoint):
            return True

        def power_off(self, endpoint):
            raise AssertionError(
                "observation cycle must never switch power"
            )

    now = datetime.now(timezone.utc)

    run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FakeSafetyPowerAdapter(),
        },
    )

    assert (
        registry.status(Capability.SAFETY_POWER_CONTROL)
        is CapabilityStatus.FAILED
    )


def test_observation_cycle_safety_power_capability_feeds_runtime_readiness():
    from modules.commissioning import (
        CommissioningCheck,
        CommissioningResult,
        CommissioningStatus,
    )
    from modules.guardian_types import (
        SafetyPowerRole,
        SessionState,
    )
    from modules.guardian_v1_application import GuardianV1Application
    from modules.safety_power import (
        SafetyPowerEndpoint,
        SafetyPowerTopology,
    )

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

    class FakeSafetyPowerAdapter:
        controller_id = "controller-1"
        supports_verification = False

        def check_endpoint(self, endpoint):
            return True

        def power_off(self, endpoint):
            raise AssertionError(
                "shadow observation must never switch power"
            )

    now = datetime.now(timezone.utc)

    cycle = run_observation_cycle(
        registry=app.capabilities,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FakeSafetyPowerAdapter(),
        },
    )

    assert (
        app.capabilities.status(Capability.SAFETY_POWER_CONTROL)
        is CapabilityStatus.AVAILABLE
    )

    fingerprint = "observation-cycle-runtime-test"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    executed_actions = []

    result = app.evaluate_observation(
        armed=True,
        observation=cycle.observation,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    assert result.session.state is SessionState.IMAGING_PERMITTED
    assert result.incident is None
    assert executed_actions == []


def test_active_session_aborts_when_safety_power_capability_is_lost():
    from modules.commissioning import (
        CommissioningCheck,
        CommissioningResult,
        CommissioningStatus,
    )
    from modules.guardian_types import (
        SafetyPowerRole,
        SessionState,
    )
    from modules.guardian_v1_application import GuardianV1Application
    from modules.safety_power import (
        SafetyPowerEndpoint,
        SafetyPowerTopology,
    )

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

    class HealthySafetyPowerAdapter:
        controller_id = "controller-1"
        supports_verification = False

        def check_endpoint(self, endpoint):
            return True

        def power_off(self, endpoint):
            raise AssertionError(
                "shadow mode must never switch power"
            )

    class FailedSafetyPowerAdapter:
        controller_id = "controller-1"
        supports_verification = False

        def check_endpoint(self, endpoint):
            raise RuntimeError(
                "safety power controller unreachable"
            )

        def power_off(self, endpoint):
            raise AssertionError(
                "shadow mode must never switch power"
            )

    tracker = AsiairStateTracker()
    observatory = ObservatoryObservationCoordinator()

    fingerprint = "safety-power-loss-test"

    commissioning = CommissioningStatus(
        results={
            check: CommissioningResult.VERIFIED
            for check in CommissioningCheck
        },
        configuration_fingerprint=fingerprint,
    )

    first_time = datetime.now(timezone.utc)

    healthy_cycle = run_observation_cycle(
        registry=app.capabilities,
        asiair_tracker=tracker,
        observatory_coordinator=observatory,
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(first_time),
        now=first_time,
        roof_max_age_seconds=30,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": HealthySafetyPowerAdapter(),
        },
    )

    executed_actions = []

    initial = app.evaluate_observation(
        armed=True,
        observation=healthy_cycle.observation,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    assert initial.session.state is SessionState.IMAGING_PERMITTED
    assert initial.incident is None

    second_time = first_time

    failed_cycle = run_observation_cycle(
        registry=app.capabilities,
        asiair_tracker=tracker,
        observatory_coordinator=observatory,
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(second_time),
        now=second_time,
        roof_max_age_seconds=30,
        safety_power_topology=topology,
        safety_power_adapters={
            "controller-1": FailedSafetyPowerAdapter(),
        },
    )

    assert (
        app.capabilities.status(Capability.SAFETY_POWER_CONTROL)
        is CapabilityStatus.UNKNOWN
    )

    protected = app.evaluate_observation(
        armed=True,
        observation=failed_cycle.observation,
        commissioning=commissioning,
        configuration_fingerprint=fingerprint,
        execute_action=executed_actions.append,
    )

    assert protected.session.state is SessionState.ABORTED
    assert protected.incident is not None
    assert executed_actions == []


def test_new_roof_observation_after_cycle_start_is_not_rejected_as_future():
    from datetime import timedelta

    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
            Capability.INDEPENDENT_MOUNT_MOTION,
            Capability.INDEPENDENT_MOUNT_STOP,
            Capability.MOUNT_STOP_VERIFICATION,
            Capability.MOUNT_CONNECTION_RECOVERY,
        }
    )

    cycle_start = datetime.now(timezone.utc)
    observation_time = cycle_start + timedelta(milliseconds=10)

    result = run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(observation_time),
        now=cycle_start,
        roof_max_age_seconds=30,
    )

    assert result.observation.roof_state is RoofState.OPEN


def test_observation_cycle_never_accesses_wave_adapter():
    """No Wave Wi-Fi communication is permitted during observations."""

    class ForbiddenMountAdapter:
        def __getattribute__(self, name):
            raise AssertionError(
                f"Unexpected Wave adapter access: {name}"
            )

    now = datetime.now(timezone.utc)

    registry = CapabilityRegistry(
        configured_capabilities={
            Capability.ASIAIR_MONITORING,
            Capability.OBSERVATORY_SAFETY_MONITORING,
        }
    )

    result = run_observation_cycle(
        registry=registry,
        asiair_tracker=AsiairStateTracker(),
        observatory_coordinator=ObservatoryObservationCoordinator(),
        asiair_adapter=FakeAsiairAdapter(),
        observatory_adapter=FakeObservatoryAdapter(now),
        now=now,
        roof_max_age_seconds=30,
    )

    assert result.observation.roof_state is RoofState.OPEN
    assert result.observation.mount_motion is MountMotionState.UNKNOWN
