"""The pipeline as Dagster assets, with the data quality checks as Dagster asset checks.

    raw_snapshots (external: written to the `data` branch by the GitHub Actions collector)
      -> warehouse         canecon.build in its own process (load + dbt build)
           [check] quality_checks: fails on any 'error' row in mart_quality_checks
      -> dashboard_export  canecon.export (public series only)
      -> monthly_brief     canecon.brief for the last month (template unless a model is set)

GitHub Actions still runs the daily collection and the dashboard build; this module gives the
same steps lineage, run history and checks in Dagster's UI. Install with
`uv sync --group orchestration`, then `uv run dagster dev -m canecon.orchestration`.
"""


import json
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetSpec,
    ConfigurableResource,
    Definitions,
    Failure,
    MaterializeResult,
    MetadataValue,
    asset,
    asset_check,
)

from canecon.brief import write_brief
from canecon.export import export


class PipelinePaths(ConfigurableResource):
    data_dir: str = "data/snap/raw"
    db: str = "data/local/warehouse.duckdb"
    export_db: str = "dashboard/sources/canecon/canecon.duckdb"
    briefs_dir: str = "data/local/briefs"
    as_of: str = ""  # UTC 'YYYY-MM-DD HH:MM:SS'; empty = now
    brief_model: str = ""  # empty = template only, no API call

    def as_of_utc(self) -> str:
        return self.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


raw_snapshots = AssetSpec(
    "raw_snapshots",
    description="Append-only raw API responses and manifests on the `data` branch, written by "
    ".github/workflows/collect.yml. Not materialized by Dagster.",
)


@asset(deps=[raw_snapshots], description="DuckDB warehouse: raw tables, dbt staging, vintages and marts.")
def warehouse(context: AssetExecutionContext, paths: PipelinePaths) -> MaterializeResult:
    # dbt keeps its DuckDB connection open inside the process, so the build runs in its own
    # process, as in CI; a failed build stops everything downstream.
    cmd = [sys.executable, "-m", "canecon.build", "--data-dir", paths.data_dir, "--db", paths.db, "--as-of", paths.as_of_utc()]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    context.log.info(proc.stdout)
    if proc.returncode != 0:
        raise Failure(description="canecon-build failed", metadata={"output": MetadataValue.text(proc.stdout + proc.stderr)})
    con = duckdb.connect(paths.db, read_only=True)
    try:
        n_series, n_vintages = con.execute("select count(distinct series_id), count(*) from main.vintages").fetchone()
    finally:
        con.close()
    return MaterializeResult(metadata={"series": n_series, "vintages": n_vintages})


def summarize_quality(db: str) -> tuple[bool, dict]:
    """(passed, metadata) from mart_quality_checks: any 'error' row fails, 'warn' rows are listed."""
    con = duckdb.connect(db, read_only=True)
    try:
        rows = con.execute(
            "select status, check_name, subject, observed from main.mart_quality_checks where status <> 'pass' "
            "order by status, check_name, subject"
        ).fetchall()
        total = con.execute("select count(*) from main.mart_quality_checks").fetchone()[0]
    finally:
        con.close()
    errors = [r for r in rows if r[0] == "error"]
    return not errors, {
        "checks": total,
        "errors": len(errors),
        "warnings": len(rows) - len(errors),
        "not_passing": [[str(v) for v in r] for r in rows],
    }


@asset_check(
    asset=warehouse,
    description="Rows of mart_quality_checks. Error-level rows already fail the dbt build, so after a "
    "successful build this mostly shows the warnings; it fails if an error row is ever present.",
)
def quality_checks(paths: PipelinePaths) -> AssetCheckResult:
    passed, meta = summarize_quality(paths.db)
    meta["not_passing"] = MetadataValue.json(meta["not_passing"])
    return AssetCheckResult(passed=passed, severity=AssetCheckSeverity.ERROR, metadata=meta)


@asset(deps=[warehouse], description="Small DuckDB file (v1.4 format) with public series only, read by the dashboard.")
def dashboard_export(paths: PipelinePaths) -> MaterializeResult:
    counts = export(Path(paths.db), Path(paths.export_db))
    return MaterializeResult(metadata={k: int(v) for k, v in counts.items()})


@asset(deps=[warehouse], description="Brief for the last complete month; every number checked against the warehouse.")
def monthly_brief(paths: PipelinePaths) -> MaterializeResult:
    as_of_utc = paths.as_of_utc()
    d = datetime.strptime(as_of_utc[:10], "%Y-%m-%d")
    month = f"{d.year - (d.month == 1)}-{(d.month - 2) % 12 + 1:02d}"
    generator = None
    if paths.brief_model:
        from canecon.brief import AnthropicGenerator

        generator = AnthropicGenerator(paths.brief_model)
    con = duckdb.connect(paths.db, read_only=True)
    try:
        result = write_brief(con, month, as_of_utc, generator)
    finally:
        con.close()
    out = Path(paths.briefs_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{month}.json").write_text(json.dumps(asdict(result), indent=2, default=str), encoding="utf-8")
    return MaterializeResult(metadata={"month": month, "status": result.status, "facts": len(result.facts), "text": result.text})


defs = Definitions(
    assets=[raw_snapshots, warehouse, dashboard_export, monthly_brief],
    asset_checks=[quality_checks],
    resources={"paths": PipelinePaths()},
)
