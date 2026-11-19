# Patch 13: simultaneous-paths evidence and the sign-off template

`guardian_v1_watch.py --kasa-host <strip>` also READS the power strip each cycle (read-only;
only get_outlet_states is used) and counts the cycles in which the roof feed, the ASIAIR check
and the strip were all available together: "cycles_with_all_three_paths_available" in the
evidence file. This is the evidence the SIMULTANEOUS_PATHS check asks for.

`guardian_v1_commissioning_template.py --output PATH` writes a sign-off template (fingerprint
filled in, all eight checks NOT_TESTED, no approver; never overwrites). The operator marks
checks VERIFIED by hand. `--check PATH` reports whether Guardian would accept the record.
Neither tool approves anything.
