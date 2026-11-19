# Patch 16: monitoring watch ready for a long imaging baseline

* Records every raw ASIAIR check, so single missed pings are visible even though Guardian's
  2-in-a-row rule hides them. The summary line and the evidence file give: checks, missed,
  errors, longest run of misses, longest silence in seconds.
* Saves a checkpoint every 60 cycles (5 minutes) to the same evidence file, written atomically,
  so a crash or power loss keeps everything but the last few minutes.
* Ctrl-C (or a kill) finishes the current cycle, then saves and prints the summary.

Baseline run (read-only; do not add --kasa-host for long runs):

    python guardian_v1_watch.py --asiair-host 192.168.1.20 \
        --alpaca-host alpaca-api.tx.starfront.space --alpaca-port 443 \
        --seconds 28800 --label imaging-baseline
