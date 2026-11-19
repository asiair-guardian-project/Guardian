import datetime
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "guardian.log"


def _cleanup_old_logs(keep_days=7):
    """Remove archived Guardian logs older than the retention period."""

    today = datetime.datetime.now().date()
    cutoff = today - datetime.timedelta(days=keep_days)

    for archive in LOG_DIR.glob("guardian.log.*"):
        try:
            archive_date = datetime.date.fromisoformat(
                archive.name.removeprefix("guardian.log.")
            )
        except ValueError:
            continue

        if archive_date < cutoff:
            archive.unlink()


def _rotate_if_needed():
    """Archive the active log when it belongs to a previous day."""

    if not LOG_FILE.exists() or LOG_FILE.stat().st_size == 0:
        return

    with open(LOG_FILE, "r", encoding="utf-8") as file:
        first_line = file.readline()

    try:
        log_date = datetime.date.fromisoformat(first_line[:10])
    except ValueError:
        return

    today = datetime.datetime.now().date()

    if log_date >= today:
        return

    archive = LOG_DIR / f"guardian.log.{log_date.isoformat()}"

    if archive.exists():
        with open(archive, "a", encoding="utf-8") as destination:
            destination.write(LOG_FILE.read_text(encoding="utf-8"))
        LOG_FILE.unlink()
    else:
        LOG_FILE.rename(archive)

    _cleanup_old_logs(keep_days=7)


def _write(level, message):
    """Write one formatted event to the Guardian log."""

    LOG_DIR.mkdir(exist_ok=True)
    _rotate_if_needed()

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"{timestamp} [{level:<8}] {message}"

    with open(LOG_FILE, "a", encoding="utf-8") as file:
        file.write(formatted_message + "\n")

    print(formatted_message)


def info(message):
    _write("INFO", message)


def warning(message):
    _write("WARNING", message)


def error(message):
    _write("ERROR", message)


def action(message):
    _write("ACTION", message)


def critical(message):
    _write("CRITICAL", message)