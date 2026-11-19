import subprocess


class KeychainError(Exception):
    """Raised when a Guardian secret cannot be read from macOS Keychain."""


def get_secret(account, service):
    """
    Read one secret from macOS Keychain.
    """

    try:
        value = subprocess.run(
            [
                "security",
                "find-generic-password",
                "-a", account,
                "-s", service,
                "-w",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    except (subprocess.CalledProcessError, OSError) as error:
        raise KeychainError(
            f"Unable to read Keychain item: {service}"
        ) from error

    if not value:
        raise KeychainError(
            f"Keychain item is empty: {service}"
        )

    return value