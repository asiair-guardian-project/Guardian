import pytest

from modules.guardian_types import SafetyPowerResult, SafetyPowerRole
from modules.safety_power import SafetyPowerEndpoint, SafetyPowerTopology
from modules.safety_power_manager import (
    SafetyPowerManager,
    SafetyPowerRoutingError,
)


class FakeAdapter:
    supports_verification = False
    def __init__(self, controller_id):
        self.controller_id = controller_id

    def power_off(self, endpoint):
        return SafetyPowerResult.COMMANDED_UNVERIFIED


def test_routes_endpoint_to_matching_controller():
    adapter = FakeAdapter("controller-1")
    manager = SafetyPowerManager(
        {"controller-1": adapter}
    )

    endpoint = SafetyPowerEndpoint(
        "controller-1",
        "output-1",
    )

    assert manager.adapter_for(endpoint) is adapter


def test_missing_controller_adapter_is_rejected():
    manager = SafetyPowerManager({})

    endpoint = SafetyPowerEndpoint(
        "controller-1",
        "output-1",
    )

    with pytest.raises(SafetyPowerRoutingError):
        manager.adapter_for(endpoint)


def test_mismatched_adapter_identity_is_rejected():
    adapter = FakeAdapter("controller-2")

    manager = SafetyPowerManager(
        {"controller-1": adapter}
    )

    endpoint = SafetyPowerEndpoint(
        "controller-1",
        "output-1",
    )

    with pytest.raises(SafetyPowerRoutingError):
        manager.adapter_for(endpoint)


def test_power_off_routes_command_to_correct_adapter():
    calls = []

    class RecordingAdapter(FakeAdapter):
        def power_off(self, endpoint):
            calls.append(endpoint)
            return SafetyPowerResult.COMMANDED_UNVERIFIED

    adapter = RecordingAdapter("controller-1")
    manager = SafetyPowerManager(
        {"controller-1": adapter}
    )

    endpoint = SafetyPowerEndpoint(
        "controller-1",
        "output-1",
    )

    result = manager.power_off(endpoint)

    assert calls == [endpoint]
    assert result is SafetyPowerResult.COMMANDED_UNVERIFIED


def test_power_off_rejects_unroutable_endpoint_without_command():
    adapter = FakeAdapter("controller-1")
    manager = SafetyPowerManager(
        {"controller-1": adapter}
    )

    endpoint = SafetyPowerEndpoint(
        "controller-2",
        "output-1",
    )

    with pytest.raises(SafetyPowerRoutingError):
        manager.power_off(endpoint)


def test_power_off_endpoints_respects_dependency_order():
    calls = []

    class RecordingAdapter(FakeAdapter):
        def power_off(self, endpoint):
            calls.append(endpoint)
            return SafetyPowerResult.COMMANDED_UNVERIFIED

    upstream = SafetyPowerEndpoint("controller-1", "upstream")
    downstream = SafetyPowerEndpoint("controller-2", "downstream")

    manager = SafetyPowerManager(
        {
            "controller-1": RecordingAdapter("controller-1"),
            "controller-2": RecordingAdapter("controller-2"),
        }
    )

    from modules.safety_power import (
        SafetyPowerEndpointRequirements,
        SafetyPowerResource,
        SafetyPowerResourceEffects,
    )

    controller_2 = SafetyPowerResource(
        "controller",
        "controller-2",
    )

    requirements = {
        downstream: SafetyPowerEndpointRequirements(
            downstream,
            frozenset({controller_2}),
        )
    }

    resource_effects = {
        upstream: SafetyPowerResourceEffects(
            upstream,
            frozenset({controller_2}),
        )
    }

    records = manager.power_off_endpoints(
        {upstream, downstream},
        requirements,
        resource_effects,
    )

    assert calls == [downstream, upstream]
    assert [record.endpoint for record in records] == [
        downstream,
        upstream,
    ]


def test_power_off_endpoints_continues_after_endpoint_failure():
    calls = []

    class FailingAdapter(FakeAdapter):
        def power_off(self, endpoint):
            calls.append(endpoint)
            raise RuntimeError("simulated failure")

    class WorkingAdapter(FakeAdapter):
        def power_off(self, endpoint):
            calls.append(endpoint)
            return SafetyPowerResult.COMMANDED_UNVERIFIED

    first = SafetyPowerEndpoint("controller-1", "output-1")
    second = SafetyPowerEndpoint("controller-2", "output-1")

    manager = SafetyPowerManager(
        {
            "controller-1": FailingAdapter("controller-1"),
            "controller-2": WorkingAdapter("controller-2"),
        }
    )

    records = manager.power_off_endpoints(
        {first, second},
        {},
        {},
    )

    assert len(calls) == 2

    results = {
        record.endpoint: record.result
        for record in records
    }

    assert results[first] is SafetyPowerResult.FAILED
    assert (
        results[second]
        is SafetyPowerResult.COMMANDED_UNVERIFIED
    )

