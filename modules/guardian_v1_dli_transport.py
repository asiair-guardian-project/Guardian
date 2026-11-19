"""Digital Loggers (REST-API models) transport for the Guardian safety-power adapter.

UNTESTED ON REAL HARDWARE. Written from the published REST API reference and checked only against a simulated
controller (tests/dli_fake.py). Every reply that is not exactly what the reference describes is treated as "unknown",
which never counts as a verified cut. Run guardian_v1_dli_probe.py (read-only) before relying on this.

Same interface as PythonKasaTransport, so it plugs into KasaSafetyPowerAdapter unchanged:
  check_outlet / get_outlet_state / power_off_outlet, and the batch calls power_off_outlets / get_outlet_states
  that use ONE connection.

Outlet numbers here are the numbers printed on the unit (1-8). The REST API counts from 0, so number N is index N-1.
Before every power-off the controller's own name for that outlet must equal the configured name; otherwise that outlet
is refused. State is read from `physical_state` (the relay itself), not from the commanded state.

Protocol facts used (Digital Loggers REST API, firmware 1.7+):
  GET  /restapi/relay/outlets/=N/name/            -> JSON list with the outlet name
  GET  /restapi/relay/outlets/=N/physical_state/  -> JSON list with true/false
  PUT  /restapi/relay/outlets/=N/state/  form value=false   (needs header X-CSRF: x)
  HTTP Digest authentication; credentials are never stored in the configuration.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import secrets
import subprocess
import urllib.parse

from modules.guardian_types import SafetyPowerState
from modules.kasa_safety_power_adapter import KasaTransportError

MAX_OUTLETS = 8
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class DliTransportError(KasaTransportError):
    pass


def dli_credentials():
    """Environment first (DLI_USERNAME / DLI_PASSWORD), then the macOS Keychain, like the Kasa credentials."""
    username, password = os.environ.get("DLI_USERNAME"), os.environ.get("DLI_PASSWORD")
    if username and password:
        return username, password
    try:
        def fetch(service):
            return subprocess.run(
                ["security", "find-generic-password", "-a", "guardian", "-s", service, "-w"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
        username, password = fetch("Guardian Digital Loggers Username"), fetch("Guardian Digital Loggers Password")
    except (subprocess.CalledProcessError, OSError) as error:
        raise DliTransportError(
            "Digital Loggers credentials are not available from the environment or macOS Keychain."
        ) from error
    if not username or not password:
        raise DliTransportError("Digital Loggers credentials retrieved from macOS Keychain are incomplete.")
    return username, password


class DigestConnection:
    """One keep-alive HTTP connection with RFC 7616 Digest authentication (MD5 and SHA-256, qop=auth)."""

    def __init__(self, host, port, scheme, username, password, timeout):
        self._host, self._port, self._scheme = host, port, scheme
        self._username, self._password, self._timeout = username, password, timeout
        self._conn = None
        self._challenge = None
        self._nc = 0

    def _connect(self):
        cls = http.client.HTTPSConnection if self._scheme == "https" else http.client.HTTPConnection
        self._conn = cls(self._host, self._port, timeout=self._timeout)

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None

    @staticmethod
    def _parse_challenge(header):
        if not header or not header.lower().startswith("digest "):
            return None
        fields = {k: q or u for k, q, u in re.findall(r'(\w+)=(?:"([^"]*)"|([^,\s]*))', header[7:])}
        return fields if "nonce" in fields and "realm" in fields else None

    def _authorization(self, method, uri):
        ch = self._challenge
        algorithm = ch.get("algorithm", "MD5").upper()
        if algorithm in ("MD5", "MD5-SESS"):
            h = lambda s: hashlib.md5(s.encode()).hexdigest()
        elif algorithm == "SHA-256":
            h = lambda s: hashlib.sha256(s.encode()).hexdigest()
        else:
            raise DliTransportError(f"unsupported Digest algorithm {algorithm}")
        qops = [q.strip() for q in ch.get("qop", "").split(",") if q.strip()]
        self._nc += 1
        nc, cnonce = f"{self._nc:08x}", secrets.token_hex(8)
        ha1 = h(f"{self._username}:{ch['realm']}:{self._password}")
        if algorithm == "MD5-SESS":
            ha1 = h(f"{ha1}:{ch['nonce']}:{cnonce}")
        ha2 = h(f"{method}:{uri}")
        if "auth" in qops:
            response = h(f"{ha1}:{ch['nonce']}:{nc}:{cnonce}:auth:{ha2}")
        elif not qops:
            response = h(f"{ha1}:{ch['nonce']}:{ha2}")
        else:
            raise DliTransportError("unsupported Digest qop")
        parts = [f'username="{self._username}"', f'realm="{ch["realm"]}"', f'nonce="{ch["nonce"]}"',
                 f'uri="{uri}"', f'response="{response}"', f"algorithm={algorithm}"]
        if "auth" in qops:
            parts += ["qop=auth", f"nc={nc}", f'cnonce="{cnonce}"']
        if ch.get("opaque"):
            parts.append(f'opaque="{ch["opaque"]}"')
        return "Digest " + ", ".join(parts)

    def _once(self, method, path, body, headers):
        if self._conn is None:
            self._connect()
        h = dict(headers)
        if self._challenge:
            h["Authorization"] = self._authorization(method, path)
        self._conn.request(method, path, body=body, headers=h)
        resp = self._conn.getresponse()
        return resp.status, resp.getheader("WWW-Authenticate"), resp.read()

    def request(self, method, path, form=None):
        headers = {"Accept": "application/json", "X-CSRF": "x"}
        body = None
        if form is not None:
            body = urllib.parse.urlencode(form)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            status, www, data = self._once(method, path, body, headers)
            if status == 401:
                challenge = self._parse_challenge(www)
                if challenge is None:
                    raise DliTransportError("the controller refused the request and offered no Digest sign-in")
                self._challenge = challenge
                status, www, data = self._once(method, path, body, headers)
                if status == 401:
                    raise DliTransportError("the controller rejected the user name or password")
        except DliTransportError:
            self.close()
            raise
        except (OSError, http.client.HTTPException) as error:
            self.close()
            raise DliTransportError(f"unable to communicate with the controller: {error}") from error
        return status, data


def _first(data):
    """The REST API answers selector requests with a JSON list; accept exactly one element."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise DliTransportError("the controller's reply was not JSON") from error
    if isinstance(value, list):
        if len(value) != 1:
            raise DliTransportError("the controller's reply did not hold exactly one value")
        value = value[0]
    return value


