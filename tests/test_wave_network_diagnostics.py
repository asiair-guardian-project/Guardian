from unittest.mock import patch

from modules.wave_network import get_wave_network_diagnostics


def fake_run(command, **kwargs):
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    result = Result()

    if command[0] == "ipconfig":
        result.stdout = "192.168.4.2\n"

    elif command[0] == "route":
        result.stdout = (
            "route to: 192.168.4.1\n"
            "interface: en1\n"
        )

    elif command[0] == "ping":
        result.returncode = 0

    return result


with patch("modules.wave_network.subprocess.run", side_effect=fake_run):
    result = get_wave_network_diagnostics()

assert result["en1_ip"] == "192.168.4.2"
assert result["route_interface"] == "en1"
assert result["ping_ok"] is True

print("PASS: Wave network diagnostics")