def test_verifying_adapter_must_explicitly_confirm_off():
    class VerifyingAdapter(FakeAdapter):
        supports_verification = True

        def power_off(self, endpoint):
            return SafetyPowerResult.COMMANDED_UNVERIFIED

        def verify_off(self, endpoint):
            return SafetyPowerResult.VERIFIED_OFF

    endpoint = SafetyPowerEndpoint("controller-1", "output-1")
    manager = SafetyPowerManager(
        {"controller-1": VerifyingAdapter("controller-1")}
    )

    assert manager.power_off(endpoint) is SafetyPowerResult.VERIFIED_OFF

def test_failed_verification_is_failed():
    class VerifyingAdapter(FakeAdapter):
        supports_verification = True

        def power_off(self, endpoint):
            return SafetyPowerResult.COMMANDED_UNVERIFIED

        def verify_off(self, endpoint):
            return SafetyPowerResult.FAILED

    endpoint = SafetyPowerEndpoint("controller-1", "output-1")
    manager = SafetyPowerManager(
        {"controller-1": VerifyingAdapter("controller-1")}
    )

    assert manager.power_off(endpoint) is SafetyPowerResult.FAILED

def test_verification_exception_is_failed():
    class VerifyingAdapter(FakeAdapter):
        supports_verification = True

        def power_off(self, endpoint):
            return SafetyPowerResult.COMMANDED_UNVERIFIED

        def verify_off(self, endpoint):
            raise RuntimeError("verification unavailable")

    endpoint = SafetyPowerEndpoint("controller-1", "output-1")
    manager = SafetyPowerManager(
        {"controller-1": VerifyingAdapter("controller-1")}
    )

    assert manager.power_off(endpoint) is SafetyPowerResult.FAILED

def test_power_off_roles_deduplicates_shared_endpoint():
    calls = []

    class RecordingAdapter(FakeAdapter):
        def power_off(self, endpoint):
            calls.append(endpoint)
            return SafetyPowerResult.COMMANDED_UNVERIFIED

    shared = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: shared,
            SafetyPowerRole.MOUNT: shared,
        }
    )

    manager = SafetyPowerManager(
        {"controller-1": RecordingAdapter("controller-1")}
    )

    records = manager.power_off_roles(
        {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
        },
        topology,
        {},
        {},
    )

    assert calls == [shared]
    assert len(records) == 2
    assert {record.role for record in records} == {
        SafetyPowerRole.ASIAIR,
        SafetyPowerRole.MOUNT,
    }
    assert all(record.endpoint == shared for record in records)
    assert all(
        record.result is SafetyPowerResult.COMMANDED_UNVERIFIED
        for record in records
    )

def test_power_off_roles_handles_separate_endpoints():
    calls = []

    class RecordingAdapter(FakeAdapter):
        def power_off(self, endpoint):
            calls.append(endpoint)
            return SafetyPowerResult.COMMANDED_UNVERIFIED

    asiair = SafetyPowerEndpoint("controller-1", "output-1")
    mount = SafetyPowerEndpoint("controller-2", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
            SafetyPowerRole.MOUNT: mount,
        }
    )

    manager = SafetyPowerManager(
        {
            "controller-1": RecordingAdapter("controller-1"),
            "controller-2": RecordingAdapter("controller-2"),
        }
    )

    records = manager.power_off_roles(
        {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
        },
        topology,
        {},
        {},
    )

    assert set(calls) == {asiair, mount}
    assert len(calls) == 2

    results = {
        record.role: (record.endpoint, record.result)
        for record in records
    }

    assert results[SafetyPowerRole.ASIAIR] == (
        asiair,
        SafetyPowerResult.COMMANDED_UNVERIFIED,
    )
    assert results[SafetyPowerRole.MOUNT] == (
        mount,
        SafetyPowerResult.COMMANDED_UNVERIFIED,
    )


def test_power_off_roles_reports_missing_role_endpoint_as_failed():
    asiair = SafetyPowerEndpoint("controller-1", "output-1")

    topology = SafetyPowerTopology(
        {
            SafetyPowerRole.ASIAIR: asiair,
        }
    )

    manager = SafetyPowerManager(
        {
            "controller-1": FakeAdapter("controller-1"),
        }
    )

    records = manager.power_off_roles(
        {
            SafetyPowerRole.ASIAIR,
            SafetyPowerRole.MOUNT,
        },
        topology,
        {},
        {},
    )

    results = {
        record.role: record
        for record in records
    }

    assert results[SafetyPowerRole.ASIAIR].endpoint == asiair
    assert (
        results[SafetyPowerRole.MOUNT].endpoint
        is None
    )
    assert (
        results[SafetyPowerRole.MOUNT].result
        is SafetyPowerResult.FAILED
    )
