import hashlib
from pathlib import Path

import pytest
import yaml

from modules.guardian_v1_activation_transaction import (
    activate_offline, ActivationTransactionError,
)


def fixture(tmp_path):
    original = {
        "asiair": {"timeout_seconds": 3, "ip_address": "127.0.0.1"},
        "monitor": {"interval_seconds": 5},
    }
    # Use actual schema fixture from setup_config tests rather than a minimal invented config.
    return original


def test_requires_offline_authorization(tmp_path):
    with pytest.raises(ActivationTransactionError, match="Offline authorization"):
        activate_offline(tmp_path/"active", tmp_path/"candidate", tmp_path/"backup",
                         expected_active_sha256="x", expected_candidate_sha256="y",
                         offline_authorization="NO")


def test_rejects_missing_files(tmp_path):
    with pytest.raises(ActivationTransactionError, match="Backup preflight"):
        activate_offline(tmp_path/"active", tmp_path/"candidate", tmp_path/"backup",
                         expected_active_sha256="x", expected_candidate_sha256="y",
                         offline_authorization="OFFLINE_MONITOR_STOPPED")
