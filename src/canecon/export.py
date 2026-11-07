"""Export the public part of the warehouse for the dashboard.

The dashboard (Evidence) bundles a DuckDB driver that cannot read files written by
DuckDB 2.x, so this writes a separate small database in an older storage format.

It is also the publication boundary: only series with public_dashboard = true in
dbt/seeds/series_info.csv are exported, so a series whose licence is unclear (USD/CAD,
sourced by the Bank of Canada from LSEG) never reaches the public site.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

STORAGE_VERSION = "v1.4.0"
REPO_URL = "https://github.com/itsChihyeh/canecon-pipeline"

PUBLIC = "(select series_id from w.main.series_info where public_dashboard)"

# name -> query against the warehouse attached as `w`. Every query that carries series
# data filters on PUBLIC; tests check that no other series leaks through.
TABLES: dict[str, str] = {
    "series": f"""
        select i.series_id, i.label, i.definition, i.source_name, i.source_code, i.source_url,
               c.source, c.frequency, c.unit
        from w.main.series_info i join w.main.series_catalog c using (series_id)
        where i.series_id in {PUBLIC}
    """,
    "latest": f"""
        select series_id, ref_period, cast(value as double) as value, n_vintages, published_at,
               source_snapshot_sha256, source_object_path
        from w.main.mart_latest where series_id in {PUBLIC}
    """,
    "vintages": f"""
        select series_id, ref_period, vintage_number, cast(value as double) as value,
               valid_from, valid_to, first_seen_at, source_kind, release_label,
               cast(revision_from_previous as double) as revision_from_previous,
               source_snapshot_sha256, source_object_path
        from w.main.vintages where series_id in {PUBLIC}
    """,
    "first_release": f"""
        select series_id, ref_period, cast(first_value as double) as first_value,
               first_published_at, is_true_first_release, source_kind
        from w.main.mart_first_release where series_id in {PUBLIC}
    """,
    "growth_revisions": f"select * from w.main.mart_growth_revisions where series_id in {PUBLIC}",
    "growth_revision_path": f"select * from w.main.mart_growth_revision_path where series_id in {PUBLIC}",
    "series_freshness": f"select * from w.main.mart_series_freshness where series_id in {PUBLIC}",
    "quality_checks": f"""
        select * from w.main.mart_quality_checks
        where subject in {PUBLIC} or subject not in (select series_id from w.main.series_catalog)
    """,
    "collection_coverage": "select * from w.main.mart_collection_coverage",
    "request_freshness": "select * from w.main.mart_data_freshness",
    "runs": "select * from w.raw.runs",
}


def export(warehouse: Path, out: Path, data_commit: str | None = None) -> dict[str, int]:
    """Write the dashboard database. Returns row counts per table."""
    out.parent.mkdir(parents=True, exist_ok=True)
    for p in (out, out.with_name(out.name + ".wal")):
        p.unlink(missing_ok=True)
    con = duckdb.connect()
    try:
        con.execute("attach ? as w (read_only)", [str(warehouse)])
        con.execute(f"attach ? as d (storage_version '{STORAGE_VERSION}')", [str(out)])
        counts = {}
        for name, query in TABLES.items():
            con.execute(f"create table d.main.{name} as {query}")
            counts[name] = con.execute(f"select count(*) from d.main.{name}").fetchall()[0][0]
        ref = data_commit or "data"
        con.execute(
            "create table d.main.build_info as select ? as built_at, ? as data_commit, ? as snapshot_base_url, "
            "(select max(checked_as_of) from w.main.mart_quality_checks) as quality_checked_as_of",
            [
                datetime.now(UTC).replace(tzinfo=None, microsecond=0),
                data_commit,
                f"{REPO_URL}/blob/{ref}/raw/",
            ],
        )
        con.execute("detach d")
    finally:
        con.close()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export the public dashboard database.")
    parser.add_argument("--db", type=Path, default=Path("data/local/warehouse.duckdb"))
    parser.add_argument("--out", type=Path, default=Path("dashboard/sources/canecon/canecon.duckdb"))
    parser.add_argument("--data-commit", help="data branch commit the warehouse was built from (for snapshot links)")
    args = parser.parse_args(argv)
    counts = export(args.db, args.out, args.data_commit)
    for name, n in counts.items():
        print(f"  {name}: {n} rows")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
