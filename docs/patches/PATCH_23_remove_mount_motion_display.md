# Patch 23 - remove "Mount motion" from the v1.0 displays

v1.0 does not track mount motion (it always reads UNKNOWN), so it is no longer shown on the web page or in the Mac app. Protection is unchanged; this is display only. The Mac app needs a rebuild (zsh build_on_mac.sh) to pick it up.
Test: tests/test_guardian_v1_web.py::test_mount_motion_is_not_shown_because_v10_does_not_track_it
