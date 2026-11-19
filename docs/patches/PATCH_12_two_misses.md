# Patch 12: ASIAIR lost only after 2 missed checks in a row

Before: one unanswered ping made an established ASIAIR "lost", which cuts power. Now Guardian's
compositions (and the monitoring watch) require 2 unanswered checks in a row (about 10 s at the
5 s cycle). A reply in between resets the count. The first reply after LOST recovers it.

Setting: `--asiair-lost-after-misses N` on guardian_v1_armed.py and guardian_v1_watch.py
(default 2). The tracker class default stays 1 for compatibility; every Guardian composition
passes DEFAULT_LOST_AFTER_MISSES. A probe that errors (neither reachable nor unreachable) does
not count as a miss.
