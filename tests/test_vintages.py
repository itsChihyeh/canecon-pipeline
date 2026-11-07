"""End-to-end vintage tests: synthetic raw captures -> load -> dbt build -> checks.

Every expected value below was worked out by hand from the scenario, not produced by
the code under test.

Scenario (StatCan GDP vector, values in millions, scalar factor 6):

| run | captured (UTC)     | release (Eastern) | 2025-11   | 2025-12   | note                      |
|-----|--------------------|-------------------|-----------|-----------|---------------------------|
| A   | 2026-01-10 15:00   | 2026-01-09 08:30  | 100       | -         | first capture             |
| B   | 2026-02-10 15:00   | 2026-02-09 08:30  | 101       | 200       | Nov revised up            |
| C   | 2026-03-10 15:00   | 2026-03-09 08:30  | 100       | 200       | Nov revised back (DST on) |
| D   | 2026-03-11 15:00   | 2026-03-09 08:30  | 100       | 200       | same content again        |
| E   | 2026-04-10 15:00   | 2026-04-09 08:30  | 0.1 (x1e9)| 200.0     | scale/decimals change only|
| F   | 2026-05-10 15:00   | 2026-05-08 08:30  | 999       | 999       | run partial -> ignored    |
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import httpx
import pytest

from canecon.build import run_dbt
from canecon.collect import RawStore, run_collection
from canecon.load import load
from canecon.pit import as_of
from canecon.sources import daily_requests

M = 10**6


def statcan_body(release: str, points: list[tuple]) -> bytes:
    """points: (refPer, value, scalarFactorCode, decimals)"""
    return json.dumps(
        [
            {
                "status": "SUCCESS",
                "object": {
                    "vectorId": 65201210,
                    "productId": 36100434,
                    "vectorDataPoint": [
                        {
                            "refPer": ref,
                            "value": value,
                            "decimals": dec,
                            "scalarFactorCode": scalar,
                            "releaseTime": release,
                            "statusCode": 0,
                            "symbolCode": 0,
                        }
                        for ref, value, scalar, dec in points
                    ],
                },
            }
        ]
    ).encode()


BOC_OK = json.dumps({"observations": [{"d": "2026-01-09", "V39079": {"v": "2.50"}}]}).encode()

RUNS = [
    ("2026-01-10T15:00:00Z", statcan_body("2026-01-09T08:30", [("2025-11-01", 100.0, 6, 0)]), 200),
    (
        "2026-02-10T15:00:00Z",
        statcan_body("2026-02-09T08:30", [("2025-11-01", 101.0, 6, 0), ("2025-12-01", 200.0, 6, 0)]),
        200,
    ),
    (
        "2026-03-10T15:00:00Z",
        statcan_body("2026-03-09T08:30", [("2025-11-01", 100.0, 6, 0), ("2025-12-01", 200.0, 6, 0)]),
        200,
    ),
    (
        "2026-03-11T15:00:00Z",
        statcan_body("2026-03-09T08:30", [("2025-11-01", 100.0, 6, 0), ("2025-12-01", 200.0, 6, 0)]),
        200,
    ),
    (
        "2026-04-10T15:00:00Z",
        statcan_body("2026-04-09T08:30", [("2025-11-01", 0.1, 9, 1), ("2025-12-01", 200.0, 6, 1)]),
        200,
    ),
    (
        "2026-05-10T15:00:00Z",
        statcan_body("2026-05-08T08:30", [("2025-11-01", 999.0, 6, 0), ("2025-12-01", 999.0, 6, 0)]),
        503,
    ),
]


def build_store(root: Path) -> None:
    store = RawStore(root)
    reqs = [r for r in daily_requests() if r.request_id in ("statcan_vectors_latest", "boc_observations_recent")]
    for captured, body, boc_status in RUNS:

        def handler(request: httpx.Request, body=body, boc_status=boc_status) -> httpx.Response:
            if "valet" in str(request.url):
                return httpx.Response(boc_status, content=BOC_OK if boc_status == 200 else b"down")
            return httpx.Response(200, content=body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        run_collection(store, reqs, client, sleep=lambda _: None, now=lambda c=captured: c)


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("wh")
    build_store(tmp / "raw")
    db = tmp / "wh.duckdb"
    load(tmp / "raw", db)
    # Synthetic dates and tiny values: quality thresholds are tested in test_reliability.py.
    assert run_dbt(db, exclude="tag:quality"), "dbt build (models + data tests) failed"
    con = duckdb.connect(str(db))
    yield con, tmp
    con.close()


def gdp_vintages(con, ref):
    return con.execute(
        "select vintage_number, value, cast(valid_from as varchar), cast(valid_to as varchar) "
        "from vintages where series_id = 'gdp_all_industries' and ref_period = ? order by vintage_number",
        [ref],
    ).fetchall()


def test_revision_up_and_back_gives_three_vintages(warehouse):
    con, _ = warehouse
    # Jan 9 08:30 EST = 13:30Z; Feb 9 08:30 EST = 13:30Z; Mar 9 08:30 EDT = 12:30Z
    assert gdp_vintages(con, "2025-11-01") == [
        (1, 100 * M, "2026-01-09 13:30:00", "2026-02-09 13:30:00"),
        (2, 101 * M, "2026-02-09 13:30:00", "2026-03-09 12:30:00"),
        (3, 100 * M, "2026-03-09 12:30:00", None),
    ]


def test_scale_and_decimal_changes_are_not_revisions(warehouse):
    con, _ = warehouse
    # Run E re-expresses Nov as 0.1 x 1e9 and Dec with one decimal: no new vintages.
    assert len(gdp_vintages(con, "2025-11-01")) == 3
    assert gdp_vintages(con, "2025-12-01") == [(1, 200 * M, "2026-02-09 13:30:00", None)]


def test_same_content_rerun_adds_no_vintage_and_no_object(warehouse):
    con, tmp = warehouse
    n_vintages = con.execute("select count(*) from vintages").fetchone()[0]
    assert n_vintages == 4 + 1  # 4 GDP vintages + 1 policy-rate vintage
    objects = list((tmp / "raw" / "objects").rglob("*.json"))
    # distinct contents: StatCan bodies A, B, C(=D), E, F + BoC ok body = 6
    assert len(objects) == 6


def test_partial_run_is_ignored(warehouse):
    con, _ = warehouse
    assert con.execute("select count(*) from raw.observations where value = 999").fetchone()[0] == 0
    assert con.execute("select status from raw.runs order by started_at desc limit 1").fetchone()[0] == "partial"


def test_point_in_time_has_no_look_ahead(warehouse):
    con, _ = warehouse
    gdp = "gdp_all_industries"
    assert [(r[1].isoformat(), r[2]) for r in as_of(con, "2026-02-01 00:00:00", gdp)] == [("2025-11-01", 100 * M)]
    # one second before the February release: still the old value, December unknown
    assert [(r[1].isoformat(), r[2]) for r in as_of(con, "2026-02-09 13:29:59", gdp)] == [("2025-11-01", 100 * M)]
    assert [(r[1].isoformat(), r[2]) for r in as_of(con, "2026-02-09 13:30:00", gdp)] == [
        ("2025-11-01", 101 * M),
        ("2025-12-01", 200 * M),
    ]
    assert [(r[1].isoformat(), r[2]) for r in as_of(con, "2026-12-31 00:00:00", gdp)] == [
        ("2025-11-01", 100 * M),
        ("2025-12-01", 200 * M),
    ]
    assert as_of(con, "2026-01-01 00:00:00", gdp) == []


def test_first_release_flags(warehouse):
    con, _ = warehouse
    rows = dict(
        con.execute(
            "select cast(ref_period as varchar), is_true_first_release from mart_first_release "
            "where series_id = 'gdp_all_industries'"
        ).fetchall()
    )
    # Nov was already published when we started; Dec appeared after we started watching.
    assert rows == {"2025-11-01": False, "2025-12-01": True}


def test_growth_revision_uses_point_in_time_previous_month(warehouse):
    con, _ = warehouse
    row = con.execute(
        "select first_growth_pct, latest_growth_pct, growth_revision_pp from mart_growth_revisions "
        "where series_id = 'gdp_all_industries' and ref_period = '2025-12-01'"
    ).fetchone()
    # first: 200/101 - 1 = 0.980198...; latest: 200/100 - 1 = 1.0
    assert [float(x) for x in row] == [98.0198, 100.0, 1.9802]


def test_lineage_points_to_the_exact_raw_snapshot(warehouse):
    con, tmp = warehouse
    path, sha = con.execute(
        "select source_object_path, source_snapshot_sha256 from vintages "
        "where series_id = 'gdp_all_industries' and ref_period = '2025-11-01' and vintage_number = 3"
    ).fetchone()
    assert (tmp / "raw" / path).read_bytes() == RUNS[2][1]
    assert sha in path


def test_rebuild_is_idempotent(warehouse, tmp_path):
    con, tmp = warehouse
    db2 = tmp_path / "again.duckdb"
    load(tmp / "raw", db2)
    assert run_dbt(db2, exclude="tag:quality")
    con2 = duckdb.connect(str(db2))
    q = "select * from vintages order by series_id, ref_period, vintage_number"
    assert con2.execute(q).fetchall() == con.execute(q).fetchall()
    con2.close()


def test_growth_revision_path_follows_each_release(warehouse):
    con, _ = warehouse
    rows = con.execute(
        "select release_number, cast(released_at as varchar), growth_pct, change_since_first_pp, gap_to_latest_pp "
        "from mart_growth_revision_path where series_id = 'gdp_all_industries' and ref_period = '2025-12-01' "
        "order by release_number"
    ).fetchall()
    # Dec first appears in the Feb 9 release (Nov 101, Dec 200): 200/101 - 1 = 98.0198%.
    # Mar 9 revises Nov back to 100: 200/100 - 1 = 100%. The Apr 9 release only re-expresses
    # the same values (scale/decimals), so growth stays 100%. The partial May run is ignored.
    assert [(n, t, float(g), float(c), float(d)) for n, t, g, c, d in rows] == [
        (1, "2026-02-09 13:30:00", 98.0198, 0.0, 1.9802),
        (2, "2026-03-09 12:30:00", 100.0, 1.9802, 0.0),
        (3, "2026-04-09 12:30:00", 100.0, 1.9802, 0.0),
    ]


# Mixed precision: each release is compared with the last value kept as a vintage, not with
# the observation just before it. Nov (millions):
#   Jan 9: 100.24 (2 decimals) -> vintage 1
#   Feb 9: 100.2  (1 decimal)  -> same as 100.24 at one decimal, no new vintage
#   Mar 9: 100.16 (2 decimals) -> differs from 100.24 at two decimals: vintage 2.
#          (Compared only with Feb's 100.2 at one decimal it would look unchanged.)
#   Apr 9: 100.2  (1 decimal)  -> same as 100.16 at one decimal, no new vintage
PRECISION_RUNS = [
    ("2026-01-10T15:00:00Z", statcan_body("2026-01-09T08:30", [("2025-11-01", 100.24, 6, 2)])),
    ("2026-02-10T15:00:00Z", statcan_body("2026-02-09T08:30", [("2025-11-01", 100.2, 6, 1)])),
    ("2026-03-10T15:00:00Z", statcan_body("2026-03-09T08:30", [("2025-11-01", 100.16, 6, 2)])),
    ("2026-04-10T15:00:00Z", statcan_body("2026-04-09T08:30", [("2025-11-01", 100.2, 6, 1)])),
]


@pytest.fixture(scope="module")
def precision_warehouse(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("precision")
    store = RawStore(tmp / "raw")
    reqs = [r for r in daily_requests() if r.request_id in ("statcan_vectors_latest", "boc_observations_recent")]
    for captured, body in PRECISION_RUNS:

        def handler(request: httpx.Request, body=body) -> httpx.Response:
            return httpx.Response(200, content=BOC_OK if "valet" in str(request.url) else body)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        run_collection(store, reqs, client, sleep=lambda _: None, now=lambda c=captured: c)
    db = tmp / "wh.duckdb"
    load(tmp / "raw", db)
    assert run_dbt(db, exclude="tag:quality"), "dbt build (models + data tests) failed"
    con = duckdb.connect(str(db))
    yield con
    con.close()


def test_mixed_precision_compares_with_last_kept_vintage(precision_warehouse):
    rows = gdp_vintages(precision_warehouse, "2025-11-01")
    assert [(n, round(float(v)), f, t) for n, v, f, t in rows] == [
        (1, 100_240_000, "2026-01-09 13:30:00", "2026-03-09 12:30:00"),
        (2, 100_160_000, "2026-03-09 12:30:00", None),
    ]
