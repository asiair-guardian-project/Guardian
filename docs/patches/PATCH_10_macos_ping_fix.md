# Patch 10: ASIAIR ping check on macOS

Found by the Patch 9 watch on the real rig: with the ASIAIR powered off, Guardian still
reported ONLINE. macOS `ping` exits 2 when packets are sent and none return; the adapter
only treated exit 1 as "unreachable" and raised on 2, so the probe became UNKNOWN and the
session state stayed ONLINE. ASIAIR_LOST could never fire on a Mac.

The adapter now trusts the ping statistics line (packets sent, none received = unreachable)
on both macOS and Linux. An unknown host or other ping failure is still a probe failure.
