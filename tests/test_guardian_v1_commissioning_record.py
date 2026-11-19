"""The commissioning record loader fails closed. No hardware, no network."""
import json
import os

import pytest

from modules.commissioning import CommissioningCheck
from modules.guardian_v1_commissioning_record import (
    SCHEMA,
    load_commissioning_record,
)

FP = "a" * 64


def good_record(**changes):
    record = {
        "schema": SCHEMA,
        "configuration_fingerprint": FP,
        "approved_by": "Operator",
        "approved_at": "2026-11-02T12:00:00Z",
        "results": {check.name: "VERIFIED" for check in CommissioningCheck},
    }
    record.update(changes)
    return record


def write(tmp_path, record, mode=0o600, name="record.json"):
    path = tmp_path / name
    path.write_text(record if isinstance(record, str) else json.dumps(record))
    path.chmod(mode)
    return path


def test_a_complete_matching_record_commissions_the_configuration(tmp_path):
    load = load_commissioning_record(write(tmp_path, good_record()), FP)
    assert load.usable
    assert load.reason == "commissioned"
    assert load.approved_by == "Operator"
    assert load.status.valid_for_configuration(FP)


@pytest.mark.parametrize("make", [
    lambda tmp: None,                                              # no path configured
    lambda tmp: tmp / "does-not-exist.json",
    lambda tmp: write(tmp, "{ not json"),
    lambda tmp: write(tmp, good_record(schema="something-else")),
    lambda tmp: write(tmp, good_record(configuration_fingerprint="b" * 64)),
    lambda tmp: write(tmp, good_record(configuration_fingerprint="")),
    lambda tmp: write(tmp, good_record(approved_by="")),
    lambda tmp: write(tmp, good_record(approved_by=None)),
    lambda tmp: write(tmp, good_record(approved_at=" ")),
    lambda tmp: write(tmp, good_record(results={})),
    lambda tmp: write(tmp, good_record(results={"ASIAIR_MONITORING": "VERIFIED"})),
    lambda tmp: write(tmp, good_record(results={
        **{c.name: "VERIFIED" for c in CommissioningCheck}, "EXTRA_CHECK": "VERIFIED"})),
    lambda tmp: write(tmp, good_record(results={
        **{c.name: "VERIFIED" for c in CommissioningCheck}, "ASIAIR_MONITORING": "MAYBE"})),
    lambda tmp: write(tmp, good_record(results=[1, 2, 3])),
    lambda tmp: write(tmp, good_record(), mode=0o666),            # writable by others
    lambda tmp: write(tmp, good_record(), mode=0o620),            # group-writable
    lambda tmp: write(tmp, "[]"),
    lambda tmp: write(tmp, "x" * 70000),                          # oversized
])
def test_every_problem_leaves_an_empty_unusable_record(tmp_path, make):
    load = load_commissioning_record(make(tmp_path), FP)
    assert not load.usable
    assert dict(load.status.results) == {}
    assert not load.status.valid_for_configuration(FP)


def test_a_directory_is_not_a_record(tmp_path):
    load = load_commissioning_record(tmp_path, FP)
    assert not load.usable


def test_a_symlink_is_refused_even_if_it_points_at_a_good_record(tmp_path):
    real = write(tmp_path, good_record())
    link = tmp_path / "link.json"
    link.symlink_to(real)
    load = load_commissioning_record(link, FP)
    assert not load.usable
    assert "symlink" in load.reason


def test_one_check_not_verified_means_not_commissioned(tmp_path):
    results = {c.name: "VERIFIED" for c in CommissioningCheck}
    results["MOUNT_SAFETY_POWER"] = "NOT_TESTED"
    load = load_commissioning_record(write(tmp_path, good_record(results=results)), FP)
    assert not load.usable
    assert "incomplete" in load.reason
    assert not load.status.valid_for_configuration(FP)


def test_failed_check_means_not_commissioned(tmp_path):
    results = {c.name: "VERIFIED" for c in CommissioningCheck}
    results["PROTECTION_LOGIC"] = "FAILED"
    load = load_commissioning_record(write(tmp_path, good_record(results=results)), FP)
    assert not load.usable


def test_read_only_group_and_world_permissions_are_allowed(tmp_path):
    assert load_commissioning_record(write(tmp_path, good_record(), mode=0o644), FP).usable
