"""Read-only monitoring watch for commissioning evidence (switches nothing)."""
import argparse
import signal
import sys
from pathlib import Path

from modules.guardian_v1_monitoring_watch import run_watch, watch_path, write_watch

DEFAULT_DIR = Path.home() / "Library/Application Support/GuardianV1/watches"


def main(argv=None, *, asiair_adapter=None, observatory_adapter=None, out=print,
         power_reader_factory=None):
    p = argparse.ArgumentParser(allow_abbrev=False,
        description="Read-only: watch the real ASIAIR and roof feed as Guardian sees them.")
    p.add_argument("--asiair-host", required=True)
    p.add_argument("--alpaca-host", required=True)
    p.add_argument("--alpaca-port", type=int, required=True)
    p.add_argument("--alpaca-device", type=int, default=17)
    p.add_argument("--seconds", type=float, default=120)
    p.add_argument("--interval", type=float, default=5)
    p.add_argument("--lost-after-misses", type=int, default=2,
                   help="Unanswered pings in a row before ASIAIR counts as lost (default 2)")
    p.add_argument("--kasa-host", default=None,
                   help="Also READ the power strip each cycle (read-only) for the simultaneous-paths check")
    p.add_argument("--label", default="watch")
    p.add_argument("--evidence-dir", default=str(DEFAULT_DIR))
    a = p.parse_args(argv)
    if asiair_adapter is None:
        from modules.asiair_icmp_adapter import AsiairIcmpAdapter
        asiair_adapter = AsiairIcmpAdapter(a.asiair_host)
    if observatory_adapter is None:
        from modules.alpaca_observatory_adapter import AlpacaObservatorySafetyAdapter
        observatory_adapter = AlpacaObservatorySafetyAdapter(
            host=a.alpaca_host, port=a.alpaca_port, device_number=a.alpaca_device)
    power_reader = None
    if a.kasa_host:
        if power_reader_factory is None:
            from modules.guardian_v1_rehearsal import target_requests
            from modules.guardian_v1_watch_power import make_reader
            power_reader = make_reader(a.kasa_host, target_requests() + [(1, "Mac Mini")])
        else:
            power_reader = power_reader_factory(a.kasa_host)
    out(f"Watching for {a.seconds:.0f} s (read-only; nothing is switched). Changes print below.")
    path = watch_path(a.evidence_dir, a.label)
    stop = {"requested": False}

    def request_stop(signum, frame):
        stop["requested"] = True  # finish the cycle, then save what was gathered

    previous = [(s, signal.signal(s, request_stop)) for s in (signal.SIGINT, signal.SIGTERM)]
    report = run_watch(should_stop=lambda: stop["requested"], asiair_adapter=asiair_adapter, observatory_adapter=observatory_adapter,
                       seconds=a.seconds, interval_seconds=a.interval,
                       lost_after_misses=a.lost_after_misses,
                       power_reader=power_reader, on_line=out,
                       on_checkpoint=lambda r: write_watch(r, a.evidence_dir, a.label, path))
    for sig, handler in previous:
        signal.signal(sig, handler)
    write_watch(report, a.evidence_dir, a.label, path)
    s = report["asiair_ping_summary"]
    out(f"ASIAIR checks: {s['checks']}, missed: {s['missed']}, errors: {s['errors']}, "
        f"longest run of misses: {s['longest_miss_streak']}, longest silence: {s['longest_silence_seconds']} s")
    out(f"\nDone: {report['cycles']} cycles, {len(report['changes'])} state line(s). Evidence: {path}")
    if a.kasa_host:
        out(f"Cycles with roof feed, ASIAIR and power strip ALL available together: "
            f"{report['cycles_with_all_three_paths_available']} of {report['cycles']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
