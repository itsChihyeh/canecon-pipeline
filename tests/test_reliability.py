"""Reliability tests: fault injection, catch-up, coverage and data quality checks.

Inputs are recorded real responses (tests/fixtures). Expected values are worked out
by hand from the scenario in canecon.demo:

    2026-11-05  daily run, all ok                        -> collected
    2026-11-06  daily run: Valet 500, 500 then ok;        -> partial, day missing
                series info 503 on all 4 attempts
    2026-11-07  daily run, all ok                        -> collected
    2026-11-07 15:30  catch-up for 2026-11-06            -> 2026-11-06 caught_up
"""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import duckdb
import httpx
import pytest

from canecon.build import run_dbt
from canecon.collect import RawStore, missing_days, plan_catchup, run_collection, validate
from canecon.demo import RecordedTransport, run_demo
from canecon.faults import FaultInjectingTransport, parse_rule
from canecon.load import load
from canecon.sources import catchup_requests

FIXTURES = Path(__file__).parent / "fixtures"


# --- fault rules ---------------------------------------------------------------


def test_fault_rule_parsing():
    r = parse_rule("valet=500,500")
    assert (r.keyword, r.faults, r.forever) == ("valet", ["500", "500"], False)
    r = parse_rule("getSeriesInfo=503*")
    assert (r.keyword, r.faults, r.forever) == ("getSeriesInfo", ["503"], True)
    assert parse_rule("statcan=timeout").faults == ["timeout"]
    for bad in ["valet", "valet=", "=500", "valet=200", "valet=abc", "valet=500,503*"]:
        with pytest.raises(ValueError):
            parse_rule(bad)


def test_injected_faults_run_out_then_requests_pass_through():
    t = FaultInjectingTransport(RecordedTransport(), [parse_rule("valet=500,timeout")])
    client = httpx.Client(transport=t)
    url = "https://www.bankofcanada.ca/valet/observations/X/json"
    assert client.get(url).status_code == 500
    with pytest.raises(httpx.ConnectTimeout):
        client.get(url)
    assert client.get(url).status_code == 200
    assert t.log == [("valet", "500"), ("valet", "timeout")]


# --- missing days and catch-up planning ---------------------------------------


def run(started: str, status: str, kind: str = "daily", **extra) -> dict:
    return {"run_id": started, "started_at": started, "status": status, "kind": kind, **extra}


def test_missing_days_counts_only_successful_runs():
    runs = [
        run("2026-11-05T15:00:00Z", "success"),
        run("2026-11-06T15:00:00Z", "partial"),
        # 2026-11-07: no run at all
        run("2026-11-08T15:00:00Z", "success"),
        run("2026-11-08T16:00:00Z", "success", kind="backfill_gdp_realtime"),
    ]
    assert missing_days(runs, date(2026, 11, 9)) == [date(2026, 11, 6), date(2026, 11, 7), date(2026, 11, 9)]
    runs.append(run("2026-11-09T10:00:00Z", "success", kind="catchup", for_dates=["2026-11-06", "2026-11-07"]))
    assert missing_days(runs, date(2026, 11, 9)) == [date(2026, 11, 9)]


def test_runs_logged_before_p3_count_by_start_day():
    # The first real run (2026-11-07) has neither 'kind' nor 'for_dates'.
    legacy = {"run_id": "a", "started_at": "2026-11-07T14:32:59Z", "status": "success"}
    assert missing_days([legacy], date(2026, 11, 8)) == [date(2026, 11, 8)]


def test_catchup_rejects_future_dates(tmp_path):
    with pytest.raises(ValueError):
        plan_catchup(RawStore(tmp_path), [date(2026, 11, 8)], today=date(2026, 11, 7))
    assert plan_catchup(RawStore(tmp_path), [date(2026, 11, 6), date(2026, 11, 6)], date(2026, 11, 7)) == [
        date(2026, 11, 6)
    ]


def test_catchup_requests_cover_each_missed_day():
    reqs = catchup_requests([date(2026, 11, 6), date(2026, 11, 4)], today_eastern=date(2026, 11, 7))
    ids = [r.request_id for r in reqs]
    assert ids == [
        "statcan_vectors_latest",
        "statcan_series_info",
        "boc_observations_recent",
        "boc_observations_since",
        "statcan_changed_cubes_2026-11-04",
        "statcan_changed_cubes_2026-11-06",
    ]
    since = reqs[3]
    assert since.params == {"start_date": "2026-10-21"}  # 14 days before the earliest missed day
    assert reqs[5].url.endswith("/getChangedCubeList/2026-11-06")


def test_catchup_does_not_ask_statcan_about_today():
    # Found live on 2026-11-07: getChangedCubeList for the current day answers 409.
    ids = [r.request_id for r in catchup_requests([date(2026, 11, 7)], today_eastern=date(2026, 11, 7))]
    assert not any(i.startswith("statcan_changed_cubes_") for i in ids)
    assert "boc_observations_since" in ids


def test_recorded_changed_cubes_pass_validation():
    req = catchup_requests([date(2026, 11, 6)], today_eastern=date(2026, 11, 7))[-1]
    assert validate(req, (FIXTURES / "statcan_changed_cubes_2026-11-06.json").read_bytes()) is None
    # A future date returns 404 with a message, never a 200 that looks valid.
    assert validate(req, b'{"message":"The input date is a future release date."}') == "expected status SUCCESS"


