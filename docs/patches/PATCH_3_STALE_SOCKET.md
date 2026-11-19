# Patch 3 — Relaunch after a hard kill (stale operator socket)

## The problem
The monitor refused to start if `operator.sock` already existed. A graceful
stop removes that file, but a hard kill (`kill -9`), a crash that skips cleanup,
or a power failure leaves it behind. The monitor then fails every start with
`FileExistsError`. With launchd `KeepAlive` it would be relaunched every 10
seconds and fail every time, and after a power outage the Mac would come back
with no monitor running.

## The fix
`GuardianOperatorSocket.start()` now removes a leftover socket file only when
ALL of these hold: it is not a symlink, it is a socket (not a regular file),
it is owned by the current user, and connecting to it is refused (nobody is
listening). Anything else is refused exactly as before, including a live
Guardian already listening on that socket.

## Files
Changed: `modules/guardian_v1_operator_socket.py`
New: `tests/test_guardian_v1_stale_socket.py` (7 tests, one of which really
SIGKILLs a process that owns the socket, then relaunches)

## Undo
Restore the backup tarball, or `git checkout -- modules/guardian_v1_operator_socket.py`
and delete `tests/test_guardian_v1_stale_socket.py`.
