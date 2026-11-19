# Patch 11: ASIAIR ping time allowance on macOS

Measured on the rig: an unanswered one-packet `ping -W 2000` takes 3.02 s on macOS. Guardian
allowed the process 3.0 s, so it was killed first and read as a broken probe (UNKNOWN), not
as "no answer". The allowance is now the wait plus 4 s.
