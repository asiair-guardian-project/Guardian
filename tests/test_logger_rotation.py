import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from modules import logger


with tempfile.TemporaryDirectory() as tmp:
    log_dir = Path(tmp)
    log_file = log_dir / "guardian.log"

    logger.LOG_DIR = log_dir
    logger.LOG_FILE = log_file

    # Simulate eight archived daily logs.
    today = datetime.now().date()
    for days_ago in range(1, 9):
        day = today - timedelta(days=days_ago)
        archive = log_dir / f"guardian.log.{day.isoformat()}"
        archive.write_text(f"test log for {day}\n", encoding="utf-8")

    logger._cleanup_old_logs(keep_days=7)

    archives = sorted(log_dir.glob("guardian.log.*"))

    assert len(archives) == 7, f"Expected 7 archives, found {len(archives)}"

    oldest_kept = today - timedelta(days=7)
    assert (log_dir / f"guardian.log.{oldest_kept.isoformat()}").exists()

    removed = today - timedelta(days=8)
    assert not (log_dir / f"guardian.log.{removed.isoformat()}").exists()

    print("Logger rotation cleanup test PASS")

with tempfile.TemporaryDirectory() as tmp:
    log_dir = Path(tmp)
    log_file = log_dir / "guardian.log"

    logger.LOG_DIR = log_dir
    logger.LOG_FILE = log_file

    yesterday = datetime.now().date() - timedelta(days=1)
    log_file.write_text(
        f"{yesterday.isoformat()} 23:59:00 [INFO    ] previous day\n",
        encoding="utf-8",
    )

    logger._rotate_if_needed()

    archive = log_dir / f"guardian.log.{yesterday.isoformat()}"

    assert archive.exists(), "Previous day's log was not archived"
    assert not log_file.exists(), "Active log should be recreated on next write"

    print("Logger daily rotation test PASS")
