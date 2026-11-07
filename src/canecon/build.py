"""Load raw snapshots into DuckDB, then run dbt (models + tests)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import duckdb

from canecon.load import load

DBT_DIR = Path(__file__).resolve().parents[2] / "dbt"


def run_dbt(
    db_path: Path,
    command: str = "build",
    quality_as_of: str | None = None,
    exclude: str | None = None,
) -> bool:
    """Run dbt. quality_as_of pins the reference time of freshness checks (UTC)."""
    from dbt.cli.main import dbtRunner

    os.environ["CANECON_DB"] = str(db_path.resolve())
    args = [command, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--quiet"]
    if quality_as_of:
        args += ["--vars", json.dumps({"quality_as_of": quality_as_of})]
    if exclude:
        args += ["--exclude", exclude]
    result = dbtRunner().invoke(args)
    return bool(result.success)


def quality_report(db_path: Path) -> list[tuple]:
    """Non-passing data quality checks, for the log."""
    con = duckdb.connect(str(db_path))
    try:
        return con.execute(
            "select status, check_name, subject, observed, detail from main.mart_quality_checks "
            "where status <> 'pass' order by status, check_name, subject"
        ).fetchall()
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the warehouse from raw snapshots.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--db", type=Path, default=Path("data/local/warehouse.duckdb"))
    parser.add_argument("--as-of", help="reference time for freshness checks, UTC 'YYYY-MM-DD HH:MM:SS' (default: now)")
    args = parser.parse_args(argv)
    n = load(args.data_dir, args.db)
    print(f"loaded {n} observation rows into {args.db}")
    ok = run_dbt(args.db, quality_as_of=args.as_of)
    print("dbt build:", "ok" if ok else "FAILED")
    try:
        rows = quality_report(args.db)
    except duckdb.Error as exc:  # e.g. the build failed before the mart existed
        print(f"quality checks unavailable: {exc}")
    else:
        print(f"quality checks not passing: {len(rows)}")
        for status, check, subject, observed, detail in rows:
            print(f"  {status.upper():5} {check} [{subject}] observed={observed} {detail or ''}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
