"""The dashboard export is the publication boundary: only public series leave the warehouse."""

from __future__ import annotations

import duckdb
import pytest
from test_vintages import build_store

from canecon.build import run_dbt
from canecon.export import TABLES, export
from canecon.load import load

PUBLIC = {
    "gdp_all_industries",
    "retail_sales_total_sa",
    "unemployment_rate_sa",
    "cpi_all_items",
    "policy_rate_target",
    "gov_bond_yield_2y",
    "gov_bond_yield_10y",
}


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("export")
    build_store(tmp / "raw")
    db = tmp / "wh.duckdb"
    load(tmp / "raw", db)
    assert run_dbt(db, exclude="tag:quality")
    con = duckdb.connect(str(db))
    # The synthetic scenario has GDP and the policy rate only; add an FX row to every
    # table that carries series data, as if it had been collected.
    con.execute(
        "insert into main.vintages by name select * replace ('fx_usdcad' as series_id) from main.vintages limit 1"
    )
    con.execute(
        "insert into main.mart_latest by name select * replace ('fx_usdcad' as series_id) from main.mart_latest limit 1"
    )
    con.execute(
        "insert into main.mart_first_release by name "
        "select * replace ('fx_usdcad' as series_id) from main.mart_first_release limit 1"
    )
    # dbt keeps its connection to db open inside this process, so export from a copy;
    # in the pipeline the export runs as its own process.
    copy = tmp / "wh_copy.duckdb"
    con.execute("attach ? as wh_copy", [str(copy)])
    con.execute("copy from database wh to wh_copy")
    con.execute("detach wh_copy")
    con.close()
    out = tmp / "dash.duckdb"
    counts = export(copy, out, data_commit="abc1234")
    con = duckdb.connect(str(out), read_only=True)
    yield con, counts
    con.close()


def test_fx_is_not_exported(exported):
    con, _ = exported
    for table in TABLES:
        cols = [r[0] for r in con.execute(f"describe {table}").fetchall()]
        key = "series_id" if "series_id" in cols else "subject" if "subject" in cols else None
        if key is None:
            continue
        values = {r[0] for r in con.execute(f"select distinct {key} from {table}").fetchall()}
        assert "fx_usdcad" not in values, table
        if key == "series_id":
            assert values <= PUBLIC, table


def test_public_series_are_exported_with_their_values(exported):
    con, counts = exported
    assert {r[0] for r in con.execute("select series_id from series").fetchall()} == PUBLIC
    # Hand-computed from the scenario in test_vintages: GDP Nov 2025 has 3 vintages, Dec 1.
    assert con.execute("select count(*) from vintages where series_id = 'gdp_all_industries'").fetchone()[0] == 4
    assert counts["vintages"] == 5  # + 1 policy-rate vintage; the FX row is dropped


def test_snapshot_links_point_at_the_data_commit(exported):
    con, _ = exported
    assert con.execute("select snapshot_base_url from build_info").fetchone()[0] == (
        "https://github.com/itsChihyeh/canecon-pipeline/blob/abc1234/raw/"
    )