# --- the demo scenario end to end ---------------------------------------------


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("demo")
    return workdir, run_demo(workdir, out=lambda _: None)


def test_demo_retries_with_backoff_and_marks_day_two_partial(demo):
    _, result = demo
    assert [r["status"] for r in result["runs"]] == ["success", "partial", "success", "success"]
    assert result["runs"][1]["n_ok"] == 2
    # series info: 4 attempts, 3 waits (2, 4, 8); Valet: 3 attempts, 2 waits (2, 4)
    assert result["sleeps"] == [2.0, 4.0, 8.0, 2.0, 4.0]


def test_demo_manifest_records_attempts(demo):
    workdir, _ = demo
    rows = [json.loads(line) for line in (workdir / "raw" / "manifest.jsonl").read_text().splitlines()]
    day2 = {r["request_id"]: r for r in rows if r["captured_at"].startswith("2026-11-06")}
    assert (day2["statcan_series_info"]["attempts"], day2["statcan_series_info"]["ok"]) == (4, False)
    assert day2["statcan_series_info"]["http_status"] == 503
    assert (day2["boc_observations_recent"]["attempts"], day2["boc_observations_recent"]["ok"]) == (3, True)


def test_demo_gap_appears_then_is_filled(demo):
    _, result = demo
    before, after = result["builds"]
    assert before["dbt_ok"] and after["dbt_ok"]
    assert [(d, s) for d, s, *_ in before["coverage"]] == [
        ("2026-11-05", "collected"),
        ("2026-11-06", "missing"),
        ("2026-11-07", "collected"),
    ]
    assert [(d, s) for d, s, *_ in after["coverage"]] == [
        ("2026-11-05", "collected"),
        ("2026-11-06", "caught_up"),
        ("2026-11-07", "collected"),
    ]
    # The recorded getChangedCubeList for 2026-11-06 lists 14-10-0287 (Labour Force Survey).
    assert after["coverage"][1][4] == "unemployment_rate_sa"
    assert before["coverage"][1][4] is None  # nobody asked StatCan before the catch-up

    def gaps(build):
        return next(c for c in build["checks"] if c[0] == "missing_collection_days")

    assert gaps(before)[2:4] == ("warn", 1.0)
    assert gaps(after)[2:4] == ("pass", 0.0)


def test_demo_quality_checks_all_pass_after_catchup(demo):
    workdir, _ = demo
    con = duckdb.connect(str(workdir / "after_catchup.duckdb"))
    rows = con.execute("select check_name, subject, status from main.mart_quality_checks").fetchall()
    con.close()
    assert len(rows) == 7 * 3 + 2  # freshness, range, jump per series + 2 collector checks
    assert {s for _, _, s in rows} == {"pass"}


# --- quality checks fail the build -------------------------------------------


def corrupt_gdp_scale(raw: Path) -> None:
    """Rewrite the latest GDP response with values 1000x too large (a scale bug).

    Stored objects are append-only, so this builds a new object and a new successful
    run instead of editing anything.
    """
    body = json.loads((FIXTURES / "statcan_vectors_latest_2026-11-07.json").read_bytes())
    for item in body:
        if item["object"]["vectorId"] == 65201210:
            for p in item["object"]["vectorDataPoint"]:
                p["value"] = p["value"] * 1000
    content = json.dumps(body).encode()

    def handler(request: httpx.Request) -> httpx.Response:
        if "getDataFromVectorsAndLatestNPeriods" in str(request.url):
            return httpx.Response(200, content=content)
        return RecordedTransport().handle_request(request)

    from canecon.sources import daily_requests

    run_collection(
        RawStore(raw), daily_requests(), httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None, now=lambda: "2026-11-07T15:45:00Z",
    )


def test_scale_bug_fails_the_build(demo, tmp_path):
    workdir, _ = demo
    raw = tmp_path / "raw"
    shutil.copytree(workdir / "raw", raw)
    corrupt_gdp_scale(raw)
    db = tmp_path / "wh.duckdb"
    load(raw, db)
    assert not run_dbt(db, quality_as_of="2026-11-07 16:00:00")
    con = duckdb.connect(str(db))
    failing = con.execute(
        "select check_name, subject, status from main.mart_quality_checks where status <> 'pass' order by 1"
    ).fetchall()
    con.close()
    # 1000x GDP: values above the 5e12 bound; the jump between the old and new latest
    # values does not show because every period of the latest response was rescaled.
    assert failing == [("vintages_out_of_range", "gdp_all_industries", "error")]


def test_stale_data_fails_the_build(demo, tmp_path):
    workdir, _ = demo
    db = tmp_path / "late.duckdb"
    load(workdir / "raw", db)
    # Ten days after the last run, with no new data: collector and daily series are stale.
    assert not run_dbt(db, quality_as_of="2026-11-17 16:00:00")
    con = duckdb.connect(str(db))
    errors = con.execute(
        "select check_name, subject from main.mart_quality_checks where status = 'error' order by 1, 2"
    ).fetchall()
    con.close()
    assert errors == [
        ("hours_since_last_successful_run", "collector"),
        ("ref_period_age_days", "gov_bond_yield_10y"),
        ("ref_period_age_days", "gov_bond_yield_2y"),
        ("ref_period_age_days", "policy_rate_target"),
    ]
