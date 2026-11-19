"""Guardian 1.0 Kasa Safety Power adapter."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class KasaEndpointConfig:
    """Expected physical identity of one Kasa-controlled endpoint."""

    outlet_number: int
    expected_alias: str

    def __post_init__(self) -> None:
        if self.outlet_number < 1:
            raise ValueError("outlet_number must be at least 1")

        if not self.expected_alias.strip():
            raise ValueError("expected_alias must not be empty")

from collections.abc import Mapping
from typing import Protocol

from modules.guardian_types import (
    SafetyPowerResult,
    SafetyPowerState,
)
from modules.safety_power import SafetyPowerEndpoint


class KasaTransport(Protocol):
    """Low-level Kasa operations required by the Guardian adapter."""

    def check_outlet(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> bool:
        ...

    def get_outlet_state(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> SafetyPowerState:
        ...

    def power_off_outlet(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> bool:
        ...


class KasaSafetyPowerAdapter:
    """Guardian Safety Power adapter for a configured Kasa controller."""

    def __init__(
        self,
        *,
        controller_id: str,
        endpoints: Mapping[str, KasaEndpointConfig],
        transport: KasaTransport,
    ) -> None:
        if not controller_id.strip():
            raise ValueError("controller_id must not be empty")

        self._controller_id = controller_id
        self._endpoints = dict(endpoints)
        self._transport = transport

    @property
    def controller_id(self) -> str:
        return self._controller_id

    @property
    def supports_verification(self) -> bool:
        return True

    def _config_for(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> KasaEndpointConfig:
        if endpoint.controller_id != self.controller_id:
            raise ValueError(
                "endpoint controller_id does not match Kasa adapter"
            )

        try:
            return self._endpoints[endpoint.endpoint_id]
        except KeyError as error:
            raise ValueError(
                f"unknown Kasa endpoint_id: {endpoint.endpoint_id!r}"
            ) from error

    def check_endpoint(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> bool:
        config = self._config_for(endpoint)

        return self._transport.check_outlet(
            config.outlet_number,
            config.expected_alias,
        )

    def get_power_state(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerState:
        config = self._config_for(endpoint)

        return self._transport.get_outlet_state(
            config.outlet_number,
            config.expected_alias,
        )

    def power_off(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerResult:
        config = self._config_for(endpoint)

        command_sent = self._transport.power_off_outlet(
            config.outlet_number,
            config.expected_alias,
        )

        if not command_sent:
            return SafetyPowerResult.FAILED

        return SafetyPowerResult.COMMANDED_UNVERIFIED

    def verify_off(
        self,
        endpoint: SafetyPowerEndpoint,
    ) -> SafetyPowerResult:
        state = self.get_power_state(endpoint)

        if state is SafetyPowerState.OFF:
            return SafetyPowerResult.VERIFIED_OFF

        return SafetyPowerResult.FAILED

    # ---- batch path: one connection for all outlets -------------------
    # Connecting to the strip costs about 1.4 s, so an emergency shutdown
    # must not reconnect for every outlet and every check. These methods
    # command every outlet over one connection, then verify them all over
    # a second, fresh one (a fresh read is required: state read on the
    # command connection can be stale). Each outlet keeps its own identity
    # check and its own result; one bad outlet never blocks the others.

    @property
    def supports_batch(self) -> bool:
        return (
            hasattr(self._transport, "power_off_outlets")
            and hasattr(self._transport, "get_outlet_states")
        )

    def _configs_for(self, endpoints):
        """Return ({endpoint: config}, [endpoints that could not be mapped])."""

        configs = {}
        unmapped = []

        for endpoint in endpoints:
            try:
                configs[endpoint] = self._config_for(endpoint)
            except ValueError:
                unmapped.append(endpoint)

        return configs, unmapped

    def check_endpoints(self, endpoints):
        """Check several endpoints over ONE connection: {endpoint: valid}.

        An outlet counts as valid when it can be read and carries the
        expected name. A strip that cannot be reached marks every endpoint
        invalid. Raises if the transport cannot read in batch.
        """

        endpoints = list(endpoints)
        configs, _unmapped = self._configs_for(endpoints)
        results = {endpoint: False for endpoint in endpoints}

        if not configs:
            return results

        requests = [
            (config.outlet_number, config.expected_alias)
            for config in configs.values()
        ]
        states = self._transport.get_outlet_states(requests)

        for endpoint, config in configs.items():
            results[endpoint] = states.get(config.outlet_number) is not None

        return results

    def power_off_many(self, endpoints):
        """Command several endpoints OFF over one connection, in the order given."""

        endpoints = list(endpoints)
        configs, unmapped = self._configs_for(endpoints)
        results = {endpoint: SafetyPowerResult.FAILED for endpoint in endpoints}

        if not configs:
            return results

        requests = [
            (config.outlet_number, config.expected_alias)
            for config in configs.values()
        ]

        try:
            sent = self._transport.power_off_outlets(requests)
        except Exception:
            return results

        for endpoint, config in configs.items():
            if sent.get(config.outlet_number) is True:
                results[endpoint] = SafetyPowerResult.COMMANDED_UNVERIFIED

        return results

    def verify_off_many(self, endpoints):
        """Verify several endpoints are OFF over one fresh connection."""

        endpoints = list(endpoints)
        configs, unmapped = self._configs_for(endpoints)
        results = {endpoint: SafetyPowerResult.FAILED for endpoint in endpoints}

        if not configs:
            return results

        requests = [
            (config.outlet_number, config.expected_alias)
            for config in configs.values()
        ]

        try:
            states = self._transport.get_outlet_states(requests)
        except Exception:
            return results

        for endpoint, config in configs.items():
            if states.get(config.outlet_number) is SafetyPowerState.OFF:
                results[endpoint] = SafetyPowerResult.VERIFIED_OFF

        return results


import asyncio
import time

from modules.kasa_hs300_connection import (
    close_hs300,
    connect_hs300,
)


class KasaTransportError(RuntimeError):
    """Raised when Kasa communication or endpoint validation fails."""


# v0.6 waits 5 s after commanding outlets off before opening a fresh
# connection to verify: the HS300 does not like closely spaced connections.
# Only the READ-BACK waits; the OFF command itself is never delayed.
VERIFY_GAP_SECONDS_V06 = 5.0
DEFAULT_VERIFY_GAP_SECONDS = VERIFY_GAP_SECONDS_V06


class PythonKasaTransport:
    """Synchronous Guardian transport backed by python-kasa."""

    def __init__(
        self,
        *,
        host: str,
        username: str,
        password: str,
        timeout_seconds: int = 5,
        verify_gap_seconds: float | None = None,
        clock=time.monotonic,
        sleep=time.sleep,
    ) -> None:
        if not host.strip():
            raise ValueError("host must not be empty")

        if not username:
            raise ValueError("username must not be empty")

        if not password:
            raise ValueError("password must not be empty")

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        self._verify_gap_seconds = (
            DEFAULT_VERIFY_GAP_SECONDS
            if verify_gap_seconds is None else verify_gap_seconds
        )
        if self._verify_gap_seconds < 0:
            raise ValueError("verify_gap_seconds must not be negative")
        self._clock = clock
        self._sleep = sleep
        self._last_command_end = None
        self._host = host
        self._username = username
        self._password = password
        self._timeout_seconds = timeout_seconds

    async def _get_device(self):
        try:
            return await connect_hs300(
                self._host,
                self._username,
                self._password,
                timeout_seconds=self._timeout_seconds,
            )

        except Exception as error:
            raise KasaTransportError(
                f"unable to communicate with Kasa controller "
                f"{self._host}: {error}"
            ) from error

    async def _validated_outlet(
        self,
        outlet_number: int,
        expected_alias: str,
    ):
        device = await self._get_device()

        try:
            children = getattr(device, "children", None)

            if not children or len(children) < outlet_number:
                raise KasaTransportError(
                    f"Kasa outlet {outlet_number} is unavailable"
                )

            outlet = children[outlet_number - 1]

            try:
                await outlet.update()
            except Exception as error:
                raise KasaTransportError(
                    f"unable to update Kasa outlet "
                    f"{outlet_number}: {error}"
                ) from error

            if outlet.alias != expected_alias:
                raise KasaTransportError(
                    f"Kasa outlet {outlet_number} identity mismatch: "
                    f"expected {expected_alias!r}, "
                    f"found {outlet.alias!r}"
                )

            return device, outlet

        except Exception:
            await close_hs300(device)
            raise

    async def _check_outlet_async(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> bool:
        device, _outlet = await self._validated_outlet(
            outlet_number,
            expected_alias,
        )

        try:
            return True
        finally:
            await close_hs300(device)

    def check_outlet(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> bool:
        return asyncio.run(
            self._check_outlet_async(
                outlet_number,
                expected_alias,
            )
        )

    async def _get_outlet_state_async(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> SafetyPowerState:
        device, outlet = await self._validated_outlet(
            outlet_number,
            expected_alias,
        )

        try:
            return (
                SafetyPowerState.ON
                if outlet.is_on
                else SafetyPowerState.OFF
            )
        finally:
            await close_hs300(device)

    def get_outlet_state(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> SafetyPowerState:
        return asyncio.run(
            self._get_outlet_state_async(
                outlet_number,
                expected_alias,
            )
        )

    async def _power_off_outlet_async(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> bool:
        device, outlet = await self._validated_outlet(
            outlet_number,
            expected_alias,
        )

        try:
            if (
                os.environ.get("PYTEST_CURRENT_TEST")
                and os.environ.get(
                    "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS"
                ) != "YES_I_UNDERSTAND"
            ):
                raise KasaTransportError(
                    "Kasa hardware switching is blocked during "
                    "automated tests. Set "
                    "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS="
                    "YES_I_UNDERSTAND only for deliberate "
                    "live-hardware testing."
                )

            await outlet.turn_off()

        except KasaTransportError:
            raise

        except Exception as error:
            raise KasaTransportError(
                f"unable to power off Kasa outlet "
                f"{outlet_number} ({expected_alias}): {error}"
            ) from error

        finally:
            await close_hs300(device)

        return True

    def power_off_outlet(
        self,
        outlet_number: int,
        expected_alias: str,
    ) -> bool:
        return asyncio.run(
            self._power_off_outlet_async(
                outlet_number,
                expected_alias,
            )
        )

    # ---- batch path: one connection, per-outlet validation -------------

    async def _validated_child(self, device, outlet_number, expected_alias):
        """Return the child outlet after number and name checks, or raise."""

        children = getattr(device, "children", None)

        if not children or len(children) < outlet_number:
            raise KasaTransportError(
                f"Kasa outlet {outlet_number} is unavailable"
            )

        outlet = children[outlet_number - 1]
        await outlet.update()

        if outlet.alias != expected_alias:
            raise KasaTransportError(
                f"Kasa outlet {outlet_number} identity mismatch: "
                f"expected {expected_alias!r}, found {outlet.alias!r}"
            )

        return outlet

    async def _power_off_outlets_async(self, requests) -> dict:
        results = {number: False for number, _alias in requests}

        if (
            os.environ.get("PYTEST_CURRENT_TEST")
            and os.environ.get("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS")
            != "YES_I_UNDERSTAND"
        ):
            raise KasaTransportError(
                "Kasa hardware switching is blocked during automated "
                "tests. Set GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS="
                "YES_I_UNDERSTAND only for deliberate live-hardware "
                "testing."
            )

        try:
            device = await self._get_device()
        except KasaTransportError:
            return results

        try:
            for number, alias in requests:
                try:
                    outlet = await self._validated_child(
                        device, number, alias
                    )
                    await outlet.turn_off()
                    results[number] = True
                except Exception:
                    results[number] = False  # others still proceed
        finally:
            await close_hs300(device)

        return results

    def power_off_outlets(self, requests) -> dict:
        """Command several outlets OFF over ONE connection.

        requests: [(outlet_number, expected_alias), ...] in shutdown order.
        Returns {outlet_number: True if the OFF command was sent}.
        """

        try:
            return asyncio.run(self._power_off_outlets_async(list(requests)))
        finally:
            self._last_command_end = self._clock()

    async def _get_outlet_states_async(self, requests) -> dict:
        states = {number: None for number, _alias in requests}

        try:
            device = await self._get_device()
        except KasaTransportError:
            return states

        try:
            for number, alias in requests:
                try:
                    outlet = await self._validated_child(
                        device, number, alias
                    )
                    states[number] = (
                        SafetyPowerState.ON
                        if outlet.is_on
                        else SafetyPowerState.OFF
                    )
                except Exception:
                    states[number] = None
        finally:
            await close_hs300(device)

        return states

    def get_outlet_states(self, requests) -> dict:
        """Read several outlets over ONE fresh connection (None = unknown).

        The first read after an OFF command waits until the verify gap has
        passed since that command's connection closed.
        """

        if self._last_command_end is not None:
            remaining = self._verify_gap_seconds - (
                self._clock() - self._last_command_end
            )
            self._last_command_end = None

            if remaining > 0:
                self._sleep(remaining)

        return asyncio.run(self._get_outlet_states_async(list(requests)))
