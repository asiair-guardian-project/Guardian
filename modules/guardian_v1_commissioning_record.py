"""Load the operator's signed-off commissioning record (fail closed).

Commissioning is a human decision. Nothing in Guardian writes this file; the
operator creates it deliberately after the eight checks have been completed.
Guardian only READS it, and any problem at all (missing, unreadable, wrong
shape, wrong configuration, unsafe file permissions) yields an EMPTY record,
which keeps ARM refused.

File format (JSON):
    {
      "schema": "guardian-commissioning-record-v1",
      "configuration_fingerprint": "<installation fingerprint, exactly>",
      "approved_by": "<name>",
      "approved_at": "<ISO date/time>",
      "results": {"ASIAIR_MONITORING": "VERIFIED", ... all eight checks ...}
    }
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from modules.commissioning import (
    CommissioningCheck,
    CommissioningResult,
    CommissioningStatus,
)

SCHEMA = "guardian-commissioning-record-v1"
MAX_BYTES = 65536


@dataclass(frozen=True)
class CommissioningLoad:
    status: CommissioningStatus
    reason: str
    approved_by: str | None = None
    approved_at: str | None = None

    @property
    def usable(self) -> bool:
        return self.status.commissioned


def _empty(reason: str) -> CommissioningLoad:
    return CommissioningLoad(CommissioningStatus(results={}), reason)


def load_commissioning_record(path, expected_fingerprint: str) -> CommissioningLoad:
    """Read the record. Never raises; problems return an empty status."""

    if path is None:
        return _empty("no commissioning record configured")

    try:
        record_path = Path(path)

        if record_path.is_symlink():
            return _empty("commissioning record is a symlink")

        info = os.lstat(record_path)

        if not stat.S_ISREG(info.st_mode):
            return _empty("commissioning record is not a regular file")

        if info.st_uid != os.getuid():
            return _empty("commissioning record is not owned by the current user")

        if info.st_mode & 0o022:
            return _empty("commissioning record is writable by others")

        if info.st_size > MAX_BYTES:
            return _empty("commissioning record is too large")

        data = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as error:
        return _empty(f"commissioning record unreadable: {type(error).__name__}")

    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        return _empty("commissioning record has the wrong schema")

    fingerprint = data.get("configuration_fingerprint")

    if not isinstance(fingerprint, str) or not fingerprint:
        return _empty("commissioning record has no configuration fingerprint")

    if fingerprint != expected_fingerprint:
        return _empty("commissioning record is for a different configuration")

    approved_by = data.get("approved_by")
    approved_at = data.get("approved_at")

    if not isinstance(approved_by, str) or not approved_by.strip():
        return _empty("commissioning record has no approver")

    if not isinstance(approved_at, str) or not approved_at.strip():
        return _empty("commissioning record has no approval time")

    raw_results = data.get("results")
    expected_names = {check.name for check in CommissioningCheck}

    if not isinstance(raw_results, dict) or set(raw_results) != expected_names:
        return _empty("commissioning record must list exactly the eight checks")

    results = {}

    for name, value in raw_results.items():
        try:
            results[CommissioningCheck[name]] = CommissioningResult[value]
        except (KeyError, TypeError):
            return _empty(f"commissioning record has an invalid result for {name}")

    status = CommissioningStatus(
        results=results,
        configuration_fingerprint=fingerprint,
    )

    if not status.commissioned:
        return CommissioningLoad(
            status, "commissioning record is incomplete: not every check is VERIFIED",
            approved_by, approved_at,
        )

    return CommissioningLoad(status, "commissioned", approved_by, approved_at)
