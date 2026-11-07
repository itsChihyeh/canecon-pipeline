"""Failure-and-recovery demo, offline and reproducible.

Replays three collection days against recorded real API responses (tests/fixtures),
with faults injected on day 2:

    day 1  2026-11-05  normal run                                  -> success
    day 2  2026-11-06  Valet answers 500 twice, then recovers      -> retried, ok
                       series info answers 503 on every attempt    -> run is partial
    day 3  2026-11-07  normal run                                  -> success
    then   catch-up for the missed day                             -> success

After each step it rebuilds the warehouse and prints the coverage and quality checks,
so you can see the gap appear and disappear. Nothing is sent over the network.
Run from a checkout of the repository: uv run canecon-demo-failure
"""

from __future__ import annotations

import argparse
import tempfile
from datetime import date
from pathlib import Path
from typing import Callable

import duckdb
import httpx

from canecon.build import run_dbt
from canecon.collect import RawStore, plan_catchup, run_collection
from canecon.faults import FaultInjectingTransport, parse_rule
from canecon.load import load
from canecon.sources import catchup_requests, daily_requests

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
RECORDED = {
    "getDataFromVectorsAndLatestNPeriods": "statcan_vectors_latest_2026-11-07.json",
    "getSeriesInfoFromVector": "statcan_series_info_2026-11-07.json",
    "getChangedCubeList": "statcan_changed_cubes_2026-11-06.json",
    "valet": "boc_observations_recent_2026-11-07.json",
}

DAYS = ["2026-11-05", "2026-11-06", "2026-11-07"]
DAY2_FAULTS = ["valet=500,500", "getSeriesInfo=503*"]
CATCHUP_AT = "2026-11-07T15:30:00Z"
AS_OF = "2026-11-07 16:00:00"


class RecordedTransport(httpx.BaseTransport):
    """Answers every request with the recorded response for its endpoint."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        for key, name in RECORDED.items():
            if key in url:
                return httpx.Response(200, content=(FIXTURES / name).read_bytes(), request=request)
        return httpx.Response(404, content=b"not recorded", request=request)


def _client(fault_specs: list[str] | None, out: Callable[[str], None]) -> httpx.Client:
    transport: httpx.BaseTransport = RecordedTransport()
    if fault_specs:
        transport = FaultInjectingTransport(
            transport,
            [parse_rule(s) for s in fault_specs],
            on_fault=lambda keyword, fault: out(f"      injected {fault} for the '{keyword}' request"),
        )
    return httpx.Client(transport=transport)


def _clock(start: str) -> Callable[[], str]:
    """Fake clock: always the given time, so runs land on the intended day."""
    return lambda: start


def _snapshot(db: Path) -> dict:
    con = duckdb.connect(str(db))
    try:
        coverage = con.execute(
            "select cast(collection_day as varchar), status, n_runs, run_statuses, statcan_series_released "
            "from main.mart_collection_coverage order by collection_day"
        ).fetchall()
        checks = con.execute(
            "select check_name, subject, status, observed, detail from main.mart_quality_checks "
            "where check_name in ('missing_collection_days', 'hours_since_last_successful_run') "
            "order by check_name"
        ).fetchall()
    finally:
        con.close()
    return {"coverage": coverage, "checks": checks}


def run_demo(workdir: Path, out: Callable[[str], None] = print) -> dict:
    raw = workdir / "raw"
    store = RawStore(raw)
    result: dict = {"runs": [], "sleeps": [], "builds": []}

    def sleep(seconds: float) -> None:
        result["sleeps"].append(seconds)
        out(f"      backoff: would wait {seconds:g}s before retrying (skipped in the demo)")

    def build(label: str) -> None:
        db = workdir / f"{label}.duckdb"
        load(raw, db)
        ok = run_dbt(db, quality_as_of=AS_OF)
        snap = _snapshot(db)
        result["builds"].append({"label": label, "dbt_ok": ok, **snap})
        out(f"  dbt build (models + tests): {'ok' if ok else 'FAILED'}")
        for day, status, n_runs, statuses, released in snap["coverage"]:
            note = f", StatCan released that day: {released or 'none of ours'}" if released is not None else ""
            out(f"  coverage {day}: {status} ({n_runs} run(s): {statuses}{note})")
        for name, subject, status, observed, detail in snap["checks"]:
            out(f"  check {name}: {status} (observed {observed:g}){' ' + detail if detail else ''}")

    for i, day in enumerate(DAYS, start=1):
        faults = DAY2_FAULTS if day == "2026-11-06" else None
        out(f"\nDay {i} ({day}): daily run" + (f" with injected faults {faults}" if faults else ""))
        with _client(faults, out) as client:
            summary = run_collection(store, daily_requests(), client, sleep=sleep, now=_clock(f"{day}T15:00:00Z"))
        result["runs"].append(summary)
        out(f"  run status: {summary['status']} ({summary['n_ok']}/{summary['n_requests']} requests ok)")
        if summary["status"] != "success":
            out("  -> this run's data is not loaded; the day counts as missing")

    out("\nBefore catch-up:")
    build("before_catchup")

    days = plan_catchup(store, None, date.fromisoformat(DAYS[-1]))
    out(f"\nCatch-up for missing days {[d.isoformat() for d in days]}")
    with _client(None, out) as client:
        summary = run_collection(
            store, catchup_requests(days, today_eastern=date.fromisoformat(DAYS[-1])), client, sleep=sleep, now=_clock(CATCHUP_AT),
            kind="catchup", for_dates=[d.isoformat() for d in days],
        )
    result["runs"].append(summary)
    out(f"  run status: {summary['status']} ({summary['n_ok']}/{summary['n_requests']} requests ok)")

    out("\nAfter catch-up:")
    build("after_catchup")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline demo: injected API failures, retry, partial run, catch-up.")
    parser.add_argument("--workdir", type=Path, help="keep the demo data here (default: a temporary folder)")
    args = parser.parse_args(argv)
    if args.workdir:
        args.workdir.mkdir(parents=True, exist_ok=True)
        result = run_demo(args.workdir)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(Path(tmp))
    return 0 if all(b["dbt_ok"] for b in result["builds"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
