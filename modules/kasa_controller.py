import asyncio
import os
import subprocess

from modules.kasa_hs300_connection import (
    close_hs300,
    connect_hs300,
)


class KasaControllerError(Exception):
    """Raised when Kasa communication or configuration fails."""


class KasaSafetyError(KasaControllerError):
    """Raised when an operation targets a protected outlet."""


class KasaController:
    """Safe interface to the observatory HS300 power strip."""

    PROTECTED_OUTLETS = {
        "Mac Mini",
    }

    PROTECTED_OUTLET_NUMBERS = {
        1,
    }

    def __init__(self, host):
        self.host = host

    def _require_hardware_switching_allowed(self):
        """
        Refuse physical Kasa switching during automated tests unless
        live-hardware execution has been deliberately authorized.

        Read-only Kasa operations are unaffected.
        """

        if (
            os.environ.get("PYTEST_CURRENT_TEST")
            and os.environ.get(
                "GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS"
            ) != "YES_I_UNDERSTAND"
        ):
            raise KasaSafetyError(
                "Kasa hardware switching is blocked during automated tests. "
                "Set GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS=YES_I_UNDERSTAND "
                "only for deliberate live-hardware testing."
            )

    def _credentials(self):
        username = os.environ.get("KASA_USERNAME")
        password = os.environ.get("KASA_PASSWORD")

        if username and password:
            return username, password

        try:
            username = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a", "guardian",
                    "-s", "Guardian Kasa Username",
                    "-w",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            password = subprocess.run(
                [
                    "security",
                    "find-generic-password",
                    "-a", "guardian",
                    "-s", "Guardian Kasa Password",
                    "-w",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

        except (subprocess.CalledProcessError, OSError) as error:
            raise KasaControllerError(
                "Kasa credentials are not available from "
                "the environment or macOS Keychain."
            ) from error

        if not username or not password:
            raise KasaControllerError(
                "Kasa credentials retrieved from macOS Keychain "
                "are incomplete."
            )

        return username, password

    async def _get_strip(self):
        username, password = self._credentials()

        last_error = None

        for attempt in range(1, 4):
            try:
                return await connect_hs300(
                    self.host,
                    username,
                    password,
                )

            except Exception as error:
                last_error = error

                if attempt < 3:
                    await asyncio.sleep(5)

        raise KasaControllerError(
            "Unable to establish a verified connection to "
            f"Kasa strip {self.host} after 3 attempts: {last_error}"
        ) from last_error

    async def _close_strip(self, strip):
        """Close resources owned by a Kasa strip connection."""

        await close_hs300(strip)

    async def get_outlets(self):
        """
        Return the current HS300 outlet names and states.

        Read-only. No outlet switching occurs.
        """

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children:
                raise KasaControllerError(
                    "Kasa device does not expose individual outlets."
                )

            result = []

            for number, outlet in enumerate(children, start=1):
                await outlet.update()

                result.append(
                    {
                        "number": number,
                        "name": outlet.alias,
                        "is_on": outlet.is_on,
                        "protected": (
                            outlet.alias in self.PROTECTED_OUTLETS
                        ),
                    }
                )

            return result

        finally:
            await self._close_strip(strip)

    async def _find_outlet(self, name):
        """
        Return strip, outlet number, and child object matching an alias.

        The caller owns the returned strip connection and must close it.
        On lookup failure, this method closes the connection itself.
        """

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children:
                raise KasaControllerError(
                    "Kasa device does not expose individual outlets."
                )

            matches = []

            for number, outlet in enumerate(children, start=1):
                await outlet.update()

                if outlet.alias == name:
                    matches.append((number, outlet))

            if not matches:
                raise KasaControllerError(
                    f"Kasa outlet not found: {name}"
                )

            if len(matches) > 1:
                raise KasaControllerError(
                    f"Multiple Kasa outlets have alias: {name}"
                )

            number, outlet = matches[0]
            return strip, number, outlet

        except Exception:
            await self._close_strip(strip)
            raise

    def _check_outlet_safety(self, number, name):
        """Reject any attempt to switch a protected outlet."""

        if (
            number in self.PROTECTED_OUTLET_NUMBERS
            or name in self.PROTECTED_OUTLETS
        ):
            raise KasaSafetyError(
                f"Refusing to switch protected outlet "
                f"{number}: {name}"
            )

    async def set_outlet_power(self, name, turn_on):
        """
        Set one HS300 outlet ON or OFF and verify the result.

        Protected outlets are rejected before a switching
        command is sent.
        """

        strip, number, outlet = await self._find_outlet(name)

        try:
            self._check_outlet_safety(
                number=number,
                name=outlet.alias,
            )

            outlet_alias = outlet.alias

            try:
                if turn_on:
                    self._require_hardware_switching_allowed()
                    await outlet.turn_on()
                else:
                    self._require_hardware_switching_allowed()
                    await outlet.turn_off()

            except KasaSafetyError:
                raise

            except Exception as error:
                raise KasaControllerError(
                    f"Unable to switch outlet {number} "
                    f"({outlet_alias}): {error}"
                ) from error

        finally:
            await self._close_strip(strip)

        expected_state = bool(turn_on)

        for _ in range(3):
            await asyncio.sleep(1)

            verify_strip, verify_number, verify_outlet = (
                await self._find_outlet(outlet_alias)
            )

            try:
                if verify_outlet.is_on == expected_state:
                    return {
                        "number": verify_number,
                        "name": verify_outlet.alias,
                        "is_on": verify_outlet.is_on,
                    }
            finally:
                await self._close_strip(verify_strip)

        raise KasaControllerError(
            f"Outlet {number} ({outlet_alias}) "
            f"did not reach the requested state."
        )

    async def _power_off_from_strip(
        self,
        strip,
        number,
        expected_alias,
    ):
        """
        Power off one validated HS300 outlet using an existing strip session.

        This method sends the OFF command only. Final state verification
        must be performed using a fresh HS300 discovery.
        """

        children = getattr(strip, "children", None)

        if not children or len(children) < number:
            raise KasaSafetyError(
                f"{expected_alias} emergency power target is unavailable."
            )

        outlet = children[number - 1]

        await outlet.update()

        if outlet.alias != expected_alias:
            raise KasaSafetyError(
                f"{expected_alias} emergency power target "
                f"failed safety validation."
            )

        try:
            self._require_hardware_switching_allowed()
            await outlet.turn_off()

        except KasaSafetyError:
            raise

        except Exception as error:
            raise KasaControllerError(
                f"Unable to power off {expected_alias}: {error}"
            ) from error

        return {
            "number": number,
            "name": outlet.alias,
            "command_sent": True,
        }

    async def _verify_outlets_off(
        self,
        expected_outlets,
    ):
        """
        Verify requested outlets OFF using one fresh HS300 connection.

        expected_outlets must contain:
        [(physical_number, expected_alias), ...]
        """

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children:
                raise KasaControllerError(
                    "Kasa device does not expose individual outlets."
                )

            results = {}

            for number, expected_alias in expected_outlets:
                if len(children) < number:
                    raise KasaSafetyError(
                        f"{expected_alias} verification target "
                        f"is unavailable."
                    )

                outlet = children[number - 1]

                if outlet.alias != expected_alias:
                    raise KasaSafetyError(
                        f"{expected_alias} verification target failed "
                        f"safety validation."
                    )

                results[expected_alias] = {
                    "number": number,
                    "name": outlet.alias,
                    "is_on": outlet.is_on,
                    "verified_off": not outlet.is_on,
                }

            return results

        finally:
            await self._close_strip(strip)

    async def _power_on_from_strip(
        self,
        strip,
        number,
        expected_alias,
    ):
        """
        Power on one validated HS300 outlet using an existing strip session.

        This method sends the ON command only. Final state verification
        must be performed using a fresh HS300 discovery.
        """

        children = getattr(strip, "children", None)

        if not children or len(children) < number:
            raise KasaSafetyError(
                f"{expected_alias} startup power target is unavailable."
            )

        outlet = children[number - 1]

        await outlet.update()

        if outlet.alias != expected_alias:
            raise KasaSafetyError(
                f"{expected_alias} startup power target "
                f"failed safety validation."
            )

        try:
            self._require_hardware_switching_allowed()
            await outlet.turn_on()

        except KasaSafetyError:
            raise

        except Exception as error:
            raise KasaControllerError(
                f"Unable to power on {expected_alias}: {error}"
            ) from error

        return {
            "number": number,
            "name": outlet.alias,
            "command_sent": True,
        }

    async def _verify_outlets_on(
        self,
        expected_outlets,
    ):
        """
        Verify requested outlets ON using one fresh HS300 connection.

        expected_outlets must contain:
        [(physical_number, expected_alias), ...]
        """

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children:
                raise KasaControllerError(
                    "Kasa device does not expose individual outlets."
                )

            results = {}

            for number, expected_alias in expected_outlets:
                if len(children) < number:
                    raise KasaSafetyError(
                        f"{expected_alias} verification target "
                        f"is unavailable."
                    )

                outlet = children[number - 1]

                if outlet.alias != expected_alias:
                    raise KasaSafetyError(
                        f"{expected_alias} verification target failed "
                        f"safety validation."
                    )

                results[expected_alias] = {
                    "number": number,
                    "name": outlet.alias,
                    "is_on": outlet.is_on,
                    "verified_on": outlet.is_on,
                }

            return results

        finally:
            await self._close_strip(strip)

    async def power_off_emergency_targets(self, targets):
        """
        Power off selected observatory devices using one HS300 session,
        then verify their final states using one fresh discovery.

        Valid target names:
        WAVE
        PEGASUS
        ASIAIR
        """

        target_map = {
            "WAVE": (3, "Wave 150i"),
            "PEGASUS": (4, "Pegasus"),
            "ASIAIR": (2, "ASIAIR"),
        }

        if not targets:
            return {}

        requested = []

        for target in targets:
            if target not in target_map:
                raise KasaSafetyError(
                    f"Unknown emergency power target: {target}"
                )

            requested.append(target_map[target])

        # One authenticated connection for the entire command phase.
        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children:
                raise KasaControllerError(
                    "Kasa device does not expose individual outlets."
                )

            # Validate every target before switching anything.
            for number, expected_alias in requested:
                if len(children) < number:
                    raise KasaSafetyError(
                        f"{expected_alias} emergency power target "
                        f"is unavailable."
                    )

                outlet = children[number - 1]

                if outlet.alias != expected_alias:
                    raise KasaSafetyError(
                        f"{expected_alias} emergency power target "
                        f"failed safety validation."
                    )

            command_results = {}

            # Send all requested OFF commands using the same connection.
            for number, expected_alias in requested:
                try:
                    command_results[expected_alias] = (
                        await self._power_off_from_strip(
                            strip,
                            number,
                            expected_alias,
                        )
                    )

                except KasaSafetyError:
                    raise

                except KasaControllerError as error:
                    command_results[expected_alias] = {
                        "number": number,
                        "name": expected_alias,
                        "command_sent": False,
                        "error": str(error),
                    }

        finally:
            await self._close_strip(strip)

        # Allow the HS300 time before a fresh authenticated
        # connection is opened for final verification.
        await asyncio.sleep(5)

        # One fresh discovery verifies the final physical states.
        verification_results = await self._verify_outlets_off(
            requested
        )

        return {
            "commands": command_results,
            "verification": verification_results,
        }

    async def power_on_imaging_targets(self):
        """
        Power on the normal imaging equipment using one HS300 session,
        then verify final states using one fresh discovery.

        Startup order:
        PEGASUS
        WAVE
        ASIAIR
        """

        requested = [
            (4, "Pegasus"),
            (3, "Wave 150i"),
            (2, "ASIAIR"),
        ]

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children:
                raise KasaControllerError(
                    "Kasa device does not expose individual outlets."
                )

            # Validate every target before switching anything.
            for number, expected_alias in requested:
                if len(children) < number:
                    raise KasaSafetyError(
                        f"{expected_alias} startup power target "
                        f"is unavailable."
                    )

                outlet = children[number - 1]

                if outlet.alias != expected_alias:
                    raise KasaSafetyError(
                        f"{expected_alias} startup power target "
                        f"failed safety validation."
                    )

            command_results = {}

            # Send all ON commands using the same connection.
            for number, expected_alias in requested:
                try:
                    command_results[expected_alias] = (
                        await self._power_on_from_strip(
                            strip,
                            number,
                            expected_alias,
                        )
                    )

                except KasaSafetyError:
                    raise

                except KasaControllerError as error:
                    command_results[expected_alias] = {
                        "number": number,
                        "name": expected_alias,
                        "command_sent": False,
                        "error": str(error),
                    }

        finally:
            await self._close_strip(strip)

        verification_results = await self._verify_outlets_on(
            requested
        )

        return {
            "commands": command_results,
            "verification": verification_results,
        }

    async def power_off_wave(self):
        """
        Emergency power-off for the Wave 150i.

        Validates physical outlet number and alias, sends OFF using one
        HS300 session, closes it, then verifies using a fresh session.
        """

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children or len(children) < 3:
                raise KasaSafetyError(
                    "Wave emergency power target is unavailable."
                )

            number = 3
            outlet = children[number - 1]

            await outlet.update()

            if outlet.alias != "Wave 150i":
                raise KasaSafetyError(
                    "Wave emergency power target failed safety validation."
                )

            try:
                self._require_hardware_switching_allowed()
                await outlet.turn_off()

            except KasaSafetyError:
                raise

            except Exception as error:
                raise KasaControllerError(
                    f"Unable to power off Wave 150i: {error}"
                ) from error

        finally:
            await self._close_strip(strip)

        await asyncio.sleep(1)

        verify_strip, verify_number, verify_outlet = (
            await self._find_outlet("Wave 150i")
        )

        try:
            if (
                verify_number != 3
                or verify_outlet.alias != "Wave 150i"
            ):
                raise KasaSafetyError(
                    "Wave emergency power target failed "
                    "verification safety validation."
                )

            if verify_outlet.is_on:
                raise KasaControllerError(
                    "Wave 150i power-off could not be verified."
                )

            return {
                "number": verify_number,
                "name": verify_outlet.alias,
                "is_on": False,
            }

        finally:
            await self._close_strip(verify_strip)

    async def power_off_asiair(self):
        """
        Emergency power-off for the ASIAIR.

        Validates physical outlet number and alias, sends OFF using one
        HS300 session, closes it, then verifies using a fresh session.
        """

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children or len(children) < 2:
                raise KasaSafetyError(
                    "ASIAIR emergency power target is unavailable."
                )

            number = 2
            outlet = children[number - 1]

            await outlet.update()

            if outlet.alias != "ASIAIR":
                raise KasaSafetyError(
                    "ASIAIR emergency power target failed safety validation."
                )

            try:
                self._require_hardware_switching_allowed()
                await outlet.turn_off()

            except KasaSafetyError:
                raise

            except Exception as error:
                raise KasaControllerError(
                    f"Unable to power off ASIAIR: {error}"
                ) from error

        finally:
            await self._close_strip(strip)

        await asyncio.sleep(1)

        verify_strip, verify_number, verify_outlet = (
            await self._find_outlet("ASIAIR")
        )

        try:
            if (
                verify_number != 2
                or verify_outlet.alias != "ASIAIR"
            ):
                raise KasaSafetyError(
                    "ASIAIR emergency power target failed "
                    "verification safety validation."
                )

            if verify_outlet.is_on:
                raise KasaControllerError(
                    "ASIAIR power-off could not be verified."
                )

            return {
                "number": verify_number,
                "name": verify_outlet.alias,
                "is_on": False,
            }

        finally:
            await self._close_strip(verify_strip)

    async def power_off_pegasus(self):
        """
        Emergency power-off for the Pegasus Powerbox Micro.

        Validates physical outlet number and alias, sends OFF using one
        HS300 session, closes it, then verifies using a fresh session.
        """

        strip = await self._get_strip()

        try:
            children = getattr(strip, "children", None)

            if not children or len(children) < 4:
                raise KasaSafetyError(
                    "Pegasus emergency power target is unavailable."
                )

            number = 4
            outlet = children[number - 1]

            await outlet.update()

            if outlet.alias != "Pegasus":
                raise KasaSafetyError(
                    "Pegasus emergency power target failed safety validation."
                )

            try:
                self._require_hardware_switching_allowed()
                await outlet.turn_off()

            except KasaSafetyError:
                raise

            except Exception as error:
                raise KasaControllerError(
                    f"Unable to power off Pegasus: {error}"
                ) from error

        finally:
            await self._close_strip(strip)

        await asyncio.sleep(1)

        verify_strip, verify_number, verify_outlet = (
            await self._find_outlet("Pegasus")
        )

        try:
            if (
                verify_number != 4
                or verify_outlet.alias != "Pegasus"
            ):
                raise KasaSafetyError(
                    "Pegasus emergency power target failed "
                    "verification safety validation."
                )

            if verify_outlet.is_on:
                raise KasaControllerError(
                    "Pegasus power-off could not be verified."
                )

            return {
                "number": verify_number,
                "name": verify_outlet.alias,
                "is_on": False,
            }

        finally:
            await self._close_strip(verify_strip)

