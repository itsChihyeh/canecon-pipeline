"""Dagster assets: a failed build stops everything downstream; the asset check reads the quality mart.

The happy path on real data is run by hand (see docs/extensions.md): it needs the published
snapshots, and the synthetic scenario here is deliberately outside the quality bounds.
"""

from __future__ import annotations

import duckdb
import pytest

pytest.importorskip("dagster")

from dagster import materialize  # noqa: E402
from test_vintages import build_store  # noqa: E402

from canecon.orchestration import (  # noqa: E402
    PipelinePaths,
    dashboard_export,
    monthly_brief,
    quality_checks,
    summarize_quality,
    warehouse,
)

ASSETS = [warehouse, dashboard_export, monthly_brief, quality_checks]


def paths(tmp, data_dir):
    return PipelinePaths(
        data_dir=str(data_dir),
        db=str(tmp / "wh.duckdb"),
        export_db=str(tmp / "dash.duckdb"),
        briefs_dir=str(tmp / "briefs"),
        as_of="2026-05-15 00:00:00",
    )


@pytest.mark.parametrize("case", ["quality_errors", "no_snapshots"])
def test_failed_build_stops_downstream(tmp_path, case):
    # quality_errors: the synthetic GDP values (about 1e8) are far below the catalogue's lower
    # bound (1e12), so dbt's error-level quality tests fail the build.
    if case == "quality_errors":
        build_store(tmp_path / "raw")
    result = materialize(ASSETS, resources={"paths": paths(tmp_path, tmp_path / "raw")}, raise_on_error=False)
    assert not result.success
    assert not result.asset_materializations_for_node("warehouse")
    assert not result.asset_materializations_for_node("dashboard_export")
    assert not result.asset_materializations_for_node("monthly_brief")
    assert not (tmp_path / "dash.duckdb").exists()
    assert not (tmp_path / "briefs").exists()


def quality_db(tmp_path, statuses):
    db = tmp_path / "q.duckdb"
    con = duckdb.connect(str(db))
    con.execute(
        "create table main.mart_quality_checks (status varchar, check_name varchar, subject varchar, observed double)"
    )
    con.executemany("insert into main.mart_quality_checks values (?, 'c', 's', 1)", [[s] for s in statuses])
    con.close()
    return str(db)


def test_quality_summary_passes_with_warnings_and_fails_on_errors(tmp_path):
    passed, meta = summarize_quality(quality_db(tmp_path, ["pass", "pass", "warn"]))
    assert passed and meta["checks"] == 3 and meta["warnings"] == 1 and meta["errors"] == 0
    (tmp_path / "q.duckdb").unlink()
    passed, meta = summarize_quality(quality_db(tmp_path, ["pass", "warn", "error"]))
    assert not passed and meta["errors"] == 1 and meta["warnings"] == 1