class DigitalLoggersTransport:
    def __init__(self, *, host, username, password, port=None, scheme="http", timeout_seconds=5, connect=None):
        if not str(host).strip():
            raise ValueError("host must not be empty")
        if not username or not password:
            raise ValueError("username and password must not be empty")
        if scheme not in ("http", "https"):
            raise ValueError("scheme must be http or https")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._host = str(host).strip()
        self._port = port if port is not None else (443 if scheme == "https" else 80)
        self._scheme = scheme
        self._username, self._password, self._timeout = username, password, timeout_seconds
        self._connect = connect or DigestConnection
        self._open = None

    # -- connection ---------------------------------------------------------
    def _session(self):
        if self._open is None:
            self._open = self._connect(self._host, self._port, self._scheme,
                                       self._username, self._password, self._timeout)
        return self._open

    def close(self):
        if self._open is not None:
            try:
                self._open.close()
            finally:
                self._open = None

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _index(outlet_number):
        if isinstance(outlet_number, bool) or not isinstance(outlet_number, int) \
                or not 1 <= outlet_number <= MAX_OUTLETS:
            raise DliTransportError(f"outlet {outlet_number} is outside 1-{MAX_OUTLETS}")
        return outlet_number - 1

    def _get(self, session, index, leaf):
        status, data = session.request("GET", f"/restapi/relay/outlets/={index}/{leaf}/")
        if status != 200:
            raise DliTransportError(f"outlet {index + 1} {leaf}: the controller answered {status}")
        return _first(data)

    def _validated(self, session, outlet_number, expected_alias):
        index = self._index(outlet_number)
        name = self._get(session, index, "name")
        if not isinstance(name, str) or name != expected_alias:
            raise DliTransportError(
                f"outlet {outlet_number} identity mismatch: expected {expected_alias!r}, found {name!r}")
        return index

    def _state(self, session, index):
        value = self._get(session, index, "physical_state")
        if value is True:
            return SafetyPowerState.ON
        if value is False:
            return SafetyPowerState.OFF
        raise DliTransportError("the controller gave an unrecognised outlet state")

    def _refuse_switching_in_tests(self):
        if (os.environ.get("PYTEST_CURRENT_TEST") and self._host not in _LOOPBACK
                and os.environ.get("GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS") != "YES_I_UNDERSTAND"):
            raise DliTransportError("Digital Loggers switching is blocked during automated tests against a "
                                    "real address. Set GUARDIAN_ALLOW_LIVE_HARDWARE_TESTS=YES_I_UNDERSTAND "
                                    "only for deliberate live-hardware testing.")

    def _switch_off(self, session, index):
        status, _ = session.request("PUT", f"/restapi/relay/outlets/={index}/state/", form={"value": "false"})
        if status not in (200, 204):
            raise DliTransportError(f"outlet {index + 1}: the controller answered {status} to the OFF command")

    # -- single-outlet interface (one connection each) ----------------------
    def check_outlet(self, outlet_number, expected_alias):
        try:
            self._validated(self._session(), outlet_number, expected_alias)
            return True
        finally:
            self.close()

    def get_outlet_state(self, outlet_number, expected_alias):
        try:
            session = self._session()
            index = self._validated(session, outlet_number, expected_alias)
            return self._state(session, index)
        finally:
            self.close()

    def power_off_outlet(self, outlet_number, expected_alias):
        self._refuse_switching_in_tests()
        try:
            session = self._session()
            index = self._validated(session, outlet_number, expected_alias)
            self._switch_off(session, index)
            return True
        finally:
            self.close()

    def power_on_outlet_for_test(self, number, expected_alias):
        """ONLY for guardian_v1_outlet_test (restoring the empty spare test outlet). Guardian never switches ON."""
        self._refuse_switching_in_tests()
        try:
            session = self._session()
            index = self._validated(session, number, expected_alias)
            status, _ = session.request("PUT", f"/restapi/relay/outlets/={index}/state/", form={"value": "true"})
            if status not in (200, 204):
                raise DliTransportError(f"outlet {number}: the controller answered {status} to the ON command")
            return True
        finally:
            self.close()

    # -- batch interface (ONE connection) -----------------------------------
    def power_off_outlets(self, requests):
        requests = list(requests)
        results = {number: False for number, _ in requests}
        self._refuse_switching_in_tests()
        try:
            session = self._session()
            for number, alias in requests:
                try:
                    index = self._validated(session, number, alias)
                    self._switch_off(session, index)
                    results[number] = True
                except Exception:
                    results[number] = False        # the others still proceed
        finally:
            self.close()
        return results

    def get_outlet_states(self, requests):
        requests = list(requests)
        states = {number: None for number, _ in requests}
        try:
            session = self._session()
            for number, alias in requests:
                try:
                    index = self._validated(session, number, alias)
                    states[number] = self._state(session, index)
                except Exception:
                    states[number] = None
        finally:
            self.close()
        return states

    # -- read-only survey (used by guardian_v1_dli_probe.py; sends no PUT) ---
    def survey(self, count=MAX_OUTLETS):
        """[(number, name or None, state or None, problem or None)] for outlets 1..count over one connection."""
        rows = []
        try:
            session = self._session()
            for number in range(1, count + 1):
                index = self._index(number)
                try:
                    name = self._get(session, index, "name")
                    if not isinstance(name, str):
                        raise DliTransportError("the outlet name was not text")
                except Exception as error:
                    rows.append((number, None, None, str(error)))
                    continue
                try:
                    rows.append((number, name, self._state(session, index), None))
                except Exception as error:
                    rows.append((number, name, None, str(error)))
        finally:
            self.close()
        return rows
