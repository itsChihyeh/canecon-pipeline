"""Load raw snapshots into DuckDB, then run dbt (models + tests)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from canecon.load import load

DBT_DIR = Path(__file__).resolve().parents[2] / "dbt"


def run_dbt(db_path: Path, command: str = "build") -> bool:
    from dbt.cli.main import dbtRunner

    os.environ["CANECON_DB"] = str(db_path.resolve())
    result = dbtRunner().invoke(
        [command, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR), "--quiet"]
    )
    return bool(result.success)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the warehouse from raw snapshots.")
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--db", type=Path, default=Path("data/local/warehouse.duckdb"))
    args = parser.parse_args(argv)
    n = load(args.data_dir, args.db)
    print(f"loaded {n} observation rows into {args.db}")
    ok = run_dbt(args.db)
    print("dbt build:", "ok" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
