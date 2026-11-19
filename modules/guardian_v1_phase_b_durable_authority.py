"""Fail-closed, durable single-use authorization journal for isolated Phase B.

This module NEVER authorizes hardware by itself. A separately reviewed live
caller must establish physical preflight, process exclusivity and approval.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from modules.guardian_v1_commissioning_test_authority import TestAuthorizationError


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _write_new(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(record, f, sort_keys=True, indent=2)
            f.flush()
            os.fsync(f.fileno())
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        # Keep an incomplete record to fail closed; never free the test ID.
        raise


class DurableTestAuthorization:
    """Consume a scoped test ID once, across processes and restarts.

    Must be used with an isolated commissioning bridge, not production ARM.
    The journal is intentionally append-only by filename: results are stored
    separately so the consumed marker cannot be cleared by a result update.
    """
    def __init__(self, *, journal_dir, test_id, scope):
        if not test_id or not all(c.isalnum() or c in '-_' for c in test_id):
            raise ValueError('test_id must be nonempty and filesystem-safe')
        self.journal_dir = Path(journal_dir)
        self.test_id = test_id
        self.scope = scope
        self.marker = self.journal_dir / f'{test_id}.consumed.json'
        self.outcome = self.journal_dir / f'{test_id}.outcome.json'

    def consume(self, *, fingerprint, controller_id, roles):
        requested = frozenset(roles)
        record = {
            'event': 'PHASE_B_AUTHORIZATION_CONSUMED',
            'timestamp_utc': _utc(),
            'test_id': self.test_id,
            'requested': {'configuration_fingerprint': fingerprint,
                          'controller_id': controller_id,
                          'roles': sorted(requested)},
            'approved_scope': {'configuration_fingerprint': self.scope.configuration_fingerprint,
                               'controller_id': self.scope.controller_id,
                               'roles': sorted(self.scope.roles)},
            'commissioning_status': 'NOT_AUTHORIZED',
        }
        try:
            _write_new(self.marker, record)
        except FileExistsError as exc:
            raise TestAuthorizationError('test authorization already consumed') from exc
        if (fingerprint != self.scope.configuration_fingerprint or
                controller_id != self.scope.controller_id or
                requested != self.scope.roles):
            raise TestAuthorizationError('scope mismatch; authorization consumed')
        return True

    def record_outcome(self, *, status, details):
        if not self.marker.exists():
            raise TestAuthorizationError('cannot record result without consumed authorization')
        if status not in {'PASS', 'FAIL', 'EXCEPTION', 'UNKNOWN'}:
            raise ValueError('unsupported outcome')
        record = {'event': 'PHASE_B_TEST_OUTCOME', 'timestamp_utc': _utc(),
                  'test_id': self.test_id, 'status': status,
                  'details': details, 'commissioning_status': 'NOT_AUTHORIZED'}
        try:
            _write_new(self.outcome, record)
        except FileExistsError as exc:
            raise TestAuthorizationError('outcome already recorded') from exc
        return self.outcome
